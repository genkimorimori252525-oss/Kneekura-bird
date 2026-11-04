#!/usr/bin/env python3
"""Verify the focused predictive-terrain-avoidance GameTest."""

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
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def read_jsonl(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                rows.append(value)
    except OSError:
        return []
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
    require(bool(list(args.root.rglob("flight_profiles.json"))), errors,
            "no measured flight_profiles.json was produced or staged")
    log_path = latest(args.root.rglob("aircraft/*.jsonl"))
    rows = read_jsonl(log_path)
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
    metrics["frame_count"] = len(frames)
    metrics["terrain_adapter_count"] = len(adapters)
    metrics["terrain_start_count"] = len(starts)
    require(bool(rows), errors, "no autonomous-flight telemetry was produced")
    require(bool(frames), errors, "no autonomous-flight frame telemetry was produced")
    require(bool(starts), errors, "predictive terrain avoidance never activated")
    require(bool(adapters), errors, "terrain avoidance produced no applied adapter telemetry")

    coordinates = [value for frame in frames if (value := route_coordinates(frame)) is not None]
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
        require(maximum_longitudinal > -45.0, errors,
                f"aircraft did not pass the obstacle wall: {maximum_longitudinal:.3f}")
        require(maximum_lateral >= 24.0 or maximum_altitude >= 112.0, errors,
                "aircraft neither routed around nor climbed above the obstacle wall")

    adapter_speeds = [value for row in adapters if (value := finite(row.get("speed_bps"))) is not None]
    guard_values = [value for frame in frames
                    if (value := finite(frame.get("profile_stall_guard_speed_bps"))) is not None]
    require(bool(adapter_speeds and guard_values), errors,
            "terrain adapter speed or stall-guard telemetry was unavailable")
    if adapter_speeds and guard_values:
        minimum_speed = min(adapter_speeds)
        stall_guard = guard_values[0]
        metrics["terrain_minimum_speed_bps"] = minimum_speed
        metrics["terrain_stall_guard_speed_bps"] = stall_guard
        require(minimum_speed >= stall_guard * 0.80, errors,
                f"terrain avoidance lost unsafe airspeed: {minimum_speed:.3f}/{stall_guard:.3f}")

    require(not any(bool(frame.get("on_ground")) for frame in frames), errors,
            "aircraft touched the ground during terrain avoidance")

    result = {
        "scenario": "terrain",
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
