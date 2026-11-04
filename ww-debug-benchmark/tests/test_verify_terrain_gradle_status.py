"""Check that terrain evidence cannot override a failed GameTest process."""

import json
import copy
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


VERIFIER = Path(__file__).resolve().parents[1] / "tools" / "verify_terrain_scenario.py"


class TerrainGradleStatusTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "flight_profiles.json").write_text("{}\n", encoding="utf-8")
        aircraft = self.root / "aircraft"
        aircraft.mkdir()
        self.target_uuid = "11111111-1111-4111-8111-111111111111"
        self.other_uuid = "22222222-2222-4222-8222-222222222222"
        self.summary = self.root / "validation-summary-1.json"
        self.summary_data = {
            "state": "complete", "total": 1, "completed": 1,
            "results": [{"aircraft_uuid": self.target_uuid, "passed": True,
                         "final_phase": "PARKED", "reason": "completed_full_mission"}],
        }
        self.summary.write_text(json.dumps(self.summary_data), encoding="utf-8")
        self.log = aircraft / f"warfare_wings-a6m-{self.target_uuid}.jsonl"
        self.rows = [
            {"event": "frame", "position": {"x": 0, "y": 120, "z": 25},
             "home_position": {"x": 0, "y": 0, "z": 0},
             "runway_forward": {"x": 1, "z": 0}, "on_ground": False,
             "profile_stall_guard_speed_bps": 10},
            {"event": "terrain_avoidance_start"},
            {"event": "control_adapter", "applied_safety_override": "predictive_terrain_avoidance",
             "speed_bps": 20},
        ]
        for row in self.rows:
            row["aircraft_uuid"] = self.target_uuid
        self.write_rows()

    def write_rows(self):
        self.log.write_text("".join(json.dumps(row) + "\n" for row in self.rows), encoding="utf-8")

    def verify(self, gradle_status):
        output = self.root / "result.json"
        process = subprocess.run(
            [sys.executable, str(VERIFIER), "--root", str(self.root),
             "--gradle-status", str(gradle_status), "--output", str(output)],
            capture_output=True, text=True, check=False,
        )
        self.assertTrue(output.is_file(), process.stderr)
        return process.returncode, json.loads(output.read_text(encoding="utf-8"))

    def test_valid_telemetry_with_successful_gradle_passes(self):
        status, result = self.verify(0)
        self.assertEqual(status, 0, result)
        self.assertTrue(result["passed"], result)

    def test_valid_telemetry_cannot_override_failed_gradle(self):
        for gradle_status in (1, 42, -9):
            with self.subTest(gradle_status=gradle_status):
                status, result = self.verify(gradle_status)
                self.assertNotEqual(status, 0, result)
                self.assertFalse(result["passed"], result)
                self.assertTrue(any("GameTest" in error and str(gradle_status) in error
                                    for error in result["errors"]), result)

    def test_ground_contact_still_fails_with_successful_gradle(self):
        self.rows[0]["on_ground"] = True
        self.write_rows()
        status, result = self.verify(0)
        self.assertNotEqual(status, 0, result)
        self.assertTrue(any("ground" in error for error in result["errors"]), result)

    def test_every_frame_requires_explicit_boolean_on_ground(self):
        missing = object()
        for value in (missing, None, 0, 1, "", "false", [], {}):
            with self.subTest(value=value):
                # The first valid frame must not hide an invalid later frame.
                frame = copy.deepcopy(self.rows[0])
                if value is missing:
                    frame.pop("on_ground")
                else:
                    frame["on_ground"] = value
                self.rows.append(frame)
                self.write_rows()
                status, result = self.verify(0)
                self.rows.pop()
                self.assertNotEqual(status, 0, result)
                self.assertFalse(result["passed"], result)
                self.assertTrue(any("on_ground" in error for error in result["errors"]), result)

    def test_invalid_on_ground_does_not_hide_observed_contact(self):
        self.rows[0]["on_ground"] = None
        self.rows.append(dict(self.rows[0], on_ground=True))
        self.write_rows()
        status, result = self.verify(0)
        self.assertNotEqual(status, 0, result)
        self.assertTrue(any("on_ground" in error for error in result["errors"]), result)
        self.assertTrue(any("touched the ground" in error for error in result["errors"]), result)

    def test_incomplete_or_unsuccessful_summary_cannot_pass(self):
        missing = object()
        cases = {
            "state": ("running", "aborted", None, missing),
            "total": (0, 2, True, 1.0, "1", None, missing),
            "completed": (0, 2, True, 1.0, "1", None, missing),
            "passed": (False, 1, "true", None, missing),
            "final_phase": ("ABORTED", "BRAKE", None, missing),
        }
        for field, values in cases.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    summary = copy.deepcopy(self.summary_data)
                    owner = summary["results"][0] if field in ("passed", "final_phase") else summary
                    if value is missing:
                        owner.pop(field)
                    else:
                        owner[field] = value
                    self.summary.write_text(json.dumps(summary), encoding="utf-8")
                    status, result = self.verify(0)
                    self.assertNotEqual(status, 0, result)
                    self.assertFalse(result["passed"], result)
                    self.assertTrue(any(field in error for error in result["errors"]), result)

    def test_failed_summary_does_not_hide_observed_ground_contact(self):
        self.summary_data["results"][0]["passed"] = False
        self.summary.write_text(json.dumps(self.summary_data), encoding="utf-8")
        self.rows[0]["on_ground"] = True
        self.write_rows()
        status, result = self.verify(0)
        self.assertNotEqual(status, 0, result)
        self.assertTrue(any("passed" in error for error in result["errors"]), result)
        self.assertTrue(any("ground" in error for error in result["errors"]), result)

    def test_successful_summary_reason_is_not_a_fixed_string_requirement(self):
        self.summary_data["results"][0]["reason"] = "another_success_reason"
        self.summary.write_text(json.dumps(self.summary_data), encoding="utf-8")
        status, result = self.verify(0)
        self.assertEqual(status, 0, result)
        self.assertTrue(result["passed"], result)

    def test_crash_report_cannot_be_overridden_by_successful_gradle_and_telemetry(self):
        crashes = self.root / "crash-reports"
        crashes.mkdir()
        report = crashes / "crash-2026-11-04-server.txt"
        report.write_text("synthetic crash report\n", encoding="utf-8")
        status, result = self.verify(0)
        self.assertNotEqual(status, 0, result)
        self.assertFalse(result["passed"], result)
        self.assertIn(str(report), result["metrics"]["crash_reports"])
        self.assertTrue(any("crash" in error.lower() for error in result["errors"]), result)

    def test_crash_report_does_not_hide_observed_ground_contact(self):
        crashes = self.root / "crash-reports"
        crashes.mkdir()
        (crashes / "crash-report.txt").write_text("synthetic crash report\n", encoding="utf-8")
        self.rows[0]["on_ground"] = True
        self.write_rows()
        status, result = self.verify(0)
        self.assertNotEqual(status, 0, result)
        self.assertTrue(any("crash" in error.lower() for error in result["errors"]), result)
        self.assertTrue(any("ground" in error for error in result["errors"]), result)

    def test_newer_other_aircraft_cannot_hide_target_ground_contact(self):
        self.rows[0]["on_ground"] = True
        self.write_rows()
        other = self.log.with_name(f"warfare_wings-a6m-{self.other_uuid}.jsonl")
        other_rows = [dict(row, aircraft_uuid=self.other_uuid) for row in self.rows]
        other_rows[0]["on_ground"] = False
        other.write_text("".join(json.dumps(row) + "\n" for row in other_rows), encoding="utf-8")
        os.utime(self.log, (1000000000, 1000000000))
        os.utime(other, (1000000001, 1000000001))
        status, result = self.verify(0)
        self.assertNotEqual(status, 0, result)
        self.assertTrue(any("ground" in error for error in result["errors"]), result)

    def test_newer_other_aircraft_does_not_prevent_selecting_target(self):
        other = self.log.with_name(f"warfare_wings-a6m-{self.other_uuid}.jsonl")
        other_rows = [dict(row, aircraft_uuid=self.other_uuid) for row in self.rows]
        other_rows[0]["on_ground"] = True
        other.write_text("".join(json.dumps(row) + "\n" for row in other_rows), encoding="utf-8")
        os.utime(self.log, (1000000000, 1000000000))
        os.utime(other, (1000000001, 1000000001))
        status, result = self.verify(0)
        self.assertEqual(status, 0, result)
        self.assertEqual(result["metrics"]["telemetry_log"], str(self.log))

    def test_missing_target_log_cannot_fall_back_to_other_aircraft(self):
        self.log.rename(self.log.with_name(f"warfare_wings-a6m-{self.other_uuid}.jsonl"))
        status, result = self.verify(0)
        self.assertNotEqual(status, 0, result)

    def test_missing_or_multiple_summaries_fail(self):
        self.summary.unlink()
        status, result = self.verify(0)
        self.assertNotEqual(status, 0, result)
        self.summary.write_text(json.dumps(self.summary_data), encoding="utf-8")
        (self.root / "validation-summary-2.json").write_text(self.summary.read_text())
        status, result = self.verify(0)
        self.assertNotEqual(status, 0, result)

    def test_invalid_or_ambiguous_summary_identity_fails(self):
        for results in ([], [None], ["bad"], [[]], [{"aircraft_uuid": "invalid"}],
                        [{"aircraft_uuid": self.target_uuid}, {"aircraft_uuid": self.other_uuid}]):
            with self.subTest(results=results):
                self.summary.write_text(json.dumps({"results": results}), encoding="utf-8")
                status, result = self.verify(0)
                self.assertNotEqual(status, 0, result)

    def test_multiple_matching_logs_fail(self):
        second_dir = self.root / "other-run" / "aircraft"
        second_dir.mkdir(parents=True)
        (second_dir / self.log.name).write_text(self.log.read_text())
        status, result = self.verify(0)
        self.assertNotEqual(status, 0, result)

    def test_absent_or_conflicting_row_identity_fails(self):
        for identity in (None, self.other_uuid, "invalid"):
            with self.subTest(identity=identity):
                for row in self.rows:
                    if identity is None:
                        row.pop("aircraft_uuid", None)
                    else:
                        row["aircraft_uuid"] = identity
                self.write_rows()
                status, result = self.verify(0)
                self.assertNotEqual(status, 0, result)

    def test_one_conflicting_row_in_target_log_fails(self):
        self.rows[1]["aircraft_uuid"] = self.other_uuid
        self.write_rows()
        status, result = self.verify(0)
        self.assertNotEqual(status, 0, result)

    def test_invalid_jsonl_rows_fail_without_hiding_ground_or_speed(self):
        self.rows[0]["on_ground"] = True
        self.rows[2]["speed_bps"] = 1
        valid = [json.dumps(row).encode() + b"\n" for row in self.rows]
        for bad in (b'{"event":\n', b'\n', b'[]\n', b'42\n',
                    b'{"bad":NaN}\n', b'{"bad":"\xff"}\n',
                    b'{"bad":"\\ud800"}\n'):
            with self.subTest(bad=bad):
                self.log.write_bytes(valid[0] + bad + b''.join(valid[1:]))
                status, result = self.verify(0)
                self.assertNotEqual(status, 0, result)
                self.assertFalse(result["passed"], result)
                self.assertTrue(any("line 2" in e for e in result["errors"]), result)
                self.assertTrue(any("touched the ground" in e for e in result["errors"]), result)
                self.assertTrue(any("unsafe airspeed" in e for e in result["errors"]), result)
                self.assertFalse(result["metrics"]["selected_log_parse_and_identity_checks_passed"])
                self.assertNotIn("maximum_longitudinal_blocks", result["metrics"])

    def test_unpaired_unicode_does_not_hide_observed_ground_contact(self):
        frame = dict(self.rows[0], on_ground=True, annotation="\ud800")
        self.log.write_text(json.dumps(frame) + "\n" + self.log.read_text(), encoding="utf-8")
        status, result = self.verify(0)
        self.assertNotEqual(status, 0, result)
        self.assertTrue(any("line 1" in e and "ground" in e for e in result["errors"]), result)

    def test_nonstandard_constant_does_not_hide_observed_ground_contact(self):
        frame = dict(self.rows[0], on_ground=True, annotation=float("nan"))
        self.log.write_text(json.dumps(frame) + "\n" + self.log.read_text(), encoding="utf-8")
        status, result = self.verify(0)
        self.assertNotEqual(status, 0, result)
        self.assertTrue(any("line 1" in e and "ground" in e for e in result["errors"]), result)

    def test_unpaired_unicode_does_not_hide_observed_unsafe_speed(self):
        adapter = dict(self.rows[2], speed_bps=1, annotation="\ud800")
        self.log.write_text(self.log.read_text() + json.dumps(adapter) + "\n", encoding="utf-8")
        status, result = self.verify(0)
        self.assertNotEqual(status, 0, result)
        self.assertTrue(any("line 4" in e and "unsafe airspeed" in e for e in result["errors"]), result)

    def test_invalid_identity_or_summary_marks_metrics_incomplete(self):
        self.rows[1]["aircraft_uuid"] = self.other_uuid
        self.write_rows()
        status, result = self.verify(0)
        self.assertNotEqual(status, 0, result)
        self.assertFalse(result["metrics"]["selected_log_parse_and_identity_checks_passed"])
        self.rows[1]["aircraft_uuid"] = self.target_uuid
        self.write_rows()
        self.summary_data["state"] = "running"
        self.summary.write_text(json.dumps(self.summary_data), encoding="utf-8")
        status, result = self.verify(0)
        self.assertNotEqual(status, 0, result)
        self.assertFalse(result["metrics"]["selected_log_parse_and_identity_checks_passed"])

    @unittest.skipIf(os.name == "nt", "POSIX undecodable filenames")
    def test_undecodable_log_path_can_be_reported(self):
        target = self.log.with_name(os.fsdecode(b"\xff-" + os.fsencode(self.log.name)))
        self.log.rename(target)
        status, result = self.verify(0)
        self.assertEqual(status, 0, result)
        self.assertEqual(result["metrics"]["telemetry_log"], str(target))

    def test_valid_crlf_and_unterminated_last_object_are_accepted(self):
        self.log.write_bytes(b"\r\n".join(json.dumps(row).encode() for row in self.rows))
        status, result = self.verify(0)
        self.assertEqual(status, 0, result)

    def test_empty_log_is_incomplete(self):
        self.log.write_bytes(b"")
        status, result = self.verify(0)
        self.assertNotEqual(status, 0, result)
        self.assertFalse(result["metrics"]["selected_log_parse_and_identity_checks_passed"])

    def test_invalid_row_cannot_pass_otherwise_valid_evidence(self):
        for bad in (b'{"event":\n', b'[]\n', b'\n', b'{"bad":"\xff"}\n'):
            with self.subTest(bad=bad):
                self.write_rows()
                with self.log.open("ab") as out:
                    out.write(bad)
                status, result = self.verify(0)
                self.assertNotEqual(status, 0, result)
                self.assertFalse(result["passed"], result)
                self.assertFalse(result["metrics"]["selected_log_parse_and_identity_checks_passed"])

    def test_read_error_after_selection_keeps_observed_ground(self):
        spec = importlib.util.spec_from_file_location("terrain_verifier", VERIFIER)
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        self.rows[0]["on_ground"] = True
        first = json.dumps(self.rows[0]).encode() + b"\n"
        real_open = Path.open

        class InterruptedLog:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def __iter__(self):
                yield first
                raise OSError("synthetic read failure")

        def open_with_interruption(path, *args, **kwargs):
            if path == self.log and args and args[0] == "rb":
                return InterruptedLog()
            return real_open(path, *args, **kwargs)

        output = self.root / "io-result.json"
        argv = [str(VERIFIER), "--root", str(self.root), "--gradle-status", "0", "--output", str(output)]
        with mock.patch.object(Path, "open", open_with_interruption), mock.patch.object(sys, "argv", argv):
            status = verifier.main()
        result = json.loads(output.read_text())
        self.assertNotEqual(status, 0, result)
        self.assertTrue(any("could not read" in e for e in result["errors"]), result)
        self.assertTrue(any("touched the ground" in e for e in result["errors"]), result)
        self.assertFalse(result["metrics"]["selected_log_parse_and_identity_checks_passed"])


if __name__ == "__main__":
    unittest.main()
