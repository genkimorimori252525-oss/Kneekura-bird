# Formation pending pilot-reference observation

This is a **private source-copy experiment**, based on the checkout's #209
`e3fe81a` production sources. The runner writes copied sources to a new output
directory and modifies only the copies of `FormationFlightManager` and
`ControlAuthorityArbiter` in candidate mode. It never edits production source,
starts Minecraft, runs Gradle, or accesses a world.

The candidate reuses the `pilotOf` call already made by the formation mob gate,
together with the `ServerLevel` reference already obtained there. It passes
those references in a package-private result and compares them at formation's
pending write, reusing the getter calls already made by the #209 write gate.
The existing public `FormationFlightManager.applyControl(Entity):ControlOutcome`
is a wrapper. The original two-argument pending helper is left unchanged for
combat; a separate formation helper contains a small amount of duplicate gate
logic. Direct collision writes and outcomes with no pending proposal retain the
existing path. A rejected pending proposal uses #209's existing rejection path:
its marker is not updated and may remain stale. The setter adapter's return
means an attempted call, not native setter success.

## Run and inspect

Use Python 3, JDK 17, and a trusted, ordered JSON array of absolute mapped
Minecraft/Forge and library classpath paths. Dependencies and the local evidence
manifest are not supplied by this repository. From the repository root, choose
**new** output directories outside all world and checkout paths:

```sh
python3 ww-debug-benchmark/tools/observe_formation_owner_candidate.py \
  --mode baseline --java-home /path/to/jdk17 \
  --dependencies-json /path/to/classpath.json --output /path/to/baseline
python3 ww-debug-benchmark/tools/observe_formation_owner_candidate.py \
  --mode candidate --java-home /path/to/jdk17 \
  --dependencies-json /path/to/classpath.json --output /path/to/candidate
python3 ww-debug-benchmark/tools/inspect_formation_owner_descriptor.py \
  --baseline /path/to/baseline --candidate /path/to/candidate \
  --java-home /path/to/jdk17 --output /path/to/descriptor
python3 ww-debug-benchmark/tools/verify_formation_owner_comparison.py \
  --baseline /path/to/baseline --candidate /path/to/candidate \
  --descriptor /path/to/descriptor --output /path/to/comparison
```

Record outer process exits separately. The first two runners intentionally exit
nonzero: baseline includes formation and combat A→B contract failures;
candidate retains the two combat failures, and both contain intentional getter
exceptions. A missing report/case, changed inputs, unexpected class origin, or
unrelated failure is inconclusive. The verifier checks the saved per-case exits,
input/classpath hashes, sentinel identities, 17 normalized getter traces, and
public descriptor. It does not turn the observational cases into passes. Check
class-load logs and patches separately. The `classes/` directory contains both
production-source copies and fake classes. Hashes do not authenticate inputs,
rule out transient mutation, or pin the complete JDK/Python environment.

The saved v5 baseline has four red identity contracts; candidate fixes the two
formation cases while the two combat cases stay red. The synthetic pending-level
getter callback has its own baseline red and candidate green. Eight ABA,
transient dismount, level-change, and direct-manager-reentry cases remain
observations, even if they exit zero. Same UUID on distinct fake Mob objects is
an identity test, not proof that the real runtime permits those objects.

Fake getter tracing classifies a call by the first relevant **ancestor** in the
stack, not necessarily its immediate caller. RuntimeException and Error sentinels
are artificially injected at formation and pending gate getter sites; the
preserved identity and ordered trace do not prove the real getters can throw or
reenter. The normal direct, claimed-without-proposal, terrain flag, collision,
player, empty, client and removed tests use artificial state and components.
No actual takeover, Minecraft logical side, world geometry, native setter,
concurrent mutation or transformed class is verified.

No endpoint-reference check detects A→B→A, an intervening dismount/reboard of
the same object, or a change after its final check. Reentry and runtime hooks
(including hooks on `isMobPiloted`, whose internal call is replaced by a direct
`pilotOf` call) remain unverified. The formation provider's captured references
may also become stale during its own calculation. Earlier base and direct writes
are not undone, and combat pending is intentionally outside this candidate.
