#!/usr/bin/env python3
"""Verify an energy fighter fires, breaks, extends/repositions, and returns safely."""

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
    started = [row for row in rows if row.get("event") == "energy_dogfight_validation_started"]
    completed = [row for row in rows if row.get("event") == "energy_dogfight_validation_completed"]
    target_statuses = [row for row in rows if row.get("event") == "energy_dogfight_validation_target_status"]
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

    status_actions: list[str] = []
    status_values: list[dict[str, float]] = []
    doctrines: set[str] = set()
    for row in statuses + transitions:
        reason = str(row.get("reason", ""))
        values = texts(reason)
        if "doctrine" in values:
            doctrines.add(values["doctrine"])
    for row in statuses:
        reason = str(row.get("reason", ""))
        match = STATUS_ACTION.search(reason)
        if match:
            status_actions.append(match.group(1))
            status_values.append(numbers(reason))

    recovery_samples = sum(action in {"EXTEND", "REPOSITION"} for action in status_actions)
    energy_ratios = [value["energy_ratio"] for value in status_values if "energy_ratio" in value]
    lead_seconds = [value["lead_seconds"] for value in status_values if "lead_seconds" in value]
    downranges = [
        value["downrange"]
        for row in target_statuses
        if "downrange" in (value := numbers(str(row.get("reason", ""))))
    ]
    target_motion = max(downranges) - min(downranges) if len(downranges) >= 2 else 0.0

    fire_ticks = [tick(row) for row in fires if tick(row) >= 0]
    break_ticks = [value for value, action in action_rows if action == "BREAK_AWAY" and value >= 0]
    recovery_ticks = [
        value for value, action in action_rows
        if action in {"EXTEND", "REPOSITION"} and value >= 0
    ]
    broke_after_fire = bool(fire_ticks and any(value > min(fire_ticks) for value in break_ticks))
    recovered_after_break = bool(break_ticks and any(value > min(break_ticks) for value in recovery_ticks))

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
    require(bool(started), errors, "energy-fighter target was never injected")
    require(bool(completed), errors, "energy-fighter combat window never completed")
    require(target_motion >= 80.0, errors,
            f"energy target did not actually move far enough: {target_motion:.2f} blocks")
    require("energy_fighter" in doctrines, errors,
            f"P-47N did not report energy-fighter doctrine: {sorted(doctrines)}")
    require("FIRING_PASS" in distinct, errors, "no energy-fighter firing pass was selected")
    require(bool(fires), errors, "energy fighter never fired during the pass")
    require("BREAK_AWAY" in distinct and broke_after_fire, errors,
            "energy fighter did not break away after firing")
    require(any(action in distinct for action in ("EXTEND", "REPOSITION")), errors,
            "energy fighter never extended or repositioned after the pass")
    require(recovered_after_break, errors,
            "extension or reposition did not occur after the break-away")
    require(recovery_samples >= 2, errors,
            f"energy-recovery action was not sustained: {recovery_samples} status samples")
    require(any(value > 0.05 for value in lead_seconds), errors,
            "no positive projectile lead time was recorded")
    require(bool(clears), errors, "combat action did not clear after the target left")
    require(3 <= len(action_rows) <= 24, errors,
            f"action transition count was unrealistic: {len(action_rows)}")
    if dwell_ticks:
        require(statistics.median(dwell_ticks) >= 8.0, errors,
                f"median action dwell was too short: {statistics.median(dwell_ticks):.1f} ticks")
    require(ground_frames == 0, errors,
            f"P-47N touched the ground during energy combat: {ground_frames} frames")
    if speeds:
        require(min(speeds) >= 8.5, errors,
                f"energy combat speed fell dangerously low: {min(speeds):.2f} bps")

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
            "P-47N did not return to a passed parked mission after combat")

    result = {
        "scenario": "dogfight_energy",
        "passed": not errors,
        "errors": errors,
        "metrics": {
            "gradle_status": args.gradle_status,
            "telemetry_log": str(log_path) if log_path else None,
            "start_tick": start_tick,
            "completion_tick": completion_tick,
            "target_downrange_motion": target_motion,
            "actions": actions,
            "distinct_actions": sorted(distinct),
            "transition_count": len(action_rows),
            "median_dwell_ticks": statistics.median(dwell_ticks) if dwell_ticks else None,
            "fire_count": len(fires),
            "broke_after_fire": broke_after_fire,
            "recovered_after_break": recovered_after_break,
            "recovery_status_samples": recovery_samples,
            "lead_seconds_max": max(lead_seconds) if lead_seconds else None,
            "energy_ratio_min": min(energy_ratios) if energy_ratios else None,
            "energy_ratio_max": max(energy_ratios) if energy_ratios else None,
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
