# Formation turn-recovery observation (stand-alone draft)

This is a test-only characterization, not a Minecraft GameTest. It compiles the
actual `AutopilotSession`, profile, formation manager, authority arbiter,
collision probe, pilot gate, and their small control value types from this
checkout. It supplies stand-in entities, world, snapshot, aircraft setter,
terrain flag, log, combat managers, and **AutonomousFlightManager**. The fake
manager calls the real session once and passes its returned values directly to
the fake setter. It does not reproduce the real manager's adapter, terrain
planner, cleanup, or Minecraft tick lifecycle.

## Run

Use JDK 17 and a trusted, explicitly ordered classpath JSON array containing the
mapped Minecraft/Forge and library dependencies needed to compile these sources.
The classpath may contain directories and JARs; paths must be absolute, exist, and be readable.
Prepare the classpath from your own fixed development environment: this draft
does not resolve or download dependencies. For example, in the original cloud
workspace a previously recorded classpath was available at
`/workspace/issue7-evidence-20261104/postphysics-standin-repo-v2/dependencies.json`.
It is local evidence, not a repository dependency or a portable path.

From `ww-debug-benchmark`, choose a **new**, writable output path outside the
checkout and all Minecraft/world directories. Its parent must already exist.
Do not use an output directory containing evidence to retain: creation fails if
it exists.

```sh
python3 tools/test_formation_turn_recovery_standalone.py \
  --java-home /path/to/jdk-17 \
  --dependencies-json /path/to/explicit-classpath.json \
  --output /path/to/new-observation-directory
```

The runner compiles with annotation processing disabled and empty sourcepath,
then runs each case in a fresh JVM. It writes sources for the stand-ins, class
files, a runner snapshot, stdout/stderr, JVM class-load logs and `report.json` in
the new directory. Inputs and classpath entries are hashed before and after;
this does not authenticate a JDK, classpath, or source, prevent concurrent
changes between hashes, or prove which class was loaded. Inspect class-load
logs and compare hashes against the intended fixed checkout and dependencies.
Report generation can be interrupted, including by timeout or unreadable input;
a missing report, missing case, nonzero exit, changed input or classpath, or
unexpected class origin is inconclusive. Check all eight command exits and the
process exit, not merely that a report exists. The runner assumes trusted local
inputs and a controlled output directory; it is not a sandbox.

## Inputs and interpretation

The fixed target and leader aircraft UUIDs are `(0,2)` and `(0,1)`; their
mob pilot UUIDs are `(0,3)` and `(0,4)`. The player pilot also has `(0,3)`.
In the `grouped` and `ungrouped` cases, only the target's group tag is
intentionally changed; other fixture inputs, including UUIDs, are fixed. They
start at `TURN_RIGHT` phase tick 439 and use the same synthetic speed, profile,
heading and leader geometry. The real session returns `turn_speed_recovery` in
both. The fixture asserts `FORMATION`, two fake setter calls and final engine
0.08 for grouped, versus `BASE_AUTONOMY`, one fake setter call and engine 1.0
for ungrouped. These exact values describe this artificial fixture only.

Additional separate cases observe a fake terrain-active branch, a collision
prediction using stand-in geometry, a player through fake-manager cleanup, and
the session timeout boundary. The terrain case does not run terrain avoidance;
the player case does not establish real takeover safety or other writers. No
case proves real separation, safe priority handling, flight motion, or the
cause of the recorded formation timeout. No claim is made that the recorded
A6M trajectory was replayed. Compare only the structured `case=` lines between
runs; logging may include timestamps and environment-dependent warnings.
