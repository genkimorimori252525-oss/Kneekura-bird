# Early formation gate: collision-writer counterexample

`observe_early_formation_collision.py` is a test-only, standalone reproduction of an unsafe hypothetical source change. It copies the #226 recorded-turn runner and eleven #214 sources into a **new** output directory, runs the unchanged sources, and runs another copy after injecting only `phase == FlightPhase.TURN_RIGHT` into the early `FormationFlightManager` eligibility condition. It never changes production source or starts Gradle, Minecraft, or a world.

For the synthetic collision scenarios, the expected counterexample is the same `COLLISION_AVOIDANCE` label on both copies, but two fake setter calls on baseline and only the base call after injection. The collision adapter assertion consequently exits 1 on the changed copy. The changed copy also deliberately suppresses formation, so its two grouped assertions exit 1. The wrapper checks those four expected reds, the successful baseline and controls, recorded setter order, adapter absence, two terrain controls, source-copy identity, per-run classpath and input hashes, and key class origins. It returns 0 with `EXPECTED_COLLISION_COUNTEREXAMPLE` only when all checks match. Its 0 means the counterexample was reproduced, not that the injected change is safe.

This is a synthetic world, terrain planner, aircraft and setter. The artificial collision places the leader three blocks away; it does not establish separation, native setter success, actual player takeover or aircraft dynamics. The same-tick leader and follower recordings are not proven simultaneous. Collision-risk labels do not alone prove a collision-avoidance input. Other phase policies and safe alternatives are outside this experiment.

Use JDK 17 and a trusted JSON array of existing absolute mapped Minecraft/Forge and library classpath entries, as required by `test_formation_recorded_turn_observation.py`. Choose an output that does not exist, outside the checkout and every Minecraft/world directory. The parent directory must already exist. The runner explicitly rejects existing outputs and leaves logs and copied inputs in place on failure. The tool is not a sandbox.

```sh
python3 -I -B tools/observe_early_formation_collision.py \
  --java-home /path/to/jdk17 \
  --dependencies-json /path/to/explicit-classpath.json \
  --output /path/to/new-output
```

The local dependency array and historical results are not part of the repository. Review `summary.json`, `injected.patch`, the per-mode `outer-result.json`, `run/report.json`, case stdout/stderr and class-load logs. An unavailable dependency, missing case/report, input mismatch, class-origin mismatch, different failure, timeout or changed source is `INCONCLUSIVE` and exits nonzero. Failure evidence is retained; do not remove or overwrite it to retry. The candidate's inherited `expected_base` metadata is a historical expectation and does not describe its intentionally modified source: identify it by the patch and hashes.

The runner pins the historical #226 fixture and #214 source hashes and rejects any different revision rather than treating a new checkout as equivalent. The subprocess group timeout applies only to the isolated stand-in runner it starts; this is not process or network isolation for untrusted inputs. The result is one counterexample to this specific early return, not a complete safety review.
