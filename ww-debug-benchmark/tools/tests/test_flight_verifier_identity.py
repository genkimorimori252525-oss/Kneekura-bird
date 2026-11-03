"""Exercise full/landing verification with multiple real-shaped telemetry files."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid

VERIFIER = Path(__file__).resolve().parents[1] / "verify_flight_scenario.py"
TARGET = "a50055ec-8717-4c65-b5c0-1de53ad23da8"
OTHER = "208005b6-f2e3-440c-a3e3-e295c8525561"


class FlightVerifierIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.logs = self.root / "world/wwdebug/autopilot/run/aircraft"
        self.logs.mkdir(parents=True)
        (self.root / "flight_profiles.json").write_text("{}", encoding="utf-8")
        self.summary_path = self.root / "world/wwdebug/autopilot/validation-summary-1.json"
        self.summary([{"aircraft_uuid": TARGET, "passed": True}])

    def summary(self, results):
        self.summary_path.write_text(json.dumps({"state": "complete", "total": len(results),
                                                  "results": results}), encoding="utf-8")

    def log(self, name, uuids, mtime):
        path = self.logs / name
        path.write_text("".join(json.dumps({"event": "frame", "aircraft_uuid": uuid}) + "\n"
                                for uuid in uuids), encoding="utf-8")
        os.utime(path, (mtime, mtime))
        return path

    def verify(self, scenario="full", env=None):
        output = self.root / "result.json"
        proc = subprocess.run([sys.executable, str(VERIFIER), "--root", str(self.root),
                               "--scenario", scenario, "--gradle-status", "0", "--output", str(output)],
                              text=True, capture_output=True, check=False, env=env)
        self.assertTrue(output.is_file(), proc.stderr)
        return proc, json.loads(output.read_text(encoding="utf-8"))

    def test_summary_aircraft_selected_when_another_log_is_newer(self):
        target = self.log("target.jsonl", [TARGET], 1)
        self.log("unrelated.jsonl", [OTHER], 2)
        for scenario in ("full", "landing"):
            with self.subTest(scenario=scenario):
                proc, result = self.verify(scenario)
                self.assertEqual(proc.returncode, 0, result)
                self.assertEqual(result["metrics"]["telemetry_log"], str(target))

    def test_missing_target_fails_even_if_another_aircraft_has_frames(self):
        self.log("unrelated.jsonl", [OTHER], 2)
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)
        self.assertFalse(result["passed"])

    def test_duplicate_target_logs_are_ambiguous(self):
        self.log("one.jsonl", [TARGET], 1)
        self.log("two.jsonl", [TARGET], 2)
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)

    def test_mixed_identity_log_is_rejected(self):
        self.log("mixed.jsonl", [TARGET, OTHER], 2)
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)

    def test_missing_invalid_or_duplicate_summary_uuids_fail(self):
        self.log("target.jsonl", [TARGET], 1)
        self.log("invalid.jsonl", ["not-a-uuid"], 2)
        for results in ([{"passed": True}],
                        [{"aircraft_uuid": "not-a-uuid", "passed": True}],
                        [{"aircraft_uuid": TARGET, "passed": True},
                         {"aircraft_uuid": TARGET.upper(), "passed": True}]):
            with self.subTest(results=results):
                self.summary(results)
                proc, result = self.verify()
                self.assertNotEqual(proc.returncode, 0, result)

    def test_all_aircraft_summaries_select_each_corresponding_log(self):
        target = self.log("target.jsonl", [TARGET], 1)
        other = self.log("other.jsonl", [OTHER], 2)
        self.summary([{"aircraft_uuid": TARGET, "passed": True},
                      {"aircraft_uuid": OTHER, "passed": True}])
        for scenario in ("full", "landing"):
            with self.subTest(scenario=scenario):
                proc, result = self.verify(scenario)
                self.assertEqual(proc.returncode, 0, result)
                self.assertEqual(result["metrics"]["telemetry_logs"],
                                 {TARGET: str(target), OTHER: str(other)})
                self.assertEqual(result["metrics"]["frame_counts"], {TARGET: 1, OTHER: 1})

    def test_multi_aircraft_requires_a_log_and_frame_for_each(self):
        self.log("target.jsonl", [TARGET], 1)
        self.summary([{"aircraft_uuid": TARGET, "passed": True},
                      {"aircraft_uuid": OTHER, "passed": True}])
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)
        (self.logs / "other.jsonl").write_text(
            json.dumps({"event": "session_start", "aircraft_uuid": OTHER}) + "\n", encoding="utf-8")
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)

    def test_multi_aircraft_duplicate_and_mixed_logs_fail(self):
        self.summary([{"aircraft_uuid": TARGET, "passed": True},
                      {"aircraft_uuid": OTHER, "passed": True}])
        self.log("target.jsonl", [TARGET], 1)
        self.log("other.jsonl", [OTHER], 2)
        duplicate = self.log("duplicate.jsonl", [TARGET], 3)
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)
        duplicate.unlink()
        self.log("mixed.jsonl", [TARGET, OTHER], 3)
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)

    def test_malformed_summary_result_fails_with_result_file(self):
        self.summary([None])
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)

    def test_corrupt_target_or_unrelated_log_fails_with_result_file(self):
        target = self.log("target.jsonl", [TARGET], 1)
        unrelated = self.log("unrelated.jsonl", [OTHER], 2)
        corruptions = {"invalid_json": b'{"event":\n', "invalid_utf8": b'\xff\n',
                       "non_object": b'"not an object"\n', "blank_line": b'\n'}
        messages = {"invalid_json": "invalid JSON", "invalid_utf8": "invalid UTF-8",
                    "non_object": "non-object JSON", "blank_line": "invalid JSON"}
        for scenario in ("full", "landing"):
            for path, identity in ((target, TARGET), (unrelated, OTHER)):
                for kind, broken in corruptions.items():
                    with self.subTest(scenario=scenario, file=path.name, corruption=kind):
                        path.write_bytes((json.dumps({"event": "frame", "aircraft_uuid": identity})
                                          + "\n").encode("utf-8") + broken)
                        (self.root / "result.json").unlink(missing_ok=True)
                        proc, result = self.verify(scenario)
                        self.assertNotEqual(proc.returncode, 0, result)
                        self.assertFalse(result["passed"])
                        self.assertTrue(any(path.name in error and messages[kind] in error
                                            and "line 2" in error for error in result["errors"]), result)
                        self.log(path.name, [identity], 1 if path == target else 2)

    def test_unreadable_candidate_log_fails_with_result_file(self):
        self.log("target.jsonl", [TARGET], 1)
        (self.logs / "unreadable.jsonl").mkdir()
        proc, result = self.verify()
        self.assertNotEqual(proc.returncode, 0, result)
        self.assertTrue(any("cannot read telemetry log" in error and "unreadable.jsonl" in error
                            for error in result["errors"]), result)

    def test_json_parser_resource_limits_fail_with_result_file(self):
        target = self.log("target.jsonl", [TARGET], 1)
        unrelated = self.log("unrelated.jsonl", [OTHER], 2)
        corruptions = {
            "ValueError": b'{"number":' + b'9' * 5000 + b'}\n',
            "RecursionError": b'{"nested":' + b'[' * 10000 + b'0' + b']' * 10000 + b'}\n',
        }
        if not hasattr(sys, "get_int_max_str_digits"):
            del corruptions["ValueError"]
        child_env = dict(os.environ, PYTHONINTMAXSTRDIGITS="4300")
        for scenario in ("full", "landing"):
            for path, identity in ((target, TARGET), (unrelated, OTHER)):
                for reason, broken in corruptions.items():
                    with self.subTest(scenario=scenario, file=path.name, exception=reason):
                        try:
                            path.write_bytes((json.dumps({"event": "frame", "aircraft_uuid": identity})
                                              + "\n").encode("utf-8") + broken)
                            (self.root / "result.json").unlink(missing_ok=True)
                            proc, result = self.verify(scenario, env=child_env)
                            self.assertNotEqual(proc.returncode, 0, result)
                            self.assertTrue(any(path.name in error and reason in error and "line 2" in error
                                                for error in result["errors"]), result)
                        finally:
                            self.log(path.name, [identity], 1 if path == target else 2)

    def test_duplicate_json_keys_and_nonstandard_numbers_fail(self):
        target = self.log("target.jsonl", [TARGET], 1)
        unrelated = self.log("unrelated.jsonl", [OTHER], 2)
        corruptions = {
            "DuplicateKeyError": b'{"aircraft_uuid":"ignored","aircraft_uuid":"duplicate"}\n',
            "InvalidConstantError NaN": b'{"value":NaN}\n',
            "InvalidConstantError Infinity": b'{"value":Infinity}\n',
            "InvalidConstantError -Infinity": b'{"value":-Infinity}\n',
        }
        for scenario in ("full", "landing"):
            for path, identity in ((target, TARGET), (unrelated, OTHER)):
                for reason, broken in corruptions.items():
                    with self.subTest(scenario=scenario, file=path.name, error=reason):
                        try:
                            path.write_bytes((json.dumps({"event": "frame", "aircraft_uuid": identity})
                                             + "\n").encode("utf-8") + broken)
                            (self.root / "result.json").unlink(missing_ok=True)
                            proc, result = self.verify(scenario)
                            self.assertNotEqual(proc.returncode, 0, result)
                            self.assertTrue(any(path.name in error and reason in error and "line 2" in error
                                                for error in result["errors"]), result)
                        finally:
                            self.log(path.name, [identity], 1 if path == target else 2)

    def test_standard_json_with_same_key_in_distinct_objects_is_accepted(self):
        row = {"event": "frame", "aircraft_uuid": TARGET,
               "a": {"value": 1.2e-3}, "b": {"value": None}}
        (self.logs / "valid.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
        proc, result = self.verify()
        self.assertEqual(proc.returncode, 0, result)

    @unittest.skipUnless(sys.platform.startswith("linux"), "RSS delta uses Linux ru_maxrss units")
    def test_multi_aircraft_memory_does_not_scale_with_total_log_size(self):
        aircraft_ids = [str(uuid.UUID(int=index + 1)) for index in range(4)]
        self.summary([{"aircraft_uuid": value, "passed": True} for value in aircraft_ids])
        for index, value in enumerate(aircraft_ids):
            line = json.dumps({"event": "frame", "aircraft_uuid": value, "payload": "x" * 6000}) + "\n"
            with (self.logs / f"aircraft-{index}.jsonl").open("w", encoding="utf-8") as stream:
                for _ in range(2000):
                    stream.write(line)

        program = '''
import importlib.util, io, json, resource, sys
from contextlib import redirect_stdout
spec = importlib.util.spec_from_file_location("verifier", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
sys.argv = [sys.argv[1], "--root", sys.argv[2], "--scenario", "full", "--gradle-status", "0", "--output", sys.argv[3]]
before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
with redirect_stdout(io.StringIO()):
    code = module.main()
after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
print(json.dumps({"exit": code, "peak_growth_kib": after - before}))
'''
        proc = subprocess.run([sys.executable, "-c", program, str(VERIFIER), str(self.root),
                               str(self.root / "memory-result.json")], text=True,
                              capture_output=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        measured = json.loads(proc.stdout)
        self.assertEqual(measured["exit"], 0, measured)
        result = json.loads((self.root / "memory-result.json").read_text(encoding="utf-8"))
        self.assertEqual(result["metrics"]["frame_counts"], {value: 2000 for value in aircraft_ids})
        self.assertLess(measured["peak_growth_kib"], 30 * 1024, measured)

    def test_focused_turn_still_works_without_a_summary(self):
        self.summary_path.unlink()
        rows = [
            {"event": "phase_transition", "reason": "TURN_LEFT->CRUISE_CROSS:left_turn_heading_reached"},
            {"event": "phase_transition", "reason": "TURN_RIGHT->STALL_SETUP:right_turn_heading_reached"},
            {"event": "frame", "phase": "TURN_LEFT", "roll_deg": -9,
             "position": {"y": 100}, "on_ground": False},
            {"event": "frame", "phase": "TURN_RIGHT", "roll_deg": 9,
             "position": {"y": 100}, "on_ground": False},
        ]
        (self.logs / "turn.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows),
                                              encoding="utf-8")
        with (self.logs / "turn.jsonl").open("a", encoding="utf-8") as stream:
            stream.write('{"broken":\n')
        proc, result = self.verify("turn")
        self.assertEqual(proc.returncode, 0, result)


if __name__ == "__main__":
    unittest.main()
