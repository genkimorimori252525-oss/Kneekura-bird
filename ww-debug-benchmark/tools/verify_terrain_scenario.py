#!/usr/bin/env python3
"""Verify the focused predictive-terrain-avoidance GameTest."""

from __future__ import annotations

import argparse
import json
import math
import sys
import uuid
from pathlib import Path
from typing import Any


def target_uuid(root: Path, errors: list[str]) -> uuid.UUID | None:
    summaries = [path for path in root.rglob("validation-summary-*.json") if path.is_file()]
    if len(summaries) != 1:
        errors.append(f"expected exactly one validation summary, found {len(summaries)}")
        return None
    try:
        summary = json.loads(summaries[0].read_text(encoding="utf-8"))
        results = summary["results"]
        if not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], dict):
            raise ValueError("expected one result")
        if summary.get("state") != "complete":
            errors.append("validation summary state must be complete")
        for field in ("total", "completed"):
            value = summary.get(field)
            if type(value) is not int or value != 1:
                errors.append(f"validation summary {field} must be the integer 1")
        if results[0].get("passed") is not True:
            errors.append("validation summary result passed must be true")
        if results[0].get("final_phase") != "PARKED":
            errors.append("validation summary result final_phase must be PARKED")
        value = results[0]["aircraft_uuid"]
        if not isinstance(value, str):
            raise ValueError("aircraft UUID is not a string")
        return uuid.UUID(value)
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, IndexError):
        errors.append("validation summary must identify exactly one aircraft with a valid UUID")
        return None


def target_log(root: Path, target: uuid.UUID | None, errors: list[str]) -> Path | None:
    if target is None:
        return None
    suffix = f"-{target}"
    candidates = [path for path in root.rglob("aircraft/*.jsonl")
                  if path.is_file() and path.stem.endswith(suffix)]
    if len(candidates) != 1:
        errors.append(f"expected exactly one aircraft log for {target}, found {len(candidates)}")
        return None
    return candidates[0]


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def adapter_speed(value: Any) -> float | None:
    if type(value) not in (int, float):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) and number >= 0 else None


def parse_stall_guard(value: Any) -> float | None:
    if type(value) not in (int, float):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) and number > 0 else None


def read_jsonl(path: Path | None, errors: list[str], tainted: list[tuple[int, dict[str, Any]]]) -> list[dict[str, Any]]:
    if path is None:
        return []
    rows: list[dict[str, Any]] = []
    lines = 0
    try:
        with path.open("rb") as source:
            for lines, line in enumerate(source, 1):
                value = None
                try:
                    nonstandard = []
                    def mark_constant(constant: str) -> None:
                        nonstandard.append(constant)

                    value = json.loads(line.decode("utf-8"), parse_constant=mark_constant)
                    if not isinstance(value, dict):
                        raise ValueError("row is not an object")
                    if nonstandard:
                        raise ValueError("nonstandard JSON constant")
                    pending = [value]
                    while pending:
                        item = pending.pop()
                        if isinstance(item, str):
                            item.encode("utf-8")
                        elif isinstance(item, dict):
                            pending.extend(item.keys())
                            pending.extend(item.values())
                        elif isinstance(item, list):
                            pending.extend(item)
                except (UnicodeError, ValueError, RecursionError):
                    errors.append(f"selected terrain log line {lines} is not a valid UTF-8 JSON object")
                    if isinstance(value, dict):
                        tainted.append((lines, value))
                    continue
                rows.append(value)
    except OSError as exc:
        errors.append(f"could not read selected terrain log after {lines} lines: {exc.__class__.__name__}")
    if not lines:
        errors.append("selected terrain log is empty or unreadable")
    return rows


def route_coordinates(frame: dict[str, Any]) -> tuple[float, float, float] | None:
    position = frame.get("position") or {}
    home = frame.get("home_position") or {}
    forward = frame.get("runway_forward") or {}
    values = (
        finite(position.get("x")), finite(position.get("y")), finite(position.get("z")),
        finite(home.get("x")), finite(home.get("y")), finite(home.get("z")),
        finite(forward.get("x")), finite(forward.get("z")),
    )
    if any(value is None for value in values):
        return None
    px, py, pz, hx, hy, hz, fx, fz = values
    dx, dz = px - hx, pz - hz
    return dx * fx + dz * fz, dx * -fz + dz * fx, py - hy


def require(condition: bool, errors: list[str], message: str) -> None:
    if not condition:
        errors.append(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--gradle-status", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    errors: list[str] = []
    metrics: dict[str, Any] = {
        "scenario": "terrain",
        "gradle_status": args.gradle_status,
        "crash_reports": [str(path) for path in args.root.glob("crash-reports/*.txt")],
    }

    require(args.gradle_status == 0, errors,
            f"headless GameTest exited with status {args.gradle_status}")
    require(not metrics["crash_reports"], errors,
            "crash report paths found under the supplied root")
    require(bool(list(args.root.rglob("flight_profiles.json"))), errors,
            "no measured flight_profiles.json was produced or staged")
    identity_error_offset = len(errors)
    aircraft_uuid = target_uuid(args.root, errors)
    log_path = target_log(args.root, aircraft_uuid, errors)
    integrity_errors: list[str] = []
    tainted: list[tuple[int, dict[str, Any]]] = []
    rows = read_jsonl(log_path, integrity_errors, tainted)
    errors.extend(integrity_errors)
    if rows and aircraft_uuid is not None:
        for row in rows:
            try:
                value = row["aircraft_uuid"]
                if not isinstance(value, str) or uuid.UUID(value) != aircraft_uuid:
                    raise ValueError("aircraft UUID does not match")
            except (ValueError, TypeError, KeyError):
                errors.append("aircraft log contains missing, invalid or conflicting aircraft UUID")
                break
    frames = [row for row in rows if row.get("event") == "frame"]
    adapters = [
        row for row in rows
        if row.get("event") == "control_adapter"
        and row.get("applied_safety_override") in {
            "predictive_terrain_avoidance", "terrain_emergency_climb"
        }
    ]
    starts = [row for row in rows if row.get("event") == "terrain_avoidance_start"]

    metrics["telemetry_log"] = str(log_path) if log_path else None
    metrics["aircraft_uuid"] = str(aircraft_uuid) if aircraft_uuid else None
    metrics["frame_count"] = len(frames)
    metrics["terrain_adapter_count"] = len(adapters)
    metrics["terrain_start_count"] = len(starts)
    metrics["selected_log_parse_and_identity_checks_passed"] = log_path is not None and len(errors) == identity_error_offset
    if metrics["selected_log_parse_and_identity_checks_passed"]:
        require(bool(rows), errors, "no autonomous-flight telemetry was produced")
        require(bool(frames), errors, "no autonomous-flight frame telemetry was produced")
        require(bool(starts), errors, "predictive terrain avoidance never activated")
        require(bool(adapters), errors, "terrain avoidance produced no applied adapter telemetry")

    coordinates = [value for frame in frames if (value := route_coordinates(frame)) is not None]
    if metrics["selected_log_parse_and_identity_checks_passed"]:
        require(bool(coordinates), errors, "terrain route coordinates were unavailable")
    if coordinates:
        longitudes = [value[0] for value in coordinates]
        laterals = [value[1] for value in coordinates]
        altitudes = [value[2] for value in coordinates]
        maximum_longitudinal = max(longitudes)
        maximum_lateral = max(abs(value) for value in laterals)
        maximum_altitude = max(altitudes)
        metrics["maximum_longitudinal_blocks"] = maximum_longitudinal
        metrics["maximum_abs_lateral_blocks"] = maximum_lateral
        metrics["maximum_relative_altitude_blocks"] = maximum_altitude
        if metrics["selected_log_parse_and_identity_checks_passed"]:
            require(maximum_longitudinal > -45.0, errors,
                    f"aircraft did not pass the obstacle wall: {maximum_longitudinal:.3f}")
            require(maximum_lateral >= 24.0 or maximum_altitude >= 112.0, errors,
                    "aircraft neither routed around nor climbed above the obstacle wall")

    speeds = [adapter_speed(row.get("speed_bps")) for row in adapters]
    require(all(value is not None for value in speeds), errors,
            "terrain adapter has invalid or missing speed_bps")
    adapter_speeds = [value for value in speeds if value is not None]
    guards = [(raw, parse_stall_guard(raw)) for frame in frames
              for raw in [frame.get("profile_stall_guard_speed_bps")]]
    require(all(value is not None for _, value in guards), errors,
            "frame has invalid or missing profile_stall_guard_speed_bps")
    valid_guards = [(raw, value) for raw, value in guards if value is not None]
    guards_consistent = not valid_guards or all(raw == valid_guards[0][0] for raw, _ in valid_guards)
    guards_valid = all(value is not None for _, value in guards)
    require(guards_consistent, errors,
            "profile_stall_guard_speed_bps changed between frames")
    guard_values = [value for _, value in valid_guards]
    if metrics["selected_log_parse_and_identity_checks_passed"]:
        require(bool(adapter_speeds and guard_values), errors,
                "terrain adapter speed or stall-guard telemetry was unavailable")
    if adapter_speeds and guard_values:
        minimum_speed = min(adapter_speeds)
        stall_guard = max(guard_values)
        metrics["terrain_minimum_speed_bps"] = minimum_speed
        metrics["terrain_stall_guard_speed_bps"] = stall_guard
        guard_note = " (against maximum observed guard; guard values differ)" if not guards_consistent else ""
        require(minimum_speed >= stall_guard * 0.80, errors,
                f"terrain avoidance lost unsafe airspeed: {minimum_speed:.3f}/{stall_guard:.3f}{guard_note}")
        if any(value is None for value in speeds) or not guards_valid or not guards_consistent:
            metrics["observed_terrain_minimum_speed_bps"] = metrics.pop("terrain_minimum_speed_bps")
        if not guards_valid or not guards_consistent:
            metrics["observed_terrain_stall_guard_speed_bps"] = metrics.pop("terrain_stall_guard_speed_bps")

    require(all(type(frame.get("on_ground")) is bool for frame in frames), errors,
            "terrain frame has invalid or missing on_ground")
    require(not any(bool(frame.get("on_ground")) for frame in frames), errors,
            "aircraft touched the ground during terrain avoidance")
    tainted_guards = []
    tainted_speeds = []
    for line_number, row in tainted:
        if row.get("event") == "frame":
            if row.get("on_ground") is True:
                errors.append(f"selected terrain log line {line_number} observed ground contact (identity unverified)")
            guard = parse_stall_guard(row.get("profile_stall_guard_speed_bps"))
            if guard is None:
                errors.append(f"selected terrain log line {line_number} has invalid or missing profile_stall_guard_speed_bps (identity unverified)")
            elif guard_values and guard != guard_values[0]:
                errors.append(f"selected terrain log line {line_number} observed conflicting profile_stall_guard_speed_bps (identity unverified)")
            if guard is not None:
                tainted_guards.append((guard, line_number))
            if guard is not None and adapter_speeds and min(adapter_speeds) < guard * 0.80:
                errors.append(f"selected terrain log line {line_number} observed unsafe airspeed against guard (identity unverified)")
        if (row.get("event") == "control_adapter"
                and row.get("applied_safety_override") in ("predictive_terrain_avoidance", "terrain_emergency_climb")):
            speed = adapter_speed(row.get("speed_bps"))
            if speed is None:
                errors.append(f"selected terrain log line {line_number} has invalid or missing speed_bps (identity unverified)")
            elif guard_values and speed < max(guard_values) * 0.80:
                errors.append(f"selected terrain log line {line_number} observed unsafe airspeed (identity unverified)")
            if speed is not None:
                tainted_speeds.append((speed, line_number))

    if tainted_guards and tainted_speeds:
        guard, guard_line = max(tainted_guards)
        speed, speed_line = min(tainted_speeds)
        if speed < guard * 0.80:
            errors.append(f"selected terrain log line {speed_line} observed unsafe airspeed against guard in line {guard_line} (identity unverified)")

    if not metrics["selected_log_parse_and_identity_checks_passed"]:
        for name in ("frame_count", "terrain_adapter_count", "terrain_start_count",
                     "maximum_longitudinal_blocks", "maximum_abs_lateral_blocks",
                     "maximum_relative_altitude_blocks", "terrain_minimum_speed_bps",
                     "terrain_stall_guard_speed_bps"):
            if name in metrics:
                metrics["observed_" + name] = metrics.pop(name)

    result = {
        "scenario": "terrain",
        "passed": not errors,
        "errors": errors,
        "metrics": metrics,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=True, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True, indent=2))
    if errors:
        for error in errors:
            print("ERROR:", error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
