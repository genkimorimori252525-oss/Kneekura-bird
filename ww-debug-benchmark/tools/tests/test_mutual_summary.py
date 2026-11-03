"""Post-combat completion must belong to the actual primary fighter."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


VERIFIER = Path(__file__).resolve().parents[1] / "verify_mutual_dogfight_scenario.py"
PRIMARY = "15a7c379-1310-4def-b8a0-fdaa8b1787b1"
OPPONENT = "f93acc19-18a9-44de-9f33-f0ddc38f7095"
OTHER = "7bd32675-6cff-4a29-a777-0e76c2348004"


class MutualSummaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        logs = self.root / "world/wwdebug/autopilot/run/aircraft"
        logs.mkdir(parents=True)
        primary = "AUTOPILOT TEST warfare_wings:a6m"
        opponent = "MUTUAL BLUE P47N"

        def row(name, aircraft_id, event, tick, reason="", **extra):
            return {"aircraft_name": name, "aircraft_uuid": aircraft_id, "event": event,
                    "server_tick": tick, "reason": reason, **extra}

        self.primary_path = logs / "primary.jsonl"
        self.primary_rows = [
            row(primary, PRIMARY, "mutual_dogfight_validation_started", 100,
                f"primary_uuid={PRIMARY}:opponent_uuid={OPPONENT}"),
            row(primary, PRIMARY, "combat_target_acquired", 101,
                "target_faction=blue:explicit_faction_hostile=true"),
            row(primary, PRIMARY, "air_combat_action_transition", 102,
                "to=INTERCEPT:doctrine=turn_fighter"),
            row(primary, PRIMARY, "weapon_fire", 103),
            row(primary, PRIMARY, "frame", 104, speed_bps=25, on_ground=False),
            row(primary, PRIMARY, "mutual_dogfight_validation_completed", 300,
                "minimum_separation=10.0:maximum_separation=100.0:"
                "primary_track_ticks=150:opponent_track_ticks=150:"
                "primary_combat_ticks=150:opponent_combat_ticks=150"),
        ]
        self.write_primary()
        rows = [
            row(opponent, OPPONENT, "combat_target_acquired", 101,
                "target_faction=red:explicit_faction_hostile=true"),
            row(opponent, OPPONENT, "air_combat_action_transition", 102,
                "to=INTERCEPT:doctrine=energy_fighter"),
            row(opponent, OPPONENT, "weapon_fire", 103),
            row(opponent, OPPONENT, "frame", 104, speed_bps=25, on_ground=False),
        ]
        (logs / "opponent.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows),
                                            encoding="utf-8")
        self.summary = {"state": "complete", "total": 1, "completed": 1, "results": [{
            "entity_id": "warfare_wings:a6m", "aircraft_uuid": PRIMARY, "passed": True,
            "reason": "completed_full_mission", "final_phase": "PARKED",
            "last_transition_reason": "complete_stop_stable_for_40_ticks"}]}

    def write_primary(self):
        self.primary_path.write_text("".join(json.dumps(r) + "\n" for r in self.primary_rows),
                                     encoding="utf-8")

    def verify(self):
        (self.root / "validation-summary-1.json").write_text(json.dumps(self.summary), encoding="utf-8")
        output = self.root / "result.json"
        output.unlink(missing_ok=True)
        result = subprocess.run([sys.executable, str(VERIFIER), "--root", str(self.root),
                                 "--gradle-status", "0", "--output", str(output)],
                                capture_output=True, text=True, check=False)
        self.assertTrue(output.exists(), result.stderr)
        return result.returncode, json.loads(output.read_text(encoding="utf-8"))

    def test_complete_primary_parked_summary_passes(self):
        code, result = self.verify()
        self.assertEqual(code, 0, result)
        self.assertTrue(result["passed"])

    def test_missing_or_wrong_terminal_values_fail(self):
        row = self.summary["results"][0]
        for key, invalid in (("passed", "false"), ("entity_id", "warfare_wings:b17"),
                             ("reason", "not_completed"), ("final_phase", "CRUISE_OUTBOUND"),
                             ("last_transition_reason", "unknown")):
            original = row[key]
            for value in (None, invalid):
                with self.subTest(key=key, value=value):
                    if value is None:
                        del row[key]
                    else:
                        row[key] = value
                    code, result = self.verify()
                    self.assertNotEqual(code, 0, result)
                    self.assertFalse(result["passed"])
                    row[key] = original

    def test_summary_must_have_one_complete_result(self):
        original = self.summary.copy()
        for key, value in (("state", "running"), ("total", 2), ("total", True),
                           ("completed", 0), ("completed", "1"), ("results", []),
                           ("results", [None]), ("results", [original["results"][0]] * 2)):
            with self.subTest(key=key, value=value):
                self.summary = dict(original, **{key: value})
                code, result = self.verify()
                self.assertNotEqual(code, 0, result)
                self.assertFalse(result["passed"])

    def test_summary_uuid_must_match_every_primary_log_row(self):
        row = self.summary["results"][0]
        for value in (None, "not-a-uuid", OTHER, OPPONENT):
            with self.subTest(value=value):
                row["aircraft_uuid"] = value
                code, result = self.verify()
                self.assertNotEqual(code, 0, result)
                self.assertFalse(result["passed"])
        row["aircraft_uuid"] = PRIMARY
        self.primary_rows[2]["aircraft_uuid"] = OTHER
        self.write_primary()
        code, result = self.verify()
        self.assertNotEqual(code, 0, result)
        self.assertFalse(result["passed"])

    def test_uuid_comparison_uses_normalized_values(self):
        self.summary["results"][0]["aircraft_uuid"] = PRIMARY.upper()
        code, result = self.verify()
        self.assertEqual(code, 0, result)

    def test_scene_primary_uuid_must_match_the_primary_log(self):
        self.primary_rows[0]["reason"] = f"primary_uuid={OTHER}:opponent_uuid={OPPONENT}"
        self.write_primary()
        code, result = self.verify()
        self.assertNotEqual(code, 0, result)
        self.assertFalse(result["passed"])

    def test_malformed_summary_root_produces_failure_result(self):
        self.summary = []
        code, result = self.verify()
        self.assertNotEqual(code, 0, result)
        self.assertFalse(result["passed"])


if __name__ == "__main__":
    unittest.main()
