#!/usr/bin/env python3
"""Run the isolated post-physics direct-call fixture, never a game or a world.

Pass a JSON array of explicit dependency classpath entries and a new output directory.
The stand-ins shadow Minecraft types only in these child JVMs. They are outside Gradle
source sets and do not prove real entity, native physics, lifecycle, or GameTest behavior.
"""
import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys

CASES = (
    "player-locked", "empty-locked", "client-locked", "player-decel", "empty-decel", "client-decel",
    "mob-locked", "mob-default", "mob-min", "mob-max", "airborne", "wrong-phase", "no-session",
    "cross-player", "cross-empty", "cross-client", "cross-mob", "cross-mob-crossover",
    "stale-player", "stale-empty", "stale-empty-airborne", "stale-stop", "stale-client", "stale-airborne", "stale-force-stop-locked",
)


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inventory(paths):
    result = {}
    for path in paths:
        files = sorted(p for p in path.rglob("*") if p.is_file()) if path.is_dir() else [path]
        for item in files:
            result[str(item)] = sha(item)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java-home", type=pathlib.Path, required=True)
    parser.add_argument("--dependencies-json", type=pathlib.Path, required=True,
                        help="JSON array of existing classpath entries")
    parser.add_argument("--output", type=pathlib.Path, required=True,
                        help="new directory; existing evidence is never overwritten")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--source-root", type=pathlib.Path, help="actual src/main/java to compile")
    mode.add_argument("--classes", type=pathlib.Path, help="actual Gradle-generated main classes")
    parser.add_argument("--source-provenance", type=pathlib.Path,
                        help="src/main/java whose hash is recorded in classes mode")
    args = parser.parse_args()
    if args.classes and args.source_provenance is None:
        parser.error("--classes requires --source-provenance")

    output = args.output.absolute()
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    fixture = pathlib.Path(__file__).resolve().parents[1] / "tests/postphysics_standin/src"
    standin_sources = sorted(fixture.rglob("*.java"))
    source_root = (args.source_root or args.source_provenance).resolve()
    actual_sources = [source_root / "com/wwdebug/autopilot" / (name + ".java")
                      for name in ("AutonomousFlightManager", "MobPilotGate", "AutopilotWheelLockAdapter")]
    deps = [pathlib.Path(item).resolve() for item in json.loads(args.dependencies_json.read_text())]
    java = (args.java_home / "bin" / ("java.exe" if os.name == "nt" else "java")).resolve()
    javac = (args.java_home / "bin" / ("javac.exe" if os.name == "nt" else "javac")).resolve()
    main_classes = args.classes.resolve() if args.classes else output / "production"
    fake_classes = output / "standins"
    fake_classes.mkdir()
    if args.source_root:
        main_classes.mkdir()
    observed = deps + ([main_classes] if args.classes else [])
    before = inventory(observed)
    source_before = inventory(actual_sources + standin_sources
                              + [pathlib.Path(__file__).resolve(), args.dependencies_json.resolve(), java, javac])
    (output / "before.json").write_text(json.dumps({"sources": source_before, "classpath": before}, indent=2) + "\n")

    def run(name, argv):
        result = subprocess.run(argv, cwd=output, capture_output=True)
        (output / (name + ".json")).write_text(json.dumps({"argv": argv, "cwd": str(output),
                                                            "exit": result.returncode}, indent=2) + "\n")
        (output / (name + ".stdout")).write_bytes(result.stdout)
        (output / (name + ".stderr")).write_bytes(result.stderr)
        print(name, result.returncode, flush=True)
        return result.returncode

    failures = 0
    deps_cp = os.pathsep.join(map(str, deps))
    if args.source_root:
        failures += run("compile-production", [str(javac), "-proc:none", "--release", "17", "-cp", deps_cp,
                                                "-d", str(main_classes), *map(str, actual_sources)]) != 0
    main_cp = str(main_classes) + os.pathsep + deps_cp
    if not failures:
        failures += run("compile-standins", [str(javac), "-proc:none", "--release", "17", "-cp", main_cp,
                                             "-d", str(fake_classes), *map(str, standin_sources)]) != 0
    if not failures:
        for case in CASES:
            failures += run(case, [str(java), "-Xmx128m", "-Xverify:all",
                                   "-Xlog:class+load=info:file=" + str(output / (case + ".classes.log")),
                                   "-cp", str(fake_classes) + os.pathsep + main_cp,
                                   "com.wwdebug.autopilot.PostPhysicsStandinProbe", case]) != 0
    after = inventory(observed)
    source_after = inventory(actual_sources + standin_sources
                             + [pathlib.Path(__file__).resolve(), args.dependencies_json.resolve(), java, javac])
    (output / "after.json").write_text(json.dumps({"sources": source_after, "classpath": after,
        "standin_classes": inventory([fake_classes]),
        "production_classes": inventory([main_classes])}, indent=2) + "\n")
    if before != after or source_before != source_after:
        print("input changed during run", file=sys.stderr)
        failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
