#!/usr/bin/env python3
"""Verify two explicitly hostile autonomous fighters acquire, manoeuvre, fire and separate safely."""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
from pathlib import Path
from typing import Any

TEXT = re.compile(r"([a-z_]+)=([^:]+)")
NUMBER = re.compile(r"([a-z_]+)=(-?\d+(?:\.\d+)?)")
ACTION = re.compile(r"(?:^|:)to=([A-Z_]+)")


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


def numbers(reason: str) -> dict[str, float]:
    return {name: float(value) for name, value in NUMBER.findall(reason)}


def texts(reason: str) -> dict[str, str]:
    return {name: value for name, value in TEXT.findall(reason)}


def require(condition: bool, errors: list[str], message: str) -> None:
    if not condition:
        errors.append(message)


def boundary_tick(events: list[dict[str, Any]], label: str, errors: list[str]) -> int | None:
    """An ambiguous or unplaceable boundary cannot define a safety window."""
    if len(events) != 1:
        errors.append(f"expected exactly one mutual dogfight {label} event; found {len(events)}")
        return None
    value = events[0].get("server_tick")
    if type(value) is not int or value < 0:
        errors.append(f"mutual dogfight {label} event has missing or invalid tick")
        return None
    return value


def combat_frame_metrics(frames: list[dict[str, Any]], label: str,
                         errors: list[str]) -> tuple[float | None, int | None]:
    """Validate observed samples; this does not imply continuous tick coverage."""
    if not frames:
        errors.append(f"{label} has no combat-window frame telemetry")
        return None, None

    speeds: list[float] = []
    invalid_speeds = 0
    invalid_ground = 0
    ground_frames = 0
    for frame in frames:
        value = frame.get("speed_bps")
        try:
            speed = float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None
        except (ValueError, OverflowError):
            speed = None
        if speed is None or not math.isfinite(speed) or speed < 0:
            invalid_speeds += 1
        else:
            speeds.append(speed)
        ground = frame.get("on_ground")
        if type(ground) is not bool:
            invalid_ground += 1
        elif ground:
            ground_frames += 1

    if invalid_speeds:
        errors.append(f"{label} has {invalid_speeds} frames with missing or invalid speed")
    if invalid_ground:
        errors.append(f"{label} has {invalid_ground} frames with missing or invalid ground state")
    # Preserve violations observed in valid, placeable samples even when another sample makes
    # the aggregate unknown. An unknown sample cannot make an observed violation disappear.
    if ground_frames:
        errors.append(f"{label} touched the ground during mutual combat: {ground_frames} observed frames")
    if speeds and min(speeds) < 8.5:
        errors.append(f"{label} speed became unsafe: {min(speeds)!r} bps")
    return (min(speeds) if not invalid_speeds else None,
            ground_frames if not invalid_ground else None)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--gradle-status", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    logs: dict[str, tuple[Path, list[dict[str, Any]]]] = {}
    for path in args.root.rglob("aircraft/*.jsonl"):
        rows = read_jsonl(path)
        name = next((str(row.get("aircraft_name")) for row in rows if row.get("aircraft_name")), path.name)
        logs[name] = (path, rows)

    primary_entry = next(
        ((path, rows) for name, (path, rows) in logs.items()
         if name.startswith("AUTOPILOT TEST warfare_wings:a6m")),
        None,
    )
    opponent_entry = next(
        ((path, rows) for name, (path, rows) in logs.items()
         if "MUTUAL BLUE P47N" in name),
        None,
    )
    primary_rows = primary_entry[1] if primary_entry else []
    opponent_rows = opponent_entry[1] if opponent_entry else []

    started = [row for row in primary_rows if row.get("event") == "mutual_dogfight_validation_started"]
    completed = [row for row in primary_rows if row.get("event") == "mutual_dogfight_validation_completed"]
    mutual_status = [row for row in primary_rows if row.get("event") == "mutual_dogfight_validation_status"]

    primary_acquisitions = [row for row in primary_rows if row.get("event") == "combat_target_acquired"]
    opponent_acquisitions = [row for row in opponent_rows if row.get("event") == "combat_target_acquired"]
    primary_transitions = [row for row in primary_rows if row.get("event") == "air_combat_action_transition"]
    opponent_transitions = [row for row in opponent_rows if row.get("event") == "air_combat_action_transition"]
    primary_fires = [row for row in primary_rows if row.get("event") == "weapon_fire"]
    opponent_fires = [row for row in opponent_rows if row.get("event") == "weapon_fire"]

    status_values = [numbers(str(row.get("reason", ""))) for row in mutual_status]
    completion_values = numbers(str(completed[-1].get("reason", ""))) if completed else {}
    separations = [value["separation"] for value in status_values if "separation" in value]
    min_separation = completion_values.get("minimum_separation", min(separations) if separations else None)
    max_separation = completion_values.get("maximum_separation", max(separations) if separations else None)
    primary_track_ticks = completion_values.get("primary_track_ticks", 0.0)
    opponent_track_ticks = completion_values.get("opponent_track_ticks", 0.0)
    primary_combat_ticks = completion_values.get("primary_combat_ticks", 0.0)
    opponent_combat_ticks = completion_values.get("opponent_combat_ticks", 0.0)

    primary_doctrines = {
        value["doctrine"]
        for row in primary_transitions
        if "doctrine" in (value := texts(str(row.get("reason", ""))))
    }
    opponent_doctrines = {
        value["doctrine"]
        for row in opponent_transitions
        if "doctrine" in (value := texts(str(row.get("reason", ""))))
    }
    primary_actions = [
        match.group(1)
        for row in primary_transitions
        if (match := ACTION.search(str(row.get("reason", ""))))
    ]
    opponent_actions = [
        match.group(1)
        for row in opponent_transitions
        if (match := ACTION.search(str(row.get("reason", ""))))
    ]

    errors: list[str] = []
    start_tick = boundary_tick(started, "start", errors)
    completion_tick = boundary_tick(completed, "completion", errors)
    window_valid = start_tick is not None and completion_tick is not None and completion_tick > start_tick
    if start_tick is not None and completion_tick is not None and not window_valid:
        errors.append("mutual dogfight completion must follow start")

    def combat_frames(rows: list[dict[str, Any]], label: str) -> tuple[list[dict[str, Any]], bool]:
        invalid_ticks = sum(
            1 for row in rows if row.get("event") == "frame"
            and (type(row.get("server_tick")) is not int or row["server_tick"] < 0)
        )
        if invalid_ticks:
            errors.append(f"{label} has {invalid_ticks} frames with missing or invalid ticks")
        frames = [
            row for row in rows if row.get("event") == "frame"
            and type(row.get("server_tick")) is int and row["server_tick"] >= 0
            and window_valid
            and start_tick <= row["server_tick"] <= completion_tick
        ]
        return frames, invalid_ticks == 0

    primary_frames, primary_ticks_valid = combat_frames(primary_rows, "A6M")
    opponent_frames, opponent_ticks_valid = combat_frames(opponent_rows, "P-47N")
    primary_min_speed, primary_ground = combat_frame_metrics(primary_frames, "A6M", errors)
    opponent_min_speed, opponent_ground = combat_frame_metrics(opponent_frames, "P-47N", errors)
    # An unplaceable sample could belong to the combat window, so even otherwise valid
    # in-window samples cannot establish a minimum speed or a zero-ground count.
    if not primary_ticks_valid:
        primary_min_speed, primary_ground = None, None
    if not opponent_ticks_valid:
        opponent_min_speed, opponent_ground = None, None

    primary_acquisition_reasons = [str(row.get("reason", "")) for row in primary_acquisitions]
    opponent_acquisition_reasons = [str(row.get("reason", "")) for row in opponent_acquisitions]

    require(bool(primary_rows), errors, "primary A6M telemetry was not produced")
    require(bool(opponent_rows), errors, "opposing P-47N telemetry was not produced")
    require(bool(started), errors, "mutual dogfight scene never started")
    require(bool(completed), errors, "mutual dogfight scene never completed")
    require(any("target_faction=blue" in reason and "explicit_faction_hostile=true" in reason
                for reason in primary_acquisition_reasons), errors,
            "A6M never explicitly acquired the blue-faction opponent")
    require(any("target_faction=red" in reason and "explicit_faction_hostile=true" in reason
                for reason in opponent_acquisition_reasons), errors,
            "P-47N never explicitly acquired the red-faction opponent")
    require(primary_track_ticks >= 80, errors,
            f"A6M did not track the P-47N long enough: {primary_track_ticks}")
    require(opponent_track_ticks >= 80, errors,
            f"P-47N did not track the A6M long enough: {opponent_track_ticks}")
    require(primary_combat_ticks >= 100, errors,
            f"A6M air-combat control was not sustained: {primary_combat_ticks}")
    require(opponent_combat_ticks >= 100, errors,
            f"P-47N air-combat control was not sustained: {opponent_combat_ticks}")
    require(bool(primary_transitions), errors, "A6M selected no air-combat actions")
    require(bool(opponent_transitions), errors, "P-47N selected no air-combat actions")
    require("turn_fighter" in primary_doctrines, errors,
            f"A6M doctrine was not turn_fighter: {sorted(primary_doctrines)}")
    require("energy_fighter" in opponent_doctrines, errors,
            f"P-47N doctrine was not energy_fighter: {sorted(opponent_doctrines)}")
    require(bool(primary_fires), errors, "A6M never fired at the P-47N")
    require(bool(opponent_fires), errors, "P-47N never fired at the A6M")
    require(min_separation is not None and min_separation >= 8.0, errors,
            f"fighters approached below the hard safety threshold: {min_separation}")
    require(max_separation is not None and max_separation <= 480.0, errors,
            f"fighters separated beyond the combat area: {max_separation}")
    summary_paths = list(args.root.rglob("validation-summary-*.json"))
    summary_path = max(summary_paths, key=lambda path: path.stat().st_mtime) if summary_paths else None
    summary: dict[str, Any] = {}
    if summary_path:
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            summary = {}
    results = summary.get("results") or []
    require(summary.get("state") == "complete", errors,
            "primary post-combat mission summary was not complete")
    require(bool(results) and all(bool(row.get("passed")) for row in results), errors,
            "primary A6M did not return to a passed parked mission")

    result = {
        "scenario": "dogfight_mutual",
        "passed": not errors,
        "errors": errors,
        "metrics": {
            "gradle_status": args.gradle_status,
            "primary_log": str(primary_entry[0]) if primary_entry else None,
            "opponent_log": str(opponent_entry[0]) if opponent_entry else None,
            "start_tick": start_tick,
            "completion_tick": completion_tick,
            "minimum_separation": min_separation,
            "maximum_separation": max_separation,
            "primary_track_ticks": primary_track_ticks,
            "opponent_track_ticks": opponent_track_ticks,
            "primary_combat_ticks": primary_combat_ticks,
            "opponent_combat_ticks": opponent_combat_ticks,
            "primary_actions": primary_actions,
            "opponent_actions": opponent_actions,
            "primary_fire_count": len(primary_fires),
            "opponent_fire_count": len(opponent_fires),
            "primary_combat_frame_count": len(primary_frames),
            "opponent_combat_frame_count": len(opponent_frames),
            "primary_min_speed_bps": primary_min_speed,
            "opponent_min_speed_bps": opponent_min_speed,
            "primary_ground_frames": primary_ground,
            "opponent_ground_frames": opponent_ground,
            "primary_doctrines": sorted(primary_doctrines),
            "opponent_doctrines": sorted(opponent_doctrines),
            "validation_summary": str(summary_path) if summary_path else None,
        },
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
