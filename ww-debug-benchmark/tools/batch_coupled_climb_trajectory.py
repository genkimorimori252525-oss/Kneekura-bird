#!/usr/bin/env python3
"""Run the calibrated P-47N trajectory model across preserved artifacts.

The command recursively discovers paired P-47N/A6M telemetry, removes byte-identical
duplicate trajectories, loads the selected candidate JSON, and requires every unique
trajectory to reach the unchanged attack sector without violating the local
separation, stall, ground-clearance, or pull-out gates.

This remains pre-flight evidence only because the target follows its preserved path;
a new Forge GameTest is authoritative for target reaction, LOS, threats and safety.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import analyze_coupled_climb_trajectory as trajectory


START_EVENTS = {
    "energy_crossing_reentry_start",
    "energy_coupled_climb_start",
}


def event_starts(path: Path) -> list[int]:
    starts: list[int] = []
    with path.open(encoding="utf-8") as handle:
        for raw in handle:
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if row.get("event") in START_EVENTS:
                starts.append(int(row["server_tick"]))
    return starts


def discover(root: Path) -> list[tuple[str, Path, Path, int]]:
    sessions: list[tuple[str, Path, Path, int]] = []
    for aircraft_dir in sorted(root.rglob("aircraft")):
        p47 = sorted(aircraft_dir.glob("warfare_wings-p47n-*.jsonl"))
        a6m = sorted(aircraft_dir.glob("warfare_wings-a6m-*.jsonl"))
        if len(p47) != 1 or len(a6m) != 1:
            continue
        sessions.extend(
            (str(aircraft_dir.parent), p47[0], a6m[0], start_tick)
            for start_tick in event_starts(p47[0])
        )
    return sessions


def digest_pair(p47: Path, target: Path, start_tick: int) -> str:
    digest = hashlib.sha256()
    digest.update(str(start_tick).encode("ascii"))
    for path in (p47, target):
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def simulation_args(p47: Path, target: Path, start_tick: int) -> argparse.Namespace:
    return trajectory.build_parser().parse_args([
        "--p47", str(p47),
        "--target", str(target),
        "--start-tick", str(start_tick),
    ])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    discovered = discover(args.root)
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
            "qualified_for_headless": result["qualified_for_headless"],
            "termination_reason": result["termination_reason"],
            "first_attack": result["first_attack"],
            "minimum_speed_bps": result["minimum_speed_bps"],
            "minimum_distance": result["minimum_distance"],
            "maximum_distance": result["maximum_distance"],
            "minimum_pitch": result["minimum_pitch"],
            "maximum_pitch": result["maximum_pitch"],
            "minimum_estimated_agl": result["minimum_estimated_agl"],
            "minimum_pull_out_margin": result["minimum_pull_out_margin"],
            "initial_engine_power": result["initial_engine_power"],
            "initial_engine_power_source": result["initial_engine_power_source"],
            "samples": result["samples"],
        })

    passes = sum(bool(row["qualified_for_headless"]) for row in rows)
    report = {
        "candidate": trajectory.selected_candidate_defaults(),
        "discovered_sessions": len({session for session, _, _, _ in discovered}),
        "discovered_reentries": len(discovered),
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
            "minimum_estimated_agl": min(
                (row["minimum_estimated_agl"] for row in rows), default=None
            ),
            "minimum_pull_out_margin": min(
                (row["minimum_pull_out_margin"] for row in rows), default=None
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
