from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parent.parent
loader = SourceFileLoader('desktop', str(ROOT / 'tools/desktop.py'))
spec = spec_from_loader(loader.name, loader)
desktop = module_from_spec(spec)
loader.exec_module(desktop)


class DesktopTests(TestCase):
    def test_wayland_never_uses_partial_xwayland_window_list(self):
        env = {'XDG_SESSION_TYPE': 'wayland', 'DISPLAY': ':1', 'XDG_CURRENT_DESKTOP': 'GNOME'}
        self.assertEqual(desktop.detect(env), 'gnome')
        env['XDG_CURRENT_DESKTOP'] = 'KDE'
        self.assertEqual(desktop.detect(env), 'plasma')
        env['XDG_CURRENT_DESKTOP'] = 'unknown'
        self.assertEqual(desktop.detect(env), 'unsupported')

    def test_hyprland_and_explicit_x11(self):
        self.assertEqual(desktop.detect({'HYPRLAND_INSTANCE_SIGNATURE': 'fixture', 'WAYLAND_DISPLAY': 'wayland-1'}), 'hyprland')
        self.assertEqual(desktop.detect({'XDG_SESSION_TYPE': 'x11', 'DISPLAY': ':0', 'XDG_CURRENT_DESKTOP': 'XFCE'}), 'x11')
        self.assertEqual(desktop.detect({}), 'unsupported')
        self.assertEqual(desktop.detect({'XDG_SESSION_TYPE': 'x11', 'DISPLAY': ':0', 'XDG_CURRENT_DESKTOP': 'GNOME'}), 'gnome')

    def test_sway_uses_its_native_ipc(self):
        self.assertEqual(desktop.detect({'SWAYSOCK': '/fixture', 'WAYLAND_DISPLAY': 'wayland-1'}), 'sway')

    def test_x11_actions_use_window_protocol_requests(self):
        from unittest.mock import Mock
        backend = object.__new__(desktop.X11)
        window = Mock()
        backend.windows = {'42': window}
        backend.timestamp = Mock(return_value=1234)
        backend.request = Mock()
        backend.display = Mock()
        backend.xutil = Mock(IconicState=3)
        backend.error = Mock()
        backend.values = Mock(return_value=[])
        backend.action('42', 'minimize')
        backend.request.assert_called_once_with(window, 'WM_CHANGE_STATE', [3, 0, 0, 0, 0])
        backend.request.reset_mock()
        backend.action('42', 'restore')
        backend.request.assert_called_once_with(window, '_NET_ACTIVE_WINDOW', [2, 1234, 0, 0, 0])
        backend.request.reset_mock()
        backend.action('gone', 'close')
        backend.request.assert_not_called()

    def test_x11_timestamp_preserves_pending_model_changes(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        backend = object.__new__(desktop.X11)
        backend.x = SimpleNamespace(PropertyNotify=1, DestroyNotify=2, MapNotify=3, UnmapNotify=4)
        backend.xatom = SimpleNamespace(CARDINAL=6)
        backend.clock = Mock(id=7)
        backend.clock_serial = 0
        backend.atom = Mock(return_value=10)
        backend.display = Mock()
        backend.display.next_event.side_effect = [SimpleNamespace(type=2),
            SimpleNamespace(type=1, window=SimpleNamespace(id=7), atom=10, time=999)]
        backend.schedule_refresh = Mock()
        self.assertEqual(backend.timestamp(), 999)
        backend.schedule_refresh.assert_called_once()

    def test_x11_clock_tail_always_schedules_a_refresh(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        backend = object.__new__(desktop.X11)
        backend.x = SimpleNamespace(PropertyNotify=1)
        backend.xatom = SimpleNamespace(CARDINAL=6)
        backend.clock = Mock(id=7)
        backend.clock_serial = 0
        backend.atom = Mock(return_value=10)
        backend.display = Mock()
        backend.display.next_event.return_value = SimpleNamespace(type=1,
            window=SimpleNamespace(id=7), atom=10, time=999)
        backend.schedule_refresh = Mock()
        backend.timestamp()
        backend.schedule_refresh.assert_called_once()

    def test_x11_drains_events_buffered_by_property_queries(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        backend = object.__new__(desktop.X11)
        backend.x = SimpleNamespace(PropertyNotify=1, DestroyNotify=2, MapNotify=3, UnmapNotify=4)
        backend.display = Mock()
        backend.display.pending_events.side_effect = [1, 0, 1, 0, 0]
        backend.display.next_event.return_value = SimpleNamespace(type=2)
        backend.publish = Mock()
        backend.poll()
        self.assertEqual(backend.publish.call_count, 2)

    def test_kwin_action_cannot_inject_script(self):
        with self.assertRaises(ValueError):
            desktop.kwin_action('bad";throw 1', 'focus')
        with self.assertRaises(ValueError):
            desktop.kwin_action('{12345678-1234-1234-1234-123456789abc}', 'eval')
        script = desktop.kwin_action('{12345678-1234-1234-1234-123456789abc}', 'minimize')
        self.assertIn('w.minimized = true', script)

    def test_gnome_motion_uses_the_same_source(self):
        generated = (ROOT / 'integrations/gnome/motion.js').read_text()
        source = (ROOT / 'plugin/DockMotion.js').read_text().replace('.pragma library\n', '')
        self.assertEqual(generated, source.replace('function ', 'export function '))


class BridgeProtocolTests(TestCase):
    def test_batched_commands_and_sigterm_cleanup(self):
        import os
        import select
        import subprocess
        import sys
        import time
        program = """
import sys
sys.path.insert(0, sys.argv[1])
import desktop
from gi.repository import GLib
class Fixture:
    glib = GLib
    def __init__(self): print('ready', flush=True)
    def action(self, identifier, action):
        if identifier == 'gone': raise Exception('Synthetic native action failure')
        print(identifier + ':' + action, flush=True)
    def poll(self): pass
    def close(self): print('closed', flush=True)
desktop.X11 = Fixture
desktop.bridge('x11')
"""
        child = subprocess.Popen([sys.executable, '-c', program, str(ROOT / 'tools')],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            self.assertEqual(child.stdout.readline(), b'ready\n')
            child.stdin.write(b'{"id":"gone","action":"close"}\n{"id":"1","action":"focus"}\n{"id":"2","action":"close"}\n')
            child.stdin.flush()
            output = b''
            deadline = time.monotonic() + 2
            while output.count(b'\n') < 3 and time.monotonic() < deadline:
                if select.select([child.stdout], [], [], 0.1)[0]:
                    output += os.read(child.stdout.fileno(), 4096)
            self.assertEqual(output.splitlines(), [b'{"error":"Window action could not be completed"}', b'1:focus', b'2:close'])
            child.terminate()
            remaining, error = child.communicate(timeout=3)
            self.assertIn(b'closed', remaining)
            self.assertEqual(child.returncode, 0, error.decode())
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=3)


class SwayTests(TestCase):
    def test_hidden_and_visible_scratchpad_windows(self):
        app = {'id': 42, 'app_id': 'fixture.app', 'name': 'Fixture', 'focused': False,
            'scratchpad_state': 'fresh'}
        tree = {'type': 'root', 'nodes': [
            {'type': 'workspace', 'name': '__i3_scratch', 'floating_nodes': [app]},
            {'type': 'workspace', 'name': 'work', 'floating_nodes': [{**app, 'id': 43}]}]}
        rows = desktop.sway_windows(tree)
        self.assertTrue(rows[0]['minimized'])
        self.assertFalse(rows[1]['minimized'])
        self.assertEqual(rows[0]['tl']['address'], '42')

    def test_failed_sway_refresh_clears_stale_windows(self):
        from unittest.mock import Mock, patch
        import subprocess
        backend = object.__new__(desktop.Sway)
        backend.last = [{'cls': 'stale'}]
        backend.glib = Mock(SOURCE_REMOVE=False)
        with patch.object(desktop.subprocess, 'run', side_effect=subprocess.TimeoutExpired('swaymsg', 3)), patch.object(desktop, 'emit') as output:
            backend.refresh()
        self.assertIsNone(backend.last)
        output.assert_called_once_with(windows=[], error='Sway window information is unavailable')

    def test_window_criteria_never_accept_command_text(self):
        from unittest.mock import patch
        backend = object.__new__(desktop.Sway)
        with patch.object(desktop.subprocess, 'run') as command:
            with self.assertRaises(ValueError):
                backend.action('42] kill; [con_id=1', 'focus')
            command.assert_not_called()


class GnomeInstallTests(TestCase):
    def test_update_archives_old_source_across_filesystems(self):
        from unittest.mock import patch
        import errno
        import json
        import os
        import tempfile
        home = Path(tempfile.mkdtemp(prefix='dock-gnome-install-'))
        data, state = home / 'data', home / 'state'
        target = data / 'gnome-shell/extensions' / desktop.GNOME_ID
        target.mkdir(parents=True)
        (target / 'metadata.json').write_text(json.dumps({'uuid': desktop.GNOME_ID}))
        (target / 'extension.js').write_text('old source')
        original_rename = os.rename

        def rename(source, destination, *args, **kwargs):
            if str(destination).startswith(str(state)):
                raise OSError(errno.EXDEV, 'Synthetic cross-filesystem archive')
            return original_rename(source, destination, *args, **kwargs)

        with patch.dict(desktop.os.environ, {'XDG_DATA_HOME': str(data), 'XDG_STATE_HOME': str(state)}), patch.object(desktop.os, 'rename', side_effect=rename):
            desktop.install_gnome()
        self.assertIn('export default class', (target / 'extension.js').read_text())
        backups = list(state.glob('omarchy-dock/backups/*/' + desktop.GNOME_ID + '/extension.js'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), 'old source')
