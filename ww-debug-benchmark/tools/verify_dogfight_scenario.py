#!/usr/bin/env python3
"""Verify finite moving-target combat, guarded fire, safe pursuit or break-away, and recovery."""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any, Iterable

ACTION = re.compile(r"(?:^|:)to=([A-Z_]+)")
STATUS_ACTION = re.compile(r"(?:^|:)action=([A-Z_]+)")
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
    started = [row for row in rows if row.get("event") == "dogfight_validation_started"]
    completed = [row for row in rows if row.get("event") == "dogfight_validation_completed"]
    target_statuses = [row for row in rows if row.get("event") == "dogfight_validation_target_status"]
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

    status_samples: list[tuple[str, dict[str, float]]] = []
    for row in statuses:
        reason = str(row.get("reason", ""))
        match = STATUS_ACTION.search(reason)
        if match:
            status_samples.append((match.group(1), numbers(reason)))
    tail_samples = [
        values for action, values in status_samples
        if action == "FIRING_PASS"
        and 24.0 <= values.get("distance", -1.0) <= 125.0
        and abs(values.get("closure", 999.0)) <= 10.0
    ]
    tail_distances = [values["distance"] for values in tail_samples if "distance" in values]
    tail_closures = [values["closure"] for values in tail_samples if "closure" in values]
    sustained_tail_chase = len(tail_samples) >= 6 and len(fires) >= 4

    lead_seconds = [
        value["lead_seconds"]
        for row in statuses
        if "lead_seconds" in (value := numbers(str(row.get("reason", ""))))
    ]
    downranges = [
        value["downrange"]
        for row in target_statuses
        if "downrange" in (value := numbers(str(row.get("reason", ""))))
    ]
    target_motion = max(downranges) - min(downranges) if len(downranges) >= 2 else 0.0

    start_tick = min((tick(row) for row in started), default=-1)
    completion_tick = max((tick(row) for row in completed), default=-1)
    combat_frames = [
        row for row in frames
        if start_tick >= 0 and completion_tick >= start_tick
        and start_tick <= tick(row) <= completion_tick
    ]
    speeds = []
    ground_frames = 0
    for frame in combat_frames:
        try:
            speeds.append(float(frame.get("speed_bps")))
        except (TypeError, ValueError):
            pass
        if bool(frame.get("on_ground")):
            ground_frames += 1

    completed_attack_cycle = (
        "BREAK_AWAY" in distinct
        and any(action in distinct for action in ("EXTEND", "REPOSITION"))
    )

    errors: list[str] = []
    require(bool(rows), errors, "no autonomous-flight telemetry was produced")
    require(bool(started), errors, "moving dogfight target was never injected")
    require(bool(completed), errors, "dogfight validation window never completed")
    require(target_motion >= 100.0, errors,
            f"straight target did not actually move far enough: {target_motion:.2f} blocks")
    require(any(action in distinct for action in ("INTERCEPT", "ATTACK_APPROACH", "FIRING_PASS")),
            errors, "no pursuit or firing action was selected")
    require("FIRING_PASS" in distinct, errors, "no firing-pass action was selected")
    require(completed_attack_cycle or sustained_tail_chase, errors,
            "neither a break-away/reposition cycle nor a stable sustained tail chase occurred")
    require(bool(fires), errors, "no guarded machine-gun fire occurred during the dogfight")
    require(any(value > 0.05 for value in lead_seconds), errors,
            "no positive projectile lead time was recorded")
    require(bool(clears), errors, "combat action did not clear after the target left")
    require(1 <= len(action_rows) <= 24, errors,
            f"action transition count was unrealistic: {len(action_rows)}")
    if dwell_ticks:
        require(statistics.median(dwell_ticks) >= 8.0, errors,
                f"median action dwell was too short: {statistics.median(dwell_ticks):.1f} ticks")
    require(ground_frames == 0, errors,
            f"aircraft touched the ground during combat: {ground_frames} frames")
    if speeds:
        require(min(speeds) >= 8.5, errors,
                f"combat speed fell dangerously low: {min(speeds):.2f} bps")

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
            "aircraft did not return to a passed parked mission after combat")

    engagement_mode = "attack_cycle" if completed_attack_cycle else (
        "sustained_tail_chase" if sustained_tail_chase else "unqualified"
    )
    result = {
        "scenario": "dogfight",
        "passed": not errors,
        "errors": errors,
        "metrics": {
            "gradle_status": args.gradle_status,
            "telemetry_log": str(log_path) if log_path else None,
            "start_tick": start_tick,
            "completion_tick": completion_tick,
            "target_downrange_motion": target_motion,
            "engagement_mode": engagement_mode,
            "actions": actions,
            "distinct_actions": sorted(distinct),
            "transition_count": len(action_rows),
            "median_dwell_ticks": statistics.median(dwell_ticks) if dwell_ticks else None,
            "fire_count": len(fires),
            "lead_seconds_max": max(lead_seconds) if lead_seconds else None,
            "tail_sample_count": len(tail_samples),
            "tail_distance_median": statistics.median(tail_distances) if tail_distances else None,
            "tail_closure_abs_median": statistics.median(
                [abs(value) for value in tail_closures]) if tail_closures else None,
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
