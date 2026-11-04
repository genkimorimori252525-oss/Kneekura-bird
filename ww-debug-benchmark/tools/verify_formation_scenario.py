#!/usr/bin/env python3
"""Verify three-aircraft collision avoidance and tagged formation convergence."""

from __future__ import annotations

import argparse
import itertools
import json
import math
import re
import statistics
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any

SLOT_ERROR = re.compile(r"(?:^|:)slot_error=(-?\d+(?:\.\d+)?)")
FORMATION_TEST_PHASES = {"CRUISE_OUTBOUND"}
MAX_POSITION_PAIRS_PER_TICK = 4096


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
        if (row.get("event") != "formation_slot_tracking"
                or str(row.get("phase", "")) not in FORMATION_TEST_PHASES):
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
                     if row.get("event") == "formation_slot_tracking"
                     and str(row.get("phase", "")) in FORMATION_TEST_PHASES]
    metrics["collision_start_count"] = len(collision_starts)
    metrics["collision_clear_count"] = len(collision_clears)
    metrics["formation_tracking_count"] = len(tracking_rows)
    require(bool(collision_starts), errors,
            "predicted aircraft collision avoidance never activated")
    require(bool(collision_clears), errors,
            "collision avoidance never cleared after separation")
    require(bool(tracking_rows), errors,
            "formation slot tracking never activated during straight flight")

    frames_by_name: dict[str, dict[int, list[tuple[float, float, float]]]] = {}
    for name, (_, rows) in logs.items():
        frames: dict[int, list[tuple[float, float, float]]] = {}
        seen_ticks: set[int] = set()
        duplicate_ticks: set[int] = set()
        for row in rows:
            if (row.get("event") != "frame"
                    or str(row.get("phase", "")) not in FORMATION_TEST_PHASES):
                continue
            row_tick = tick(row)
            if row_tick is not None:
                if row_tick in seen_ticks:
                    duplicate_ticks.add(row_tick)
                seen_ticks.add(row_tick)
            row_position = position(row)
            if row_tick is not None and row_position is not None:
                frames.setdefault(row_tick, []).append(row_position)
        require(not duplicate_ticks, errors,
                f"{name} has duplicate formation frame ticks: {sorted(duplicate_ticks)[:5]}")
        frames_by_name[name] = frames

    pair_series: dict[str, list[tuple[int, float]]] = {}
    truncated_pairs: set[str] = set()
    for first, second in itertools.combinations(sorted(frames_by_name), 2):
        pair = f"{first} <> {second}"
        common = sorted(set(frames_by_name[first]) & set(frames_by_name[second]))
        series: list[tuple[int, float]] = []
        for value in common:
            first_positions = frames_by_name[first][value]
            second_positions = frames_by_name[second][value]
            count = len(first_positions) * len(second_positions)
            if count > MAX_POSITION_PAIRS_PER_TICK:
                truncated_pairs.add(pair)
                errors.append(f"{pair} tick {value} position pair evaluation limit "
                              f"{MAX_POSITION_PAIRS_PER_TICK} exceeded ({count} pairs); "
                              "distance metrics are incomplete")
            positions = ((a, b) for a in first_positions for b in second_positions)
            evaluated = itertools.islice(positions, MAX_POSITION_PAIRS_PER_TICK)
            series.append((value, min(distance(a, b) for a, b in evaluated)))
        pair_series[pair] = series

    all_distances = [value for series in pair_series.values() for _, value in series]
    minimum_evaluated = min(all_distances) if all_distances else None
    metrics["minimum_pairwise_distance_blocks"] = None if truncated_pairs else minimum_evaluated
    if truncated_pairs:
        metrics["minimum_evaluated_pairwise_distance_blocks"] = minimum_evaluated
    require(bool(all_distances), errors,
            "synchronized formation position telemetry was unavailable")
    if all_distances:
        require(minimum_evaluated >= 2.0, errors,
                f"aircraft bodies approached collision distance: {minimum_evaluated:.3f}")

    recovered_pairs = 0
    pair_metrics: dict[str, Any] = {}
    for pair, series in pair_series.items():
        if pair in truncated_pairs:
            pair_metrics[pair] = None
            continue
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
            "straight_flight_final_distance": series[-1][1],
        }
        if initial < 13.0 and best_later >= 15.0:
            recovered_pairs += 1
    metrics["pairwise_separation"] = pair_metrics
    metrics["recovered_dangerous_pairs"] = None if truncated_pairs else recovered_pairs
    if not truncated_pairs:
        require(recovered_pairs >= 1, errors,
                "no initially dangerous aircraft pair recovered to at least 15 blocks separation")

    convergence: dict[str, Any] = {}
    for name in wingman_names[:2]:
        rows = logs[name][1]
        values = slot_errors(rows)
        require(len(values) >= 6, errors,
                f"{name} produced fewer than six straight-flight formation samples")
        if not values:
            continue
        initial = values[0][1]
        late_window = [value for _, value in values[-min(6, len(values)):]]
        late_median = statistics.median(late_window)
        final = values[-1][1]
        converged = late_median <= 35.0 or late_median <= initial * 0.75
        convergence[name] = {
            "sample_count": len(values),
            "initial_slot_error": initial,
            "late_window_median_slot_error": late_median,
            "straight_flight_final_slot_error": final,
            "converged": converged,
        }
        require(converged, errors,
                f"{name} did not sustain convergence: {initial:.3f} -> median {late_median:.3f}")
    metrics["formation_convergence"] = convergence

    unsafe_ground_frames = []
    speed_metrics: dict[str, Any] = {}
    for name, (_, rows) in logs.items():
        formation_frames = [row for row in rows
                            if row.get("event") == "frame"
                            and str(row.get("phase", "")) in FORMATION_TEST_PHASES]
        require(bool(formation_frames), errors,
                f"{name} produced no straight-flight formation frames")
        speeds: list[float] = []
        guards: list[float] = []
        unsafe_speeds: list[tuple[float, float]] = []
        speed_guard_pairs: list[tuple[float, float]] = []
        invalid_fields: dict[str, list[int | None]] = {
            "on_ground": [], "speed_bps": [], "profile_stall_guard_speed_bps": []
        }
        for row in formation_frames:
            row_tick = tick(row)
            ground = row.get("on_ground")
            if not isinstance(ground, bool):
                invalid_fields["on_ground"].append(row_tick)
            elif ground:
                unsafe_ground_frames.append((name, row_tick))

            values: dict[str, float | None] = {}
            for field in ("speed_bps", "profile_stall_guard_speed_bps"):
                raw = row.get(field)
                try:
                    value = float(raw) if type(raw) in (int, float) else None
                except OverflowError:
                    value = None
                if value is None or not math.isfinite(value) or (field == "profile_stall_guard_speed_bps" and value <= 0):
                    invalid_fields[field].append(row_tick)
                    values[field] = None
                else:
                    values[field] = value
            speed = values["speed_bps"]
            guard = values["profile_stall_guard_speed_bps"]
            if speed is not None:
                speeds.append(speed)
            if guard is not None:
                guards.append(guard)
            if speed is not None and guard is not None:
                speed_guard_pairs.append((speed, guard))
                if speed < guard * 0.90:
                    unsafe_speeds.append((speed, guard))

        for field, invalid_ticks in invalid_fields.items():
            require(not invalid_ticks, errors,
                    f"{name} has invalid or missing {field} in formation frames at ticks {invalid_ticks[:5]}")
        # These metrics summarize observed frames only, and are incomplete if any
        # observed speed or guard could not be evaluated.
        speed_metrics[name] = None
        if (formation_frames and not invalid_fields["speed_bps"]
                and not invalid_fields["profile_stall_guard_speed_bps"]):
            constant_guard = len(set(guards)) == 1
            speed_metrics[name] = {
                "minimum_formation_speed_bps": min(speeds),
                "stall_guard_speed_bps": guards[0] if constant_guard else None,
            }
            if not constant_guard:
                # Compare the exact values represented by the observed floats.
                speed, guard = min(
                    speed_guard_pairs,
                    key=lambda pair: Fraction.from_float(pair[0]) / Fraction.from_float(pair[1]),
                )
                try:
                    ratio = float(Fraction.from_float(speed) / Fraction.from_float(guard))
                except OverflowError:
                    ratio = None
                if ratio == 0.0 and speed != 0.0:
                    ratio = None  # A nonzero ratio underflowed the float representation.
                speed_metrics[name].update({
                    "worst_speed_bps": speed,
                    "worst_stall_guard_speed_bps": guard,
                    "worst_speed_to_guard_ratio": ratio,
                })
        if unsafe_speeds:
            speed, guard = min(unsafe_speeds, key=lambda pair: pair[0])
            require(False, errors,
                    f"{name} lost unsafe formation airspeed: {speed:.3f}/{guard:.3f}")
    metrics["formation_speed"] = speed_metrics
    metrics["unsafe_ground_frames"] = unsafe_ground_frames
    require(not unsafe_ground_frames, errors,
            f"formation aircraft touched ground during straight formation flight: {unsafe_ground_frames[:5]}")

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
