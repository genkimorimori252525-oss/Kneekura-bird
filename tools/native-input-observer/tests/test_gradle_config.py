"""Only private temporary directories are used."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import safe_launch


class GradleConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_user_home_config_rejected_without_modifying_file(self):
        home = self.root / 'home'
        home.mkdir(mode=0o700)
        safe_launch.reject_gradle_user_config(home)
        marker = home / 'gradle.properties'
        marker.write_bytes(b'keep')
        with self.assertRaises(ValueError):
            safe_launch.reject_gradle_user_config(home)
        self.assertEqual(marker.read_bytes(), b'keep')

    def test_user_home_caches_cannot_link_to_shared_files(self):
        home = self.root / 'home'
        (home / 'caches').mkdir(parents=True, mode=0o700)
        outside = self.root / 'outside'
        outside.write_bytes(b'keep')
        alias = home / 'caches/shared'
        os.link(outside, alias)
        with self.assertRaises(ValueError):
            safe_launch.reject_gradle_user_config(home)
        self.assertEqual(outside.read_bytes(), b'keep')
        alias.unlink()
        alias.symlink_to(outside)
        with self.assertRaises(ValueError):
            safe_launch.reject_gradle_user_config(home)
        self.assertEqual(outside.read_bytes(), b'keep')

    def test_shared_cloud_cache_is_never_accepted(self):
        with self.assertRaises(ValueError):
            safe_launch.reject_gradle_user_config(Path('/workspace/.cloud-setup/gradle-home'))

    def test_distribution_init_or_properties_rejected(self):
        dist = self.root / 'dist'
        (dist / 'bin').mkdir(parents=True)
        gradle = dist / 'bin/gradle'
        gradle.write_bytes(b'fake')
        (dist / 'init.d').mkdir()
        (dist / 'init.d/readme.txt').write_text('not a script')
        safe_launch.reject_gradle_install_config(gradle)
        init = dist / 'init.d/evil.gradle'
        init.write_bytes(b'keep')
        with self.assertRaises(ValueError):
            safe_launch.reject_gradle_install_config(gradle)
        self.assertEqual(init.read_bytes(), b'keep')
        init.unlink()
        properties = dist / 'gradle.properties'
        properties.write_bytes(b'keep')
        with self.assertRaises(ValueError):
            safe_launch.reject_gradle_install_config(gradle)
        self.assertEqual(properties.read_bytes(), b'keep')

    def test_replaced_log_identity_is_rejected_without_changing_replacement(self):
        log = self.root / 'stdout.log'
        identity = safe_launch.write_new(log, b'original')
        moved = self.root / 'original'
        log.rename(moved)
        log.write_bytes(b'other-data')
        with self.assertRaises(ValueError):
            safe_launch.read_private_regular(log, expected_identity=identity)
        with self.assertRaises(ValueError):
            safe_launch.open_log_append(log, identity)
        self.assertEqual(log.read_bytes(), b'other-data')
        self.assertEqual(moved.read_bytes(), b'original')

    def test_attestations_not_implied_by_programmatic_call(self):
        class Args:
            isolated_single_jvm_attested = False
            exclusive_gradle_home_attested = False
            network_isolated_attested = False
        with self.assertRaises(ValueError):
            safe_launch.launch(Args())


if __name__ == '__main__':
    unittest.main()
