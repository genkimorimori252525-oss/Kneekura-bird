#!/usr/bin/env python3
"""Describe one explicit telemetry file without claiming simulation equivalence.

Only sanitized JSON is written to stdout. Inputs are read-only and their exact bytes are hashed;
this tool does not discover files, fill gaps, calculate model errors or decide flight safety.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import uuid

MAX_BYTES = 64 * 1024 * 1024
MAX_LINE = 1024 * 1024
MAX_ROWS = 1_000_000
MAX_TICK = (1 << 63) - 1
MAX_RANGES = 100_000
KNOWN_EVENTS = frozenset({'frame', 'control_adapter', 'session_start', 'session_end', 'phase_transition'})
# A fixed allowlist prevents untrusted field names/values from leaking in public output.
FIELDS = {
    'position': 'vector', 'velocity_bpt': 'vector', 'aircraft_forward': 'vector',
    'desired_direction': 'vector', 'yaw_deg': 'number', 'pitch_deg': 'number', 'roll_deg': 'number',
    'speed_bps': 'number', 'vertical_speed_bps': 'number', 'altitude_above_ground': 'number',
    'on_ground': 'boolean', 'control_x': 'number', 'control_x_logical': 'number',
    'control_y': 'number', 'control_z': 'number', 'engine_target_command': 'number',
    'engine_target_actual': 'number', 'engine_power': 'number', 'fuel_utilization': 'number',
    'mission_ticks': 'integer', 'phase_ticks': 'integer',
}
PROVENANCE = {
    'source_head': 40, 'source_sha256': 64, 'mod_sha256': 64,
    'immersive_aircraft_sha256': 64, 'warfare_wings_sha256': 64,
    'config_sha256': 64, 'profile_sha256': 64, 'model_sha256': 64,
}
REASONS = [
    'fast_simulation_has_no_per_tick_trajectory',
    'fast_simulation_has_no_final_applied_control_trace',
    'real_mod_control_fields_do_not_prove_final_applied_input',
    'model_error_and_scope_have_not_been_measured',
]


class Invalid(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def read_explicit(path):
    # Never follow a final symlink or block on a FIFO. All data and its digest describe the
    # exact bytes read, not a claim that another process kept the file unchanged afterwards.
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    if not hasattr(os, 'O_NOFOLLOW'):
        raise Invalid('nofollow_unavailable')
    try:
        fd = os.open(path, flags)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_BYTES:
                raise Invalid('input_not_regular_or_too_large')
            data = stream.read(MAX_BYTES + 1)
            after = os.fstat(stream.fileno())
    except (OSError, ValueError):
        raise Invalid('input_unreadable') from None
    if len(data) > MAX_BYTES:
        raise Invalid('input_not_regular_or_too_large')
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) or len(data) != after.st_size:
        raise Invalid('input_changed_during_read')
    return data, hashlib.sha256(data).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Invalid('duplicate_json_key')
        result[key] = value
    return result


def finite_tree(value):
    if isinstance(value, str):
        try:
            value.encode('utf-8', errors='strict')
        except UnicodeEncodeError:
            raise Invalid('invalid_unicode') from None
    if isinstance(value, float) and not math.isfinite(value):
        raise Invalid('nonfinite_json_number')
    if isinstance(value, dict):
        for key, item in value.items():
            finite_tree(key)
            finite_tree(item)
    elif isinstance(value, list):
        for item in value:
            finite_tree(item)


def parse_json(raw):
    def bad_constant(_):
        raise Invalid('nonfinite_json_number')
    try:
        parsed = json.loads(raw, object_pairs_hook=unique_object, parse_constant=bad_constant)
        finite_tree(parsed)
        return parsed
    except Invalid:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
        raise Invalid('invalid_json') from None


def parse_provenance(raw):
    value = parse_json(raw)
    if not isinstance(value, dict) or any(key not in PROVENANCE for key in value):
        raise Invalid('invalid_provenance_schema')
    result = {}
    for key, length in PROVENANCE.items():
        item = value.get(key)
        if item is not None and (not isinstance(item, str) or re.fullmatch(r'[0-9a-f]{' + str(length) + '}', item) is None):
            raise Invalid('invalid_provenance_hash')
        result[key] = item
    return result


def digest_text(domain, value):
    return hashlib.sha256((domain + '\0' + value).encode('utf-8')).hexdigest()


def identity(row):
    aircraft = row.get('aircraft_uuid')
    kind = row.get('aircraft_entity_id')
    run = row.get('run_id')
    if not isinstance(aircraft, str) or not isinstance(kind, str) or not kind or not isinstance(run, str) or not run:
        raise Invalid('missing_aircraft_identity')
    try:
        parsed = uuid.UUID(aircraft)
    except (ValueError, AttributeError):
        raise Invalid('invalid_aircraft_uuid') from None
    if str(parsed) != aircraft:
        raise Invalid('invalid_aircraft_uuid')
    return aircraft, kind, run


def tick_value(row):
    tick = row.get('server_tick')
    if type(tick) is not int or tick < 0 or tick > MAX_TICK:
        raise Invalid('invalid_server_tick')
    return tick


def usable(value, kind):
    if kind == 'number':
        if type(value) not in (int, float):
            return False
        try:
            return math.isfinite(float(value))
        except OverflowError:
            return False
    if kind == 'integer':
        return type(value) is int
    if kind == 'boolean':
        return type(value) is bool
    return isinstance(value, dict) and all(usable(value.get(axis), 'number') for axis in ('x', 'y', 'z'))


def ranges(sorted_ticks):
    result = []
    for tick in sorted_ticks:
        if result and tick == result[-1][1] + 1:
            result[-1][1] = tick
        else:
            result.append([tick, tick])
            if len(result) > MAX_RANGES:
                raise Invalid('too_many_tick_ranges')
    return result


def frame_summary(frame_ticks):
    unique = sorted(set(frame_ticks))
    observed = ranges(unique)
    missing = [[left[1] + 1, right[0] - 1] for left, right in zip(observed, observed[1:])]
    return {
        'min': unique[0] if unique else None,
        'max': unique[-1] if unique else None,
        'observed_count': len(frame_ticks),
        'unique_count': len(unique),
        'ranges': observed,
        'missing_ranges': missing,
        'missing_count': sum(end - start + 1 for start, end in missing),
        'outside_observed_range': 'UNKNOWN',
        'duplicate_count': len(frame_ticks) - len(unique),
        'out_of_order_count': sum(b < a for a, b in zip(frame_ticks, frame_ticks[1:])),
    }


def parse_telemetry(raw):
    counts, fields, unknown_fields = Counter(), Counter(), Counter()
    frame_ticks, identities = [], set()
    previous = None
    first_tick = None
    last_tick = None
    backwards_rows = 0
    rows = 0
    malformed_fields = 0
    for line in raw.splitlines():
        rows += 1
        if rows > MAX_ROWS or len(line) > MAX_LINE:
            raise Invalid('telemetry_limits_exceeded')
        row = parse_json(line)
        if not isinstance(row, dict):
            raise Invalid('telemetry_row_not_object')
        identities.add(identity(row))
        tick = tick_value(row)
        first_tick = tick if first_tick is None else min(first_tick, tick)
        last_tick = tick if last_tick is None else max(last_tick, tick)
        if previous is not None and tick < previous:
            backwards_rows += 1
        previous = tick
        event = row.get('event')
        if not isinstance(event, str) or not event:
            raise Invalid('missing_event')
        event_key = event if event in KNOWN_EVENTS else 'other'
        counts[event_key] += 1
        if event == 'frame':
            frame_ticks.append(tick)
            for key, kind in FIELDS.items():
                if key in row:
                    fields[key + ':present'] += 1
                    if usable(row[key], kind):
                        fields[key + ':usable'] += 1
                    else:
                        malformed_fields += 1
            for key in row:
                if key not in FIELDS:
                    unknown_fields['occurrences'] += 1
    if not rows:
        raise Invalid('empty_telemetry')
    if not frame_ticks:
        raise Invalid('no_frame_rows')
    summary = frame_summary(frame_ticks)
    errors = []
    if len(identities) != 1:
        errors.append('multiple_aircraft_or_run_identities')
    if backwards_rows:
        errors.append('row_tick_order_decreased')
    if summary['out_of_order_count']:
        errors.append('frame_tick_order_decreased')
    if summary['duplicate_count']:
        errors.append('duplicate_frame_ticks')
    quality_flags = ['missing_interior_frame_ticks'] if summary['missing_count'] else []
    if malformed_fields:
        errors.append('malformed_known_frame_fields')
    # Do not combine tick/field metrics across distinct aircraft or run identities.
    if len(identities) == 1:
        aircraft, kind, run = next(iter(identities))
        redacted = {'aircraft_uuid_sha256': digest_text('aircraft_uuid', aircraft),
                    'aircraft_type_sha256': digest_text('aircraft_type', kind),
                    'run_id_sha256': digest_text('run_id', run)}
    else:
        redacted, summary, fields, unknown_fields = None, None, Counter(), Counter()
        first_tick, last_tick, backwards_rows, quality_flags = None, None, None, []
        errors = ['multiple_aircraft_or_run_identities']
    return {
        'schema_version': 'UNKNOWN_UNDECLARED_IN_JSONL',
        'event_counts': dict(sorted(counts.items())) if len(identities) == 1 else None,
        'row_count': rows,
        'row_ticks': {'min': first_tick, 'max': last_tick} if first_tick is not None else None,
        'row_tick_order_decreases': backwards_rows,
        'identity_consistent': len(identities) == 1,
        'identity': redacted,
        'frame_ticks': summary,
        'available_frame_fields': {name: {'present': fields[name + ':present'], 'usable': fields[name + ':usable']}
                                   for name in sorted(FIELDS) if fields[name + ':present']},
        'other_frame_field_occurrences': unknown_fields['occurrences'],
        'quality_flags': quality_flags,
        'integrity_errors': errors,
    }


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Invalid('invalid_arguments')


def main(argv=None):
    parser = Parser(description='Build a pseudonymized, read-only comparability manifest.')
    parser.add_argument('--telemetry', required=True)
    parser.add_argument('--provenance', required=True)
    result = {'manifest_schema_version': 1, 'status': 'NOT_COMPARABLE', 'integrity': 'INVALID',
              'integrity_scope': 'STRUCTURE_ONLY_NOT_COMPLETENESS_OR_SAFETY', 'reason_codes': REASONS,
              'input_sha256': {'telemetry': None, 'provenance': None},
              'provenance': None, 'provenance_claims_verified': False, 'frame_ticks': None}
    try:
        args = parser.parse_args(argv)
        log, result['input_sha256']['telemetry'] = read_explicit(Path(args.telemetry))
        source, result['input_sha256']['provenance'] = read_explicit(Path(args.provenance))
        result['provenance'] = parse_provenance(source)
        observed = parse_telemetry(log)
        result.update(observed)
        errors = observed['integrity_errors']
        result['integrity'] = 'INVALID' if errors else 'VALID'
        result['error_codes'] = errors
    except Invalid as error:
        result['error_codes'] = [error.code]
    except (MemoryError, OverflowError, RecursionError):
        result['error_codes'] = ['resource_limit_or_invalid_nesting']
    print(json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False))
    return 0 if result['integrity'] == 'VALID' else 2


if __name__ == '__main__':
    sys.exit(main())
