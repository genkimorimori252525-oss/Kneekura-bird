"""Mutual verifier must not hide log rows behind forged tick order."""
import copy
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

VERIFIER = Path(__file__).resolve().parents[1] / "verify_mutual_dogfight_scenario.py"


class MutualMonotonicTicksTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.logs = self.root / "world/wwdebug/autopilot/run/aircraft"
        self.logs.mkdir(parents=True)
        self.primary = [
            self.row("primary", "mutual_dogfight_validation_started", 100),
            self.row("primary", "combat_target_acquired", 101,
                     "target_faction=blue:explicit_faction_hostile=true"),
            self.row("primary", "air_combat_action_transition", 102, "to=INTERCEPT:doctrine=turn_fighter"),
            self.row("primary", "weapon_fire", 103),
            self.row("primary", "frame", 104, speed_bps=25, on_ground=False),
            self.row("primary", "mutual_dogfight_validation_completed", 300,
                     "minimum_separation=10.0:maximum_separation=100.0:primary_track_ticks=150:"
                     "opponent_track_ticks=150:primary_combat_ticks=150:opponent_combat_ticks=150"),
        ]
        self.opponent = [
            self.row("opponent", "combat_target_acquired", 101,
                     "target_faction=red:explicit_faction_hostile=true"),
            self.row("opponent", "air_combat_action_transition", 102, "to=INTERCEPT:doctrine=energy_fighter"),
            self.row("opponent", "weapon_fire", 103),
            self.row("opponent", "frame", 104, speed_bps=25, on_ground=False),
        ]
        (self.root / "validation-summary-1.json").write_text(json.dumps({
            "state": "complete", "results": [{"passed": True}]}), encoding="utf-8")

    @staticmethod
    def row(role, event, tick, reason="", **fields):
        name = "AUTOPILOT TEST warfare_wings:a6m" if role == "primary" else "MUTUAL BLUE P47N"
        return {"aircraft_name": name, "event": event, "server_tick": tick, "reason": reason, **fields}

    def verify(self):
        for name, rows in (("primary.jsonl", self.primary), ("opponent.jsonl", self.opponent)):
            (self.logs / name).write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        output = self.root / "result.json"
        output.unlink(missing_ok=True)
        proc = subprocess.run([sys.executable, str(VERIFIER), "--root", str(self.root),
                               "--gradle-status", "0", "--output", str(output)],
                              capture_output=True, text=True, check=False)
        self.assertTrue(output.is_file(), proc.stderr)
        return proc.returncode, json.loads(output.read_text(encoding="utf-8"))

    def test_ordered_same_tick_rows_remain_valid(self):
        self.primary.insert(2, self.row("primary", "control_adapter", 101))
        code, result = self.verify()
        self.assertEqual(code, 0, result)

    def test_ground_frame_cannot_hide_between_start_and_completion(self):
        self.primary.insert(3, self.row("primary", "frame", 99, speed_bps=25, on_ground=True))
        code, result = self.verify()
        self.assertNotEqual(code, 0, result)
        self.assertTrue(any("primary telemetry tick" in e for e in result["errors"]), result)

    def test_opponent_collision_cannot_hide_in_past_tick(self):
        self.opponent.insert(2, self.row("opponent", "control_adapter", 99,
                             "other_uuid=example:current=7.9", applied_safety_override="collision_avoidance"))
        code, result = self.verify()
        self.assertNotEqual(code, 0, result)
        self.assertTrue(any("opponent telemetry tick" in e for e in result["errors"]), result)

    def test_every_used_row_requires_nonnegative_integer_tick(self):
        for role in ("primary", "opponent"):
            for value in (None, True, False, -1, 102.0, "102", float("inf"), float("nan")):
                with self.subTest(role=role, value=value):
                    primary, opponent = copy.deepcopy(self.primary), copy.deepcopy(self.opponent)
                    rows = self.primary if role == "primary" else self.opponent
                    extra = self.row(role, "other_event", 102)
                    if value is None:
                        del extra["server_tick"]
                    else:
                        extra["server_tick"] = value
                    rows.insert(2, extra)
                    code, result = self.verify()
                    self.assertNotEqual(code, 0, result)
                    if not (isinstance(value, float) and not math.isfinite(value)):
                        self.assertTrue(any(role + " telemetry tick" in e for e in result["errors"]), result)
                    else:
                        self.assertTrue(result["errors"], result)
                    self.primary, self.opponent = primary, opponent

    def test_regression_after_scene_window_is_not_ignored(self):
        self.primary.append(self.row("primary", "other_event", 299))
        code, result = self.verify()
        self.assertNotEqual(code, 0, result)
        self.assertTrue(any("primary telemetry tick" in e for e in result["errors"]), result)

    def test_infinite_frame_tick_produces_failed_report(self):
        self.primary[4]["server_tick"] = float("inf")
        code, result = self.verify()
        self.assertNotEqual(code, 0, result)
        self.assertTrue(result["errors"], result)


if __name__ == "__main__":
    unittest.main()
