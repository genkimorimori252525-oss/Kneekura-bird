"""CLI regression for intra-tick mutual-combat separation evidence."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

VERIFIER = Path(__file__).resolve().parents[1] / "verify_mutual_dogfight_scenario.py"
PRIMARY = "11111111-1111-4111-8111-111111111111"
OPPONENT = "22222222-2222-4222-8222-222222222222"
OTHER = "33333333-3333-4333-8333-333333333333"


class MutualSeparationEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.logs = self.root / "world/wwdebug/autopilot/run/aircraft"
        self.logs.mkdir(parents=True)
        self.primary = self.base_rows(PRIMARY, "AUTOPILOT TEST warfare_wings:a6m", "blue", "turn_fighter")
        self.opponent = self.base_rows(OPPONENT, "AUTOPILOT TEST MUTUAL BLUE P47N", "red", "energy_fighter")
        self.primary.extend([
            self.row(PRIMARY, "AUTOPILOT TEST warfare_wings:a6m", "mutual_dogfight_validation_started", 100,
                     f"primary_uuid={PRIMARY}:opponent_uuid={OPPONENT}"),
            self.row(PRIMARY, "AUTOPILOT TEST warfare_wings:a6m", "mutual_dogfight_validation_completed", 200,
                     "minimum_separation=9.0:maximum_separation=100.0:primary_track_ticks=100:"
                     "opponent_track_ticks=100:primary_combat_ticks=120:opponent_combat_ticks=120"),
        ])
        summary = {"state": "complete", "total": 1, "results": [{"passed": True}]}
        (self.root / "validation-summary-1.json").write_text(json.dumps(summary), encoding="utf-8")
        self.primary_sample = self.collision(value="9.0")
        self.opponent_sample = self.collision(primary=False, value="9.0")
        self.primary.append(self.primary_sample)
        self.opponent.append(self.opponent_sample)

    @staticmethod
    def row(uid, name, event, when, reason="", **extra):
        return {"aircraft_uuid": uid, "aircraft_name": name, "event": event,
                "server_tick": when, "reason": reason, **extra}

    def base_rows(self, uid, name, target, doctrine):
        return [
            self.row(uid, name, "combat_target_acquired", 110,
                     f"target_faction={target}:explicit_faction_hostile=true"),
            self.row(uid, name, "air_combat_action_transition", 111,
                     f"to=FIRING_PASS:doctrine={doctrine}"),
            self.row(uid, name, "weapon_fire", 120),
            self.row(uid, name, "frame", 130, speed_bps=25.0, on_ground=False),
        ]

    def collision(self, primary=True, value="8.1", when=150, other=None, event="control_adapter"):
        uid, name, target = ((PRIMARY, "AUTOPILOT TEST warfare_wings:a6m", OPPONENT) if primary
                             else (OPPONENT, "AUTOPILOT TEST MUTUAL BLUE P47N", PRIMARY))
        data = {"applied_safety_override": "collision_avoidance"} if event == "control_adapter" else {}
        return self.row(uid, name, event, when,
                        f"other_uuid={target if other is None else other}:current={value}:predicted=3.0", **data)

    def verify(self):
        for name, rows in (("primary.jsonl", self.primary), ("opponent.jsonl", self.opponent)):
            (self.logs / name).write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        output = self.root / "result.json"
        process = subprocess.run([sys.executable, str(VERIFIER), "--root", str(self.root),
                                  "--gradle-status", "0", "--output", str(output)],
                                 capture_output=True, text=True, check=False)
        self.assertTrue(output.is_file(), process.stderr)
        return process, json.loads(output.read_text(encoding="utf-8"))

    def test_adapter_below_eight_is_rejected_for_either_participant(self):
        for primary in (True, False):
            with self.subTest(primary=primary):
                rows = self.primary if primary else self.opponent
                row = self.collision(primary=primary, value="7.4")
                rows.append(row)
                proc, result = self.verify()
                self.assertNotEqual(proc.returncode, 0, result)
                self.assertFalse(result["passed"])
                rows.remove(row)

    def test_each_participant_requires_a_pair_observation(self):
        for primary in (True, False):
            with self.subTest(primary=primary):
                rows = self.opponent if primary else self.primary
                row = self.opponent_sample if primary else self.primary_sample
                rows.remove(row)
                proc, result = self.verify()
                self.assertNotEqual(proc.returncode, 0, result)
                rows.append(row)

    def test_rounded_boundary_is_unprovable_and_eight_point_one_passes(self):
        row = self.collision(value="8.0")
        self.primary.append(row)
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)
        row["reason"] = f"other_uuid={OPPONENT}:current=8.1:predicted=3.0"
        proc, result = self.verify()
        self.assertEqual(proc.returncode, 0, result)
        self.assertEqual(result["metrics"].get("collision_observed_minimum"), 8.1)

    def test_start_event_can_expose_unsafe_distance_if_adapter_missing(self):
        self.primary.append(self.collision(value="7.4", event="collision_avoidance_start"))
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)

    def test_unavailable_or_unidentifiable_samples_fail_closed(self):
        self.primary.remove(self.primary_sample)
        self.opponent.remove(self.opponent_sample)
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)
        self.primary.append(self.primary_sample)
        self.opponent.append(self.opponent_sample)
        for reason in (f"other_uuid={OPPONENT}:current=nan", f"other_uuid={OPPONENT}:current=8.01",
                       f"other_uuid={OPPONENT}:current=1e309", "current=7.4",
                       f"other_uuid={OPPONENT}:current={'9' * 400}.0",
                       f"other_uuid={OPPONENT}:current=8.1:current=7.4"):
            with self.subTest(reason=reason):
                row = self.collision()
                row["reason"] = reason
                self.primary.append(row)
                proc, result = self.verify()
                self.assertNotEqual(proc.returncode, 0, result)
                self.primary.remove(row)

    def test_outside_window_and_unrelated_target_do_not_become_pair_samples(self):
        self.primary.extend([self.collision(value="7.4", when=99),
                             self.collision(value="9.5", other=OTHER),
                             self.collision(value="8.1")])
        proc, result = self.verify()
        self.assertEqual(proc.returncode, 0, result)
        self.assertEqual(result["metrics"].get("collision_observed_minimum"), 8.1)

    def test_near_other_aircraft_is_not_silently_ignored(self):
        self.primary.extend([self.collision(value="7.4", other=OTHER), self.collision(value="9.0")])
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)

    def test_adapter_with_missing_override_and_spaced_fields_is_not_ignored(self):
        self.primary.append(self.collision(value="9.0"))
        bad = self.collision(value="7.4")
        del bad["applied_safety_override"]
        bad["reason"] = f"other_uuid ={OPPONENT}:current =7.4"
        self.primary.append(bad)
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)

    def test_unknown_collision_tick_or_mixed_aircraft_identity_fails(self):
        for invalid in (None, True, 150.5, float("inf"), -1):
            with self.subTest(tick=invalid):
                row = self.collision()
                row["server_tick"] = invalid
                self.primary.append(row)
                proc, result = self.verify()
                self.assertNotEqual(proc.returncode, 0, result)
                self.primary.remove(row)
        self.primary.append(self.row(OTHER, "AUTOPILOT TEST warfare_wings:a6m", "frame", 150,
                                     speed_bps=25.0, on_ground=False))
        self.primary.append(self.collision())
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)

    def test_rounded_scene_boundary_is_not_treated_as_proof(self):
        self.primary.append(self.collision(value="9.0"))
        completion = next(row for row in self.primary
                          if row["event"] == "mutual_dogfight_validation_completed")
        original = completion["reason"]
        completion["reason"] = original.replace("minimum_separation=9.0", "minimum_separation=8.0")
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)
        completion["reason"] = original.replace("minimum_separation=9.0", "minimum_separation=8.01")
        proc, result = self.verify()
        self.assertEqual(proc.returncode, 0, result)

    def test_rounded_scene_maximum_boundary_is_not_treated_as_proof(self):
        self.primary.append(self.collision(value="9.0"))
        completion = next(row for row in self.primary
                          if row["event"] == "mutual_dogfight_validation_completed")
        original = completion["reason"]
        completion["reason"] = original.replace("maximum_separation=100.0", "maximum_separation=480.00")
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)
        completion["reason"] = original.replace("maximum_separation=100.0", "maximum_separation=479.99")
        proc, result = self.verify()
        self.assertEqual(proc.returncode, 0, result)
        for replacement in ("maximum_separation=100.001", "maximum_separation=100.0oops", ""):
            with self.subTest(replacement=replacement):
                completion["reason"] = original.replace("maximum_separation=100.0", replacement)
                proc, result = self.verify()
                self.assertNotEqual(proc.returncode, 0, result)

    def test_start_event_must_identify_the_same_unique_pair(self):
        self.primary.append(self.collision(value="9.0"))
        started = next(row for row in self.primary if row["event"] == "mutual_dogfight_validation_started")
        for reason in ("", f"primary_uuid={PRIMARY}:opponent_uuid={OTHER}",
                       f"primary_uuid={PRIMARY}:opponent_uuid={OPPONENT}:opponent_uuid={OTHER}"):
            with self.subTest(reason=reason):
                started["reason"] = reason
                proc, result = self.verify()
                self.assertNotEqual(proc.returncode, 0, result)

    def test_scene_minimum_requires_unambiguous_reported_precision(self):
        self.primary.append(self.collision(value="9.0"))
        completion = next(row for row in self.primary
                          if row["event"] == "mutual_dogfight_validation_completed")
        original = completion["reason"]
        for replacement in ("minimum_separation=8.001", "minimum_separation=9.0oops", ""):
            with self.subTest(replacement=replacement):
                completion["reason"] = original.replace("minimum_separation=9.0", replacement)
                proc, result = self.verify()
                self.assertNotEqual(proc.returncode, 0, result)

    def test_scene_window_requires_ordered_integer_ticks(self):
        self.primary.append(self.collision(value="9.0"))
        completion = next(row for row in self.primary
                          if row["event"] == "mutual_dogfight_validation_completed")
        for invalid in (None, True, 200.5, float("inf"), -1, 99):
            with self.subTest(tick=invalid):
                completion["server_tick"] = invalid
                proc, result = self.verify()
                self.assertNotEqual(proc.returncode, 0, result)

    def test_scene_window_rejects_equal_ticks_even_with_same_tick_samples(self):
        for row in self.primary + self.opponent:
            if row["event"] in ("frame", "mutual_dogfight_validation_started",
                                "mutual_dogfight_validation_completed"):
                row["server_tick"] = 150
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)

    def test_scene_window_rejects_duplicate_start_or_completion(self):
        for event in ("mutual_dogfight_validation_started", "mutual_dogfight_validation_completed"):
            with self.subTest(event=event):
                row = next(row for row in self.primary if row["event"] == event)
                duplicate = row.copy()
                self.primary.append(duplicate)
                proc, result = self.verify()
                self.assertNotEqual(proc.returncode, 0, result)
                self.primary.pop()

    def test_scene_start_requires_nonnegative_integer_tick(self):
        start = next(row for row in self.primary if row["event"] == "mutual_dogfight_validation_started")
        for invalid in (None, True, 100.5, float("inf"), -1):
            with self.subTest(tick=invalid):
                start["server_tick"] = invalid
                proc, result = self.verify()
                self.assertNotEqual(proc.returncode, 0, result)

    def test_duplicate_selected_aircraft_logs_are_not_silently_overwritten(self):
        path = self.logs / "shadow.jsonl"
        for primary, names in ((True, ("AUTOPILOT TEST warfare_wings:a6m",
                                      "AUTOPILOT TEST warfare_wings:a6m alternate", "unrelated display name")),
                               (False, ("AUTOPILOT TEST MUTUAL BLUE P47N", "unrelated display name"))):
            for name in names:
                with self.subTest(primary=primary, name=name):
                    shadow = self.collision(primary=primary, value="7.4")
                    shadow["aircraft_name"] = name
                    path.write_text(json.dumps(shadow) + "\n", encoding="utf-8")
                    proc, result = self.verify()
                    self.assertNotEqual(proc.returncode, 0, result)

    def test_unrelated_aircraft_log_does_not_make_the_pair_ambiguous(self):
        row = self.row(OTHER, "other plane", "frame", 150, speed_bps=25.0, on_ground=False)
        (self.logs / "other.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
        proc, result = self.verify()
        self.assertEqual(proc.returncode, 0, result)


if __name__ == "__main__":
    unittest.main()
