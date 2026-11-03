# Isolated direct `stopSilently` probe

This test calls `BenchmarkManager.stopSilently(server)` directly and synchronously.
It does not fire or exercise `ServerStoppingEvent`, server shutdown, save ordering,
client disconnect or natural END ticking. It is a destructive experiment, not a
normal game test. It must run only in a separately verified new disposable world,
with a dedicated JVM and exactly one selected test. Do not reuse a failed world;
preserve its complete files and logs. Run no other GameTest or server in that JVM.
The flag is an attestation, not proof that the world is fresh.

The test runs a player-free positive-control session followed by a distinct real
D4Y benchmark session with a normally mounted FakePlayer and ArmorStand. A fuel preparation and native aircraft tick occur before player mounting, as in
#145 v3; inputs, engine target, position and velocity are then seeded and read
back before mounting.
The test calls the void API only after verifying session ownership and identity;
normal return, session/maps, direct entity references, pilot/player relationships,
controls and forced chunk snapshots are logged separately. Removed or detached
player aircraft is unsafe. A missing UUID lookup, missing marker, changed session,
exception, missing selected test, incomplete log or timeout is inconclusive.
A retained session is inconclusive here: safety over later END ticks and recovery
requires separate tests. Same-value writes, orientation, fuel, a real client and
other occupied seats are unobserved. Chunk-set equality cannot identify owners,
concurrent force requests or intervening changes. Cleanup refuses to abort an
unknown session or a retained previously player-occupied session; preserve the
world on partial constructor or cleanup failure. Even if fixture cleanup refuses
an occupied session, normal server shutdown can later call stopSilently again;
this probe does not promise the entity survives the remainder of that JVM.

Use the init script `ww-debug-benchmark/tools/benchmark-silent-stop-isolated.init.gradle`
with the existing fixed Java, Gradle, Forge and MOD inputs. Verify externally that
`run-gametest`, including any server.properties-selected world, is absent before
starting a fresh JVM. Check the printed `SILENT_STOP_PROBE_CONFIG`, selected test
count/name, exact positive and player markers, GameTest result, process exit,
forced snapshots and complete stderr/stdout. Zero selected tests or process exit 0
alone is not success. No runner, network, SSL or permission changes are authorized.
To return to the prior state, switch back to the original worktree. For shared
changes, use a revert commit so history is retained. Preserve all run evidence.
Existing #145 public-stop evidence remains a separate result.
