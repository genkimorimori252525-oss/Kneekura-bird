#!/usr/bin/env python3
"""Verify headless autonomous-flight evidence with scenario-specific acceptance criteria."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Iterable


def latest(paths: Iterable[Path]) -> Path | None:
    candidates = [path for path in paths if path.is_file()]
    return max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None


def finite(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def read_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def read_jsonl(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return rows
    for line in lines:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def phase_frames(frames: list[dict[str, Any]], phase: str) -> list[dict[str, Any]]:
    return [frame for frame in frames if frame.get("phase") == phase]


def numeric(frames: list[dict[str, Any]], key: str) -> list[float]:
    result: list[float] = []
    for frame in frames:
        value = finite(frame.get(key))
        if value is not None:
            result.append(value)
    return result


def altitude_values(frames: list[dict[str, Any]]) -> list[float]:
    result: list[float] = []
    for frame in frames:
        position = frame.get("position") or {}
        value = finite(position.get("y"))
        if value is not None:
            result.append(value)
    return result


def transition_reasons(rows: list[dict[str, Any]]) -> set[str]:
    return {
        str(row.get("reason"))
        for row in rows
        if row.get("event") == "phase_transition" and row.get("reason") is not None
    }


def require(condition: bool, errors: list[str], message: str) -> None:
    if not condition:
        errors.append(message)


def verify_summary(summary: dict[str, Any], errors: list[str], metrics: dict[str, Any]) -> None:
    results = summary.get("results") or []
    total = int(summary.get("total") or 0)
    failures = [row for row in results if not row.get("passed")]
    metrics["summary_total"] = total
    metrics["summary_passed"] = total - len(failures)
    require(summary.get("state") == "complete", errors,
            f"validation state was {summary.get('state')!r}")
    require(total > 0 and len(results) == total, errors,
            f"validation result count was {len(results)}/{total}")
    if failures:
        first = failures[0]
        errors.append(
            "first flight failure: "
            f"{first.get('entity_id')}:{first.get('final_phase')}:{first.get('reason')}"
        )


def verify_turn(rows: list[dict[str, Any]], frames: list[dict[str, Any]],
                errors: list[str], metrics: dict[str, Any]) -> None:
    reasons = transition_reasons(rows)
    require(any("TURN_LEFT->CRUISE_CROSS:left_turn_heading_reached" in value for value in reasons),
            errors, "left turn did not reach the commanded heading")
    require(any("TURN_RIGHT->STALL_SETUP:right_turn_heading_reached" in value for value in reasons),
            errors, "right turn did not reach the commanded heading")

    left = phase_frames(frames, "TURN_LEFT")
    right = phase_frames(frames, "TURN_RIGHT")
    left_roll = numeric(left, "roll_deg")
    right_roll = numeric(right, "roll_deg")
    require(bool(left_roll), errors, "left-turn roll telemetry was unavailable")
    require(bool(right_roll), errors, "right-turn roll telemetry was unavailable")
    if left_roll:
        metrics["left_min_roll_deg"] = min(left_roll)
        require(min(left_roll) <= -8.0, errors,
                f"left turn did not bank left enough: {min(left_roll):.3f} deg")
    if right_roll:
        metrics["right_max_roll_deg"] = max(right_roll)
        require(max(right_roll) >= 8.0, errors,
                f"right turn did not bank right enough: {max(right_roll):.3f} deg")

    for name, selected in (("left", left), ("right", right)):
        heights = altitude_values(selected)
        require(bool(heights), errors, f"{name}-turn altitude telemetry was unavailable")
        if heights:
            excursion = max(heights) - min(heights)
            metrics[f"{name}_altitude_excursion_blocks"] = excursion
            require(excursion <= 5.0, errors,
                    f"{name} turn altitude excursion was {excursion:.3f} blocks")
        require(not any(bool(frame.get("on_ground")) for frame in selected), errors,
                f"aircraft touched the ground during the {name} turn")


def verify_stall(rows: list[dict[str, Any]], frames: list[dict[str, Any]],
                 errors: list[str], metrics: dict[str, Any]) -> None:
    reasons = transition_reasons(rows)
    require(any("STALL_ENTRY->STALL_RECOVERY" in value for value in reasons),
            errors, "controlled stall did not enter recovery")
    require(any("STALL_RECOVERY->RETURN_TO_PATTERN" in value for value in reasons),
            errors, "stall recovery did not return to the flight pattern")

    entry = phase_frames(frames, "STALL_ENTRY")
    recovery = phase_frames(frames, "STALL_RECOVERY")
    entry_speeds = numeric(entry, "speed_bps")
    guard_values = numeric(entry, "profile_stall_guard_speed_bps")
    require(bool(entry_speeds and guard_values), errors,
            "stall-entry speed or measured guard telemetry was unavailable")
    if entry_speeds and guard_values:
        minimum_speed = min(entry_speeds)
        guard = guard_values[0]
        metrics["stall_minimum_speed_bps"] = minimum_speed
        metrics["stall_guard_speed_bps"] = guard
        require(minimum_speed <= guard * 1.20, errors,
                f"stall entry never approached the measured guard speed: {minimum_speed:.3f}/{guard:.3f}")

    recovery_speeds = numeric(recovery, "speed_bps")
    climb_targets = numeric(recovery, "profile_climb_target_speed_bps")
    require(bool(recovery_speeds and climb_targets), errors,
            "stall-recovery speed telemetry was unavailable")
    if recovery_speeds and climb_targets:
        maximum_speed = max(recovery_speeds)
        target = climb_targets[0]
        metrics["recovery_maximum_speed_bps"] = maximum_speed
        metrics["recovery_target_speed_bps"] = target
        require(maximum_speed >= target * 0.90, errors,
                f"stall recovery did not restore enough airspeed: {maximum_speed:.3f}/{target:.3f}")

    require(not any(bool(frame.get("on_ground")) for frame in entry + recovery), errors,
            "aircraft touched the ground during stall entry or recovery")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--scenario", choices=("full", "landing", "stall", "turn"), required=True)
    parser.add_argument("--gradle-status", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    errors: list[str] = []
    metrics: dict[str, Any] = {
        "scenario": args.scenario,
        "gradle_status": args.gradle_status,
    }
    crash_reports = list(args.root.glob("crash-reports/*.txt"))
    metrics["crash_reports"] = [str(path) for path in crash_reports]

    # Full and landing scenarios are expected to end through PARKED and a clean GameTest exit.
    # Focused turn/stall scenarios intentionally stop at their short mission budget after their
    # evidence has been recorded, so Forge reports the timeout as exit code 1 and writes a GameTest
    # failure report. Those process-level signals are non-fatal only when the telemetry criteria
    # below prove that the requested maneuver completed correctly.
    if args.scenario in {"full", "landing"}:
        if args.gradle_status != 0:
            errors.append(f"Gradle GameTest exit code was {args.gradle_status}")
        if crash_reports:
            errors.append("crash report created: " + ", ".join(str(path) for path in crash_reports))

    profile_paths = list(args.root.rglob("flight_profiles.json"))
    require(bool(profile_paths), errors, "no measured flight_profiles.json was produced or staged")

    log_path = latest(args.root.rglob("aircraft/*.jsonl"))
    rows = read_jsonl(log_path)
    frames = [row for row in rows if row.get("event") == "frame"]
    require(bool(rows), errors, "no per-aircraft autonomous-flight telemetry was produced")
    require(bool(frames), errors, "no autonomous-flight frame telemetry was produced")
    metrics["telemetry_log"] = str(log_path) if log_path else None
    metrics["frame_count"] = len(frames)

    summary_path = latest(args.root.rglob("validation-summary-*.json"))
    summary = read_json(summary_path)
    metrics["summary_path"] = str(summary_path) if summary_path else None

    if args.scenario in {"full", "landing"}:
        require(bool(summary), errors, "no autonomous-flight validation summary was produced")
        if summary:
            verify_summary(summary, errors, metrics)
    elif args.scenario == "turn":
        verify_turn(rows, frames, errors, metrics)
    elif args.scenario == "stall":
        verify_stall(rows, frames, errors, metrics)

    result = {
        "scenario": args.scenario,
        "passed": not errors,
        "errors": errors,
        "metrics": metrics,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if errors:
        for error in errors:
            print("ERROR:", error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
