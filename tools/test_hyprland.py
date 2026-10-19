#!/usr/bin/env python3
from pathlib import Path
import argparse
import json
import os
import resource
import shutil
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description='Exercise only temporary fixture windows on the current Hyprland desktop')
    parser.add_argument('--live', action='store_true', required=True,
        help='Allow a temporary visible fixture window; existing applications and desktop preferences are not changed')
    parser.add_argument('--omarchy-shell', type=Path, help='Also test the installed Omarchy theme interface at this shell directory')
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    result = subprocess.run(['hyprctl', '-j', 'instances'], check=True, capture_output=True, text=True, timeout=5)
    eligible = []
    for row in json.loads(result.stdout):
        process = Path('/proc') / str(row.get('pid'))
        try:
            if process.stat().st_uid == os.getuid() and (process / 'comm').read_text().strip() == 'Hyprland':
                eligible.append(row)
        except OSError:
            continue
    if len(eligible) != 1:
        raise RuntimeError('Exactly one owned Hyprland instance is required for this live test')
    instance = eligible[0]
    lock = json.loads(subprocess.run(['hyprctl', '-i', instance['instance'], '-j', 'locked'],
        check=True, capture_output=True, text=True, timeout=5).stdout)
    if not isinstance(lock.get('locked'), bool):
        raise RuntimeError('Cannot determine the session lock state')
    if lock['locked']:
        raise RuntimeError('The desktop is locked; unlock it before testing native focus')
    stage = Path(tempfile.mkdtemp(prefix='dock-hyprland-native-'))
    for name in ['home', 'config', 'data', 'state', 'cache']:
        (stage / name).mkdir(mode=0o700)
    shutil.copytree(ROOT / 'plugin/backends', stage / 'backends')
    if args.omarchy_shell:
        commons = args.omarchy_shell / 'Commons'
        if not (commons / 'qmldir').is_file():
            raise RuntimeError('The supplied Omarchy shell has no Commons module')
        (stage / 'Commons').symlink_to(commons, target_is_directory=True)
    theme = stage / 'home/.local/state/omarchy/current/theme'
    theme.mkdir(parents=True)
    def set_palette(background):
        (theme / 'colors.toml').write_text('background = "' + background
            + '"\nforeground = "#ecedef"\naccent = "#a1c4d8"\nurgent = "#ef8484"\n')
    set_palette('#202428')
    (theme / 'shell.toml').write_text('')
    title = 'Dock native fixture ' + stage.name
    reference = title + ' focus reference'
    window = stage / 'window.qml'
    window.write_text('import QtQuick\nimport QtQuick.Window\nQtObject {\n'
        'property Window target: Window { visible: true; width: 240; height: 160; title: '
        + json.dumps(title) + ' }\n'
        'property Window reference: Window { visible: true; width: 180; height: 120; title: '
        + json.dumps(reference) + ' }\n}\n')
    source = (ROOT / 'tests/HyprlandIntegration.qml.in').read_text().replace('__TITLE__', json.dumps(title)).replace('__REFERENCE__', json.dumps(reference))
    qml = next(path for path in [Path('/usr/lib/qt6/bin/qml'), Path('/usr/lib64/qt6/bin/qml')] if path.is_file())
    env = {key: os.environ[key] for key in ['PATH', 'LANG', 'XDG_RUNTIME_DIR'] if key in os.environ}
    env.update(HOME=str(stage / 'home'), XDG_CONFIG_HOME=str(stage / 'config'), XDG_DATA_HOME=str(stage / 'data'),
        XDG_STATE_HOME=str(stage / 'state'), XDG_CACHE_HOME=str(stage / 'cache'),
        WAYLAND_DISPLAY=instance['wl_socket'], HYPRLAND_INSTANCE_SIGNATURE=instance['instance'],
        QT_QPA_PLATFORMTHEME='generic', QT_STYLE_OVERRIDE='Fusion', QT_QUICK_BACKEND='software', LIBGL_ALWAYS_SOFTWARE='1')
    providers = ['Hyprland', 'Omarchy'] if args.omarchy_shell else ['Hyprland']
    for provider in providers:
        children = []
        set_palette('#202428')
        try:
            with (stage / (provider + '-app.log')).open('w') as app_log, (stage / (provider + '-dock.log')).open('w') as dock_log:
                app = subprocess.Popen([str(qml), str(window)], env={**env, 'QT_QPA_PLATFORM': 'wayland'}, stdout=app_log, stderr=app_log)
                children.append(app)
                (stage / 'shell.qml').write_text(source.replace('__PID__', str(app.pid)))
                dock = subprocess.Popen(['quickshell', '-p', str(stage / 'shell.qml')],
                    env={**env, 'QT_QPA_PLATFORM': 'wayland', 'DOCK_QA_PROVIDER': provider}, stdout=dock_log, stderr=dock_log)
                children.append(dock)
                deadline, updated = time.monotonic() + 15, False
                while time.monotonic() < deadline:
                    output = (stage / (provider + '-dock.log')).read_text()
                    if 'DOCK_QA_THEME_READY' in output and not updated:
                        set_palette('#304858'); updated = True
                    if 'DOCK_QA_PASS' in output:
                        print(provider + ' native focus, minimize, restore and close passed' + ('; theme reload passed' if updated else ''), flush=True)
                        break
                    if 'DOCK_QA_FAIL' in output or dock.poll() is not None:
                        raise AssertionError('Native dock fixture stopped; inspect ' + str(stage))
                    time.sleep(0.05)
                else:
                    raise AssertionError('Native dock transitions timed out; inspect ' + str(stage))
                assert app.wait(timeout=3) == 0, 'The fixture window did not close normally'
        finally:
            for child in reversed(children):
                if child.poll() is None:
                    child.terminate()
                    try:
                        child.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait()
    print('Native Hyprland checks passed. Artifacts: ' + str(stage))


if __name__ == '__main__':
    main()
