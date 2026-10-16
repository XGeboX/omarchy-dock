#!/usr/bin/env python3
from pathlib import Path
import argparse
import ctypes
import json
import os
import resource
import shutil
import subprocess
import sys
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description='Test the dock in an isolated X11 session with synthetic windows')
    parser.add_argument('--prefix', type=Path, default=Path('/'))
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    stage = Path(tempfile.mkdtemp(prefix='dock-x11-integration-'))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    env = os.environ.copy()
    for key in ['DISPLAY', 'WAYLAND_DISPLAY', 'DBUS_SESSION_BUS_ADDRESS', 'HYPRLAND_INSTANCE_SIGNATURE', 'SWAYSOCK']:
        env.pop(key, None)
    for name in ['home', 'config', 'data', 'runtime', 'cache', 'state']:
        (stage / name).mkdir(mode=0o700)
    env.update(HOME=str(stage / 'home'), XDG_CONFIG_HOME=str(stage / 'config'),
        XDG_DATA_HOME=str(stage / 'data'), XDG_DATA_DIRS=str(stage / 'data'),
        XDG_CONFIG_DIRS=str(stage / 'config'), XDG_CACHE_HOME=str(stage / 'cache'),
        XDG_STATE_HOME=str(stage / 'state'), XDG_RUNTIME_DIR=str(stage / 'runtime'),
        QT_QPA_PLATFORM='xcb', QT_QPA_PLATFORMTHEME='generic', QT_STYLE_OVERRIDE='Fusion',
        QT_QUICK_BACKEND='software', LIBGL_ALWAYS_SOFTWARE='1',
        OMARCHY_DOCK_BACKEND='x11', XDG_SESSION_TYPE='x11')
    if args.prefix != Path('/'):
        env.update(LD_LIBRARY_PATH=str(args.prefix / 'usr/lib'),
            GI_TYPELIB_PATH=str(args.prefix / 'usr/lib/girepository-1.0'),
            PYTHONPATH=str(args.prefix / ('usr/lib/python' + str(sys.version_info.major) + '.' + str(sys.version_info.minor) + '/site-packages')))
    if env.get('PYTHONPATH'):
        sys.path[:0] = env['PYTHONPATH'].split(os.pathsep)
    rc = stage / 'rc.xml'
    rc.write_text('<openbox_config xmlns="http://openbox.org/3.4/rc"><desktops><number>2</number></desktops></openbox_config>')
    window_source = stage / 'window.qml'
    window_source.write_text('import QtQuick\nimport QtQuick.Window\nWindow { visible: true; width: 240; height: 160; title: "Dock test fixture" }\n')
    config = stage / 'config/omarchy-dock/config.json'
    config.parent.mkdir()
    applications = stage / 'data/applications'
    applications.mkdir()
    theme = stage / 'data/icons/hicolor'
    (theme / '48x48/apps').mkdir(parents=True)
    (theme / 'index.theme').write_text('[Icon Theme]\\nName=Hicolor\\nDirectories=48x48/apps\\n[48x48/apps]\\nSize=48\\nContext=Applications\\nType=Fixed\\n'.replace('\\n', '\n'))
    for name in ['application-x-executable', 'image-missing']:
        shutil.copyfile(root / 'tests/fixtures/Browser.svg', theme / '48x48/apps' / (name + '.svg'))
    qml = next(path for path in [Path('/usr/lib/qt6/bin/qml'), Path('/usr/lib64/qt6/bin/qml')] if path.is_file())
    (applications / 'fixture.desktop').write_text('[Desktop Entry]\nType=Application\nName=Fixture\nExec="' + str(qml)
        + '" "' + str(window_source) + '"\nIcon=' + str(root / 'tests/fixtures/Browser.svg') + '\n')
    children, logs = [], []
    backend = None
    try:
        log = (stage / 'dbus.log').open('w'); logs.append(log)
        bus = subprocess.Popen(['dbus-daemon', '--session', '--nofork', '--print-address=1'], env=env, stdout=subprocess.PIPE, stderr=log)
        children.append(bus)
        import select
        if not select.select([bus.stdout], [], [], 5)[0]:
            raise RuntimeError('The isolated session bus did not become ready')
        env['DBUS_SESSION_BUS_ADDRESS'] = bus.stdout.readline().decode().strip()
        read_fd, write_fd = os.pipe()
        log = (stage / 'xvfb.log').open('w'); logs.append(log)
        server = subprocess.Popen([str(args.prefix / 'usr/bin/Xvfb'), '-displayfd', str(write_fd),
            '-screen', '0', '1280x720x24', '-nolisten', 'tcp'], env=env,
            stdout=log, stderr=log, pass_fds=(write_fd,))
        children.append(server); os.close(write_fd)
        import select
        if not select.select([read_fd], [], [], 8)[0]:
            raise RuntimeError('The isolated X server did not become ready')
        display = os.read(read_fd, 30).decode().strip(); os.close(read_fd)
        if not display.isdigit():
            raise RuntimeError('Invalid isolated display')
        env['DISPLAY'] = ':' + display
        # Only this test process acquires the synthetic display. Host sessions and
        # user application directories are absent from all child environments.
        os.environ.update({key: value for key, value in env.items() if key in ['DISPLAY',
            'XDG_RUNTIME_DIR', 'GI_TYPELIB_PATH', 'LD_LIBRARY_PATH', 'PYTHONPATH']})
        os.environ.pop('WAYLAND_DISPLAY', None)
        wm_env = env.copy()
        wm_env['XDG_DATA_DIRS'] = str(args.prefix / 'usr/share')
        log = (stage / 'openbox.log').open('w'); logs.append(log)
        wm = subprocess.Popen([str(args.prefix / 'usr/bin/openbox'), '--config-file', str(rc)],
            env=wm_env, stdout=log, stderr=log); children.append(wm)
        time.sleep(0.5)
        if wm.poll() is not None:
            raise RuntimeError('The isolated window manager stopped')
        import desktop
        backend = desktop.X11()

        def wait_for(predicate):
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                backend.poll()
                if predicate(): return
                time.sleep(0.02)
            raise AssertionError('Timed out waiting for a synthetic window transition')

        def fixture():
            return next((window for window in (backend.last or []) if window['tl']['title'] == 'Dock test fixture'), None)

        log = (stage / 'fixture.log').open('w'); logs.append(log)
        app = subprocess.Popen([str(qml), str(window_source)], env=env, stdout=log, stderr=log); children.append(app)
        wait_for(lambda: fixture() is not None)
        first = fixture()
        cls = first['cls']
        config.write_text(json.dumps({'pinned': [{'class': cls, 'desktop': 'fixture'}], 'iconSize': 52, 'magnification': 1.55}))
        log = (stage / 'quickshell.log').open('w'); logs.append(log)
        shell = subprocess.Popen(['quickshell', '-p', str(root / 'shell.qml')], env=env, stdout=log, stderr=log); children.append(shell)
        time.sleep(1)
        assert shell.poll() is None, 'The standalone dock did not stay running'
        assert 'Configuration Loaded' in (stage / 'quickshell.log').read_text()
        backend.action(first['tl']['address'], 'focus')
        wait_for(lambda: fixture()['tl']['activated'])
        time.sleep(0.2)
        xlib = ctypes.CDLL('libX11.so.6')
        xtest = ctypes.CDLL('libXtst.so.6')
        xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]; xlib.XOpenDisplay.restype = ctypes.c_void_p
        xlib.XFlush.argtypes = [ctypes.c_void_p]
        xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]
        xtest.XTestFakeMotionEvent.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ulong]
        xtest.XTestFakeButtonEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
        connection = xlib.XOpenDisplay(env['DISPLAY'].encode())
        assert connection
        def click(minimized_count=0):
            rest = (1 + minimized_count) * 59 + 30
            x = round((1280 - rest) / 2 + 35)
            xtest.XTestFakeMotionEvent(connection, 0, x, 670, 0); xlib.XFlush(connection)
            time.sleep(0.08)
            xtest.XTestFakeButtonEvent(connection, 1, 1, 0)
            xtest.XTestFakeButtonEvent(connection, 1, 0, 0); xlib.XFlush(connection)
        click()
        wait_for(lambda: fixture()['minimized'])
        print('Real dock click minimized the synthetic window')
        time.sleep(0.2)
        click(1)
        wait_for(lambda: not fixture()['minimized'] and fixture()['tl']['activated'])
        print('Real dock click restored and focused the synthetic window')
        backend.action(first['tl']['address'], 'close')
        wait_for(lambda: fixture() is None)
        time.sleep(0.3)
        click()
        wait_for(lambda: fixture() is not None)
        print('Real dock click launched the synthetic desktop entry')
        backend.action(fixture()['tl']['address'], 'close')
        wait_for(lambda: fixture() is None)
        xlib.XCloseDisplay(connection)
        output = (stage / 'quickshell.log').read_text()
        assert 'WARN scene' not in output and 'ERROR' not in output and 'Component is not ready' not in output, output
        print('Standalone X11 integration passed. Logs: ' + str(stage))
    finally:
        if backend is not None:
            for window in list(backend.last or []):
                if window['tl']['title'] == 'Dock test fixture':
                    backend.action(window['tl']['address'], 'close')
            backend.close()
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
                try: child.wait(timeout=3)
                except subprocess.TimeoutExpired: child.kill(); child.wait()
        for log in logs: log.close()


if __name__ == '__main__':
    main()
