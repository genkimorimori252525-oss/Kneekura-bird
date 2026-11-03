"""CLI tests for strict decoding of mutual-combat completion evidence."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

VERIFIER = Path(__file__).resolve().parents[1] / "verify_mutual_dogfight_scenario.py"
PRIMARY = "AUTOPILOT TEST warfare_wings:a6m"
OPPONENT = "MUTUAL BLUE P47N"
PRIMARY_ID = "11111111-1111-4111-8111-111111111111"
OPPONENT_ID = "22222222-2222-4222-8222-222222222222"
PRIMARY_PILOT = "33333333-3333-4333-8333-333333333333"
OPPONENT_PILOT = "44444444-4444-4444-8444-444444444444"
COMPLETION = ("reciprocal_fire_confirmed:age_ticks=200:"
              "primary_track_ticks=150:opponent_track_ticks=150:"
              "primary_combat_ticks=150:opponent_combat_ticks=150:"
              "minimum_separation=9.5:maximum_separation=40.0")


class CompletionMetricsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.logs = self.root / "world/wwdebug/autopilot/run/aircraft"
        self.logs.mkdir(parents=True)
        (self.root / "validation-summary-1.json").write_text(
            json.dumps({"state": "complete", "total": 1, "completed": 1, "results": [{
                "entity_id": "warfare_wings:a6m", "aircraft_uuid": PRIMARY_ID, "passed": True,
                "reason": "completed_full_mission", "final_phase": "PARKED",
                "last_transition_reason": "complete_stop_stable_for_40_ticks"}]}), encoding="utf-8")
        self.primary = self.logs / "primary.jsonl"
        self.opponent = self.logs / "opponent.jsonl"
        self.write_rows(self.primary, PRIMARY, [
            {"event": "mutual_dogfight_validation_started", "server_tick": 10,
             "reason": f"primary_uuid={PRIMARY_ID}:primary_pilot_uuid={PRIMARY_PILOT}:"
                       f"opponent_uuid={OPPONENT_ID}:opponent_pilot_uuid={OPPONENT_PILOT}"},
            {"event": "combat_target_acquired", "server_tick": 11,
             "reason": f"uuid={OPPONENT_PILOT}:target_faction=blue:explicit_faction_hostile=true"},
            {"event": "air_combat_action_transition", "server_tick": 12, "reason": "doctrine=turn_fighter:to=INTERCEPT"},
            {"event": "weapon_fire", "server_tick": 13, "reason": f"target_uuid={OPPONENT_PILOT}"},
            {"event": "mutual_dogfight_validation_status", "server_tick": 15, "reason": "separation=9.5"},
            {"event": "frame", "server_tick": 15, "speed_bps": 30, "on_ground": False},
            {"event": "control_adapter", "server_tick": 15, "applied_safety_override": "collision_avoidance",
             "reason": f"other_uuid={OPPONENT_ID}:current=9.0"},
            {"event": "mutual_dogfight_validation_completed", "server_tick": 210, "reason": COMPLETION},
            {"event": "phase_transition", "server_tick": 300, "phase": "PARKED",
             "reason": "BRAKE->PARKED:complete_stop_stable_for_40_ticks"},
            {"event": "frame", "server_tick": 300, "phase": "PARKED", "on_ground": True,
             "horizontal_speed_bps": 0.0},
            {"event": "session_end", "server_tick": 300, "phase": "PARKED", "reason": "validation_aircraft_cleanup"},
        ])
        self.write_rows(self.opponent, OPPONENT, [
            {"event": "combat_target_acquired", "server_tick": 11,
             "reason": f"uuid={PRIMARY_PILOT}:target_faction=red:explicit_faction_hostile=true"},
            {"event": "air_combat_action_transition", "server_tick": 12, "reason": "doctrine=energy_fighter:to=INTERCEPT"},
            {"event": "weapon_fire", "server_tick": 13, "reason": f"target_uuid={PRIMARY_PILOT}"},
            {"event": "frame", "server_tick": 15, "speed_bps": 30, "on_ground": False},
            {"event": "control_adapter", "server_tick": 15, "applied_safety_override": "collision_avoidance",
             "reason": f"other_uuid={PRIMARY_ID}:current=9.0"},
        ])

    @staticmethod
    def write_rows(path, name, rows):
        uid, pilot = ((PRIMARY_ID, PRIMARY_PILOT) if name == PRIMARY else (OPPONENT_ID, OPPONENT_PILOT))
        path.write_text("".join(json.dumps(dict(row, aircraft_name=name, aircraft_uuid=uid, pilot_uuid=pilot)) + "\n"
                                for row in rows),
                        encoding="utf-8")

    def set_completion(self, reason):
        rows = [json.loads(line) for line in self.primary.read_text(encoding="utf-8").splitlines()]
        for row in rows:
            if row.get("event") == "mutual_dogfight_validation_completed":
                row["reason"] = reason
        self.primary.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    def verify(self):
        output = self.root / "result.json"
        output.unlink(missing_ok=True)
        proc = subprocess.run([sys.executable, str(VERIFIER), "--root", str(self.root),
                               "--gradle-status", "0", "--output", str(output)],
                              text=True, capture_output=True, check=False)
        self.assertTrue(output.exists(), proc.stderr)
        return proc, json.loads(output.read_text(encoding="utf-8"))

    def test_standard_completion_succeeds(self):
        proc, result = self.verify()
        self.assertEqual(proc.returncode, 0, result)
        self.assertEqual(result["metrics"]["primary_track_ticks"], 150)
        self.assertEqual(result["metrics"]["scene_age_ticks"], 200)
        self.assertEqual(result["metrics"]["minimum_separation"], 9.5)

    def test_counters_must_be_unique_whole_nonnegative_java_integers(self):
        for field in ("primary_track_ticks", "opponent_track_ticks", "primary_combat_ticks", "opponent_combat_ticks"):
            for value in ("150nonsense", "150.0", "+150", "150e0", "2147483648", "9" * 5000):
                with self.subTest(field=field, value=value):
                    self.set_completion(COMPLETION.replace(f"{field}=150", f"{field}={value}"))
                    proc, result = self.verify()
                    self.assertNotEqual(proc.returncode, 0, result)
                    self.assertTrue(any(error.startswith("scene completion ") and field in error
                                        for error in result["errors"]), result)
            with self.subTest(field=field, value="duplicate"):
                self.set_completion(COMPLETION.replace(f"{field}=150", f"{field}=0:{field}=150"))
                proc, result = self.verify()
                self.assertNotEqual(proc.returncode, 0, result)
                self.assertIn(f"scene completion has missing, ambiguous or invalid integer {field}",
                              result["errors"], result)
            with self.subTest(field=field, value="duplicate with whitespace"):
                self.set_completion(COMPLETION.replace(f"{field}=150", f"{field} =0:{field}=150"))
                proc, result = self.verify()
                self.assertNotEqual(proc.returncode, 0, result)
                self.assertIn(f"scene completion has missing, ambiguous or invalid integer {field}",
                              result["errors"], result)

    def test_extrema_must_be_unique_finite_nonnegative_and_ordered(self):
        cases = (
            COMPLETION.replace("minimum_separation=9.5:maximum_separation=40.0",
                               "minimum_separation=150.0:maximum_separation=20.0"),
            COMPLETION.replace("minimum_separation=9.5", "minimum_separation=9.5junk"),
            COMPLETION.replace("minimum_separation=9.5", "minimum_separation=1:minimum_separation=9.5"),
            COMPLETION.replace("maximum_separation=40.0", "maximum_separation=40.0junk"),
            COMPLETION.replace("maximum_separation=40.0", "maximum_separation=40:maximum_separation=40.0"),
            COMPLETION.replace("minimum_separation=9.5", "minimum_separation=-9.5"),
            COMPLETION.replace("maximum_separation=40.0", "maximum_separation=Infinity"),
            COMPLETION.replace("maximum_separation=40.0", "maximum_separation=" + "9" * 5000),
            COMPLETION.replace("minimum_separation=9.5:", ""),
            COMPLETION.replace(":maximum_separation=40.0", ""),
        )
        for reason in cases:
            with self.subTest(reason=reason):
                self.set_completion(reason)
                proc, result = self.verify()
                self.assertNotEqual(proc.returncode, 0, result)
                self.assertTrue(any(error.startswith("scene completion ") and "separation" in error
                                    for error in result["errors"]), result)

    def test_completion_fields_cannot_be_missing(self):
        for field in ("primary_track_ticks", "opponent_track_ticks", "primary_combat_ticks", "opponent_combat_ticks"):
            with self.subTest(field=field):
                self.set_completion(COMPLETION.replace(f"{field}=150:", ""))
                proc, result = self.verify()
                self.assertNotEqual(proc.returncode, 0, result)
                self.assertIn(f"scene completion has missing, ambiguous or invalid integer {field}",
                              result["errors"], result)

    def test_completion_must_be_unique(self):
        rows = [json.loads(line) for line in self.primary.read_text(encoding="utf-8").splitlines()]
        index = next(i for i, row in enumerate(rows) if row["event"] == "mutual_dogfight_validation_completed")
        rows.insert(index + 1, dict(rows[index]))
        self.primary.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)
        self.assertIn("expected exactly one mutual dogfight completion event; found 2", result["errors"], result)

    def test_scene_age_is_present_unique_positive_java_integer(self):
        for field in ("age_ticks=0", "age_ticks=-1", "age_ticks=200junk", "age_ticks=200.0",
                      "age_ticks=2147483648", "age_ticks=1:age_ticks=200", ""):
            with self.subTest(field=field):
                replacement = field + ":" if field else ""
                self.set_completion(COMPLETION.replace("age_ticks=200:", replacement))
                proc, result = self.verify()
                self.assertNotEqual(proc.returncode, 0, result)
                self.assertTrue(any(error.startswith("scene completion ") and "age_ticks" in error
                                    for error in result["errors"]), result)

    def test_each_counter_cannot_exceed_scene_age(self):
        for field in ("primary_track_ticks", "opponent_track_ticks",
                      "primary_combat_ticks", "opponent_combat_ticks"):
            with self.subTest(field=field):
                self.set_completion(COMPLETION.replace(f"{field}=150", f"{field}=1000"))
                proc, result = self.verify()
                self.assertNotEqual(proc.returncode, 0, result)
                self.assertIn(f"scene completion {field} exceeds age_ticks", result["errors"], result)

    def test_counters_equal_to_scene_age_are_accepted(self):
        self.set_completion(COMPLETION.replace("=150", "=200"))
        proc, result = self.verify()
        self.assertEqual(proc.returncode, 0, result)
        self.assertEqual(result["metrics"]["scene_age_ticks"], 200)

    def test_scene_age_cannot_exceed_combat_window(self):
        # Keep the accepted 2,000-tick boundary consistent with the producer's
        # start/completion interval and put all parked cleanup after completion.
        rows = [json.loads(line) for line in self.primary.read_text(encoding="utf-8").splitlines()]
        for row in rows:
            if row["event"] == "mutual_dogfight_validation_completed":
                row["server_tick"] = 2010
            elif row.get("phase") == "PARKED":
                row["server_tick"] = 2100
        self.primary.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        self.set_completion(COMPLETION.replace("age_ticks=200", "age_ticks=2000"))
        proc, result = self.verify()
        self.assertEqual(proc.returncode, 0, result)
        self.assertEqual(result["metrics"]["scene_age_ticks"], 2000)
        for age in (2001, 2_147_483_647):
            with self.subTest(age=age):
                self.set_completion(COMPLETION.replace("age_ticks=200", f"age_ticks={age}"))
                proc, result = self.verify()
                self.assertNotEqual(proc.returncode, 0, result)
                self.assertIn("scene completion age_ticks exceeds combat window 2000", result["errors"], result)


if __name__ == "__main__":
    unittest.main()
