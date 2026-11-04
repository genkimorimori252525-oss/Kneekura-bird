"""Check that terrain evidence cannot override a failed GameTest process."""

import json
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
        self.log = aircraft / "terrain.jsonl"
        self.rows = [
            {"event": "frame", "position": {"x": 0, "y": 120, "z": 25},
             "home_position": {"x": 0, "y": 0, "z": 0},
             "runway_forward": {"x": 1, "z": 0}, "on_ground": False,
             "profile_stall_guard_speed_bps": 10},
            {"event": "terrain_avoidance_start"},
            {"event": "control_adapter", "applied_safety_override": "predictive_terrain_avoidance",
             "speed_bps": 20},
        ]
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


if __name__ == "__main__":
    unittest.main()
