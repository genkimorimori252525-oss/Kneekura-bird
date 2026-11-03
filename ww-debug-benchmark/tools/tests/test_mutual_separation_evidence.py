"""CLI regression for intra-tick mutual-combat separation evidence."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from mutual_fixture import combat_identity, complete_summary, fill_interior_frames, parked_cleanup

VERIFIER = Path(__file__).resolve().parents[1] / "verify_mutual_dogfight_scenario.py"
PRIMARY = "11111111-1111-4111-8111-111111111111"
OPPONENT = "22222222-2222-4222-8222-222222222222"
OTHER = "33333333-3333-4333-8333-333333333333"
WINDOW_METRICS = ("start_tick", "completion_tick", "scene_age_ticks", "minimum_separation", "maximum_separation",
                  "primary_interior_frame_ticks", "opponent_interior_frame_ticks",
                  "primary_interior_missing_ticks", "opponent_interior_missing_ticks",
                  "collision_observed_minimum", "collision_observation_rows", "collision_observation_rows_by_aircraft",
                  "other_aircraft_collision_observed_minimum", "primary_track_ticks", "opponent_track_ticks",
                  "primary_combat_ticks", "opponent_combat_ticks", "primary_actions", "opponent_actions",
                  "primary_fire_count", "opponent_fire_count", "primary_combat_frame_count",
                  "opponent_combat_frame_count", "primary_min_speed_bps", "opponent_min_speed_bps",
                  "primary_ground_frames", "opponent_ground_frames", "primary_doctrines", "opponent_doctrines")


class MutualSeparationEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.logs = self.root / "world/wwdebug/autopilot/run/aircraft"
        self.logs.mkdir(parents=True)
        self.primary = self.base_rows(PRIMARY, "AUTOPILOT TEST warfare_wings:a6m", "blue", "turn_fighter")
        self.opponent = self.base_rows(OPPONENT, "AUTOPILOT TEST MUTUAL BLUE P47N", "red", "energy_fighter")
        self.primary.insert(0, self.row(PRIMARY, "AUTOPILOT TEST warfare_wings:a6m",
                                        "mutual_dogfight_validation_started", 100,
                                        f"primary_uuid={PRIMARY}:opponent_uuid={OPPONENT}"))
        self.primary.append(self.row(PRIMARY, "AUTOPILOT TEST warfare_wings:a6m",
                                     "mutual_dogfight_validation_completed", 200,
                                     "age_ticks=100:minimum_separation=9.0:maximum_separation=100.0:primary_track_ticks=100:"
                                     "opponent_track_ticks=100:primary_combat_ticks=100:opponent_combat_ticks=100"))
        summary = complete_summary(PRIMARY)
        (self.root / "validation-summary-1.json").write_text(json.dumps(summary), encoding="utf-8")
        self.primary_sample = self.collision(value="9.0")
        self.opponent_sample = self.collision(primary=False, value="9.0")
        self.add_row(self.primary, self.primary_sample)
        self.add_row(self.opponent, self.opponent_sample)
        self.primary = fill_interior_frames(self.primary, 100, 200)
        self.opponent = fill_interior_frames(self.opponent, 100, 200)

    @staticmethod
    def add_row(rows, row):
        """Insert a newly produced valid sample chronologically; retain invalid ticks as-is."""
        when = row.get("server_tick")
        if type(when) is int and when >= 0:
            for index, existing in enumerate(rows):
                old = existing.get("server_tick")
                if type(old) is int and old > when:
                    rows.insert(index, row)
                    return
        rows.append(row)

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

    def verify(self, omit=None):
        for name, rows in (("primary.jsonl", self.primary), ("opponent.jsonl", self.opponent)):
            if name == omit:
                (self.logs / name).unlink(missing_ok=True)
                continue
            if name == "primary.jsonl":
                rows = parked_cleanup(rows, PRIMARY)
            rows = combat_identity(rows, name == "primary.jsonl")
            (self.logs / name).write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        output = self.root / "result.json"
        process = subprocess.run([sys.executable, str(VERIFIER), "--root", str(self.root),
                                  "--gradle-status", "0", "--output", str(output)],
                                 capture_output=True, text=True, check=False)
        self.assertTrue(output.is_file(), process.stderr)
        return process, json.loads(output.read_text(encoding="utf-8"))

    def make_crash(self):
        path = self.root / "crash-reports/crash-test.txt"
        path.parent.mkdir()
        path.write_text("crash diagnostic", encoding="utf-8")
        return str(path)

    def assert_unknown_window(self, result, crash):
        metrics = result["metrics"]
        self.assertIs(metrics["scene_window_valid"], False, result)
        for key in WINDOW_METRICS:
            self.assertIsNone(metrics[key], (key, result))
        self.assertIs(metrics["telemetry_scan_complete"], True)
        self.assertEqual(metrics["gradle_status"], 0)
        self.assertEqual(metrics["crash_reports"], [crash])
        self.assertEqual(metrics["validation_summary"], str(self.root / "validation-summary-1.json"))

    def test_missing_participant_invalidates_scene_window(self):
        crash = self.make_crash()
        for role in ("primary", "opponent"):
            with self.subTest(role=role):
                proc, result = self.verify(omit=f"{role}.jsonl")
                self.assertNotEqual(proc.returncode, 0, result)
                self.assertIn(f"{role} aircraft log is missing or ambiguous", result["errors"], result)
                self.assert_unknown_window(result, crash)
                other = "opponent" if role == "primary" else "primary"
                self.assertIsNone(result["metrics"][f"{role}_log"], result)
                self.assertEqual(result["metrics"][f"{other}_log"], str(self.logs / f"{other}.jsonl"))

    def test_duplicate_candidate_name_invalidates_scene_window(self):
        crash = self.make_crash()
        shadow = self.logs / "shadow.jsonl"
        for role in ("primary", "opponent"):
            with self.subTest(role=role):
                rows = self.primary if role == "primary" else self.opponent
                rows = parked_cleanup(rows, PRIMARY) if role == "primary" else rows
                rows = combat_identity(rows, role == "primary")
                shadow.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
                try:
                    proc, result = self.verify()
                    self.assertNotEqual(proc.returncode, 0, result)
                    self.assertIn(f"{role} aircraft log is missing or ambiguous", result["errors"], result)
                    self.assert_unknown_window(result, crash)
                    self.assertIn(result["metrics"][f"{role}_log"], (str(shadow), str(self.logs / f"{role}.jsonl")))
                    other = "opponent" if role == "primary" else "primary"
                    self.assertEqual(result["metrics"][f"{other}_log"], str(self.logs / f"{other}.jsonl"))
                finally:
                    shadow.unlink()

    def test_duplicate_uuid_under_other_name_invalidates_scene_window(self):
        crash = self.make_crash()
        shadow = self.logs / "shadow.jsonl"
        for role in ("primary", "opponent"):
            with self.subTest(role=role):
                uid = PRIMARY if role == "primary" else OPPONENT
                row = self.row(uid, "unrelated display name", "frame", 150, speed_bps=25.0, on_ground=False)
                shadow.write_text(json.dumps(row) + "\n", encoding="utf-8")
                try:
                    proc, result = self.verify()
                    self.assertNotEqual(proc.returncode, 0, result)
                    self.assertIn(f"{role} aircraft UUID occurs in more than one telemetry file", result["errors"], result)
                    self.assert_unknown_window(result, crash)
                    for selected in ("primary", "opponent"):
                        self.assertEqual(result["metrics"][f"{selected}_log"], str(self.logs / f"{selected}.jsonl"))
                finally:
                    shadow.unlink()

    def test_adapter_below_eight_is_rejected_for_either_participant(self):
        for primary in (True, False):
            with self.subTest(primary=primary):
                rows = self.primary if primary else self.opponent
                row = self.collision(primary=primary, value="7.4")
                self.add_row(rows, row)
                proc, result = self.verify()
                self.assertNotEqual(proc.returncode, 0, result)
                self.assertFalse(result["passed"])
                self.assertIn("rounded mutual collision observation does not establish 8-block separation: 7.4", result["errors"])
                self.assertIs(result["metrics"]["scene_window_valid"], True, result)
                self.assertEqual(result["metrics"]["collision_observed_minimum"], 7.4, result)
                rows.remove(row)

    def test_each_participant_requires_a_pair_observation(self):
        for primary in (True, False):
            with self.subTest(primary=primary):
                rows = self.opponent if primary else self.primary
                row = self.opponent_sample if primary else self.primary_sample
                rows.remove(row)
                proc, result = self.verify()
                self.assertNotEqual(proc.returncode, 0, result)
                missing_role = "opponent" if primary else "primary"
                self.assertIn(f"{missing_role} has no interpretable mutual collision-separation observation", result["errors"])
                self.add_row(rows, row)

    def test_rounded_boundary_is_unprovable_and_eight_point_one_passes(self):
        row = self.collision(value="8.0")
        self.add_row(self.primary, row)
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)
        self.assertIn("rounded mutual collision observation does not establish 8-block separation: 8.0", result["errors"])
        row["reason"] = f"other_uuid={OPPONENT}:current=8.1:predicted=3.0"
        proc, result = self.verify()
        self.assertEqual(proc.returncode, 0, result)
        self.assertEqual(result["metrics"].get("collision_observed_minimum"), 8.1)

    def test_start_event_can_expose_unsafe_distance_if_adapter_missing(self):
        self.add_row(self.primary, self.collision(value="7.4", event="collision_avoidance_start"))
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)
        self.assertIn("rounded mutual collision observation does not establish 8-block separation: 7.4", result["errors"])

    def test_unavailable_or_unidentifiable_samples_fail_closed(self):
        self.primary.remove(self.primary_sample)
        self.opponent.remove(self.opponent_sample)
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)
        self.assertIn("primary has no interpretable mutual collision-separation observation", result["errors"])
        self.assertIn("opponent has no interpretable mutual collision-separation observation", result["errors"])
        self.add_row(self.primary, self.primary_sample)
        self.add_row(self.opponent, self.opponent_sample)
        for reason in (f"other_uuid={OPPONENT}:current=nan", f"other_uuid={OPPONENT}:current=8.01",
                       f"other_uuid={OPPONENT}:current=1e309", "current=7.4",
                       f"other_uuid={OPPONENT}:current={'9' * 400}.0",
                       f"other_uuid={OPPONENT}:current=8.1:current=7.4"):
            with self.subTest(reason=reason):
                row = self.collision()
                row["reason"] = reason
                self.add_row(self.primary, row)
                proc, result = self.verify()
                self.assertNotEqual(proc.returncode, 0, result)
                self.assertIn("primary collision evidence has an invalid target or current distance", result["errors"])
                self.primary.remove(row)

    def test_outside_window_and_unrelated_target_do_not_become_pair_samples(self):
        for sample in (self.collision(value="7.4", when=99),
                       self.collision(value="9.5", other=OTHER), self.collision(value="8.1")):
            self.add_row(self.primary, sample)
        proc, result = self.verify()
        self.assertEqual(proc.returncode, 0, result)
        self.assertEqual(result["metrics"].get("collision_observed_minimum"), 8.1)

    def test_near_other_aircraft_is_not_silently_ignored(self):
        for sample in (self.collision(value="7.4", other=OTHER), self.collision(value="9.0")):
            self.add_row(self.primary, sample)
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)
        self.assertIn("rounded collision observation with another aircraft does not establish 8-block separation: 7.4", result["errors"])

    def test_adapter_with_missing_override_and_spaced_fields_is_not_ignored(self):
        self.add_row(self.primary, self.collision(value="9.0"))
        bad = self.collision(value="7.4")
        del bad["applied_safety_override"]
        bad["reason"] = f"other_uuid ={OPPONENT}:current =7.4"
        self.add_row(self.primary, bad)
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)
        self.assertIn("rounded mutual collision observation does not establish 8-block separation: 7.4", result["errors"])

    def test_unknown_collision_tick_or_mixed_aircraft_identity_fails(self):
        for invalid in (None, True, 150.5, float("inf"), -1):
            with self.subTest(tick=invalid):
                row = self.collision()
                row["server_tick"] = invalid
                self.add_row(self.primary, row)
                proc, result = self.verify()
                self.assertNotEqual(proc.returncode, 0, result)
                if invalid == float("inf"):
                    self.assertTrue(any("InvalidConstantError Infinity" in error for error in result["errors"]), result)
                else:
                    self.assertIn("primary collision evidence has no valid tick", result["errors"])
                self.primary.remove(row)
        self.add_row(self.primary, self.row(OTHER, "AUTOPILOT TEST warfare_wings:a6m", "frame", 150,
                                            speed_bps=25.0, on_ground=False))
        self.add_row(self.primary, self.collision())
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)
        self.assertIn("primary telemetry must identify exactly one aircraft", result["errors"])

    def test_rounded_scene_boundary_is_not_treated_as_proof(self):
        self.add_row(self.primary, self.collision(value="9.0"))
        completion = next(row for row in self.primary
                          if row["event"] == "mutual_dogfight_validation_completed")
        original = completion["reason"]
        completion["reason"] = original.replace("minimum_separation=9.0", "minimum_separation=8.0")
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)
        self.assertIn("rounded scene minimum does not establish 8-block separation: 8.0", result["errors"])
        completion["reason"] = original.replace("minimum_separation=9.0", "minimum_separation=8.01")
        proc, result = self.verify()
        self.assertEqual(proc.returncode, 0, result)

    def test_rounded_scene_maximum_boundary_is_not_treated_as_proof(self):
        self.add_row(self.primary, self.collision(value="9.0"))
        completion = next(row for row in self.primary
                          if row["event"] == "mutual_dogfight_validation_completed")
        original = completion["reason"]
        completion["reason"] = original.replace("maximum_separation=100.0", "maximum_separation=480.00")
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)
        self.assertIn("rounded scene maximum does not establish the 480-block limit: 480.0", result["errors"])
        completion["reason"] = original.replace("maximum_separation=100.0", "maximum_separation=479.99")
        proc, result = self.verify()
        self.assertEqual(proc.returncode, 0, result)
        for replacement in ("maximum_separation=100.001", "maximum_separation=100.0oops", ""):
            with self.subTest(replacement=replacement):
                completion["reason"] = original.replace("maximum_separation=100.0", replacement)
                proc, result = self.verify()
                self.assertNotEqual(proc.returncode, 0, result)
                self.assertIn("scene completion has missing, ambiguous or invalid rounded maximum_separation", result["errors"])

    def test_start_event_must_identify_the_same_unique_pair(self):
        self.add_row(self.primary, self.collision(value="9.0"))
        started = next(row for row in self.primary if row["event"] == "mutual_dogfight_validation_started")
        for reason in ("", f"primary_uuid={PRIMARY}:opponent_uuid={OTHER}",
                       f"primary_uuid={PRIMARY}:opponent_uuid={OPPONENT}:opponent_uuid={OTHER}"):
            with self.subTest(reason=reason):
                started["reason"] = reason
                proc, result = self.verify()
                self.assertNotEqual(proc.returncode, 0, result)
                self.assertIn("scene start does not uniquely identify the selected aircraft pair", result["errors"])
                self.assertIs(result["metrics"]["scene_window_valid"], False, result)
                self.assertIsNone(result["metrics"]["primary_ground_frames"], result)
                self.assertIsNone(result["metrics"]["collision_observation_rows"], result)
                self.assertIn("scene start does not uniquely identify the selected aircraft pair", result["errors"])

    def test_scene_minimum_requires_unambiguous_reported_precision(self):
        self.add_row(self.primary, self.collision(value="9.0"))
        completion = next(row for row in self.primary
                          if row["event"] == "mutual_dogfight_validation_completed")
        original = completion["reason"]
        for replacement in ("minimum_separation=8.001", "minimum_separation=9.0oops", ""):
            with self.subTest(replacement=replacement):
                completion["reason"] = original.replace("minimum_separation=9.0", replacement)
                proc, result = self.verify()
                self.assertNotEqual(proc.returncode, 0, result)
                self.assertIn("scene completion has missing, ambiguous or invalid rounded minimum_separation", result["errors"])

    def test_scene_window_requires_ordered_integer_ticks(self):
        self.add_row(self.primary, self.collision(value="9.0"))
        completion = next(row for row in self.primary
                          if row["event"] == "mutual_dogfight_validation_completed")
        for invalid in (None, True, 200.5, float("inf"), -1, 99):
            with self.subTest(tick=invalid):
                completion["server_tick"] = invalid
                proc, result = self.verify()
                self.assertNotEqual(proc.returncode, 0, result)
                if invalid == float("inf"):
                    self.assertTrue(any("InvalidConstantError Infinity" in error for error in result["errors"]), result)
                elif invalid == 99 and type(invalid) is int:
                    self.assertIn("mutual dogfight completion must follow start", result["errors"])
                else:
                    self.assertIn("mutual dogfight completion event has missing or invalid tick", result["errors"])

    def test_scene_window_rejects_equal_ticks_even_with_same_tick_samples(self):
        for row in self.primary + self.opponent:
            row["server_tick"] = 150
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)
        self.assertIn("mutual dogfight completion must follow start", result["errors"])

    def test_scene_window_rejects_duplicate_start_or_completion(self):
        for event in ("mutual_dogfight_validation_started", "mutual_dogfight_validation_completed"):
            with self.subTest(event=event):
                row = next(row for row in self.primary if row["event"] == event)
                duplicate = row.copy()
                self.add_row(self.primary, duplicate)
                proc, result = self.verify()
                self.assertNotEqual(proc.returncode, 0, result)
                label = "start" if event.endswith("started") else "completion"
                self.assertIn(f"expected exactly one mutual dogfight {label} event; found 2", result["errors"])
                self.primary.pop(next(i for i, item in enumerate(self.primary) if item is duplicate))

    def test_scene_start_requires_nonnegative_integer_tick(self):
        start = next(row for row in self.primary if row["event"] == "mutual_dogfight_validation_started")
        for invalid in (None, True, 100.5, float("inf"), -1):
            with self.subTest(tick=invalid):
                start["server_tick"] = invalid
                proc, result = self.verify()
                self.assertNotEqual(proc.returncode, 0, result)
                if invalid == float("inf"):
                    self.assertTrue(any("InvalidConstantError Infinity" in error for error in result["errors"]), result)
                else:
                    self.assertIn("mutual dogfight start event has missing or invalid tick", result["errors"])

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
                    self.assertTrue(any("aircraft log is missing or ambiguous" in error
                                        or "aircraft UUID occurs in more than one telemetry file" in error
                                        for error in result["errors"]), result)

    def test_unrelated_aircraft_log_does_not_make_the_pair_ambiguous(self):
        row = self.row(OTHER, "other plane", "frame", 150, speed_bps=25.0, on_ground=False)
        (self.logs / "other.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
        proc, result = self.verify()
        self.assertEqual(proc.returncode, 0, result)


if __name__ == "__main__":
    unittest.main()
