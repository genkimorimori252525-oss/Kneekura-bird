"""Regression tests for parsing mutual-combat mission summaries."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

VERIFIER = Path(__file__).resolve().parents[1] / "verify_mutual_dogfight_scenario.py"


class MutualSummaryJsonIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        logs = self.root / "world/wwdebug/autopilot/run/aircraft"
        logs.mkdir(parents=True)
        self.summary = self.root / "validation-summary-1.json"
        primary = [
            {"event": "mutual_dogfight_validation_started", "server_tick": 10},
            {"event": "mutual_dogfight_validation_status", "server_tick": 15, "reason": "separation=9.5"},
            {"event": "combat_target_acquired", "reason": "target_faction=blue:explicit_faction_hostile=true"},
            {"event": "air_combat_action_transition", "reason": "doctrine=turn_fighter:to=TURN"},
            {"event": "weapon_fire"},
            {"event": "frame", "server_tick": 15, "speed_bps": 30, "on_ground": False},
            {"event": "mutual_dogfight_validation_completed", "server_tick": 20,
             "reason": "minimum_separation=9.5:maximum_separation=40:primary_track_ticks=90:"
                       "opponent_track_ticks=90:primary_combat_ticks=110:opponent_combat_ticks=110"},
        ]
        opponent = [
            {"event": "combat_target_acquired", "reason": "target_faction=red:explicit_faction_hostile=true"},
            {"event": "air_combat_action_transition", "reason": "doctrine=energy_fighter:to=TURN"},
            {"event": "weapon_fire"},
            {"event": "frame", "server_tick": 15, "speed_bps": 30, "on_ground": False},
        ]
        for filename, name, rows in (("primary.jsonl", "AUTOPILOT TEST warfare_wings:a6m", primary),
                                     ("opponent.jsonl", "MUTUAL BLUE P47N", opponent)):
            (logs / filename).write_text("".join(json.dumps(dict(row, aircraft_name=name)) + "\n"
                                                 for row in rows), encoding="utf-8")

    def verify(self, summary):
        self.summary.write_bytes(summary)
        output = self.root / "result.json"
        output.unlink(missing_ok=True)
        proc = subprocess.run([sys.executable, str(VERIFIER), "--root", str(self.root),
                               "--gradle-status", "0", "--output", str(output)],
                              capture_output=True, text=True, check=False)
        self.assertTrue(output.exists(), proc.stderr)
        return proc.returncode, json.loads(output.read_text(encoding="utf-8"))

    def test_valid_summary_passes(self):
        status, result = self.verify(b'{"state":"complete","results":[{"passed":true}]}')
        self.assertEqual(status, 0, result)
        self.assertTrue(result["passed"])

    def test_duplicate_keys_do_not_hide_failed_summary(self):
        cases = [b'{"state":"failed","state":"complete","results":[{"passed":true}]}',
                 b'{"state":"complete","results":[{"passed":false,"passed":true}]}']
        for summary in cases:
            with self.subTest(summary=summary):
                status, result = self.verify(summary)
                self.assertNotEqual(status, 0, result)
                self.assertFalse(result["passed"])
                self.assertTrue(any("summary" in error for error in result["errors"]), result)

    def test_invalid_utf8_saves_failed_result(self):
        status, result = self.verify(b'{"state":"complete","results":[{"passed":true}],"note":"\xff"}')
        self.assertNotEqual(status, 0, result)
        self.assertFalse(result["passed"])
        self.assertTrue(any("summary" in error for error in result["errors"]), result)

    def test_nonstandard_numeric_constants_fail_even_in_unused_fields(self):
        for value in (b"NaN", b"Infinity", b"-Infinity"):
            with self.subTest(value=value):
                status, result = self.verify(
                    b'{"state":"complete","results":[{"passed":true,"unused":' + value + b'}]}')
                self.assertNotEqual(status, 0, result)
                self.assertFalse(result["passed"])
                self.assertTrue(any("summary" in error for error in result["errors"]), result)


if __name__ == "__main__":
    unittest.main()
