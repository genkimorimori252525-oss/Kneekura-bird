#!/usr/bin/env python3
"""Inspect mapped GameTest function call sites; not runtime or data-flow proof."""

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path


REGISTRY = "net.minecraft.gametest.framework.GameTestRegistry"
FUNCTION = "net.minecraft.gametest.framework.TestFunction"
REG_DESC = "(Ljava/lang/reflect/Method;)Lnet/minecraft/gametest/framework/TestFunction;"
CTOR_DESC = ("(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;"
             "Lnet/minecraft/world/level/block/Rotation;IJZIILjava/util/function/Consumer;)V")
RUN_DESC = "(Lnet/minecraft/gametest/framework/GameTestHelper;)V"
HEADER = re.compile(r"^  \S.*\);$")
INSTRUCTION = re.compile(r"^\s*(\d+):\s+([a-z][a-z0-9_]*)\b")
REFERENCE = re.compile(r"^\s*(\d+):\s+(\w+)\s+#\d+(?:,\s*\d+)?\s+// (Method|InterfaceMethod|Field) (\S+):(\S+)\s*$")


def _methods(text: str, classname: str, selector, descriptor: str, terminal: str):
    lines = text.splitlines()
    if (sum(line == f"public class {classname} {{" for line in lines) != 1
            or not lines or lines[-1] != "}" or sum(line == "}" for line in lines) != 1):
        return None, [f"unexpected or truncated class declaration: {classname}"]
    headers = [i for i, line in enumerate(lines) if HEADER.fullmatch(line)]
    matches = []
    for start in headers:
        if not selector(lines[start]):
            continue
        end = next((i for i in headers if i > start), len(lines))
        body = lines[start + 1:end]
        descriptors = [line.strip() for line in body if line.strip().startswith("descriptor:")]
        if descriptors == [f"descriptor: {descriptor}"]:
            matches.append(body)
    if len(matches) != 1:
        return None, [f"expected exactly one selected method with descriptor {descriptor}"]
    body = matches[0]
    if sum(line.strip() == "Code:" for line in body) != 1:
        return None, ["expected one Code block"]
    code = body[next(i for i, line in enumerate(body) if line.strip() == "Code:") + 1:]
    instructions = [m for line in code if (m := INSTRUCTION.match(line))]
    offsets = [int(m.group(1)) for m in instructions]
    if (not offsets or offsets[0] != 0 or any(a >= b for a, b in zip(offsets, offsets[1:]))
            or instructions[-1].group(2) != terminal):
        return None, ["invalid instruction offsets or terminal opcode"]
    return [m for line in code if (m := REFERENCE.fullmatch(line))], []


def _check_refs(refs, requirements):
    errors, positions = [], []
    for label, opcode, kind, name, descriptor in requirements:
        # Count every reference to this owner/name, including wrong opcode or descriptor.
        found = [m for m in refs if m.group(4) == name]
        if (len(found) != 1 or found[0].group(2) != opcode or found[0].group(3) != kind
                or found[0].group(5) != descriptor):
            errors.append(f"{label}: expected one {opcode} {kind} with fixed descriptor")
        else:
            positions.append(int(found[0].group(1)))
    if not errors and any(a >= b for a, b in zip(positions, positions[1:])):
        errors.append("required references are not in increasing bytecode order")
    return errors


def check_registry_listing(text: str) -> list[str]:
    refs, errors = _methods(text, REGISTRY,
        lambda line: line == f"  private static {FUNCTION} turnMethodIntoTestFunction(java.lang.reflect.Method);",
        REG_DESC, "areturn")
    if errors:
        return errors
    return _check_refs(refs, (
        ("consumer conversion", "invokestatic", "Method", "turnMethodIntoConsumer",
         "(Ljava/lang/reflect/Method;)Ljava/util/function/Consumer;"),
        ("function constructor", "invokespecial", "Method",
         'net/minecraft/gametest/framework/TestFunction."<init>"', CTOR_DESC),
    ))


def check_function_listing(text: str) -> list[str]:
    lines = text.splitlines()
    field_lines = [line for line in lines if re.fullmatch(r"  .*\sfunction;", line)]
    if field_lines != ["  private final java.util.function.Consumer<net.minecraft.gametest.framework.GameTestHelper> function;"]:
        return ["expected one private final consumer field named function"]
    field_index = lines.index(field_lines[0])
    if field_index + 1 >= len(lines) or lines[field_index + 1].strip() != "descriptor: Ljava/util/function/Consumer;":
        return ["unexpected function field descriptor"]
    constructor, errors = _methods(text, FUNCTION,
        lambda line: line.startswith(f"  public {FUNCTION}("), CTOR_DESC, "return")
    if errors:
        return errors
    errors = _check_refs(constructor, (("function assignment", "putfield", "Field", "function",
                                       "Ljava/util/function/Consumer;"),))
    run, run_errors = _methods(text, FUNCTION,
        lambda line: line == "  public void run(net.minecraft.gametest.framework.GameTestHelper);",
        RUN_DESC, "return")
    if run_errors:
        return errors + run_errors
    return errors + _check_refs(run, (
        ("function read", "getfield", "Field", "function", "Ljava/util/function/Consumer;"),
        ("consumer invocation", "invokeinterface", "InterfaceMethod", "java/util/function/Consumer.accept",
         "(Ljava/lang/Object;)V"),
    ))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry-class", type=Path, required=True)
    parser.add_argument("--function-class", type=Path, required=True)
    parser.add_argument("--javap", required=True, help="path to trusted JDK 17 javap")
    args = parser.parse_args()
    result = {"passed": False, "scope": "static reference counts, descriptors and order only"}
    try:
        version = subprocess.run([args.javap, "-version"], check=True, capture_output=True,
                                 text=True, timeout=15).stdout.strip()
        if not re.match(r"^17(?:[.+_-]|$)", version):
            raise ValueError(f"expected JDK 17 javap, got {version!r}")
        blobs = {"registry": args.registry_class.read_bytes(), "function": args.function_class.read_bytes()}
        result["javap_version"] = version
        result["class_sha256"] = {name: hashlib.sha256(data).hexdigest() for name, data in blobs.items()}
        with tempfile.TemporaryDirectory(prefix="gametest-function-class-") as directory:
            listings = {}
            for name, data in blobs.items():
                snapshot = Path(directory) / ("GameTestRegistry.class" if name == "registry" else "TestFunction.class")
                snapshot.write_bytes(data)
                listings[name] = subprocess.run([args.javap, "-c", "-p", "-s", str(snapshot)],
                    check=True, capture_output=True, text=True, timeout=15).stdout
        errors = check_registry_listing(listings["registry"]) + check_function_listing(listings["function"])
        result["errors"] = errors
        result["passed"] = not errors
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError) as exc:
        result["errors"] = [f"could not inspect class: {exc}"]
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
