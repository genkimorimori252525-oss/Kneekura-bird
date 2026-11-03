"""Exercise full/landing verification with multiple real-shaped telemetry files."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

VERIFIER = Path(__file__).resolve().parents[1] / "verify_flight_scenario.py"
TARGET = "a50055ec-8717-4c65-b5c0-1de53ad23da8"
OTHER = "208005b6-f2e3-440c-a3e3-e295c8525561"


class FlightVerifierIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.logs = self.root / "world/wwdebug/autopilot/run/aircraft"
        self.logs.mkdir(parents=True)
        (self.root / "flight_profiles.json").write_text("{}", encoding="utf-8")
        self.summary_path = self.root / "world/wwdebug/autopilot/validation-summary-1.json"
        self.summary([{"aircraft_uuid": TARGET, "passed": True}])

    def summary(self, results):
        self.summary_path.write_text(json.dumps({"state": "complete", "total": len(results),
                                                  "results": results}), encoding="utf-8")

    def log(self, name, uuids, mtime):
        path = self.logs / name
        path.write_text("".join(json.dumps({"event": "frame", "aircraft_uuid": uuid}) + "\n"
                                for uuid in uuids), encoding="utf-8")
        os.utime(path, (mtime, mtime))
        return path

    def verify(self, scenario="full"):
        output = self.root / "result.json"
        proc = subprocess.run([sys.executable, str(VERIFIER), "--root", str(self.root),
                               "--scenario", scenario, "--gradle-status", "0", "--output", str(output)],
                              text=True, capture_output=True, check=False)
        self.assertTrue(output.is_file(), proc.stderr)
        return proc, json.loads(output.read_text(encoding="utf-8"))

    def test_summary_aircraft_selected_when_another_log_is_newer(self):
        target = self.log("target.jsonl", [TARGET], 1)
        self.log("unrelated.jsonl", [OTHER], 2)
        for scenario in ("full", "landing"):
            with self.subTest(scenario=scenario):
                proc, result = self.verify(scenario)
                self.assertEqual(proc.returncode, 0, result)
                self.assertEqual(result["metrics"]["telemetry_log"], str(target))

    def test_missing_target_fails_even_if_another_aircraft_has_frames(self):
        self.log("unrelated.jsonl", [OTHER], 2)
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)
        self.assertFalse(result["passed"])

    def test_duplicate_target_logs_are_ambiguous(self):
        self.log("one.jsonl", [TARGET], 1)
        self.log("two.jsonl", [TARGET], 2)
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)

    def test_mixed_identity_log_is_rejected(self):
        self.log("mixed.jsonl", [TARGET, OTHER], 2)
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)

    def test_missing_invalid_or_duplicate_summary_uuids_fail(self):
        self.log("target.jsonl", [TARGET], 1)
        self.log("invalid.jsonl", ["not-a-uuid"], 2)
        for results in ([{"passed": True}],
                        [{"aircraft_uuid": "not-a-uuid", "passed": True}],
                        [{"aircraft_uuid": TARGET, "passed": True},
                         {"aircraft_uuid": TARGET.upper(), "passed": True}]):
            with self.subTest(results=results):
                self.summary(results)
                proc, result = self.verify()
                self.assertNotEqual(proc.returncode, 0, result)

    def test_all_aircraft_summaries_select_each_corresponding_log(self):
        target = self.log("target.jsonl", [TARGET], 1)
        other = self.log("other.jsonl", [OTHER], 2)
        self.summary([{"aircraft_uuid": TARGET, "passed": True},
                      {"aircraft_uuid": OTHER, "passed": True}])
        for scenario in ("full", "landing"):
            with self.subTest(scenario=scenario):
                proc, result = self.verify(scenario)
                self.assertEqual(proc.returncode, 0, result)
                self.assertEqual(result["metrics"]["telemetry_logs"],
                                 {TARGET: str(target), OTHER: str(other)})
                self.assertEqual(result["metrics"]["frame_counts"], {TARGET: 1, OTHER: 1})

    def test_multi_aircraft_requires_a_log_and_frame_for_each(self):
        self.log("target.jsonl", [TARGET], 1)
        self.summary([{"aircraft_uuid": TARGET, "passed": True},
                      {"aircraft_uuid": OTHER, "passed": True}])
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)
        (self.logs / "other.jsonl").write_text(
            json.dumps({"event": "session_start", "aircraft_uuid": OTHER}) + "\n", encoding="utf-8")
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)

    def test_multi_aircraft_duplicate_and_mixed_logs_fail(self):
        self.summary([{"aircraft_uuid": TARGET, "passed": True},
                      {"aircraft_uuid": OTHER, "passed": True}])
        self.log("target.jsonl", [TARGET], 1)
        self.log("other.jsonl", [OTHER], 2)
        duplicate = self.log("duplicate.jsonl", [TARGET], 3)
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)
        duplicate.unlink()
        self.log("mixed.jsonl", [TARGET, OTHER], 3)
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)

    def test_malformed_summary_result_fails_with_result_file(self):
        self.summary([None])
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)

    def test_focused_turn_still_works_without_a_summary(self):
        self.summary_path.unlink()
        rows = [
            {"event": "phase_transition", "reason": "TURN_LEFT->CRUISE_CROSS:left_turn_heading_reached"},
            {"event": "phase_transition", "reason": "TURN_RIGHT->STALL_SETUP:right_turn_heading_reached"},
            {"event": "frame", "phase": "TURN_LEFT", "roll_deg": -9,
             "position": {"y": 100}, "on_ground": False},
            {"event": "frame", "phase": "TURN_RIGHT", "roll_deg": 9,
             "position": {"y": 100}, "on_ground": False},
        ]
        (self.logs / "turn.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows),
                                              encoding="utf-8")
        proc, result = self.verify("turn")
        self.assertEqual(proc.returncode, 0, result)


if __name__ == "__main__":
    unittest.main()
