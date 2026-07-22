#!/usr/bin/env python3
"""Evaluate one coupled-climb candidate across preserved mutual-dogfight runs.

The script recursively discovers session directories containing one P-47N JSONL and
one A6M JSONL, starts at the first ``energy_crossing_reentry_start`` event, and calls
``analyze_apex_yaw_replay`` for each pair.

Two results are intentionally reported:

* ``angular_pass`` means the modeled nose reached raw <= 45 deg and lead <= 12 deg.
* ``static_gate_pass`` additionally checks recorded range 24..125 blocks and recorded
  closure -6..28 bps at the same tick.

Recorded positions and velocities come from an older real-physics run, so the static
range/closure gate is diagnostic rather than proof. Only a new Forge GameTest can
qualify the changed controller.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

import analyze_apex_yaw_replay as replay


def event_start(path: Path) -> int | None:
    with path.open(encoding="utf-8") as handle:
        for raw in handle:
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if row.get("event") == "energy_crossing_reentry_start":
                return int(row["server_tick"])
    return None


def discover(root: Path) -> list[tuple[str, Path, Path, int]]:
    sessions: list[tuple[str, Path, Path, int]] = []
    for aircraft_dir in sorted(root.rglob("aircraft")):
        p47 = sorted(aircraft_dir.glob("warfare_wings-p47n-*.jsonl"))
        a6m = sorted(aircraft_dir.glob("warfare_wings-a6m-*.jsonl"))
        if len(p47) != 1 or len(a6m) != 1:
            continue
        start = event_start(p47[0])
        if start is None:
            continue
        sessions.append((str(aircraft_dir.parent), p47[0], a6m[0], start))
    return sessions


def closure_bps(p47: replay.Frame, target: replay.Frame) -> float:
    line = target.position - p47.position
    if line.length() <= 1.0e-9:
        return 0.0
    relative = target.velocity - p47.velocity
    return -relative.scale(20.0).dot(line.normalized())


def qualify(result: dict, p47_frames: dict[int, replay.Frame],
            target_frames: dict[int, replay.Frame]) -> dict:
    first_angular = None
    first_static = None
    minimum_distance = None
    maximum_distance = None

    for row in result["rows"]:
        tick = int(row["tick"])
        p47 = p47_frames.get(tick)
        target = target_frames.get(tick)
        if p47 is None or target is None:
            continue
        distance = (target.position - p47.position).length()
        closure = closure_bps(p47, target)
        minimum_distance = distance if minimum_distance is None else min(minimum_distance, distance)
        maximum_distance = distance if maximum_distance is None else max(maximum_distance, distance)
        angular = row["raw_angle"] <= 45.0 and row["lead_angle"] <= 12.0
        if angular and first_angular is None:
            first_angular = {
                "tick": tick,
                "raw_angle": row["raw_angle"],
                "lead_angle": row["lead_angle"],
                "distance": distance,
                "closure_bps": closure,
            }
        static_gate = angular and 24.0 <= distance <= 125.0 and -6.0 <= closure <= 28.0
        if static_gate and first_static is None:
            first_static = {
                "tick": tick,
                "raw_angle": row["raw_angle"],
                "lead_angle": row["lead_angle"],
                "distance": distance,
                "closure_bps": closure,
            }

    return {
        "angular_pass": first_angular is not None,
        "static_gate_pass": first_static is not None,
        "first_angular": first_angular,
        "first_static_gate": first_static,
        "minimum_raw_angle": result["minimum_raw_angle"],
        "minimum_lead_angle": result["minimum_lead_angle"],
        "minimum_modeled_pitch": result["minimum_pitch"],
        "maximum_modeled_pitch": result["maximum_pitch"],
        "recorded_minimum_distance": minimum_distance,
        "recorded_maximum_distance": maximum_distance,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--root", type=Path, required=True,
                        help="Extracted artifact root containing wwdebug/autopilot sessions")
    result.add_argument("--output", type=Path)
    result.add_argument("--lead-ticks", type=float, default=8.0)
    result.add_argument("--max-ticks", type=int, default=220)
    result.add_argument("--yaw-speed", type=float, default=2.5)
    result.add_argument("--pitch-speed", type=float, default=2.4)
    result.add_argument("--climb-pitch", type=float, default=-30.0)
    result.add_argument("--yaw-trigger-pitch", type=float, default=-8.0)
    result.add_argument("--pivot-complete-heading", type=float, default=35.0)
    result.add_argument("--pivot-divisor", type=float, default=26.0)
    result.add_argument("--capture-pitch-divisor", type=float, default=11.0)
    result.add_argument("--capture-pitch-damping", type=float, default=0.20)
    result.add_argument("--yaw-damping", type=float, default=0.16)
    return result


def main() -> int:
    args = parser().parse_args()
    candidate = replay.Candidate(
        climb_pitch=args.climb_pitch,
        yaw_trigger_pitch=args.yaw_trigger_pitch,
        pivot_complete_heading=args.pivot_complete_heading,
        pivot_divisor=args.pivot_divisor,
        capture_pitch_divisor=args.capture_pitch_divisor,
        capture_pitch_damping=args.capture_pitch_damping,
        yaw_damping=args.yaw_damping,
    )
    sessions = discover(args.root)
    if not sessions:
        raise SystemExit(f"no paired mutual-dogfight telemetry found below {args.root}")

    rows = []
    for name, p47_path, target_path, start_tick in sessions:
        p47_frames = replay.load_frames(p47_path)
        target_frames = replay.load_frames(target_path)
        if start_tick not in p47_frames or start_tick not in target_frames:
            continue
        result = replay.simulate(
            p47_frames,
            target_frames,
            start_tick,
            candidate,
            lead_ticks=args.lead_ticks,
            max_ticks=args.max_ticks,
            yaw_speed=args.yaw_speed,
            pitch_speed=args.pitch_speed,
        )
        rows.append({
            "session": name,
            "start_tick": start_tick,
            **qualify(result, p47_frames, target_frames),
        })

    report = {
        "candidate": asdict(candidate),
        "session_count": len(rows),
        "angular_passes": sum(row["angular_pass"] for row in rows),
        "static_gate_passes": sum(row["static_gate_pass"] for row in rows),
        "warning": "Recorded position/velocity are not resimulated; Forge GameTest remains authoritative.",
        "sessions": rows,
    }
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    return 0 if report["angular_passes"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
