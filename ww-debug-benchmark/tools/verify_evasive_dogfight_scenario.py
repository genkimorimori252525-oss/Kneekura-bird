#!/usr/bin/env python3
"""Verify lead pursuit and guarded fire against a reversing evasive target."""

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
    started = [row for row in rows if row.get("event") == "evasive_dogfight_validation_started"]
    completed = [row for row in rows if row.get("event") == "evasive_dogfight_validation_completed"]
    target_statuses = [row for row in rows if row.get("event") == "evasive_dogfight_validation_target_status"]
    reversals = [row for row in rows if row.get("event") == "evasive_dogfight_validation_maneuver_reversal"]
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

    status_values = [numbers(str(row.get("reason", ""))) for row in statuses]
    lead_seconds = [value["lead_seconds"] for value in status_values if "lead_seconds" in value]
    doctrines = {
        value["doctrine"]
        for row in statuses + transitions
        if "doctrine" in (value := texts(str(row.get("reason", ""))))
    }
    track_values = [numbers(str(row.get("reason", ""))) for row in target_statuses]
    cross_tracks = [value["cross_track"] for value in track_values if "cross_track" in value]
    downranges = [value["downrange"] for value in track_values if "downrange" in value]
    headings = [value["heading_offset_deg"] for value in track_values if "heading_offset_deg" in value]
    reversal_counts = [value["reversals"] for value in track_values if "reversals" in value]
    target_motion = max(downranges) - min(downranges) if len(downranges) >= 2 else 0.0
    cross_track_span = max(cross_tracks) - min(cross_tracks) if len(cross_tracks) >= 2 else 0.0

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
    require(bool(started), errors, "evasive target was never injected")
    require(bool(completed), errors, "evasive combat window never completed")
    require(len(reversals) >= 4 or max(reversal_counts, default=0.0) >= 4.0, errors,
            f"target did not reverse often enough: events={len(reversals)}")
    require(max((abs(value) for value in headings), default=0.0) >= 20.0, errors,
            "target heading deviation never reached a meaningful evasive angle")
    require(cross_track_span >= 18.0, errors,
            f"target weave was too narrow: {cross_track_span:.2f} blocks")
    require(target_motion >= 180.0, errors,
            f"evasive target did not move far enough downrange: {target_motion:.2f} blocks")
    require("turn_fighter" in doctrines, errors,
            f"A6M did not report turn-fighter doctrine: {sorted(doctrines)}")
    require(any(action in distinct for action in ("INTERCEPT", "ATTACK_APPROACH", "FIRING_PASS")),
            errors, "no pursuit action was selected")
    require(bool(fires), errors, "no guarded machine-gun fire occurred against the evasive target")
    require(any(value >= 0.20 for value in lead_seconds), errors,
            "no meaningful positive lead was maintained against the evasive target")
    require(bool(clears), errors, "combat action did not clear after the evasive target left")
    require(1 <= len(action_rows) <= 30, errors,
            f"action transition count was unrealistic: {len(action_rows)}")
    if dwell_ticks:
        require(statistics.median(dwell_ticks) >= 7.0, errors,
                f"median action dwell was too short: {statistics.median(dwell_ticks):.1f} ticks")
    require(ground_frames == 0, errors,
            f"aircraft touched the ground during evasive combat: {ground_frames} frames")
    if speeds:
        require(min(speeds) >= 8.5, errors,
                f"evasive combat speed fell dangerously low: {min(speeds):.2f} bps")

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
            "aircraft did not return to a passed parked mission after evasive combat")

    result = {
        "scenario": "dogfight_evasive",
        "passed": not errors,
        "errors": errors,
        "metrics": {
            "gradle_status": args.gradle_status,
            "telemetry_log": str(log_path) if log_path else None,
            "start_tick": start_tick,
            "completion_tick": completion_tick,
            "target_motion_downrange": target_motion,
            "target_cross_track_span": cross_track_span,
            "target_heading_abs_max": max((abs(value) for value in headings), default=None),
            "target_reversal_count": max(reversal_counts, default=len(reversals)),
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
