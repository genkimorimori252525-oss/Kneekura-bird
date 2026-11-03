#!/usr/bin/env python3
"""Verify one A6M mutual-combat scene; multi-aircraft validation is not supported."""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import uuid
from pathlib import Path
from typing import Any

TEXT = re.compile(r"([a-z_]+)=([^:]+)")
NUMBER = re.compile(r"([a-z_]+)=(-?\d+(?:\.\d+)?)")
ACTION = re.compile(r"(?:^|:)to=([A-Z_]+)")
# Candidate IDs are ResourceLocation.toString() values, with explicit namespace.
ENTITY_ID = re.compile(r"[a-z0-9_.-]+:[a-z0-9/._-]+")


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


def normalized_uuid(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return str(uuid.UUID(value))
    except ValueError:
        return None


def verify_primary_summary(summary: Any, primary_rows: list[dict[str, Any]],
                           started: list[dict[str, Any]], errors: list[str]) -> None:
    if not isinstance(summary, dict):
        errors.append("primary post-combat mission summary is not an object")
        return
    require(summary.get("state") == "complete", errors,
            "primary post-combat mission summary was not complete")
    results = summary.get("results")
    if not isinstance(results, list) or not results or not all(isinstance(row, dict) for row in results):
        errors.append("primary post-combat summary must contain aircraft results")
        return
    # The verifier selects one A6M scene only; it cannot establish evidence
    # for other sequential candidates in an aircraft=all run.
    require(len(results) == 1, errors,
            "mutual verification supports exactly one A6M summary result; aircraft=all is unsupported")
    for field in ("total", "completed"):
        value = summary.get(field)
        require(type(value) is int and value == len(results), errors,
                f"primary post-combat summary {field} does not match result count")

    result_uuids = [normalized_uuid(row.get("aircraft_uuid")) for row in results]
    require(None not in result_uuids and len(set(result_uuids)) == len(result_uuids),
            errors, "post-combat summary aircraft UUIDs must be valid and unique")
    entity_ids = [row.get("entity_id") for row in results]
    valid_ids = all(isinstance(value, str) and ENTITY_ID.fullmatch(value)
                    for value in entity_ids)
    require(bool(valid_ids), errors, "post-combat summary aircraft entity_id is invalid")
    if valid_ids:
        # startAll deduplicates fighter profiles by ResourceLocation; startOne has one result.
        require(len(set(entity_ids)) == len(entity_ids), errors,
                "post-combat summary aircraft entity_ids must be unique")
    for result in results:
        for field, expected in (("passed", True), ("reason", "completed_full_mission"),
                                ("final_phase", "PARKED"),
                                ("last_transition_reason", "complete_stop_stable_for_40_ticks")):
            actual = result.get(field)
            valid = actual is True if field == "passed" else actual == expected
            require(valid, errors, f"post-combat summary {field} is invalid")

    row_uuids = {normalized_uuid(row.get("aircraft_uuid")) for row in primary_rows}
    start_uuids = {normalized_uuid(texts(str(row.get("reason", ""))).get("primary_uuid"))
                   for row in started}
    primary_ids = row_uuids & start_uuids
    primary_id = next(iter(primary_ids)) if len(primary_ids) == 1 else None
    # The scene opponent is a temporary aircraft, discarded before the
    # primary validation run continues; it is not a result candidate.
    opponents: list[str | None] = []
    for row in started:
        reason = row.get("reason")
        fields = [part[len("opponent_uuid="):] for part in reason.split(":")
                  if part.startswith("opponent_uuid=")] if isinstance(reason, str) else []
        opponents.append(normalized_uuid(fields[0]) if len(fields) == 1 else None)
    opponent_id = opponents[0] if len(opponents) == 1 else None
    require(opponent_id is not None and opponent_id != primary_id and opponent_id not in result_uuids,
            errors, "scene opponent UUID must be distinct from all summary aircraft")
    primary_results = [row for row in results
                       if row.get("entity_id") == "warfare_wings:a6m"
                       and normalized_uuid(row.get("aircraft_uuid")) == primary_id]
    require(primary_id is not None and row_uuids == {primary_id} and start_uuids == {primary_id}
            and len(primary_results) == 1, errors,
            "primary A6M summary UUID does not uniquely match the primary log and scene")

    # The validator records success at PARKED, then force-stops the session
    # with validation_aircraft_cleanup; closeAircraft writes session_end last.
    completions = [(i, row) for i, row in enumerate(primary_rows)
                   if row.get("event") == "mutual_dogfight_validation_completed"]
    transitions = [(i, row) for i, row in enumerate(primary_rows)
                   if row.get("event") == "phase_transition"]
    ends = [(i, row) for i, row in enumerate(primary_rows)
            if row.get("event") == "session_end"]
    terminal_ok = False
    if len(completions) == 1 and transitions and len(ends) == 1:
        completion_i, completion = completions[0]
        parked_i, parked = transitions[-1]
        end_i, end = ends[0]
        ticks = [completion.get("server_tick"), parked.get("server_tick"), end.get("server_tick")]
        terminal_ticks = [row.get("server_tick") for row in primary_rows[parked_i:end_i + 1]]
        terminal_ok = (
            completion_i < parked_i < end_i == len(primary_rows) - 1
            and all(type(value) is int and value >= 0 for value in ticks)
            and ticks[0] <= ticks[1] <= ticks[2]
            and all(type(value) is int and value >= 0 for value in terminal_ticks)
            and terminal_ticks == sorted(terminal_ticks)
            and parked.get("phase") == "PARKED"
            and parked.get("reason") == "BRAKE->PARKED:complete_stop_stable_for_40_ticks"
            and end.get("phase") == "PARKED"
            and end.get("reason") == "validation_aircraft_cleanup"
            and all(row.get("phase") != "ABORTED" for row in primary_rows)
            and all(row.get("phase") == "PARKED" for row in primary_rows[parked_i:])
        )
        # BRAKE records the transition and a frame from the same snapshot.
        # Later parked frames, if any, must remain grounded and below the
        # controller's strict 0.25 blocks/second horizontal-speed threshold.
        frames = [row for row in primary_rows[parked_i + 1:end_i] if row.get("event") == "frame"]
        frame_ticks = [row.get("server_tick") for row in frames]
        terminal_ok = terminal_ok and bool(frames) and all(
            type(value) is int and value >= 0 for value in frame_ticks
        ) and frame_ticks[0] == ticks[1] and all(
            ticks[1] <= value <= ticks[2] for value in frame_ticks
        ) and frame_ticks == sorted(frame_ticks) and all(
            row.get("on_ground") is True
            and type(row.get("horizontal_speed_bps")) in (int, float)
            and 0 <= row["horizontal_speed_bps"] < 0.25 for row in frames
        )
    require(terminal_ok, errors,
            "primary post-combat log does not establish parked validation cleanup")


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

    summary_paths = list(args.root.rglob("validation-summary-*.json"))
    summary_path = max(summary_paths, key=lambda path: path.stat().st_mtime) if summary_paths else None
    summary: dict[str, Any] = {}
    if summary_path:
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            summary = {}
    verify_primary_summary(summary, primary_rows, started, errors)

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
