# Defensive identity: source-copy investigation

This is a test-only continuation of [the baseline probe](DEFENSIVE_PILOT_STANDIN.md),
not a production fix or a Minecraft/Forge GameTest. The portable runners copy the
#214 production sources to a **new output directory**, apply a private source-copy
candidate, compile against supplied dependencies, and run fake-entity fixtures.
They do not modify production sources or access a world.

The candidate carries the existing defensive manager's captured pilot object and
server level through the defensive facade branch to the pending-write guard. It
keeps the public facade and defensive wrappers. When the current server-side mob
pilot or level has a different object identity and the saved references are
non-null, the candidate rejects the pending write and returns a local `NONE` with
no marker update. Existing removed/client/non-mob rejection and classification
remain separate. The base setter and defensive state changes and logs have already
happened and are not rolled back. `ATTEMPTED` means only that the adapter was
called; it does not establish that native setters succeeded.

The `inspect_defensive_identity_*` runners are based on the same candidate source:

- `matrix`: 19 scenarios, including distinct B and same-UUID distinct B, level
  swap, same pilot, synthetic claimed/no-proposal, fake energy/direct/offensive,
  real collision-probe code with fake world, fake terrain and existing gates.
- `exceptions`: fake getter RuntimeException and Error sentinel observations. Eight
  intentionally thrown cases exit 1; four mismatch cases reach no rejected getter
  and exit 0. The runner's outer exit 1 is expected and must not hide a compile
  error or a different exception.
- `wrappers`: direct calls to the public defensive and facade wrappers, including
  proposal, empty seat and risk suppression; plus same-pilot and swap controls.
- `level_exceptions`: four synthetic level-swap cases instrument the rejected
  getter; the candidate avoids that getter in these cases.
- `null`: fake code fabricates `CombatEvaluation` and invokes the private helper
  directly by reflection. Null pilot, null level, both null, and valid values are
  helper-level controls only. They do not establish that a real producer can
  return a null capture, nor do they exercise the outer rejection classification.

All fixtures use fake `isRemoved()` callback timing, world, awareness, aircraft
setter, neighbours and/or flight snapshot. `defense-claimed` depends on fake
logger reentry that reinstalls state; it is not proof of natural runtime reachability.
The weapon manager is not ticked; firing, friendly fire and other weapon safety
conditions are unproved. No claim is made about real takeover, same-pilot
unboarding/reboarding, ABA, concurrent/reentrant getter callbacks, identity changes
after the check, other direct writers, cleanup, physical collision avoidance or
pilot skill. Authority/marker labels and synthetic setter attempts do not prove
native input application. The candidate requires independent review and suitable
real MOD validation before any behavioral completion claim.

The final v2 source-copy SHA-256 values in the saved local evidence were:

```
ControlAuthorityArbiter.java     0bd7e22f7928de30e1c9621ae4cd16942c6723f395d7f7da278c998da4ca01c3
FighterCombatFacade.java         405b1d9cca93bddb8a7a379f1828a810a15f777093b9f9c19072c22038df858f
DefensiveAirCombatManager.java   4cf26f7412093458f35a06da0d2a7dc888116b58a697577b0d833febfd5659fb
```

The matrix, exception, wrapper, level-exception and null evidence all used these
same three source hashes and the same 11 relevant compiled class hashes; each
recorded unchanged inputs and classpath. `matrix-v2` differs from the earlier v1
candidate by moving one source comment. Since this changed class bytes, v1 class
results are not reported as v2 results. Evidence is locally under
`/workspace/issue7-evidence-20261104/defensive-pilot-identity-decision-*-v2/` and
`defensive-pilot-null-capture-v1/`; associated `-outer/` directories record outer
exits. These local paths are not published artifacts. Earlier compile errors,
failed candidate variants and their evidence were retained.

Each portable runner accepts `--java-home`, `--dependencies-json`, `--output` and
`--policy candidate`. Follow the dependency and fresh output instructions in the
baseline document. The matrix, exceptions and wrappers runners also accept
`--policy baseline`; baseline swap assertions fail. The `null` runner only applies
to the candidate because it directly names candidate-only records and helper.
A missing sentinel, unexpected individual exit, failed compilation or changed
input makes the relevant observation inconclusive. Output events and getter counts
are observations of the fake fixture, not runtime instrumentation.
