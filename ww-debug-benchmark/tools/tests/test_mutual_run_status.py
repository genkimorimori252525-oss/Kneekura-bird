"""Exercise mutual verification's process and crash-report acceptance gates."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


VERIFIER = Path(__file__).resolve().parents[1] / "verify_mutual_dogfight_scenario.py"


class MutualRunStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        aircraft = self.root / "world/wwdebug/autopilot/run/aircraft"
        aircraft.mkdir(parents=True)
        primary = "AUTOPILOT TEST warfare_wings:a6m"
        opponent = "MUTUAL BLUE P47N"

        def row(name, event, tick, reason="", **extra):
            return {"aircraft_name": name, "event": event, "server_tick": tick,
                    "reason": reason, **extra}

        primary_rows = [
            row(primary, "mutual_dogfight_validation_started", 100),
            row(primary, "combat_target_acquired", 101,
                "target_faction=blue:explicit_faction_hostile=true"),
            row(primary, "air_combat_action_transition", 102,
                "to=INTERCEPT:doctrine=turn_fighter"),
            row(primary, "weapon_fire", 103),
            row(primary, "frame", 104, speed_bps=25, on_ground=False),
            row(primary, "mutual_dogfight_validation_completed", 300,
                "minimum_separation=10.0:maximum_separation=100.0:"
                "primary_track_ticks=150:opponent_track_ticks=150:"
                "primary_combat_ticks=150:opponent_combat_ticks=150"),
        ]
        opponent_rows = [
            row(opponent, "combat_target_acquired", 101,
                "target_faction=red:explicit_faction_hostile=true"),
            row(opponent, "air_combat_action_transition", 102,
                "to=INTERCEPT:doctrine=energy_fighter"),
            row(opponent, "weapon_fire", 103),
            row(opponent, "frame", 104, speed_bps=25, on_ground=False),
        ]
        for name, rows in (("a6m.jsonl", primary_rows), ("p47n.jsonl", opponent_rows)):
            (aircraft / name).write_text("".join(json.dumps(x) + "\n" for x in rows), encoding="utf-8")
        (self.root / "validation-summary-1.json").write_text(
            json.dumps({"state": "complete", "results": [{"passed": True}]}), encoding="utf-8")

    def verify(self, status):
        output = self.root / "result.json"
        result = subprocess.run([sys.executable, str(VERIFIER), "--root", str(self.root),
                                 "--gradle-status", str(status), "--output", str(output)],
                                capture_output=True, text=True, check=False)
        self.assertTrue(output.exists(), result.stderr)
        return result.returncode, json.loads(output.read_text(encoding="utf-8"))

    def test_clean_success_is_accepted(self):
        code, result = self.verify(0)
        self.assertEqual(code, 0, result)
        self.assertTrue(result["passed"])
        self.assertEqual(result["metrics"]["crash_reports"], [])

    def test_nonzero_gradle_status_rejects_otherwise_passing_evidence(self):
        code, result = self.verify(1)
        self.assertNotEqual(code, 0, result)
        self.assertFalse(result["passed"])
        self.assertIn("Gradle GameTest exit code was 1", result["errors"])

    def test_empty_crash_directory_is_accepted(self):
        (self.root / "crash-reports").mkdir()
        code, result = self.verify(0)
        self.assertEqual(code, 0, result)
        self.assertEqual(result["metrics"]["crash_reports"], [])

    def test_crash_path_that_is_not_a_directory_fails(self):
        (self.root / "crash-reports").write_text("not a directory", encoding="utf-8")
        code, result = self.verify(0)
        self.assertNotEqual(code, 0, result)
        self.assertTrue(any("cannot inspect crash reports" in error for error in result["errors"]))

    def test_crash_report_rejects_otherwise_passing_evidence(self):
        crash = self.root / "crash-reports/crash-test.txt"
        crash.parent.mkdir()
        crash.write_text("crash", encoding="utf-8")
        code, result = self.verify(0)
        self.assertNotEqual(code, 0, result)
        self.assertFalse(result["passed"])
        self.assertTrue(any("crash report created:" in error for error in result["errors"]))
        self.assertEqual(result["metrics"]["crash_reports"], [str(crash)])

    def test_unreadable_crash_directory_fails_with_result_json(self):
        crash_dir = self.root / "crash-reports"
        crash_dir.mkdir()
        output = self.root / "denied-result.json"
        verifier = runpy.run_path(str(VERIFIER))
        real_scandir = os.scandir

        def denied_scandir(path):
            if Path(path) == crash_dir:
                raise PermissionError("injected directory read failure")
            return real_scandir(path)

        argv = [str(VERIFIER), "--root", str(self.root), "--gradle-status", "0",
                "--output", str(output)]
        with (mock.patch.object(sys, "argv", argv),
              mock.patch("os.scandir", side_effect=denied_scandir),
              redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO())):
            code = verifier["main"]()
        self.assertTrue(output.exists())
        result = json.loads(output.read_text(encoding="utf-8"))
        self.assertNotEqual(code, 0, result)
        self.assertFalse(result["passed"])
        self.assertTrue(any("cannot inspect crash reports" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
