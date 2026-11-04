import json
import math
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


VERIFIER = Path(__file__).resolve().parents[1] / "tools" / "verify_formation_scenario.py"
LEADER = "FORMATION_LEADER"
WING1 = "FORMATION_WINGMAN_1"
WING2 = "FORMATION_WINGMAN_2"
MISSING = object()


def fixture():
    logs = {}
    for name, initial, final in ((LEADER, 0, 0), (WING1, 10, 20), (WING2, -30, -30)):
        logs[name] = [
            {"aircraft_name": name, "event": "frame", "phase": "CRUISE_OUTBOUND",
             "server_tick": tick, "position": {"x": x, "y": 100, "z": 0},
             "on_ground": False, "speed_bps": 20, "profile_stall_guard_speed_bps": 10}
            for tick, x in ((0, initial), (60, final))
        ]
        if name != LEADER:
            logs[name].extend(
                {"aircraft_name": name, "event": "formation_slot_tracking",
                 "phase": "CRUISE_OUTBOUND", "server_tick": tick * 10,
                 "reason": "slot_error=20"}
                for tick in range(6)
            )
    logs[LEADER].extend(
        {"aircraft_name": LEADER, "event": event, "phase": "CRUISE_OUTBOUND", "server_tick": tick}
        for event, tick in (("collision_avoidance_start", 0), ("collision_avoidance_clear", 60))
    )
    return logs


def verify(logs, reverse_scan=None, raw_files=None, unreadable=None):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        aircraft = root / "aircraft"
        aircraft.mkdir()
        for name, rows in logs.items():
            (aircraft / f"{name}.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        for name, data in (raw_files or {}).items():
            (aircraft / f"{name}.jsonl").write_bytes(data)
        if unreadable:
            # Opening a discovered directory as a file fails without symlink privileges.
            (aircraft / f"{unreadable}.jsonl").mkdir()
        output = root / "result.json"
        if reverse_scan is None:
            command = [sys.executable, str(VERIFIER)]
        else:
            # Exercise real files in both explicit discovery orders.
            ordered_runner = """
import pathlib, runpy, sys
original = pathlib.Path.rglob
reverse = sys.argv.pop(1) == 'reverse'
script = sys.argv.pop(1)
pathlib.Path.rglob = lambda self, pattern: iter(sorted(original(self, pattern), reverse=reverse))
sys.argv[0] = script
runpy.run_path(script, run_name='__main__')
"""
            command = [sys.executable, "-c", ordered_runner,
                       "reverse" if reverse_scan else "forward", str(VERIFIER)]
        process = subprocess.run(
            command + ["--root", str(root), "--gradle-status", "0", "--output", str(output)],
            capture_output=True, text=True, check=False)
        if not output.exists():
            raise AssertionError(f"verifier did not write a result: {process.stderr}")
        try:
            result = json.loads(output.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise AssertionError(f"verifier wrote an invalid result: {process.stderr}") from exc
        return process.returncode, result


def set_field(frame, field, value):
    if value is MISSING:
        frame.pop(field)
    else:
        frame[field] = value


class FormationSafetyTest(unittest.TestCase):
    def assert_verdict(self, logs, passed):
        status, result = verify(logs)
        self.assertEqual(status, 0 if passed else 1, result)
        self.assertEqual(result["passed"], passed, result)
        return result

    def test_complete_safe_samples_pass(self):
        result = self.assert_verdict(fixture(), True)
        self.assertEqual(result["metrics"]["unsafe_ground_frames"], [])
        self.assertEqual(result["metrics"]["formation_speed"][LEADER],
                         {"minimum_formation_speed_bps": 20, "stall_guard_speed_bps": 10})

    def test_malformed_aircraft_jsonl_fails_with_path_and_line(self):
        for invalid in (b'\xff', b'', b'{"bad":', b'[]', b'null', b'{"bad": NaN}'):
            with self.subTest(invalid=invalid):
                logs = fixture()
                rows = [json.dumps(row).encode() for row in logs[LEADER]]
                raw = b'\n'.join([rows[0], invalid, *rows[1:]]) + b'\n'
                status, result = verify(logs, raw_files={LEADER: raw})
                self.assertEqual(status, 1, result)
                self.assertFalse(result["passed"], result)
                self.assertTrue(any("FORMATION_LEADER.jsonl" in e and "line 2" in e
                                    for e in result["errors"]), result)
                self.assertIs(result["metrics"].get("formation_assessment_complete"), False)
                self.assertNotIn("formation_aircraft", result["metrics"])
                self.assertIn(LEADER, result["metrics"]["observed_formation_aircraft"])
                self.assertNotIn("minimum_pairwise_distance_blocks", result["metrics"])
                self.assertNotIn("formation_speed", result["metrics"])

    def test_unpaired_surrogates_are_rejected_with_valid_rows_retained(self):
        for invalid in (b'{"aircraft_name":"FORMATION_\\ud800"}',
                        b'{"nested":{"\\udfff":1}}',
                        b'{"nested":[{"value":"\\ud800"}]}'):
            with self.subTest(invalid=invalid):
                logs = fixture()
                logs[LEADER][0]["on_ground"] = True
                logs[LEADER][1]["speed_bps"] = 1
                rows = [json.dumps(row).encode() for row in logs[LEADER]]
                raw = b'\n'.join([rows[0], invalid, *rows[1:]]) + b'\n'
                status, result = verify(logs, raw_files={LEADER: raw})
                self.assertEqual(status, 1, result)
                self.assertTrue(any("line 2" in e and "Unicode" in e for e in result["errors"]), result)
                self.assertTrue(any("touched ground" in e for e in result["errors"]), result)
                self.assertTrue(any("lost unsafe formation airspeed" in e for e in result["errors"]), result)
                self.assertIs(result["metrics"]["formation_assessment_complete"], False)

    def test_unicode_invalid_frame_still_reports_its_ground_and_speed_violations(self):
        for invalid_name in (False, True):
            with self.subTest(invalid_name=invalid_name):
                logs = fixture()
                frame = dict(logs[LEADER][0], on_ground=True, speed_bps=1,
                             metadata={"unrelated": "\ud800"})
                if invalid_name:
                    frame["aircraft_name"] = "FORMATION_\ud800"
                rows = [json.dumps(row).encode() for row in logs[LEADER]]
                raw = b'\n'.join([rows[0], json.dumps(frame).encode(), *rows[1:]]) + b'\n'
                status, result = verify(logs, raw_files={LEADER: raw})
                self.assertEqual(status, 1, result)
                self.assertTrue(any("line 2" in e and "Unicode" in e for e in result["errors"]), result)
                self.assertTrue(any("FORMATION_LEADER.jsonl" in e and "touched ground" in e
                                    for e in result["errors"]), result)
                self.assertTrue(any("FORMATION_LEADER.jsonl" in e and "lost unsafe formation airspeed" in e
                                    for e in result["errors"]), result)
                self.assertTrue(any("identity unverified" in e for e in result["errors"]), result)
                self.assertTrue(any("excluded from pairwise distance" in e for e in result["errors"]), result)
                self.assertIs(result["metrics"]["formation_assessment_complete"], False)
                self.assertNotIn("formation_speed", result["metrics"])

    def test_unicode_invalid_frame_with_huge_tick_retains_known_violations(self):
        logs = fixture()
        frame = dict(logs[LEADER][0], server_tick=10 ** 400, on_ground=True, speed_bps=1,
                     metadata={"unrelated": "\ud800"})
        rows = [json.dumps(row).encode() for row in logs[LEADER]]
        raw = b'\n'.join([rows[0], json.dumps(frame).encode(), *rows[1:]]) + b'\n'
        status, result = verify(logs, raw_files={LEADER: raw})
        self.assertEqual(status, 1, result)
        self.assertTrue(any("line 2" in e and "Unicode" in e for e in result["errors"]), result)
        self.assertTrue(any("touched ground" in e for e in result["errors"]), result)
        self.assertTrue(any("lost unsafe formation airspeed" in e for e in result["errors"]), result)

    def test_escaped_surrogate_pair_is_accepted(self):
        logs = fixture()
        rows = [json.dumps(row).encode() for row in logs[LEADER]]
        raw = b'\n'.join([rows[0], b'{"nested":{"\\ud83d\\ude80":"\\ud83d\\ude80"}}', *rows[1:]]) + b'\n'
        status, result = verify(logs, raw_files={LEADER: raw})
        self.assertEqual(status, 0, result)
        self.assertTrue(result["passed"], result)

    def test_valid_unicode_aircraft_name_is_preserved(self):
        logs = fixture()
        for row in logs[LEADER]:
            row["aircraft_name"] = "FORMATION_LEADER_飛行"
        status, result = verify(logs)
        self.assertEqual(status, 0, result)
        self.assertIn("FORMATION_LEADER_飛行", result["metrics"]["formation_aircraft"])

    def test_invalid_unicode_in_first_aircraft_name_still_writes_result(self):
        logs = fixture()
        raw = b'{"aircraft_name":"FORMATION_\\ud800"}\n' + b''.join(
            json.dumps(row).encode() + b'\n' for row in logs[LEADER])
        status, result = verify(logs, raw_files={LEADER: raw})
        self.assertEqual(status, 1, result)
        self.assertTrue(any("line 1" in e and "Unicode" in e for e in result["errors"]), result)

    @unittest.skipUnless(os.name == "posix", "surrogateescape file names require POSIX")
    def test_invalid_bytes_in_file_name_do_not_break_json_result(self):
        name = os.fsdecode(b'unknown-\xff')
        status, result = verify(fixture(), raw_files={name: b'{broken'})
        self.assertEqual(status, 1, result)
        display_name = name.encode("utf-8", "backslashreplace").decode("utf-8")
        self.assertTrue(any(display_name in e and "invalid JSON" in e
                            for e in result["errors"]), result)
        json.dumps(result, ensure_ascii=False).encode("utf-8")

    def test_bad_unknown_and_unreadable_aircraft_files_also_fail(self):
        for files in ({"raw_files": {"UNKNOWN": b'{broken'}},
                      {"raw_files": {"EMPTY": b''}}, {"unreadable": "UNREADABLE"}):
            with self.subTest(files=files):
                status, result = verify(fixture(), **files)
                self.assertEqual(status, 1, result)
                self.assertFalse(result["passed"], result)
                name = next(iter(files.get("raw_files", {})), files.get("unreadable"))
                self.assertTrue(any(f"{name}.jsonl" in error for error in result["errors"]), result)

    def test_invalid_line_keeps_known_safety_violations_on_both_sides(self):
        for invalid in (b'{broken', b'\xff', b'', b'[]'):
            with self.subTest(invalid=invalid):
                logs = fixture()
                logs[LEADER][0]["on_ground"] = True
                logs[LEADER][1]["speed_bps"] = 1
                logs[WING1][0]["position"]["x"] = 0.5
                rows = [json.dumps(row).encode() for row in logs[LEADER]]
                raw = b'\n'.join([rows[0], invalid, *rows[1:]]) + b'\n'
                status, result = verify(logs, raw_files={LEADER: raw})
                self.assertEqual(status, 1, result)
                self.assertTrue(any("touched ground" in e for e in result["errors"]), result)
                self.assertTrue(any("lost unsafe formation airspeed" in e for e in result["errors"]), result)
                self.assertTrue(any("collision distance" in e for e in result["errors"]), result)
                self.assertNotIn("formation_convergence", result["metrics"])

    def test_incomplete_data_does_not_claim_unobserved_events_never_occurred(self):
        logs = fixture()
        logs[LEADER] = [row for row in logs[LEADER] if row["event"] == "frame"]
        raw = b'\n'.join(json.dumps(row).encode() for row in logs[LEADER]) + b'\n{bad\n'
        status, result = verify(logs, raw_files={LEADER: raw})
        self.assertEqual(status, 1, result)
        self.assertTrue(any("invalid JSON" in e for e in result["errors"]), result)
        self.assertFalse(any("never activated" in e or "never cleared" in e
                             for e in result["errors"]), result)

    def test_incomplete_logs_still_report_observed_nonconvergence(self):
        logs = fixture()
        for row in logs[WING1]:
            if row["event"] == "formation_slot_tracking":
                row["reason"] = "slot_error=100"
        status, result = verify(logs, raw_files={"UNKNOWN": b'{broken'})
        self.assertEqual(status, 1, result)
        self.assertTrue(any(WING1 in e and "observed" in e and "convergence" in e
                            for e in result["errors"]), result)
        self.assertNotIn("formation_convergence", result["metrics"])

    def test_malformed_json_and_duplicate_names_report_both_issues(self):
        logs = fixture()
        duplicate = fixture()[LEADER]
        duplicate[0]["on_ground"] = True
        logs["ZZZ_DUPLICATE"] = duplicate
        status, result = verify(logs, raw_files={"UNKNOWN": b'{broken'})
        self.assertEqual(status, 1, result)
        self.assertTrue(any("duplicate formation aircraft name" in e for e in result["errors"]), result)
        self.assertTrue(any("UNKNOWN.jsonl" in e and "invalid JSON" in e for e in result["errors"]), result)
        self.assertTrue(any("ZZZ_DUPLICATE.jsonl" in e and "touched ground" in e
                            for e in result["errors"]), result)
        self.assertIs(result["metrics"]["formation_assessment_complete"], False)
        self.assertNotIn("formation_aircraft", result["metrics"])
        self.assertIn(LEADER, result["metrics"]["observed_formation_aircraft"])

    def test_lf_crlf_and_complete_last_line_without_newline_are_accepted(self):
        for newline, trailing in ((b'\n', True), (b'\r\n', True), (b'\n', False), (b'\r\n', False)):
            with self.subTest(newline=newline, trailing=trailing):
                logs = fixture()
                raw = newline.join(json.dumps(row).encode() for row in logs[LEADER])
                status, result = verify(logs, raw_files={LEADER: raw + (newline if trailing else b'')})
                self.assertEqual(status, 0, result)
                self.assertTrue(result["passed"], result)

    def test_distinct_names_pass_in_both_scan_orders(self):
        for reverse_scan in (False, True):
            with self.subTest(reverse_scan=reverse_scan):
                status, result = verify(fixture(), reverse_scan=reverse_scan)
                self.assertEqual(status, 0, result)
                self.assertTrue(result["passed"], result)

    def test_duplicate_aircraft_names_fail_without_complete_safety_metrics_in_both_scan_orders(self):
        for reverse_scan in (False, True):
            with self.subTest(reverse_scan=reverse_scan):
                logs = fixture()
                duplicate = fixture()[LEADER]
                duplicate[0]["on_ground"] = True
                logs["ZZZ_DUPLICATE"] = duplicate
                status, result = verify(logs, reverse_scan=reverse_scan)
                self.assertEqual(status, 1, result)
                self.assertFalse(result["passed"], result)
                self.assertTrue(any("duplicate" in error.lower() and LEADER in error
                                    for error in result["errors"]), result)
                paths = result["metrics"]["duplicate_formation_logs"][LEADER]
                self.assertEqual({Path(path).name for path in paths},
                                 {"FORMATION_LEADER.jsonl", "ZZZ_DUPLICATE.jsonl"})
                self.assertNotIn("formation_speed", result["metrics"])
                self.assertNotIn("unsafe_ground_frames", result["metrics"])

    def test_duplicate_logs_report_observed_safety_violations_by_file_in_both_orders(self):
        for reverse_scan in (False, True):
            with self.subTest(reverse_scan=reverse_scan):
                logs = fixture()
                logs[LEADER][0]["speed_bps"] = 1
                logs[LEADER][1]["on_ground"] = None
                duplicate = fixture()[LEADER]
                duplicate[0]["on_ground"] = True
                logs["ZZZ_DUPLICATE"] = duplicate
                status, result = verify(logs, reverse_scan=reverse_scan)
                self.assertEqual(status, 1, result)
                self.assertFalse(result["passed"], result)
                errors = result["errors"]
                self.assertTrue(any("FORMATION_LEADER.jsonl" in e and
                                    "lost unsafe formation airspeed" in e for e in errors), result)
                self.assertTrue(any("FORMATION_LEADER.jsonl" in e and
                                    "invalid or missing on_ground" in e for e in errors), result)
                self.assertTrue(any("ZZZ_DUPLICATE.jsonl" in e and
                                    "touched ground" in e for e in errors), result)
                self.assertIs(result["metrics"].get("formation_assessment_complete"), False)
                self.assertNotIn("minimum_pairwise_distance_blocks", result["metrics"])
                self.assertNotIn("formation_convergence", result["metrics"])

    def test_duplicate_names_still_report_duplicate_ticks_and_known_frame_violations(self):
        for reverse_scan in (False, True):
            with self.subTest(reverse_scan=reverse_scan):
                logs = fixture()
                unsafe = dict(logs[LEADER][0], on_ground=True, speed_bps=1)
                logs[LEADER].insert(0, unsafe)
                logs["ZZZ_DUPLICATE"] = fixture()[LEADER]
                status, result = verify(logs, reverse_scan=reverse_scan)
                self.assertEqual(status, 1, result)
                errors = result["errors"]
                self.assertTrue(any("duplicate formation aircraft name" in e for e in errors), result)
                self.assertTrue(any("FORMATION_LEADER.jsonl" in e and
                                    "duplicate formation frame ticks" in e for e in errors), result)
                self.assertTrue(any("FORMATION_LEADER.jsonl" in e and
                                    "lost unsafe formation airspeed" in e for e in errors), result)
                self.assertTrue(any("FORMATION_LEADER.jsonl" in e and
                                    "touched ground" in e for e in errors), result)
                self.assertIs(result["metrics"].get("formation_assessment_complete"), False)

    def test_every_ground_sample_must_be_a_boolean(self):
        for value in (MISSING, None, 0, 1, "false", [], {}):
            with self.subTest(value=value):
                logs = fixture()
                set_field(logs[LEADER][0], "on_ground", value)
                result = self.assert_verdict(logs, False)
                self.assertTrue(any("on_ground" in error and LEADER in error
                                    for error in result["errors"]), result)

    def test_every_speed_and_guard_sample_must_be_a_finite_json_number(self):
        for field in ("speed_bps", "profile_stall_guard_speed_bps"):
            for value in (MISSING, None, True, False, "10", [], {}, math.nan, math.inf, -math.inf):
                with self.subTest(field=field, value=value):
                    logs = fixture()
                    set_field(logs[LEADER][0], field, value)
                    result = self.assert_verdict(logs, False)
                    if isinstance(value, float) and not math.isfinite(value):
                        # Python serializes these as non-standard JSON constants.
                        self.assertTrue(any("invalid JSON" in error and LEADER in error
                                            for error in result["errors"]), result)
                        self.assertIs(result["metrics"]["formation_assessment_complete"], False)
                    else:
                        self.assertTrue(any(field in error and LEADER in error
                                            for error in result["errors"]), result)
                        self.assertIsNone(result["metrics"]["formation_speed"][LEADER])

    def test_json_number_outside_float_range_remains_a_field_error(self):
        for field in ("speed_bps", "profile_stall_guard_speed_bps"):
            with self.subTest(field=field):
                logs = fixture()
                logs[LEADER][0][field] = 123456
                raw = ''.join(json.dumps(row) + '\n' for row in logs[LEADER]).encode()
                raw = raw.replace(b'123456', b'1e400', 1)
                status, result = verify(logs, raw_files={LEADER: raw})
                self.assertEqual(status, 1, result)
                self.assertTrue(any(field in e and "invalid or missing" in e
                                    for e in result["errors"]), result)
                self.assertIsNone(result["metrics"]["formation_speed"][LEADER])

    def test_nonpositive_guard_is_not_evaluable(self):
        for guard in (0, -1):
            with self.subTest(guard=guard):
                logs = fixture()
                logs[LEADER][0]["profile_stall_guard_speed_bps"] = guard
                result = self.assert_verdict(logs, False)
                self.assertIsNone(result["metrics"]["formation_speed"][LEADER])

    def test_valid_unsafe_samples_are_reported_alongside_malformed_samples(self):
        logs = fixture()
        logs[LEADER][0]["on_ground"] = None
        logs[LEADER][0]["speed_bps"] = "invalid"
        logs[LEADER][1]["on_ground"] = True
        logs[LEADER][1]["speed_bps"] = -1
        result = self.assert_verdict(logs, False)
        self.assertIn([LEADER, 60], result["metrics"]["unsafe_ground_frames"])
        self.assertTrue(any("lost unsafe formation airspeed" in error and LEADER in error
                            for error in result["errors"]), result)
        self.assertIsNone(result["metrics"]["formation_speed"][LEADER])

    def test_each_speed_uses_its_own_positive_guard_at_90_percent(self):
        logs = fixture()
        logs[LEADER][0].update(speed_bps=9, profile_stall_guard_speed_bps=10)
        logs[LEADER][1].update(speed_bps=18, profile_stall_guard_speed_bps=20)
        result = self.assert_verdict(logs, True)
        self.assertEqual(result["metrics"]["formation_speed"][LEADER], {
            "minimum_formation_speed_bps": 9,
            "stall_guard_speed_bps": None,
            "worst_speed_bps": 9,
            "worst_stall_guard_speed_bps": 10,
            "worst_speed_to_guard_ratio": 0.9,
        })
        logs[LEADER][1]["speed_bps"] = 17.9
        result = self.assert_verdict(logs, False)
        self.assertTrue(any("lost unsafe formation airspeed" in error and LEADER in error
                            for error in result["errors"]), result)
        self.assertEqual(result["metrics"]["formation_speed"][LEADER]["worst_speed_bps"], 17.9)
        self.assertEqual(result["metrics"]["formation_speed"][LEADER]["worst_stall_guard_speed_bps"], 20)
        self.assertAlmostEqual(result["metrics"]["formation_speed"][LEADER]["worst_speed_to_guard_ratio"], 0.895)
        logs[LEADER][0].update(speed_bps=18, profile_stall_guard_speed_bps=20)
        logs[LEADER][1].update(speed_bps=9, profile_stall_guard_speed_bps=10)
        self.assert_verdict(logs, True)

    def test_worst_ratio_orders_near_equal_ratios_without_rounding(self):
        logs = fixture()
        next_one = math.nextafter(1.0, math.inf)
        next_two = math.nextafter(next_one, math.inf)
        logs[LEADER][0].update(speed_bps=next_one, profile_stall_guard_speed_bps=next_two)
        logs[LEADER][1].update(speed_bps=1.0, profile_stall_guard_speed_bps=next_one)
        result = self.assert_verdict(logs, True)
        metrics = result["metrics"]["formation_speed"][LEADER]
        # 1/next_one is strictly smaller than next_one/next_two.
        self.assertEqual(metrics["worst_speed_bps"], 1.0)
        self.assertEqual(metrics["worst_stall_guard_speed_bps"], next_one)

    def test_nonzero_ratio_that_underflows_is_not_reported_as_zero(self):
        logs = fixture()
        logs[LEADER][0].update(speed_bps=math.ulp(0.0), profile_stall_guard_speed_bps=1e308)
        result = self.assert_verdict(logs, False)
        metrics = result["metrics"]["formation_speed"][LEADER]
        self.assertEqual(metrics["worst_speed_bps"], math.ulp(0.0))
        self.assertEqual(metrics["worst_stall_guard_speed_bps"], 1e308)
        self.assertIsNone(metrics["worst_speed_to_guard_ratio"])

    def test_duplicate_frame_tick_fails_and_retains_observed_collision_in_either_order(self):
        for collision_first in (True, False):
            with self.subTest(collision_first=collision_first):
                logs = fixture()
                safe = logs[WING1][0]
                collision = dict(safe, position={"x": 0.5, "y": 100, "z": 0})
                logs[WING1][0:1] = [collision, safe] if collision_first else [safe, collision]
                result = self.assert_verdict(logs, False)
                self.assertTrue(any(WING1 in error and "duplicate" in error.lower()
                                    and "0" in error for error in result["errors"]), result)
                self.assertTrue(any("collision distance" in error for error in result["errors"]), result)
                self.assertEqual(result["metrics"]["minimum_pairwise_distance_blocks"], 0.5)

    def test_excessive_duplicate_pairs_fail_with_incomplete_distance_metrics(self):
        logs = fixture()
        logs[WING1][0]["position"]["x"] = 0.5
        for name in (LEADER, WING1):
            frame = logs[name][0]
            logs[name][0:1] = [dict(frame) for _ in range(65)]
        result = self.assert_verdict(logs, False)
        self.assertTrue(any("pair" in error.lower() and "limit" in error.lower()
                            for error in result["errors"]), result)
        self.assertTrue(any("collision distance" in error for error in result["errors"]), result)
        metrics = result["metrics"]
        self.assertIsNone(metrics["minimum_pairwise_distance_blocks"])
        self.assertEqual(metrics["minimum_evaluated_pairwise_distance_blocks"], 0.5)
        self.assertIsNone(metrics["pairwise_separation"][f"{LEADER} <> {WING1}"])
        self.assertIsNone(metrics["recovered_dangerous_pairs"])

    def test_unexamined_position_cannot_produce_complete_safety_metrics(self):
        logs = fixture()
        leader = logs[LEADER][0]
        wing = logs[WING1][0]
        far = dict(leader, position={"x": 100, "y": 100, "z": 0})
        close = dict(wing, position={"x": 0.5, "y": 100, "z": 0})
        logs[LEADER][0:1] = [dict(far) for _ in range(64)] + [leader]
        logs[WING1][0:1] = [dict(close) for _ in range(65)]
        result = self.assert_verdict(logs, False)
        metrics = result["metrics"]
        self.assertTrue(any("pair" in error.lower() and "limit" in error.lower()
                            for error in result["errors"]), result)
        self.assertIsNone(metrics["minimum_pairwise_distance_blocks"])
        self.assertGreaterEqual(metrics["minimum_evaluated_pairwise_distance_blocks"], 2)
        self.assertIsNone(metrics["pairwise_separation"][f"{LEADER} <> {WING1}"])
        self.assertIsNone(metrics["recovered_dangerous_pairs"])

    def test_duplicate_pairs_at_evaluation_limit_still_report_complete_minimum(self):
        logs = fixture()
        logs[WING1][0]["position"]["x"] = 0.5
        for name in (LEADER, WING1):
            frame = logs[name][0]
            logs[name][0:1] = [dict(frame) for _ in range(64)]
        result = self.assert_verdict(logs, False)
        self.assertFalse(any("pair" in error.lower() and "limit" in error.lower()
                             for error in result["errors"]), result)
        self.assertEqual(result["metrics"]["minimum_pairwise_distance_blocks"], 0.5)
        self.assertTrue(any("collision distance" in error for error in result["errors"]), result)

    def test_duplicate_tick_keeps_ground_and_airspeed_violations(self):
        logs = fixture()
        unsafe = dict(logs[WING1][0], on_ground=True, speed_bps=1)
        logs[WING1].insert(0, unsafe)
        result = self.assert_verdict(logs, False)
        self.assertTrue(any(WING1 in error and "duplicate" in error.lower()
                            for error in result["errors"]), result)
        self.assertIn([WING1, 0], result["metrics"]["unsafe_ground_frames"])
        self.assertTrue(any(WING1 in error and "lost unsafe formation airspeed" in error
                            for error in result["errors"]), result)

    def test_duplicate_tick_is_rejected_even_if_one_frame_has_no_position(self):
        logs = fixture()
        duplicate = dict(logs[WING1][0])
        duplicate.pop("position")
        logs[WING1].append(duplicate)
        result = self.assert_verdict(logs, False)
        self.assertTrue(any(WING1 in error and "duplicate" in error.lower()
                            for error in result["errors"]), result)

    def test_duplicate_tick_in_another_phase_is_not_a_formation_duplicate(self):
        logs = fixture()
        logs[WING1].append(dict(logs[WING1][0], phase="RETURN"))
        self.assert_verdict(logs, True)

    def test_each_selected_aircraft_needs_a_formation_frame(self):
        logs = fixture()
        logs[WING2] = [row for row in logs[WING2] if row["event"] != "frame"]
        result = self.assert_verdict(logs, False)
        self.assertTrue(any(WING2 in error and "frame" in error.lower() for error in result["errors"]), result)
        self.assertIsNone(result["metrics"]["formation_speed"][WING2])


if __name__ == "__main__":
    unittest.main()
