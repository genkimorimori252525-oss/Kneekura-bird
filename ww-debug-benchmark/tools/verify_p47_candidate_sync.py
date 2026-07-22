#!/usr/bin/env python3
"""Verify the selected P-47N replay candidate matches production constants.

This check also pins the existing attack and safety thresholds so an experimental
candidate cannot silently qualify by weakening real firing or maneuver safeguards.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = Path(__file__).with_name("p47_coupled_climb_candidate.json")
JAVA = ROOT / "src/main/java/com/wwdebug/autopilot/EnergyFighterApexYawAdapter.java"

CANDIDATE_CONSTANTS = {
    "climb_pitch": "CLIMB_TARGET_PITCH_DEG",
    "yaw_trigger_pitch": "YAW_TRIGGER_PITCH_DEG",
    "pivot_complete_heading": "PIVOT_COMPLETE_HEADING_DEG",
    "pivot_divisor": "PIVOT_INPUT_DIVISOR",
    "capture_pitch_divisor": "CAPTURE_PITCH_DIVISOR",
    "capture_pitch_damping": "CAPTURE_PITCH_RATE_DAMPING",
    "yaw_damping": "YAW_RATE_DAMPING",
    "lead_ticks": "LEAD_TICKS",
    "crossing_entry_min_horizontal_angle": "CROSSING_ENTRY_MIN_HORIZONTAL_ANGLE_DEG",
    "crossing_entry_max_horizontal_angle": "CROSSING_ENTRY_MAX_HORIZONTAL_ANGLE_DEG",
    "crossing_entry_min_closure": "CROSSING_ENTRY_MIN_CLOSURE_BPS",
    "crossing_improvement_epsilon": "CROSSING_IMPROVEMENT_EPSILON_DEG_PER_TICK",
    "crossing_stall_ticks": "CROSSING_STALL_TICKS",
    "lag_ticks": "LAG_TICKS",
    "lag_yaw_fraction": "LAG_YAW_FRACTION",
    "lag_target_pitch": "LAG_TARGET_PITCH_DEG",
    "approach_lead_ticks": "APPROACH_LEAD_TICKS",
    "reentry_speed_floor": "REENTRY_SPEED_FLOOR_BPS",
    "reentry_target_speed_offset": "REENTRY_TARGET_SPEED_OFFSET_BPS",
    "reentry_min_agl": "REENTRY_MIN_AGL",
    "reentry_pull_out_seconds": "REENTRY_PULL_OUT_SECONDS",
}

CANDIDATE_BOOLEAN_CONSTANTS = {
    "p47_legacy_heading_capture_enabled": "P47_LEGACY_HEADING_CAPTURE_ENABLED",
}

PINNED_GATES = {
    "START_MIN_AGL": 90.0,
    "ATTACK_MAX_RAW_ANGLE_DEG": 45.0,
    "ATTACK_MAX_LEAD_ANGLE_DEG": 12.0,
    "ATTACK_MIN_DISTANCE": 24.0,
    "ATTACK_MAX_DISTANCE": 125.0,
    "ATTACK_MIN_CLOSURE_BPS": -6.0,
    "ATTACK_MAX_CLOSURE_BPS": 28.0,
}


def java_constants(text: str) -> dict[str, float]:
    pattern = re.compile(
        r"private\s+static\s+final\s+(?:double|int)\s+"
        r"([A-Z0-9_]+)\s*=\s*(-?(?:\d+(?:\.\d*)?|\.\d+))\s*;"
    )
    return {name: float(value) for name, value in pattern.findall(text)}


def java_boolean_constants(text: str) -> dict[str, bool]:
    pattern = re.compile(
        r"private\s+static\s+final\s+boolean\s+"
        r"([A-Z0-9_]+)\s*=\s*(true|false)\s*;"
    )
    return {name: value == "true" for name, value in pattern.findall(text)}


def main() -> int:
    candidate = json.loads(CANDIDATE.read_text(encoding="utf-8"))["parameters"]
    java_text = JAVA.read_text(encoding="utf-8")
    constants = java_constants(java_text)
    boolean_constants = java_boolean_constants(java_text)
    errors: list[str] = []

    for parameter, constant_name in CANDIDATE_CONSTANTS.items():
        expected = float(candidate[parameter])
        actual = constants.get(constant_name)
        if actual is None:
            errors.append(f"missing Java constant {constant_name}")
        elif not math.isclose(actual, expected, rel_tol=0.0, abs_tol=1.0e-9):
            errors.append(
                f"{constant_name}={actual} does not match candidate {parameter}={expected}"
            )

    for parameter, constant_name in CANDIDATE_BOOLEAN_CONSTANTS.items():
        expected = candidate[parameter]
        actual = boolean_constants.get(constant_name)
        if actual is None:
            errors.append(f"missing Java boolean constant {constant_name}")
        elif actual is not expected:
            errors.append(
                f"{constant_name}={actual} does not match candidate {parameter}={expected}"
            )

    for constant_name, expected in PINNED_GATES.items():
        actual = constants.get(constant_name)
        if actual is None:
            errors.append(f"missing pinned gate {constant_name}")
        elif not math.isclose(actual, expected, rel_tol=0.0, abs_tol=1.0e-9):
            errors.append(
                f"pinned gate {constant_name} changed from {expected} to {actual}"
            )

    if "boolean crossingStalled = isP47n(profile)" not in java_text:
        errors.append("crossing-lag hypothesis is not explicitly restricted to P-47N")
    if "boolean crossingCorridorPreviouslySeen = state.crossingCorridorSeen" not in java_text:
        errors.append("horizontal crossing corridor is not latched before plateau confirmation")
    if "horizontalRawAngle >= CROSSING_ENTRY_MIN_HORIZONTAL_ANGLE_DEG" not in java_text:
        errors.append("crossing corridor is not driven by the horizontal raw target angle")
    if java_text.count("state.stage == Stage.PIVOT && isP47n(profile)") < 2:
        errors.append("crossing corridor latch and plateau confirmation are not P-47N-only")
    if java_text.count("closure >= CROSSING_ENTRY_MIN_CLOSURE_BPS") < 3:
        errors.append("non-negative closure is not retained at corridor, plateau, and handoff")
    if '"energy_coupled_climb_crossing_corridor_latched"' not in java_text:
        errors.append("crossing corridor latch telemetry event is missing")
    if "!isP47n(profile) || P47_LEGACY_HEADING_CAPTURE_ENABLED" not in java_text:
        errors.append("P-47N legacy heading-capture switch is not connected")
    attack_gate_index = java_text.find("boolean attackSector")
    for guard in ("reentry_energy_guard", "reentry_pull_out_guard"):
        guard_index = java_text.find(f'"{guard}"')
        if guard_index < 0:
            errors.append(f"missing connected Java safety guard {guard}")
        elif attack_gate_index < 0 or guard_index >= attack_gate_index:
            errors.append(f"Java safety guard {guard} no longer precedes the attack gate")

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print(
        "P-47N candidate constants match production; P-47N scope and all pinned gates are intact."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
