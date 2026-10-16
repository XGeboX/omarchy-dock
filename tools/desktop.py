#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime, timezone
import argparse
import json
import os
import re
import signal
import shutil
import subprocess
import sys
import time
import tempfile

ROOT = Path(__file__).resolve().parent.parent


def detect(env):
    desktop = env.get('XDG_CURRENT_DESKTOP', '').lower().split(':')
    if any('gnome' in item for item in desktop):
        return 'gnome'
    wayland = env.get('XDG_SESSION_TYPE') == 'wayland' or bool(env.get('WAYLAND_DISPLAY'))
    if not wayland and env.get('DISPLAY'):
        return 'x11'
    if wayland:
        if env.get('HYPRLAND_INSTANCE_SIGNATURE'):
            return 'hyprland'
        if 'kde' in desktop:
            return 'plasma'
        if env.get('SWAYSOCK'):
            return 'sway'
    return 'unsupported'


def kwin_action(identifier, action):
    if not re.fullmatch(r'\{?[0-9a-fA-F-]{36}\}?', identifier):
        raise ValueError('Invalid window identifier')
    operations = {
        'focus': 'w.minimized = false; workspace.activeWindow = w;',
        'restore': 'w.minimized = false; workspace.activeWindow = w;',
        'minimize': 'w.minimized = true;',
        'close': 'w.closeWindow();',
    }
    if action not in operations:
        raise ValueError('Invalid window action')
    return ('var windows = workspace.windowList();\n'
            'for (var i = 0; i < windows.length; i++) {\n'
            'var w = windows[i]; if (String(w.internalId) === ' + json.dumps(identifier) + ') { '
            + operations[action] + ' break; } }\n')


def emit(**data):
    print(json.dumps(data, separators=(',', ':')), flush=True)


class Plasma:
    def __init__(self):
        import dbus
        import dbus.service
        from dbus.mainloop.glib import DBusGMainLoop
        from gi.repository import GLib

        DBusGMainLoop(set_as_default=True)
        self.glib = GLib
        self.bus = dbus.SessionBus()
        self.scripting = dbus.Interface(self.bus.get_object('org.kde.KWin', '/Scripting'), 'org.kde.kwin.Scripting')
        self.name = dbus.service.BusName('org.xgebox.OmarchyDock', self.bus, do_not_queue=True)
        self.scripts = []
        self.stage = Path(tempfile.mkdtemp(prefix='omarchy-dock-kwin-'))
        self.serial = 0
        self.last = None
        owner = self

        class Receiver(dbus.service.Object):
            @dbus.service.method('org.xgebox.OmarchyDock', in_signature='s', out_signature='')
            def Update(self, text):
                rows = json.loads(str(text))
                if rows != owner.last:
                    owner.last = rows
                    emit(windows=rows)

        self.receiver = Receiver(self.bus, '/org/xgebox/OmarchyDock')
        self.load((ROOT / 'integrations/plasma/windows.js').read_text(), persistent=True)

    def load(self, source, persistent=False):
        import dbus
        self.serial += 1
        name = 'omarchy-dock-' + str(os.getpid()) + '-' + str(self.serial)
        path = self.stage / ('windows.js' if persistent else 'action.js')
        if persistent:
            source = "var dockScript = " + json.dumps(name) + ";\nvar dockOwner = " + json.dumps(str(self.bus.get_unique_name())) + ";\n" + source
        path.write_text(source)
        index = int(self.bus.call_blocking('org.kde.KWin', '/Scripting',
            'org.kde.kwin.Scripting', 'loadScript', 'ss', (str(path), name), timeout=3))
        if index < 0:
            raise RuntimeError('KWin refused the dock script')
        self.scripts.append(name)
        script = dbus.Interface(self.bus.get_object('org.kde.KWin', '/Scripting/Script' + str(index)), 'org.kde.kwin.Script')
        script.run(timeout=3)
        if not persistent:
            self.scripting.unloadScript(name, timeout=3)
            self.scripts.remove(name)
            # Action scripts contain no user data, and are reused to avoid an unbounded cache.
            path.write_text('')

    def poll(self):
        context = self.glib.MainContext.default()
        while context.pending():
            context.iteration(False)

    def action(self, identifier, action):
        self.load(kwin_action(identifier, action))

    def close(self):
        for name in self.scripts:
            self.scripting.unloadScript(name, timeout=3)
        self.receiver.remove_from_connection()


def sway_windows(tree):
    result = []

    def visit(node, workspace=''):
        if node.get('type') == 'workspace':
            workspace = node.get('name', '')
        cls = node.get('app_id') or (node.get('window_properties') or {}).get('class')
        if cls:
            result.append({'cls': cls, 'minimized': workspace == '__i3_scratch',
                'tl': {'address': str(node['id']), 'title': node.get('name') or '',
                    'activated': bool(node.get('focused'))}})
        for child in node.get('nodes', []) + node.get('floating_nodes', []):
            visit(child, workspace)

    visit(tree)
    return result


class Sway:
    def __init__(self):
        from gi.repository import GLib
        self.glib = GLib
        self.last = None
        self.idle = 0
        self.on_disconnect = lambda: None
        self.subscription = subprocess.Popen(['swaymsg', '-m', '-r', '-t', 'subscribe', '["window","workspace"]'],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.watch = GLib.io_add_watch(self.subscription.stdout.fileno(),
            GLib.IOCondition.IN | GLib.IOCondition.HUP, self.changed)
        self.refresh()

    def changed(self, _source, _condition):
        data = os.read(self.subscription.stdout.fileno(), 65536)
        if not data:
            emit(windows=[])
            emit(error='The Sway session disconnected')
            self.on_disconnect()
            return self.glib.SOURCE_REMOVE
        if not self.idle:
            self.idle = self.glib.idle_add(self.refresh)
        return self.glib.SOURCE_CONTINUE

    def refresh(self):
        self.idle = 0
        try:
            result = subprocess.run(['swaymsg', '-r', '-t', 'get_tree'], capture_output=True,
                text=True, timeout=3, check=True)
            windows = sway_windows(json.loads(result.stdout))
        except (OSError, ValueError, subprocess.SubprocessError):
            self.last = None
            emit(windows=[], error='Sway window information is unavailable')
            return self.glib.SOURCE_REMOVE
        if windows != self.last:
            self.last = windows
            emit(windows=windows)
        return self.glib.SOURCE_REMOVE

    def action(self, identifier, action):
        if not re.fullmatch(r'[0-9]+', identifier):
            raise ValueError('Invalid window identifier')
        selector = '[con_id=' + identifier + '] '
        operations = {'focus': selector + 'focus', 'minimize': selector + 'move scratchpad',
            'restore': selector + 'move container to workspace current; ' + selector + 'focus',
            'close': selector + 'kill'}
        if action not in operations:
            raise ValueError('Invalid window action')
        result = subprocess.run(['swaymsg', '-r', operations[action]], capture_output=True,
            text=True, timeout=3, check=True)
        if not all(item.get('success') for item in json.loads(result.stdout)):
            raise RuntimeError('Sway could not complete the window action')

    def close(self):
        for identifier in [self.watch, self.idle]:
            source = self.glib.MainContext.default().find_source_by_id(identifier) if identifier else None
            if source is not None:
                source.destroy()
        self.subscription.stdout.close()
        if self.subscription.poll() is None:
            self.subscription.terminate()
            try:
                self.subscription.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.subscription.kill()
                self.subscription.wait()


class X11:
    def __init__(self):
        from gi.repository import GLib
        from Xlib import X, Xatom, Xutil, display, error
        from Xlib.protocol import event

        self.glib, self.x, self.xatom, self.xutil = GLib, X, Xatom, Xutil
        self.error, self.event = error, event
        self.display = display.Display()
        self.root = self.display.screen().root
        self.atoms = {}
        self.windows = {}
        self.last = None
        self.relevant = {self.atom(name) for name in ['_NET_CLIENT_LIST', '_NET_ACTIVE_WINDOW',
            '_NET_WM_STATE', '_NET_WM_WINDOW_TYPE', '_NET_WM_NAME', 'WM_NAME', 'WM_CLASS']}
        self.clock_serial = 0
        self.idle = 0
        self.clock = self.root.create_window(0, 0, 1, 1, 0, 0,
            X.InputOnly, X.CopyFromParent, event_mask=X.PropertyChangeMask)
        self.root.change_attributes(event_mask=X.PropertyChangeMask | X.SubstructureNotifyMask)
        self.watch = GLib.io_add_watch(self.display.fileno(), GLib.IOCondition.IN, self.changed)
        self.publish()
        self.poll()

    def atom(self, name):
        if name not in self.atoms:
            self.atoms[name] = self.display.intern_atom(name)
        return self.atoms[name]

    def values(self, window, name):
        value = window.get_full_property(self.atom(name), self.x.AnyPropertyType)
        return list(value.value) if value is not None else []

    def changed(self, _source, _condition):
        self.poll()
        return self.glib.SOURCE_CONTINUE

    def relevant_event(self, value):
        if value.type == self.x.PropertyNotify:
            return value.atom in self.relevant
        return value.type in [self.x.DestroyNotify, self.x.MapNotify, self.x.UnmapNotify]

    def schedule_refresh(self):
        if not self.idle:
            self.idle = self.glib.idle_add(self.refresh)

    def refresh(self):
        self.idle = 0
        self.publish()
        self.poll()
        return self.glib.SOURCE_REMOVE

    def poll(self):
        # Property roundtrips can queue events in Xlib after the socket is drained.
        while True:
            changed = False
            while self.display.pending_events():
                changed |= self.relevant_event(self.display.next_event())
            if not changed:
                return
            self.publish()

    def publish(self):
        identifiers = self.values(self.root, '_NET_CLIENT_LIST')
        active = self.values(self.root, '_NET_ACTIVE_WINDOW')
        alive = {}
        rows = []
        for identifier in identifiers:
            window = self.display.create_resource_object('window', identifier)
            try:
                window.change_attributes(event_mask=self.x.PropertyChangeMask | self.x.StructureNotifyMask,
                    onerror=self.error.CatchError(self.error.BadWindow))
                state = self.values(window, '_NET_WM_STATE')
                kind = self.values(window, '_NET_WM_WINDOW_TYPE')
                if self.atom('_NET_WM_STATE_SKIP_TASKBAR') in state or any(self.atom(name) in kind
                        for name in ['_NET_WM_WINDOW_TYPE_DOCK', '_NET_WM_WINDOW_TYPE_DESKTOP']):
                    continue
                classes = window.get_wm_class()
                cls = classes[1] if classes else ''
                if not cls:
                    continue
                title = window.get_full_property(self.atom('_NET_WM_NAME'), self.atom('UTF8_STRING'))
                text = bytes(title.value).decode('utf-8', 'replace') if title is not None else (window.get_wm_name() or '')
                key = str(identifier)
                alive[key] = window
                rows.append({'cls': cls, 'minimized': self.atom('_NET_WM_STATE_HIDDEN') in state,
                    'tl': {'address': key, 'title': text, 'activated': bool(active and active[0] == identifier)}})
            except self.error.BadWindow:
                continue
        self.windows = alive
        if rows != self.last:
            self.last = rows
            emit(windows=rows)

    def timestamp(self):
        self.clock_serial = (self.clock_serial + 1) & 0xffffffff
        clock_atom = self.atom('_OMARCHY_DOCK_TIMESTAMP')
        self.clock.change_property(clock_atom, self.xatom.CARDINAL, 32, [self.clock_serial])
        self.display.flush()
        while True:
            value = self.display.next_event()
            if value.type == self.x.PropertyNotify and value.window.id == self.clock.id and value.atom == clock_atom:
                self.schedule_refresh()
                return value.time

    def request(self, window, name, values):
        message = self.event.ClientMessage(window=window, client_type=self.atom(name), data=(32, values))
        self.root.send_event(message, event_mask=self.x.SubstructureRedirectMask | self.x.SubstructureNotifyMask)

    def action(self, identifier, action):
        window = self.windows.get(identifier)
        if window is None:
            return
        timestamp = self.timestamp()
        if action in ['focus', 'restore']:
            workspace = self.values(window, '_NET_WM_DESKTOP')
            if workspace and workspace[0] != 0xffffffff:
                self.request(self.root, '_NET_CURRENT_DESKTOP', [workspace[0], timestamp, 0, 0, 0])
            window.map(onerror=self.error.CatchError(self.error.BadWindow))
            self.request(window, '_NET_ACTIVE_WINDOW', [2, timestamp, 0, 0, 0])
        elif action == 'minimize':
            self.request(window, 'WM_CHANGE_STATE', [self.xutil.IconicState, 0, 0, 0, 0])
        elif action == 'close':
            self.request(window, '_NET_CLOSE_WINDOW', [timestamp, 2, 0, 0, 0])
        else:
            raise ValueError('Invalid window action')
        self.display.flush()

    def close(self):
        for identifier in [self.watch, self.idle]:
            source = self.glib.MainContext.default().find_source_by_id(identifier) if identifier else None
            if source is not None:
                source.destroy()
        self.clock.destroy()
        self.display.close()


def bridge(name):
    backend = {'plasma': Plasma, 'sway': Sway, 'x11': X11}[name]()
    glib = backend.glib
    loop = glib.MainLoop()
    if name == 'sway':
        backend.on_disconnect = loop.quit
    pending = b''

    def read_commands(_source, _condition):
        nonlocal pending
        data = os.read(sys.stdin.fileno(), 65536)
        if not data:
            loop.quit()
            return glib.SOURCE_REMOVE
        pending += data
        if len(pending) > 1048576:
            emit(error='Dock command buffer exceeded its limit')
            loop.quit()
            return glib.SOURCE_REMOVE
        while b'\n' in pending:
            line, pending = pending.split(b'\n', 1)
            try:
                value = json.loads(line)
                backend.action(value['id'], value['action'])
            except Exception:
                # Native windows can disappear between a menu click and dispatch.
                # Keep the command watch alive after backend-specific exceptions.
                emit(error='Window action could not be completed')
        return glib.SOURCE_CONTINUE

    def terminate():
        loop.quit()
        return glib.SOURCE_REMOVE

    sources = [glib.io_add_watch(sys.stdin.fileno(), glib.IOCondition.IN | glib.IOCondition.HUP, read_commands),
        glib.unix_signal_add(glib.PRIORITY_DEFAULT, signal.SIGTERM, terminate)]
    try:
        loop.run()
    finally:
        for identifier in sources:
            source = glib.MainContext.default().find_source_by_id(identifier)
            if source is not None:
                source.destroy()
        backend.close()


def doctor(name):
    requirements = ['quickshell'] if name not in ['gnome', 'unsupported'] else []
    if name == 'sway':
        requirements += ['swaymsg']
    if name == 'gnome':
        requirements += ['gnome-extensions']
    missing = [command for command in requirements if shutil.which(command) is None]
    if name in ['plasma', 'x11', 'sway']:
        for module in (['dbus', 'gi'] if name == 'plasma' else ['gi']):
            try:
                __import__(module)
            except ImportError:
                missing.append('Python module ' + module)
    if name == 'x11':
        try:
            __import__('Xlib')
        except ImportError:
            missing.append('Python module Xlib')
    return {'desktop': name, 'scope': 'dependency checks only', 'missing': missing, 'ready': name != 'unsupported' and not missing}


GNOME_ID = 'omarchy-dock@xgebox.github.io'


def install_gnome():
    destination = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share') / 'gnome-shell/extensions' / GNOME_ID
    source = ROOT / 'integrations/gnome'
    destination.parent.mkdir(parents=True, exist_ok=True)
    if os.path.lexists(destination):
        if destination.is_symlink() or not destination.is_dir():
            raise ValueError('A different installation occupies the GNOME extension path')
        metadata = json.loads((destination / 'metadata.json').read_text())
        if metadata.get('uuid') != GNOME_ID:
            raise ValueError('A different extension occupies the install path')
    staging = Path(tempfile.mkdtemp(prefix='omarchy-dock-stage-', dir=destination.parent.parent))
    for name in ['extension.js', 'metadata.json', 'motion.js', 'stylesheet.css']:
        shutil.copy2(source / name, staging / name)
    shutil.copy2(ROOT / 'LICENSE', staging / 'LICENSE')
    if os.path.lexists(destination):
        state = Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state') / 'omarchy-dock/backups'
        state.mkdir(parents=True, exist_ok=True)
        backup = Path(tempfile.mkdtemp(prefix='gnome-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-'), dir=state)) / GNOME_ID
        shutil.move(str(destination), str(backup))
        try:
            staging.rename(destination)
        except OSError:
            shutil.move(str(backup), str(destination))
            raise
    else:
        staging.rename(destination)
    print('GNOME extension installed. Log out and back in if this is the first installation, then run omarchy-dock run.')


def main():
    parser = argparse.ArgumentParser(description='Standalone dock launcher and desktop diagnostics')
    parser.add_argument('action', choices=['run', 'doctor', 'bridge', 'install-gnome', 'disable-gnome'], nargs='?', default='doctor')
    parser.add_argument('backend', choices=['hyprland', 'wlr', 'sway', 'x11', 'plasma', 'gnome', 'unsupported'], nargs='?')
    args = parser.parse_args()
    name = args.backend or detect(os.environ)
    try:
        if args.action == 'install-gnome':
            install_gnome()
            return 0
        if args.action == 'disable-gnome':
            subprocess.run(['gnome-extensions', 'disable', GNOME_ID], check=True, timeout=10)
            return 0
        if args.action == 'bridge':
            if name not in ['x11', 'plasma', 'sway']:
                raise ValueError('Only X11, Plasma and Sway use the process bridge')
            bridge(name)
            return 0
        report = doctor(name)
        if args.action == 'doctor':
            print(json.dumps(report, indent=2))
            return 0 if report['ready'] else 1
        if not report['ready']:
            raise RuntimeError('Desktop integration is unavailable: ' + json.dumps(report))
        if name == 'gnome':
            subprocess.run(['gnome-extensions', 'enable', GNOME_ID], check=True, timeout=10)
            for _ in range(20):
                info = subprocess.run(['gnome-extensions', 'info', GNOME_ID], capture_output=True,
                    text=True, timeout=5, env={**os.environ, 'LC_ALL': 'C'})
                if re.search(r'^\s*State:\s*(ACTIVE|ENABLED)\s*$', info.stdout, re.MULTILINE):
                    print('Enabled the native GNOME dock extension')
                    return 0
                time.sleep(0.1)
            raise RuntimeError('GNOME did not confirm an active dock. Log out and back in after first installation, then retry.')
        config = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'omarchy-dock/config.json'
        config.parent.mkdir(parents=True, exist_ok=True)
        if not config.exists():
            with config.open('x') as file:
                file.write((ROOT / 'config.example.json').read_text())
        value = json.loads(config.read_text())
        if not isinstance(value, dict) or not isinstance(value.get('pinned', []), list):
            raise ValueError('Invalid dock configuration; it has been preserved')
        os.environ['OMARCHY_DOCK_BACKEND'] = name
        os.execvp('quickshell', ['quickshell', '-p', str(ROOT / 'shell.qml')])
    except (OSError, ValueError, RuntimeError, ImportError, subprocess.SubprocessError) as error:
        print('omarchy-dock: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
