# Formation recovery capture: source-copy observation

`observe_formation_recovery_frame.py` adapts the earlier #207 test-only fixture to the fixed #214 production sources. It creates source copies and stand-ins in a **new** output directory and compiles the named session, manager, arbiter, formation, profile and collision-probe sources. It never edits production code, launches Gradle or Minecraft, uses a world, simulates aircraft motion, or verifies a native setter.

Use JDK 17 and a trusted JSON array of absolute existing mapped Minecraft/Forge and library classpath entries. Choose a different, nonexistent output directory for every invocation, outside the checkout and all Minecraft/world directories; its parent must already exist. The runner refuses an existing output with `FileExistsError` and a nonzero exit before creating a report or modifying it. It is not a sandbox.

```sh
python3 -I -B tools/observe_formation_recovery_frame.py \
  --mode baseline --java-home /path/to/jdk17 \
  --dependencies-json /path/to/classpath.json --output /path/to/new-baseline
python3 -I -B tools/observe_formation_recovery_frame.py \
  --mode bound --java-home /path/to/jdk17 \
  --dependencies-json /path/to/classpath.json --output /path/to/new-bound
python3 -I -B tools/observe_formation_recovery_frame.py \
  --mode unbound --java-home /path/to/jdk17 \
  --dependencies-json /path/to/classpath.json --output /path/to/new-unbound
python3 -I -B tools/observe_formation_recovery_frame.py \
  --mode nested --java-home /path/to/jdk17 \
  --dependencies-json /path/to/classpath.json --output /path/to/new-nested
```

`baseline` checks the unchanged #214 source with the bound candidate's contract; the grouped and fake prior-writer cases are intentionally red. `bound` runs those and the other stand-in cases with an experimental same-call recovery frame. `unbound` intentionally removes two pilot-reference comparisons and expects the artificial mob-swap case to fail. `nested` injects arbiter reentry separately from the direct-manager reentry case. The wrapper exits 0 as `EXPECTED_OBSERVATIONS_NOT_SAFETY` when its mode's expected observations, including the expected reds, are present. After output creation, a compile failure, wrong assertion, missing record, changed input, class-origin mismatch, different source hash, timeout or other error is `INCONCLUSIVE` and exits nonzero. Inspect `report.json`, per-case stdout/stderr and class-load logs, source patches, outer exit and runner snapshot. Case exit 0 for a fallback marked `*_NOT_SAFETY` records only that observation.

The tool pins the 11 #214 source SHA-256 values. Each report records the runner, original and generated source, fixtures, compiler/classpath files before and after, commands, case exits, generated class hashes, and selected actual class origins. The `production` output includes both real-source and fake classes, while `fixture` is empty; do not interpret those directory names as provenance. Class origins are checked for one representative case per mode, and compiled hashes are captured once after all cases; the tool does not prove the origin or stability of every case. On an interrupted run, later inventories may be absent. Hashes do not authenticate the JDK, inputs or runtime, or exclude transient change. The dependency array and historical local results are not provided by the repository.

The fake profile and snapshots are synthetic; they are not the exact #214 recorded-input replay. Bound mode keeps #214's pending pilot/level gate, captures a frame before the base manager call, and tests replacement of the formation pending input only when the captured turn recovery is considered current. The original formation proposal telemetry and `FORMATION` label remain even when the candidate calls the setter with recovery arguments. The fake setter records calls rather than native success. A player/empty/client callback after an earlier base call cannot undo that earlier write. Collision/terrain, fake combat, prior writer, timeout, phase transition and proposal-absent controls cover only their named synthetic situations. The current real formation path does not produce a claimed formation result with an empty pending value; the fake combat claimed-without-proposal case does not test that formation branch.

The `getter-throw` test injects an exception at the **third** fake `getControllingPassenger` invocation. With the unchanged source this occurs at formation evaluation after one base call; in the experimental capture it occurs at the manager's mob gate before a base call, after the extra capture getter. This count-based injection reaches different semantic call sites and does not establish that the same real getter failure occurs in both versions. The extra `beginCapture` pilot/level getters run before its surrounding `try`; either can throw before the base manager call. Other added getters, real exception rates, all exception cleanup paths, change-and-restore, reentrancy beyond these stand-ins, concurrent mutation and same-object dismount/reboard remain unverified.

The nested cleanup check now fails if the test hook is missing. The earlier #231 runner ignored a missing hook, so its nested assertion alone could pass without checking cleanup; its recorded candidate source was independently checked to contain `hasCaptureForTest`.

The experimental source keeps `applyControl` and its mission-output STORE in the fixture's compiled class, but **does not apply or test** `AutonomousFlightRouteGuidanceMixin` or any transformed production class. Its own bound checks, fallback behavior, and exit 0 do not prove a safe implementation. The real reflective adapter performs separate input and engine writes, can swallow errors or partially mutate state, and returns no success signal; this tool does not model those faults. Historical #150 and #214 contain wingmen that completed a right turn while formation was selected, so these stand-ins do not establish the real timeout's cause or a production fix.

The optional negative checker verifies that a missing nested hook is rejected. It makes a private copy of the runner, removes only the generated candidate's test hook, compiles the source copies, and checks that nested execution fails with the expected missing-hook assertion. It also checks the generated source and `javap` output for the absent hook. It does not modify the runner or production source:

```sh
python3 -I -B tools/check_nested_recovery_hook.py \
  --java-home /path/to/jdk17 --dependencies-json /path/to/classpath.json \
  --output /path/to/new-negative-check
```

The checker exits 0 as `EXPECTED_HOOK_REJECTION_NOT_SAFETY` only for the expected rejection; a false green or other result is `INCONCLUSIVE` and exits nonzero. It saves the hook-removal patch, copied runner, source and input hashes, commands, original runner report, stdout/stderr and disassembly. It requires a new output and does not itself test real cleanup, native setters or the Mixin.
