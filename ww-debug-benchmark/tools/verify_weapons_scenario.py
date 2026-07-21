#!/usr/bin/env python3
"""Verify friendly-fire inhibition, burst firing and ammunition consumption."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

NUMBER = re.compile(r"([a-z_]+)=(-?\d+(?:\.\d+)?)")


def latest(paths: Iterable[Path]) -> Path | None:
    candidates = [path for path in paths if path.is_file()]
    return max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None


def read_jsonl(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
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


def values(reason: str) -> dict[str, float]:
    return {name: float(value) for name, value in NUMBER.findall(reason)}


def require(condition: bool, errors: list[str], message: str) -> None:
    if not condition:
        errors.append(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--gradle-status", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    log_path = latest(args.root.rglob("aircraft/*.jsonl"))
    rows = read_jsonl(log_path)
    acquisitions = [row for row in rows if row.get("event") == "combat_target_acquired"]
    inhibits = [row for row in rows if row.get("event") == "weapon_fire_inhibited"]
    clears = [row for row in rows if row.get("event") == "friendly_fire_corridor_cleared"]
    fires = [row for row in rows if row.get("event") == "weapon_fire"]
    burst_starts = [row for row in rows if row.get("event") == "weapon_burst_start"]
    burst_ends = [row for row in rows if row.get("event") == "weapon_burst_end"]

    errors: list[str] = []
    reasons = [str(row.get("reason", "")).lower() for row in acquisitions]
    require(bool(rows), errors, "no autonomous-flight telemetry was produced")
    require(any("zombie" in reason for reason in reasons), errors,
            "hostile zombie was not selected")
    require(not any("villager" in reason for reason in reasons), errors,
            "neutral villager was selected as the target")
    require(any("friendly_fire_corridor_blocked_by" in str(row.get("reason", ""))
                for row in inhibits), errors,
            "friendly-fire corridor never inhibited the weapon")
    require(bool(clears), errors, "friendly-fire corridor was never cleared")
    require(bool(fires), errors, "machine gun never fired after the corridor cleared")
    require(bool(burst_starts), errors, "no weapon burst was started")
    require(bool(burst_ends), errors, "no complete short burst was recorded")

    clear_tick = min((tick(row) for row in clears), default=-1)
    fire_ticks = [tick(row) for row in fires]
    if clear_tick >= 0 and fire_ticks:
        require(all(value >= clear_tick for value in fire_ticks), errors,
                "weapon fired before the neutral entity cleared the corridor")

    parsed = [values(str(row.get("reason", ""))) for row in fires]
    reserve_decreased = any(
        value.get("reserve_after", 0) < value.get("reserve_before", 0)
        for value in parsed
    )
    loaded_decreased = any(
        value.get("loaded_after", 0) < value.get("loaded_before", 0)
        for value in parsed
    )
    weapons_fired = sum(int(value.get("weapons_fired", 0)) for value in parsed)
    require(reserve_decreased or loaded_decreased, errors,
            "weapon firing did not consume reserve or loaded ammunition")
    require(weapons_fired > 0, errors, "weapon fire records reported zero fired mounts")

    result = {
        "scenario": "weapons",
        "passed": not errors,
        "errors": errors,
        "metrics": {
            "gradle_status": args.gradle_status,
            "telemetry_log": str(log_path) if log_path else None,
            "acquisition_count": len(acquisitions),
            "inhibit_count": len(inhibits),
            "corridor_clear_tick": clear_tick,
            "fire_count": len(fires),
            "fire_ticks": fire_ticks,
            "burst_start_count": len(burst_starts),
            "burst_end_count": len(burst_ends),
            "weapons_fired_total": weapons_fired,
            "reserve_decreased": reserve_decreased,
            "loaded_ammo_decreased": loaded_decreased,
            "fire_reasons": [row.get("reason") for row in fires],
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
