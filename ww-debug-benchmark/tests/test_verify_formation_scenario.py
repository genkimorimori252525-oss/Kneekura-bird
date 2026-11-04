import json
import math
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


def verify(logs):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        aircraft = root / "aircraft"
        aircraft.mkdir()
        for name, rows in logs.items():
            (aircraft / f"{name}.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        output = root / "result.json"
        process = subprocess.run(
            [sys.executable, str(VERIFIER), "--root", str(root), "--gradle-status", "0",
             "--output", str(output)], capture_output=True, text=True, check=False)
        result = json.loads(output.read_text(encoding="utf-8"))
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
                    self.assertTrue(any(field in error and LEADER in error
                                        for error in result["errors"]), result)
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

    def test_each_selected_aircraft_needs_a_formation_frame(self):
        logs = fixture()
        logs[WING2] = [row for row in logs[WING2] if row["event"] != "frame"]
        result = self.assert_verdict(logs, False)
        self.assertTrue(any(WING2 in error and "frame" in error.lower() for error in result["errors"]), result)
        self.assertIsNone(result["metrics"]["formation_speed"][WING2])


if __name__ == "__main__":
    unittest.main()
