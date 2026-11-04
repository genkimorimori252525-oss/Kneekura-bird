#!/usr/bin/env python3
"""Compile and run the isolated geometry contract against explicit classpath inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inputs(classes: Path, jars: list[Path], test: Path, oracle: Path, runner: Path, source: Path,
           java: Path, javac: Path) -> dict:
    class_files = sorted(classes.rglob("*.class"))
    if not class_files:
        raise ValueError("compiled classes directory contains no class files")
    target = classes / "com/wwdebug/autopilot/CombatWeaponManager.class"
    if not target.is_file():
        raise ValueError("compiled CombatWeaponManager.class is missing")
    return {
        "test_sha256": sha256(test),
        "oracle_sha256": sha256(oracle),
        "runner_sha256": sha256(runner),
        "observed_source_sha256_unverified": sha256(source),
        "java_sha256": sha256(java),
        "javac_sha256": sha256(javac),
        "classes": {str(path.relative_to(classes)): sha256(path) for path in class_files},
        "classpath_files": [{"path": str(path), "sha256": sha256(path)} for path in jars],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--classes", required=True, type=Path,
                        help="directory containing compiled production classes")
    parser.add_argument("--classpath-file", required=True, type=Path,
                        help="UTF-8 file listing one fixed dependency jar per line")
    parser.add_argument("--java", required=True, type=Path, help="JDK 17 java executable")
    parser.add_argument("--javac", required=True, type=Path, help="JDK 17 javac executable")
    parser.add_argument("--evidence", required=True, type=Path,
                        help="new evidence directory; must not already exist")
    args = parser.parse_args()

    evidence = args.evidence.absolute()
    evidence.mkdir(mode=0o700, parents=False, exist_ok=False)
    metadata = {"scope": "standalone geometry only; not GameTest or firing safety"}
    try:
        classes = args.classes.resolve(strict=True)
        test = (Path(__file__).parent / "com/wwdebug/autopilot/ProtectedCorridorGeometryCheck.java").resolve(strict=True)
        oracle = (Path(__file__).parent / "exact_corridor_oracle.py").resolve(strict=True)
        runner = Path(__file__).resolve(strict=True)
        source = (Path(__file__).parent.parent / "src/main/java/com/wwdebug/autopilot/CombatWeaponManager.java").resolve(strict=True)
        jars = [Path(line).resolve(strict=True) for line in args.classpath_file.read_text(encoding="utf-8").splitlines() if line]
        if not classes.is_dir() or not jars or not all(path.is_file() for path in jars):
            raise ValueError("classes must be a directory and classpath entries must be files")
        java, javac = args.java.resolve(strict=True), args.javac.resolve(strict=True)
        java_version = subprocess.run([str(java), "-version"], capture_output=True, text=True, timeout=15)
        javac_version = subprocess.run([str(javac), "-version"], capture_output=True, text=True, timeout=15)
        metadata["java_version"] = (java_version.stdout + java_version.stderr).strip()
        metadata["javac_version"] = (javac_version.stdout + javac_version.stderr).strip()
        if (java_version.returncode != 0 or javac_version.returncode != 0
                or not re.match(r'^(?:openjdk|java) version "17(?:[.+_-]|\")', metadata["java_version"])
                or not re.match(r"^javac 17(?:[.+_-]|$)", metadata["javac_version"])):
            raise ValueError("java and javac must both be JDK 17")
        before = inputs(classes, jars, test, oracle, runner, source, java, javac)
        metadata["inputs_before"] = before
        with tempfile.TemporaryDirectory(prefix="ww-corridor-check-") as directory:
            cp = os.pathsep.join([str(classes), *(str(path) for path in jars)])
            compile_argv = [str(javac), "-cp", cp, "-d", directory, str(test)]
            metadata["compile_argv"] = compile_argv
            compiled = subprocess.run(compile_argv, cwd=evidence, capture_output=True, text=True, timeout=60)
            (evidence / "compile.stdout").write_text(compiled.stdout, encoding="utf-8")
            (evidence / "compile.stderr").write_text(compiled.stderr, encoding="utf-8")
            metadata["compile_exit"] = compiled.returncode
            if compiled.returncode != 0:
                raise ValueError("test compilation failed")
            run_argv = [str(java), "-cp", directory + os.pathsep + cp,
                        "com.wwdebug.autopilot.ProtectedCorridorGeometryCheck"]
            metadata["run_argv"] = run_argv
            result = subprocess.run(run_argv, cwd=evidence, capture_output=True, text=True, timeout=60)
            (evidence / "run.stdout").write_text(result.stdout, encoding="utf-8")
            (evidence / "run.stderr").write_text(result.stderr, encoding="utf-8")
            metadata["run_exit"] = result.returncode
            if result.returncode != 0:
                raise ValueError("geometry contract failed")
            oracle_argv = [sys.executable, str(oracle), "--java", str(java), "--classpath",
                           directory + os.pathsep + cp]
            metadata["oracle_argv"] = oracle_argv
            checked = subprocess.run(oracle_argv, cwd=evidence, capture_output=True, text=True, timeout=90)
            (evidence / "oracle.stdout").write_text(checked.stdout, encoding="utf-8")
            (evidence / "oracle.stderr").write_text(checked.stderr, encoding="utf-8")
            metadata["oracle_exit"] = checked.returncode
        metadata["inputs_after"] = inputs(classes, jars, test, oracle, runner, source, java, javac)
        metadata["inputs_unchanged"] = metadata["inputs_before"] == metadata["inputs_after"]
        metadata["passed"] = result.returncode == 0 and checked.returncode == 0 and metadata["inputs_unchanged"]
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        metadata["passed"] = False
        metadata["error"] = str(error)
    (evidence / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: metadata.get(key) for key in ("scope", "passed", "compile_exit", "run_exit", "oracle_exit", "inputs_unchanged", "error")}, indent=2))
    return 0 if metadata["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
