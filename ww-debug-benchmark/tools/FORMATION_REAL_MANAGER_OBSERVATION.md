# Formation recovery observation with the autonomous manager

This is a standalone characterization, not a Minecraft GameTest. The runner
compiles the actual checkout's `AutonomousFlightManager`, `AutopilotSession`,
`FormationFlightManager`, `ControlAuthorityArbiter`, `AirspaceSafetyProbe`,
`MobPilotGate`, profile, phase and control value types together with test-only
stand-ins. No Minecraft server or world is started. No aircraft behavior is
changed by this runner.

The fake checkpoint sets a newly created real session to a fixed TURN_RIGHT
state immediately after the real manager creates it. The terrain planner and
its active marker, snapshot, entities, level, profile lookup, logging, and
reflective aircraft setter are stand-ins. The fake server level's entity query
ignores the requested AABB; its clip always returns MISS. The fake terrain
planner injects a consistent decision/marker without modeling terrain. The
player case first creates a session using a fake mob and then replaces the pilot
on that same fake entity. These fixtures do not establish natural session
creation, takeover, world geometry, terrain avoidance, collision clearance,
flight physics, other writers, or the cause of the recorded A6M timeout.

## Run and inspect

Use JDK 17 and a trusted JSON array of absolute paths to existing mapped
Minecraft/Forge and library dependencies. From `ww-debug-benchmark`, use a
new output directory outside the checkout and all Minecraft/world directories:

```sh
python3 tools/test_formation_turn_recovery_real_manager.py \
  --java-home /path/to/jdk-17 \
  --dependencies-json /path/to/explicit-classpath.json \
  --output /path/to/new-observation-directory
```

The output directory must not exist. The runner is not a sandbox: use trusted
inputs and a controlled directory. All named production and stand-in sources
are compiled in **one** javac invocation into `production/`; that name does
not mean all classes there are production classes. `fixture/` is empty in this
runner. Source and generated-class hashes, classpath hashes sampled before and
after, runner snapshot, command exits, stdout/stderr and individual JVM class
load logs are saved. Those hashes do not authenticate the inputs or prevent
intermediate changes. Check all nine command exits and the process exit, hash
stability, relevant class origins and the source hashes against the intended
checkout. An absent report/case, unexpected class origin, changed input or
nonzero result is inconclusive.

The real session's JSON frame is captured by the fake log sink **before** the
manager's terrain/native adapters and before later formation writes; it is a
planned control record, not the final applied control. The fake aircraft setter
records each subsequent call in order. Each case asserts the reported authority,
real collision probe result on the fake entities, expected setter sequence,
and adapter reason where applicable. Paired grouped/ungrouped cases change only
the target's group tag while holding UUID, geometry, snapshot and phase fixed.
Separately, the collision and collision-timeout cases change the phase-tick
boundary with the same fake near geometry; terrain and collision-terrain inject
a fake terrain decision. The two collision label cases must be read with the
actual setters, since a label alone does not prove that a collision avoidance
command was written.

This runner characterizes specific fixed inputs. It neither replaces real MOD
GameTests nor establishes safe behavior in untested situations.
