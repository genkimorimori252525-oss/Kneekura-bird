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
# Candidate IDs are ResourceLocation.toString() values, with explicit namespace.
ENTITY_ID = re.compile(r"[a-z0-9_.-]+:[a-z0-9/._-]+")
COMBAT_ACTIONS = {"INTERCEPT", "ATTACK_APPROACH", "FIRING_PASS", "BREAK_AWAY",
                  "EXTEND", "REPOSITION", "DISENGAGE"}
# Must track MutualDogfightValidationManager.COMBAT_WINDOW_TICKS; update both together.
COMBAT_WINDOW_TICKS = 2_000


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


def reason_fields(reason: str, key: str) -> list[str]:
    result: list[str] = []
    for part in reason.split(":"):
        if "=" in part:
            field, value = part.split("=", 1)
            if field.strip() == key:
                result.append(value.strip())
    return result


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


def find_summaries(root: Path, errors: list[str]) -> list[Path]:
    """Inspect the entire supplied artifact tree without silently skipping entries."""
    summaries: list[Path] = []
    pending = [root]
    while pending:
        path = pending.pop()
        try:
            info = path.stat(follow_symlinks=False)
            # Windows junctions and other reparse points may not be POSIX symlinks.
            reparse = bool(getattr(info, "st_file_attributes", 0) & 0x400)
            if stat.S_ISLNK(info.st_mode) or reparse:
                errors.append(f"cannot inspect summary tree link: {path}")
            elif fnmatch.fnmatch(path.name, "validation-summary-*.json"):
                if stat.S_ISREG(info.st_mode):
                    summaries.append(path)
                else:
                    errors.append(f"summary candidate is not a regular file: {path}")
            elif stat.S_ISDIR(info.st_mode):
                with os.scandir(path) as entries:
                    pending.extend(Path(entry.path) for entry in entries)
        except OSError as exception:
            errors.append(f"cannot inspect summary tree {path}: {type(exception).__name__}")
    return summaries


def verify_tick_order(rows: list[dict[str, Any]], role: str, errors: list[str]) -> bool:
    """Validate every selected log row before using ticks to choose a scene window."""
    previous = -1
    for index, row in enumerate(rows, 1):
        current = tick(row)
        if current < 0:
            errors.append(f"{role} telemetry tick must be a nonnegative integer at row {index}")
            return False
        if current < previous:
            errors.append(f"{role} telemetry tick decreased at row {index}: {previous} -> {current}")
            return False
        previous = current
    return True


def completion_metrics(completed: list[dict[str, Any]], errors: list[str]) -> dict[str, float | None]:
    """Decode the completion's exact fields; an ambiguous record is not evidence."""
    counters = ("primary_track_ticks", "opponent_track_ticks",
                "primary_combat_ticks", "opponent_combat_ticks")
    integer_fields = ("age_ticks",) + counters
    distances = ("minimum_separation", "maximum_separation")
    values: dict[str, float | None] = {key: None for key in integer_fields + distances}
    if len(completed) != 1:
        errors.append(f"expected exactly one mutual dogfight completion event; found {len(completed)}")
        return values
    reason = completed[0].get("reason")
    if not isinstance(reason, str):
        errors.append("scene completion reason is missing or invalid")
        return values

    fields: dict[str, list[tuple[str, str]]] = {key: [] for key in values}
    for part in reason.split(":"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        canonical = key.strip()
        if canonical in fields:
            fields[canonical].append((key, value))
    for key in integer_fields:
        matches = fields[key]
        if (len(matches) != 1 or matches[0][0] != key
                or not re.fullmatch(r"(?:0|[1-9][0-9]{0,9})", matches[0][1])):
            errors.append(f"scene completion has missing, ambiguous or invalid integer {key}")
            continue
        value = int(matches[0][1])
        if value > 2_147_483_647:
            errors.append(f"scene completion integer {key} exceeds Java int range")
            continue
        if key == "age_ticks" and value == 0:
            errors.append("scene completion age_ticks must be positive")
            continue
        if key == "age_ticks" and value > COMBAT_WINDOW_TICKS:
            errors.append(f"scene completion age_ticks exceeds combat window {COMBAT_WINDOW_TICKS}")
            continue
        # Keep the existing JSON metrics' float representation after exact integer validation.
        values[key] = float(value)
    age = values["age_ticks"]
    for key in counters:
        if age is None:
            values[key] = None
        elif values[key] is not None and values[key] > age:
            errors.append(f"scene completion {key} exceeds age_ticks")
            values[key] = None
    for key in distances:
        matches = fields[key]
        if (len(matches) != 1 or matches[0][0] != key
                or not re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]{1,2})?", matches[0][1])):
            errors.append(f"scene completion has missing, ambiguous or invalid rounded {key}")
            continue
        value = float(matches[0][1])
        if not math.isfinite(value):
            errors.append(f"scene completion {key} is not finite")
            continue
        values[key] = value
    minimum, maximum = values["minimum_separation"], values["maximum_separation"]
    if minimum is not None and maximum is not None and minimum > maximum:
        errors.append("scene completion minimum_separation exceeds maximum_separation")
        values["minimum_separation"] = values["maximum_separation"] = None
    return values


def interior_frame_coverage(frames: list[dict[str, Any]], label: str,
                            start: int | None, end: int | None, ticks_valid: bool,
                            errors: list[str]) -> tuple[int | None, int | None, bool]:
    """Count observed valid ticks without allocating a potentially huge tick range.

    The initial opponent frame can be a direct fixture call before opening; teardown
    can precede its final tick. Neither boundary is proof of a scheduled entity tick.
    Complete interior samples still do not prove same-tick ordering or continuous safety.
    """
    if start is None or end is None or end <= start or not ticks_valid:
        return None, None, False
    expected = end - start - 1
    if expected == 0:
        errors.append(f"{label} combat interior is empty; frame coverage is unverified")
        return 0, None, False
    ticks: set[int] = set()
    for frame in frames:
        when = frame['server_tick']
        if not start < when < end:
            continue
        speed = frame.get('speed_bps')
        try:
            speed = float(speed) if type(speed) in (int, float) else None
        except (ValueError, OverflowError):
            speed = None
        if speed is not None and math.isfinite(speed) and speed >= 0 and type(frame.get('on_ground')) is bool:
            ticks.add(when)
    missing = expected - len(ticks)
    if missing:
        errors.append(f"{label} combat interior frame coverage is incomplete: {missing} ticks lack valid frames")
    return len(ticks), missing, missing == 0


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
    participant_logs_unambiguous = len(primary_candidates) == 1 and len(opponent_candidates) == 1
    primary_entry = primary_candidates[0] if primary_candidates else None
    opponent_entry = opponent_candidates[0] if opponent_candidates else None
    primary_rows = primary_entry[1] if primary_entry else []
    opponent_rows = opponent_entry[1] if opponent_entry else []
    primary_tick_order_valid = verify_tick_order(primary_rows, "primary", errors)
    opponent_tick_order_valid = verify_tick_order(opponent_rows, "opponent", errors)

    # The same UUID under a different name can otherwise hide a second log of the
    # selected aircraft. Unrelated aircraft names/UUIDs do not affect selection.
    participant_ids: dict[str, str] = {}
    for role, entry in (("primary", primary_entry), ("opponent", opponent_entry)):
        if entry is None:
            participant_logs_unambiguous = False
            continue
        path, rows = entry
        if not rows or any(not isinstance(row.get("aircraft_uuid"), str) for row in rows):
            participant_logs_unambiguous = False
        selected_ids = {row.get("aircraft_uuid") for row in rows if isinstance(row.get("aircraft_uuid"), str)}
        try:
            selected_ids = {str(uuid.UUID(value)) for value in selected_ids}
        except ValueError:
            participant_logs_unambiguous = False
            continue  # The identity check below reports invalid selected telemetry.
        if len(selected_ids) == 1:
            participant_ids[role] = next(iter(selected_ids))
        else:
            participant_logs_unambiguous = False
        for _, other_path, other_rows in logs:
            if other_path == path:
                continue
            for row in other_rows:
                try:
                    value = row.get("aircraft_uuid")
                    if isinstance(value, str) and str(uuid.UUID(value)) in selected_ids:
                        errors.append(f"{role} aircraft UUID occurs in more than one telemetry file")
                        participant_logs_unambiguous = False
                        break
                except ValueError:
                    continue
    if len(participant_ids) != 2 or len(set(participant_ids.values())) != 2:
        participant_logs_unambiguous = False

    started = [row for row in primary_rows if row.get("event") == "mutual_dogfight_validation_started"]
    completed = [row for row in primary_rows if row.get("event") == "mutual_dogfight_validation_completed"]
    primary_acquisitions = [row for row in primary_rows if row.get("event") == "combat_target_acquired"]
    opponent_acquisitions = [row for row in opponent_rows if row.get("event") == "combat_target_acquired"]
    primary_transitions = [row for row in primary_rows if row.get("event") == "air_combat_action_transition"]
    opponent_transitions = [row for row in opponent_rows if row.get("event") == "air_combat_action_transition"]
    primary_fires = [row for row in primary_rows if row.get("event") == "weapon_fire"]
    opponent_fires = [row for row in opponent_rows if row.get("event") == "weapon_fire"]

    completion_values = completion_metrics(completed, errors)
    min_separation = completion_values["minimum_separation"]
    max_separation = completion_values["maximum_separation"]
    primary_track_ticks = completion_values["primary_track_ticks"]
    opponent_track_ticks = completion_values["opponent_track_ticks"]
    primary_combat_ticks = completion_values["primary_combat_ticks"]
    opponent_combat_ticks = completion_values["opponent_combat_ticks"]

    start_tick = boundary_tick(started, "start", errors)
    completion_tick = boundary_tick(completed, "completion", errors)
    window_valid = start_tick is not None and completion_tick is not None and completion_tick > start_tick
    if start_tick is not None and completion_tick is not None and not window_valid:
        errors.append("mutual dogfight completion must follow start")

    # Under the fixed-mod normal tick path, age increases at most once per gameTime.
    # Skipped calls can make age smaller; repeated calls in one gameTime are outside
    # this validation contract and are not prevented by the producer.
    age_ticks = completion_values["age_ticks"]
    age_window_valid = (window_valid and age_ticks is not None
                        and age_ticks <= completion_tick - start_tick)
    if window_valid and age_ticks is not None and not age_window_valid:
        errors.append("scene completion age_ticks exceeds elapsed server ticks")
    scene_pair_matches = (len(started) == 1 and len(participant_ids) == 2
                          and reason_uuid(started[0], "primary_uuid") == participant_ids["primary"]
                          and reason_uuid(started[0], "opponent_uuid") == participant_ids["opponent"])
    pilot_identity_matches = False
    if window_valid and scene_pair_matches:
        primary_pilot = reason_uuid(started[0], "primary_pilot_uuid")
        opponent_pilot = reason_uuid(started[0], "opponent_pilot_uuid")
        ids = (participant_ids["primary"], primary_pilot, participant_ids["opponent"], opponent_pilot)
        if None not in ids and len(set(ids)) == 4:
            pilot_identity_matches = True
            for rows, pilot in ((primary_rows, primary_pilot), (opponent_rows, opponent_pilot)):
                in_window = [row for row in rows if start_tick <= tick(row) <= completion_tick]
                if not in_window or any(normalized_uuid(row.get("pilot_uuid")) != pilot
                                        or row.get("pilot_entity_id") != "minecraft:villager"
                                        for row in in_window):
                    pilot_identity_matches = False
                    break
    # This only establishes that the window can be interpreted from the logs;
    # it is not a verdict on combat, safety, or complete mission evidence.
    scene_window_valid = bool(age_window_valid and telemetry_complete and participant_logs_unambiguous
                              and scene_pair_matches and pilot_identity_matches
                              and primary_tick_order_valid and opponent_tick_order_valid)

    def within_window(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [row for row in rows if window_valid
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
    primary_covered, primary_missing, primary_coverage_valid = interior_frame_coverage(
            primary_frames, "A6M", start_tick, completion_tick, primary_ticks_valid, errors)
    opponent_covered, opponent_missing, opponent_coverage_valid = interior_frame_coverage(
            opponent_frames, "P-47N", start_tick, completion_tick, opponent_ticks_valid, errors)
    primary_min_speed, primary_ground = combat_frame_metrics(primary_frames, "A6M", errors)
    opponent_min_speed, opponent_ground = combat_frame_metrics(opponent_frames, "P-47N", errors)
    # An unplaceable sample could belong to the combat window, so even otherwise valid
    # in-window samples cannot establish a minimum speed or a zero-ground count.
    if not primary_ticks_valid:
        primary_min_speed, primary_ground = None, None
    if not opponent_ticks_valid:
        opponent_min_speed, opponent_ground = None, None

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
    if window_valid:
        verify_participants(started, completed, primary_rows, opponent_rows,
                            primary_acquisitions, opponent_acquisitions,
                            primary_fires, opponent_fires, start_tick, completion_tick, errors)
    require(bool(primary_rows), errors, "primary A6M telemetry was not produced")
    require(bool(opponent_rows), errors, "opposing P-47N telemetry was not produced")
    require(bool(started), errors, "mutual dogfight scene never started")
    require(bool(completed), errors, "mutual dogfight scene never completed")
    if window_valid:
        collision_metrics = collision_separation_evidence(
                primary_rows, opponent_rows, start_tick, completion_tick, errors)
    else:
        collision_metrics = {"collision_observed_minimum": None, "collision_observation_rows": 0}
    require(bool(primary_acquisitions) and all(reason_field(row, "target_faction") == "blue"
                and reason_field(row, "explicit_faction_hostile") == "true"
                for row in primary_acquisitions), errors,
            "A6M acquisitions must identify the blue-faction opponent as explicitly hostile")
    require(bool(opponent_acquisitions) and all(reason_field(row, "target_faction") == "red"
                and reason_field(row, "explicit_faction_hostile") == "true"
                for row in opponent_acquisitions), errors,
            "P-47N acquisitions must identify the red-faction opponent as explicitly hostile")
    require(primary_track_ticks is not None and primary_track_ticks >= 80, errors,
            f"A6M did not track the P-47N long enough: {primary_track_ticks}")
    require(opponent_track_ticks is not None and opponent_track_ticks >= 80, errors,
            f"P-47N did not track the A6M long enough: {opponent_track_ticks}")
    require(primary_combat_ticks is not None and primary_combat_ticks >= 100, errors,
            f"A6M air-combat control was not sustained: {primary_combat_ticks}")
    require(opponent_combat_ticks is not None and opponent_combat_ticks >= 100, errors,
            f"P-47N air-combat control was not sustained: {opponent_combat_ticks}")
    require(bool(primary_actions), errors, "A6M selected no air-combat actions")
    require(bool(opponent_actions), errors, "P-47N selected no air-combat actions")
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
    # Preserve explicit errors for observed unsafe frames, but never present
    # partial combat-window safety samples as complete values for either plane.
    if not (primary_coverage_valid and opponent_coverage_valid):
        primary_min_speed = opponent_min_speed = None
        primary_ground = opponent_ground = None

    summary_paths = find_summaries(args.root, errors)
    require(len(summary_paths) == 1, errors,
            f"expected exactly one validation summary in the artifact tree, found {len(summary_paths)}")
    summary_path = summary_paths[0] if len(summary_paths) == 1 else None
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
            "scene_window_valid": scene_window_valid,
            "crash_reports": [str(path) for path in crash_reports],
            "primary_log": str(primary_entry[0]) if primary_entry else None,
            "opponent_log": str(opponent_entry[0]) if opponent_entry else None,
            "start_tick": start_tick,
            "completion_tick": completion_tick,
            "scene_age_ticks": completion_values["age_ticks"],
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
            "primary_interior_frame_ticks": primary_covered,
            "opponent_interior_frame_ticks": opponent_covered,
            "primary_interior_missing_ticks": primary_missing,
            "opponent_interior_missing_ticks": opponent_missing,
            "primary_min_speed_bps": primary_min_speed,
            "opponent_min_speed_bps": opponent_min_speed,
            "primary_ground_frames": primary_ground,
            "opponent_ground_frames": opponent_ground,
            "primary_doctrines": sorted(primary_doctrines),
            "opponent_doctrines": sorted(opponent_doctrines),
            "validation_summary": str(summary_path) if summary_path else None,
        },
    }
    if not scene_window_valid:
        # Missing rows, bad order, an invalid window or age can hide evidence for either aircraft.
        # Do not present partial observations as complete safety measurements.
        for key in ("start_tick", "completion_tick", "scene_age_ticks", "minimum_separation", "maximum_separation",
                    "primary_interior_frame_ticks", "opponent_interior_frame_ticks",
                    "primary_interior_missing_ticks", "opponent_interior_missing_ticks",
                    "collision_observed_minimum", "collision_observation_rows",
                    "collision_observation_rows_by_aircraft", "other_aircraft_collision_observed_minimum",
                    "primary_track_ticks", "opponent_track_ticks", "primary_combat_ticks",
                    "opponent_combat_ticks", "primary_actions", "opponent_actions",
                    "primary_fire_count", "opponent_fire_count", "primary_combat_frame_count",
                    "opponent_combat_frame_count", "primary_min_speed_bps", "opponent_min_speed_bps",
                    "primary_ground_frames", "opponent_ground_frames", "primary_doctrines", "opponent_doctrines"):
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
