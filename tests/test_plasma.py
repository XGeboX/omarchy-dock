from pathlib import Path
from types import ModuleType
from unittest import TestCase
from unittest.mock import Mock, patch
import json
import sys

from test_desktop import desktop


class PlasmaTests(TestCase):
    def setUp(self):
        self.scripts = []
        self.unloaded = []
        self.fail_run = False
        self.fail_unload = set()
        self.bus = Mock()
        self.scripting = Mock()
        self.bus.get_unique_name.return_value = ':1.fixture'
        self.bus.call_blocking.side_effect = self.load_script
        self.bus.get_object.side_effect = self.get_object
        self.scripting.unloadScript.side_effect = self.unload_script

        class Object:
            def __init__(self, _bus, _path):
                self.removed = False

            def remove_from_connection(self):
                self.removed = True

        dbus = ModuleType('dbus')
        service = ModuleType('dbus.service')
        dbus.service = service
        dbus.SessionBus = lambda: self.bus
        dbus.Interface = lambda value, _interface: value
        service.BusName = Mock()
        service.Object = Object
        service.method = lambda *_args, **_kwargs: lambda function: function
        mainloop = ModuleType('dbus.mainloop')
        glib = ModuleType('dbus.mainloop.glib')
        glib.DBusGMainLoop = Mock()
        gi = ModuleType('gi')
        repository = ModuleType('gi.repository')
        repository.GLib = Mock()
        gi.repository = repository
        self.modules = patch.dict(sys.modules, {'dbus': dbus, 'dbus.service': service,
            'dbus.mainloop': mainloop, 'dbus.mainloop.glib': glib, 'gi': gi, 'gi.repository': repository})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        with patch.object(desktop, 'emit') as output:
            self.backend = desktop.Plasma()
            output.assert_not_called()

    def load_script(self, *args, **kwargs):
        path, name = args[5]
        self.assertEqual(args[3:5], ('loadScript', 'ss'))
        self.assertTrue(Path(path).is_file())
        self.scripts.append((name, Path(path)))
        return len(self.scripts)

    def get_object(self, _bus, path):
        if path == '/Scripting':
            return self.scripting
        script = Mock()
        if self.fail_run:
            script.run.side_effect = RuntimeError('Synthetic native script failure')
        return script

    def unload_script(self, name, **_kwargs):
        if name in self.fail_unload:
            raise RuntimeError('Synthetic unload failure')
        self.unloaded.append(name)
        return True

    def test_window_updates_are_forwarded_once(self):
        rows = [{'cls': 'fixture', 'minimized': False, 'tl': {'address': 'fixture', 'title': 'Fixture'}}]
        with patch.object(desktop, 'emit') as output:
            self.backend.receiver.Update(json.dumps(rows))
            self.backend.receiver.Update(json.dumps(rows))
        output.assert_called_once_with(windows=rows)
        source = self.scripts[0][1].read_text()
        self.assertIn('dockOwner = ":1.fixture"', source)

    def test_action_runs_and_unloads_only_the_temporary_script(self):
        self.backend.action('{12345678-1234-1234-1234-123456789abc}', 'minimize')
        self.assertEqual(self.unloaded, [self.scripts[1][0]])
        self.assertEqual(self.backend.scripts, [self.scripts[0][0]])
        self.assertEqual(self.scripts[1][1].read_text(), '')

    def test_failed_action_still_unloads_the_temporary_script(self):
        self.fail_run = True
        with self.assertRaisesRegex(RuntimeError, 'script failure'):
            self.backend.action('{12345678-1234-1234-1234-123456789abc}', 'close')
        self.assertEqual(self.unloaded, [self.scripts[1][0]])
        self.assertEqual(self.backend.scripts, [self.scripts[0][0]])

    def test_failed_unload_is_retained_for_shutdown_retry(self):
        name = 'omarchy-dock-' + str(desktop.os.getpid()) + '-2'
        self.fail_unload.add(name)
        with self.assertRaisesRegex(RuntimeError, 'unload failure'):
            self.backend.action('{12345678-1234-1234-1234-123456789abc}', 'focus')
        self.assertIn(name, self.backend.scripts)
        self.fail_unload.clear()
        self.backend.close()
        self.assertIn(name, self.unloaded)
        self.assertTrue(self.backend.receiver.removed)
        self.assertEqual(self.backend.scripts, [])

    def test_shutdown_attempts_each_script_and_disconnects_after_failure(self):
        self.backend.scripts.append('another-script')
        self.fail_unload.add(self.backend.scripts[0])
        with self.assertRaises(RuntimeError):
            self.backend.close()
        self.assertIn('another-script', self.unloaded)
        self.assertTrue(self.backend.receiver.removed)
        self.assertEqual(len(self.backend.scripts), 1)
