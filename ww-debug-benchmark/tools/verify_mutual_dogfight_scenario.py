#!/usr/bin/env python3
"""Verify two explicitly hostile autonomous fighters acquire, manoeuvre, fire and separate safely."""

from __future__ import annotations

import argparse
import json
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


def latest_telemetry_session(
        root: Path,
) -> tuple[Path | None, tuple[Path, list[dict[str, Any]]] | None,
           tuple[Path, list[dict[str, Any]]] | None]:
    sessions: list[
        tuple[int, Path, tuple[Path, list[dict[str, Any]]],
              tuple[Path, list[dict[str, Any]]]]
    ] = []
    for aircraft_dir in root.rglob("aircraft"):
        if not aircraft_dir.is_dir():
            continue
        primary_entry = None
        opponent_entry = None
        freshness = 0
        for path in aircraft_dir.glob("*.jsonl"):
            rows = read_jsonl(path)
            name = next(
                (str(row.get("aircraft_name")) for row in rows
                 if row.get("aircraft_name")),
                path.name,
            )
            try:
                freshness = max(freshness, path.stat().st_mtime_ns)
            except OSError:
                pass
            if name.startswith("AUTOPILOT TEST warfare_wings:a6m"):
                primary_entry = (path, rows)
            elif "MUTUAL BLUE P47N" in name:
                opponent_entry = (path, rows)
        if primary_entry is not None and opponent_entry is not None:
            sessions.append((freshness, aircraft_dir.parent,
                             primary_entry, opponent_entry))

    if not sessions:
        return None, None, None
    _, session_path, primary_entry, opponent_entry = max(
        sessions, key=lambda entry: (entry[0], str(entry[1]))
    )
    return session_path, primary_entry, opponent_entry


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--gradle-status", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    telemetry_session, primary_entry, opponent_entry = latest_telemetry_session(args.root)
    primary_rows = primary_entry[1] if primary_entry else []
    opponent_rows = opponent_entry[1] if opponent_entry else []
    primary_uuid = next(
        (str(row.get("aircraft_uuid")) for row in primary_rows
         if row.get("aircraft_uuid")),
        None,
    )

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

    start_tick = min((tick(row) for row in started), default=-1)
    completion_tick = max((tick(row) for row in completed), default=-1)

    def combat_frames(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            row for row in rows if row.get("event") == "frame"
            and start_tick >= 0 and completion_tick >= start_tick
            and start_tick <= tick(row) <= completion_tick
        ]

    primary_frames = combat_frames(primary_rows)
    opponent_frames = combat_frames(opponent_rows)
    primary_speeds = [float(row["speed_bps"]) for row in primary_frames if row.get("speed_bps") is not None]
    opponent_speeds = [float(row["speed_bps"]) for row in opponent_frames if row.get("speed_bps") is not None]
    primary_ground = sum(bool(row.get("on_ground")) for row in primary_frames)
    opponent_ground = sum(bool(row.get("on_ground")) for row in opponent_frames)

    primary_acquisition_reasons = [str(row.get("reason", "")) for row in primary_acquisitions]
    opponent_acquisition_reasons = [str(row.get("reason", "")) for row in opponent_acquisitions]

    errors: list[str] = []
    require(args.gradle_status == 0, errors,
            f"headless GameTest process failed with status {args.gradle_status}")
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
    require(primary_ground == 0, errors,
            f"A6M touched the ground during mutual combat: {primary_ground} frames")
    require(opponent_ground == 0, errors,
            f"P-47N touched the ground during mutual combat: {opponent_ground} frames")
    if primary_speeds:
        require(min(primary_speeds) >= 8.5, errors,
                f"A6M speed became unsafe: {min(primary_speeds):.2f} bps")
    if opponent_speeds:
        require(min(opponent_speeds) >= 8.5, errors,
                f"P-47N speed became unsafe: {min(opponent_speeds):.2f} bps")

    summary_paths = sorted(
        args.root.rglob("validation-summary-*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    summary_path = None
    summary: dict[str, Any] = {}
    for candidate_path in summary_paths:
        try:
            candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        candidate_results = candidate.get("results") or []
        if primary_uuid is not None and not any(
                str(row.get("aircraft_uuid")) == primary_uuid
                for row in candidate_results):
            continue
        summary_path = candidate_path
        summary = candidate
        break
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
            "telemetry_session": str(telemetry_session) if telemetry_session else None,
            "primary_log": str(primary_entry[0]) if primary_entry else None,
            "opponent_log": str(opponent_entry[0]) if opponent_entry else None,
            "primary_uuid": primary_uuid,
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
            "primary_min_speed_bps": min(primary_speeds) if primary_speeds else None,
            "opponent_min_speed_bps": min(opponent_speeds) if opponent_speeds else None,
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
