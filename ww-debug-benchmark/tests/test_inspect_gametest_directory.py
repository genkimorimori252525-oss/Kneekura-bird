import hashlib
import importlib.util
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "inspect_gametest_directory.py"
SPEC = importlib.util.spec_from_file_location("inspect_gametest_directory", SCRIPT)
INSPECTOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSPECTOR)
FIXTURE = b"server-port=25565\n"
EXPECTED = hashlib.sha256(FIXTURE).hexdigest()


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux no-follow inspection only")
class InspectGameTestDirectoryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "workspace"
        self.project = self.root / "checkout" / "ww-debug-benchmark"
        self.project.mkdir(parents=True)
        self.run = self.project / "run-gametest"

    def inspect(self, *, root=None, project=None, expected=EXPECTED):
        process = subprocess.run(
            [sys.executable, str(SCRIPT), "--workspace-root", str(root or self.root),
             "--project-dir", str(project or self.project),
             "--expected-properties-sha256", expected],
            capture_output=True, text=True, timeout=5, check=False)
        self.assertEqual(process.stderr, "", process.stderr)
        return process.returncode, json.loads(process.stdout)

    def assert_observation(self, observation, code=0, **kwargs):
        status, result = self.inspect(**kwargs)
        self.assertEqual(status, code, result)
        self.assertEqual(result["observation"], observation, result)
        self.assertEqual(result["scope"], "observation_only")
        self.assertNotIn("safe", result)
        self.assertNotIn("ready", result)
        return result

    def test_absent_is_only_observed_and_not_created(self):
        self.assert_observation("ABSENT")
        self.assertFalse(self.run.exists())

    def test_empty_directory_is_only_observed(self):
        self.run.mkdir()
        before = self.run.stat()
        result = self.assert_observation("EMPTY")
        self.assertEqual(result["run_identity"]["inode"], before.st_ino)
        self.assertEqual(list(self.run.iterdir()), [])

    def test_only_expected_regular_properties_is_observed_without_modification(self):
        self.run.mkdir()
        path = self.run / "server.properties"
        path.write_bytes(FIXTURE)
        before = path.stat()
        result = self.assert_observation("MATCHING_PROPERTIES_ONLY")
        self.assertEqual(result["properties_sha256"], EXPECTED)
        self.assertEqual(path.read_bytes(), FIXTURE)
        self.assertEqual(path.stat().st_ino, before.st_ino)

    def test_modified_properties_is_rejected_and_preserved(self):
        self.run.mkdir()
        path = self.run / "server.properties"
        path.write_bytes(b"user data\n")
        result = self.assert_observation("REJECTED", 1)
        self.assertEqual(result["reason"], "PROPERTIES_HASH_MISMATCH")
        self.assertEqual(path.read_bytes(), b"user data\n")

    def test_unexpected_entries_including_ignored_or_hidden_are_rejected(self):
        for name in ("world", "mods", "eula.txt", "config", ".hidden"):
            with self.subTest(name=name), tempfile.TemporaryDirectory(dir=self.root) as temp:
                project = Path(temp) / "ww-debug-benchmark"
                run = project / "run-gametest"
                run.mkdir(parents=True)
                (run / name).write_bytes(b"preserve")
                result = self.assert_observation("REJECTED", 1, project=project)
                self.assertEqual(result["reason"], "UNEXPECTED_RUN_CONTENT")
                self.assertEqual((run / name).read_bytes(), b"preserve")

    def test_run_symlink_is_rejected_and_target_untouched(self):
        target = Path(self.temp.name) / "outside"
        target.mkdir()
        sentinel = target / "sentinel"
        sentinel.write_bytes(b"outside")
        self.run.symlink_to(target, target_is_directory=True)
        self.assert_observation("REJECTED", 1)
        self.assertEqual(sentinel.read_bytes(), b"outside")

    def test_symlink_in_project_ancestor_is_rejected(self):
        alias = self.root / "link"
        alias.symlink_to(self.project.parent, target_is_directory=True)
        self.assert_observation("REJECTED", 1, project=alias / "ww-debug-benchmark")

    def test_symlink_properties_is_rejected_and_target_untouched(self):
        self.run.mkdir()
        outside = Path(self.temp.name) / "outside"
        outside.write_bytes(FIXTURE)
        (self.run / "server.properties").symlink_to(outside)
        self.assert_observation("REJECTED", 1)
        self.assertEqual(outside.read_bytes(), FIXTURE)

    def test_hardlinked_properties_is_rejected_and_untouched(self):
        self.run.mkdir()
        outside = Path(self.temp.name) / "outside"
        outside.write_bytes(FIXTURE)
        os.link(outside, self.run / "server.properties")
        self.assert_observation("REJECTED", 1)
        self.assertEqual(outside.read_bytes(), FIXTURE)

    def test_fifo_properties_is_rejected_without_blocking(self):
        self.run.mkdir()
        os.mkfifo(self.run / "server.properties")
        self.assert_observation("REJECTED", 1)

    def test_project_outside_workspace_is_rejected(self):
        self.assert_observation("REJECTED", 1, root=self.project)

    def test_relative_and_ambiguous_paths_are_rejected(self):
        self.assert_observation("REJECTED", 1, root=".")
        self.assert_observation("REJECTED", 1, project=str(self.project) + "/../ww-debug-benchmark")

    def test_invalid_expected_hash_is_rejected(self):
        self.assert_observation("REJECTED", 1, expected="not-a-sha256")

    def test_replacement_is_visible_as_a_different_observation_identity(self):
        self.run.mkdir()
        first = self.assert_observation("EMPTY")["run_identity"]
        self.run.rename(self.project / "saved-run")
        self.run.mkdir()
        second = self.assert_observation("EMPTY")["run_identity"]
        self.assertNotEqual((first["device"], first["inode"]),
                            (second["device"], second["inode"]))

    def test_property_file_size_limit_is_fail_closed(self):
        self.run.mkdir()
        path = self.run / "server.properties"
        path.write_bytes(b"x" * (1024 * 1024 + 1))
        self.assert_observation("REJECTED", 1)
        self.assertEqual(path.stat().st_size, 1024 * 1024 + 1)

    def test_unsupported_platform_or_dirfd_is_not_an_observation(self):
        with mock.patch.object(INSPECTOR.sys, "platform", "win32"):
            with self.assertRaisesRegex(INSPECTOR.Unavailable, "NO_REQUIRED_LINUX_NOFOLLOW_SUPPORT"):
                INSPECTOR.inspect(str(self.root), str(self.project), EXPECTED)
            with self.assertRaisesRegex(INSPECTOR.Unavailable, "NO_REQUIRED_LINUX_NOFOLLOW_SUPPORT"):
                INSPECTOR.inspect(r"C:\\workspace", r"C:\\workspace\\ww-debug-benchmark", EXPECTED)
        with mock.patch.object(INSPECTOR.os, "supports_dir_fd", set()):
            with self.assertRaisesRegex(INSPECTOR.Unavailable, "NO_REQUIRED_LINUX_NOFOLLOW_SUPPORT"):
                INSPECTOR.inspect(str(self.root), str(self.project), EXPECTED)
        with mock.patch.object(INSPECTOR.os, "supports_fd", set()):
            with self.assertRaisesRegex(INSPECTOR.Unavailable, "NO_REQUIRED_LINUX_NOFOLLOW_SUPPORT"):
                INSPECTOR.inspect(str(self.root), str(self.project), EXPECTED)

    def test_run_replacement_during_inspection_is_not_reported_as_empty(self):
        self.run.mkdir()
        previous = self.project / "retained-run"
        original_listdir = os.listdir
        original_supports_fd = os.supports_fd
        replaced = False

        def swap_once(fd):
            nonlocal replaced
            if not replaced:
                replaced = True
                self.run.rename(previous)
                self.run.mkdir()
            return original_listdir(fd)

        with mock.patch.object(INSPECTOR.os, "listdir", side_effect=swap_once) as patched:
            with mock.patch.object(INSPECTOR.os, "supports_fd", original_supports_fd | {patched}):
                with self.assertRaisesRegex(INSPECTOR.Unavailable, "DIRECTORY_CHANGED_DURING_INSPECTION"):
                    INSPECTOR.inspect(str(self.root), str(self.project), EXPECTED)
        self.assertTrue(previous.is_dir())
        self.assertTrue(self.run.is_dir())

    def test_run_replacement_between_initial_stat_and_open_is_not_accepted(self):
        self.run.mkdir()
        previous = self.project / "retained-run"
        original_stat = os.stat
        original_dir_fd = os.supports_dir_fd
        original_follow = os.supports_follow_symlinks
        replaced = False

        def swap_after_first_stat(path, *args, **kwargs):
            nonlocal replaced
            result = original_stat(path, *args, **kwargs)
            if path == "run-gametest" and not replaced:
                replaced = True
                self.run.rename(previous)
                self.run.mkdir()
            return result

        with mock.patch.object(INSPECTOR.os, "stat", side_effect=swap_after_first_stat) as patched:
            with mock.patch.object(INSPECTOR.os, "supports_dir_fd", original_dir_fd | {patched}):
                with mock.patch.object(INSPECTOR.os, "supports_follow_symlinks", original_follow | {patched}):
                    with self.assertRaisesRegex(INSPECTOR.Unavailable, "DIRECTORY_CHANGED_DURING_INSPECTION"):
                        INSPECTOR.inspect(str(self.root), str(self.project), EXPECTED)
        self.assertTrue(previous.is_dir())
        self.assertTrue(self.run.is_dir())

    def test_owner_change_during_directory_inspection_is_unavailable(self):
        self.run.mkdir()
        run_inode = self.run.stat().st_ino
        original_fstat = os.fstat
        count = 0

        def changed_owner(fd):
            nonlocal count
            value = original_fstat(fd)
            if value.st_ino == run_inode:
                count += 1
                if count >= 4:
                    return types.SimpleNamespace(st_dev=value.st_dev, st_ino=value.st_ino,
                                                 st_mode=value.st_mode, st_uid=value.st_uid + 1,
                                                 st_gid=value.st_gid)
            return value

        with mock.patch.object(INSPECTOR.os, "fstat", side_effect=changed_owner):
            with self.assertRaisesRegex(INSPECTOR.Unavailable, "DIRECTORY_CHANGED_DURING_INSPECTION"):
                INSPECTOR.inspect(str(self.root), str(self.project), EXPECTED)

    def test_proc_fd_unavailable_is_not_reported_as_matching(self):
        self.run.mkdir()
        (self.run / "server.properties").write_bytes(FIXTURE)
        with mock.patch.object(INSPECTOR, "open_pinned_for_read", side_effect=OSError("unavailable")):
            with self.assertRaisesRegex(INSPECTOR.Unavailable, "FILESYSTEM_INSPECTION_FAILED"):
                INSPECTOR.inspect(str(self.root), str(self.project), EXPECTED)
        self.assertEqual((self.run / "server.properties").read_bytes(), FIXTURE)

    def test_claimed_but_unusable_fd_listing_is_unavailable(self):
        self.run.mkdir()
        original_supports_fd = os.supports_fd
        with mock.patch.object(INSPECTOR.os, "listdir", side_effect=TypeError("unsupported")) as patched:
            with mock.patch.object(INSPECTOR.os, "supports_fd", original_supports_fd | {patched}):
                with self.assertRaisesRegex(INSPECTOR.Unavailable, "FILESYSTEM_INSPECTION_FAILED"):
                    INSPECTOR.inspect(str(self.root), str(self.project), EXPECTED)

    def test_fd_close_failure_is_unavailable_and_other_fds_are_closed(self):
        self.run.mkdir()
        original_close = os.close
        closed = []

        def close_then_report_failure(fd):
            original_close(fd)
            closed.append(fd)
            if len(closed) == 1:
                raise OSError("simulated close failure")

        with mock.patch.object(INSPECTOR.os, "close", side_effect=close_then_report_failure):
            with self.assertRaisesRegex(INSPECTOR.Unavailable, "DESCRIPTOR_CLOSE_FAILED"):
                INSPECTOR.inspect(str(self.root), str(self.project), EXPECTED)
        self.assertGreaterEqual(len(closed), 4)

    def test_unavailable_cli_reports_no_observation_or_authorization(self):
        output = io.StringIO()
        args = ["inspect", "--workspace-root", str(self.root), "--project-dir", str(self.project),
                "--expected-properties-sha256", EXPECTED]
        with mock.patch.object(INSPECTOR.sys, "argv", args):
            with mock.patch.object(INSPECTOR, "inspect", side_effect=INSPECTOR.Unavailable("IO_ERROR")):
                with contextlib.redirect_stdout(output):
                    self.assertEqual(INSPECTOR.main(), 2)
        self.assertEqual(json.loads(output.getvalue()),
                         {"scope": "observation_only", "observation": "UNAVAILABLE", "reason": "IO_ERROR"})


if __name__ == "__main__":
    unittest.main()
