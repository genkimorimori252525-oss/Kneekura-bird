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


def main() -> int:
    candidate = json.loads(CANDIDATE.read_text(encoding="utf-8"))["parameters"]
    constants = java_constants(JAVA.read_text(encoding="utf-8"))
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

    for constant_name, expected in PINNED_GATES.items():
        actual = constants.get(constant_name)
        if actual is None:
            errors.append(f"missing pinned gate {constant_name}")
        elif not math.isclose(actual, expected, rel_tol=0.0, abs_tol=1.0e-9):
            errors.append(
                f"pinned gate {constant_name} changed from {expected} to {actual}"
            )

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print(
        "P-47N candidate constants match production and all pinned attack/safety gates are intact."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
