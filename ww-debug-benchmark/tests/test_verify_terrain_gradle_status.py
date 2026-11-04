"""Check that terrain evidence cannot override a failed GameTest process."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


VERIFIER = Path(__file__).resolve().parents[1] / "tools" / "verify_terrain_scenario.py"


class TerrainGradleStatusTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "flight_profiles.json").write_text("{}\n", encoding="utf-8")
        aircraft = self.root / "aircraft"
        aircraft.mkdir()
        self.target_uuid = "11111111-1111-4111-8111-111111111111"
        self.other_uuid = "22222222-2222-4222-8222-222222222222"
        self.summary = self.root / "validation-summary-1.json"
        self.summary.write_text(json.dumps({"results": [{"aircraft_uuid": self.target_uuid}]}),
                                encoding="utf-8")
        self.log = aircraft / f"warfare_wings-a6m-{self.target_uuid}.jsonl"
        self.rows = [
            {"event": "frame", "position": {"x": 0, "y": 120, "z": 25},
             "home_position": {"x": 0, "y": 0, "z": 0},
             "runway_forward": {"x": 1, "z": 0}, "on_ground": False,
             "profile_stall_guard_speed_bps": 10},
            {"event": "terrain_avoidance_start"},
            {"event": "control_adapter", "applied_safety_override": "predictive_terrain_avoidance",
             "speed_bps": 20},
        ]
        for row in self.rows:
            row["aircraft_uuid"] = self.target_uuid
        self.write_rows()

    def write_rows(self):
        self.log.write_text("".join(json.dumps(row) + "\n" for row in self.rows), encoding="utf-8")

    def verify(self, gradle_status):
        output = self.root / "result.json"
        process = subprocess.run(
            [sys.executable, str(VERIFIER), "--root", str(self.root),
             "--gradle-status", str(gradle_status), "--output", str(output)],
            capture_output=True, text=True, check=False,
        )
        self.assertTrue(output.is_file(), process.stderr)
        return process.returncode, json.loads(output.read_text(encoding="utf-8"))

    def test_valid_telemetry_with_successful_gradle_passes(self):
        status, result = self.verify(0)
        self.assertEqual(status, 0, result)
        self.assertTrue(result["passed"], result)

    def test_valid_telemetry_cannot_override_failed_gradle(self):
        for gradle_status in (1, 42, -9):
            with self.subTest(gradle_status=gradle_status):
                status, result = self.verify(gradle_status)
                self.assertNotEqual(status, 0, result)
                self.assertFalse(result["passed"], result)
                self.assertTrue(any("GameTest" in error and str(gradle_status) in error
                                    for error in result["errors"]), result)

    def test_ground_contact_still_fails_with_successful_gradle(self):
        self.rows[0]["on_ground"] = True
        self.write_rows()
        status, result = self.verify(0)
        self.assertNotEqual(status, 0, result)
        self.assertTrue(any("ground" in error for error in result["errors"]), result)

    def test_crash_report_cannot_be_overridden_by_successful_gradle_and_telemetry(self):
        crashes = self.root / "crash-reports"
        crashes.mkdir()
        report = crashes / "crash-2026-11-04-server.txt"
        report.write_text("synthetic crash report\n", encoding="utf-8")
        status, result = self.verify(0)
        self.assertNotEqual(status, 0, result)
        self.assertFalse(result["passed"], result)
        self.assertIn(str(report), result["metrics"]["crash_reports"])
        self.assertTrue(any("crash" in error.lower() for error in result["errors"]), result)

    def test_crash_report_does_not_hide_observed_ground_contact(self):
        crashes = self.root / "crash-reports"
        crashes.mkdir()
        (crashes / "crash-report.txt").write_text("synthetic crash report\n", encoding="utf-8")
        self.rows[0]["on_ground"] = True
        self.write_rows()
        status, result = self.verify(0)
        self.assertNotEqual(status, 0, result)
        self.assertTrue(any("crash" in error.lower() for error in result["errors"]), result)
        self.assertTrue(any("ground" in error for error in result["errors"]), result)

    def test_newer_other_aircraft_cannot_hide_target_ground_contact(self):
        self.rows[0]["on_ground"] = True
        self.write_rows()
        other = self.log.with_name(f"warfare_wings-a6m-{self.other_uuid}.jsonl")
        other_rows = [dict(row, aircraft_uuid=self.other_uuid) for row in self.rows]
        other_rows[0]["on_ground"] = False
        other.write_text("".join(json.dumps(row) + "\n" for row in other_rows), encoding="utf-8")
        os.utime(self.log, (1000000000, 1000000000))
        os.utime(other, (1000000001, 1000000001))
        status, result = self.verify(0)
        self.assertNotEqual(status, 0, result)
        self.assertTrue(any("ground" in error for error in result["errors"]), result)

    def test_newer_other_aircraft_does_not_prevent_selecting_target(self):
        other = self.log.with_name(f"warfare_wings-a6m-{self.other_uuid}.jsonl")
        other_rows = [dict(row, aircraft_uuid=self.other_uuid) for row in self.rows]
        other_rows[0]["on_ground"] = True
        other.write_text("".join(json.dumps(row) + "\n" for row in other_rows), encoding="utf-8")
        os.utime(self.log, (1000000000, 1000000000))
        os.utime(other, (1000000001, 1000000001))
        status, result = self.verify(0)
        self.assertEqual(status, 0, result)
        self.assertEqual(result["metrics"]["telemetry_log"], str(self.log))

    def test_missing_target_log_cannot_fall_back_to_other_aircraft(self):
        self.log.rename(self.log.with_name(f"warfare_wings-a6m-{self.other_uuid}.jsonl"))
        status, result = self.verify(0)
        self.assertNotEqual(status, 0, result)

    def test_missing_or_multiple_summaries_fail(self):
        self.summary.unlink()
        status, result = self.verify(0)
        self.assertNotEqual(status, 0, result)
        self.summary.write_text(json.dumps({"results": [{"aircraft_uuid": self.target_uuid}]}))
        (self.root / "validation-summary-2.json").write_text(self.summary.read_text())
        status, result = self.verify(0)
        self.assertNotEqual(status, 0, result)

    def test_invalid_or_ambiguous_summary_identity_fails(self):
        for results in ([], [{"aircraft_uuid": "invalid"}],
                        [{"aircraft_uuid": self.target_uuid}, {"aircraft_uuid": self.other_uuid}]):
            with self.subTest(results=results):
                self.summary.write_text(json.dumps({"results": results}), encoding="utf-8")
                status, result = self.verify(0)
                self.assertNotEqual(status, 0, result)

    def test_multiple_matching_logs_fail(self):
        second_dir = self.root / "other-run" / "aircraft"
        second_dir.mkdir(parents=True)
        (second_dir / self.log.name).write_text(self.log.read_text())
        status, result = self.verify(0)
        self.assertNotEqual(status, 0, result)

    def test_absent_or_conflicting_row_identity_fails(self):
        for identity in (None, self.other_uuid, "invalid"):
            with self.subTest(identity=identity):
                for row in self.rows:
                    if identity is None:
                        row.pop("aircraft_uuid", None)
                    else:
                        row["aircraft_uuid"] = identity
                self.write_rows()
                status, result = self.verify(0)
                self.assertNotEqual(status, 0, result)

    def test_one_conflicting_row_in_target_log_fails(self):
        self.rows[1]["aircraft_uuid"] = self.other_uuid
        self.write_rows()
        status, result = self.verify(0)
        self.assertNotEqual(status, 0, result)


if __name__ == "__main__":
    unittest.main()
