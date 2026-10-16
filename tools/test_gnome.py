#!/usr/bin/env python3
from pathlib import Path
import argparse
import json
import os
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
UUID = 'omarchy-dock@xgebox.github.io'


def worker(stage, prefix):
    children = []
    try:
        with (stage / 'compositor.log').open('w') as log:
            shell = subprocess.Popen([str(prefix / 'usr/bin/gnome-shell'), '--headless', '--wayland',
                '--no-x11', '--wayland-display', 'dock-test', '--virtual-monitor', '1280x720'], stdout=log, stderr=log)
            children.append(shell)
            deadline = time.monotonic() + 8
            while not (stage / 'runtime/dock-test').exists():
                if shell.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError('The isolated GNOME Shell did not start')
                time.sleep(0.1)
            os.environ.update(WAYLAND_DISPLAY='dock-test', GDK_BACKEND='wayland')
            with (stage / 'fixture.log').open('w') as app_log:
                app = subprocess.Popen([sys.executable, str(stage / 'fixture.py')], stdout=app_log, stderr=app_log)
                children.append(app)
                time.sleep(0.5)
                command = str(prefix / 'usr/bin/gnome-extensions')
                subprocess.run([command, 'enable', UUID], check=True, timeout=8, capture_output=True)
                deadline = time.monotonic() + 15
                while not (stage / 'result.json').exists():
                    if shell.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError('Native GNOME checks did not finish')
                    time.sleep(0.1)
                result = json.loads((stage / 'result.json').read_text())
                if 'error' in result:
                    raise AssertionError(result['error'])
                info = subprocess.run([command, 'info', UUID], check=True, timeout=5, capture_output=True, text=True)
                if 'State: ACTIVE' not in info.stdout:
                    raise AssertionError('GNOME did not report the extension active')
                subprocess.run([command, 'disable', UUID], check=True, timeout=5, capture_output=True)
                print(json.dumps(result), flush=True)
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()


def main():
    parser = argparse.ArgumentParser(description='Exercise the native dock in a private headless GNOME session')
    parser.add_argument('--prefix', type=Path, default=Path('/'))
    parser.add_argument('--worker', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    if args.worker:
        worker(args.worker, args.prefix)
        return
    stage = Path(tempfile.mkdtemp(prefix='dock-gnome-integration-'))
    for name in ['home', 'config', 'data', 'runtime', 'cache', 'state', 'schemas']:
        (stage / name).mkdir(mode=0o700)
    for directory in [Path('/usr/share/glib-2.0/schemas'), args.prefix / 'usr/share/glib-2.0/schemas']:
        for source in directory.glob('*'):
            if source.suffix in ['.xml', '.override']:
                shutil.copy2(source, stage / 'schemas' / source.name)
    subprocess.run(['glib-compile-schemas', str(stage / 'schemas')], check=True)
    services = stage / 'data/dbus-1/services'
    services.mkdir(parents=True)
    if args.prefix != Path('/'):
        helper = stage / 'org.gnome.Shell.Extensions'
        source = args.prefix / 'usr/share/gnome-shell/org.gnome.Shell.Extensions'
        helper.write_text(source.read_text().replace("prefix: '/usr'", "prefix: '" + str(args.prefix / 'usr') + "'")
            .replace("libdir: '/usr/lib'", "libdir: '" + str(args.prefix / 'usr/lib') + "'"))
        source = args.prefix / 'usr/share/dbus-1/services/org.gnome.Shell.Extensions.service'
        (services / source.name).write_text(source.read_text().replace('/usr/share/gnome-shell/org.gnome.Shell.Extensions', str(helper)))
    extension = stage / 'data/gnome-shell/extensions' / UUID
    shutil.copytree(ROOT / 'integrations/gnome', extension)
    (extension / 'extension.js').rename(extension / 'dock.js')
    wrapper = (ROOT / 'tests/GnomeIntegration.js.in').read_text()
    for key, value in {'__RESULT__': stage / 'result.json', '__IMAGE__': stage / 'gnome-dock.png'}.items():
        wrapper = wrapper.replace(key, json.dumps(str(value)))
    (extension / 'extension.js').write_text(wrapper)
    (stage / 'fixture.py').write_text('''import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
app = Gtk.Application(application_id='io.github.xgebox.DockFixture')
def activate(app):
    window = Gtk.ApplicationWindow(application=app, title='Dock native fixture')
    window.set_default_size(240, 160)
    window.show_all()
app.connect('activate', activate)
app.run([])
''')
    applications = stage / 'data/applications'
    applications.mkdir()
    (applications / 'io.github.xgebox.DockFixture.desktop').write_text('[Desktop Entry]\nType=Application\nName=Fixture\nExec="'
        + sys.executable + '" "' + str(stage / 'fixture.py') + '"\nIcon=' + str(ROOT / 'tests/fixtures/Browser.svg') + '\n')
    config = stage / 'config/omarchy-dock/config.json'
    config.parent.mkdir()
    config.write_text(json.dumps({'pinned': [{'class': 'fixture', 'desktop': 'io.github.xgebox.DockFixture'},
        {'class': 'second', 'name': 'Second', 'command': 'true', 'icon': str(ROOT / 'tests/fixtures/Files.svg')}], 'iconSize': 52}))
    env = {key: os.environ[key] for key in ['PATH', 'LANG'] if key in os.environ}
    library = args.prefix / 'usr/lib'
    env.update(HOME=str(stage / 'home'), XDG_CONFIG_HOME=str(stage / 'config'), XDG_DATA_HOME=str(stage / 'data'),
        XDG_DATA_DIRS=str(args.prefix / 'usr/share') + ':/usr/share', XDG_CACHE_HOME=str(stage / 'cache'),
        XDG_STATE_HOME=str(stage / 'state'), XDG_RUNTIME_DIR=str(stage / 'runtime'), XDG_CONFIG_DIRS=str(stage / 'config'),
        GSETTINGS_SCHEMA_DIR=str(stage / 'schemas'), GSETTINGS_BACKEND='memory', LC_ALL='C',
        LD_LIBRARY_PATH=':'.join(map(str, [library / 'gnome-shell', library / 'mutter-18', library])),
        GI_TYPELIB_PATH=':'.join(map(str, [library / 'gnome-shell', library / 'gnome-shell/girepository-1.0',
            library / 'mutter-18', library / 'girepository-1.0'])), LIBGL_ALWAYS_SOFTWARE='1',
        GNOME_SHELL_DATADIR=str(args.prefix / 'usr/share/gnome-shell'), XDG_SESSION_TYPE='wayland', XDG_CURRENT_DESKTOP='GNOME')
    with (stage / 'session.log').open('w') as log:
        process = subprocess.Popen(['dbus-run-session', '--', sys.executable, str(Path(__file__).resolve()),
            '--prefix', str(args.prefix), '--worker', str(stage)], env=env, stdout=log, stderr=log, start_new_session=True)
        try:
            process.wait(timeout=35)
            if process.returncode:
                raise RuntimeError('Native GNOME checks failed; inspect ' + str(stage))
        finally:
            # This group belongs exclusively to this private test session and its bus helpers.
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    print('Native GNOME integration passed. Artifacts: ' + str(stage))


if __name__ == '__main__':
    main()
