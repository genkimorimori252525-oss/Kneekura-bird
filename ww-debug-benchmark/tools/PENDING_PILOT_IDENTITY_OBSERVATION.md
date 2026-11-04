# Pending proposal pilot identity observation

This test-only probe compiles **unmodified copies** of the checkout's arbiter,
manager, session, formation manager, and other named control sources alongside
synthetic entities, world, checkpoint, snapshot, terrain, combat and setter.
It does not run Minecraft, Forge, a real aircraft or GameTest. The fixture's
world ignores AABBs, its clip always misses and its setter merely records calls.

From the repository root, provide a JDK 17 and a trusted, explicitly ordered
JSON array of absolute paths to existing mapped Minecraft/Forge and library
classpath entries. Use a new evidence directory outside all worlds and the
checkout:

```sh
python3 ww-debug-benchmark/tools/inspect_pilot_identity.py \
  --expected-arbiter-sha256 eb98d82a4c319a7714230824efd3bab8868b1982e37093660a64e05a8563c202 \
  --java-home /path/to/jdk17 --dependencies-json /path/to/classpath.json \
  --output /path/to/new-evidence
```

The runner checks the expected arbiter SHA, verifies all 11 source copies match
their inputs, forbids generated patches, and records per-process exits, logs,
class-load origins and before/after hashes. Capture the outer process exit
separately. Missing records, changed input or classpath, unexpected class
origins or unrelated failures make a run inconclusive. Hash checks do not
authenticate the JDK, dependency artifacts, or output and cannot exclude an
intermediate mutation.

`formation-swap` changes the target pilot after real formation slot guidance has
been computed and its fake adapter log has been captured. `combat-swap` constructs
a **fake** combat pending proposal while pilot A is still present and then
changes the pilot before returning that proposal. In each case A and B are
separately allocated Mob objects with different fixed UUIDs; the fake setter
records the actual pilot object reference on each call. The first base call is
made while A is present. The candidate contract requires that the pending call
not be sent after A changes to B. With the recorded source (SHA above), both
cases exit 1 at that contract assertion and print a second setter called with B.
This is a synthetic red, not evidence that the callback happens in a live world.

The same-UUID cases use a distinct B object with an equal UUID and assert both
reference inequality and UUID equality before the same no-pending contract. They
are separate red cases; no claim is made that two such live entities can coexist
or exchange a seat. The same-pilot cases reassign the **same A object**, without
removing it, and expect normal formation or fake-combat pending control.
Player, empty, client and removed callbacks are checked in both proposal paths;
formation-terrain, collision direct writer, risk-only, fake combat direct writer,
and claimed-without-proposal have separate controls. These controls preserve
only the tested stand-in call counts and values.

A-to-B-to-A and empty-to-the-same-A, alternate fake level, and fake reentry by
calling the manager are explicitly `INCONCLUSIVE` observations. Comparing only
pilot references at two endpoints cannot detect intermediate changes, and the
reentry is not a full Minecraft/arbiter reentry. The UUID-keyed marker is seeded
artificially and printed; it does not prove live server marker ownership. Prior
base/direct calls, setter success, other writers, player takeover, real terrain,
collision clearance, concurrency and actual aircraft safety remain unverified.
The returned authority is a label, not proof that an input was applied.
