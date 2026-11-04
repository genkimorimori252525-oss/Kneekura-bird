#!/usr/bin/env python3
"""Check the compiled arbiter's call-site order; this is not runtime proof."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path


CLASS = "com.wwdebug.autopilot.ControlAuthorityArbiter"
DESCRIPTOR = "(Lnet/minecraft/world/entity/Entity;)Lcom/wwdebug/autopilot/ControlAuthorityArbiter$Authority;"
ENTITY = "(Lnet/minecraft/world/entity/Entity;)"
TARGET_HEADER = ("  private static com.wwdebug.autopilot.ControlAuthorityArbiter$Authority "
                 "decide(net.minecraft.world.entity.Entity);")
CALLS = (
    ("player gate", "com/wwdebug/autopilot/MobPilotGate.isPlayerControlled:" + ENTITY + "Z"),
    ("base control", "com/wwdebug/autopilot/AutonomousFlightManager.applyControl:" + ENTITY + "V"),
    ("mutual hold", "com/wwdebug/autopilot/MutualDogfightMissionHoldAdapter.apply:" + ENTITY + "V"),
    ("formation", "com/wwdebug/autopilot/FormationFlightManager.applyControl:" + ENTITY + "Lcom/wwdebug/autopilot/ControlOutcome;"),
    ("collision", "com/wwdebug/autopilot/AirspaceSafetyProbe.collisionRisk:" + ENTITY + "Z"),
)
HEADER = re.compile(r"^  \S.*\);$")
DECIDE = re.compile(r"^  \S.*\sdecide\([^;]*\);$")
CALL = re.compile(r"^\s*(\d+):\s+invokestatic\s+#\d+\s+// Method (\S+)\s*$")
INSTRUCTION = re.compile(r"^\s*(\d+):\s+([a-z][a-z0-9_]*)\b")


def check_listing(text: str) -> list[str]:
    """Return errors without inferring branch behavior or successful writes."""
    lines = text.splitlines()
    if (sum(line == f"public final class {CLASS} {{" for line in lines) != 1
            or not lines or lines[-1] != "}" or sum(line == "}" for line in lines) != 1):
        return ["expected exactly one arbiter class declaration"]
    headers = [i for i, line in enumerate(lines) if HEADER.fullmatch(line)]
    candidates = []
    for number, start in enumerate(headers):
        if not DECIDE.fullmatch(lines[start]):
            continue
        end = headers[number + 1] if number + 1 < len(headers) else len(lines)
        body = lines[start + 1:end]
        descriptors = [line.strip() for line in body if line.strip().startswith("descriptor:")]
        if descriptors == [f"descriptor: {DESCRIPTOR}"]:
            if lines[start] != TARGET_HEADER:
                return ["decide(Entity) declaration does not match the expected private static method"]
            candidates.append(body)
    if len(candidates) != 1:
        return [f"expected one decide(Entity) method with the exact descriptor, found {len(candidates)}"]
    body = candidates[0]
    if sum(line.strip() == "Code:" for line in body) != 1:
        return ["expected one Code block in decide(Entity)"]
    code = body[next(i for i, line in enumerate(body) if line.strip() == "Code:") + 1:]
    instructions = [match for line in code if (match := INSTRUCTION.match(line))]
    offsets = [int(match.group(1)) for match in instructions]
    if (not offsets or offsets[0] != 0
            or any(a >= b for a, b in zip(offsets, offsets[1:]))
            or instructions[-1].group(2) != "areturn"):
        return ["invalid instruction offsets or missing terminal reference return"]
    found: dict[str, list[int]] = {name: [] for name, _ in CALLS}
    for line in code:
        match = CALL.fullmatch(line)
        if match:
            for name, signature in CALLS:
                if match.group(2) == signature:
                    found[name].append(int(match.group(1)))
    errors = [f"{name} ({signature}): expected one invokestatic, found {len(found[name])}"
              for name, signature in CALLS if len(found[name]) != 1]
    if not errors:
        offsets = [found[name][0] for name, _ in CALLS]
        if any(a >= b for a, b in zip(offsets, offsets[1:])):
            errors.append("required calls are not in increasing bytecode order")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--class-file", type=Path, required=True)
    parser.add_argument("--javap", required=True, help="path to JDK 17 javap")
    args = parser.parse_args()
    try:
        version = subprocess.run([args.javap, "-version"], check=True, capture_output=True, text=True, timeout=15).stdout.strip()
        if not re.match(r"^17(?:[.+_-]|$)", version):
            raise ValueError(f"expected JDK 17 javap, got {version!r}")
        class_bytes = args.class_file.read_bytes()
        # Hash and inspect the same byte snapshot even if another process rebuilds
        # the original path while javap is running.
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "ControlAuthorityArbiter.class"
            snapshot.write_bytes(class_bytes)
            result = subprocess.run([args.javap, "-c", "-p", "-s", str(snapshot)],
                                    check=True, capture_output=True, text=True, timeout=15)
        errors = check_listing(result.stdout)
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"passed": False, "errors": [f"could not inspect class: {exc}"]}))
        return 1
    print(json.dumps({"passed": not errors, "errors": errors, "javap_version": version,
                      "class_sha256": hashlib.sha256(class_bytes).hexdigest(),
                      "scope": "static call-site presence and bytecode order only"}, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
