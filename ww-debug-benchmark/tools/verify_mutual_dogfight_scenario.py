#!/usr/bin/env python3
"""Verify two explicitly hostile autonomous fighters acquire, manoeuvre, fire and separate safely."""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
import uuid
from decimal import Decimal
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
    except (TypeError, ValueError, OverflowError):
        return -1


def numbers(reason: str) -> dict[str, float]:
    return {name: float(value) for name, value in NUMBER.findall(reason)}


def texts(reason: str) -> dict[str, str]:
    return {name: value for name, value in TEXT.findall(reason)}


def require(condition: bool, errors: list[str], message: str) -> None:
    if not condition:
        errors.append(message)


def reason_fields(reason: str, key: str) -> list[str]:
    result: list[str] = []
    for part in reason.split(":"):
        if "=" in part:
            field, value = part.split("=", 1)
            if field.strip() == key:
                result.append(value.strip())
    return result


def scene_distances(completed: list[dict[str, Any]], errors: list[str]) -> tuple[float | None, float | None]:
    """Read scene extrema rounded to 0.01 block; sparse status rows are not extrema."""
    if len(completed) != 1:
        errors.append("scene must have exactly one completion event for separation evidence")
        return None, None
    completion_tick = completed[0].get("server_tick")
    if type(completion_tick) is not int or completion_tick < 0:
        errors.append("scene completion has no valid integer tick")
    distances: list[float | None] = []
    for name in ("minimum_separation", "maximum_separation"):
        fields = reason_fields(str(completed[0].get("reason", "")), name)
        if len(fields) != 1 or not re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]{1,2})?", fields[0]):
            errors.append(f"scene completion has a missing, ambiguous or invalid rounded {name}")
            distances.append(None)
            continue
        value = float(fields[0])
        if not math.isfinite(value):
            errors.append(f"scene completion {name} is not finite")
            distances.append(None)
            continue
        distances.append(value)
    return distances[0], distances[1]


def collision_separation_evidence(primary: list[dict[str, Any]], opponent: list[dict[str, Any]],
                                  start: int, end: int, errors: list[str]) -> dict[str, Any]:
    """Check rounded, intermittent collision rows; they do not prove continuous separation.

    The producer records center distance using Math.rint(value * 10) / 10. A logged
    8.0 can represent a true distance below 8.0; 8.1 is the first provably safe value.
    A start event and a control adapter may represent the same observation, so counts
    below are log rows rather than independent samples. Both aircraft need at least
    one row: a safe run without an avoidance event on either side is unverified.
    """
    def identity(rows: list[dict[str, Any]], role: str) -> str | None:
        ids: set[str] = set()
        for row in rows:
            try:
                value = row.get("aircraft_uuid")
                if not isinstance(value, str):
                    raise ValueError("missing UUID")
                ids.add(str(uuid.UUID(value)))
            except ValueError:
                errors.append(f"{role} telemetry has an invalid aircraft UUID")
                return None
        if len(ids) != 1:
            errors.append(f"{role} telemetry must identify exactly one aircraft")
            return None
        return next(iter(ids))

    first_id, second_id = identity(primary, "primary"), identity(opponent, "opponent")
    if first_id is None or second_id is None or first_id == second_id:
        if first_id is not None and first_id == second_id:
            errors.append("primary and opponent identify the same aircraft")
        return {"collision_observed_minimum": None, "collision_observation_rows": 0}

    starts = [row for row in primary if row.get("event") == "mutual_dogfight_validation_started"]
    try:
        if len(starts) != 1:
            raise ValueError("ambiguous start")
        start_row = starts[0]
        start_tick = start_row.get("server_tick")
        if type(start_tick) is not int or start_tick < 0:
            raise ValueError("invalid start tick")
        start_reason = str(start_row.get("reason", ""))
        first = reason_fields(start_reason, "primary_uuid")
        second = reason_fields(start_reason, "opponent_uuid")
        if len(first) != 1 or len(second) != 1:
            raise ValueError("missing or duplicate identifiers")
        if str(uuid.UUID(first[0])) != first_id or str(uuid.UUID(second[0])) != second_id:
            raise ValueError("start identifies a different pair")
    except ValueError:
        errors.append("scene start does not uniquely identify the selected aircraft pair")
        return {"collision_observed_minimum": None, "collision_observation_rows": 0}

    pair: list[Decimal] = []
    other: list[Decimal] = []
    counts = {"primary": 0, "opponent": 0}
    invalid_reported: set[str] = set()
    for role, rows, expected in (("primary", primary, second_id), ("opponent", opponent, first_id)):
        for row in rows:
            event = row.get("event")
            reason = str(row.get("reason", ""))
            is_adapter = event == "control_adapter" and (
                    row.get("applied_safety_override") == "collision_avoidance"
                    or reason_fields(reason, "other_uuid") or reason_fields(reason, "current"))
            if event != "collision_avoidance_start" and not is_adapter:
                continue
            when = row.get("server_tick")
            if type(when) is not int or when < 0:
                if role not in invalid_reported:
                    errors.append(f"{role} collision evidence has no valid tick")
                    invalid_reported.add(role)
                continue
            if when < start or when > end:
                continue
            targets, values = reason_fields(reason, "other_uuid"), reason_fields(reason, "current")
            try:
                if len(targets) != 1 or len(values) != 1:
                    raise ValueError("missing or duplicate fields")
                target = str(uuid.UUID(targets[0]))
                if not re.fullmatch(r"(?:0|[1-9][0-9]*)\.[0-9]", values[0]):
                    raise ValueError("distance is not a one-decimal nonnegative value")
                distance = Decimal(values[0])
                if not math.isfinite(float(distance)):
                    raise ValueError("distance is not finite")
            except ValueError:
                if role not in invalid_reported:
                    errors.append(f"{role} collision evidence has an invalid target or current distance")
                    invalid_reported.add(role)
                continue
            if target == (first_id if role == "primary" else second_id):
                if role not in invalid_reported:
                    errors.append(f"{role} collision evidence identifies the aircraft itself")
                    invalid_reported.add(role)
                continue
            if target == expected:
                pair.append(distance)
                counts[role] += 1
            else:
                other.append(distance)

    for role, count in counts.items():
        require(count > 0, errors, f"{role} has no interpretable mutual collision-separation observation")
    if pair:
        require(min(pair) > Decimal("8.0"), errors,
                f"rounded mutual collision observation does not establish 8-block separation: {min(pair)}")
    if other:
        require(min(other) > Decimal("8.0"), errors,
                f"rounded collision observation with another aircraft does not establish 8-block separation: {min(other)}")
    return {
        "collision_observed_minimum": float(min(pair)) if pair else None,
        "collision_observation_rows": len(pair),
        "collision_observation_rows_by_aircraft": counts,
        "other_aircraft_collision_observed_minimum": float(min(other)) if other else None,
        "collision_observation_scope": "intermittent center distances rounded to 0.1 block; missing either aircraft's observations is unverified; not continuous separation",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--gradle-status", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    errors: list[str] = []

    logs: list[tuple[str, Path, list[dict[str, Any]]]] = []
    for path in args.root.rglob("aircraft/*.jsonl"):
        rows = read_jsonl(path)
        name = next((str(row.get("aircraft_name")) for row in rows if row.get("aircraft_name")), path.name)
        logs.append((name, path, rows))

    primary_candidates = [(path, rows) for name, path, rows in logs
                          if name.startswith("AUTOPILOT TEST warfare_wings:a6m")]
    opponent_candidates = [(path, rows) for name, path, rows in logs if "MUTUAL BLUE P47N" in name]
    require(len(primary_candidates) == 1, errors, "primary aircraft log is missing or ambiguous")
    require(len(opponent_candidates) == 1, errors, "opponent aircraft log is missing or ambiguous")
    primary_entry = primary_candidates[0] if primary_candidates else None
    opponent_entry = opponent_candidates[0] if opponent_candidates else None
    primary_rows = primary_entry[1] if primary_entry else []
    opponent_rows = opponent_entry[1] if opponent_entry else []

    # The same UUID under a different name can otherwise hide a second log of the
    # selected aircraft. Unrelated aircraft names/UUIDs do not affect selection.
    for role, entry in (("primary", primary_entry), ("opponent", opponent_entry)):
        if entry is None:
            continue
        path, rows = entry
        selected_ids = {row.get("aircraft_uuid") for row in rows if isinstance(row.get("aircraft_uuid"), str)}
        try:
            selected_ids = {str(uuid.UUID(value)) for value in selected_ids}
        except ValueError:
            continue  # The identity check below reports invalid selected telemetry.
        for _, other_path, other_rows in logs:
            if other_path == path:
                continue
            for row in other_rows:
                try:
                    value = row.get("aircraft_uuid")
                    if isinstance(value, str) and str(uuid.UUID(value)) in selected_ids:
                        errors.append(f"{role} aircraft UUID occurs in more than one telemetry file")
                        break
                except ValueError:
                    continue

    started = [row for row in primary_rows if row.get("event") == "mutual_dogfight_validation_started"]
    completed = [row for row in primary_rows if row.get("event") == "mutual_dogfight_validation_completed"]
    primary_acquisitions = [row for row in primary_rows if row.get("event") == "combat_target_acquired"]
    opponent_acquisitions = [row for row in opponent_rows if row.get("event") == "combat_target_acquired"]
    primary_transitions = [row for row in primary_rows if row.get("event") == "air_combat_action_transition"]
    opponent_transitions = [row for row in opponent_rows if row.get("event") == "air_combat_action_transition"]
    primary_fires = [row for row in primary_rows if row.get("event") == "weapon_fire"]
    opponent_fires = [row for row in opponent_rows if row.get("event") == "weapon_fire"]

    completion_values = numbers(str(completed[-1].get("reason", ""))) if completed else {}
    min_separation, max_separation = scene_distances(completed, errors)
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

    require(bool(primary_rows), errors, "primary A6M telemetry was not produced")
    require(bool(opponent_rows), errors, "opposing P-47N telemetry was not produced")
    require(bool(started), errors, "mutual dogfight scene never started")
    require(bool(completed), errors, "mutual dogfight scene never completed")
    require(0 <= start_tick < completion_tick, errors,
            f"scene window must end after it starts: {start_tick}..{completion_tick}")
    collision_metrics = collision_separation_evidence(
            primary_rows, opponent_rows, start_tick, completion_tick, errors)
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
    # A recorded 8.00 is rounded to 0.01 and can represent a true value just below 8.0.
    # Math.rint rounds the scene extrema to 0.01: 8.00 and 480.00 can hide
    # threshold violations. These are scene-tick measurements, not continuous paths.
    require(min_separation is not None and min_separation > 8.0, errors,
            f"rounded scene minimum does not establish 8-block separation: {min_separation}")
    require(max_separation is not None and max_separation < 480.0, errors,
            f"rounded scene maximum does not establish the 480-block limit: {max_separation}")
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
            **collision_metrics,
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
