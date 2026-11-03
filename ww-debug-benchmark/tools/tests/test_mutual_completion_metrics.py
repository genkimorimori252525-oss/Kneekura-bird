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
            json.dumps({"state": "complete", "results": [{"passed": True}]}), encoding="utf-8")
        self.primary = self.logs / "primary.jsonl"
        self.opponent = self.logs / "opponent.jsonl"
        self.write_rows(self.primary, PRIMARY, [
            {"event": "mutual_dogfight_validation_started", "server_tick": 10},
            {"event": "mutual_dogfight_validation_status", "server_tick": 15, "reason": "separation=9.5"},
            {"event": "combat_target_acquired", "reason": "target_faction=blue:explicit_faction_hostile=true"},
            {"event": "air_combat_action_transition", "reason": "doctrine=turn_fighter:to=TURN"},
            {"event": "weapon_fire"},
            {"event": "frame", "server_tick": 15, "speed_bps": 30, "on_ground": False},
            {"event": "mutual_dogfight_validation_completed", "server_tick": 210, "reason": COMPLETION},
        ])
        self.write_rows(self.opponent, OPPONENT, [
            {"event": "combat_target_acquired", "reason": "target_faction=red:explicit_faction_hostile=true"},
            {"event": "air_combat_action_transition", "reason": "doctrine=energy_fighter:to=TURN"},
            {"event": "weapon_fire"},
            {"event": "frame", "server_tick": 15, "speed_bps": 30, "on_ground": False},
        ])

    @staticmethod
    def write_rows(path, name, rows):
        path.write_text("".join(json.dumps(dict(row, aircraft_name=name)) + "\n" for row in rows),
                        encoding="utf-8")

    def set_completion(self, reason, server_tick=None):
        rows = [json.loads(line) for line in self.primary.read_text(encoding="utf-8").splitlines()]
        for row in rows:
            if row.get("event") == "mutual_dogfight_validation_completed":
                row["reason"] = reason
                if server_tick is not None:
                    row["server_tick"] = server_tick
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
                    self.assertTrue(any(field in error for error in result["errors"]), result)
            with self.subTest(field=field, value="duplicate"):
                self.set_completion(COMPLETION.replace(f"{field}=150", f"{field}=0:{field}=150"))
                proc, result = self.verify()
                self.assertNotEqual(proc.returncode, 0, result)
                self.assertTrue(any(field in error for error in result["errors"]), result)
            with self.subTest(field=field, value="duplicate with whitespace"):
                self.set_completion(COMPLETION.replace(f"{field}=150", f"{field} =0:{field}=150"))
                proc, result = self.verify()
                self.assertNotEqual(proc.returncode, 0, result)
                self.assertTrue(any(field in error for error in result["errors"]), result)

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
                self.assertTrue(any("separation" in error for error in result["errors"]), result)

    def test_completion_fields_cannot_be_missing(self):
        for field in ("primary_track_ticks", "opponent_track_ticks", "primary_combat_ticks", "opponent_combat_ticks"):
            with self.subTest(field=field):
                self.set_completion(COMPLETION.replace(f"{field}=150:", ""))
                proc, result = self.verify()
                self.assertNotEqual(proc.returncode, 0, result)
                self.assertTrue(any(field in error for error in result["errors"]), result)

    def test_completion_must_be_unique(self):
        with self.primary.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"aircraft_name": PRIMARY,
                                     "event": "mutual_dogfight_validation_completed",
                                     "server_tick": 211, "reason": COMPLETION}) + "\n")
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)
        self.assertTrue(any("completion event" in error for error in result["errors"]), result)

    def test_scene_age_is_present_unique_positive_java_integer(self):
        for field in ("age_ticks=0", "age_ticks=-1", "age_ticks=200junk", "age_ticks=200.0",
                      "age_ticks=2147483648", "age_ticks=1:age_ticks=200", ""):
            with self.subTest(field=field):
                replacement = field + ":" if field else ""
                self.set_completion(COMPLETION.replace("age_ticks=200:", replacement))
                proc, result = self.verify()
                self.assertNotEqual(proc.returncode, 0, result)
                self.assertTrue(any("age_ticks" in error for error in result["errors"]), result)

    def test_each_counter_cannot_exceed_scene_age(self):
        for field in ("primary_track_ticks", "opponent_track_ticks",
                      "primary_combat_ticks", "opponent_combat_ticks"):
            with self.subTest(field=field):
                self.set_completion(COMPLETION.replace(f"{field}=150", f"{field}=1000"))
                proc, result = self.verify()
                self.assertNotEqual(proc.returncode, 0, result)
                self.assertTrue(any(field in error and "age_ticks" in error for error in result["errors"]), result)

    def test_counters_equal_to_scene_age_are_accepted(self):
        self.set_completion(COMPLETION.replace("=150", "=200"))
        proc, result = self.verify()
        self.assertEqual(proc.returncode, 0, result)
        self.assertEqual(result["metrics"]["scene_age_ticks"], 200)

    def test_scene_age_cannot_exceed_combat_window(self):
        self.set_completion(COMPLETION.replace("age_ticks=200", "age_ticks=2000"), server_tick=2010)
        proc, result = self.verify()
        self.assertEqual(proc.returncode, 0, result)
        self.assertEqual(result["metrics"]["scene_age_ticks"], 2000)
        for age in (2001, 2_147_483_647):
            with self.subTest(age=age):
                self.set_completion(COMPLETION.replace("age_ticks=200", f"age_ticks={age}"), server_tick=2010)
                proc, result = self.verify()
                self.assertNotEqual(proc.returncode, 0, result)
                self.assertTrue(any("age_ticks" in error and "2000" in error
                                    for error in result["errors"]), result)

    def test_scene_age_cannot_exceed_elapsed_server_ticks(self):
        for age in (201, 2000):
            with self.subTest(age=age):
                self.set_completion(COMPLETION.replace("age_ticks=200", f"age_ticks={age}"))
                proc, result = self.verify()
                self.assertNotEqual(proc.returncode, 0, result)
                self.assertTrue(any("age_ticks" in error and "elapsed" in error
                                    for error in result["errors"]), result)

    def test_scene_age_can_be_less_than_elapsed_server_ticks(self):
        self.set_completion(COMPLETION.replace("age_ticks=200", "age_ticks=100").replace("=150", "=100"))
        proc, result = self.verify()
        self.assertEqual(proc.returncode, 0, result)
        self.assertEqual(result["metrics"]["scene_age_ticks"], 100)

    def test_tick_boundaries_must_be_unambiguous_nonnegative_integers(self):
        original = self.primary.read_text(encoding="utf-8")
        for event in ("mutual_dogfight_validation_started", "mutual_dogfight_validation_completed"):
            for invalid in (None, -1, True, "10"):
                with self.subTest(event=event, invalid=invalid):
                    rows = [json.loads(line) for line in original.splitlines()]
                    for row in rows:
                        if row.get("event") == event:
                            row["server_tick"] = invalid
                    self.primary.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
                    proc, result = self.verify()
                    self.assertNotEqual(proc.returncode, 0, result)
                    self.assertTrue(any("tick" in error for error in result["errors"]), result)

    def test_duplicate_start_or_reversed_boundaries_fail(self):
        original = self.primary.read_text(encoding="utf-8")
        with self.primary.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"aircraft_name": PRIMARY, "event": "mutual_dogfight_validation_started",
                                     "server_tick": 10}) + "\n")
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)
        self.assertTrue(any("start" in error for error in result["errors"]), result)
        self.primary.write_text(original, encoding="utf-8")
        self.set_completion(COMPLETION, server_tick=9)
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)
        self.assertTrue(any("completion" in error and "start" in error for error in result["errors"]), result)


if __name__ == "__main__":
    unittest.main()
