# Isolated benchmark player-reset probe

This **test-only, expected-red** investigation reproduces one benchmark reset while a player controls a two-seat D4Y. It does not fix the benchmark, qualify an aircraft, or prove the broader player-input invariant. The test-only base is `fb1c5c0` (same production files as main `2585f44`); the observed run used fixture commit `e41daade4751d5438ff69e711573c04278a4d000`.

## Evidence from 2026-11-03

* v3 (`2154e4f`) selected one test but the old name guard rejected its unprefixed name before the benchmark began. stdout SHA-256: `43e400582d199536b1e0b3305973b2193a4e0643864f0805969f7f6fe5c743aa`.
* v4 (`149717c`) selected one test but rejected the nonempty forced set before the benchmark began. That run did not record the set's coordinates. stdout SHA-256: `8765df51f05a1c04f8d39547532e85e4f03f29155bbada941d3241311853bec6`.
* v5 (`e41daad`) selected exactly one dedicated test. At structure `(0,-60,0)`, expected and observed forced chunks were the same 25-coordinate grid. The player-free positive control changed the engine target approximately `0.24 → 0`, position `(-149,188,1) → (-150,185,0)`, and velocity `(0.11,0.07,0.13) → (0,0,0)`. A FakePlayer mounted through the ordinary capacity-checked `startRiding` API was the controlling passenger with the benchmark ArmorStand still aboard; the next benchmark tick made the same changes. The three input values were unchanged in these snapshots. Cleanup restored the initial forced set and removed the benchmark session, control, and heartbeat entries. One required GameTest failed and Gradle exited `1`. stdout SHA-256: `9060354c63a760df0dd89361c5cf0e6810633177e0e5d49d86ed272d5364f65a`.

The v5 run used Minecraft 1.20.1, Forge 47.4.20, Java 17.0.17 and Gradle 8.8. The supplied original MOD files were checked against these SHA-256 values:

* `immersive_aircraft-1.3.3+1.20.1-forge.jar`: `d1f7cfeed3ac2cf69472ae756eb9189dad04ab21b8afbd443c82f40e51bbf065`
* `warfare_wings-1.1.4-1.20.1-forge.jar`: `3b6b245e703862517fe7aae6acd95ccafc865e1e81ba7a26e2b9abcfe1120187`

The files are not included here; follow their applicable use and distribution terms. Preserve each run's actual MOD, profile, source and log hashes separately. A source hash alone does not prove which binaries were loaded.

## Run only in an isolated environment

Use a **new worktree**, a dedicated fresh world, a separate JVM, and no concurrent tests, server, player, command, or other owner of that world. Before starting Gradle, independently verify that `ww-debug-benchmark/run-gametest` does not exist, is not a symlink, and its parent path resolves into that new worktree. Also inspect any supplied configuration, including `server.properties` / `level-name`, symlinks, and the actual world path. The init script's attestation property is not proof of freshness or isolation. Use a new evidence directory; preserve any previous run rather than deleting or overwriting it.

`prepareFlightGameTestRuntime` creates files under the fixed `run-gametest` path and deletes its `mods` directory and staged profile. It does this independently of a task working-directory override. Stage the exact MODs in `ww-debug-benchmark/flight-test-mods/`, verify their hashes, and retain the selected flight profile and build provenance. Do not use this procedure against an existing user world.

From `ww-debug-benchmark`, after those checks, a launch shape is:

```sh
# Set a NEW evidence directory and prepare fixed MODs/profile before this command.
: "${PROBE_EVIDENCE:?set a new empty evidence directory}"
python3 - "$PROBE_EVIDENCE" <<'PYSAFE' || exit 1
from pathlib import Path
import subprocess, sys
root = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], text=True).strip()).resolve()
work = Path.cwd().resolve()
evidence = Path(sys.argv[1]).absolute()
if work != root / 'ww-debug-benchmark':
    raise SystemExit('unexpected project directory')
if any(p.is_symlink() for p in (evidence, *evidence.parents)):
    raise SystemExit('symlink in evidence path')
if not evidence.is_dir() or any(evidence.iterdir()):
    raise SystemExit('evidence directory must already exist and be empty')
if evidence.resolve() == root or root in evidence.resolve().parents:
    raise SystemExit('evidence directory must be outside the worktree')
run = work / 'run-gametest'
if run.exists() or run.is_symlink():
    raise SystemExit('run-gametest must not already exist')
PYSAFE
for name in stdout stderr exit; do
  test ! -e "$PROBE_EVIDENCE/$name" && test ! -L "$PROBE_EVIDENCE/$name" || exit 1
done
if env -u JAVA_TOOL_OPTIONS -u JDK_JAVA_OPTIONS -u _JAVA_OPTIONS \
  gradle --no-daemon --no-configuration-cache --offline -I "$PWD/tools/benchmark-reset-isolated.init.gradle" \
  runGameTestServer --info >"$PROBE_EVIDENCE/stdout" 2>"$PROBE_EVIDENCE/stderr"; then
  probe_status=0
else
  probe_status=$?
fi
printf '%s\n' "$probe_status" >"$PROBE_EVIDENCE/exit"
```

Use the project's configured Java 17, Gradle 8.8 and cache; the command assumes `$PROBE_EVIDENCE` already names a newly created, empty directory outside the worktree. Do not enable GitHub Actions. Preserve stdout, stderr, exit status, the complete run directory, source/fixture/init-script and input hashes. Do not reuse the world, especially after setup or cleanup fails.

Externally verify **all** of the following before classifying a run; zero registered tests or a startup/guard failure is inconclusive, never a pass:

1. The runtime reports only namespace `wwdebug_benchmark_reset_probe`, the `benchmark_player_reset_probe_only:1` batch has one test, and `selected_test_count=1` names `benchmarkphaseresetrespectsplayer` with its dedicated batch and template.
2. Before benchmark creation, the logged expected and actual coordinate lists are equal and have the 25 points at offsets `-1..3` in each dimension. The positive-control before/after records show the reset; the player record shows the player first in the passenger list and the test has passed its controlling-passenger and same-root assertions.
3. The player before/after records, phase, named test result and process exit are present. A v5-style failure at `benchmark phase reset must not change player-controlled engine, inputs, position or velocity` with exit `1` is **red**, not a successful qualification. A zero exit without the one-test completion and all prior evidence is inconclusive.
4. Compare cleanup `forced_before` and `forced_after` as sets, confirm `sessions=0 controls=0 heartbeats=0`, and inspect every cleanup error. An unknown snapshot or cleanup failure is inconclusive and requires preserving the world. Never forcibly clear the baseline to make this check pass.

As a preliminary external gate, these checks require evidence that the intended test actually ran; they do not replace the value and cleanup review above:

```sh
out="$PROBE_EVIDENCE/stdout"
for marker in \
  'Enabled Gametest Namespaces: [wwdebug_benchmark_reset_probe]' \
  "Running test batch 'benchmark_player_reset_probe_only:1' (1 tests)" \
  'benchmark_reset_probe selected_test_count=1' \
  'name=benchmarkphaseresetrespectsplayer' \
  'benchmark_reset_probe positive_before=' \
  'benchmark_reset_probe player_after=' \
  'benchmark_reset_probe cleanup ' \
  '1 GAME TESTS COMPLETE'; do
  rg -Fq "$marker" "$out" || { echo "INCONCLUSIVE: missing $marker"; exit 1; }
done
cat "$PROBE_EVIDENCE/exit"
```

The 25 initial chunks are created by the fixed GameTest structure setup. Equal sets cannot establish who owns a request, detect another owner requesting the same chunk, or exclude changes between snapshots. The benchmark uses boolean forced-chunk ownership; partial constructor/cleanup failures can leave state that the fixture cannot safely undo. Only a disposable isolated world limits the impact.

The test seeds `STRAIGHT_ACCELERATION` at tick 599 and calls `BenchmarkManager.tick` synchronously with a FakePlayer. It does not demonstrate a natural 600-tick run, network player behavior, the public benchmark command, same-value setter writes, attitude changes, fuel changes, or all 24 aircraft. An ended session is treated as inconclusive because a safe stop and an exception caught by the benchmark are not distinguished.

## Additional continuity assertions (not yet run in Minecraft)

Before the first player-controlled END call, this fixture records and logs the phase, phase tick, and presence of the target aircraft's command and heartbeat. After the original v5 safety assertion, it requires that both stale entries were present, verifies the original session/test remains active and the first END call did not advance its phase, and checks both entries were invalidated. It calls the real `BenchmarkManager.tick` three more times while the player remains in control, and checks the original session/test identity, phase, phase tick and the same engine/input/position/velocity snapshot each time. After a normal player dismount it checks the original ArmorStand is again the controlling passenger, then makes three more benchmark calls and direct `BenchmarkManager.applyControl` calls; the original test must not advance or reinstall stale commands or heartbeats. All phase checks use the pre-first-END baseline. The `continuity ... result=verified` marker is emitted only after those assertions pass. A missing marker, missing stale-state precondition, or loss of the original session/test is inconclusive, not proof of safe cleanup or a safe alternative session outcome.

All repeated calls occur synchronously in one GameTest callback and cover only one aircraft. Immediately after dismount, commands, heartbeat and phase are checked before any further tick; the vehicle-value baseline is taken after dismount, so changes caused inside dismount itself are not attributed by this probe. These checks do not demonstrate natural multi-tick behavior, changes on a client, any other aircraft, `/benchmark stop`, abort or server-stop behavior, fuel inventory, attitude, fall distance, or same-value writes. The old v5 failure remains the first safety assertion; until that behavior changes, none of these new assertions is reached. No Minecraft execution of the extended fixture has been performed by this change.

To restore the prior environment, stop the dedicated JVM, preserve its run directory and evidence as a distinct immutable record, and return to the original worktree and its untouched run directory. Do not copy this test world over an existing world or alter an existing world's forced chunks.
