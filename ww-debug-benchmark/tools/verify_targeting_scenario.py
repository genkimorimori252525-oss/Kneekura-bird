#!/usr/bin/env python3
"""Verify that combat awareness selects a hostile and ignores neutral entities without firing."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable


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
    losses = [row for row in rows if row.get("event") == "combat_target_lost"]
    fire_events = [row for row in rows if row.get("event") == "weapon_fire"]
    reasons = [str(row.get("reason", "")).lower() for row in acquisitions]

    errors: list[str] = []
    require(bool(rows), errors, "no autonomous-flight telemetry was produced")
    require(bool(acquisitions), errors, "no hostile target was acquired")
    require(any("zombie" in reason for reason in reasons), errors,
            "the hostile zombie was not selected")
    require(not any("villager" in reason for reason in reasons), errors,
            "a neutral villager was incorrectly selected")
    require(not any("player" in reason for reason in reasons), errors,
            "a player was incorrectly selected")
    require(not fire_events, errors,
            "target-awareness validation fired without an installed test weapon")

    result = {
        "scenario": "targeting",
        "passed": not errors,
        "errors": errors,
        "metrics": {
            "gradle_status": args.gradle_status,
            "telemetry_log": str(log_path) if log_path else None,
            "acquisition_count": len(acquisitions),
            "loss_count": len(losses),
            "acquisition_reasons": reasons,
            "fire_event_count": len(fire_events),
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
