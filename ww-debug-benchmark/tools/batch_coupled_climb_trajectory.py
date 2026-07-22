#!/usr/bin/env python3
"""Run the calibrated P-47N trajectory model across preserved artifacts.

The command recursively discovers paired P-47N/A6M telemetry, removes byte-identical
duplicate trajectories, loads the selected candidate JSON, and requires every unique
trajectory to reach the unchanged angle/range/closure attack sector.

This remains pre-flight evidence only because the target follows its preserved path;
a new Forge GameTest is authoritative for target reaction, LOS, threats and safety.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import analyze_coupled_climb_trajectory as trajectory
import batch_apex_yaw_replay as discovery


def digest_pair(p47: Path, target: Path, start_tick: int) -> str:
    digest = hashlib.sha256()
    digest.update(str(start_tick).encode("ascii"))
    for path in (p47, target):
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def simulation_args(p47: Path, target: Path, start_tick: int) -> SimpleNamespace:
    selected = trajectory.selected_candidate_defaults()
    return SimpleNamespace(
        p47=p47,
        target=target,
        start_tick=start_tick,
        output=None,
        max_ticks=390,
        lead_ticks=selected["lead_ticks"],
        climb_pitch=selected["climb_pitch"],
        yaw_trigger_pitch=selected["yaw_trigger_pitch"],
        pivot_complete_heading=selected["pivot_complete_heading"],
        pivot_divisor=selected["pivot_divisor"],
        capture_pitch_divisor=selected["capture_pitch_divisor"],
        capture_pitch_damping=selected["capture_pitch_damping"],
        yaw_damping=selected["yaw_damping"],
        engine_speed=0.102,
        lift=0.165,
        friction=0.013,
        glide_factor=0.055,
        horizontal_decay=0.97,
        vertical_decay=0.97,
        yaw_speed=2.5,
        pitch_speed=2.4,
        engine_reaction_steps=100.0,
        cruise_speed=33.6741875662,
        stall_guard_speed=10.1662137203,
        recorded_engine_power=1.0,
        initial_engine_power=None,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    discovered = discovery.discover(args.root)
    if not discovered:
        raise SystemExit(f"no paired mutual-dogfight telemetry found below {args.root}")

    seen: set[str] = set()
    rows: list[dict] = []
    duplicates: list[dict] = []
    for session, p47, target, start_tick in discovered:
        digest = digest_pair(p47, target, start_tick)
        if digest in seen:
            duplicates.append({"session": session, "start_tick": start_tick, "digest": digest})
            continue
        seen.add(digest)
        result = trajectory.simulate(simulation_args(p47, target, start_tick))
        rows.append({
            "session": session,
            "start_tick": start_tick,
            "digest": digest,
            "modeled_attack": result["modeled_attack"],
            "first_attack": result["first_attack"],
            "minimum_speed_bps": result["minimum_speed_bps"],
            "minimum_distance": result["minimum_distance"],
            "maximum_distance": result["maximum_distance"],
            "minimum_pitch": result["minimum_pitch"],
            "maximum_pitch": result["maximum_pitch"],
            "initial_engine_power": result["initial_engine_power"],
            "initial_engine_power_source": result["initial_engine_power_source"],
            "samples": result["samples"],
        })

    passes = sum(bool(row["modeled_attack"]) for row in rows)
    report = {
        "candidate": trajectory.selected_candidate_defaults(),
        "discovered_sessions": len(discovered),
        "unique_trajectories": len(rows),
        "duplicate_trajectories": duplicates,
        "passes": passes,
        "all_unique_passed": passes == len(rows),
        "aggregate": {
            "minimum_speed_bps": min(
                (row["minimum_speed_bps"] for row in rows), default=None
            ),
            "minimum_separation_blocks": min(
                (row["minimum_distance"] for row in rows), default=None
            ),
            "maximum_separation_blocks": max(
                (row["maximum_distance"] for row in rows), default=None
            ),
        },
        "warning": (
            "Pre-flight only: target response, LOS, terrain, collision and threat "
            "arbitration require the real Forge GameTest."
        ),
        "trajectories": rows,
    }
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    return 0 if report["all_unique_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
