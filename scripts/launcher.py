#!/usr/bin/env python3
"""macOS release launcher. Only the standard library is needed to bootstrap."""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile

REPOSITORY = 'dan8an/insta-commenter'
ASSET = 'InstaComment-macOS.zip'
APP_URL = 'http://localhost:5173'
SOURCE = Path(__file__).resolve().parents[1]
INSTALL = Path.home() / 'Library' / 'Application Support' / 'InstaComment'
VERSION = re.compile(r'v(\d+)\.(\d+)\.(\d+)\Z')
MAX_DOWNLOAD = 50 * 1024 * 1024


def say(message):
    print(message, flush=True)


def version_key(version):
    match = VERSION.fullmatch(version)
    if not match:
        raise ValueError(f'Invalid stable release version: {version!r}')
    return tuple(map(int, match.groups()))


def read_json(path):
    return json.loads(path.read_text())


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def fetch(url, limit=MAX_DOWNLOAD):
    if url.startswith('https://'):
        # Apple's curl uses macOS certificate trust. A python.org installation
        # can lack its own CA bundle even when the system trusts GitHub.
        with tempfile.NamedTemporaryFile(prefix='instacomment-download-') as download:
            result = subprocess.run([
                '/usr/bin/curl', '--fail', '--silent', '--show-error', '--location',
                '--proto', '=https', '--proto-redir', '=https',
                '--connect-timeout', '10', '--max-time', '60',
                '--max-filesize', str(limit), '--user-agent', 'InstaComment-Launcher',
                '--output', download.name, url,
            ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            if result.returncode:
                raise OSError(f'HTTPS download failed: {result.stderr.strip()}')
            data = download.read(limit + 1)
    else:
        request = urllib.request.Request(url, headers={'Accept': '*/*'})
        with urllib.request.urlopen(request, timeout=15) as response:
            data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Download exceeds the launcher size limit.')
    return data


def latest_release():
    release = json.loads(fetch(f'https://api.github.com/repos/{REPOSITORY}/releases/latest', 1024 * 1024))
    version_key(release['tag_name'])
    if release.get('draft') or release.get('prerelease'):
        raise ValueError('Expected a published stable release.')
    names = {asset['name'] for asset in release['assets']}
    if not {ASSET, ASSET + '.sha256'} <= names:
        raise ValueError('The latest release does not have a complete launcher download.')
    return release['tag_name']


def validate_source(root, expected=None):
    manifest = read_json(root / 'release.json')
    version_key(manifest['version'])
    if manifest.get('repository') != REPOSITORY or manifest.get('format') != 1:
        raise ValueError('This package is not a supported InstaComment release.')
    if expected and manifest['version'] != expected:
        raise ValueError('Release version does not match the downloaded package.')
    for name in ('InstaComment.command', 'scripts/launcher.py', 'scripts/start-local.sh',
                 'frontend/package-lock.json', 'frontend/package.json',
                 'backend/app/main.py', 'backend/requirements.txt'):
        if not (root / name).is_file():
            raise ValueError(f'Incomplete release: missing {name}')
    return manifest


def extract_package(archive, destination, expected):
    """Reject traversal, symlinks, duplicate members, and zip bombs before writing."""
    with zipfile.ZipFile(archive) as package:
        members = package.infolist()
        if sum(item.file_size for item in members) > 100 * 1024 * 1024:
            raise ValueError('Unpacked release exceeds the launcher size limit.')
        seen = set()
        for item in members:
            path = PurePosixPath(item.filename)
            if (path.is_absolute() or '..' in path.parts or '\\' in item.filename
                    or not path.parts or path.parts[0] != 'InstaComment'
                    or stat.S_ISLNK(item.external_attr >> 16) or path in seen):
                raise ValueError('Unsafe file path in release archive.')
            seen.add(path)
        package.extractall(destination)
    root = destination / 'InstaComment'
    validate_source(root, expected)
    (root / 'scripts/start-local.sh').chmod(0o755)
    (root / 'InstaComment.command').chmod(0o755)
    return root


def download_release(version, versions):
    version_key(version)
    base = f'https://github.com/{REPOSITORY}/releases/download/{version}'
    checksum = fetch(f'{base}/{ASSET}.sha256', 1024).decode().split()
    if len(checksum) != 2 or checksum[1] != ASSET or not re.fullmatch('[a-f0-9]{64}', checksum[0]):
        raise ValueError('Invalid release checksum file.')
    data = fetch(f'{base}/{ASSET}')
    if hashlib.sha256(data).hexdigest() != checksum[0]:
        raise ValueError('Release checksum verification failed. Nothing was installed.')
    target = versions / version
    # Published version numbers are immutable: never overwrite an installed release.
    if target.exists():
        validate_source(target, version)
        return target
    with tempfile.TemporaryDirectory(prefix='.download-', dir=versions) as temporary:
        stage = Path(temporary)
        archive = stage / ASSET
        archive.write_bytes(data)
        root = extract_package(archive, stage / 'unpacked', version)
        root.rename(target)
    return target


def bundled_release(source, versions):
    manifest = validate_source(source)
    target = versions / manifest['version']
    if not target.exists():
        with tempfile.TemporaryDirectory(prefix='.bundle-', dir=versions) as temporary:
            stage = Path(temporary) / 'app'
            shutil.copytree(source, stage, ignore=shutil.ignore_patterns(
                '.git', '.env', '.venv', '.local', '*.db', '*.db-*', 'node_modules',
                'dist', '__pycache__', '.pytest_cache', 'test-results', 'playwright-report'))
            stage.rename(target)
    validate_source(target, manifest['version'])
    return target


@contextlib.contextmanager
def installation_lock(home):
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    home.chmod(0o700)
    with (home / 'launcher.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('InstaComment is already running or updating. Use its existing Terminal window.') from None
        yield


def check_ports():
    for family, host in ((socket.AF_INET, '127.0.0.1'), (socket.AF_INET6, '::1')):
        for port in (8000, 5173):
            with socket.socket(family, socket.SOCK_STREAM) as connection:
                connection.settimeout(.3)
                if connection.connect_ex((host, port)) == 0:
                    raise RuntimeError(f'Port {port} is in use. Stop the existing app with Ctrl+C before launching again.')


def check_prerequisites():
    if sys.platform != 'darwin':
        raise RuntimeError('This launcher supports macOS. See the README for source setup.')
    if sys.version_info < (3, 11):
        raise RuntimeError('Install Python 3.11 or newer from https://www.python.org/downloads/macos/.')
    if not shutil.which('node') or not shutil.which('npm'):
        raise RuntimeError('Install Node.js 22 or newer (including npm) from https://nodejs.org/, then reopen the launcher.')
    node_version = subprocess.check_output(['node', '-p', 'process.versions.node'], text=True).strip()
    if int(node_version.split('.')[0]) < 22:
        raise RuntimeError('Node.js 22 or newer is required. Update Node at https://nodejs.org/.')
    if not Path('/Applications/Google Chrome.app').is_dir():
        raise RuntimeError('Install Google Chrome in Applications from https://www.google.com/chrome/.')
    return node_version


def prepare(root, node_version):
    """Install per-version dependencies, retrying interrupted setup on the next launch."""
    stamp = root / '.launcher-ready.json'
    fingerprint = hashlib.sha256(
        (root / 'backend/requirements.txt').read_bytes()
        + (root / 'frontend/package-lock.json').read_bytes()
        + (root / 'frontend/package.json').read_bytes()
        + f'{sys.executable}:{sys.version}:{node_version}'.encode()
    ).hexdigest()
    python = root / 'backend/.venv/bin/python'
    if (stamp.exists() and read_json(stamp).get('fingerprint') == fingerprint
            and python.exists() and (root / 'frontend/node_modules/.bin/vite').exists()):
        return
    say('Installing application dependencies. The first launch can take a few minutes…')
    subprocess.run([sys.executable, '-m', 'venv', str(root / 'backend/.venv')], check=True)
    subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(root / 'backend/requirements.txt')], check=True)
    subprocess.run(['npm', 'ci', '--no-audit', '--no-fund'], cwd=root / 'frontend', check=True)
    subprocess.run(['npm', 'run', 'build'], cwd=root / 'frontend', check=True)
    write_json(stamp, {'fingerprint': fingerprint})


def installed_release(home):
    state = home / 'current.json'
    if not state.exists():
        return None
    version = read_json(state)['version']
    version_key(version)
    root = home / 'versions' / version
    validate_source(root, version)
    return root


def choose_release(home, source, offline=False):
    versions = home / 'versions'
    versions.mkdir(exist_ok=True)
    current = installed_release(home)
    candidate = current
    if (source / 'release.json').exists():
        bundled = validate_source(source)['version']
        if candidate is None or version_key(bundled) > version_key(candidate.name):
            candidate = bundled_release(source, versions)
    if not offline:
        say('Checking GitHub for a stable release…')
        try:
            latest = latest_release()
            if candidate is None or version_key(latest) > version_key(candidate.name):
                say(f'Downloading {latest}…')
                candidate = download_release(latest, versions)
        except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
            if candidate is None:
                raise RuntimeError(
                    'No usable release is available. Download the launcher ZIP from GitHub Releases, '
                    'or use --local when working from a source checkout. '
                    f'Details: {error}'
                ) from error
            say(f'Update unavailable ({error}). Using {candidate.name}.')
    if candidate is None:
        raise RuntimeError('No installed or bundled release is available for --offline.')
    return candidate, current


def connect_data(root, home):
    data = home / 'data'
    data.mkdir(mode=0o700, exist_ok=True)
    local = data / '.local'
    local.mkdir(mode=0o700, exist_ok=True)
    link = root / 'backend/.local'
    if link.is_symlink():
        if link.resolve() != local.resolve():
            raise RuntimeError('The release points at an unexpected data directory.')
    elif link.exists():
        raise RuntimeError('The release already contains local browser data. Keep it safe before reinstalling.')
    else:
        link.symlink_to(local, target_is_directory=True)
    return data


def stop_process(process):
    # Kill only the process group created by this launcher, never existing servers.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=12)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()


def run_app(root, data=None, open_browser=True, on_ready=None):
    environment = os.environ.copy()
    environment.pop('API_PROXY_TARGET', None)
    environment['BROWSER_CHANNEL'] = 'chrome'
    if data:
        environment['DATABASE_URL'] = 'sqlite:///' + str(data / 'instacomment.db')
        environment['SESSION_SECRET'] = ''
    process = subprocess.Popen(['/bin/sh', str(root / 'scripts/start-local.sh')],
                               cwd=root, env=environment, start_new_session=True)
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('The application stopped during startup. See the error above.')
            try:
                health = json.loads(fetch('http://127.0.0.1:8000/api/health', 4096))
                fetch(APP_URL, 1024 * 1024)
                if health.get('status') == 'ok' and health.get('mode') == 'browser':
                    break
            except (OSError, ValueError):
                pass
            time.sleep(.5)
        else:
            raise RuntimeError('Startup timed out. See the server messages above.')
        if on_ready:
            on_ready()
        say(f'\nInstaComment is ready: {APP_URL}\nKeep this Terminal window open. Press Ctrl+C to stop.\n')
        if open_browser:
            subprocess.run(['/usr/bin/open', APP_URL], check=False)
        if process.wait() != 0:
            raise RuntimeError('A server stopped unexpectedly. See the messages above and relaunch.')
    finally:
        stop_process(process)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local', action='store_true', help='Install dependencies and run this source checkout without release updates.')
    parser.add_argument('--offline', action='store_true', help='Skip GitHub; use the installed or bundled release. First setup still needs package downloads.')
    parser.add_argument('--no-open', action='store_true', help='Do not open a browser tab automatically.')
    args = parser.parse_args(argv)
    os.umask(0o077)
    say('InstaComment · Local browser launcher')
    try:
        node_version = check_prerequisites()
        with installation_lock(INSTALL):
            check_ports()
            if args.local:
                say('Source checkout mode: GitHub updates are disabled.')
                prepare(SOURCE, node_version)
                run_app(SOURCE, open_browser=not args.no_open)
            else:
                root, previous = choose_release(INSTALL, SOURCE, args.offline)
                try:
                    prepare(root, node_version)
                except (OSError, ValueError, subprocess.CalledProcessError) as error:
                    if previous is None or root == previous:
                        raise
                    say(f'Update setup failed ({error}). Starting the previous installation.')
                    root = previous
                    prepare(root, node_version)
                data = connect_data(root, INSTALL)
                say(f'Starting {root.name}. Local data: {data}')
                run_app(root, data, not args.no_open,
                        lambda: write_json(INSTALL / 'current.json', {'version': root.name}))
        return 0
    except KeyboardInterrupt:
        say('\nInstaComment stopped. Your sign-in and activity have been kept.')
        return 0
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError) as error:
        say(f'\nCould not launch InstaComment: {error}')
        return 1


if __name__ == '__main__':
    # Terminal close/SIGTERM follows the same child cleanup path as Ctrl+C.
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGHUP, interrupted)
    sys.exit(main())
