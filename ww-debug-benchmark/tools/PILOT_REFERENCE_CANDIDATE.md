# Private pending-pilot candidate observations

These are test-only experiments stacked on the red pilot-identity fixture. They
compile copied production sources together with synthetic entities, level,
snapshot, checkpoint, terrain, combat and setter classes. The source checkout
is not modified by the runners. No Minecraft world, MOD, Gradle or GameTest is
started. The saved source base is `e3fe81a`, with arbiter source SHA-256
`eb98d82a4c319a7714230824efd3bab8868b1982e37093660a64e05a8563c202`.

Use JDK 17, Python 3 and a trusted ordered JSON array of existing absolute paths
for the mapped Minecraft/Forge and library classpath. From the repository root,
choose a new output directory outside the checkout and all world directories:

```sh
python3 ww-debug-benchmark/tools/observe_pilot_candidate.py \
  --expected-arbiter-sha256 eb98d82a4c319a7714230824efd3bab8868b1982e37093660a64e05a8563c202 \
  --java-home /path/to/jdk17 --dependencies-json /path/to/classpath.json \
  --output /path/to/new-candidate-evidence
python3 ww-debug-benchmark/tools/observe_pilot_getter.py \
  --expected-arbiter-sha256 eb98d82a4c319a7714230824efd3bab8868b1982e37093660a64e05a8563c202 \
  --java-home /path/to/jdk17 --dependencies-json /path/to/classpath.json \
  --output /path/to/new-getter-baseline-evidence
python3 ww-debug-benchmark/tools/observe_pilot_getter.py --candidate \
  --expected-arbiter-sha256 eb98d82a4c319a7714230824efd3bab8868b1982e37093660a64e05a8563c202 \
  --java-home /path/to/jdk17 --dependencies-json /path/to/classpath.json \
  --output /path/to/new-getter-candidate-evidence
```

The candidate runner modifies **only the private arbiter copy**, recording its
patch, original and copied sources, stubs, class hashes, class-load logs, per-case
exits, stdout/stderr and input/classpath hashes before and after. Its public
`applyControl(Entity): Authority` source signature remains unchanged. Capture
outer process exits separately. The hashes do not authenticate inputs, pin the
complete JDK, or rule out intermediate mutation. An absent report, unexpected
origin, modified input, wrong patch or unrelated failure is inconclusive.

The candidate captures pilot and level references separately before formation
and combat providers, then checks the corresponding references at the pending
setter. Existing removed/client/mob checks and rejection marker behavior remain
in the copied source. On the saved v2 fixed-fixture run, four distinct-pilot
contract cases that were red in the prior source fixture pass; same-pilot and
existing gate, collision, terrain and fake combat controls pass too. There are
19 assertion cases and eight **observational** cases among the 27. The latter
include fake A-to-B-to-A, empty-to-same-A, level replacement and manager reentry;
a zero exit does not qualify them as safety passes. A same-UUID distinct-object
case is an artificial identity contract, not proof of real-world reachability.
Provider-internal ABA, stale marker ownership, reentry or pilot change after the
check, actual getter behavior and successful native setter execution remain
unproved. Earlier base or direct writes are not cancelled.

The separate getter runner uses an instrumented fake getter that can switch the
pilot, throw or reenter the manager **only when its call stack identifies the
new direct `MobPilotGate.pilotOf → ControlAuthorityArbiter.decide` capture**.
It records normal and fake combat-direct paths separately. In saved v3
observations a stable getter was called 4→6 times for formation and 3→5 for
direct. In the candidate only, a synthetic exception at that additional call
occurs after base control and before fake combat, exiting 1; fake reentry adds a
base call. These are deliberately stack-aware artificial counterexamples, not
proof that a Minecraft or MOD getter throws, reenters, or has these effects.
The `throw` and `direct-throw` candidate cases and outer runner intentionally
exit nonzero. Getter stdout is observation, not a safety verdict.

The first saved getter setup outer record exited 2 because `runner.py` was
missing. The setup generator's separate syntax error appeared in the execution
tool response; its text was not captured in that outer record. Later evidence
was written to new directories and the earlier record was retained.
