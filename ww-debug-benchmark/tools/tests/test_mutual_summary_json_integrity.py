"""Regression tests for parsing mutual-combat mission summaries."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from mutual_fixture import combat_identity, complete_summary, parked_cleanup

VERIFIER = Path(__file__).resolve().parents[1] / "verify_mutual_dogfight_scenario.py"
PRIMARY_ID = "11111111-1111-4111-8111-111111111111"
OPPONENT_ID = "22222222-2222-4222-8222-222222222222"


class MutualSummaryJsonIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        logs = self.root / "world/wwdebug/autopilot/run/aircraft"
        logs.mkdir(parents=True)
        self.summary = self.root / "validation-summary-1.json"
        primary = [
            {"event": "mutual_dogfight_validation_started", "server_tick": 10,
             "reason": f"primary_uuid={PRIMARY_ID}:opponent_uuid={OPPONENT_ID}"},
            {"event": "control_adapter", "server_tick": 15, "applied_safety_override": "collision_avoidance",
             "reason": f"other_uuid={OPPONENT_ID}:current=9.0"},
            {"event": "mutual_dogfight_validation_status", "server_tick": 15, "reason": "separation=9.5"},
            {"event": "combat_target_acquired", "reason": "target_faction=blue:explicit_faction_hostile=true"},
            {"event": "air_combat_action_transition", "reason": "doctrine=turn_fighter:to=INTERCEPT"},
            {"event": "weapon_fire"},
            {"event": "frame", "server_tick": 15, "speed_bps": 30, "on_ground": False},
            {"event": "mutual_dogfight_validation_completed", "server_tick": 20,
             "reason": "minimum_separation=9.5:maximum_separation=40:primary_track_ticks=90:"
                       "opponent_track_ticks=90:primary_combat_ticks=110:opponent_combat_ticks=110"},
        ]
        opponent = [
            {"event": "control_adapter", "server_tick": 15, "applied_safety_override": "collision_avoidance",
             "reason": f"other_uuid={PRIMARY_ID}:current=9.0"},
            {"event": "combat_target_acquired", "reason": "target_faction=red:explicit_faction_hostile=true"},
            {"event": "air_combat_action_transition", "reason": "doctrine=energy_fighter:to=INTERCEPT"},
            {"event": "weapon_fire"},
            {"event": "frame", "server_tick": 15, "speed_bps": 30, "on_ground": False},
        ]
        for filename, name, uid, rows in (("primary.jsonl", "AUTOPILOT TEST warfare_wings:a6m", PRIMARY_ID, primary),
                                          ("opponent.jsonl", "MUTUAL BLUE P47N", OPPONENT_ID, opponent)):
            rows = [dict(row, aircraft_name=name, aircraft_uuid=uid) for row in rows]
            if uid == PRIMARY_ID:
                rows = parked_cleanup(rows, uid)
            rows = combat_identity(rows, uid == PRIMARY_ID)
            (logs / filename).write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    def verify(self, summary):
        self.summary.write_bytes(summary)
        output = self.root / "result.json"
        output.unlink(missing_ok=True)
        proc = subprocess.run([sys.executable, str(VERIFIER), "--root", str(self.root),
                               "--gradle-status", "0", "--output", str(output)],
                              capture_output=True, text=True, check=False)
        self.assertTrue(output.exists(), proc.stderr)
        return proc.returncode, json.loads(output.read_text(encoding="utf-8"))

    def assert_summary_error(self, result, error_type):
        expected = f"cannot read validation summary {self.summary}: {error_type}"
        self.assertIn(expected, result["errors"], result)

    def test_valid_summary_passes(self):
        summary = complete_summary(PRIMARY_ID)
        summary["unused"] = 1.25e3
        status, result = self.verify(json.dumps(summary).encode())
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
                self.assert_summary_error(result, "SummaryDuplicateKeyError")

    def test_invalid_utf8_saves_failed_result(self):
        status, result = self.verify(b'{"state":"complete","results":[{"passed":true}],"note":"\xff"}')
        self.assertNotEqual(status, 0, result)
        self.assertFalse(result["passed"])
        self.assert_summary_error(result, "UnicodeDecodeError")

    def test_nonstandard_numeric_constants_fail_even_in_unused_fields(self):
        for value in (b"NaN", b"Infinity", b"-Infinity"):
            with self.subTest(value=value):
                status, result = self.verify(
                    b'{"state":"complete","results":[{"passed":true,"unused":' + value + b'}]}')
                self.assertNotEqual(status, 0, result)
                self.assertFalse(result["passed"])
                self.assert_summary_error(result, "SummaryInvalidConstantError")

    def test_overflowing_numbers_fail_even_in_unused_fields(self):
        for value in (b"1e9999", b"-1e9999"):
            with self.subTest(value=value):
                status, result = self.verify(
                    b'{"state":"complete","results":[{"passed":true}],"unused":' + value + b'}')
                self.assertNotEqual(status, 0, result)
                self.assertFalse(result["passed"])
                self.assert_summary_error(result, "ValueError")

    def test_parser_limits_save_failed_result(self):
        values = [b'{"unused":' + b'[' * 10000 + b'0' + b']' * 10000 + b'}']
        if hasattr(sys, "get_int_max_str_digits") and sys.get_int_max_str_digits() > 0:
            values.append(b'{"unused":' + b'9' * (sys.get_int_max_str_digits() + 1) + b'}')
        for value in values:
            with self.subTest(kind="deep" if b'[' in value else "large integer"):
                status, result = self.verify(value)
                self.assertNotEqual(status, 0, result)
                self.assertFalse(result["passed"])
                self.assert_summary_error(result, "RecursionError" if b'[' in value else "ValueError")

    def test_non_object_summary_saves_failed_result(self):
        for value in (b"null", b"false", b"2", b'"text"', b"[]", b"[{}]"):
            with self.subTest(value=value):
                status, result = self.verify(value)
                self.assertNotEqual(status, 0, result)
                self.assertFalse(result["passed"])
                self.assert_summary_error(result, "ValueError")


if __name__ == "__main__":
    unittest.main()
