"""Post-combat completion must belong to the actual primary fighter."""
import json
import copy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from mutual_fixture import fill_interior_frames


VERIFIER = Path(__file__).resolve().parents[1] / "verify_mutual_dogfight_scenario.py"
PRIMARY = "15a7c379-1310-4def-b8a0-fdaa8b1787b1"
OPPONENT = "f93acc19-18a9-44de-9f33-f0ddc38f7095"
OTHER = "7bd32675-6cff-4a29-a777-0e76c2348004"
PRIMARY_PILOT = "2a8ad002-ac1b-4f83-8903-60fb4366ddee"
OPPONENT_PILOT = "696d5d49-c397-4b53-a30d-f7eeaa531887"


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
            return {"aircraft_name": name, "aircraft_uuid": aircraft_id,
                    "pilot_uuid": PRIMARY_PILOT if aircraft_id == PRIMARY else OPPONENT_PILOT, "event": event,
                    "server_tick": tick, "reason": reason, **extra}

        self.primary_path = logs / "primary.jsonl"
        self.primary_rows = [
            row(primary, PRIMARY, "mutual_dogfight_validation_started", 100,
                f"primary_uuid={PRIMARY}:primary_pilot_uuid={PRIMARY_PILOT}:"
                f"opponent_uuid={OPPONENT}:opponent_pilot_uuid={OPPONENT_PILOT}"),
            row(primary, PRIMARY, "combat_target_acquired", 101,
                f"uuid={OPPONENT_PILOT}:target_faction=blue:explicit_faction_hostile=true"),
            row(primary, PRIMARY, "air_combat_action_transition", 102,
                "to=INTERCEPT:doctrine=turn_fighter"),
            row(primary, PRIMARY, "weapon_fire", 103, f"target_uuid={OPPONENT_PILOT}"),
            row(primary, PRIMARY, "frame", 104, speed_bps=25, on_ground=False),
            row(primary, PRIMARY, "control_adapter", 104, f"other_uuid={OPPONENT}:current=9.0",
                applied_safety_override="collision_avoidance"),
            row(primary, PRIMARY, "mutual_dogfight_validation_completed", 300,
                "age_ticks=200:minimum_separation=10.0:maximum_separation=100.0:"
                "primary_track_ticks=150:opponent_track_ticks=150:"
                "primary_combat_ticks=150:opponent_combat_ticks=150"),
            row(primary, PRIMARY, "phase_transition", 400,
                "BRAKE->PARKED:complete_stop_stable_for_40_ticks", phase="PARKED"),
            row(primary, PRIMARY, "frame", 400, phase="PARKED", on_ground=True,
                horizontal_speed_bps=0.0),
            row(primary, PRIMARY, "session_end", 400,
                "validation_aircraft_cleanup", phase="PARKED"),
        ]
        self.primary_rows = fill_interior_frames(self.primary_rows, 100, 300)
        self.write_primary()
        rows = [
            row(opponent, OPPONENT, "combat_target_acquired", 101,
                f"uuid={PRIMARY_PILOT}:target_faction=red:explicit_faction_hostile=true"),
            row(opponent, OPPONENT, "air_combat_action_transition", 102,
                "to=INTERCEPT:doctrine=energy_fighter"),
            row(opponent, OPPONENT, "weapon_fire", 103, f"target_uuid={PRIMARY_PILOT}"),
            row(opponent, OPPONENT, "frame", 104, speed_bps=25, on_ground=False),
            row(opponent, OPPONENT, "control_adapter", 104, f"other_uuid={PRIMARY}:current=9.0",
                applied_safety_override="collision_avoidance"),
        ]
        rows = fill_interior_frames(rows, 100, 300)
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
                    expected = ("primary A6M summary UUID does not uniquely match the primary log and scene"
                                if key == "entity_id" else f"post-combat summary {key} is invalid")
                    self.assertIn(expected, result["errors"], result)
                    row[key] = original

    def test_summary_result_counts_must_be_consistent(self):
        original = self.summary.copy()
        for key, value in (("state", "running"), ("total", 2), ("total", True),
                           ("completed", 0), ("completed", "1"), ("results", []),
                           ("results", [None]), ("results", [original["results"][0]] * 2)):
            with self.subTest(key=key, value=value):
                self.summary = dict(original, **{key: value})
                code, result = self.verify()
                self.assertNotEqual(code, 0, result)
                self.assertFalse(result["passed"])
                if key in ("total", "completed"):
                    expected = f"primary post-combat summary {key} does not match result count"
                elif key == "state":
                    expected = "primary post-combat mission summary was not complete"
                elif value == [original["results"][0]] * 2:
                    expected = "mutual verification supports exactly one A6M summary result; aircraft=all is unsupported"
                else:
                    expected = "primary post-combat summary must contain aircraft results"
                self.assertIn(expected, result["errors"], result)

    def test_multiple_aircraft_summary_cannot_claim_unverified_secondary(self):
        secondary = dict(self.summary["results"][0], entity_id="warfare_wings:p51d",
                         aircraft_uuid=OTHER)
        self.summary["total"] = self.summary["completed"] = 2
        self.summary["results"].append(secondary)
        code, result = self.verify()
        self.assertNotEqual(code, 0, result)
        self.assertFalse(result["passed"])
        self.assertIn("mutual verification supports exactly one A6M summary result; "
                      "aircraft=all is unsupported", result["errors"])

    def test_multiple_aircraft_summary_rejects_bad_or_ambiguous_results(self):
        secondary = dict(self.summary["results"][0], entity_id="warfare_wings:p51d",
                         aircraft_uuid=OTHER)
        self.summary["total"] = self.summary["completed"] = 2
        self.summary["results"].append(secondary)
        original = copy.deepcopy(self.summary)
        for key, value in (("passed", "false"), ("reason", "failed"),
                           ("final_phase", "CRUISE_OUTBOUND"),
                           ("last_transition_reason", "unknown"),
                           ("entity_id", " "), ("entity_id", "bad id"),
                           ("entity_id", "warfare_wings:"), ("entity_id", ":p51d"),
                           ("entity_id", "Warfare_Wings:p51d"),
                           ("entity_id", "warfare_wings:p51d:extra"),
                           ("entity_id", ["warfare_wings:p51d"]), ("entity_id", True),
                           ("entity_id", "p51d"), ("entity_id", "warfare_wings:a6m"),
                           ("aircraft_uuid", None), ("aircraft_uuid", "invalid"),
                           ("aircraft_uuid", PRIMARY.upper())):
            with self.subTest(key=key, value=value):
                self.summary = copy.deepcopy(original)
                self.summary["results"][1][key] = value
                code, result = self.verify()
                self.assertNotEqual(code, 0, result)
                self.assertFalse(result["passed"])
                if key == "aircraft_uuid":
                    expected = "post-combat summary aircraft UUIDs must be valid and unique"
                elif key == "entity_id":
                    expected = ("post-combat summary aircraft entity_ids must be unique"
                                if value == "warfare_wings:a6m" else
                                "post-combat summary aircraft entity_id is invalid")
                else:
                    expected = f"post-combat summary {key} is invalid"
                self.assertIn(expected, result["errors"], result)

    def test_opponent_scene_aircraft_is_not_a_summary_primary_aircraft(self):
        secondary = dict(self.summary["results"][0], entity_id="warfare_wings:p51d",
                         aircraft_uuid=OPPONENT)
        self.summary["total"] = self.summary["completed"] = 2
        self.summary["results"].append(secondary)
        code, result = self.verify()
        self.assertNotEqual(code, 0, result)
        self.assertIn("scene opponent UUID must be distinct from all summary aircraft", result["errors"], result)

    def test_summary_parked_must_agree_with_primary_terminal_log(self):
        baseline = copy.deepcopy(self.primary_rows)
        for case in ("no parked transition", "no session end", "abort after parked",
                     "end before parked", "wrong end reason", "parked before combat complete",
                     "contradictory later frame", "invalid terminal tick"):
            with self.subTest(case=case):
                self.primary_rows = copy.deepcopy(baseline)
                if case == "no parked transition":
                    self.primary_rows.pop(-3)
                elif case == "no session end":
                    self.primary_rows.pop()
                elif case == "abort after parked":
                    self.primary_rows.append(dict(self.primary_rows[-1], event="phase_transition",
                                                  phase="ABORTED", reason="PARKED->ABORTED:failed"))
                elif case == "end before parked":
                    self.primary_rows[-3], self.primary_rows[-1] = self.primary_rows[-1], self.primary_rows[-3]
                elif case == "wrong end reason":
                    self.primary_rows[-1]["reason"] = "other_cleanup"
                elif case == "contradictory later frame":
                    self.primary_rows.insert(-1, dict(self.primary_rows[-2], phase="CRUISE"))
                elif case == "invalid terminal tick":
                    self.primary_rows[-1]["server_tick"] = True
                else:
                    self.primary_rows[-3]["server_tick"] = 299
                self.write_primary()
                code, result = self.verify()
                self.assertNotEqual(code, 0, result)
                self.assertIn("primary post-combat log does not establish parked validation cleanup",
                              result["errors"], result)

    def test_parked_frame_must_confirm_grounded_low_speed_on_transition_tick(self):
        baseline = copy.deepcopy(self.primary_rows)
        for case in ("missing", "wrong tick", "airborne", "missing ground", "fast", "negative speed",
                     "missing speed", "boolean speed", "string speed", "infinite speed", "nan speed",
                     "later fast frame", "later tick past cleanup"):
            with self.subTest(case=case):
                self.primary_rows = copy.deepcopy(baseline)
                frame = self.primary_rows[-2]
                if case == "missing":
                    self.primary_rows.pop(-2)
                elif case == "wrong tick":
                    frame["server_tick"] = 401
                elif case == "airborne":
                    frame["on_ground"] = False
                elif case == "missing ground":
                    del frame["on_ground"]
                elif case in ("fast", "negative speed", "boolean speed", "string speed",
                              "infinite speed", "nan speed"):
                    frame["horizontal_speed_bps"] = {"fast": 0.25, "negative speed": -1.0,
                        "boolean speed": True, "string speed": "0.0", "infinite speed": float("inf"),
                        "nan speed": float("nan")}[case]
                elif case == "missing speed":
                    del frame["horizontal_speed_bps"]
                elif case == "later fast frame":
                    self.primary_rows.insert(-1, dict(frame, horizontal_speed_bps=120))
                else:
                    self.primary_rows.insert(-1, dict(frame, server_tick=401))
                self.write_primary()
                code, result = self.verify()
                self.assertNotEqual(code, 0, result)
                self.assertIn("primary post-combat log does not establish parked validation cleanup",
                              result["errors"], result)

    def test_every_parked_event_tick_is_valid_and_ordered_until_cleanup(self):
        baseline = copy.deepcopy(self.primary_rows)
        for bad_tick in (None, True, "400", -1, 399, 401):
            with self.subTest(tick=bad_tick):
                self.primary_rows = copy.deepcopy(baseline)
                event = dict(self.primary_rows[-2], event="control_authority_change",
                             server_tick=bad_tick)
                self.primary_rows.insert(-1, event)
                self.write_primary()
                code, result = self.verify()
                self.assertNotEqual(code, 0, result)
                self.assertIn("primary post-combat log does not establish parked validation cleanup",
                              result["errors"], result)

        # A terminal tick later than the inserted records cannot mask their reversal.
        self.primary_rows = copy.deepcopy(baseline)
        self.primary_rows.insert(-1, dict(self.primary_rows[-2], event="control_authority_change",
                                          server_tick=402))
        self.primary_rows.insert(-1, dict(self.primary_rows[-2], event="control_authority_change",
                                          server_tick=401))
        self.primary_rows[-1]["server_tick"] = 403
        self.write_primary()
        code, result = self.verify()
        self.assertNotEqual(code, 0, result)
        self.assertIn("primary post-combat log does not establish parked validation cleanup",
                      result["errors"], result)

    def test_multiple_aircraft_summary_requires_primary_a6m(self):
        secondary = dict(self.summary["results"][0], entity_id="warfare_wings:p51d",
                         aircraft_uuid=OTHER)
        self.summary["total"] = self.summary["completed"] = 2
        self.summary["results"].append(secondary)
        self.summary["results"][0]["entity_id"] = "warfare_wings:b17"
        code, result = self.verify()
        self.assertNotEqual(code, 0, result)
        self.assertIn("primary A6M summary UUID does not uniquely match the primary log and scene",
                      result["errors"], result)

    def test_summary_uuid_must_match_every_primary_log_row(self):
        row = self.summary["results"][0]
        for value in (None, "not-a-uuid", OTHER, OPPONENT):
            with self.subTest(value=value):
                row["aircraft_uuid"] = value
                code, result = self.verify()
                self.assertNotEqual(code, 0, result)
                self.assertFalse(result["passed"])
                self.assertIn("primary A6M summary UUID does not uniquely match the primary log and scene",
                              result["errors"], result)
        row["aircraft_uuid"] = PRIMARY
        next(row for row in self.primary_rows if row["event"] == "air_combat_action_transition")["aircraft_uuid"] = OTHER
        self.write_primary()
        code, result = self.verify()
        self.assertNotEqual(code, 0, result)
        self.assertFalse(result["passed"])
        self.assertIn("primary A6M summary UUID does not uniquely match the primary log and scene",
                      result["errors"], result)

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
        self.assertIn("primary A6M summary UUID does not uniquely match the primary log and scene",
                      result["errors"], result)

    def test_malformed_summary_root_produces_failure_result(self):
        self.summary = []
        code, result = self.verify()
        self.assertNotEqual(code, 0, result)
        self.assertFalse(result["passed"])
        self.assertTrue(any(error.startswith("cannot read validation summary ") and error.endswith(": ValueError")
                            for error in result["errors"]), result)


if __name__ == "__main__":
    unittest.main()
