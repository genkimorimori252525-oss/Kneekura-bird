#!/usr/bin/env python3
"""Observe the route-clock policy directly; does not start Minecraft or Gradle.

This characterizes a negative value, not a live Mixin/route or a GameTest.
The output directory must not already exist and must be outside this checkout.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "src/main/java/com/wwdebug/autopilot"
PROBE = r'''package com.wwdebug.autopilot;
public final class Probe {
    public static void main(String[] args) {
        switch (args[0]) {
            case "negative" -> {
                try {
                    MissionRouteClockPolicy.phaseTicksAfterHeldTick(FlightPhase.CRUISE_OUTBOUND, -499);
                    throw new AssertionError("negative unexpectedly accepted");
                } catch (IllegalArgumentException expected) {
                    System.out.println("CRUISE_OUTBOUND,-499: " + expected.getClass().getSimpleName()
                            + ":" + expected.getMessage());
                }
            }
            case "outbound" -> {
                int value = MissionRouteClockPolicy.phaseTicksAfterHeldTick(FlightPhase.CRUISE_OUTBOUND, 239);
                if (value != 238) throw new AssertionError("outbound: " + value);
                System.out.println("CRUISE_OUTBOUND,239 -> " + value);
            }
            case "turn" -> {
                int value = MissionRouteClockPolicy.phaseTicksAfterHeldTick(FlightPhase.TURN_RIGHT, 440);
                if (value != 439) throw new AssertionError("turn: " + value);
                System.out.println("TURN_RIGHT,440 -> " + value);
            }
            case "mission" -> {
                int value = MissionRouteClockPolicy.missionTicksAfterHeldTick(10001);
                if (value != 10000) throw new AssertionError("mission: " + value);
                System.out.println("mission,10001 -> " + value);
            }
            default -> throw new IllegalArgumentException(args[0]);
        }
    }
}'''


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java-home", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    out = args.output.absolute()
    parent = out.parent.resolve(strict=True)
    checkout = ROOT.parent
    if parent == checkout or checkout in parent.parents:
        parser.error("output must be outside the checkout")
    # mkdir is atomic and fails for an existing directory, file, or symlink.
    out = parent / out.name
    out.mkdir(mode=0o700)
    classes = out / "classes"
    empty = out / "empty"
    classes.mkdir()
    empty.mkdir()
    probe = out / "Probe.java"
    probe.write_text(PROBE, encoding="utf-8")
    suffix = ".exe" if os.name == "nt" else ""
    java_home = args.java_home.resolve(strict=True)
    java = java_home / "bin" / ("java" + suffix)
    javac = java_home / "bin" / ("javac" + suffix)
    phase = SOURCES / "FlightPhase.java"
    policy = SOURCES / "MissionRouteClockPolicy.java"
    inputs = [Path(__file__).resolve(), java, javac, phase, policy, probe]
    report = {
        "scope": "Direct policy calls only; no live route, Mixin, server, world, or physical behavior.",
        "inputs_before": {}, "inputs_after": {}, "runs": {},
    }
    try:
        report["inputs_before"] = {str(p): digest(p) for p in inputs}
        for source in (phase, policy):
            (out / (source.name + ".snapshot")).write_bytes(source.read_bytes())

        def run(name, argv):
            try:
                completed = subprocess.run(argv, cwd=out, capture_output=True, timeout=30)
                stdout, stderr, status = completed.stdout, completed.stderr, completed.returncode
                report["runs"][name] = {"argv": [str(v) for v in argv], "exit": status}
            except subprocess.TimeoutExpired as error:
                stdout, stderr = error.stdout or b"", error.stderr or b""
                report["runs"][name] = {"argv": [str(v) for v in argv], "timeout": True}
                status = 124
            (out / (name + ".stdout")).write_bytes(stdout)
            (out / (name + ".stderr")).write_bytes(stderr)
            return status

        status = run("compile", [javac, "-encoding", "UTF-8", "-proc:none", "--release", "17",
                                 "-cp", empty, "-sourcepath", empty, "-d", classes,
                                 phase, policy, probe])
        if status == 0:
            for case in ("negative", "outbound", "turn", "mission"):
                status = run(case, [java, "-cp", classes, "com.wwdebug.autopilot.Probe", case])
                if status:
                    break
        report["inputs_after"] = {str(p): digest(p) for p in inputs}
        report["inputs_unchanged"] = report["inputs_before"] == report["inputs_after"]
        report["class_sha256"] = {str(p.relative_to(out)): digest(p)
                                  for p in sorted(classes.rglob("*.class"))}
        report["complete"] = (len(report["runs"]) == 5
                              and all(x.get("exit") == 0 for x in report["runs"].values())
                              and report["inputs_unchanged"])
    except (OSError, ValueError) as error:
        report["complete"] = False
        report["error"] = {"type": type(error).__name__, "message": str(error)}
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("complete" if report.get("complete") else "incomplete")
    return 0 if report.get("complete") else 1


if __name__ == "__main__":
    sys.exit(main())
