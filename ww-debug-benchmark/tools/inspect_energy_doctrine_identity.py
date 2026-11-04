#!/usr/bin/env python3
"""Exercise real energy/offensive source with synthetic entities; never runs a MOD.

Only use trusted local JDK, classpath, source checkout and fixture inputs. This
runner is not a sandbox. An intentional assertion failure is evidence only when
the case reached its stated hook and failed for the stated contract.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent / "src/main/java"
FIXTURE = HERE / "inspect_offensive_identity.py"
PROBE = HERE / "energy_pilot_fixture/Probe.java"
SOURCE_NAMES = (
    "ControlAuthorityArbiter", "FormationFlightManager", "AirspaceSafetyProbe",
    "MobPilotGate", "ControlOutcome", "ControlProposal", "FlightControlOutput",
    "FlightPhase", "AutopilotSession", "FlightProfile", "AutonomousFlightManager",
    "FighterCombatFacade", "DefensiveAirCombatManager", "DefensiveAirCombatAction",
    "AirCombatManeuverManager", "AirCombatAction", "AirCombatDoctrineTuning",
    "AutopilotDoctrine", "EnergyFighterApexYawAdapter",
)
# Supplied by the fixture contract; edit in lockstep with the separately reviewed Probe.
CASES = (
    "fallback-same", "fallback-swap", "fallback-same-uuid", "fallback-player",
    "fallback-empty", "fallback-client", "fallback-removed", "fallback-outer-a-inner-b",
    "alignment-same", "alignment-swap", "collision", "terrain",
)


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def inventory(entries):
    result = {}
    for entry in entries:
        files = sorted(p for p in entry.rglob("*") if p.is_file()) if entry.is_dir() else [entry]
        for item in files:
            result[str(item)] = sha(item)
    return result


def replace_once(text, old, new, label):
    if text.count(old) != 1:
        raise ValueError(f"fake transformation anchor mismatch: {label}")
    return text.replace(old, new, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java-home", type=Path, required=True)
    parser.add_argument("--dependencies-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    deps_file = args.dependencies_json.resolve(strict=True)
    raw_deps = json.loads(deps_file.read_text(encoding="utf-8"))
    if not isinstance(raw_deps, list) or not raw_deps or any(not isinstance(x, str) for x in raw_deps):
        raise ValueError("dependencies must be a nonempty JSON array of paths")
    deps = [Path(x) for x in raw_deps]
    if any(not x.is_absolute() or not x.exists() for x in deps):
        raise ValueError("dependency paths must be absolute and exist")
    jdk = args.java_home.resolve(strict=True) / "bin"
    for executable in (jdk / "java", jdk / "javac"):
        if not executable.is_file():
            raise ValueError(f"missing JDK executable: {executable}")
    sources = [ROOT / "com/wwdebug/autopilot" / (name + ".java") for name in SOURCE_NAMES]
    for path in [FIXTURE, PROBE, *sources]:
        if not path.is_file():
            raise ValueError(f"missing fixture input: {path}")

    out = args.output.absolute()
    out.mkdir(mode=0o700)  # Refuse an existing result, including partial or failed evidence.
    src, fake, classes, empty = (out / x for x in ("source-copy", "stubs", "classes", "empty"))
    for directory in (src, fake, classes, empty):
        directory.mkdir()
    shutil.copyfile(__file__, out / "runner-snapshot.py")
    shutil.copyfile(FIXTURE, out / "fixture-snapshot.py")
    shutil.copyfile(PROBE, out / "probe-snapshot.java")

    spec = importlib.util.spec_from_file_location("offensive_fixture", FIXTURE)
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    stubs = dict(fixture.STUBS)
    del stubs["com/wwdebug/autopilot/EnergyFighterApexYawAdapter.java"]
    del stubs["com/wwdebug/autopilot/Probe.java"]
    changes = {
        "net/minecraft/world/entity/LivingEntity.java": (
            "public Entity getVehicle(){return null;}",
            "public Entity vehicle; public Entity getVehicle(){return vehicle;}",
        ),
        "net/minecraft/world/entity/Entity.java": (
            "public boolean onGround(){return false;}",
            "public float distanceTo(Entity other){return (float)position().distanceTo(other.position());}public boolean onGround(){return false;}",
        ),
        "net/minecraft/server/level/ServerLevel.java": (
            "public MinecraftServer getServer(){return null;}",
            "public long getGameTime(){return 1000L;} public MinecraftServer getServer(){return null;}",
        ),
        "com/wwdebug/autopilot/FlightSnapshot.java": (
            "public float pitchDeg(){return 0;}",
            "public float pitchDeg(){return 0;}public float rollDeg(){return 0;}",
        ),
    }
    for name, (old, new) in changes.items():
        stubs[name] = replace_once(stubs[name], old, new, name)
    stubs["com/wwdebug/autopilot/Probe.java"] = PROBE.read_text(encoding="utf-8")

    copies, fake_files = [], []
    for source in sources:
        dest = src / source.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        copies.append(dest)
    for name, content in sorted(stubs.items()):
        dest = fake / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        fake_files.append(dest)

    inputs = [Path(__file__).resolve(), FIXTURE, PROBE, deps_file, jdk / "java", jdk / "javac", *sources, *copies, *fake_files]
    before, cp_before = inventory(inputs), inventory(deps)
    equal = all(sha(original) == sha(copy) for original, copy in zip(sources, copies))
    if not equal:
        raise RuntimeError("source copy mismatch")
    report = {
        "scope": "Synthetic callbacks and entities; real energy and offensive source; no Minecraft, actual weapon, native setter or runtime takeover proof.",
        "cases": CASES,
        "fake_changes": {name: {"old": pair[0], "new": pair[1]} for name, pair in changes.items()},
        "removed_stubs": ["EnergyFighterApexYawAdapter", "Probe"],
        "source_copy_equal": equal,
        "inputs_before": before,
        "classpath_before": cp_before,
        "runs": {},
    }

    def run(name, command):
        before_classes = inventory([classes])
        try:
            completed = subprocess.run(command, cwd=out, capture_output=True, timeout=30)
            code, stdout_bytes, stderr_bytes = completed.returncode, completed.stdout, completed.stderr
        except subprocess.TimeoutExpired as exc:
            code, stdout_bytes, stderr_bytes = None, exc.stdout or b"", exc.stderr or b""
        stdout, stderr = out / (name + ".stdout"), out / (name + ".stderr")
        stdout.write_bytes(stdout_bytes)
        stderr.write_bytes(stderr_bytes)
        load = out / (name + ".classes.log")
        outputs = [stdout, stderr] + ([load] if load.exists() else [])
        report["runs"][name] = {"argv": command, "exit": code, "timed_out": code is None,
                                "classes_before": before_classes, "classes_after": inventory([classes]),
                                "outputs": inventory(outputs)}
        print(name, code, flush=True)
        return code

    try:
        cp = os.pathsep.join(map(str, deps))
        rc = run("compile", [str(jdk / "javac"), "-proc:none", "--release", "17", "-cp", cp,
                             "-sourcepath", str(empty), "-d", str(classes), *map(str, copies), *map(str, fake_files)])
        if rc == 0:
            for case in CASES:
                run(case, [str(jdk / "java"), "-Xmx128m", "-Xverify:all",
                           "-Xlog:class+load=info:file=" + str(out / (case + ".classes.log")),
                           "-cp", str(classes) + os.pathsep + cp, "com.wwdebug.autopilot.Probe", case])
    finally:
        report["inputs_after"] = inventory(inputs)
        report["inputs_unchanged"] = before == report["inputs_after"]
        report["classpath_after"] = inventory(deps)
        report["classpath_unchanged"] = cp_before == report["classpath_after"]
        report["compiled_classes"] = inventory([classes])
        report["stage_stable"] = all(v["classes_before"] == v["classes_after"] == report["compiled_classes"]
                                     for k, v in report["runs"].items() if k != "compile")
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    # Four red assertions are intentional. The report must be reviewed case by case.
    return 0 if (report["inputs_unchanged"] and report["classpath_unchanged"] and report["stage_stable"]
                 and len(report["runs"]) == len(CASES) + 1
                 and all(report["runs"][name]["exit"] == 0 for name in CASES)) else 1


if __name__ == "__main__":
    sys.exit(main())
