"""Filesystem preflight checks use only disposable temporary paths."""
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import safe_preflight


class PreflightPathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(strict=True)

    def assert_rejected(self, function, *args, **kwargs):
        with self.assertRaises((ValueError, OSError)):
            function(*args, **kwargs)

    def test_existing_path_without_symlinks_is_accepted(self):
        path = self.root / "existing"
        path.write_bytes(b"data")
        safe_preflight.check_no_symlink(path)
        self.assertEqual(path.read_bytes(), b"data")

    def test_missing_path_requires_explicit_opt_out(self):
        path = self.root / "missing"
        self.assert_rejected(safe_preflight.check_no_symlink, path)
        safe_preflight.check_no_symlink(path, must_exist=False)
        self.assertFalse(path.exists())

    def test_leaf_symlink_and_dangling_symlink_are_rejected(self):
        target = self.root / "target"
        target.write_bytes(b"target")
        for name, destination in (("link", target), ("dangling", self.root / "absent")):
            with self.subTest(name=name):
                link = self.root / name
                try:
                    link.symlink_to(destination)
                except (OSError, NotImplementedError) as exc:
                    self.skipTest(f"symlink unavailable: {exc}")
                self.assert_rejected(safe_preflight.check_no_symlink, link)
                self.assert_rejected(safe_preflight.check_no_symlink, link, must_exist=False)
                self.assertTrue(link.is_symlink())
        self.assertEqual(target.read_bytes(), b"target")

    def test_ancestor_symlink_rejected_for_existing_and_new_leaf(self):
        actual = self.root / "actual"
        actual.mkdir()
        (actual / "file").write_bytes(b"payload")
        link = self.root / "parent-link"
        try:
            link.symlink_to(actual, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"directory symlink unavailable: {exc}")
        self.assert_rejected(safe_preflight.check_no_symlink, link / "file")
        self.assert_rejected(safe_preflight.check_no_symlink, link / "new", must_exist=False)
        self.assertEqual((actual / "file").read_bytes(), b"payload")
        self.assertFalse((actual / "new").exists())

    def test_dangling_symlink_ancestor_is_rejected_for_new_leaf(self):
        missing_target = self.root / "missing-target"
        link = self.root / "dangling-parent"
        try:
            link.symlink_to(missing_target, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"directory symlink unavailable: {exc}")
        self.assert_rejected(safe_preflight.check_no_symlink, link / "child", must_exist=False)
        self.assert_rejected(safe_preflight.create_private_scratch, link / "child")
        self.assertTrue(link.is_symlink())
        self.assertFalse(missing_target.exists())

    def test_regular_file_requires_matching_sha256(self):
        path = self.root / "mod.jar"
        payload = b"test fixture bytes"
        path.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        safe_preflight.check_regular_file(path, digest)
        self.assert_rejected(safe_preflight.check_regular_file, path, "0" * 64)
        self.assertEqual(path.read_bytes(), payload)

    def test_missing_directory_and_symlink_are_not_regular_files(self):
        digest = hashlib.sha256(b"payload").hexdigest()
        regular = self.root / "regular"
        regular.write_bytes(b"payload")
        self.assert_rejected(safe_preflight.check_regular_file, self.root / "missing", digest)
        self.assert_rejected(safe_preflight.check_regular_file, self.root, digest)
        link = self.root / "link"
        try:
            link.symlink_to(regular)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlink unavailable: {exc}")
        self.assert_rejected(safe_preflight.check_regular_file, link, digest)
        self.assertTrue(link.is_symlink())

    def test_regular_file_rejects_symlink_ancestor(self):
        actual = self.root / "actual"
        actual.mkdir()
        path = actual / "payload"
        path.write_bytes(b"payload")
        link = self.root / "parent-link"
        try:
            link.symlink_to(actual, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"directory symlink unavailable: {exc}")
        self.assert_rejected(safe_preflight.check_regular_file, link / path.name,
                             hashlib.sha256(b"payload").hexdigest())
        self.assertEqual(path.read_bytes(), b"payload")

    @unittest.skipUnless(hasattr(os, "link"), "hard links unavailable")
    def test_hard_linked_regular_file_is_rejected(self):
        original = self.root / "original"
        alias = self.root / "alias"
        payload = b"payload"
        original.write_bytes(payload)
        try:
            os.link(original, alias)
        except OSError as exc:
            self.skipTest(f"hard link unavailable: {exc}")
        digest = hashlib.sha256(payload).hexdigest()
        for path in (original, alias):
            with self.subTest(path=path.name):
                self.assert_rejected(safe_preflight.check_regular_file, path, digest)
                self.assertEqual(path.read_bytes(), payload)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO unavailable")
    def test_fifo_is_rejected_without_opening(self):
        path = self.root / "fifo"
        os.mkfifo(path)
        program = """
import sys
import safe_preflight
try:
    safe_preflight.check_regular_file(sys.argv[1], '0' * 64)
except (OSError, ValueError):
    raise SystemExit(0)
raise SystemExit(1)
"""
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]),
                   PYTHONDONTWRITEBYTECODE="1")
        try:
            result = subprocess.run([sys.executable, "-c", program, str(path)],
                                    env=env, capture_output=True, text=True, timeout=3)
        except subprocess.TimeoutExpired:
            self.fail("checking a FIFO must not block while opening it")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(stat.S_ISFIFO(path.lstat().st_mode))

    def test_fresh_scratch_is_private_and_empty(self):
        path = self.root / "scratch"
        old_umask = os.umask(0)
        try:
            safe_preflight.create_private_scratch(path)
        finally:
            os.umask(old_umask)
        self.assertTrue(path.is_dir())
        self.assertFalse(path.is_symlink())
        self.assertEqual(list(path.iterdir()), [])
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)

    def test_existing_scratch_directory_is_rejected_and_preserved(self):
        path = self.root / "scratch"
        path.mkdir()
        marker = path / "keep"
        marker.write_bytes(b"keep")
        self.assert_rejected(safe_preflight.create_private_scratch, path)
        self.assertEqual(marker.read_bytes(), b"keep")

    def test_existing_scratch_file_is_rejected_and_preserved(self):
        path = self.root / "scratch"
        path.write_bytes(b"keep")
        self.assert_rejected(safe_preflight.create_private_scratch, path)
        self.assertEqual(path.read_bytes(), b"keep")

    def test_existing_or_dangling_scratch_symlink_is_rejected(self):
        target = self.root / "target"
        target.mkdir()
        for name, destination in (("link", target), ("dangling", self.root / "absent")):
            with self.subTest(name=name):
                link = self.root / name
                try:
                    link.symlink_to(destination, target_is_directory=True)
                except (OSError, NotImplementedError) as exc:
                    self.skipTest(f"directory symlink unavailable: {exc}")
                self.assert_rejected(safe_preflight.create_private_scratch, link)
                self.assertTrue(link.is_symlink())
        self.assertEqual(list(target.iterdir()), [])
        self.assertFalse((self.root / "absent").exists())

    def test_scratch_under_symlink_ancestor_is_rejected(self):
        target = self.root / "target"
        target.mkdir()
        link = self.root / "parent-link"
        try:
            link.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"directory symlink unavailable: {exc}")
        self.assert_rejected(safe_preflight.create_private_scratch, link / "scratch")
        self.assertFalse((target / "scratch").exists())


if __name__ == "__main__":
    unittest.main()
