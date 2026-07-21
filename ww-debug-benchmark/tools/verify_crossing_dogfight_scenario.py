#!/usr/bin/env python3
"""Verify a high-aspect crossing-target lead intercept, firing pass, break and mission recovery."""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any, Iterable

ACTION = re.compile(r"(?:^|:)to=([A-Z_]+)")
TEXT = re.compile(r"([a-z_]+)=([^:]+)")
NUMBER = re.compile(r"([a-z_]+)=(-?\d+(?:\.\d+)?)")


def latest(paths: Iterable[Path]) -> Path | None:
    candidates = [path for path in paths if path.is_file()]
    return max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None


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


def tick(row: dict[str, Any]) -> int:
    try:
        return int(row.get("server_tick", -1))
    except (TypeError, ValueError):
        return -1


def numbers(reason: str) -> dict[str, float]:
    return {name: float(value) for name, value in NUMBER.findall(reason)}


def texts(reason: str) -> dict[str, str]:
    return {name: value for name, value in TEXT.findall(reason)}


def require(condition: bool, errors: list[str], message: str) -> None:
    if not condition:
        errors.append(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--gradle-status", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    log_path = latest(args.root.rglob("aircraft/*.jsonl"))
    rows = read_jsonl(log_path)
    started = [row for row in rows if row.get("event") == "crossing_dogfight_validation_started"]
    completed = [row for row in rows if row.get("event") == "crossing_dogfight_validation_completed"]
    target_statuses = [
        row for row in rows if row.get("event") == "crossing_dogfight_validation_target_status"
    ]
    transitions = [row for row in rows if row.get("event") == "air_combat_action_transition"]
    statuses = [row for row in rows if row.get("event") == "air_combat_status"]
    fires = [row for row in rows if row.get("event") == "weapon_fire"]
    clears = [row for row in rows if row.get("event") == "air_combat_action_clear"]
    frames = [row for row in rows if row.get("event") == "frame"]

    action_rows: list[tuple[int, str]] = []
    for row in transitions:
        match = ACTION.search(str(row.get("reason", "")))
        if match:
            action_rows.append((tick(row), match.group(1)))
    actions = [action for _, action in action_rows]
    distinct = set(actions)
    transition_ticks = [value for value, _ in action_rows if value >= 0]
    dwell_ticks = [later - earlier for earlier, later in zip(transition_ticks, transition_ticks[1:])]

    start_values = numbers(str(started[0].get("reason", ""))) if started else {}
    crossing_angle = start_values.get("crossing_angle_deg")
    cross_tracks = [
        value["cross_track"]
        for row in target_statuses
        if "cross_track" in (value := numbers(str(row.get("reason", ""))))
    ]
    lead_seconds = [
        value["lead_seconds"]
        for row in statuses
        if "lead_seconds" in (value := numbers(str(row.get("reason", ""))))
    ]
    doctrines = {
        value["doctrine"]
        for row in statuses + transitions
        if "doctrine" in (value := texts(str(row.get("reason", ""))))
    }

    start_tick = min((tick(row) for row in started), default=-1)
    completion_tick = max((tick(row) for row in completed), default=-1)
    combat_frames = [
        row for row in frames
        if start_tick >= 0 and completion_tick >= start_tick
        and start_tick <= tick(row) <= completion_tick
    ]
    speeds: list[float] = []
    ground_frames = 0
    for frame in combat_frames:
        try:
            speeds.append(float(frame.get("speed_bps")))
        except (TypeError, ValueError):
            pass
        if bool(frame.get("on_ground")):
            ground_frames += 1

    errors: list[str] = []
    require(bool(rows), errors, "no autonomous-flight telemetry was produced")
    require(bool(started), errors, "crossing target was never injected")
    require(bool(completed), errors, "crossing-target validation window never completed")
    require(crossing_angle is not None and crossing_angle >= 55.0, errors,
            f"target crossing angle was too shallow: {crossing_angle}")
    require(bool(cross_tracks), errors, "no crossing-target track telemetry was recorded")
    if cross_tracks:
        require(min(cross_tracks) <= -15.0, errors,
                f"target did not begin clearly left of the flight path: {min(cross_tracks):.2f}")
        require(max(cross_tracks) >= 12.0, errors,
                f"target never crossed through to the right side: {max(cross_tracks):.2f}")
    require(any(action in distinct for action in ("INTERCEPT", "ATTACK_APPROACH")), errors,
            "no intercept or attack-approach action was selected")
    require("FIRING_PASS" in distinct, errors, "no firing-pass action was selected")
    require("BREAK_AWAY" in distinct, errors, "no post-pass break-away action was selected")
    require(bool(fires), errors, "no guarded machine-gun fire occurred against the crossing target")
    require(any(value >= 0.25 for value in lead_seconds), errors,
            "crossing engagement never required a meaningful positive lead time")
    require("turn_fighter" in doctrines, errors,
            f"A6M dogfight did not report turn-fighter doctrine: {sorted(doctrines)}")
    require(bool(clears), errors, "combat action did not clear after the crossing target left")
    require(3 <= len(action_rows) <= 22, errors,
            f"action transition count was unrealistic: {len(action_rows)}")
    if dwell_ticks:
        require(statistics.median(dwell_ticks) >= 8.0, errors,
                f"median action dwell was too short: {statistics.median(dwell_ticks):.1f} ticks")
    require(ground_frames == 0, errors,
            f"aircraft touched the ground during crossing combat: {ground_frames} frames")
    if speeds:
        require(min(speeds) >= 8.5, errors,
                f"crossing combat speed fell dangerously low: {min(speeds):.2f} bps")

    summary_path = latest(args.root.rglob("validation-summary-*.json"))
    summary: dict[str, Any] = {}
    if summary_path:
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            summary = {}
    results = summary.get("results") or []
    require(summary.get("state") == "complete", errors,
            "full post-combat mission summary was not complete")
    require(bool(results) and all(bool(row.get("passed")) for row in results), errors,
            "aircraft did not return to a passed parked mission after crossing combat")

    result = {
        "scenario": "dogfight_crossing",
        "passed": not errors,
        "errors": errors,
        "metrics": {
            "gradle_status": args.gradle_status,
            "telemetry_log": str(log_path) if log_path else None,
            "start_tick": start_tick,
            "completion_tick": completion_tick,
            "crossing_angle_deg": crossing_angle,
            "cross_track_min": min(cross_tracks) if cross_tracks else None,
            "cross_track_max": max(cross_tracks) if cross_tracks else None,
            "actions": actions,
            "distinct_actions": sorted(distinct),
            "transition_count": len(action_rows),
            "median_dwell_ticks": statistics.median(dwell_ticks) if dwell_ticks else None,
            "fire_count": len(fires),
            "lead_seconds_max": max(lead_seconds) if lead_seconds else None,
            "doctrines": sorted(doctrines),
            "combat_min_speed_bps": min(speeds) if speeds else None,
            "combat_ground_frames": ground_frames,
            "combat_clear_count": len(clears),
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
