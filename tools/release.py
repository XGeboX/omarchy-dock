#!/usr/bin/env python3
from pathlib import Path
import gzip
import hashlib
import io
import json
import tarfile

root = Path(__file__).resolve().parent.parent
version = json.loads((root / 'plugin/manifest.json').read_text())['version']
prefix = 'omarchy-dock-' + version
output = root / '.release-artifacts'
output.mkdir(exist_ok=True)
archive = output / (prefix + '.tar.gz')
files = [root / name for name in ['LICENSE', 'README.md', 'CHANGELOG.md', 'config.example.json', 'shell.qml']]
for directory in ['plugin', 'bin', 'tools', 'tests', 'docs', 'integrations']:
    files.extend(path for path in (root / directory).rglob('*') if path.is_file()
        and path.suffix in ['.qml', '.js', '.json', '.py', '.svg', '.in', '.png', '.mjs', '.css', '.md'])
files.append(root / 'bin/omarchy-dock')
files = sorted(set(files))
with archive.open('wb') as file:
    with gzip.GzipFile(filename='', fileobj=file, mode='wb', mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w|', format=tarfile.USTAR_FORMAT) as tar:
            for path in files:
                relative = path.relative_to(root)
                if path.is_symlink() or any(part.startswith('.') for part in relative.parts):
                    raise ValueError('Unexpected hidden file or symlink in release input: ' + str(relative))
                data = path.read_bytes()
                info = tarfile.TarInfo(prefix + '/' + relative.as_posix())
                info.size = len(data)
                info.mode = 0o755 if relative.parts[0] == 'bin' else 0o644
                info.mtime = 0
                tar.addfile(info, io.BytesIO(data))
checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
(output / (archive.name + '.sha256')).write_text(checksum + '  ' + archive.name + '\n')
print(archive.name + ': ' + checksum)
