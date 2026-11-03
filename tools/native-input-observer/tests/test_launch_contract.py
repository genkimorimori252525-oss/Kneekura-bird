"""Isolated launcher contracts using only throwaway files and fake subprocesses."""
import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

SOURCE = Path(__file__).resolve().parents[1]


def tar_bytes(entries):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as bundle:
        for name, kind, data in entries:
            info = tarfile.TarInfo(name)
            if kind == "dir":
                info.type = tarfile.DIRTYPE
                bundle.addfile(info)
            elif kind == "file":
                info.size = len(data)
                bundle.addfile(info, io.BytesIO(data))
            elif kind in ("symlink", "hardlink"):
                info.type = tarfile.SYMTYPE if kind == "symlink" else tarfile.LNKTYPE
                info.linkname = data
                bundle.addfile(info)
            else:
                raise AssertionError(kind)
    return output.getvalue()


class LaunchContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(strict=True)
        self.source = self.root / "source"
        local = self.source / "tools" / "native-input-observer"
        local.mkdir(parents=True)
        for name in ("safe_launch.py", "safe_preflight.py", "safe-launch.init.gradle"):
            shutil.copyfile(SOURCE / name, local / name)
        self.sentinel = self.source / "ww-debug-benchmark" / "run-gametest" / "sentinel"
        self.sentinel.parent.mkdir(parents=True)
        self.sentinel.write_bytes(b"preserve original world")
        spec = importlib.util.spec_from_file_location("isolated_safe_launch", local / "safe_launch.py")
        self.launcher = importlib.util.module_from_spec(spec)
        with mock.patch.dict(sys.modules, {"safe_preflight": self._local_preflight(local)}):
            spec.loader.exec_module(self.launcher)
        self.launcher.MODS = {
            "immersive_aircraft-1.3.3+1.20.1-forge.jar": self.hash(b"fake immersive"),
            "warfare_wings-1.1.4-1.20.1-forge.jar": self.hash(b"fake warfare"),
        }
        inputs = self.root / "inputs"
        (inputs / "java" / "bin").mkdir(parents=True)
        (inputs / "gradle-dist" / "bin").mkdir(parents=True)
        (inputs / "gradle-home").mkdir()
        for name, payload in (("observer.jar", b"fake observer"), ("immersive.jar", b"fake immersive"),
                              ("warfare.jar", b"fake warfare"), ("java/bin/java", b"fake java"),
                              ("gradle-dist/bin/gradle", b"fake gradle")):
            (inputs / name).write_bytes(payload)
        self.args = argparse.Namespace(
            scratch=str(self.root / "attempt"), observer_jar=str(inputs / "observer.jar"),
            observer_sha256=self.hash(b"fake observer"), immersive_jar=str(inputs / "immersive.jar"),
            warfare_jar=str(inputs / "warfare.jar"), java_home=str(inputs / "java"),
            java_sha256=self.hash(b"fake java"), gradle=str(inputs / "gradle-dist" / "bin" / "gradle"),
            gradle_sha256=self.hash(b"fake gradle"), gradle_user_home=str(inputs / "gradle-home"),
            isolated_single_jvm_attested=True, exclusive_gradle_home_attested=True,
            network_isolated_attested=True)
        self.archive = tar_bytes([("ww-debug-benchmark", "dir", b""),
                                  ("ww-debug-benchmark/build.gradle", "file", b"// disposable fixture")])

    @staticmethod
    def _local_preflight(local):
        spec = importlib.util.spec_from_file_location("safe_preflight", local / "safe_preflight.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @staticmethod
    def hash(data):
        return hashlib.sha256(data).hexdigest()

    def assert_sentinel(self):
        self.assertEqual(self.sentinel.read_bytes(), b"preserve original world")

    def test_fixed_command_has_no_user_task_exclusion_or_dry_run(self):
        command = self.launcher.fixed_command("/tmp/gradle", "/tmp/project", "/tmp/init.gradle")
        self.assertEqual(command, ["/tmp/gradle", "--no-daemon", "--no-configuration-cache", "--offline",
                                   "--console=plain", "-p", "/tmp/project", "-I", "/tmp/init.gradle",
                                   "runGameTestServer"])
        self.assertNotIn("-x", command)
        self.assertNotIn("--dry-run", command)

    def test_parse_args_rejects_user_task_exclusions_and_dry_run(self):
        values = []
        for option in ("scratch", "observer-jar", "observer-sha256", "immersive-jar", "warfare-jar",
                       "java-home", "java-sha256", "gradle", "gradle-sha256", "gradle-user-home"):
            values += ["--" + option, "dummy"]
        values += ["--isolated-single-jvm-attested", "--exclusive-gradle-home-attested",
                   "--network-isolated-attested"]
        self.launcher.parse_args(values)
        for required in ("--isolated-single-jvm-attested", "--exclusive-gradle-home-attested",
                         "--network-isolated-attested"):
            with self.subTest(missing=required), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                self.launcher.parse_args([value for value in values if value != required])
        for extra in (["-x", "prepareFlightGameTestRuntime"], ["--dry-run"],
                      ["--exclude-task", "prepareFlightGameTestRuntime"]):
            with self.subTest(extra=extra), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                self.launcher.parse_args(values + extra)

    def test_absent_attestation_fails_before_creating_scratch(self):
        for name in ("isolated_single_jvm_attested", "exclusive_gradle_home_attested",
                     "network_isolated_attested"):
            with self.subTest(missing=name):
                setattr(self.args, name, False)
                try:
                    with mock.patch.object(self.launcher.subprocess, "run", side_effect=AssertionError("unexpected spawn")):
                        with self.assertRaises(ValueError):
                            self.launcher.launch(self.args)
                    self.assertFalse(Path(self.args.scratch).exists())
                    self.assert_sentinel()
                finally:
                    setattr(self.args, name, True)

    def test_gradle_distribution_init_and_properties_are_rejected_before_spawn(self):
        dist = Path(self.args.gradle).parent.parent
        init = dist / "init.d"
        init.mkdir()
        for name in ("init.gradle", "init.gradle.kts"):
            path = init / name
            with self.subTest(path=str(path)):
                path.write_text("// injected")
                with mock.patch.object(self.launcher.subprocess, "run", side_effect=AssertionError("unexpected spawn")):
                    with self.assertRaises(ValueError):
                        self.launcher.launch(self.args)
                self.assertFalse(Path(self.args.scratch).exists())
                self.assert_sentinel()
                path.unlink()
        properties = dist / "gradle.properties"
        properties.write_text("org.gradle.jvmargs=-Dexample=true")
        with mock.patch.object(self.launcher.subprocess, "run", side_effect=AssertionError("unexpected spawn")):
            with self.assertRaises(ValueError):
                self.launcher.launch(self.args)
        self.assertFalse(Path(self.args.scratch).exists())
        self.assert_sentinel()

    def test_extract_excludes_existing_run_gametest_from_archive(self):
        scratch = self.root / "extract"
        scratch.mkdir()
        archive = tar_bytes([("ww-debug-benchmark", "dir", b""),
                             ("ww-debug-benchmark/build.gradle", "file", b"build"),
                             ("ww-debug-benchmark/run-gametest", "dir", b""),
                             ("ww-debug-benchmark/run-gametest/world.dat", "file", b"old world")])
        project = self.launcher.extract_project(archive, scratch)
        self.assertEqual((project / "build.gradle").read_bytes(), b"build")
        self.assertFalse(os.path.lexists(project / "run-gametest"))
        self.assert_sentinel()

    def test_archive_rejects_traversal_absolute_and_link_entries(self):
        for name, kind, data in (("ww-debug-benchmark/../escape", "file", b"bad"),
                                 (str(self.root / "absolute-escape"), "file", b"bad"),
                                 ("other/build.gradle", "file", b"bad"),
                                 ("ww-debug-benchmark/link", "symlink", "target"),
                                 ("ww-debug-benchmark/link", "hardlink", "target")):
            with self.subTest(name=name, kind=kind):
                scratch = Path(tempfile.mkdtemp(dir=self.root))
                archive = tar_bytes([("ww-debug-benchmark", "dir", b""), (name, kind, data)])
                with self.assertRaises((ValueError, OSError)):
                    self.launcher.extract_project(archive, scratch)
                self.assertFalse((self.root / "escape").exists())
                self.assert_sentinel()

    def fake_launch(self, marker_mode, *, gradle_code=0, archive=None):
        calls = []
        def fake_run(command, **kwargs):
            calls.append((command, kwargs))
            if command[0] == "/usr/bin/git":
                return SimpleNamespace(stdout=self.archive if archive is None else archive, returncode=0)
            token = kwargs["env"]["WW_OBSERVER_ATTEMPT"]
            digest = kwargs["env"]["WW_OBSERVER_SHA256"]
            markers = [f"OBSERVER_PREPARE_GUARD attempt={token}",
                       f"OBSERVER_PREPARE_DONE attempt={token}",
                       f"OBSERVER_STAGED attempt={token} sha256={digest}"]
            if marker_mode == "all":
                lines = markers
            elif marker_mode == "none":
                lines = []
            elif marker_mode == "guard_only":
                lines = markers[:1]
            elif marker_mode == "no_staged":
                lines = markers[:2]
            elif marker_mode == "no_guard":
                lines = markers[1:]
            elif marker_mode == "wrong_order":
                lines = list(reversed(markers))
            elif marker_mode == "duplicate":
                lines = markers + markers[:1]
            elif marker_mode == "wrong_token":
                lines = [m.replace(token, "wrong-token") for m in markers]
            elif marker_mode == "substring_only":
                lines = ["not-a-marker-" + m for m in markers]
            elif marker_mode == "suffix_only":
                lines = [m + "-not-an-exact-marker" for m in markers]
            else:
                raise AssertionError(marker_mode)
            kwargs["stdout"].write(("\n".join(lines) + "\n").encode())
            return SimpleNamespace(returncode=gradle_code)
        with mock.patch.object(self.launcher.subprocess, "run", side_effect=fake_run):
            result = self.launcher.launch(self.args)
        self.assert_sentinel()
        status = json.loads((Path(self.args.scratch) / "launcher-status.json").read_text())
        return result, status, calls

    def test_zero_exit_without_all_ordered_attempt_markers_is_inconclusive(self):
        for mode in ("none", "guard_only", "no_staged", "no_guard", "wrong_order", "duplicate", "wrong_token",
                     "substring_only", "suffix_only"):
            with self.subTest(mode=mode):
                self.args.scratch = str(self.root / ("attempt-" + mode))
                result, status, calls = self.fake_launch(mode)
                self.assertEqual(result, 2, status)
                self.assertEqual(status["status"], "inconclusive")
                self.assertFalse(status["markers_valid"])
                self.assertEqual(len(calls), 2)

    def test_fixed_markers_and_zero_exit_only_claim_unverified_runtime(self):
        result, status, calls = self.fake_launch("all")
        self.assertEqual(result, 0)
        self.assertEqual(status["status"], "launcher_completed_runtime_unverified")
        self.assertTrue(status["markers_valid"])
        self.assertEqual(calls[1][0], self.launcher.fixed_command(
            self.args.gradle, str(Path(self.args.scratch) / "ww-debug-benchmark"),
            str(Path(self.args.scratch) / "safe-launch.init.gradle")))
        self.assertEqual((Path(self.args.scratch) / "exit-code.txt").read_text(), "0\n")
        self.assertFalse((Path(self.args.scratch) / "ww-debug-benchmark" / "run-gametest").exists())

    def test_nonzero_exit_preserves_output_and_is_inconclusive(self):
        result, status, _ = self.fake_launch("all", gradle_code=7)
        self.assertEqual(result, 2)
        self.assertEqual(status["status"], "inconclusive")
        scratch = Path(self.args.scratch)
        self.assertEqual((scratch / "exit-code.txt").read_text(), "7\n")
        self.assertIn("OBSERVER_PREPARE_GUARD", (scratch / "stdout.log").read_text())
        self.assertTrue((scratch / "provenance.json").is_file())
        self.assertTrue((scratch / "attempt.lock").is_file())

    def test_bad_archive_preserves_attempt_evidence_and_original_sentinel(self):
        bad = tar_bytes([("ww-debug-benchmark", "dir", b""),
                         ("ww-debug-benchmark/link", "symlink", str(self.root / "outside"))])
        with mock.patch.object(self.launcher.subprocess, "run",
                               return_value=SimpleNamespace(stdout=bad, returncode=0)):
            with self.assertRaises((OSError, ValueError, subprocess.SubprocessError)):
                self.launcher.launch(self.args)
        scratch = Path(self.args.scratch)
        self.assertTrue(scratch.is_dir())
        self.assertTrue((scratch / "attempt.lock").is_file())
        self.assertTrue((scratch / "launcher-failure.txt").is_file())
        self.assert_sentinel()

    def test_spawn_failure_preserves_provenance_and_original_sentinel(self):
        def fake_run(command, **kwargs):
            if command[0] == "/usr/bin/git":
                return SimpleNamespace(stdout=self.archive, returncode=0)
            raise OSError("injected spawn failure")
        with mock.patch.object(self.launcher.subprocess, "run", side_effect=fake_run):
            with self.assertRaises(OSError):
                self.launcher.launch(self.args)
        scratch = Path(self.args.scratch)
        self.assertTrue((scratch / "provenance.json").is_file())
        self.assertTrue((scratch / "attempt.lock").is_file())
        self.assertTrue((scratch / "launcher-failure.txt").is_file())
        self.assertTrue((scratch / "stdout.log").is_file())
        self.assertTrue((scratch / "stderr.log").is_file())
        self.assert_sentinel()


if __name__ == "__main__":
    unittest.main()
