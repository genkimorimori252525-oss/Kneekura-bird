#!/usr/bin/env python3
"""Verify two explicitly hostile autonomous fighters acquire, manoeuvre, fire and separate safely."""

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
COMBAT_ACTIONS = {"INTERCEPT", "ATTACK_APPROACH", "FIRING_PASS", "BREAK_AWAY",
                  "EXTEND", "REPOSITION", "DISENGAGE"}


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
    value = row.get("server_tick")
    return value if type(value) is int and value >= 0 else -1


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


def reason_field(row: dict[str, Any], field: str) -> str | None:
    """Read one unambiguous field from the colon-delimited event reason."""
    reason = row.get("reason")
    if not isinstance(reason, str):
        return None
    values = []
    for part in reason.split(":"):
        key, sep, value = part.partition("=")
        if sep and key.strip() == field:
            if key != field:
                return None
            values.append(value)
    return values[0] if len(values) == 1 else None


def reason_uuid(row: dict[str, Any], field: str) -> str | None:
    return normalized_uuid(reason_field(row, field))


def combat_transitions(rows: list[dict[str, Any]], doctrine: str) -> list[str]:
    """Accept only a unique valid action paired with the expected doctrine on one row."""
    actions: list[str] = []
    for row in rows:
        action = reason_field(row, "to")
        if reason_field(row, "doctrine") == doctrine and action in COMBAT_ACTIONS:
            actions.append(action)
    return actions


def verify_participants(started: list[dict[str, Any]], completed: list[dict[str, Any]],
                        primary_rows: list[dict[str, Any]], opponent_rows: list[dict[str, Any]],
                        primary_acquisitions: list[dict[str, Any]],
                        opponent_acquisitions: list[dict[str, Any]],
                        primary_fires: list[dict[str, Any]], opponent_fires: list[dict[str, Any]],
                        start_tick: int, completion_tick: int, errors: list[str]) -> None:
    for label, rows in (("primary", primary_rows), ("opponent", opponent_rows)):
        require(all(tick(row) >= 0 for row in rows), errors,
                f"{label} telemetry must have nonnegative integer server ticks")
    if len(started) != 1 or len(completed) != 1 or start_tick < 0 or completion_tick <= start_tick:
        errors.append("mutual dogfight must have one ordered start and completion")
        return
    fields = ("primary_uuid", "primary_pilot_uuid", "opponent_uuid", "opponent_pilot_uuid")
    ids = [reason_uuid(started[0], field) for field in fields]
    if None in ids or len(set(ids)) != 4:
        errors.append("mutual dogfight start must identify four distinct participant UUIDs")
        return
    primary_id, primary_pilot, opponent_id, opponent_pilot = ids

    for label, rows, aircraft_id, pilot_id in (
            ("primary", primary_rows, primary_id, primary_pilot),
            ("opponent", opponent_rows, opponent_id, opponent_pilot)):
        in_window = [row for row in rows if start_tick <= tick(row) <= completion_tick]
        require(bool(in_window) and all(
            normalized_uuid(row.get("aircraft_uuid")) == aircraft_id
            and normalized_uuid(row.get("pilot_uuid")) == pilot_id for row in in_window),
            errors, f"{label} combat-window log does not match the scene aircraft and pilot")
        # This verifier is for the fixed GameTest fixture, which creates both
        # pilots as villagers. The registry ID only describes recorded rows;
        # it does not establish pilot identity or input safety during gaps.
        require(bool(in_window) and all(row.get("pilot_entity_id") == "minecraft:villager"
                                        for row in in_window), errors,
                f"{label} combat-window log must identify the fixed villager pilot")

    for label, rows, field, expected in (
            ("primary acquisition", primary_acquisitions, "uuid", opponent_pilot),
            ("opponent acquisition", opponent_acquisitions, "uuid", primary_pilot),
            ("primary fire", primary_fires, "target_uuid", opponent_pilot),
            ("opponent fire", opponent_fires, "target_uuid", primary_pilot)):
        require(bool(rows) and all(reason_uuid(row, field) == expected for row in rows),
                errors, f"{label} must target the opposing pilot in the combat window")

    # The per-aircraft logger appends synchronously and awareness runs before
    # weapons. Same-tick acquisition therefore counts only if logged first.
    # A target acquired solely before the scenario is insufficient evidence.
    for label, rows, expected in (("primary", primary_rows, opponent_pilot),
                                  ("opponent", opponent_rows, primary_pilot)):
        acquisition_tick: int | None = None
        last_event_tick = start_tick
        for row in rows:
            row_tick = tick(row)
            if not start_tick <= row_tick <= completion_tick:
                continue
            event = row.get("event")
            if event not in ("combat_target_acquired", "combat_target_lost", "weapon_fire"):
                continue
            require(row_tick >= last_event_tick, errors,
                    f"{label} acquisition, loss and fire ticks must be ordered in the log")
            last_event_tick = row_tick
            if event == "combat_target_acquired":
                acquisition_tick = row_tick if reason_uuid(row, "uuid") == expected else None
            elif event == "combat_target_lost":
                acquisition_tick = None
            elif event == "weapon_fire":
                require(acquisition_tick is not None and acquisition_tick <= row_tick, errors,
                        f"{label} fired without prior in-window acquisition of the opposing pilot")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--gradle-status", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    logs: list[tuple[str, Path, list[dict[str, Any]]]] = []
    for path in args.root.rglob("aircraft/*.jsonl"):
        rows = read_jsonl(path)
        name = next((str(row.get("aircraft_name")) for row in rows if row.get("aircraft_name")), path.name)
        logs.append((name, path, rows))

    primary_candidates = [(path, rows) for name, path, rows in logs
                          if name.startswith("AUTOPILOT TEST warfare_wings:a6m")]
    opponent_candidates = [(path, rows) for name, path, rows in logs
                           if "MUTUAL BLUE P47N" in name]
    primary_entry = primary_candidates[0] if len(primary_candidates) == 1 else None
    opponent_entry = opponent_candidates[0] if len(opponent_candidates) == 1 else None
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

    start_tick = min((tick(row) for row in started), default=-1)
    completion_tick = max((tick(row) for row in completed), default=-1)

    def within_window(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [row for row in rows if start_tick >= 0 and completion_tick >= start_tick
                and start_tick <= tick(row) <= completion_tick]

    primary_acquisitions = within_window(primary_acquisitions)
    opponent_acquisitions = within_window(opponent_acquisitions)
    primary_fires = within_window(primary_fires)
    opponent_fires = within_window(opponent_fires)
    primary_transitions = within_window(primary_transitions)
    opponent_transitions = within_window(opponent_transitions)

    primary_actions = combat_transitions(primary_transitions, "turn_fighter")
    opponent_actions = combat_transitions(opponent_transitions, "energy_fighter")
    primary_doctrines = {"turn_fighter"} if primary_actions else set()
    opponent_doctrines = {"energy_fighter"} if opponent_actions else set()

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

    errors: list[str] = []
    require(len(primary_candidates) == 1, errors, "primary A6M log must be unambiguous")
    require(len(opponent_candidates) == 1, errors, "opposing P-47N log must be unambiguous")
    verify_participants(started, completed, primary_rows, opponent_rows,
                        primary_acquisitions, opponent_acquisitions,
                        primary_fires, opponent_fires, start_tick, completion_tick, errors)
    require(bool(primary_rows), errors, "primary A6M telemetry was not produced")
    require(bool(opponent_rows), errors, "opposing P-47N telemetry was not produced")
    require(bool(started), errors, "mutual dogfight scene never started")
    require(bool(completed), errors, "mutual dogfight scene never completed")
    require(bool(primary_acquisitions) and all(reason_field(row, "target_faction") == "blue"
                and reason_field(row, "explicit_faction_hostile") == "true"
                for row in primary_acquisitions), errors,
            "A6M acquisitions must identify the blue-faction opponent as explicitly hostile")
    require(bool(opponent_acquisitions) and all(reason_field(row, "target_faction") == "red"
                and reason_field(row, "explicit_faction_hostile") == "true"
                for row in opponent_acquisitions), errors,
            "P-47N acquisitions must identify the red-faction opponent as explicitly hostile")
    require(primary_track_ticks >= 80, errors,
            f"A6M did not track the P-47N long enough: {primary_track_ticks}")
    require(opponent_track_ticks >= 80, errors,
            f"P-47N did not track the A6M long enough: {opponent_track_ticks}")
    require(primary_combat_ticks >= 100, errors,
            f"A6M air-combat control was not sustained: {primary_combat_ticks}")
    require(opponent_combat_ticks >= 100, errors,
            f"P-47N air-combat control was not sustained: {opponent_combat_ticks}")
    require(bool(primary_actions), errors, "A6M selected no air-combat actions")
    require(bool(opponent_actions), errors, "P-47N selected no air-combat actions")
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
