"""CLI regression tests for mutual-combat telemetry integrity."""
import json
import os
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
OTHER_ID = "33333333-3333-4333-8333-333333333333"


class MutualLogIntegrityTests(unittest.TestCase):
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
        self.other = self.logs / "other.jsonl"
        self.write_rows(self.primary, PRIMARY, [
            {"event": "mutual_dogfight_validation_started", "server_tick": 10,
             "reason": f"primary_uuid={PRIMARY_ID}:opponent_uuid={OPPONENT_ID}"},
            {"event": "control_adapter", "server_tick": 15, "applied_safety_override": "collision_avoidance",
             "reason": f"other_uuid={OPPONENT_ID}:current=9.0"},
            {"event": "mutual_dogfight_validation_status", "server_tick": 15, "reason": "separation=9.5"},
            {"event": "combat_target_acquired", "reason": "target_faction=blue:explicit_faction_hostile=true"},
            {"event": "air_combat_action_transition", "reason": "doctrine=turn_fighter:to=TURN"},
            {"event": "weapon_fire"},
            {"event": "frame", "server_tick": 15, "speed_bps": 30, "on_ground": False},
            {"event": "mutual_dogfight_validation_completed", "server_tick": 20,
             "reason": "minimum_separation=9.5:maximum_separation=40:primary_track_ticks=90:"
                       "opponent_track_ticks=90:primary_combat_ticks=110:opponent_combat_ticks=110"},
        ])
        self.write_rows(self.opponent, OPPONENT, [
            {"event": "control_adapter", "server_tick": 15, "applied_safety_override": "collision_avoidance",
             "reason": f"other_uuid={PRIMARY_ID}:current=9.0"},
            {"event": "combat_target_acquired", "reason": "target_faction=red:explicit_faction_hostile=true"},
            {"event": "air_combat_action_transition", "reason": "doctrine=energy_fighter:to=TURN"},
            {"event": "weapon_fire"},
            {"event": "frame", "server_tick": 15, "speed_bps": 30, "on_ground": False},
        ])
        self.write_rows(self.other, "unrelated aircraft", [{"event": "frame", "server_tick": 15}])

    @staticmethod
    def write_rows(path, name, rows):
        uid = PRIMARY_ID if name == PRIMARY else OPPONENT_ID if name == OPPONENT else OTHER_ID
        path.write_text("".join(json.dumps(dict(row, aircraft_name=name, aircraft_uuid=uid)) + "\n" for row in rows),
                        encoding="utf-8")

    def verify(self):
        output = self.root / "result.json"
        output.unlink(missing_ok=True)
        env = dict(os.environ, PYTHONINTMAXSTRDIGITS="4300")
        proc = subprocess.run([sys.executable, str(VERIFIER), "--root", str(self.root),
                               "--gradle-status", "0", "--output", str(output)],
                              text=True, capture_output=True, check=False, env=env)
        self.assertTrue(output.exists(), proc.stderr)
        return proc, json.loads(output.read_text(encoding="utf-8"))

    def test_normal_logs_and_unrelated_candidate_pass(self):
        proc, result = self.verify()
        self.assertEqual(proc.returncode, 0, result)
        self.assertTrue(result["passed"])
        self.assertIs(result["metrics"]["telemetry_scan_complete"], True)
        self.assertEqual(result["metrics"]["minimum_separation"], 9.5)

    def test_carriage_return_record_separator_remains_supported(self):
        paths = (self.primary, self.opponent, self.other)
        originals = {path: path.read_bytes() for path in paths}
        for separator in (b'\r', b'\r\n'):
            with self.subTest(separator=separator):
                for path in paths:
                    path.write_bytes(originals[path].replace(b'\n', separator))
                proc, result = self.verify()
                self.assertEqual(proc.returncode, 0, result)

    def test_malformed_unsafe_approach_cannot_disappear(self):
        proc, result = self.verify()
        self.assertEqual(proc.returncode, 0, result)
        with self.primary.open("ab") as stream:
            stream.write(b'{"event":"mutual_dogfight_validation_status","reason":"separation=7.4"\n')
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)
        self.assertFalse(result["passed"])
        self.assertTrue(any("primary.jsonl" in error and "invalid JSON" in error for error in result["errors"]), result)
        self.assertIs(result["metrics"]["telemetry_scan_complete"], False)
        for key in ("primary_min_speed_bps", "opponent_min_speed_bps", "primary_ground_frames",
                    "opponent_ground_frames", "collision_observed_minimum", "collision_observation_rows"):
            self.assertIsNone(result["metrics"][key], (key, result))

    def test_unreadable_aircraft_symlink_cannot_be_skipped(self):
        directory = self.root / "other-run"
        directory.mkdir()
        try:
            (directory / "aircraft").symlink_to(directory / "missing", target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlink unavailable: {exc}")
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)
        self.assertTrue(any("cannot scan telemetry directory" in error for error in result["errors"]), result)
        self.assertIsNone(result["metrics"]["primary_ground_frames"], result)
        self.assertIsNone(result["metrics"]["collision_observation_rows"], result)

    def test_corrupt_selected_and_unselected_candidates_fail(self):
        corruptions = {
            "invalid JSON": b'{"broken":\n',
            "invalid UTF-8": b'\xff\n',
            "non-object JSON": b'"literal"\n',
            "invalid JSON blank": b'\n',
            "DuplicateKeyError": b'{"aircraft_uuid":"first","aircraft_uuid":"second"}\n',
            "InvalidConstantError NaN": b'{"value":NaN}\n',
            "InvalidConstantError Infinity": b'{"value":Infinity}\n',
            "InvalidConstantError -Infinity": b'{"value":-Infinity}\n',
            "RecursionError": b'{"nested":' + b'[' * 10000 + b'0' + b']' * 10000 + b'}\n',
        }
        if hasattr(sys, "get_int_max_str_digits"):
            corruptions["ValueError"] = b'{"number":' + b'9' * 5000 + b'}\n'
        for path in (self.primary, self.opponent, self.other):
            original = path.read_bytes()
            for reason, broken in corruptions.items():
                with self.subTest(file=path.name, error=reason):
                    try:
                        path.write_bytes(original + broken)
                        proc, result = self.verify()
                        self.assertNotEqual(proc.returncode, 0, result)
                        expected = "invalid JSON" if reason == "invalid JSON blank" else reason
                        self.assertTrue(any(path.name in error and expected in error
                                            for error in result["errors"]), result)
                        self.assertIsNone(result["metrics"]["opponent_min_speed_bps"], result)
                        self.assertIsNone(result["metrics"]["collision_observed_minimum"], result)
                    finally:
                        path.write_bytes(original)

    def test_unreadable_candidate_fails(self):
        (self.logs / "unreadable.jsonl").mkdir()
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)
        self.assertTrue(any("cannot read telemetry log" in error and "unreadable.jsonl" in error
                            for error in result["errors"]), result)

    def test_json_float_overflow_fails_for_all_candidate_logs(self):
        for path in (self.primary, self.opponent, self.other):
            original = path.read_bytes()
            for value in (b"1e9999", b"-1e9999"):
                with self.subTest(file=path.name, value=value):
                    try:
                        path.write_bytes(original + b'{"speed_bps":' + value + b'}\n')
                        proc, result = self.verify()
                        self.assertNotEqual(proc.returncode, 0, result)
                        self.assertTrue(any(path.name in error and "NonFiniteNumberError" in error
                                            for error in result["errors"]), result)
                    finally:
                        path.write_bytes(original)

    def test_large_finite_json_numbers_remain_supported(self):
        with self.other.open("ab") as stream:
            stream.write(b'{"values":[1e308,-1e308,1e-200]}\n')
        proc, result = self.verify()
        self.assertEqual(proc.returncode, 0, result)

    def test_directory_scan_failure_fails_with_result_file(self):
        inaccessible = self.root / "unscannable"
        inaccessible.mkdir()
        output = self.root / "scan-result.json"
        program = '''
import importlib.util, os, sys
from unittest.mock import patch
spec=importlib.util.spec_from_file_location("verifier",sys.argv[1]); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
root=sys.argv[2]; denied=sys.argv[3]; output=sys.argv[4]; original=os.scandir
def scan(path):
    if os.fspath(path)==denied: raise PermissionError("synthetic scan failure")
    return original(path)
sys.argv=[sys.argv[1],"--root",root,"--gradle-status","0","--output",output]
with patch("os.scandir",scan): result=module.main()
raise SystemExit(result)
'''
        for denied in (inaccessible, self.logs):
            with self.subTest(denied=denied):
                output.unlink(missing_ok=True)
                proc = subprocess.run([sys.executable, "-c", program, str(VERIFIER), str(self.root),
                                       str(denied), str(output)], text=True, capture_output=True, check=False)
                self.assertTrue(output.exists(), proc.stderr)
                result = json.loads(output.read_text(encoding="utf-8"))
                self.assertNotEqual(proc.returncode, 0, result)
                self.assertTrue(any(str(denied) in error and "PermissionError" in error
                                    for error in result["errors"]), result)

    def test_symlink_traversal_matches_existing_scope(self):
        with tempfile.TemporaryDirectory() as outside:
            external = Path(outside)
            aircraft = external / "aircraft"
            aircraft.mkdir()
            (aircraft / "broken.jsonl").write_text('{"broken":\n', encoding="utf-8")
            alias = self.root / "alias"
            try:
                alias.symlink_to(external, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("directory symlinks are unavailable")
            proc, result = self.verify()
            self.assertEqual(proc.returncode, 0, result)
            holder = self.root / "holder"
            holder.mkdir()
            (holder / "aircraft").symlink_to(aircraft, target_is_directory=True)
            proc, result = self.verify()
            self.assertNotEqual(proc.returncode, 0, result)
            self.assertTrue(any("broken.jsonl" in error for error in result["errors"]), result)


if __name__ == "__main__":
    unittest.main()
