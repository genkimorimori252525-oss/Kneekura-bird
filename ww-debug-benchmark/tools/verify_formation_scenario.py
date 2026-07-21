#!/usr/bin/env python3
"""Verify three-aircraft collision avoidance and tagged formation convergence."""

from __future__ import annotations

import argparse
import itertools
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

SLOT_ERROR = re.compile(r"(?:^|:)slot_error=(-?\d+(?:\.\d+)?)")
AIRBORNE_PHASES = {
    "ROTATE", "CLIMB", "CRUISE_OUTBOUND", "TURN_LEFT", "CRUISE_CROSS",
    "TURN_RIGHT", "STALL_SETUP", "STALL_ENTRY", "STALL_RECOVERY",
    "RETURN_TO_PATTERN", "DOWNWIND", "BASE", "FINAL", "FLARE", "GO_AROUND",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
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


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def tick(row: dict[str, Any]) -> int | None:
    value = finite(row.get("server_tick"))
    return int(value) if value is not None else None


def position(row: dict[str, Any]) -> tuple[float, float, float] | None:
    data = row.get("position")
    if not isinstance(data, dict):
        return None
    values = finite(data.get("x")), finite(data.get("y")), finite(data.get("z"))
    if any(value is None for value in values):
        return None
    return values  # type: ignore[return-value]


def distance(first: tuple[float, float, float],
             second: tuple[float, float, float]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(first, second)))


def require(condition: bool, errors: list[str], message: str) -> None:
    if not condition:
        errors.append(message)


def aircraft_name(rows: list[dict[str, Any]]) -> str:
    fallback = "unknown"
    for row in rows:
        value = row.get("aircraft_name")
        if not isinstance(value, str) or not value:
            continue
        fallback = value
        if "FORMATION" in value:
            return value
    return fallback


def slot_errors(rows: list[dict[str, Any]]) -> list[tuple[int, float]]:
    values: list[tuple[int, float]] = []
    for row in rows:
        if row.get("event") != "formation_slot_tracking":
            continue
        match = SLOT_ERROR.search(str(row.get("reason", "")))
        row_tick = tick(row)
        if match is None or row_tick is None:
            continue
        values.append((row_tick, float(match.group(1))))
    return values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--gradle-status", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    logs: dict[str, tuple[Path, list[dict[str, Any]]]] = {}
    for path in args.root.rglob("aircraft/*.jsonl"):
        rows = read_jsonl(path)
        name = aircraft_name(rows)
        if "FORMATION" in name:
            logs[name] = (path, rows)

    errors: list[str] = []
    metrics: dict[str, Any] = {
        "scenario": "formation",
        "gradle_status": args.gradle_status,
        "formation_aircraft": sorted(logs),
        "crash_reports": [str(path) for path in args.root.glob("crash-reports/*.txt")],
    }
    require(args.gradle_status == 0, errors,
            f"headless GameTest exited with status {args.gradle_status}")
    require(len(logs) >= 3, errors,
            f"expected at least three formation aircraft logs, found {len(logs)}")

    leader_names = [name for name in logs if "LEADER" in name]
    wingman_names = sorted(name for name in logs if "WINGMAN" in name)
    require(len(leader_names) == 1, errors,
            f"expected one formation leader, found {leader_names}")
    require(len(wingman_names) >= 2, errors,
            f"expected two formation wingmen, found {wingman_names}")

    all_rows = [row for _, rows in logs.values() for row in rows]
    collision_starts = [row for row in all_rows
                        if row.get("event") == "collision_avoidance_start"]
    collision_clears = [row for row in all_rows
                        if row.get("event") == "collision_avoidance_clear"]
    tracking_rows = [row for row in all_rows
                     if row.get("event") == "formation_slot_tracking"]
    metrics["collision_start_count"] = len(collision_starts)
    metrics["collision_clear_count"] = len(collision_clears)
    metrics["formation_tracking_count"] = len(tracking_rows)
    require(bool(collision_starts), errors,
            "predicted aircraft collision avoidance never activated")
    require(bool(collision_clears), errors,
            "collision avoidance never cleared after separation")
    require(bool(tracking_rows), errors,
            "formation slot tracking never activated")

    frames_by_name: dict[str, dict[int, tuple[float, float, float]]] = {}
    for name, (_, rows) in logs.items():
        frames: dict[int, tuple[float, float, float]] = {}
        for row in rows:
            if row.get("event") != "frame":
                continue
            row_tick = tick(row)
            row_position = position(row)
            if row_tick is not None and row_position is not None:
                frames[row_tick] = row_position
        frames_by_name[name] = frames

    pair_series: dict[str, list[tuple[int, float]]] = {}
    for first, second in itertools.combinations(sorted(frames_by_name), 2):
        common = sorted(set(frames_by_name[first]) & set(frames_by_name[second]))
        series = [
            (value, distance(frames_by_name[first][value], frames_by_name[second][value]))
            for value in common
        ]
        pair_series[f"{first} <> {second}"] = series

    all_distances = [value for series in pair_series.values() for _, value in series]
    metrics["minimum_pairwise_distance_blocks"] = min(all_distances) if all_distances else None
    require(bool(all_distances), errors,
            "synchronized formation position telemetry was unavailable")
    if all_distances:
        require(min(all_distances) >= 2.0, errors,
                f"aircraft bodies approached collision distance: {min(all_distances):.3f}")

    recovered_pairs = 0
    pair_metrics: dict[str, Any] = {}
    for pair, series in pair_series.items():
        if not series:
            continue
        start_tick = series[0][0]
        early = [value for row_tick, value in series if row_tick <= start_tick + 20]
        later = [value for row_tick, value in series if row_tick >= start_tick + 60]
        initial = min(early) if early else series[0][1]
        best_later = max(later) if later else max(value for _, value in series)
        pair_metrics[pair] = {
            "initial_minimum": initial,
            "later_maximum": best_later,
            "final_distance": series[-1][1],
        }
        if initial < 13.0 and best_later >= 15.0:
            recovered_pairs += 1
    metrics["pairwise_separation"] = pair_metrics
    metrics["recovered_dangerous_pairs"] = recovered_pairs
    require(recovered_pairs >= 1, errors,
            "no initially dangerous aircraft pair recovered to at least 15 blocks separation")

    convergence: dict[str, Any] = {}
    for name in wingman_names[:2]:
        rows = logs[name][1]
        values = slot_errors(rows)
        require(len(values) >= 3, errors,
                f"{name} produced fewer than three formation-error samples")
        if not values:
            continue
        initial = values[0][1]
        split = max(1, len(values) // 2)
        late_values = [value for _, value in values[split:]] or [values[-1][1]]
        best_late = min(late_values)
        final = values[-1][1]
        converged = best_late <= 32.0 or best_late <= initial * 0.72
        convergence[name] = {
            "sample_count": len(values),
            "initial_slot_error": initial,
            "best_late_slot_error": best_late,
            "final_slot_error": final,
            "converged": converged,
        }
        require(converged, errors,
                f"{name} did not converge toward its formation slot: {initial:.3f} -> {best_late:.3f}")
    metrics["formation_convergence"] = convergence

    unsafe_ground_frames = []
    speed_metrics: dict[str, Any] = {}
    for name, (_, rows) in logs.items():
        airborne_frames = [row for row in rows
                           if row.get("event") == "frame"
                           and str(row.get("phase", "")) in AIRBORNE_PHASES]
        unsafe_ground_frames.extend(
            (name, tick(row)) for row in airborne_frames if bool(row.get("on_ground"))
        )
        speeds = [value for row in airborne_frames
                  if (value := finite(row.get("speed_bps"))) is not None]
        guards = [value for row in airborne_frames
                  if (value := finite(row.get("profile_stall_guard_speed_bps"))) is not None]
        if speeds and guards:
            minimum = min(speeds)
            guard = guards[0]
            speed_metrics[name] = {
                "minimum_airborne_speed_bps": minimum,
                "stall_guard_speed_bps": guard,
            }
            require(minimum >= guard * 0.78, errors,
                    f"{name} lost unsafe airspeed: {minimum:.3f}/{guard:.3f}")
    metrics["airborne_speed"] = speed_metrics
    metrics["unsafe_ground_frames"] = unsafe_ground_frames
    require(not unsafe_ground_frames, errors,
            f"formation aircraft touched ground in airborne phases: {unsafe_ground_frames[:5]}")

    result = {
        "scenario": "formation",
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
