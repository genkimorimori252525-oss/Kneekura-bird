#!/usr/bin/env python3
"""Compare built energy classes with an existing synthetic source fixture.

Requires trusted local source, JDK, fixture report and dependency classpath.
This program runs their code and is not a sandbox or a Forge GameTest. The
saved report's argv is data only and is never executed. Select a new output
directory; existing evidence is never overwritten. Exit 0 means the recorded
comparisons matched, not that real flight, weapons or native setters passed.
Origins are URI-decoded/resolved paths, not protection against symlink races.
Input hashes are not authentication and classpath inventory does not prove order.
The top four target classes must load somewhere in the suite; other targets are
checked when observed, while generated lambda origins are outside this check.
Caught injected sentinel exceptions are compared separately from normal cases.
"""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import urllib.parse

CASES = (
    "fallback-same", "fallback-swap", "fallback-same-uuid", "fallback-player",
    "fallback-empty", "fallback-client", "fallback-removed", "fallback-outer-a-inner-b",
    "alignment-same", "alignment-swap", "collision", "terrain", "fallback-level",
    "fallback-outer-a-inner-b-final-a", "fallback-outer-level-inner-other-final-outer",
    "empty-claimed", "climb-same", "climb-swap", "pivot-same", "pivot-swap",
    "capture-same", "capture-swap", "empty-aim-alignment-same", "empty-aim-alignment-swap",
    "throw-energy-pilot", "throw-offensive-pilot",
)
SENTINELS = frozenset(("throw-energy-pilot", "throw-offensive-pilot"))
NAMES = (
    "AirCombatManeuverManager.class", "AirCombatManeuverManager$1.class",
    "AirCombatManeuverManager$AimSolution.class", "AirCombatManeuverManager$CombatContext.class",
    "AirCombatManeuverManager$OffensiveEvaluation.class", "AirCombatManeuverManager$State.class",
    "ControlAuthorityArbiter.class", "ControlAuthorityArbiter$Authority.class",
    "ControlAuthorityArbiter$DefensiveAttempt.class", "ControlAuthorityArbiter$PendingDecision.class",
    "EnergyFighterApexYawAdapter.class", "EnergyFighterApexYawAdapter$1.class",
    "EnergyFighterApexYawAdapter$EnergyEvaluation.class", "EnergyFighterApexYawAdapter$Stage.class",
    "EnergyFighterApexYawAdapter$State.class", "EnergyFighterApexYawAdapter$Target.class",
    "EnergyFighterApexYawAdapter$ThreatView.class", "FighterCombatFacade.class",
    "FighterCombatFacade$CombatEvaluation.class",
)
TOP = ("AirCombatManeuverManager.class", "ControlAuthorityArbiter.class",
       "EnergyFighterApexYawAdapter.class", "FighterCombatFacade.class")
OBJECT = re.compile(r"(net\.minecraft\.world\.entity\.(?:Mob|Player|LivingEntity|Entity))@([0-9a-f]+)")
TERMINAL_WARNING = "WARN Advanced terminal features are not available in this environment"


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def inventory(path):
    return {str(p.relative_to(path)): sha(p) for p in sorted(path.rglob("*")) if p.is_file()}


def classpath_inventory(entries):
    return {str(f): sha(f) for entry in entries
            for f in (sorted(p for p in entry.rglob("*") if p.is_file()) if entry.is_dir() else [entry])}


def normalized(text):
    """Remove only the terminal warning and normalize object identities consistently per run."""
    identities = {}

    def replace(match):
        key = match.group(0)
        if key not in identities:
            identities[key] = len(identities) + 1
        return match.group(1) + "@object" + str(identities[key])

    return OBJECT.sub(replace, "\n".join(line for line in text.splitlines() if TERMINAL_WARNING not in line))


def valid_origin(value, expected):
    origin = urllib.parse.urlsplit(value)
    path = Path(urllib.parse.unquote(origin.path))
    return (origin.scheme == "file" and not origin.netloc and not origin.query
            and not origin.fragment and path.is_absolute() and path.resolve() == expected.resolve())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--actual", type=Path, required=True, help="saved actual-source run directory")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--java-home", type=Path, required=True)
    parser.add_argument("--dependencies-json", type=Path, required=True)
    args = parser.parse_args()
    repo, actual, out = args.repo.resolve(strict=True), args.actual.resolve(strict=True), args.output.absolute()
    out.mkdir(mode=0o700)
    report = {"scope": "Built classes in a synthetic source fixture; no actual MOD, weapon or native-setter proof.",
              "runs": {}, "errors": [], "sentinel_cases": sorted(SENTINELS)}
    errors = report["errors"]

    def check(condition, message):
        if not condition:
            errors.append(message)

    def write_report():
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    env = os.environ.copy()
    removed = ("JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS", "JDK_JAVA_OPTIONS", "JDK_JAVAC_OPTIONS")
    report["removed_java_environment_variables_present"] = {name: name in env for name in removed}
    for name in removed:
        env.pop(name, None)

    saved_file = actual / "report.json"
    manifest_file = actual.parent / "candidate-manifest.json"
    saved = json.loads(saved_file.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    report["saved_report_sha256"], report["manifest_sha256"] = sha(saved_file), sha(manifest_file)
    check(not (actual.parent / "candidate.patch").read_bytes(), "actual source patch is not empty")
    check(saved.get("source_copy_equal") and saved.get("inputs_unchanged")
          and saved.get("classpath_unchanged") and saved.get("stage_stable"), "actual-source provenance flags")
    check(set(saved.get("runs", {})) == set(CASES) | {"compile"}, "actual-source case set mismatch")
    check(saved.get("runs", {}).get("compile", {}).get("exit") == 0, "actual-source compile failed")
    check(all(not value.get("modified") and value.get("original_sha256") == value.get("candidate_sha256")
              for value in manifest.get("sources", {}).values()), "actual manifest source differs")
    check(len(manifest.get("sources", {})) == 19, "actual source inventory count")
    probe = actual / "stubs/com/wwdebug/autopilot/Probe.java"
    check(probe.is_file() and sha(probe) == manifest.get("candidate_probe_sha256"), "actual probe changed")
    check(re.fullmatch(r"[0-9a-f]{40}", args.expected_commit) is not None, "expected commit must be a full SHA")

    dep_file = args.dependencies_json.resolve(strict=True)
    raw_deps = json.loads(dep_file.read_text(encoding="utf-8"))
    valid_deps = (isinstance(raw_deps, list) and bool(raw_deps)
                  and all(isinstance(x, str) and x and Path(x).is_absolute() and os.pathsep not in x
                          and "\n" not in x and "\r" not in x for x in raw_deps))
    check(valid_deps, "invalid dependency path list")
    if not valid_deps:
        write_report()
        return 1
    deps = [Path(x) for x in raw_deps]
    check(len(raw_deps) == len(set(raw_deps)), "duplicate dependency path")
    check(all(x.is_dir() or (x.is_file() and x.suffix.lower() in (".jar", ".zip")) for x in deps),
          "dependency must be a directory, jar or zip")
    java, javac, javap = (args.java_home.resolve(strict=True) / "bin" / x for x in ("java", "javac", "javap"))
    check(all(x.is_file() and os.access(x, os.X_OK) for x in (java, javac, javap)), "JDK executable missing")
    if errors:
        write_report()
        return 1
    dep_before = classpath_inventory(deps)
    check(dep_before == saved.get("classpath_before"), "dependency inventory differs from saved run")
    report["explicit_inputs"] = {"dependencies_json": str(dep_file), "dependencies_json_sha256": sha(dep_file),
                                 "classpath_before": dep_before, "java_sha256": sha(java),
                                 "javac_sha256": sha(javac), "javap_sha256": sha(javap),
                                 "argv_source": "explicit inputs and fixed case list"}
    git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True)
    status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"],
                            cwd=repo, capture_output=True, text=True)
    report["git_head"], report["git_status"] = git.stdout.strip(), status.stdout
    check(git.returncode == 0 and report["git_head"] == args.expected_commit, "commit mismatch")
    check(status.returncode == 0 and not status.stdout, "tracked worktree changed")

    for name, info in manifest.get("sources", {}).items():
        source = repo / "ww-debug-benchmark/src/main/java/com/wwdebug/autopilot" / (name + ".java")
        original = actual.parent / "candidate-source/com/wwdebug/autopilot" / (name + ".java")
        copy = actual / "source-copy/com/wwdebug/autopilot" / (name + ".java")
        check(all(x.is_file() and sha(x) == info["original_sha256"] for x in (source, original, copy)),
              "source mismatch " + name)
    for path, digest in saved.get("compiled_classes", {}).items():
        check(Path(path).is_file() and sha(Path(path)) == digest, "saved fixture class changed " + path)
    for name in CASES:
        entry = saved.get("runs", {}).get(name, {})
        check(entry.get("exit") == 0 and not entry.get("timed_out"), "unexpected saved case exit " + name)
        for path, digest in entry.get("outputs", {}).items():
            check(Path(path).is_file() and sha(Path(path)) == digest, "saved fixture output changed " + path)
        check(str(actual / (name + ".stdout")) in entry.get("outputs", {}), "saved stdout absent " + name)
    if errors:
        write_report()
        return 1

    stage = out / "classes"
    shutil.copytree(actual / "classes", stage)
    fake_original = actual / "stubs/com/wwdebug/benchmark/ReflectiveArmament.java"
    fake_dir = out / "fake-adjusted/com/wwdebug/benchmark"
    fake_dir.mkdir(parents=True)
    fake = fake_dir / "ReflectiveArmament.java"
    check(saved.get("inputs_before", {}).get(str(fake_original)) == sha(fake_original),
          "saved fake armament source changed")
    fake_text = fake_original.read_text(encoding="utf-8")
    check(len(re.findall(r"\bGun\b", fake_text)) == 3, "unexpected fake Gun source")
    fake.write_text(re.sub(r"\bGun\b", "MountedWeapon", fake_text), encoding="utf-8")
    report["fake_adjustment"] = {"original_sha256": sha(fake_original), "adjusted_sha256": sha(fake),
                                 "scope": "Gun to MountedWeapon type rename in artificial fake only"}
    snapshot_original = actual / "stubs/com/wwdebug/autopilot/FlightSnapshot.java"
    snapshot_dir = out / "fake-adjusted/com/wwdebug/autopilot"
    snapshot_dir.mkdir(parents=True)
    snapshot = snapshot_dir / "FlightSnapshot.java"
    snapshot_text = snapshot_original.read_text(encoding="utf-8")
    snapshot_old, snapshot_new = "public float rollDeg(){return 0;}", "public double rollDeg(){return 0;}"
    check(saved.get("inputs_before", {}).get(str(snapshot_original)) == sha(snapshot_original),
          "saved fake snapshot source changed")
    check(snapshot_text.count(snapshot_old) == 1, "unexpected fake snapshot rollDeg source")
    snapshot.write_text(snapshot_text.replace(snapshot_old, snapshot_new, 1), encoding="utf-8")
    diff = list(difflib.unified_diff(fake_text.splitlines(keepends=True), fake.read_text().splitlines(keepends=True),
                                    fromfile="original/ReflectiveArmament.java", tofile="adjusted/ReflectiveArmament.java"))
    diff += list(difflib.unified_diff(snapshot_text.splitlines(keepends=True), snapshot.read_text().splitlines(keepends=True),
                                     fromfile="original/FlightSnapshot.java", tofile="adjusted/FlightSnapshot.java"))
    (out / "fake-adjustments.patch").write_text("".join(diff), encoding="utf-8")
    report["fake_adjustment"]["snapshot"] = {"original_sha256": sha(snapshot_original),
        "adjusted_sha256": sha(snapshot), "scope": "rollDeg return float to double in artificial fake only"}
    report["fake_adjustment"]["patch_sha256"] = sha(out / "fake-adjustments.patch")
    empty = out / "empty-sourcepath"
    empty.mkdir()
    cp = os.pathsep.join(map(str, deps))
    fake_argv = [str(javac), "-proc:none", "--release", "17", "-cp", str(stage) + os.pathsep + cp,
                 "-sourcepath", str(empty), "-d", str(stage), str(fake), str(snapshot)]
    if errors:
        write_report()
        return 1
    try:
        compiler = subprocess.run(fake_argv, capture_output=True, timeout=30, env=env)
        compiler_exit, compiler_out, compiler_err = compiler.returncode, compiler.stdout, compiler.stderr
    except subprocess.TimeoutExpired as timeout:
        compiler_exit, compiler_out, compiler_err = None, timeout.stdout or b"", timeout.stderr or b""
    (out / "fake-compile.stdout").write_bytes(compiler_out)
    (out / "fake-compile.stderr").write_bytes(compiler_err)
    report["fake_adjustment"].update({"argv": fake_argv, "exit": compiler_exit,
                                      "timed_out": compiler_exit is None,
                                      "stdout_sha256": sha(out / "fake-compile.stdout"),
                                      "stderr_sha256": sha(out / "fake-compile.stderr")})
    check(compiler_exit == 0, "adjusted fake compile failed or timed out")
    if errors:
        write_report()
        return 1

    descriptor_checks = {}
    for name, location in (("fake", stage), ("built", repo / "ww-debug-benchmark/build/classes/java/main")):
        argv = [str(javap), "-public", "-s", "-classpath", str(location), "com.wwdebug.autopilot.FlightSnapshot"]
        result = subprocess.run(argv, capture_output=True, timeout=30, env=env)
        stdout, stderr = out / ("snapshot-" + name + ".javap"), out / ("snapshot-" + name + ".stderr")
        stdout.write_bytes(result.stdout)
        stderr.write_bytes(result.stderr)
        signature = bool(re.search(r"rollDeg\(\);\s+descriptor: \(\)D", stdout.read_text(encoding="utf-8")))
        descriptor_checks[name] = {"argv": argv, "exit": result.returncode, "rollDeg_double": signature,
                                   "stdout_sha256": sha(stdout), "stderr_sha256": sha(stderr),
                                   "class_sha256": sha(location / "com/wwdebug/autopilot/FlightSnapshot.class")}
        check(result.returncode == 0 and signature, "snapshot rollDeg descriptor mismatch: " + name)
    report["fake_adjustment"]["snapshot_descriptors"] = descriptor_checks
    if errors:
        write_report()
        return 1

    build = repo / "ww-debug-benchmark/build/classes/java/main/com/wwdebug/autopilot"
    destination = stage / "com/wwdebug/autopilot"
    prefixes = ("AirCombatManeuverManager", "ControlAuthorityArbiter",
                "EnergyFighterApexYawAdapter", "FighterCombatFacade")
    for directory in (build, destination):
        names = {p.name for p in directory.iterdir() if p.name.endswith(".class")
                 and any(p.name == x + ".class" or p.name.startswith(x + "$") for x in prefixes)}
        check(names == set(NAMES), "unexpected target class set in " + str(directory))
    if errors:
        write_report()
        return 1
    report["fixture_before"] = {n: sha(destination / n) for n in NAMES}
    built_before = {n: sha(build / n) for n in NAMES}
    for name in NAMES:
        shutil.copyfile(build / name, destination / name)
    staged = {n: sha(destination / n) for n in NAMES}
    check(staged == built_before, "staged built class hash mismatch")
    report["built_before"], report["staged_before"] = built_before, staged
    report["normalization_scope"] = "terminal warning lines and per-run ordered fake Entity object display identities"
    report["source_stdout_stderr_scope"] = "exit/stdout compared; stderr retained as hash, not compared"
    loaded = {}
    for name in CASES:
        before = inventory(stage)
        log = out / (name + ".classes.log")
        argv = [str(java), "-Xmx128m", "-Xverify:all", "-Xlog:class+load=info:file=" + str(log),
                "-cp", str(stage) + os.pathsep + cp, "com.wwdebug.autopilot.Probe", name]
        try:
            result = subprocess.run(argv, cwd=out, capture_output=True, timeout=30, env=env)
            code, stdout_bytes, stderr_bytes = result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired as timeout:
            code, stdout_bytes, stderr_bytes = None, timeout.stdout or b"", timeout.stderr or b""
        stdout, stderr = out / (name + ".stdout"), out / (name + ".stderr")
        stdout.write_bytes(stdout_bytes)
        stderr.write_bytes(stderr_bytes)
        after = inventory(stage)
        reference = (actual / (name + ".stdout")).read_text(encoding="utf-8")
        observed = stdout.read_text(encoding="utf-8")
        equal = normalized(observed) == normalized(reference)
        check(code == saved["runs"][name]["exit"], name + " exit differs or timed out")
        check(equal, name + " stdout differs")
        check(before == after, name + " staged classes changed")
        if name in SENTINELS:
            check("SENTINEL_EXCEPTION identity=true" in observed, name + " sentinel identity not observed")
        check(log.is_file(), name + " class load log missing")
        if log.is_file():
            for target in NAMES:
                cls = "com.wwdebug.autopilot." + target[:-6]
                lines = [line for line in log.read_text().splitlines() if "] " + cls + " source:" in line]
                for line in lines:
                    loaded[target] = loaded.get(target, 0) + 1
                    check(valid_origin(line.split(" source: ", 1)[1], stage), name + " unexpected origin " + target)
        report["runs"][name] = {"argv": argv, "exit": code, "timed_out": code is None,
                                "expected_exit": saved["runs"][name]["exit"],
                                "kind": "caught intentional sentinel" if name in SENTINELS else "synthetic control",
                                "stdout_normalized_equal": equal, "stdout_sha256": sha(stdout),
                                "stderr_sha256": sha(stderr), "class_log_sha256": sha(log) if log.is_file() else None,
                                "stage_before": before, "stage_after": after}
    report["loaded_counts"] = loaded
    report["target_classes_not_observed_loaded"] = sorted(set(NAMES) - set(loaded))
    check(all(name in loaded for name in TOP), "one or more top-level targets not observed loaded")
    report["dynamic_lambda_scope"] = "generated lambda origins are not asserted"
    report["built_after"] = {n: sha(build / n) for n in NAMES}
    report["staged_after"] = {n: sha(destination / n) for n in NAMES}
    check(report["built_after"] == built_before and report["staged_after"] == staged, "target class hashes changed")
    check(classpath_inventory(deps) == dep_before, "dependency inventory changed")
    check(sha(java) == report["explicit_inputs"]["java_sha256"]
          and sha(javac) == report["explicit_inputs"]["javac_sha256"]
          and sha(javap) == report["explicit_inputs"]["javap_sha256"], "JDK executable changed")
    report["script_sha256"] = sha(Path(__file__).resolve())
    write_report()
    print("cases", len(report["runs"]), "errors", len(errors), flush=True)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
