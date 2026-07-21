#!/usr/bin/env python3
"""Inspect a mod JAR for weapon, targeting and ammunition API candidates.

The script first searches class names and constant-pool UTF-8 bytes for combat-related terms, then
runs javap only on matching classes. This keeps the inventory deterministic and reasonably small
while avoiding guesses about a source-unavailable runtime mod.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

KEYWORDS = (
    "weapon", "gun", "cannon", "ammo", "ammunition", "gunpowder", "bullet", "projectile",
    "shoot", "shot", "fire", "attack", "target", "reload", "cooldown",
    "missile", "rocket", "bomb", "torpedo", "trigger", "magazine",
)

MEMBER_PATTERN = re.compile(
    r"^\s*(?:public|protected|private).*?(?:"
    + "|".join(re.escape(keyword) for keyword in KEYWORDS)
    + r").*?[;{]\s*$",
    re.IGNORECASE,
)


def class_name(entry: str) -> str:
    return entry[:-6].replace("/", ".")


def relevant_bytes(payload: bytes) -> list[str]:
    lowered = payload.lower()
    return [keyword for keyword in KEYWORDS if keyword.encode("ascii") in lowered]


def javap(jar: Path, name: str) -> tuple[int, str, str]:
    process = subprocess.run(
        ["javap", "-p", "-c", "-constants", "-classpath", str(jar), name],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=30,
    )
    return process.returncode, process.stdout, process.stderr


def filtered_members(output: str) -> list[str]:
    result: list[str] = []
    for line in output.splitlines():
        if MEMBER_PATTERN.match(line):
            result.append(line.strip())
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jar", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--text-output", type=Path, required=True)
    parser.add_argument("--maximum-classes", type=int, default=240)
    args = parser.parse_args()

    if not args.jar.is_file():
        print(f"ERROR: JAR not found: {args.jar}", file=sys.stderr)
        return 2

    candidates: list[dict[str, Any]] = []
    with zipfile.ZipFile(args.jar) as archive:
        for entry in archive.namelist():
            if not entry.endswith(".class") or entry.startswith("META-INF/"):
                continue
            name = class_name(entry)
            name_terms = [keyword for keyword in KEYWORDS if keyword in name.lower()]
            try:
                payload = archive.read(entry)
            except KeyError:
                continue
            byte_terms = relevant_bytes(payload)
            terms = sorted(set(name_terms + byte_terms))
            if terms:
                candidates.append({"class_name": name, "matched_terms": terms})

    candidates.sort(key=lambda value: (
        -len(value["matched_terms"]),
        0 if any(keyword in value["class_name"].lower() for keyword in KEYWORDS) else 1,
        value["class_name"],
    ))
    original_candidate_count = len(candidates)
    truncated = original_candidate_count > args.maximum_classes
    candidates = candidates[:args.maximum_classes]

    classes: list[dict[str, Any]] = []
    text_parts: list[str] = []
    for index, candidate in enumerate(candidates, 1):
        name = candidate["class_name"]
        code, stdout, stderr = javap(args.jar, name)
        members = filtered_members(stdout)
        record = {
            "class_name": name,
            "matched_terms": candidate["matched_terms"],
            "javap_exit_code": code,
            "relevant_members": members,
            "javap_output": stdout,
            "javap_error": stderr.strip(),
        }
        classes.append(record)
        text_parts.extend([
            f"## {index}. {name}",
            "matched: " + ", ".join(candidate["matched_terms"]),
            "relevant members:",
            *(f"  {member}" for member in members),
            "",
            stdout.strip(),
            "",
        ])

    summary = {
        "jar": str(args.jar),
        "keywords": list(KEYWORDS),
        "candidate_count_before_limit": original_candidate_count,
        "candidate_count": len(classes),
        "truncated": truncated,
        "classes_with_relevant_members": sum(bool(value["relevant_members"]) for value in classes),
        "classes": classes,
    }

    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.text_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    args.text_output.write_text("\n".join(text_parts), encoding="utf-8")

    print(json.dumps({
        "candidate_count": len(classes),
        "classes_with_relevant_members": summary["classes_with_relevant_members"],
        "truncated": truncated,
        "json_output": str(args.json_output),
        "text_output": str(args.text_output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
