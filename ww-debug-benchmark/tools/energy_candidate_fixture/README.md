# Private energy pending-owner candidate

This is a **test-only source-copy experiment**, not a production change. Its
base is the #224 fixture on #222: local `38dadc5ec904bd0e16ca8cd819b90db7f5ba843c`,
tree `880f7be1ac3d69896c810350233fe2fbed2de916`. A runner creates private
copies of 19 sources; four are transformed under a new evidence directory and
never written back to the checkout. The generated patch is saved for review.
The world, entities, armament, logs, setter and callbacks are fake, and energy
state is seeded artificially. Runtime takeover and actual MOD behavior are
not established.

The candidate carries the existing energy-level and mob reads through the
facade to the pending arbiter write. For DOCTRINE it also carries offensive's
own existing level and mob reads and requires both contexts to match the
current references. This is necessary because the reads occur at separate
times and alignment uses aim computed by the inner layer. After the inner mob
gate succeeds, the candidate preserves that identity in its empty result too:
an empty proposal need not imply that no aim was computed. An empty inner
context with a later nonempty energy proposal is rejected conservatively;
whether that path is reachable and its compatibility impact are untested.
No new pilot getter is intentionally added. The existing public energy and
offensive `Optional` wrappers remain, but internal callers change to a new
evaluation method, so external hooks/Mixins remain unverified.

The existing facade priority and its `claimedWithoutProposal` path are kept.
Fallback proposals retain their offensive authority; final-alignment and
CLIMB/PIVOT/CAPTURE proposals retain energy authority. Identity mismatch
returns local NONE without updating the authority marker; that old marker can
remain stale. Player, empty, removed and client rejections keep the existing
generic rejection behavior. The candidate does not undo base inputs or
energy/offensive state, aim and logging already produced. Reference endpoint
comparisons cannot prove continuity or prevent all ABA or post-check changes.

## Saved observations

With identical explicit inputs, local `energy-doctrine-candidate-baseline-v5/`
compiled successfully and had eleven expected contract failures and fifteen
other outcomes with exit 0, including two caught injected exceptions.
`energy-doctrine-candidate-v5/` compiled and gave 26 exit-0 outcomes, again
including those two intentional exception observations. The eleven artificial
failures cover different mob, a different
mob with the same UUID, energy A/inner B and energy A/inner B/final A,
final-alignment pilot change, final level change, outer-level A/inner-level
B/final A, mob changes in CLIMB, PIVOT and CAPTURE, and the explicit fake
reentry case below. Controls cover same
pilot in both DOCTRINE branches and those three other stages, player/empty/
client/removed gates, selected fake collision and terrain paths, and one
no-gun empty proposal that retains the energy claim. The level inner reference
is inferred from fake callback order and code flow, not separately logged.
The candidate's rejected cases assert that an unrelated authority marker and
the pre-existing marker remain unchanged. These tests are artificial callbacks,
not evidence that an actual user can take over at those moments.

In the additional artificial reentry case, a fake logger callback changes the
offensive action to NONE after aim creation. The inner proposal is empty while
the retained aim produces final alignment. With unchanged A, baseline and
candidate both attempt alignment; when the pending hook changes A to B, the
baseline writes and the candidate rejects. Neither natural reachability of the
reentry nor aim provenance in actual gameplay follows from this experiment.
Two additional fake getter injections throw a sentinel at the outer or inner
pilot lookup. Each comparison propagates the identical per-run exception
object, retains the earlier fake base write and preserves both markers. A
separate local comparison recorded identical fake energy/offensive level and
pilot getter sequences across all 26 cases. Those sampled fake sequences are
not proof of purity, exceptions or ordering for runtime implementations.

Baseline had 79 generated classes; candidate 80. Both source/copy, input,
classpath and per-case stage hashes matched at recorded points. Compile
produced one deprecation warning for a fake resource identifier. Other getter
exceptions and side effects, inner-empty with a missing identity context,
native setter success, actual weapons/friendly fire, runtime hooks and real
MOD remain unverified.

`energy-doctrine-candidate-descriptors-v1/` compared `javap -public -s`
output for the energy adapter, facade, arbiter and offensive manager on the v3
source trees, whose production-source hashes match v5: these four public outputs matched.
It also recorded private `CombatEvaluation` output: old four- and five-argument
constructor descriptors remain, while an energy record component is added.
Record equality, `toString`, reflection and external consumers may change;
offensive empty `OffensiveEvaluation` metadata also changes. These checks do
not prove binary, Mixin, reobfuscation or dynamic runtime compatibility.

## Reproduce

Use a trusted JDK 17 and an ordered JSON array of absolute, existing trusted
mapped dependencies. Inputs and classpath are not authenticated; the runner is
not a sandbox. Pick two fresh private directories outside any checkout/world:

```sh
python3 ww-debug-benchmark/tools/inspect_energy_identity_candidate.py \
  --mode baseline --java-home /path/to/jdk17 --dependencies-json /path/to/deps.json \
  --output /path/to/new-baseline
python3 ww-debug-benchmark/tools/inspect_energy_identity_candidate.py \
  --mode candidate --java-home /path/to/jdk17 --dependencies-json /path/to/deps.json \
  --output /path/to/new-candidate
```

The baseline outer exit 1 is expected but can also mean a setup or unrelated
failure: inspect each branch, exit code and stderr, not the outer status alone.
The candidate comparison changes the test-only stack observer to recognize the
new method name in both modes and instruments the fake logger and level getter;
it does not show actual runtime hook behavior.
Inspect `candidate.patch`, source and dependency hashes, stdout/stderr and class
origins. Snapshots do not establish uninterrupted integrity or trusted inputs.
