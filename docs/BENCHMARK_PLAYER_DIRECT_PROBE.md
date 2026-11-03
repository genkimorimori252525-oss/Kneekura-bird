# Isolated direct benchmark-input probe

This test-only hypothesis is distinct from the phase-reset probe: while a player controls the benchmark aircraft, does a direct `BenchmarkManager.applyControl` call preserve the four real inputs and invalidate that aircraft's stale control and heartbeat? Does a second direct call after dismount, before another benchmark END tick, avoid replaying the stale input? A synthetic second UUID checks that its independent marker survives both calls. This is a disposable-world GameTest, not a production fix.

The default mode remains `reset`. The exact additional mode is `direct`; unknown values fail. Both modes deliberately use the same sole GameTest, template, batch, namespace, fresh-world conditions, and forced-chunk baseline. In `direct`, the existing real session first proves its zero-valued stored input differs from a nonzero sentinel: a direct call with the ArmorStand alone must set all four real inputs to zero and record its heartbeat. A FakePlayer then mounts with the capacity-checked API; the fixture checks that it controls the aircraft and the stand remains aboard. The fixture writes and reads back a new sentinel before the measured call. It logs the target and other-UUID state before and after, checks the target input is unchanged and its old control and heartbeat are gone, and checks the other marker is unchanged. After the FakePlayer dismounts it calls the same method once more without an intervening benchmark END tick and checks no stale replay.

## Run and inspect

Follow the preflight and fresh-world checks in [the reset-probe instructions](BENCHMARK_PLAYER_RESET_PROBE.md), including fixed MOD hashes, Java/Forge/Gradle versions, a new worktree and **new disposable run directory**, a separate JVM, no parallel tests or other users, and a separate new empty evidence directory. Run only its preflight checks; do not launch its reset-mode Gradle command. The reset init script is still required. To launch `direct`, use both init scripts from `ww-debug-benchmark` after that preflight:

```sh
if env -u JAVA_TOOL_OPTIONS -u JDK_JAVA_OPTIONS -u _JAVA_OPTIONS \
  gradle --no-daemon --no-configuration-cache --offline \
  -I "$PWD/tools/benchmark-reset-isolated.init.gradle" \
  -I "$PWD/tools/benchmark-direct-control.init.gradle" \
  runGameTestServer --info >"$PROBE_EVIDENCE/stdout" 2>"$PROBE_EVIDENCE/stderr"; then
  probe_status=0
else
  probe_status=$?
fi
printf '%s\n' "$probe_status" >"$PROBE_EVIDENCE/exit"
```

The additional init script sets the mode on the GameTest child JVM's ForgeGradle RunConfig; a `-D` on the Gradle JVM alone is not evidence that the child received it. The launch expects the preflight to have rejected existing evidence files, symlinks and an existing `run-gametest`; do not run it in a user world. Preserve the full run directory and stdout/stderr/exit, source and all input hashes without overwriting previous evidence.

Verify the dedicated namespace, exactly one registered test and completion, and both `BENCHMARK_PLAYER_PROBE_MODE=direct` and `benchmark_reset_probe mode=direct`. The expected/actual 25-chunk sets must match. Check the positive before/after input values and heartbeat, the mounted player and stand, the player's before/after inputs and target/marker state, the named GameTest result, and cleanup's original/after sets and zero session/control/heartbeat counts. If the player-control assertion fails after those prerequisites, classify it as a **red** result with the actual values; do not require the later dismount record for that red. For a passing run, require the dismount before/after record and checks as well. Zero tests, missing mode, a setup/guard failure, unknown cleanup, or an absent expected record is inconclusive, regardless of process status. The reset document's external marker list refers to reset-only log names and cannot classify this mode.

The added UUID and heartbeat are fixture-only markers. Cleanup removes only the marker value it can still identify, leaves foreign or unknown session/occupant state alone, and preserves the world on failure. Boolean forced-chunk sets cannot prove exclusive ownership or reveal overlapping requests. A singleton/fresh-world attestation is not itself proof of isolation, and a partially failed benchmark constructor may leave state whose owner cannot be recovered.

This fixture uses one two-seat D4Y, FakePlayer and manually staged sentinel inputs; it does not exercise a real network player, client-side gate, normal arbiter path, a natural END/stop lifecycle, or all aircraft. Value comparisons cannot detect same-value writes; yaw/pitch/roll and fuel changes are outside this direct-call check. No real-MOD direct-mode result is claimed until a saved run establishes all prerequisites and the named assertion outcome.
