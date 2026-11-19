import contextlib
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import launcher
spec = importlib.util.spec_from_file_location('package_release', SCRIPTS / 'package-release.py')
packager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packager)


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.versions = self.home / 'versions'
        self.versions.mkdir()

    def release(self, version='v1.0.0'):
        archive = packager.package(version, self.home / 'output')
        destination = self.versions / version
        with tempfile.TemporaryDirectory(dir=self.home) as stage:
            root = launcher.extract_package(archive, Path(stage), version)
            root.rename(destination)
        return destination

    def test_package_has_executable_launcher_and_no_local_data(self):
        archive = packager.package('v1.0.0', self.home)
        with zipfile.ZipFile(archive) as bundle:
            names = bundle.namelist()
            self.assertTrue(bundle.getinfo('InstaComment/InstaComment.command').external_attr >> 16 & stat.S_IXUSR)
            self.assertTrue(all(not any(part in name.split('/') for part in
                ('.git', '.env', '.local', '.venv', 'node_modules', '__pycache__')) for name in names))
            self.assertFalse(any(name.endswith('.db') for name in names))
        expected = hashlib.sha256(archive.read_bytes()).hexdigest()
        self.assertEqual(archive.with_suffix('.zip.sha256').read_text().split()[0], expected)
        root = launcher.extract_package(archive, self.home / 'unpacked', 'v1.0.0')
        self.assertEqual(launcher.validate_source(root)['version'], 'v1.0.0')

    def test_rejects_traversal_symlink_and_absolute_members(self):
        for kind in ('traversal', 'symlink', 'outside'):
            archive = self.home / f'{kind}.zip'
            with zipfile.ZipFile(archive, 'w') as bundle:
                if kind == 'symlink':
                    item = zipfile.ZipInfo('InstaComment/link')
                    item.external_attr = (stat.S_IFLNK | 0o777) << 16
                    bundle.writestr(item, '/tmp')
                else:
                    bundle.writestr('InstaComment/../../escape' if kind == 'traversal' else '/escape', 'bad')
            with self.assertRaises(ValueError):
                launcher.extract_package(archive, self.home / 'unpacked', 'v1.0.0')
        self.assertFalse((self.home / 'escape').exists())

    def test_checksum_mismatch_never_installs(self):
        with patch.object(launcher, 'fetch', side_effect=[f'{"0" * 64}  {launcher.ASSET}'.encode(), b'bad']):
            with self.assertRaisesRegex(ValueError, 'checksum verification'):
                launcher.download_release('v1.0.0', self.versions)
        self.assertEqual(list(self.versions.iterdir()), [])

    def test_valid_download_and_manifest_mismatch(self):
        archive = packager.package('v1.0.0', self.home / 'output')
        checksum = archive.with_suffix('.zip.sha256').read_bytes()
        with patch.object(launcher, 'fetch', side_effect=[checksum, archive.read_bytes()]):
            root = launcher.download_release('v1.0.0', self.versions)
        self.assertEqual(root.name, 'v1.0.0')
        with patch.object(launcher, 'fetch', side_effect=[checksum, archive.read_bytes()]):
            with self.assertRaisesRegex(ValueError, 'version does not match'):
                launcher.download_release('v2.0.0', self.versions)
        self.assertFalse((self.versions / 'v2.0.0').exists())

    def test_release_metadata_must_have_both_assets(self):
        release = {'tag_name': 'v1.0.0', 'assets': [{'name': launcher.ASSET}]}
        with patch.object(launcher, 'fetch', return_value=json.dumps(release).encode()):
            with self.assertRaisesRegex(ValueError, 'complete launcher'):
                launcher.latest_release()

    def test_versions_cannot_escape_install_directory(self):
        for version in ('../evil', 'v1.0.0-beta', 'main', 'v1.0'):
            with self.assertRaises(ValueError):
                launcher.version_key(version)
        self.assertGreater(launcher.version_key('v1.10.0'), launcher.version_key('v1.9.0'))

    def test_network_failure_uses_current_without_changing_pointer(self):
        current = self.release()
        launcher.write_json(self.home / 'current.json', {'version': current.name})
        with patch.object(launcher, 'latest_release', side_effect=OSError('offline')):
            selected, previous = launcher.choose_release(self.home, self.home / 'no-bundle')
        self.assertEqual(selected, current)
        self.assertEqual(previous, current)
        self.assertEqual(launcher.read_json(self.home / 'current.json')['version'], 'v1.0.0')

    def test_first_install_can_use_bundled_release_without_github(self):
        bundled = self.release()
        fresh = self.home / 'fresh'
        fresh.mkdir()
        with patch.object(launcher, 'latest_release', side_effect=OSError('offline')):
            selected, previous = launcher.choose_release(fresh, bundled)
        self.assertIsNone(previous)
        self.assertEqual(selected, fresh / 'versions/v1.0.0')
        self.assertFalse((fresh / 'current.json').exists())

    def test_offline_and_no_automatic_downgrade(self):
        current = self.release('v2.0.0')
        launcher.write_json(self.home / 'current.json', {'version': current.name})
        with patch.object(launcher, 'latest_release') as latest:
            self.assertEqual(launcher.choose_release(self.home, self.home / 'none', True)[0], current)
            latest.assert_not_called()
        with patch.object(launcher, 'latest_release', return_value='v1.0.0'):
            self.assertEqual(launcher.choose_release(self.home, self.home / 'none')[0], current)

    def test_data_survives_switching_versions(self):
        old = self.release('v1.0.0')
        new = self.release('v1.1.0')
        data = launcher.connect_data(old, self.home)
        (data / '.local/session-secret').write_text('keep-secret')
        (data / 'instacomment.db').write_text('keep-history')
        launcher.connect_data(new, self.home)
        self.assertEqual((new / 'backend/.local/session-secret').read_text(), 'keep-secret')
        self.assertEqual((data / 'instacomment.db').read_text(), 'keep-history')
        launcher.connect_data(new, self.home)  # repeat launch is safe

    def test_lock_rejects_a_second_launcher(self):
        with launcher.installation_lock(self.home):
            with self.assertRaisesRegex(RuntimeError, 'already running'):
                with launcher.installation_lock(self.home):
                    self.fail('Second launcher got the lock')
        with launcher.installation_lock(self.home):
            pass

    def test_install_failure_keeps_previous_release(self):
        old = self.release('v1.0.0')
        new = self.release('v1.1.0')
        launcher.write_json(self.home / 'current.json', {'version': old.name})
        started = []
        def run(root, data, open_browser, on_ready):
            started.append(root)
            on_ready()
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(launcher, 'INSTALL', self.home))
            stack.enter_context(patch.object(launcher, 'check_prerequisites', return_value='22.0.0'))
            stack.enter_context(patch.object(launcher, 'check_ports'))
            stack.enter_context(patch.object(launcher, 'choose_release', return_value=(new, old)))
            prepare = stack.enter_context(patch.object(launcher, 'prepare', side_effect=[OSError('install failed'), None]))
            stack.enter_context(patch.object(launcher, 'run_app', side_effect=run))
            self.assertEqual(launcher.main(['--no-open']), 0)
        self.assertEqual(started, [old])
        self.assertEqual(prepare.call_count, 2)
        self.assertEqual(launcher.read_json(self.home / 'current.json')['version'], old.name)

    def test_failed_startup_does_not_promote_release(self):
        old = self.release('v1.0.0')
        new = self.release('v1.1.0')
        launcher.write_json(self.home / 'current.json', {'version': old.name})
        with contextlib.ExitStack() as stack:
            for name, value in [('INSTALL', self.home)]:
                stack.enter_context(patch.object(launcher, name, value))
            stack.enter_context(patch.object(launcher, 'check_prerequisites', return_value='22.0.0'))
            stack.enter_context(patch.object(launcher, 'check_ports'))
            stack.enter_context(patch.object(launcher, 'choose_release', return_value=(new, old)))
            stack.enter_context(patch.object(launcher, 'prepare'))
            stack.enter_context(patch.object(launcher, 'run_app', side_effect=RuntimeError('startup failed')))
            self.assertEqual(launcher.main(['--no-open']), 1)
        self.assertEqual(launcher.read_json(self.home / 'current.json')['version'], old.name)


if __name__ == '__main__':
    unittest.main()
