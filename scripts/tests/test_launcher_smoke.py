"""Real server smoke test using isolated data; never opens or posts to Instagram.
Requires installed backend/frontend dependencies and permission to bind localhost.
"""
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import launcher
from test_launcher import packager


class Ready(Exception):
    pass


class StartupSmokeTest(unittest.TestCase):
    def test_packaged_servers_ready_and_stop_with_data_preserved(self):
        launcher.check_ports()
        with tempfile.TemporaryDirectory(prefix='instacomment-smoke-') as temporary:
            home = Path(temporary)
            archive = packager.package('v0.0.0', home)
            root = launcher.extract_package(archive, home / 'unpacked', 'v0.0.0')
            (root / 'backend/.venv').symlink_to(launcher.SOURCE / 'backend/.venv', target_is_directory=True)
            (root / 'frontend/node_modules').symlink_to(launcher.SOURCE / 'frontend/node_modules', target_is_directory=True)
            data = launcher.connect_data(root, home)
            def ready():
                self.assertTrue((data / 'instacomment.db').is_file())
                self.assertTrue((data / '.local/session-secret').is_file())
                self.assertFalse((data / '.local/browser-profile').exists())
                raise Ready()
            with self.assertRaises(Ready):
                launcher.run_app(root, data, open_browser=False, on_ready=ready)
            launcher.check_ports()
            self.assertTrue((data / 'instacomment.db').is_file())
            self.assertFalse((root / 'backend/instacomment.db').exists())


if __name__ == '__main__':
    unittest.main()
