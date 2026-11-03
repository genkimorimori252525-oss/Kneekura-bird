"""Mutual combat evidence must name the two scene participants and their pilots."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


VERIFIER = Path(__file__).resolve().parents[1] / "verify_mutual_dogfight_scenario.py"
AIRCRAFT_A = "15a7c379-1310-4def-b8a0-fdaa8b1787b1"
PILOT_A = "2a8ad002-ac1b-4f83-8903-60fb4366ddee"
AIRCRAFT_B = "f93acc19-18a9-44de-9f33-f0ddc38f7095"
PILOT_B = "696d5d49-c397-4b53-a30d-f7eeaa531887"
OTHER = "7bd32675-6cff-4a29-a777-0e76c2348004"


class MutualTargetIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.logs = self.root / "world/wwdebug/autopilot/run/aircraft"
        self.logs.mkdir(parents=True)

        def row(name, aircraft, pilot, event, tick, reason="", **extra):
            return {"aircraft_name": name, "aircraft_uuid": aircraft, "pilot_uuid": pilot,
                    "event": event, "server_tick": tick, "reason": reason, **extra}

        a = lambda event, tick, reason="", **extra: row(
            "AUTOPILOT TEST warfare_wings:a6m", AIRCRAFT_A, PILOT_A, event, tick, reason, **extra)
        b = lambda event, tick, reason="", **extra: row(
            "AUTOPILOT TEST MUTUAL BLUE P47N", AIRCRAFT_B, PILOT_B, event, tick, reason, **extra)
        self.primary = [
            a("mutual_dogfight_validation_started", 100,
              f"primary_uuid={AIRCRAFT_A}:primary_pilot_uuid={PILOT_A}:"
              f"opponent_uuid={AIRCRAFT_B}:opponent_pilot_uuid={PILOT_B}"),
            a("combat_target_acquired", 101,
              f"entity.minecraft.villager:uuid={PILOT_B}:target_faction=blue:explicit_faction_hostile=true"),
            a("air_combat_action_transition", 102, "to=INTERCEPT:doctrine=turn_fighter"),
            a("weapon_fire", 103, f"target_uuid={PILOT_B}:weapons_fired=2"),
            a("frame", 104, speed_bps=25, on_ground=False),
            a("control_adapter", 104, f"other_uuid={AIRCRAFT_B}:current=9.0",
              applied_safety_override="collision_avoidance"),
            a("mutual_dogfight_validation_completed", 300,
              "age_ticks=200:minimum_separation=10.0:maximum_separation=100.0:"
              "primary_track_ticks=150:opponent_track_ticks=150:"
              "primary_combat_ticks=150:opponent_combat_ticks=150"),
            a("phase_transition", 400, "BRAKE->PARKED:complete_stop_stable_for_40_ticks", phase="PARKED"),
            a("frame", 400, phase="PARKED", on_ground=True, horizontal_speed_bps=0.0),
            a("session_end", 400, "validation_aircraft_cleanup", phase="PARKED"),
        ]
        self.opponent = [
            b("combat_target_acquired", 101,
              f"entity.minecraft.villager:uuid={PILOT_A}:target_faction=red:explicit_faction_hostile=true"),
            b("air_combat_action_transition", 102, "to=INTERCEPT:doctrine=energy_fighter"),
            b("weapon_fire", 103, f"target_uuid={PILOT_A}:weapons_fired=2"),
            b("frame", 104, speed_bps=25, on_ground=False),
            b("control_adapter", 104, f"other_uuid={AIRCRAFT_A}:current=9.0",
              applied_safety_override="collision_avoidance"),
        ]
        (self.root / "validation-summary-1.json").write_text(
            json.dumps({"state": "complete", "total": 1, "completed": 1, "results": [{
                "entity_id": "warfare_wings:a6m", "aircraft_uuid": AIRCRAFT_A, "passed": True,
                "reason": "completed_full_mission", "final_phase": "PARKED",
                "last_transition_reason": "complete_stop_stable_for_40_ticks"}]}), encoding="utf-8")

    def verify(self):
        for filename, rows in (("primary.jsonl", self.primary), ("opponent.jsonl", self.opponent)):
            (self.logs / filename).write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        output = self.root / "result.json"
        output.unlink(missing_ok=True)
        result = subprocess.run([sys.executable, str(VERIFIER), "--root", str(self.root),
                                 "--gradle-status", "0", "--output", str(output)],
                                capture_output=True, text=True, check=False)
        self.assertTrue(output.exists(), result.stderr)
        return result.returncode, json.loads(output.read_text(encoding="utf-8"))

    def test_both_participants_acquire_and_fire_at_the_other_pilot(self):
        code, result = self.verify()
        self.assertEqual(code, 0, result)
        self.assertTrue(result["passed"])

    def test_duplicate_participant_logs_are_ambiguous(self):
        for rows in (self.primary, self.opponent):
            with self.subTest(name=rows[0]["aircraft_name"]):
                duplicate = self.logs / "duplicate.jsonl"
                duplicate.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
                code, result = self.verify()
                self.assertNotEqual(code, 0, result)
                role = "primary" if rows is self.primary else "opponent"
                self.assertIn(f"{role} aircraft log is missing or ambiguous", result["errors"], result)
                duplicate.unlink()

    def test_start_requires_four_distinct_valid_participant_ids(self):
        start = self.primary[0]
        original = start["reason"]
        for invalid in ("", "primary_uuid=not-a-uuid", original.replace(PILOT_B, PILOT_A),
                        original.replace(AIRCRAFT_B, AIRCRAFT_A)):
            with self.subTest(value=invalid):
                start["reason"] = invalid
                code, result = self.verify()
                self.assertNotEqual(code, 0, result)
                self.assertIn("mutual dogfight start must identify four distinct participant UUIDs",
                              result["errors"], result)
        start["reason"] = original

    def test_each_log_must_match_scene_aircraft_and_pilot(self):
        for rows in (self.primary, self.opponent):
            for field in ("aircraft_uuid", "pilot_uuid"):
                item = rows[1]
                value = item[field]
                for invalid in (None, OTHER):
                    with self.subTest(log=rows[0]["aircraft_name"], field=field, value=invalid):
                        item[field] = invalid
                        code, result = self.verify()
                        self.assertNotEqual(code, 0, result)
                        role = "primary" if rows is self.primary else "opponent"
                        self.assertIn(f"{role} combat-window log does not match the scene aircraft and pilot",
                                      result["errors"], result)
                item[field] = value

    def test_acquisition_and_fire_must_target_opposing_pilot(self):
        for rows in (self.primary, self.opponent):
            for event in ("combat_target_acquired", "weapon_fire"):
                item = next(row for row in rows if row["event"] == event)
                reason = item["reason"]
                target = PILOT_B if rows is self.primary else PILOT_A
                for invalid in (OTHER, "not-a-uuid", ""):
                    with self.subTest(log=rows[0]["aircraft_name"], event=event, target=invalid):
                        item["reason"] = reason.replace(target, invalid)
                        code, result = self.verify()
                        self.assertNotEqual(code, 0, result)
                        role = "primary" if rows is self.primary else "opponent"
                        kind = "acquisition" if event == "combat_target_acquired" else "fire"
                        self.assertIn(f"{role} {kind} must target the opposing pilot in the combat window",
                                      result["errors"], result)
                item["reason"] = reason

    def test_hostile_faction_fields_must_be_unambiguous_exact_values(self):
        for rows, faction in ((self.primary, "blue"), (self.opponent, "red")):
            acquisition = next(row for row in rows if row["event"] == "combat_target_acquired")
            original = acquisition["reason"]
            for bad in (original.replace(f"target_faction={faction}", f"target_faction={faction}ish"),
                        original.replace("explicit_faction_hostile=true", "explicit_faction_hostile=truefalse"),
                        original + f":target_faction={faction}",
                        original + ":explicit_faction_hostile=true"):
                with self.subTest(name=rows[0]["aircraft_name"], reason=bad):
                    acquisition["reason"] = bad
                    code, result = self.verify()
                    self.assertNotEqual(code, 0, result)
                    name = "A6M" if rows is self.primary else "P-47N"
                    team = "blue" if rows is self.primary else "red"
                    self.assertIn(f"{name} acquisitions must identify the {team}-faction opponent as explicitly hostile",
                                  result["errors"], result)
            acquisition["reason"] = original

    def test_additional_malformed_faction_acquisition_is_rejected(self):
        for rows in (self.primary, self.opponent):
            item = dict(next(row for row in rows if row["event"] == "combat_target_acquired"))
            item["reason"] = item["reason"].replace("explicit_faction_hostile=true", "explicit_faction_hostile=truefalse")
            rows.append(item)
            code, result = self.verify()
            self.assertNotEqual(code, 0, result)
            name = "A6M" if rows is self.primary else "P-47N"
            team = "blue" if rows is self.primary else "red"
            self.assertIn(f"{name} acquisitions must identify the {team}-faction opponent as explicitly hostile",
                          result["errors"], result)
            rows.pop()

    def test_spaced_duplicate_acquisition_fields_are_rejected(self):
        for rows in (self.primary, self.opponent):
            item = next(row for row in rows if row["event"] == "combat_target_acquired")
            original = item["reason"]
            for duplicate in (": target_faction=red", ":target_faction =red",
                              ": explicit_faction_hostile=false", f": uuid={OTHER}"):
                with self.subTest(name=rows[0]["aircraft_name"], duplicate=duplicate):
                    item["reason"] = original + duplicate
                    code, result = self.verify()
                    self.assertNotEqual(code, 0, result)
                    role = "primary" if rows is self.primary else "opponent"
                    if "uuid" in duplicate:
                        self.assertIn(f"{role} acquisition must target the opposing pilot in the combat window",
                                      result["errors"], result)
                    else:
                        name = "A6M" if rows is self.primary else "P-47N"
                        team = "blue" if rows is self.primary else "red"
                        self.assertIn(f"{name} acquisitions must identify the {team}-faction opponent as explicitly hostile",
                                      result["errors"], result)
            item["reason"] = original

    def test_acquisition_and_fire_only_outside_scene_do_not_count(self):
        for rows in (self.primary, self.opponent):
            for event in ("combat_target_acquired", "weapon_fire"):
                item = next(row for row in rows if row["event"] == event)
                old = item["server_tick"]
                for outside in (99, 301):
                    with self.subTest(log=rows[0]["aircraft_name"], event=event, tick=outside):
                        item["server_tick"] = outside
                        code, result = self.verify()
                        self.assertNotEqual(code, 0, result)
                        role = "primary" if rows is self.primary else "opponent"
                        kind = "acquisition" if event == "combat_target_acquired" else "fire"
                        self.assertIn(f"{role} {kind} must target the opposing pilot in the combat window",
                                      result["errors"], result)
                item["server_tick"] = old

    def test_additional_in_window_fire_at_another_target_is_rejected(self):
        item = dict(next(row for row in self.primary if row["event"] == "weapon_fire"))
        item["reason"] = f"target_uuid={OTHER}:weapons_fired=1"
        self.primary.append(item)
        code, result = self.verify()
        self.assertNotEqual(code, 0, result)
        self.assertIn("primary fire must target the opposing pilot in the combat window", result["errors"], result)

    def test_uuid_normalization_accepts_uppercase(self):
        self.primary[1]["reason"] = self.primary[1]["reason"].replace(PILOT_B, PILOT_B.upper())
        self.opponent[0]["aircraft_uuid"] = AIRCRAFT_B.upper()
        code, result = self.verify()
        self.assertEqual(code, 0, result)

    def test_bad_event_ticks_cannot_hide_wrong_identity_or_target(self):
        for rows in (self.primary, self.opponent):
            for event in ("frame", "combat_target_acquired", "weapon_fire"):
                item = dict(next(row for row in rows if row["event"] == event))
                if event == "frame":
                    item["pilot_uuid"] = OTHER
                elif event == "combat_target_acquired":
                    item["reason"] = f"uuid={OTHER}:target_faction=red:explicit_faction_hostile=true"
                else:
                    item["reason"] = f"target_uuid={OTHER}"
                for invalid in (None, "bad", "104", -1, False):
                    with self.subTest(log=rows[0]["aircraft_name"], event=event, tick=invalid):
                        item["server_tick"] = invalid
                        rows.append(item)
                        code, result = self.verify()
                        self.assertNotEqual(code, 0, result)
                        role = "primary" if rows is self.primary else "opponent"
                        self.assertIn(f"{role} telemetry must have nonnegative integer server ticks",
                                      result["errors"], result)
                        rows.pop()

    def test_scene_bounds_require_nonnegative_integer_ticks(self):
        for event in ("mutual_dogfight_validation_started", "mutual_dogfight_validation_completed"):
            item = next(row for row in self.primary if row["event"] == event)
            original = item["server_tick"]
            for invalid in (None, "100", -1, False):
                with self.subTest(event=item["event"], tick=invalid):
                    item["server_tick"] = invalid
                    code, result = self.verify()
                    self.assertNotEqual(code, 0, result)
                    label = "start" if event.endswith("started") else "completion"
                    self.assertIn(f"mutual dogfight {label} event has missing or invalid tick",
                                  result["errors"], result)
            item["server_tick"] = original

    def test_action_and_doctrine_only_outside_scene_do_not_count(self):
        for rows in (self.primary, self.opponent):
            item = next(row for row in rows if row["event"] == "air_combat_action_transition")
            original = item["server_tick"]
            for outside in (99, 301):
                with self.subTest(log=rows[0]["aircraft_name"], tick=outside):
                    item["server_tick"] = outside
                    code, result = self.verify()
                    self.assertNotEqual(code, 0, result)
                    name = "A6M" if rows is self.primary else "P-47N"
                    self.assertIn(f"{name} selected no air-combat actions", result["errors"], result)
            item["server_tick"] = original

    def test_transition_without_action_is_not_an_action(self):
        for rows in (self.primary, self.opponent):
            item = next(row for row in rows if row["event"] == "air_combat_action_transition")
            original = item["reason"]
            item["reason"] = original.replace("to=INTERCEPT:", "")
            with self.subTest(log=rows[0]["aircraft_name"]):
                code, result = self.verify()
                self.assertNotEqual(code, 0, result)
                name = "A6M" if rows is self.primary else "P-47N"
                self.assertIn(f"{name} selected no air-combat actions", result["errors"], result)
            item["reason"] = original

    def test_action_must_be_a_valid_combat_action(self):
        for rows in (self.primary, self.opponent):
            item = next(row for row in rows if row["event"] == "air_combat_action_transition")
            original = item["reason"]
            for action in ("NONE", "INVENTED", "INTERCEPT:to=NONE"):
                with self.subTest(name=rows[0]["aircraft_name"], action=action):
                    item["reason"] = original.replace("INTERCEPT", action)
                    code, result = self.verify()
                    self.assertNotEqual(code, 0, result)
                    name = "A6M" if rows is self.primary else "P-47N"
                    self.assertIn(f"{name} selected no air-combat actions", result["errors"], result)
            item["reason"] = original

    def test_valid_action_and_doctrine_must_be_in_the_same_transition(self):
        for rows, doctrine in ((self.primary, "turn_fighter"), (self.opponent, "energy_fighter")):
            item = next(row for row in rows if row["event"] == "air_combat_action_transition")
            original = item["reason"]
            item["reason"] = "to=INTERCEPT:doctrine=wrong"
            extra = dict(item, reason=f"doctrine={doctrine}")
            rows.append(extra)
            code, result = self.verify()
            self.assertNotEqual(code, 0, result)
            name = "A6M" if rows is self.primary else "P-47N"
            self.assertIn(f"{name} selected no air-combat actions", result["errors"], result)
            rows.pop()
            item["reason"] = original

    def test_spaced_duplicate_action_fields_are_rejected(self):
        for rows in (self.primary, self.opponent):
            item = next(row for row in rows if row["event"] == "air_combat_action_transition")
            original = item["reason"]
            for duplicate in (": to=NONE", ":to =NONE", ": doctrine=invalid", ":doctrine =invalid"):
                with self.subTest(name=rows[0]["aircraft_name"], duplicate=duplicate):
                    item["reason"] = original + duplicate
                    code, result = self.verify()
                    self.assertNotEqual(code, 0, result)
                    name = "A6M" if rows is self.primary else "P-47N"
                    self.assertIn(f"{name} selected no air-combat actions", result["errors"], result)
            item["reason"] = original

    def test_every_fire_requires_prior_in_window_acquisition(self):
        for rows in (self.primary, self.opponent):
            acquisition = next(row for row in rows if row["event"] == "combat_target_acquired")
            fire = next(row for row in rows if row["event"] == "weapon_fire")
            original_tick = acquisition["server_tick"]
            acquisition["server_tick"] = fire["server_tick"] + 1
            with self.subTest(name=rows[0]["aircraft_name"], case="future tick"):
                code, result = self.verify()
                self.assertNotEqual(code, 0, result)
                role = "primary" if rows is self.primary else "opponent"
                self.assertIn(f"{role} fired without prior in-window acquisition of the opposing pilot",
                              result["errors"], result)
            acquisition["server_tick"] = fire["server_tick"]
            transition = next(row for row in rows if row["event"] == "air_combat_action_transition")
            transition_tick = transition["server_tick"]
            transition["server_tick"] = fire["server_tick"]
            acquisition_index, fire_index = rows.index(acquisition), rows.index(fire)
            rows[acquisition_index], rows[fire_index] = rows[fire_index], rows[acquisition_index]
            with self.subTest(name=rows[0]["aircraft_name"], case="same tick reversed"):
                code, result = self.verify()
                self.assertNotEqual(code, 0, result)
                role = "primary" if rows is self.primary else "opponent"
                self.assertIn(f"{role} fired without prior in-window acquisition of the opposing pilot",
                              result["errors"], result)
            rows[acquisition_index], rows[fire_index] = rows[fire_index], rows[acquisition_index]
            with self.subTest(name=rows[0]["aircraft_name"], case="same tick ordered"):
                code, result = self.verify()
                self.assertEqual(code, 0, result)
            acquisition["server_tick"] = original_tick
            transition["server_tick"] = transition_tick

    def test_later_acquisition_does_not_justify_earlier_fire(self):
        for rows in (self.primary, self.opponent):
            fire = next(row for row in rows if row["event"] == "weapon_fire")
            earlier = dict(fire, server_tick=100)
            rows.insert(0, earlier)
            code, result = self.verify()
            self.assertNotEqual(code, 0, result)
            role = "primary" if rows is self.primary else "opponent"
            self.assertIn(f"{role} fired without prior in-window acquisition of the opposing pilot",
                          result["errors"], result)
            rows.pop(0)

    def test_loss_requires_new_acquisition_before_fire(self):
        for rows in (self.primary, self.opponent):
            acquisition = next(row for row in rows if row["event"] == "combat_target_acquired")
            fire = next(row for row in rows if row["event"] == "weapon_fire")
            loss = dict(acquisition, event="combat_target_lost", reason="no_eligible_hostile_target",
                        server_tick=fire["server_tick"])
            index = rows.index(fire)
            rows.insert(index, loss)
            with self.subTest(name=rows[0]["aircraft_name"], case="lost before fire"):
                code, result = self.verify()
                self.assertNotEqual(code, 0, result)
                role = "primary" if rows is self.primary else "opponent"
                self.assertIn(f"{role} fired without prior in-window acquisition of the opposing pilot",
                              result["errors"], result)
            reacquired = dict(acquisition, server_tick=fire["server_tick"])
            rows.insert(index + 1, reacquired)
            with self.subTest(name=rows[0]["aircraft_name"], case="reacquired same tick"):
                code, result = self.verify()
                self.assertEqual(code, 0, result)
            loss["server_tick"] = fire["server_tick"] + 1
            with self.subTest(name=rows[0]["aircraft_name"], case="loss tick goes backwards"):
                code, result = self.verify()
                self.assertNotEqual(code, 0, result)
                role = "primary" if rows is self.primary else "opponent"
                self.assertIn(f"{role} acquisition, loss and fire ticks must be ordered in the log",
                              result["errors"], result)
            rows.remove(reacquired)
            rows.remove(loss)


if __name__ == "__main__":
    unittest.main()
