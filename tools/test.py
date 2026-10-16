#!/usr/bin/env python3
from pathlib import Path
import os
import resource
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parent.parent
runner = (shutil.which('qmltestrunner6') or shutil.which('qmltestrunner-qt6')
    or next((str(path) for path in [Path('/usr/lib/qt6/bin/qmltestrunner'),
        Path('/usr/lib64/qt6/bin/qmltestrunner')] if path.is_file()), ''))
if not Path(runner).is_file():
    sys.exit('Qt 6 qmltestrunner is required. On Arch, install qt6-declarative.')
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
env = os.environ.copy()
env.update(QT_QPA_PLATFORM='offscreen', QT_QPA_PLATFORMTHEME='generic',
    QT_STYLE_OVERRIDE='Fusion', QT_QUICK_BACKEND='software')

checks = [
    [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py'],
    [sys.executable, 'tools/render_fixture.py'],
    [runner, '-input', 'tests/tst_motion.qml', '-o', '-,txt'],
    [runner, '-input', '.test-artifacts/Surface.qml', '-o', '-,txt'],
    [runner, '-input', '.test-artifacts/tst_backend.qml', '-o', '-,txt'],
    [runner, '-input', '.test-artifacts/tst_hyprland.qml', '-o', '-,txt'],
]
if shutil.which('node'):
    checks.append(['node', 'tests/native_desktop.mjs'])
for args in checks:
    result = subprocess.run(args, cwd=root, env=env, timeout=60)
    if result.returncode:
        sys.exit(result.returncode)
