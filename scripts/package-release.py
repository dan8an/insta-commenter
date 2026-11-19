#!/usr/bin/env python3
"""Create a source-only macOS release ZIP; never include credentials or local data."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    'InstaComment.command', 'README.md', 'scripts/launcher.py', 'scripts/start-local.sh',
    'backend/requirements.txt', 'frontend/package.json', 'frontend/package-lock.json',
    'frontend/index.html', 'frontend/vite.config.ts', 'frontend/tsconfig.json',
    'frontend/postcss.config.js', 'frontend/tailwind.config.js',
)
DIRECTORIES = ('backend/app', 'frontend/src')


def package(version, output, root=ROOT):
    if not re.fullmatch(r'v\d+\.\d+\.\d+', version):
        raise ValueError('Use a stable version such as v1.0.0.')
    output.mkdir(parents=True, exist_ok=True)
    archive = output / 'InstaComment-macOS.zip'
    files = [root / name for name in FILES]
    files.append(root / 'backend/browser/worker.cjs')
    for directory in DIRECTORIES:
        files.extend(path for path in (root / directory).rglob('*')
                     if path.is_file() and path.suffix in {'.py', '.ts', '.tsx', '.css'})
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(set(files)):
            if path.is_symlink():
                raise ValueError(f'Release source must not contain symlinks: {path}')
            relative = path.relative_to(root).as_posix()
            bundle.write(path, f'InstaComment/{relative}')
        bundle.writestr('InstaComment/release.json', json.dumps({
            'version': version, 'repository': 'dan8an/insta-commenter', 'format': 1,
        }, indent=2) + '\n')
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(f'{checksum}  {archive.name}\n')
    return archive


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('version')
    parser.add_argument('--output', type=Path, default=ROOT / 'release-dist')
    args = parser.parse_args()
    print(package(args.version, args.output))
