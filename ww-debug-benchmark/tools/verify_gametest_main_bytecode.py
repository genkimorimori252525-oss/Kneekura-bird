#!/usr/bin/env python3
"""Inspect a mapped Main.class call-site sequence; this is not runtime proof."""

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path


DESCRIPTOR = (
    "(ZLjoptsimple/OptionSet;Ljoptsimple/OptionSpec;"
    "Lnet/minecraft/world/level/storage/LevelStorageSource$LevelStorageAccess;"
    "Lnet/minecraft/server/packs/repository/PackRepository;Lnet/minecraft/server/WorldStem;"
    "Lnet/minecraft/server/dedicated/DedicatedServerSettings;Lnet/minecraft/server/Services;"
    "Ljoptsimple/OptionSpec;Ljoptsimple/OptionSpec;Ljoptsimple/OptionSpec;"
    "Ljoptsimple/OptionSpec;Ljoptsimple/OptionSpec;Ljoptsimple/OptionSpec;"
    "Ljava/lang/Thread;)Lnet/minecraft/server/MinecraftServer;"
)
CALLS = (
    ("register", "invokestatic", "net/minecraftforge/gametest/ForgeGameTestHooks.registerGametests", "()V"),
    ("get all", "invokestatic", "net/minecraft/gametest/framework/GameTestRegistry.getAllTestFunctions", "()Ljava/util/Collection;"),
    ("group", "invokestatic", "net/minecraft/gametest/framework/GameTestRunner.groupTestsIntoBatches", "(Ljava/util/Collection;)Ljava/util/Collection;"),
    ("server constructor", "invokespecial", 'net/minecraft/gametest/framework/GameTestServer."<init>"',
     "(Ljava/lang/Thread;Lnet/minecraft/world/level/storage/LevelStorageSource$LevelStorageAccess;"
     "Lnet/minecraft/server/packs/repository/PackRepository;Lnet/minecraft/server/WorldStem;"
     "Ljava/util/Collection;Lnet/minecraft/core/BlockPos;)V"),
)
HEADER = re.compile(r"^  \S.*\);$")
TARGET = re.compile(r"^  private static net\.minecraft\.server\.MinecraftServer lambda\$main\$4\(.*\);$")
INSTRUCTION = re.compile(r"^\s*(\d+):\s+([a-z][a-z0-9_]*)\b")
CALL = re.compile(r"^\s*(\d+):\s+(invoke\w+)\s+#\d+(?:,\s*\d+)?\s+// (?:InterfaceMethod|Method) (\S+):(\S+)\s*$")


def check_listing(text: str) -> list[str]:
    """Check one method's static call sites, not control flow or values."""
    lines = text.splitlines()
    if (sum(line == "public class net.minecraft.server.Main {" for line in lines) != 1
            or not lines or lines[-1] != "}" or sum(line == "}" for line in lines) != 1):
        return ["expected exactly one net.minecraft.server.Main declaration"]
    headers = [i for i, line in enumerate(lines) if HEADER.fullmatch(line)]
    named = [i for i in headers if re.search(r"\slambda\$main\$4\(", lines[i])]
    if len(named) != 1 or not TARGET.fullmatch(lines[named[0]]):
        return ["expected one private static lambda$main$4 method"]
    start = named[0]
    end = next((i for i in headers if i > start), len(lines))
    body = lines[start + 1:end]
    if [line.strip() for line in body if line.strip().startswith("descriptor:")] != [f"descriptor: {DESCRIPTOR}"]:
        return ["unexpected lambda$main$4 descriptor"]
    if sum(line.strip() == "Code:" for line in body) != 1:
        return ["expected one Code block"]
    code = body[next(i for i, line in enumerate(body) if line.strip() == "Code:") + 1:]
    instructions = [match for line in code if (match := INSTRUCTION.match(line))]
    offsets = [int(match.group(1)) for match in instructions]
    if (not offsets or offsets[0] != 0 or any(a >= b for a, b in zip(offsets, offsets[1:]))
            or instructions[-1].group(2) != "areturn"):
        return ["invalid instruction offsets or missing terminal reference return"]
    parsed = [match for line in code if (match := CALL.fullmatch(line))]
    positions = []
    errors = []
    for label, opcode, owner_name, descriptor in CALLS:
        matches = [match for match in parsed if match.group(3) == owner_name]
        if len(matches) != 1 or matches[0].group(2) != opcode or matches[0].group(4) != descriptor:
            errors.append(f"{label}: expected exactly one {opcode} with the fixed descriptor")
        else:
            positions.append(int(matches[0].group(1)))
    if not errors and any(a >= b for a, b in zip(positions, positions[1:])):
        errors.append("required call sites are not in increasing bytecode order")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--class-file", type=Path, required=True)
    parser.add_argument("--javap", required=True, help="JDK 17 javap path")
    args = parser.parse_args()
    try:
        version = subprocess.run([args.javap, "-version"], check=True, capture_output=True,
                                 text=True, timeout=15).stdout.strip()
        if not re.match(r"^17(?:[.+_-]|$)", version):
            raise ValueError(f"expected JDK 17 javap, got {version!r}")
        class_bytes = args.class_file.read_bytes()
        with tempfile.TemporaryDirectory(prefix="gametest-main-class-") as directory:
            snapshot = Path(directory) / "Main.class"
            snapshot.write_bytes(class_bytes)
            result = subprocess.run([args.javap, "-c", "-p", "-s", str(snapshot)], check=True,
                                    capture_output=True, text=True, timeout=15)
        errors = check_listing(result.stdout)
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"passed": False, "errors": [f"could not inspect class: {exc}"]}))
        return 1
    print(json.dumps({"passed": not errors, "errors": errors, "javap_version": version,
                      "class_sha256": hashlib.sha256(class_bytes).hexdigest(),
                      "scope": "static call-site counts, descriptors and order only"}, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
