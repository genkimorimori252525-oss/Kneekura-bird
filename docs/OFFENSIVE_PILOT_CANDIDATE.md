# Private offensive pending-pilot candidate

This is a test-only source-copy experiment based on `d34594f`. It compiles the
checkout's source alongside artificial aircraft, world, snapshot, target
awareness, armament, terrain and setter classes. It does not edit production
sources or start Minecraft, a world, Gradle, or a GameTest.

The private candidate captures the pilot from the offensive provider's existing
mob gate, after the existing status lookup, and carries it with the existing
`ServerLevel` to the arbiter's offensive pending-write gate. Public
`AirCombatManeuverManager.applyControl(Entity): Optional` remains a wrapper.
The candidate does not bind energy or defensive proposals, change their direct
writers or deliberately held claims, or cancel prior base writes. It preserves
the old four-argument `CombatEvaluation` constructor but adds a record component:
record equality, generated methods, reflective inspection and runtime binary
compatibility are **not** established by the descriptor checks.

## Reproduce

Use Python 3, JDK 17, and an ordered trusted JSON array of absolute paths for the
fixed mapped Minecraft/Forge dependencies. The classpath artifacts are local
prerequisites and are not supplied by this repository. From the repository
root choose new output directories outside all checkout and world paths:

```sh
python3 ww-debug-benchmark/tools/observe_offensive_pilot_candidate.py \
  --mode baseline --fixture ww-debug-benchmark/tools/inspect_offensive_identity.py \
  --java-home /path/to/jdk17 --dependencies-json /path/to/classpath.json \
  --output /path/to/new-baseline
python3 ww-debug-benchmark/tools/observe_offensive_pilot_candidate.py \
  --mode candidate --fixture ww-debug-benchmark/tools/inspect_offensive_identity.py \
  --java-home /path/to/jdk17 --dependencies-json /path/to/classpath.json \
  --output /path/to/new-candidate
python3 ww-debug-benchmark/tools/inspect_offensive_pilot_descriptor.py \
  --baseline /path/to/new-baseline --candidate /path/to/new-candidate \
  --java-home /path/to/jdk17 --output /path/to/new-descriptor
python3 ww-debug-benchmark/tools/verify_offensive_pilot_comparison.py \
  --baseline /path/to/new-baseline --candidate /path/to/new-candidate \
  --descriptor /path/to/new-descriptor --output /path/to/new-comparison
```

Both source-copy runners deliberately return nonzero: baseline has three red
pilot/level swap contracts and both modes have eight injected exception cases.
Capture outer exits, inspect individual logs and the comparison report; a missing
case, unexpected failure, changed input or class origin is inconclusive. The
saved v4 candidate rejected both pilot swaps and a level swap, keeping the old
UUID marker and existing offensive state/aim. The artificial null-token case is
not proof of a reachable runtime state. Public wrapper and seeded no-target,
missing-target and no-gun controls observe the existing state/aim cleanup and
logs. Energy/direct and defensive-priority controls use synthetic state or
components, including an artificial logger reentry for the defensive claim.

Getter events and exceptions are fake, with hooks in both modes recognizing
the old public and new internal provider method names. They check the observed
status-before-pilot order and compare same-fixture output, but do not prove a
runtime hook or modded getter is side-effect-free. Candidate `pilotOf` bypasses
an `isMobPiloted` method hook while using the same underlying getter on the
observed source path. The classpath, Python/JDK installations, logs and hashes
are not authenticated by this experiment. Inspect saved class-load origins,
patches, input and class hashes before interpreting results.

The level/pilot checks compare only observed references at two points. They do
not detect A→B→A, the same pilot leaving and returning, concurrent or nested
callbacks after a check, changes within a provider, or stale same-UUID marker
ownership. Already executed base/direct writes cannot be retracted. The fake
armament never proves firing, no-friendly-fire, native setter success, real
Minecraft behavior, or air-combat safety. Prior red, failed fixture setup, and
source-copy evidence remain separate from any later production validation.

The `actual` mode copies the current worktree sources as bytes without applying
candidate transformations. It requires three expected hashes and checks that
all copied production files match their originals and no patches were emitted:

```sh
python3 ww-debug-benchmark/tools/observe_offensive_pilot_candidate.py \
  --mode actual --fixture ww-debug-benchmark/tools/inspect_offensive_identity.py \
  --java-home /path/to/jdk17 --dependencies-json /path/to/classpath.json \
  --expected-offensive-sha256 0bb0894840f420dce02b1ab0c57dcba6243865ea68d6c7f5aa9287341a7361e0 \
  --expected-facade-sha256 0ba31fa90b8327d81bc4c0b8452d6caced274341e9771a38bfbbebcfc4d00211 \
  --expected-arbiter-sha256 14a8109bfe3d75d52e8c222aa976627243b1b69384a4ee3f154334ea9fb0a434 \
  --output /path/to/new-actual
python3 ww-debug-benchmark/tools/verify_offensive_pilot_actual.py \
  --candidate /path/to/saved-v4-candidate --actual /path/to/new-actual \
  --output /path/to/new-actual-comparison
```

The comparison checks historical inputs against local Git commit `d34594f`
where production source paths have since changed. It compares saved copied
sources, fake stubs, exit codes and stdout while excluding the known terminal
warning; it does not authenticate the local Git objects or prove the runtime.
The saved actual-source run has 28 zero exits and eight intentional sentinel
exit 42 cases; its outer nonzero exit is expected and is not a blanket pass.
The descriptor checker can compare the saved baseline with the actual-source
classes; this is a static signature check, including the old four-argument
constructor, not proof that the extended record is fully compatible.
