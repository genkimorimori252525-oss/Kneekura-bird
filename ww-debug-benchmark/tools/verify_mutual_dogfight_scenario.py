#!/usr/bin/env python3
"""Verify one A6M mutual-combat scene; multi-aircraft validation is not supported."""

from __future__ import annotations

import argparse
import fnmatch
import json
import math
import os
import re
import stat
import statistics
import sys
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

TEXT = re.compile(r"([a-z_]+)=([^:]+)")
NUMBER = re.compile(r"([a-z_]+)=(-?\d+(?:\.\d+)?)")
ACTION = re.compile(r"(?:^|:)to=([A-Z_]+)")
# Candidate IDs are ResourceLocation.toString() values, with explicit namespace.
ENTITY_ID = re.compile(r"[a-z0-9_.-]+:[a-z0-9/._-]+")


class SummaryDuplicateKeyError(ValueError):
    pass


class SummaryInvalidConstantError(ValueError):
    pass


def reject_summary_constant(value: str) -> None:
    raise SummaryInvalidConstantError(value)


def finite_summary_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("summary number exceeds finite float range")
    return number


def summary_unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SummaryDuplicateKeyError("duplicate JSON object key")
        result[key] = value
    return result


class DuplicateKeyError(ValueError):
    pass


class InvalidConstantError(ValueError):
    pass


class NonFiniteNumberError(ValueError):
    pass


def unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError("duplicate JSON object key")
        result[key] = value
    return result


def reject_json_constant(value: str) -> None:
    raise InvalidConstantError(value)


def finite_json_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise NonFiniteNumberError("JSON number exceeds finite float range")
    return number


def telemetry_paths(root: Path, errors: list[str]):
    """Find candidates without hiding directory scan errors or following recursive symlinks."""
    pending = [root]
    reported: set[str] = set()

    def report(path: str, exc: OSError) -> None:
        if path not in reported:
            errors.append(f"cannot scan telemetry directory {path}: {type(exc).__name__}")
            reported.add(path)

    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as stream:
                entries = list(stream)
        except OSError as exc:
            report(str(directory), exc)
            continue
        for entry in entries:
            try:
                is_real_directory = entry.is_dir(follow_symlinks=False)
                # rglob('aircraft/*.jsonl') follows a symlink for its literal aircraft
                # component, but does not recursively follow unrelated symlink directories.
                if entry.name == "aircraft" and (is_real_directory or entry.is_symlink()):
                    try:
                        with os.scandir(entry.path) as aircraft_entries:
                            candidates = [Path(child.path) for child in aircraft_entries
                                          if fnmatch.fnmatch(child.name, "*.jsonl")]
                    except OSError as exc:
                        report(entry.path, exc)
                    else:
                        yield from candidates
                if is_real_directory:
                    pending.append(Path(entry.path))
            except OSError as exc:
                report(entry.path, exc)


def read_jsonl(path: Path, errors: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    reported: set[str] = set()

    def report_corruption(kind: str, line_number: int) -> None:
        if kind not in reported:
            errors.append(f"{kind} in telemetry log {path} at line {line_number}")
            reported.add(kind)

    try:
        # Surrogate escapes let us reject invalid bytes per line while preserving the previous
        # universal-newline handling for LF, CRLF and CR-delimited historical logs.
        with path.open("r", encoding="utf-8", errors="surrogateescape", newline=None) as stream:
            for line_number, line in enumerate(stream, 1):
                try:
                    line.encode("utf-8")
                except UnicodeEncodeError:
                    report_corruption("invalid UTF-8", line_number)
                    continue
                try:
                    value = json.loads(line, object_pairs_hook=unique_json_object,
                                       parse_constant=reject_json_constant,
                                       parse_float=finite_json_float)
                except json.JSONDecodeError:
                    report_corruption("invalid JSON", line_number)
                    continue
                except DuplicateKeyError:
                    report_corruption("DuplicateKeyError", line_number)
                    continue
                except InvalidConstantError as exc:
                    report_corruption(f"InvalidConstantError {exc}", line_number)
                    continue
                except NonFiniteNumberError:
                    report_corruption("NonFiniteNumberError", line_number)
                    continue
                except ValueError:
                    report_corruption("JSON parser ValueError", line_number)
                    continue
                except RecursionError:
                    report_corruption("JSON parser RecursionError", line_number)
                    continue
                if not isinstance(value, dict):
                    report_corruption("non-object JSON", line_number)
                    continue
                rows.append(value)
    except OSError as exc:
        errors.append(f"cannot read telemetry log {path}: {type(exc).__name__}")
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
    return (min(speeds) if not invalid_speeds else None,
            ground_frames if not invalid_ground else None)


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

    errors: list[str] = []
    logs: list[tuple[str, Path, list[dict[str, Any]]]] = []
    for path in telemetry_paths(args.root, errors):
        rows = read_jsonl(path, errors)
        name = next((str(row.get("aircraft_name")) for row in rows if row.get("aircraft_name")), path.name)
        logs.append((name, path, rows))
    telemetry_complete = not errors

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

    crash_dir = args.root / "crash-reports"
    crash_reports: list[Path] = []
    try:
        # Path.glob() suppresses scandir errors, which can make an unreadable directory
        # indistinguishable from an empty one. Inspect the path without following symlinks.
        crash_mode = os.lstat(crash_dir).st_mode
    except FileNotFoundError:
        crash_mode = None  # A clean run may not create crash-reports at all.
    except OSError as exception:
        errors.append(f"cannot inspect crash reports {crash_dir}: {type(exception).__name__}")
        crash_mode = None
    if crash_mode is not None:
        if not stat.S_ISDIR(crash_mode):
            errors.append(f"cannot inspect crash reports {crash_dir}: not a real directory")
        else:
            try:
                with os.scandir(crash_dir) as entries:
                    for entry in entries:
                        # Treat every case-insensitive .txt entry as a candidate, including
                        # directories and symlinks. Never follow an entry to classify it.
                        if entry.name.casefold().endswith(".txt"):
                            crash_reports.append(crash_dir / entry.name)
            except OSError as exception:
                # Once the path was present, a disappearing or partially read directory is
                # an inspection failure, not evidence that there were no crash reports.
                errors.append(f"cannot inspect crash reports {crash_dir}: {type(exception).__name__}")
            crash_reports.sort()
    require(args.gradle_status == 0, errors,
            f"Gradle GameTest exit code was {args.gradle_status}")
    require(not crash_reports, errors,
            "crash report candidate present: " + ", ".join(str(path) for path in crash_reports))
    require(bool(primary_rows), errors, "primary A6M telemetry was not produced")
    require(bool(opponent_rows), errors, "opposing P-47N telemetry was not produced")
    require(bool(started), errors, "mutual dogfight scene never started")
    require(bool(completed), errors, "mutual dogfight scene never completed")
    if window_valid:
        collision_metrics = collision_separation_evidence(
                primary_rows, opponent_rows, start_tick, completion_tick, errors)
    else:
        collision_metrics = {"collision_observed_minimum": None, "collision_observation_rows": 0}
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
    if primary_ground is not None:
        require(primary_ground == 0, errors,
                f"A6M touched the ground during mutual combat: {primary_ground} frames")
    if opponent_ground is not None:
        require(opponent_ground == 0, errors,
                f"P-47N touched the ground during mutual combat: {opponent_ground} frames")
    if primary_min_speed is not None:
        require(primary_min_speed >= 8.5, errors,
                f"A6M speed became unsafe: {primary_min_speed:.2f} bps")
    if opponent_min_speed is not None:
        require(opponent_min_speed >= 8.5, errors,
                f"P-47N speed became unsafe: {opponent_min_speed:.2f} bps")

    summary_paths = list(args.root.rglob("validation-summary-*.json"))
    summary_path = max(summary_paths, key=lambda path: path.stat().st_mtime) if summary_paths else None
    summary: dict[str, Any] = {}
    if summary_path:
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"),
                                 object_pairs_hook=summary_unique_object,
                                 parse_constant=reject_summary_constant,
                                 parse_float=finite_summary_float)
            if not isinstance(summary, dict):
                raise ValueError("validation summary must be an object")
        except (OSError, UnicodeDecodeError, ValueError, RecursionError) as exc:
            errors.append(f"cannot read validation summary {summary_path}: {type(exc).__name__}")
            summary = {}
    verify_primary_summary(summary, primary_rows, started, errors)

    result = {
        "scenario": "dogfight_mutual",
        "passed": not errors,
        "errors": errors,
        "metrics": {
            "gradle_status": args.gradle_status,
            "telemetry_scan_complete": telemetry_complete,
            "crash_reports": [str(path) for path in crash_reports],
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
    if not telemetry_complete:
        # A failed scan or unreadable row can hide evidence for either aircraft.
        # Do not present partial observations as complete safety measurements.
        for key in ("start_tick", "completion_tick", "minimum_separation", "maximum_separation",
                    "collision_observed_minimum", "collision_observation_rows",
                    "collision_observation_rows_by_aircraft", "other_aircraft_collision_observed_minimum",
                    "primary_track_ticks", "opponent_track_ticks", "primary_combat_ticks",
                    "opponent_combat_ticks", "primary_actions", "opponent_actions",
                    "primary_fire_count", "opponent_fire_count", "primary_combat_frame_count",
                    "opponent_combat_frame_count", "primary_min_speed_bps", "opponent_min_speed_bps",
                    "primary_ground_frames", "opponent_ground_frames", "primary_doctrines", "opponent_doctrines"):
            if key in result["metrics"]:
                result["metrics"][key] = None
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
