# AI development handoff

Last updated: 2026-11-03 (Asia/Tokyo)

## 2026-11-03 continuation checkpoint

### Silent stop bypasses the experimental takeover latch

On the evidence-only [branch](https://github.com/genkimorimori252525-oss/Kneekura-bird/tree/agent/issue7-silent-stop-latch-evidence),
head `e1781155abc756f08969c88e25772bb77e365718`, local `8a1db05` uses the experimental
`92682c7` production code plus the #148 fixture with an explicit latch check. In a fresh
fixed-mod world/JVM, the one selected test confirmed player-free positive control, stale
control/heartbeat, then a direct benchmark tick with the same session/aircraft, latch=true,
controls cleared and player, phase, inputs and forced set preserved. Direct `stopSilently`
then removed aircraft and pilot, detached the surviving FakePlayer and removed the session.
One required test failed, exit 1, stdout SHA-256
`24abcc7a3ea747070858f34d4bac9d679930f916ef3025de658790a0c2d14646`. Fixture cleanup restored
the 25-chunk baseline; ownership is not established. This was a direct method call, not a
`ServerStoppingEvent`, and says nothing about real client or exception-abort behavior.

Local logs-only archive `kneekura-issue7-silent-stop-after-latch-8a1db05-evidence-20261103.zip`
SHA-256 `727c414f2d7be4d6a6b832100beb4a1cb078fca893c64c9e5e91b6aaa934c453`; review raw
UUIDs/environment details before sharing. The generated world is preserved separately. The
experimental candidate remains non-deployable; public-stop/END passes do not protect this path.

### Direct silent stop removes a player-controlled aircraft

Draft [#148](https://github.com/genkimorimori252525-oss/Kneekura-bird/pull/148), head
`a23157e6d423339f6f2cf5e8b745b68919193462`, is test-only on #145. In the fresh-world,
fixed-mod run of local `6f96403` (production identical to main), one selected GameTest
confirmed player-free silent-stop control, nonzero sentinels and a normally mounted FakePlayer
controlling D4Y with the ArmorStand aboard. Direct `BenchmarkManager.stopSilently(server)`
returned normally, removed aircraft and pilot, detached the surviving player and removed the
session/control/heartbeat. One required test failed, Gradle exit 1. stdout SHA-256
`70c379dabfd59c05c74973b311f9bb9910746dbc51c23de12d69df7e9e03d266`. The discarded object's
unchanged snapshot does not establish aircraft survival. Forced-set cleanup matched its
25-chunk baseline; shared ownership is unproven. This did **not** fire ServerStoppingEvent
and does not establish real shutdown ordering, exception abort or client behavior. Independent
review confirmed the scope.

Local logs-only archive `kneekura-issue7-silent-stop-6f96403-evidence-20261103.zip` SHA-256
`7254ead6b89660404c783ffe47915ea1bafcb44753ffb9e3a6ec07d737e3c4e6` contains generated
UUIDs/environment details but no MOD jars or world; the disposable world is saved separately.
Do not consider the experimental public-stop latch a guard for this independent entry point.

### Telemetry comparability manifest: draft, not model qualification

Draft [#147](https://github.com/genkimorimori252525-oss/Kneekura-bird/pull/147), head
`75df0235caf022fc5a47949a2974db5ac3b1aadc`, is a 3-file/+679 read-only tool against main
`2585f44`. It records explicit JSONL input hashes, domain-hashed aircraft/run/type identity,
observed tick ranges/gaps and available fields; provenance is explicitly unverified. Existing
fast-simulation time-series comparison remains `NOT_COMPARABLE`, with no interpolation, model
error or safety verdict. Hashes are linkable pseudonyms; low-entropy values can be guessed.

Twenty synthetic tests passed, including strict UTF-8/CRLF, rejection of BOM/bare CR, bounded
rows/lines, malformed JSON and identity separation. Independent review confirmed the fixes.
Read-only saved-log analyses with unknown provenance: A6M full 4,838 frames / zero internal
gaps; P-47N mutual 1,479 frames / 521 missing ticks. Neither qualifies an aircraft or proves
unobserved intervals safe. Local output manifests `comparability-a6m-50eb5f5-v1.json` and
`comparability-p47-50eb5f5-v1.json` contain linkable hashes and require review before sharing.
No real MOD test was rerun for this tool.

### Native observer: isolated launch blocked before staging

Experimental observer source [branch](https://github.com/genkimorimori252525-oss/Kneekura-bird/tree/agent/issue7-native-input-observer-evidence),
head `9e9e859812d1bde0c38da30eb6b30a2a1fd044d9`, is separate from ordinary MOD source and
config. Its standalone Java buffer tests and jar build passed; target and explicit negative
entity are separate and unknown/truncated caller evidence fails closed. The observer is **not
runtime validated**: load, transform, hook, actual positive/negative controls and complete
windows still require proof. Normal MOD build with the observer source present contained no
observer class/config/manifest entry; a separate ordinary launch had none in stdout or runtime
logs (stdout SHA-256 `402d62db8c8eafd69de1b2bec5f4b398fe46d0d0dfb9e6962a137c77c572f28b`).

The launcher is split into [core](https://github.com/genkimorimori252525-oss/Kneekura-bird/tree/agent/issue7-observer-safe-launch-core)
`18b51041` (6 files/+790) and [tests](https://github.com/genkimorimori252525-oss/Kneekura-bird/tree/agent/issue7-observer-safe-launch-tests)
`478dd4a7` (2 files/+413). Python 32 and miniature Gradle graph 5 passed; this is not an
actual observer GameTest. A fresh read-only-bound, separate network/PID namespace attempt
with a dedicated copied cache reached pre-prepare guard and prepare completion, then failed
`:downloadMCMeta` on `piston-meta.mojang.com` despite `--offline`. No observer was staged and
no GameTest world was created. Launcher marked the result inconclusive; preserve scratch/cache.
stdout SHA-256 `89b4243490eb9f1d61d3ecbb47ca07c4c8571846994887b013c69f1d54a7549e`, stderr
`6fdadd4ef7d152bc2cbdc84961f143125a4bbbccba41d16fbbfac006839803ed`. Do not weaken isolation,
TLS or skip the task to call this a pass. Fixed ForgeGradle uses direct URLs and can fetch both
during configuration and task execution; its offline-safe replay remains unimplemented.

Two saved 1.20.1 metadata JSONs differ in asset index SHA-1 (`62b36534…` versus `ada52cc6…`);
the present cached index matches the latter. Freeze and validate the whole metadata/index/assets
set with provenance before a new hermetic approach. Previous versions by name alone are not
proof of identical inputs. Observer fixture wiring, correct class transform, normal client
behavior and the natural tick input change's cause remain open.

### Natural END observation: pass does not establish no player-input writes

An [evidence-only branch](https://github.com/genkimorimori252525-oss/Kneekura-bird/tree/agent/issue7-natural-end-exploration),
head `a6355235e4e13971a58ddf8b0b164bc3b2ae5f05`, adds the test-only natural-END probe over
the unsafe experimental `92682c7`. Local source `9d9ac28`, tree
`e14cdb200377999b975965b8ae3a43cc928e6b5a`. One fixed-mod GameTest in a new world/JVM passed
its player-free positive, occupied-stop refusal, three observed same-END pre/post pairs while
occupied and three after dismount, test cleanup, and scheduled completion. Session elapsed and
entity tickCount advanced. stdout SHA-256
`f86173f92ea05df8be53ff2141a242489ce13a69810abcfc5c0a8d9a4ea2df02`.

**Important unclassified change:** while the FakePlayer was aboard, input axes were
`(0.31,-0.42,0.53)` at END tick 2 pre/post, but `(0,0,0)` by END tick 3 pre; engine target
remained approximately 0.24. The fixture did not seed aircraft input/position/velocity after
the player mounted. The change occurred outside the observed END pair; its writer and cause
are unknown. Two independent fixed-IA bytecode reviews identified a strong hypothesis:
`VehicleEntity.tickPilot` calls `setInputs(0,0,0)` for a non-local passenger; server FakePlayer
`isLocalPlayer()` is false, the setter changes only the three axes, and the arbiter mixin runs
at TAIL. The observed values match this mechanism, but neither branch nor setter was recorded
in this run. The mapped IA jar's current SHA-256 is
`6b00887b97de551d25caacd7c888db3df4dbd80007e9a98a064cfe4b1f2ad665`; its hash at run time was
not saved and cannot be retroactively asserted. A separate opt-in, non-mutating call-site probe
would need a dedicated JVM/config, positive hook control, call ordering and proof it cannot
enter production; FakePlayer evidence would still not represent real client packets. A passing
END-pair comparison does **not**
prove that player-controlled inputs were never written. Same-value writes, intermediate
changes and other END listeners are also not excluded. Entity tickCount is only a scheduler
visit, not proof of a particular physics path. The candidate remains unsafe to deploy because
public stop recovery, exception/shutdown and forced-chunk ownership remain unresolved.

Local logs-only archive `kneekura-issue7-natural-end-9d9ac28-evidence-20261103.zip` SHA-256
`171c15408f02ea23d973239e1f59eeca61a4834c27ed99d35f4f0bb6bf7086c7`; it contains generated
test UUIDs and environment details, but no MOD JARs or generated world. The fresh world is
preserved separately. The fixture's async timeout/stopping teardown is best effort and missing
completion or cleanup evidence must be classified inconclusive.

### Experimental suspension: two limited passes, not deployable

Evidence-only [branch](https://github.com/genkimorimori252525-oss/Kneekura-bird/tree/agent/issue7-stop-refusal-exploration-only),
head `24e1eb59ffb0d63595b2caf4ae57bfcbabf63b76`, local `92682c7`, tree
`fbe83357b74e7cdf23b45568a3ccb03d4649c4d6`, changes one production file (+45/-4)
over #146. Java 17/Gradle 8.8 build passed, deterministic preflight 12/12, and the isolated
fixed-MOD stop-refusal GameTest selected and passed one test: player-free stop positive,
occupied stop refused with same session/aircraft/passengers and target control/heartbeat
cleared, two occupied and two dismounted synchronous benchmark calls passed. stdout SHA-256
`264a612682568ccc8f339ef548af13d64092cbe43eb232af0c4c33a1d4693002`. Independent review
confirmed the test fixture's cleanup explicitly invokes a private abort only after dismount;
it does **not** show recovery using public stop.

A second fresh-world test used the same production code with #144's pre-END fixture, local
`336d7b2`, tree `36e4500fb24774a15e4d6f19886655cf30551e42`; its exact tree is on an
[evidence-only branch](https://github.com/genkimorimori252525-oss/Kneekura-bird/tree/agent/issue7-stop-candidate-pre-end-evidence).
One dedicated GameTest passed, with the player-free reset positive and the initial phase 599
and existing control/heartbeat established, followed by the initial direct call and three
occupied plus three dismounted synchronous calls. stdout SHA-256
`968e8184b5b2d97f644365589a49e5c80dd75e5ddabe43f636c6299b5b47d10b`. **The fixture itself
sets sentinel position/velocity and controls after the FakePlayer mounts**; the observation
concerns later benchmark calls, not proof that no write happened during all player control.
Both tests compare values and do not detect same-value writes; they do not dispatch natural
server END events. Each fixture reported identical 25-chunk baseline sets after test-specific
cleanup and zero session/control/heartbeat counts, without proving exclusive ownership.

**Do not merge/deploy this candidate.** Its latch has no release: subsequent public stop is
rejected even after dismount, retaining the session and forced chunks indefinitely. Exception
abort and `stopSilently` bypass the latch; shutdown/restart, actual event timing, multiple
aircraft, non-controlling/nested occupants, transient mounts, shared chunk ownership and recovery
remain unresolved. Continue by specifying and testing safe recovery/exception/shutdown and
other-aircraft behavior without deleting unknown-owned chunks or aircraft.
Fixed Forge `stopRiding` fires a dismount event and changes passenger state; fixed IA seat and
controller selection depend on passenger order. Removing the benchmark pilot while promising
the occupied aircraft is unchanged is not established. The existing boolean forced-chunk ledger
lacks other-owner/refcount and original-dimension evidence; partial construction can lose ledger
entries. Do not unforce or detach based solely on an equal set or dismount. A future owner-tagged
Forge ticket experiment must handle partial add/remove, restart and migration independently;
existing vanilla entries cannot be silently attributed to the new owner. A separate natural-END
probe is being designed; same-tick event-priority snapshots cannot exclude other listeners or
same-value writes, and asynchronous teardown cannot be assumed successful.

Local logs-only archive `kneekura-issue7-experimental-suspension-92682c7-evidence-20261103.zip`
SHA-256 `f42759e3c93ac0c517e50d9e9a0574569c1096a379fbecd60b59f157f12f6603`; raw logs contain
generated UUIDs and environment details, not MOD JARs or generated worlds. The two disposable
worlds are retained separately.

### Stop refusal and post-takeover continuity: fixture red, candidate experimental

Draft [#146](https://github.com/genkimorimori252525-oss/Kneekura-bird/pull/146), head
`4b90c490b73238dc10a6ab616eba25fe1ddfe668`, is test-only on #145. In the fixed-mod,
fresh-world run of local `a0d54fc` (tree `ae57505f4c45cdf29eb686091861f47581573fc4`),
identity refusal and player-free stop controls passed. Before the player stop, phase was
`STRAIGHT_ACCELERATION` tick 599 with control and heartbeat present. The actual stop
returned 1, discarded the aircraft and detached the FakePlayer; the refusal assertion failed.
One required test failed, Gradle exit 1. stdout SHA-256
`8ad93b1d3bd37733009fff3ff96616bfd2990939f76239b1a4cd3fb68bb87c09`. Later refusal-success,
occupied and dismounted assertions were not reached. Cleanup's forced-set baseline matched
(25) and state maps were empty; ownership is not established.

The local logs-only archive `kneekura-issue7-stop-refusal-a0d54fc-evidence-20261103.zip`
has SHA-256 `8cd85d82371ff2a5f04bf1b3985ced55142360b952f25ba61f0096978afe0a62`; raw
logs include generated UUIDs and environment details, and must be reviewed before sharing.
The dedicated generated world is preserved separately. An experimental limited candidate
is under investigation: keep only the player-occupied aircraft suspended after rejecting
stop, invalidate its benchmark control, and avoid spawning pending tests while it is held.
It is not a complete safe lifecycle: exception abort, server stopping, nested/non-controlling
players, multiple active aircraft, transient mounts between ticks and ownership/recovery of
forced chunks still need separate design and evidence. Synchronous calls in this fixture are
not natural server END events. Do not merge or claim complete player safety on this basis.

The fast `FlightSimulationMain` is an independent fighter-only preflight model, with no
tick-by-tick trajectory or guaranteed final applied input. Existing real-MOD frames therefore
cannot yet establish model physics error. As a later step, create a read-only comparability
manifest with pinned source/MOD/config/profile, scenario, aircraft, observed tick intervals and
unknowns; label current time-series comparisons NOT_COMPARABLE and never fill gaps as proof.
Issue #7 records the proposed future fixed-condition, applied-input calibration.

### Public benchmark stop removes a player-controlled aircraft

Draft [#145](https://github.com/genkimorimori252525-oss/Kneekura-bird/pull/145), head
`6aa19260bd9981c1a8505e59acb0728eb628cf47`, adds a test-only stop probe on #141. Local
`5fdc7e`, tree `f153061f53f95ce2905aca1cfb3d7548bec06193`, has production stop/cleanup
identical to main `2585f44`. In a dedicated JVM and fresh world with fixed MOD versions,
one selected GameTest first refused a foreign session identity and passed the player-free
stop control. For a second D4Y, player-free preparation recorded fuel utilization 0→1 and
read back nonzero input/engine/motion sentinels; a normal FakePlayer mount controlled the
aircraft with the ArmorStand still aboard. Public `BenchmarkManager.stop` returned 1, removed
the aircraft and detached the player; the player entity survived. The safety assertion failed,
one required test failed and Gradle exited 1. stdout SHA-256
`f4cfb53915dbb37daf1421ec871f92e637af1b639ae0c47321a44e690517eb83`. This observation was
made before fixture cleanup and independently reviewed. Cleanup's 25-chunk sets were equal;
session/control/heartbeat counts were zero. These sets cannot prove exclusive ownership.

Two earlier fresh runs are **inconclusive**, not stop results: `fe78dfa` failed its nonzero
readback before mounting (stdout `e6e2bd42220c3084f40f978d7bf211886162c958fa6b8e3f9884ccb31e58bfd8`);
`c734411` logged engine=0 but did not observe fuel then (stdout
`fda8309a6e099036e70a2b05144d845e97072d5f3a4b85354ee77d3c495f65c8`). The fixed MOD's
setter refuses nonzero engine targets without fuel; the later 0→1 observation supports the
preparation fix, but does not directly prove the earlier cause. All three worlds and logs are
preserved. Local logs-only archive `kneekura-issue7-benchmark-stop-5fdc7e-evidence-20261103.zip`
SHA-256 `3006bdd4b0f524a267f762d3202929dc13e80fcdae9b72ea9bffba4e023ecb10`; review raw test
UUIDs and environment details before sharing. It contains no MOD JARs or generated worlds.

Do not invoke current abort/cleanup as a player-takeover fix. A public-stop guard alone leaves
the END/reset issue, potential persistent forced chunks, exception abort and server-shutdown
behavior unresolved; investigate the whole lifecycle without assuming boolean chunk ownership.
Network players, other aircraft, command parsing, concurrency, same-value writes and natural
shutdown remain unverified. No merge or Actions/runner change was made.

### First takeover END: stronger test remains red

Draft [#144](https://github.com/genkimorimori252525-oss/Kneekura-bird/pull/144), head
`ec9e25d2fdae0ece171b671f466361ad88263d11`, extends #141's fixture to take phase/tick
and stale-state snapshots **before** the first takeover call. Local source `d223769`, tree
`9e1292d818095cf74782d9436203650c7d3f32dc`, built successfully. In a fresh fixed-mod world,
phase was `STRAIGHT_ACCELERATION` tick 599 with control and heartbeat present; one synchronous
player-controlled benchmark call reset engine/position/velocity and advanced phase to
`TURN_WARMUP`. One required GameTest failed at the existing first assertion, so the new
continuity assertions were **not reached**. stdout SHA-256
`45735555e20278c19f7b7e422094881d9cf86895ddfe95463fe7bad9db2b5356`. Initial and final
fixture forced sets matched (25); session/control/heartbeat counts were zero. This does not
prove exclusive force ownership. Preserve world and logs, do not count this as a pass.

An END-only latch could miss player mounting and dismounting between END calls; merely retaining
the session can retain forced chunks indefinitely, while current stop/abort cleanup may discard
the occupied aircraft. These are design risks, not a proven safe lifecycle. A separate isolated
stop probe is being prepared. Do not release shared forced chunks or invoke destructive cleanup
to make the test pass.

Local logs-only archives (review contents before sharing; they include generated UUIDs and
environment details, no MOD JARs or generated worlds):

* `kneekura-issue7-benchmark-direct-guard-70814fc-evidence-20261103.zip`, SHA-256
  `ccd12582cef7848ae540e352c00cbed3ab23b48212c7abb486d366ece05cb4e0`.
* `kneekura-issue7-benchmark-pre-end-d223769-evidence-20261103.zip`, SHA-256
  `9316ca65f00dcc5bb8e38501822569298a93b568bb86d0e1c358be8f7d7fef31`.

### Direct benchmark entry: narrowly guarded; END reset remains red

Draft [#142](https://github.com/genkimorimori252525-oss/Kneekura-bird/pull/142), head
`1fff98ce`, adds the isolated direct-entry GameTest on #141. Against main-equivalent production
code, the FakePlayer-controlled D4Y's axes and engine `(0.31, -0.42, 0.53, 0.24)` all became
zero on direct `BenchmarkManager.applyControl`; positive control and cleanup were recorded,
one required GameTest failed (stdout SHA-256
`7a07a406cd2eec814b7103153e3992c112161060c954c27c5a235a9c477a5d78`).

Draft [#143](https://github.com/genkimorimori252525-oss/Kneekura-bird/pull/143), head
`4a07a1f28c9f3bd71542b28f5853f3e89ad5ba1c`, is a **one-file, seven-line** main-based
production guard: for a controlling player, use the existing `MobPilotGate`, clear the target
aircraft's benchmark control and heartbeat, and return. In local fixture tree `ae1b3d88`
(commit `70814fc`, with the same production patch), Java 17 / Gradle 8.8 build succeeded,
deterministic simulation passed 12/12, and one isolated fixed-mod direct GameTest passed.
The positive control applied stored controls; the player inputs stayed unchanged, target
state was cleared, a second UUID marker survived, and immediate dismount did not replay
stale input. stdout SHA-256 `58a7721aec4f66c851c341cd321132d9318c377edcbe946e4df788d817604328`.

**Do not merge or treat player safety as solved.** A new world/JVM with that same patched
fixture still produced #141's END/reset violation: player-controlled engine 0.24→0, position
reset to the anchor, and velocity zeroed; one required GameTest failed, Gradle exit 1.
stdout SHA-256 `436ce7c4876d8e41e7bdfb8c7c007d94907b8f1a7224e5e549db55ca9a5f0848`.
The normal arbiter returns before this direct method during player control; END can recreate
the stale entry. Neither test establishes same-value writes, natural tick/stop/abort lifecycle,
network player, all aircraft, or exclusive forced-chunk ownership. Both fixture cleanups
reported identical pre/post 25-chunk sets and zero sessions/controls/heartbeats. Separate
disposable worlds, full raw logs and fixed MOD hashes remain under
`/workspace/issue7-evidence-20261103/`; do not publish generated world data or MOD JARs
without checking applicable conditions.

Two failed test-launch attempts are preserved separately: the first could not resolve Minecraft
metadata without proxy settings; the second rejected the proxy certificate. The successful
run used the configured proxy and `/etc/ssl/certs/java/cacerts`, retaining certificate
verification, in a fresh disposable world. No GitHub Actions or runner settings changed.
Next: design and verify per-aircraft END takeover and a dismount latch without using cleanup
that discards player aircraft; separately solve stop/abort and forced-chunk ownership.
Review the existing continuity fixture before testing, retain each red result, and keep all
these PRs draft until the applicable safety invariants are independently verified.

### Player-controlled benchmark reset: reproduced, not fixed

Draft [#141](https://github.com/genkimorimori252525-oss/Kneekura-bird/pull/141), head `e6bd4a6b`,
is a **failing, test-only** probe stacked on #123. With fixed Minecraft 1.20.1 / Forge 47.4.20 and
the pinned mods, a D4Y's benchmark ArmorStand remained aboard while a FakePlayer boarded normally
and became controlling passenger. At a seeded phase boundary, a synchronous real
`BenchmarkManager.tick` changed engine target ~0.24 to 0, returned position to the benchmark
anchor and zeroed velocity. The three recorded input axes did not change. Player-free positive
control reached the same reset; the dedicated GameTest failed its safety assertion, Gradle 1.
The fixture base `fb1c5c0` differs from main `2585f44` only by test/helper additions. This is not
evidence for natural 600-tick progression, network player input, same-value writes, attitude,
fuel, or all shutdown paths. The observed GameTest forced-set baseline was 25 chunks and was
equal after test cleanup; the vanilla global boolean does not establish exclusive ownership.

Do not fix by just failing/aborting the benchmark: current `cleanup` discards the aircraft, and
`stop` removes the session before abort can fail. Direct `BenchmarkManager.applyControl`, stale
controls after takeover, END tick, multi-aircraft operation, stop/abort/server shutdown and
ownership recovery require separate tests and a safe takeover design. `fillBatch` also chooses
`anchor(active.size())`, which can reuse a remaining aircraft's slot after an earlier test finishes;
this is a static risk not yet reproduced in-game. The one-aircraft, seeded fixture cannot qualify
the complete player-safety requirement. Issue #7 and #141 contain the exact evidence and limits.

The ephemeral evidence archive `kneekura-issue7-player-reset-e41daad-evidence-20261103.zip` has
SHA-256 `4935c9191cbb25d9f5c6a2e20ac3b2afb167f3f9353e5000b8f096cbc686b722`. The separate
`kneekura-issue7-player-reset-v5-private-world-20261103.zip` has SHA-256
`7d712313590bb2e4dd999e44578d4530d8a865e6b1dcee6f086c4f2aa8566040`; it contains generated world
data, test UUIDs and world serverconfig and should be reviewed before sharing. Both are local only.

### Later checkpoint: collision regression and verifier identity

**Safety checkpoint:** Draft [#128](https://github.com/genkimorimori252525-oss/Kneekura-bird/pull/128)
(`9a7d6289`, tree `08bb32d5`) fixes the stale terrain-only report on top of #127; the A6M full
GameTest passed 64/64. In its mutual-dogfight run, however, the scene completion metric reported
minimum separation 8.22 while a same-combat collision adapter recorded `current=7.4` at a
different intra-tick sample (rounded to one decimal). Contact is not established; all samples
at or above 8 are not established either. Keep #128 draft and do not treat the existing mutual
verifier's pass as complete safety evidence. The prior #127 run had 10.83 / adapter 10.1; a
justified repeat at the same #127 code had 8.69 / adapter 8.1. UUID order changes the assigned
evasion and other combat choices, and is not fixed. Code impact versus run variation is unresolved.
The mutual verifier on main does not gate on adapter separation, Gradle status or crash reports.
Independent focused fixes are drafts; they are not combined or merged. Do not relax any safety threshold.

### Mutual verifier checkpoint and next steps

- Draft [#129](https://github.com/genkimorimori252525-oss/Kneekura-bird/pull/129), head
  `631a6503`, requires the supplied successful Gradle exit status and no crash report; 13 tests
  passed. It does not validate other evidence. Symlink and Windows junction behavior has limits.
- Draft [#130](https://github.com/genkimorimori252525-oss/Kneekura-bird/pull/130), head
  `b5f40695`, checks the ordered combat window, both participants' frames, finite nonnegative
  speed and explicit ground flags, and preserves observed dangerous values in errors even with
  invalid samples. Eighteen focused tests passed. Frame gaps remain possible in this draft alone.
- Draft [#131](https://github.com/genkimorimori252525-oss/Kneekura-bird/pull/131), head
  `e1e27be0`, checks both participants' sampled adapter distances with conservative rounding;
  19 tests passed. Reanalysis of #127 first / #128 / #127 repeat gives 10.1 pass / 7.4 fail /
  8.1 pass. Samples do not prove continuous separation or absence of contact.
- Draft [#132](https://github.com/genkimorimori252525-oss/Kneekura-bird/pull/132), head
  `7db096c9`, checks mutual candidate JSONL integrity and discovery errors, including broken
  `aircraft` links. On scan/read failure it hides incomplete telemetry metrics. Syntactically
  valid but semantically invalid events can still leave partial samples in a failed result.
  [#133](https://github.com/genkimorimori252525-oss/Kneekura-bird/pull/133), head `fb51d51d`,
  rejects malformed summary JSON and saves a failed result. Python integer size limits depend on
  configuration, float underflow and memory remain unbounded.
  [#134](https://github.com/genkimorimori252525-oss/Kneekura-bird/pull/134), head `dbbcf9fd`, validates participant and
  pilot identity, action/doctrine, acquisition/loss and shot order, with 21 focused tests.
  None of these independent candidates alone implements the separation gate.
- Draft [#135](https://github.com/genkimorimori252525-oss/Kneekura-bird/pull/135), head
  `e92d52d9`, rejects unverified multi-aircraft summaries and checks single-primary completion,
  PARKED frame and tail ordering. It does not establish 40 consecutive stopped ticks or runway
  position. Its 14 focused tests and saved-log reanalyses do not certify the 7.4 run as safe.
- Draft [#136](https://github.com/genkimorimori252525-oss/Kneekura-bird/pull/136), head
  `15f53178`, rejects multiple, unreadable or non-regular summary candidates rather than choosing
  by mtime; it also rejects symlinks/reparse points under the artifact root. Twelve focused tests
  passed. A single summary still lacks a run ID, so capture one isolated run per root. Windows
  reparse behavior and concurrent filesystem changes remain unverified; conservative refusal can
  reject unrelated links. It overlaps the other verifier changes and is integrated only in the
  local checkpoint described below, not on main.
- Draft [#137](https://github.com/genkimorimori252525-oss/Kneekura-bird/pull/137), head
  `07a48aae`, rejects non-integer, negative or regressing ticks before filtering the combat
  window, and hides partial telemetry metrics on tick errors. Seven tests and independent review
  passed. It does not prove complete telemetry or continuous separation. The later null-handling
  change is not yet in the local combined checkpoint and is not merged.
- Draft [#138](https://github.com/genkimorimori252525-oss/Kneekura-bird/pull/138), head
  `7cdef2c1`, requires exact unique scene completion values, ordered min/max, and counters no
  greater than the positive scene age. The 2000-tick age cap matches the current producer and
  must change with it. Age may not exceed elapsed server ticks under the fixed-mod normal tick
  contract, but may be less; arbitrary external same-tick calls are not covered. Fifteen tests
  and independent review passed. Its later window-invalid metric handling is locally integrated below.
- Draft [#139](https://github.com/genkimorimori252525-oss/Kneekura-bird/pull/139), head
  `5dda753b`, stacked on #134, requires the observed pilot ID to match the fixed villager fixture
  and pilot UUID. It depends on #132 strict JSONL and #137 ordered ticks; it does not qualify
  arbitrary mobs, fill missing ticks, or prove zero AI inputs after player takeover. Twenty-four
  focused tests passed. Draft [#140](https://github.com/genkimorimori252525-oss/Kneekura-bird/pull/140),
  head `121a892c`, stacked on #130, requires both aircraft to have a frame at every strict interior
  combat tick. Its 26 tests passed; all 11 earlier saved runs failed this new coverage condition.
  Missing frames do not establish a crash, and full frame coverage still does not prove continuous
  separation, physical contact or player control exclusion. Both drafts require joint integration.
  `kneekura-issue7-interior-frame-coverage-e416de9-20261103.zip` has SHA-256
  `a0166a0eddb9c7d002371c9e75e2ac893baa95c9caefdf25816f594c8bc342ff`; its input hashes were
  cross-checked against the earlier archives.
- These candidates independently start from main and edit the same verifier. Do not merge them as if
  they were already composed: reconcile and rerun their combined regression tests and saved-log
  analysis. Integration of #129–#132 has 55 focused tests and three saved-run reanalyses in a
  local worktree `/workspace/kneekura-mutual-integrated`, commit `038f9f5`. Its changes exceed
  the single-PR size limit and remain local. A further local integration of #133, #135 and #134
  is `/workspace/kneekura-mutual-integrated-expanded`, commit `15ab796`, tree `0d7e1304`:
  97 tests passed; saved #127 first/repeat and UUID low passed, while #128 failed for its 7.4
  sample and UUID high failed for no P-47N fire. This is reanalysis, not new GameTests. The
  expanded diff exceeds the PR limit. A further local integration of #136 is in
  `/workspace/kneekura-mutual-integrated-discovery`, commit `893ecb0`, tree `0774bbae`: 109 tests
  passed and the same five saved runs had the same verdicts. #136's artifact-root symlink policy
  is stricter than #132's telemetry discovery; integration tested both, but Windows remains untested.
  Adding #137 in `/workspace/kneekura-mutual-integrated-monotonic`, commit `29d56d4`, tree
  `31ece094`, produced 115 passing tests and the same five reanalysis verdicts. Adding #138 in
  `/workspace/kneekura-mutual-integrated-completion`, commit `149c46d`, tree `81f727ce`, produced
  124 passing tests and the same five verdicts, with an age-boundary fixture corrected. These large
  integrations must not become one PR.
  The subsequent #137 null-handling integration is `/workspace/kneekura-mutual-integrated-order-null`,
  commit `5f9c9a9`, tree `b487f2ab`: 125 tests passed and the same five verdicts. It preserves
  scan completeness and crash details when invalid tick order makes telemetry metrics unknown.
  Adding #138's age-versus-elapsed follow-up in `/workspace/kneekura-mutual-integrated-age-elapsed`,
  commit `d26648d`, tree `ad5f569c`, produced 129 passing tests and the same five verdicts. This
  large checkpoint is a reanalysis and exceeds the PR size limit; its changes remain unmerged.
  `/workspace/kneekura-mutual-integrated-window-null`, commit `8bd26d6`, tree `2d0f0d67`, adds
  invalid-window metric handling and participant/pilot identity checks, with 139 tests and the same
  five verdicts. Its `scene_window_valid` requires scanning, tick order, valid scene boundaries and
  participant identity; it is not a combat verdict or continuous safety proof.
  **Important:** those earlier `pass` verdicts do not establish safety through frame gaps. In the
  five saved runs, the P-47N lacks 299 / 276 / 198 / 220 / 521 interior ticks respectively
  (start < tick < completion), including three runs reported as pass. The initial opponent frame
  comes from fixture direct `applyControl`; its completion-tick frame can be absent because of
  teardown. Ground/velocity metrics describe observed frames only. #140 and the later local
  integration fail closed on interior coverage. Frame coverage alone still cannot prove continuous
  separation, bounding box contact, or same-tick order. Main's verifier also admits player pilot
  entity IDs if UUIDs match; #139 checks the fixed villager fixture. The production player gate,
  its regression test and the observed pilot type are distinct evidence.
  A later local integration with #130's observed-danger fix and #139–#140 is
  `/workspace/kneekura-mutual-integrated-coverage-split`, commit `8bfd29c`, tree `934f722a`:
  156 tests passed, but all 13 saved runs failed due to missing opponent interior frames; known
  7.4 and no-fire errors remain. The identical tree and per-change history are preserved on the
  **evidence-only, do not merge** branch `agent/issue7-verifier-integration-evidence-only`, GitHub
  head `7a41184c4bde2d828784af95a233da6c0d46a7c0`. A 12-file fixture commit was split into two
  six-file commits without changing the final tree. Reconcile the individual drafts separately.
  Independent review of `15ab796` also found that completion reason fields accept numeric prefixes
  with trailing text or duplicate keys and can accept minimum separation greater than maximum.
  A dangerous collision or ground frame in file order inside combat can also be hidden by a
  regressing tick. Drafts #137–#138 and the subsequent #137 correction to hide misleading partial
  metrics are combined locally; do not call the integration complete. No tick regression was
  observed in the 10 saved aircraft logs reviewed,
  but this is not a proof for every run. A further counterexample has scene `age_ticks` greater
  than completion tick minus start tick. Under the fixed-mod normal one-entity-tick-per-world-tick
  contract age cannot exceed elapsed ticks, though it may be smaller; the producer does not guard
  against arbitrary external mods invoking it more than once per tick. The #138 follow-up rejects
  the contradiction under that contract and is included in the latest local checkpoint.
  Broken-link and incomplete-read metric fixes are also on #132. A failed result with a
  semantically invalid collision row can still display partial valid samples. No GameTest was
  rerun merely for verifier-only changes.
- The main mutual verifier is single-scene. A candidate that accepts multi-aircraft summaries
  without validating each scene can incorrectly qualify unverified aircraft. Keep `aircraft=all`
  fail-closed until each result UUID, primary log, opponent and pilot UUID, combat and return
  evidence are matched per scene. Neither a frame nor a summary proves 40 consecutive stopped
  ticks or runway position by itself.
- To isolate the 7.4 sample, design opt-in, logged and versioned fixture UUID ordering before
  entity insertion, then compare both orders on fresh JVM/worlds. UUID ordering changes escape
  and combat choices; it does not make all flight deterministic. Preserve original thresholds,
  scenario inputs, status, crash reports and raw telemetry. Investigate actual contact separately.
- UUID order exploration is preserved at branch `agent/issue7-uuid-order-exploration-only`, GitHub
  commit `98e02be55f0f8f18d40997786e81027bb6c46a30`, tree `4f099c6d`, the same tree as local
  `66e29f5`. It is based on #128 and is not an integration PR. Explicit A6M mutual runs with low
  and high UUID order both built, passed simulator 12/12, and completed GameTest 64/64 with Gradle
  0. Four entity registrations were accepted and visible in both fresh worlds. Low: primary /
  opponent fire 6/1, scene minimum 11.75, adapter sampled minimum 10.9; the local #129–#132
  integrated verifier passed. High: fire 2/0, scene minimum 13.21, adapter sampled minimum 12.5;
  the verifier correctly failed because P-47N did not fire. The individual #133–#135 candidates
  also failed high; they are not integrated. These sparse rounded samples do not prove continuous
  separation or absence of contact. UUID also affects defense choices, and other randomness is
  not fixed; this comparison does not establish why the original 7.4 occurred. Keep #128 on hold.
  The fixture cannot rule out UUID collisions in unloaded chunks: use an empty new world and
  separate JVM for each run, preserve old worlds before starting, and check all 4 registrations and
  logs. Failure cleanup does not restore preexisting equipment; failure injection is untested.
- Independent same-server-tick 3D frame pairing found the #128 run had minimum 7.433 blocks and
  four paired ticks below 8, with 703 of 902 ticks paired and 199 missing. UUID low paired 720 /
  941 ticks, minimum 10.850; UUID high 1479 / 2001 ticks, minimum 12.413. Same tick is not guaranteed
  simultaneous; these do not establish continuous separation or bounding-box contact. High's P-47N
  has 522 missing frame ticks, including a 113-tick gap. Scene tracking counters read cached state
  on the primary side and cannot prove that the opponent was updated. Investigate entity ticks,
  chunk state and logger acceptance before attributing its missing fire to UUID order alone.
- Additional local artifacts are ephemeral: `kneekura-issue7-uuid-order-66e29f5-20261103.zip`
  SHA-256 `3afa745546c21b92b42dfc86f6f2896686f6a78716712998a12e9fead840368f`; the incremental
  `mutual-verifier-038f9f5-from-2585f44.bundle` SHA-256
  `6697f394875d7122b1583a29991db68e252ec64d9dde7c03703c6531efd649ed` and its README were
  verified by restoring with baseline `2585f44`. Pair-distance script and JSON are under
  `/workspace/issue7-evidence-20261103/mutual-frame-pair-distances-independent.*`.
  Expanded integration checkpoint bundle `mutual-verifier-15ab796-from-2585f44.bundle` has
  SHA-256 `bb85d01f8e5cf7e48d004c21552fe9118fdeb417f7aab89e100091413f77e460`; its README
  records the outstanding false passes, which the 97 tests did not discover.
  The #136-integrated `mutual-verifier-893ecb0-from-2585f44.bundle` has SHA-256
  `367ca0665309a1a7c7e802b6d60c5bbc7075e0dd989b8628c21a6326940e45c0`; its README and 109-test
  evidence explicitly retain the unresolved completion-value and tick-order false passes.
  The later `mutual-verifier-5f9c9a9-from-2585f44.bundle` has SHA-256
  `8101124922157f999cac5ad8126f20267e0c9552bb35866aa8316304dd38449e`; it was restored against
  `2585f44` and includes the 125-test checkpoint while retaining the age-versus-elapsed limit.
  The newer `mutual-verifier-d26648d-from-2585f44.bundle` has SHA-256
  `e6b4cf716f7fc220d3b92f1eb069d689cfbc7efd4f80c16cefb51ee6966c4352`; it contains the 129-test
  checkpoint. Its failed result can still display partial metrics for an invalid window or age.
  The 139-test `mutual-verifier-8bd26d6-from-2585f44.bundle` has SHA-256
  `e1051c50e667b0f101bc57f41b4bcd68ad7a79fb6395f1fab446f93bb0b449f0` and was restored from
  `2585f44`; its integration-only changes also exceed the single PR size limit.
  The newer 156-test `mutual-verifier-8bfd29c-from-2585f44.bundle` has SHA-256
  `822ea2c70630073c45185a29c547940f8593fdfc5e65d2507f7f1a1863f73b84` and was restored from
  the same baseline. Its 13 saved runs all fail the interior frame-coverage requirement.
  The independent analysis ZIP `kneekura-issue7-frame-pair-analysis-20261103.zip` has SHA-256
  `c2b8ff545cf16888cd13d4b058e9cdf7c2f3ba8d636738a2eb42678302ab7d2d`.
  The missing-frame analysis ZIP `kneekura-issue7-mutual-frame-gap-66e29f5-20261103.zip` has
  SHA-256 `e47fdadfdadc5df0c0e2499c7748ad9001a50e8ed31e07357ba269f4c38464ed`. The opponent's
  mission clock can be held by route ownership, so its unchanged count is conditional evidence;
  chunk loading, actual entity ticking and logger acceptance were not directly measured.
- A later opt-in probe is preserved on exploration-only branch `agent/issue7-mutual-observer-exploration`,
  GitHub commit `43c7cee418008a1376ef7e954286f72ffbe57459`, tree `1bbd128d`, same tree as local
  `dacb42c`. It samples before opponent rebind every 20 world ticks without forced loading; see
  `ww-debug-benchmark/MUTUAL_OBSERVER.md` on that branch for limitations and fresh-world requirement.
  Build and preflight 12/12 passed; low/high fixed-UUID runs used separate fresh worlds/JVMs and each
  GameTest passed 64/64, Gradle 0. The combined verifier rejected low (adapter 7.4, scene 8.22,
  fire 3/1) and passed high (adapter 9.4, scene 10.09, fire 9/1). Probe-free high previously had
  fire 2/0 and failed, so the missing-fire failure was not reproduced. Noise/probe effects are not
  isolated. Same-tick paired frame positions around low 7.4 are 7.448 / 7.433; the 8.22 scene value
  matches a cross-tick position pair, consistent with measurement-time differences but not proof of
  a unique cause or contact. In sampled missing-frame intervals, `position_entity_ticking=false`;
  short gaps have no sample and logging, retained references and tickCount have documented limits.
  Investigation files are in `mutual-observer-dacb42c-analysis-20261103/` in the ephemeral evidence
  directory. Do not attribute causality or weaken collision/fire criteria based on this correlation.
  Archive `kneekura-issue7-mutual-observer-dacb42c-20261103.zip` has SHA-256
  `01bccbc78d3b4dc79d78a165eff1e9eefb1b166a8ad07e13b3005192a4e85555` and contains the logged
  observations, verifier results and source patch, not mod jars or world data.
- The existing test manager forces chunks around the primary at server tick END and accumulates
  visited chunks until cleanup. Observer positions and forced-ticket updates are not simultaneous;
  other owners and ticket levels are not recorded. A short-lived, owned opponent ticket could change
  the test environment and load, and cannot establish ordinary server behavior. Before proposing it,
  investigate read-only logging of requested ownership, actual ticket state and timing. Do not
  remove unrelated forced chunks, change opening placement or relax safety constraints.
- A subsequent opt-in END-loop probe is on exploration-only branch
  `agent/issue7-mutual-ticket-observer-exploration`, GitHub commit
  `34e5c89c403ab8ba5e9b8d543e315df45a0cd34c`, tree `1d9ba048`, same tree as local `2b93260`.
  It makes no new forced-chunk calls or ticket requests. Build and preflight 12/12 passed; fixed-mod
  fresh-world low/high runs each passed GameTest 64/64, Gradle 0. Low verifier passed with fire 6/1,
  scene minimum 11.75 and adapter minimum 10.9; high failed with fire 7/0, scene minimum 13.96 and
  adapter minimum 19.3. Opponent frames were missing for 237 and 678 ticks respectively. At some
  same-tick/same-chunk pairs, earlier entity observation was not ticking while later END range was
  true. Their timing differs, so visibility cannot be isolated. In two cases a final set read was
  false before the 49th setter returned true; after-loop forced membership remains unknown. The
  validation's owner set records attempted additions, not exclusive ownership. Observations are
  intermittent and logging can alter runtime; no causal or continuous-safety conclusion follows.
  See `mutual-ticket-observer-2b93260-analysis-20261103/` in ephemeral evidence and this branch's
  `MUTUAL_TICKET_OBSERVER.md` for reproduction and limitations. Fresh worlds remain mandatory.
  The archive `kneekura-issue7-mutual-ticket-observer-2b93260-20261103.zip` has SHA-256
  `13d338a98bd39edc3eb172fb421e3ea4e0942fb956305c16b18de64cf892529c`.
- An additional same-fixed-position range/composite observer is on the exploration-only branch
  `agent/issue7-mutual-visibility-observer-exploration`, GitHub commit
  `49b75ae09abfba197139dc05b79688969548cd77`, tree `5ac265f1`, matching local `f5e2389`.
  Build and preflight 12/12 passed; fresh-world low/high runs each passed 64/64 GameTests and
  Gradle 0. Low verifier passed (fire 1/1, scene 10.85, adapter 10.1); high failed for no opponent
  fire (2/0, scene 13.21, adapter 12.5). In missing-frame intervals, END observations had range
  true / composite false at 9 low and 10 high points with forced-set reads true. Queries are not
  atomic, so visibility non-ticking is only inferred if state was stable between reads. Samples are
  intermittent; entity tick, collision and causality remain unproven. The high headline values
  matched an older no-probe run, but frame counts and combat counters differed. Source, input hashes
  and analysis are under ephemeral `mutual-visibility-f5e2389-analysis-20261103/`.
  The archive `kneekura-issue7-mutual-visibility-observer-f5e2389-20261103.zip` has SHA-256
  `ee1ee5774a54fce10100f558ca4fcba69fa4edf1f818e2fced515dc2b7423c8c`.
- Direct visibility observation is on `agent/issue7-mutual-direct-visibility-exploration`, GitHub
  commit `12328262a6304e556207e204b23372357156ab39`, tree `5baac13c`, matching local `733f6fb`.
  On fixed Minecraft 1.20.1 / Forge 47.4.20 the public `ServerLevel.isNaturalSpawningAllowed`
  method returns the entity visibility ticking condition; it is not evidence of general spawn
  eligibility. The opt-in probe requires the exact server class and versions; other runtime
  transformation remains possible. Build/preflight 12/12 passed, and fresh-world low/high each
  passed 64/64 GameTests / Gradle 0. Both failed the combat verifier: low opponent fire 0
  (scene 9.12, adapter 8.2), high adapter 7.4 (scene 8.07, fire 8/1). The direct visibility was
  false with range true at 9 low and 14 high END observations; query order is non-atomic, samples
  are intermittent, and cause/contact are not established. Inputs and the repeatable analysis are
  in `mutual-direct-733f6fb-analysis-20261103/` in ephemeral evidence.
  Archive `kneekura-issue7-mutual-direct-visibility-733f6fb-20261103.zip` has SHA-256
  `fba1320d013eba193a26455447f49a1a9b28d08f0d3c8d9ef896729ab10bb875`.
- **Temporary opponent region-ticket intervention is on hold, not implemented.** Fixed Forge's
  add/remove update normal and ticking trackers separately; an exception can leave partial state,
  and public range checks cannot prove that this owner's ticket was removed. Ticket comparison
  uses type identity hash and key but not `forceTicks`, so a unique key is not an absolute proof
  against every collision. Before any opt-in experiment, establish a ledger and independently
  observable cleanup for partial failure, scene exit, lost pilot/opponent, abort, timeout and
  server stop, with other-owner tickets and vanilla forced chunks preserved. Use separate fresh
  worlds/JVMs serially; static UUID-keyed scene/session maps also prohibit concurrent fixed-ID runs.
  `forceTicks=false`, explicit remove and a bounded expiry are distinct; expiry is not cleanup
  proof. Do not substitute persistent `ForgeChunkManager.forceChunk` or `forceTicks=true`.
  Ticket changes alter scheduling/load and cannot qualify normal servers; opening geometry and
  safety criteria remain unchanged. Issue #7 records the detailed remaining conditions.
- Local evidence archives are ephemeral. SHA-256: `kneekura-issue7-evidence-20261103.zip`
  `973cba1b0ef7e68808179616bf55762c7f3780c38a90992efe2f2f341c6cf6f8`;
  `kneekura-issue7-terrain-authority-final-20261103.zip`
  `448b1dacc6f219b847a28f890e994ffe56bc8648aed03308a9cc400e615074ce`;
  `kneekura-issue7-separation-investigation-20261103.zip`
  `79f7fde9240e196367709668a2f02b4a7257abdd4bcf3e03b39350348d9134d0`.
  The focused turn archive `a99dfc035ff14130eb40f926782af088d0f6caff03a2ece08bb6e22eaf89554e`
  contains a maneuver verifier pass but an overall mission timeout and Gradle failure, not a
  successful GameTest. Copy needed archives before this environment is discarded.

- Draft [#122](https://github.com/genkimorimori252525-oss/Kneekura-bird/pull/122) records this
  handoff. Draft [#123](https://github.com/genkimorimori252525-oss/Kneekura-bird/pull/123)
  contains fixed-mod safety regression tests; its current remote head is `42fb0813`, stacked on
  [#126](https://github.com/genkimorimori252525-oss/Kneekura-bird/pull/126). The earlier #123
  head `0364be1b` is preserved by branch `agent/control-safety-evidence-0364be1b`.
  Draft [#124](https://github.com/genkimorimori252525-oss/Kneekura-bird/pull/124) fixes a
  full/landing telemetry identity error. #126 isolates the new fixtures' individual logs without
  deleting them; general existing focused/dedicated log selection remains a separate issue. #124 head
  `23892040` preserves `aircraft=all` in synthetic tests; real multi-aircraft verification remains.
- With the same test and fixed mods, current main plus the test passed all 61 GameTests, while
  #101 head `9c21ca34e3f91485f71cf845063bc78fb4c66be2` failed the expected startup engine-input
  assertion. This demonstrates the specific no-avoidance-write case on the real mod, not all
  flight axes or collision safety. The first two fixture runs failed before the assertion because
  the test aircraft lacked usable fuel; their logs were preserved. The first corrected test source SHA-256:
  `22e31bf600b2cfddb7f2f936a9b333b80a35f5b6d589b9cb6fdc1de94c4a42d4`.
- On the passing main run, the original full verifier incorrectly selected a later unrelated
  test aircraft's two-frame log and returned pass. The summary aircraft UUID was different. The
  #124 fix reprocessed the saved run and selected the matching 4,838-frame log. Its streaming
  implementation reduced a synthetic 24-file load from about 1.25 GiB peak RSS to 10 MiB on
  Linux; this is not a 24-aircraft GameTest. The earlier #123 tree `3e661ea8` passed build,
  deterministic simulation 12/12 and real-mod GameTest 64/64. The current stacked tree `6abe4795`
  also passed 64/64 and preserved four fixture logs separately. Terrain and player takeover tests
  failed their intended assertions under separate unsafe local mutations. See
  `docs/validation/2026-11-03/collision-and-verifier.md`.
  Other scenario verifiers remain separate audit items. Draft
  [#125](https://github.com/genkimorimori252525-oss/Kneekura-bird/pull/125), stacked on #124,
  fails closed on damaged full/landing candidate logs; see its compatibility limits.
- Cloud evidence is under `/workspace/issue7-evidence-20261103/` in this instance, including
  mod hashes, logs, verifier results and the preserved first two run directories. This path is
  ephemeral: do not assume it exists in a later session. No mod jars were committed or published.
  The main test worktree is `/workspace/kneekura-collision-test`; local commit `9d7180a` has the
  first passing fixture; local `fb1c5c0` has the same tree as #123 head but a different commit ID.
  Additional test changes may follow; inspect live GitHub.
- Draft [#127](https://github.com/genkimorimori252525-oss/Kneekura-bird/pull/127), head
  `e774ae86`, reports terrain authority when this invocation dispatched a terrain-informed output
  during collision risk. Local `fcfddbe` has the same tree `05246519`: build 0, simulator 12/12,
  A6M full and mutual dogfight each GameTest 64/64, Gradle 0 and verifier pass. Full finished
  PARKED with route evidence; mutual recorded fire events 8/1, minimum separation 10.83 and zero
  combat ground frames. An earlier implementation `1ece7bf` crashed at required Mixin injection;
  that failure was retained and the injection target corrected without lowering `require=1`.
  #127 leaves the pre-existing stale terrain-only reporting case without collision risk unresolved;
  #128 proposes a separate fix, subject to the safety hold above. Dispatch does not prove
  reflection success.
- Before converting autonomy, separately verify combat suppression and the claimed-without-output
  case. The present tests cover player takeover input values and terrain input in controlled cases,
  not every axis and write count. A risk-only ownership label can disagree with the
  actual writer; do not silently treat that diagnostic label as evidence of an avoidance write.
- Static review found another #101 difference: if combat claims a tick without a proposal, its
  formation-proposal fallback differs from current main, where that proposal was never written.
  The test-only mutual-dogfight opponent also calls `AutonomousFlightManager.applyControl`
  directly and would discard its new return value. Audit both before redoing the conversion.
- [KNEEKURA TECH HUB](https://github.com/genkimorimori252525-oss/KNEEKURA-TECH-HUB) contains a
  SimLab analyzer and schema that may help future trajectory analysis. No compatibility with this
  mod's logs or calibrated aircraft physics is established; check conversion, provenance and
  applicable reuse conditions before relying on or redistributing its contents.

The owner explicitly activated **Jolly Endurance Mode** for this session. Starting checkpoint:
main `2585f44fa02b84ed7f593bf9a65798a2b4f056ea`. Live GitHub showed two open draft PRs,
[#101](https://github.com/genkimorimori252525-oss/Kneekura-bird/pull/101) and
[#121](https://github.com/genkimorimori252525-oss/Kneekura-bird/pull/121); the older
"Open pull requests: None" and conversion order below describe an earlier checkpoint, not
current state. No main check success can be inferred from the empty combined status.

Issue #7 remains open. The historical 24-aircraft route records and the limited mutual-dogfight
successes do not establish every aircraft's mission, role, and combat completion. First reproduce
basic air combat; afterward, aim for WWII-style techniques selected at appropriate times and
natural frequencies according to pilot proficiency. This sequencing was recorded on Issue #7.

PR #101 is retained as evidence, not a baseline to merge blindly. On its head `9c21ca34`, an
actual fixed-mod GameTest reproduced discarded base-autonomy engine input when collision risk held
but formation did not write avoidance. This is one controlled case, not flight safety as a whole.
On current main, base autonomy still writes before that branch, so the same loss has not been
established there. The arbiter can nevertheless report collision avoidance when that layer did
not write. Combat suppression must remain in force; do not equate a risk predicate with an
avoidance write. Before converting base autonomy, test the real arbiter path for a risk with no
avoidance write, a risk with an avoidance write, terrain priority, and player exclusion.

PR #121 is an unmerged hosted-validation preparation; it was not run. Its separation of fast
deterministic checks, a future calibrated exploration model, and fixed-mod Forge GameTests remains
the rule. Its description records build, 12/12 preflight, and A6M `full` success at the starting
main, but the original raw GameTest artifacts were not present in this environment for independent
inspection. They are not evidence for a subsequent code change. Historical route evidence also
has the build-time source-rewrite attribution caveat described below.

The managed Cloud instance has Java 17 at `/workspace/.cloud-setup/jdk-17.0.17+10` and Gradle 8.8
at `/workspace/.cloud-setup/gradle-8.8/bin/gradle`; its separate Gradle home is
`/workspace/.cloud-setup/gradle-home`. Fixed runtime mod jars and the earlier GameTest output were
absent in this checkout. Record mod versions and hashes and preserve fresh logs and verifier output
before treating any new run as evidence. The existing Cloud network policy is restricted and
enforced. GitHub Actions is stopped; do not enable it or change runner registration.

Next: finish the mutual verifier safety checks and fixed-input comparison design before treating
#128 as qualified. Review #126 → #123 → #127 → #128 and #124 → #125 as draft stacks, then cover
the combat claim-without-output branch and the test-only
opponent's direct autonomy call before retrying the proposal conversion on current main. Keep the
existing safety gates unchanged. Follow any behavior change with build, targeted fixed-mod GameTest
and telemetry/verifier inspection; do not call the test-only or approximate-model results real-mod
qualification. The raw Cloud artifacts are ephemeral, as documented in the validation record.

## Jolly Runner Hub multi-repository operation

Branch `agent/jolly-multi-runner-hub` extends `tools/JollyRunnerHub` with a `Runner 管理` tab for three independent repo-scoped Windows runners:

- Warfare Wings: `C:\actions-runner`, runner `ジョリー`
- Love-Github: `C:\actions-runner-love-github`, runner `ジョリー-Love-Github`, label `love-github`
- Durable Workflow: `C:\actions-runner-durable-workflow`, runner `ジョリー-Durable-Workflow`, label `durable-workflow`

The Hub now supports individual/all start and stop, auto-connects every configured runner, keeps process caches per profile, records the parent `cmd.exe` it starts, and treats a locked latest `_diag/Runner_*.log` as local liveness evidence when Windows redacts `Runner.Listener.exe` path/command-line fields. This last fallback prevents duplicate starts on this machine.

During the first live launch, before the fallback existed, the Hub failed to identify the already-running Warfare Wings listener and started the same registration again. GitHub kept the registration online, but listener continuity was interrupted once and the PID changed. After the fallback was installed, reopening the Hub preserved all three listener PIDs exactly (`13776,21144,21900`). Do not claim the original listener process was never interrupted.

The desktop build is installed at `C:\Users\genki\OneDrive\Desktop\JollyRunnerHub.exe`; `%LOCALAPPDATA%\JollyRunnerHub\profiles.json` contains all three profiles and no runner tokens. Love-Github PR #18 and Durable Workflow PR #12 now route Windows-compatible CI to dedicated labels. Durable's Ubuntu/container validation is retained separately as a manually dispatched hosted workflow because the current machine has no usable Linux/Docker runner.

Follow `/AGENTS.md` before changing code. Live GitHub state overrides older notes.

## Active operating mode

`Jolly Endurance Mode` / `ジョリー長航続モード` is active by explicit owner instruction.

This mode removes the default duration and remote-run stop limits only. Safety invariants, one immutable request at a time, one behavioral hypothesis per commit, evidence checkpoints, and the 10-file / 800-line patch ceiling remain authoritative. This is resumable interactive work, not background execution.

## Correction to every previous qualification record

Until PR #81 the Gradle build **rewrote its own source on every run**. Six `JavaCompile` `doFirst` actions across `build.gradle`, `settings.gradle` and `coupled-handoff-validation.gradle` patched `ww-debug-benchmark/src/main/java/com/wwdebug/autopilot/EnergyFighterApexYawAdapter.java` before compilation, changing five constants and injecting a 14-constant capture-entry-lag subsystem plus `updateTargetTurnRate` and `turnAwareLeadDirection`:

```
START_MIN_DISTANCE           82.0 -> 110.0
START_MIN_AGL                90.0 ->  80.0
CLIMB_TARGET_PITCH_DEG      -22.0 -> -10.0
PIVOT_COMPLETE_HEADING_DEG   65.0 ->  80.0
MAX_PIVOT_TICKS                96 ->   140
```

**Consequence:** every "qualified at commit X" statement in earlier revisions of this file was inaccurate — the behavior that was tested did not exist at X. The *behavior* evidence remains valid, so re-qualification is not required, but no earlier commit attribution should be trusted as reproducible.

PR #81 bakes the applied values into the source and deletes all six transforms. Equivalence is verified rather than asserted: compiling before and after produces byte-identical classes, `md5` of every `build/classes/java/main/**/*.class` is `9372e5c780dc98895d32d82053af2b2c` on both sides, and two consecutive `--rerun-tasks build` runs leave `git status --porcelain` empty.

## Hosted CI is blocked at account level

`WW Debug Benchmark build` and `WW Headless Flight GameTest` were rejected before creating any step, with the check-run annotation:

> The job was not started because recent account payments have failed or your spending limit needs to be increased.

This is neither minutes exhaustion nor a code defect. Per AGENTS.md, behavior changes must not be merged while required checks are unexecuted for this reason. The owner elected to move stage-1 validation onto the self-hosted runner permanently; that migration is the unlock and is on branch `agent/selfhosted-concurrency-safety`.

A local Gradle loop works today at zero Actions cost and completes a full build in ~18-25 s:

```
JAVA_HOME = C:\Program Files\Java\jdk-17
gradle    = C:\Users\genki\.gradle\wrapper\dists\gradle-8.8-bin\dl7vupf4psengwqhwktix4v1\gradle-8.8\bin\gradle
cwd       = <worktree>/ww-debug-benchmark
gradle --no-daemon --console=plain build
gradle --no-daemon --console=plain prepareFlightGameTestRuntime
```

There is no Gradle wrapper in this repository; invoke the cached distribution directly. A fresh worktree also needs the two gitignored runtime jars copied into `ww-debug-benchmark/flight-test-mods/`.

**Do not run a local Gradle build while the self-hosted runner is executing a qualification.** Both share `GRADLE_USER_HOME` (`C:\Users\genki\.gradle`) and can corrupt each other's ForgeGradle caches.

## Measured flight profiles are now version controlled

`AutopilotProfileRegistry.locateProfileFile` resolves `<config>/warfare_wings/flight_profiles.json` first, and `prepareFlightGameTestRuntime` stages the tracked fixture into exactly that path. The fixture previously held **fighters only (14 keys)**, and `AutonomousFlightManager:55-65` refuses to open a session without a measured profile.

Seven accepted qualifications (G4M, IL-2, B-17, B-29, Ju 87, SBD, D4Y) therefore depended on profiles that existed only inside expiring CI artifacts. All ten missing profiles were recovered from the originating run artifacts and committed in PR #80 as `validated_flight_profiles-24aircraft.json`; the bomber session measured all five bombers together and the attacker sessions all four attackers, so `g10n1`, `g10n2` and `he111` were recovered as well.

Integrity: each profile appeared in 4-8 independent artifact copies with **0 conflicting value sets** and **0 missing required fields**; role split is **14 fighter / 5 bomber / 4 attacker / 1 torpedo_bomber**. Per-aircraft provenance is in `docs/validation/2026-07-26/measured-profile-provenance.md`.

## Self-hosted runner operation

- Runner name `ジョリー`, id 22, root `C:\actions-runner`, manager `JollyRunnerHub.exe`.
- Required labels `[self-hosted, Windows, X64]`.
- Route workflow `.github/workflows/ww-local-route-validation.yml`.
- Request file `.github/local-route-validation-request.txt`, status file `.github/local-route-validation-status.json`.

### Dispatch without a no-op commit

`ww-local-route-validation.yml` accepts `workflow_dispatch` with `ref` and `aircraft` inputs, restricted to the repository owner. Use it instead of editing the request file; it avoids the no-op commits AGENTS.md prohibits:

```
gh workflow run ww-local-route-validation.yml --ref main \
  -f ref=<40-char behavior commit> -f aircraft=warfare_wings:<id>
```

### Always prove runner liveness before dispatching

Run `30154656783` (F6F) sat **queued 3h49m24s** and was finalised by GitHub with an internal error. Job `89670629423` shows `runner_id: 0`, `runner_name: ""`, `steps: []` and no log archive. `C:\actions-runner\_diag` shows the listener logged BrokerServer socket failures at `09:24:56Z`, last wrote at `09:44:33Z`, and produced **no Worker log after `08:50:47Z`** — the job was assigned at `10:32:57Z` into an already-dead listener.

`timeout-minutes: 110` is an *execution* timeout that arms at "Set up job", so it never applied, and because the only writer of the in-progress record runs on the runner, an undispatched job leaves zero repository trace.

Before every dispatch:

```
gh api repos/:owner/:repo/actions/runners -q '.runners[] | "\(.name) \(.status) busy=\(.busy)"'
```

After dispatch, confirm `runner_id != 0` on the job. **A run whose `runner_id` stays 0 is orphaned, not slow.**

### Concurrency was cancelling qualifications

Three physics workflows shared group `ww-local-self-hosted-validation` with `cancel-in-progress: true`, and `deploy-jolly-runner-hub.yml` targeted the same single runner with no group at all while firing on push and pull_request. That is why F4U job `89663345137` is recorded `cancelled` despite 14 green substantive steps with Post steps 26 and 27 stuck in_progress/pending.

Fixed on `agent/selfhosted-concurrency-safety`: physics uses `ww-selfhosted-physics` with `cancel-in-progress: false`; the Hub deploy and both stage-1 workflows have their own groups.

### Transient Forge maven failures

ForgeGradle contacts `maven.minecraftforge.net` while applying its plugin. A dropped TLS handshake fails the build in ~20 s with `SSLHandshakeException` / `SSL peer shut down incorrectly`. Because the build step carries `continue-on-error`, this surfaces only as the terminal "Fail after preserving route diagnostics" step and reads as an aircraft failure. Run `30175598909` (fw190) was lost exactly this way; the next dispatch built fine. A bounded single retry keyed on transient signatures is on the same branch.

## Exact-physics route qualification evidence

Qualified with terminal `PARKED`:

- A6M `30106085402`; G4M `30113770224`; IL-2 `30115029120`; B-17 `30115815404`; P-51D `30118532513`; Spitfire `30120064170`; B-29 `30120521495`; Ju 87 `30147903349`; SBD `30148395384`; D4Y `30148766789`; Yak-3 `30149217195`; Bf 109 `30151410943`; F4U `30151812704`; F6F `30175097134`; Ki-61 `30175707465`; Ki-84 `30175848558`; MC.202 `30176031935`; MiG-3 `30176210630`; P-40E `30176388410`; P-47N `30176568969`; G10N1 `30176753857`; G10N2 `30176938024`; He 111 `30177119529`; Fw 190 `30177411289`.

**Coverage is 24 of 24.** Role split complete: 14 fighter / 5 bomber / 4 attacker / 1 torpedo_bomber. Fw 190 needed one retry after a transient Forge maven TLS failure (`30175598909`); the identical behaviour ref then qualified it cleanly.

F4U run `30151812704` is recorded `failure` by GitHub because of the concurrency cancellation described above, while its status file records build, gametest and artifact all `success`. Treat it as qualified; the run-level verdict is an artifact of the cancel bug.

Each qualification requires ordered waypoint progression `3,2,1,0`, release to the ordinary mission, return, landing, braking, final `PARKED`, summary 1/1, Gradle status 0, and no crash report.

## Remaining route qualifications

None. Behavior ref used throughout: `4092d096f17e7aac34e19696b8a63f62f96b6c53`.

The navigate / return / land half of Issue #7 is complete and reproducible. The role and doctrine half is untouched.

## Base-aircraft inventory, settled

**24 base aircraft** (`data/warfare_wings/aircraft/*.json` excluding `_scheme` files), **90 aircraft EntityTypes** (24 base + 66 livery variants), role split **14 fighter / 5 bomber / 4 attacker / 1 torpedo_bomber**.

The historical "26" is 24 plus `immersive_aircraft:biplane` and `immersive_aircraft:bamboo_hopper`, because `BenchmarkManager.discover()` (`BenchmarkManager.java:160`) iterates the whole `ENTITY_TYPE` registry with no namespace filter. There is no 25th Warfare Wings aircraft; `mig21` exists as an unregistered `.bbmodel` and texture only.

## Known architectural defects

Numbering follows the earlier revision so closed items stay traceable.

1. **`ControlAuthorityArbiter` is a sequencer, not an arbiter.** Still open, and it gates all remaining role work. Every layer writes in fixed statement order and the winner is inferred afterwards by asking `active()`; priority exists only as the order of statements. PR #90 made the stack explicit (`Authority.priority()`, `outranks()`) and pinned it with `ControlAuthorityPriorityGameTests`, but deliberately did not change control flow.
2. ~~Player exclusion copy-pasted across eleven sites.~~ **Closed** by PRs #88 and #89. Every live production pilot test goes through `MobPilotGate`. The only `instanceof Player` left in `com.wwdebug.autopilot` are the two friendly-fire checks at `CombatTargetSelector.java:104` and `CombatWeaponManager.java:273`, which are target exclusion and deliberately not routed through the gate.
3. **`MissionOrder` is a data shell.** Still open. `MissionOrder.type()` has zero behavioural readers.
4. **Doctrine covers 2 of the 6 kinds Issue #7 needs.** Partly addressed: PR #86 added `AutopilotDoctrine` and a 24-aircraft classification resource, so doctrine now reaches the runtime. The enum still lacks the dive-bomber / ground-attacker split -- `ATTACKER` is one bucket covering D4Y, Ju 87, SBD and IL-2.
5. ~~`EnergyFighterReengagementAdapter`, 603 lines of dead code.~~ **Closed** by PR #83.
6. **Reruns can produce false passes.** Partly addressed: the migrated headless workflow purges `run-gametest/world|logs|crash-reports` before each scenario. `ww-local-route-validation.yml` still has no purge step.
7. **Priorities 2 and 3 have no implementation.** Still open, and now the largest capability gap. There is no health or damage logic anywhere in the autopilot package, though `MissionOrder.AbortCondition` already declares `PILOT_LOST`, `AIRCRAFT_DESTROYED` and `CRITICAL_DAMAGE`.
8. **`BenchmarkManager.applyControl` has no pilot check of its own.** It writes whenever `CONTROLS` holds an entry and relies entirely on the arbiter's gate above it. Not a live bypass -- the arbiter is its only caller -- but it is the one writer with no independent guard.
9. **"One final aircraft-input write" is not literally true.** `ReflectiveAircraft.applyControl` has **ten** call sites, **seven of them per-tick production writers**. An earlier revision of this file said four; that count came from a truncated search and was wrong.

   Production, in the order the arbiter reaches them: `BenchmarkManager:82`, `AutonomousFlightManager:104`, `FormationFlightManager:122` (collision avoidance) and `:212` (formation slot), then via `FighterCombatFacade` — `EnergyFighterApexYawAdapter:481`, `DefensiveAirCombatManager:77`, `AirCombatManeuverManager:101`.

   Test-only: `AutopilotValidationCheckpoint:147` (scenario seeding), `MutualDogfightOpeningAdapter:72` and `MutualDogfightValidationManager:225` (disposable opponent).

   So the claim holds only in the sense that the last writer of the tick overwrites the others. **Statement order is the priority mechanism** — which is exactly what the conversion has to remove, and why inserting a bomber or damage authority into that sequence is unsafe today.

10. **Collision avoidance is split across two classes that must agree.** `FighterCombatFacade` uses `AirspaceSafetyProbe.collisionRisk` to *suppress* combat, while `FormationFlightManager` decides independently whether to *write* the avoidance manoeuvre. The arbiter reports `COLLISION_AVOIDANCE` from the first while the aircraft is flown by the second. PR #92 gives both one predicate; before it they held duplicate copies of the same five constants.

## Control ownership is now observable

`applyControl` returns the tick's owner, and until PR #90 **nothing read it** -- `VehicleEntityBenchmarkMixin:20` calls it as a bare statement. Ownership is now written as a `control_authority_change` row on every handover, carrying both priorities and an `escalation` flag.

Confirmed against real flight data from run `30197987667`: 17 handovers across the two aircraft, for example

```
A6M  t=156   BASE_AUTONOMY(10)  -> TERRAIN_AVOIDANCE(80)           escalation=true
A6M  t=827   OFFENSIVE(40)      -> COLLISION_AVOIDANCE(70)         escalation=true
P47N t=877   OFFENSIVE(40)      -> DEFENSIVE_COMBAT(50)            escalation=true
P47N t=1464  DEFENSIVE(50)      -> ENERGY_FIGHTER_REENGAGEMENT(40) escalation=false
```

**Known limitation.** This records only the winner, so it cannot yet detect a true priority inversion -- a case where a higher-priority condition holds while a lower layer owns the tick. `escalation=false` merely means the previous higher-priority condition ended, which is normal. Detecting inversion needs the set of layers that *claimed* the tick, which only the proposal-based conversion can provide.

## Stage 1 of Issue #7 is satisfied

`dogfight_mutual` passed three consecutive times on three different heads -- runs `30183880865`, `30192528884`, `30193276288` -- with both aircraft firing, minimum separation 9.4 in all three, and zero ground frames. PR #6 never achieved this; its best was A6M 7 / P-47N 0.

Caveat: the exchange is lopsided at A6M 8-9 shots against P-47N 1. Acceptance is met; converting more P-47N re-entries into firing solutions is a stage-2 doctrine-tuning item, not the geometry deadlock PR #6 was stuck on.

## Regression baseline

`docs/validation/2026-07-26/route-regression-signatures.json` holds one signature per base aircraft, extracted from that aircraft's own qualification artifact: exact match on role, verdict, reason, final phase and terminal reason; tolerance match on tick counts and geometry. Diff against this rather than re-arguing whether a change was harmless.

## Open pull requests

None. Everything opened this session is merged.

The owner's local branch `agent/p47-local-validation` (505 commits behind main, 33 unpushed commits of P-47N research) is deliberately untouched. All work happened in worktrees created off `origin/main`. That branch's subject -- the P-47N mutual dogfight -- is resolved on main, so the branch is research history, not a baseline.

## Next exact actions

1. Convert `ControlAuthorityArbiter` to proposals, in bounded PRs. Each controller returns an `Optional<ControlProposal>` carrying its `Authority` and `FlightControlOutput` instead of writing; the arbiter selects the highest priority and performs the single write. Verify with a GameTest asserting exactly one `ReflectiveAircraft.applyControl` per aircraft per tick, and by diffing the `control_authority_change` sequence against the pre-conversion baseline above.
2. Add an `AircraftDamageAuthority` at levels 2-3, evaluating the already-declared `AbortCondition` constants. Do it after the conversion so it can be inserted by priority rather than by statement order, and before any bomber work.
3. Give `MissionOrder.type()` its first behavioural consumer by routing `RETURN_TO_BASE` and `LAND` through the qualified landing chain.
4. Split `ATTACKER` into dive-bomber and ground-attacker, and replace the empty `escort` on the five bombers and G4M.
5. Only then start bomber, attacker and torpedo missions.

Do not run a local Gradle build while the self-hosted runner has a job: both use the same `GRADLE_USER_HOME` and can corrupt each other's ForgeGradle caches. Check first:

```
gh api repos/:owner/:repo/actions/runners -q '.runners[]|"\(.name) \(.status) busy=\(.busy)"'
```
