# Private source-copy formation candidate

This is an isolated experiment, not a production change or a Minecraft
GameTest. The runner copies the checkout's named sources under a new output
directory and transforms **only those copies** of `AutonomousFlightManager` and
`ControlAuthorityArbiter`. It saves the copied sources, unified patches, hashes,
generated classes, command exits, per-case stdout/stderr, class-load logs and a
runner snapshot. Original checkout sources are also hashed before and after.
The fake checkpoint, level, entities, terrain planner, combat facade, setter and
logger are test fixtures. They do not represent real aircraft physics or a
server. The fake level ignores the entity-query AABB and raycasts always miss.

The private candidate retains the public `applyControl(Entity): void` descriptor.
It records the manager's **attempted adapted setter arguments**, never proof that
the native setter applied them. It associates the record with object/level,
session entry, generation and session fields, and checks them again immediately
before a normal `FORMATION` pending proposal would be written. If its record is
accepted it writes the adapted arguments again; otherwise it falls back to the
original formation proposal. The candidate leaves the existing FORMATION
authority and formation adapter log intact, so those records describe the
proposal rather than proving the actual final setter values.

This candidate is **not approved for production**. In artificial callbacks after
formation proposal creation, changing the fake pilot to player or empty, or
changing the fake level's client flag, makes both unmodified baseline and
candidate issue a second setter call. The fixture marks those cases red against
its no-additional-setter expectation. Callback activation of the fake terrain
marker instead leads both versions to suppress that second write. These
callbacks are synthetic; whether the corresponding changes can happen in a real
runtime at that exact point is unknown. The existing arbiter behavior and the
candidate fallback therefore cannot be called safe on the basis of this test.

The candidate cases also cover recovery/recovery release, collision writer,
terminal collision-risk-only, injected terrain, player/empty/client before
entry and fake combat claims/direct/pending. The last three are fake facade
behaviors, not real combat. `other-pending` checks only the candidate's
formation-authority predicate with synthetic proposals; it does not inject a
non-formation proposal into the real formation manager. Stale, same-UUID
replacement, fake hold/combat changes and fake setter reentry test the observed
fallback under the fixture's specific setup. The fallback is not a safety
verdict. The candidate's generation and field checks do not prove thread safety,
prevent all concurrent changes, or detect arbitrary change-and-restore (ABA).
The real hold adapter, native setter, Minecraft/Forge runtime, actual takeover,
terrain planner, other writers and real MOD telemetry are not exercised.

## Run

Use a trusted JDK 17 and an explicit JSON array of absolute paths to the existing
mapped Minecraft/Forge and library dependencies. The output path must not exist
and must be outside the checkout and all Minecraft/world directories. This
runner is not a sandbox. From `ww-debug-benchmark`:

```sh
python3 tools/observe_private_formation_candidate.py \
  --java-home /path/to/jdk-17 \
  --dependencies-json /path/to/dependencies.json \
  --output /path/to/new-candidate-output

python3 tools/observe_private_formation_candidate.py \
  --java-home /path/to/jdk-17 \
  --dependencies-json /path/to/dependencies.json \
  --output /path/to/new-baseline-output --baseline-callbacks
```

Capture each outer process exit separately. The baseline option uses unmodified
source copies and runs only the four artificial callback cases. Its report's
inherited `scope` string incorrectly says "PRIVATE CANDIDATE SOURCE COPIES";
check the recorded command, saved sources and lack of candidate patch files to
identify that run. This is a metadata limitation, not evidence of a candidate
being applied to baseline. Each red callback makes the runner exit nonzero.
Inspect every case, its actual class origin, source/fixture hashes and before/
after stability; missing records or unrelated failures are inconclusive. Hashes
do not authenticate inputs, prove the complete JDK, or prevent transient change.
