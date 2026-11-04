# Energy DOCTRINE pending-pilot synthetic red

This test-only investigation starts from #222 local commit
`5fd733014253be72e4f796a419477899ed43053f`, tree
`f92aaf03e1f455a1507b473c7a2d76411e0eab66`. It compiles **unmodified** copies
of 19 production sources including the energy adapter, offensive manager,
facade and arbiter. World, aircraft, armament, snapshot, awareness, terrain,
telemetry and native setter are artificial. Reflection seeds an energy state
directly into `DOCTRINE`; this does not show a real aircraft can naturally
reach that state or encounter the callback used below.

The fake aircraft's `isRemoved()` callback runs inside the arbiter's generic
pending-write gate. Before swapping the pilot it requires the energy and
offensive pilot reads, an offensive aim and adapter log, and the requested
alignment branch. Base control has already made one fake setter call with mob A.
When alignment is absent, energy passes through the actual offensive proposal
and its `OFFENSIVE_COMBAT` authority. When present, energy selects the actual
final-alignment proposal with `ENERGY_FIGHTER_REENGAGEMENT` authority. Both
reach the generic pending guard, which rechecks mob type but not the identity
seen during evaluation. A separate artificial case changes the pilot between
the outer energy read and inner offensive read; these two contexts differ.

The saved v3 local run compiled successfully with one fake `ResourceLocation`
deprecation warning. Eight controls exited 0: same-A for both branches,
player, empty, client, removed, fake collision suppression and fake terrain
abstention. Four cases exited 1 on the explicit contract
`CONTRACT: no stale energy pending write after ownership change`: fallback
distinct B, fallback distinct object B with A's UUID, outer-A/inner-B, and
alignment distinct B. Before that assertion each records the A base write,
the reached pending hook and, if a later fake setter occurs, its exact B object
reference. These are expected reds, **not** passing tests or actual MOD results.
The result exposes neither native setter success nor real callback timing.

Earlier v1 failed an additional terrain fixture assertion because it assumed
the offensive getter was never called; the code actually calls it and then
abstains on the fake terrain condition. V2 corrected that assertion but did not
directly assert the second fake setter's reference identity. Both failures and
records are kept; v3 adds the conditional object-identity check. Earlier base
writes, energy/offensive state and aim changes and logs are not rolled back.
No statement about continuous ownership, ABA changes, post-check reentry,
player takeover in Minecraft, real weapons, friendly fire, or terrain and
collision safety follows from this fixture. The collision/terrain cases check
only the selected fake paths.

## Run

Supply a trusted JDK 17 and a JSON array of absolute paths to the ordered,
trusted mapped Minecraft/Forge classpath entries used for compilation. The
runner loads fake definitions from the adjacent `inspect_offensive_identity.py`;
it is not a sandbox and must only be used with trusted checkout, JDK and
dependencies. Choose a new evidence directory outside checkout and any world:

```sh
python3 ww-debug-benchmark/tools/inspect_energy_doctrine_identity.py \
  --java-home /path/to/jdk17 --dependencies-json /path/to/dependencies.json \
  --output /path/to/new-private-evidence
```

Exit 1 is expected for the four intentional reds; it can also represent other
failures. Inspect each saved stdout/stderr, branch assertions, process exit,
class-load logs, source/copy hashes and stage/output hashes. Compile errors,
different assertions, timeouts, missing cases or changed inputs are
inconclusive. Per-case hash snapshots are not proof of uninterrupted integrity;
the runner does not authenticate its inputs or scrub the entire JVM
environment. Local evidence includes environment-specific paths and must be
reviewed before publication. Do not interpret the outer exit alone as success.
