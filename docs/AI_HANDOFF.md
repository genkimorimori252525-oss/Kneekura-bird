# AI development handoff

Last updated: 2026-07-26 (Asia/Tokyo)

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

- A6M `30106085402`; G4M `30113770224`; IL-2 `30115029120`; B-17 `30115815404`; P-51D `30118532513`; Spitfire `30120064170`; B-29 `30120521495`; Ju 87 `30147903349`; SBD `30148395384`; D4Y `30148766789`; Yak-3 `30149217195`; Bf 109 `30151410943`; F4U `30151812704`; **F6F `30175097134`**; **Ki-61 `30175707465`**.

F4U run `30151812704` is recorded `failure` by GitHub because of the concurrency cancellation described above, while its status file records build, gametest and artifact all `success`. Treat it as qualified; the run-level verdict is an artifact of the cancel bug.

Each qualification requires ordered waypoint progression `3,2,1,0`, release to the ordinary mission, return, landing, braking, final `PARKED`, summary 1/1, Gradle status 0, and no crash report.

## Remaining route qualifications

Behavior ref in use: `4092d096f17e7aac34e19696b8a63f62f96b6c53`.

Outstanding: `fw190` (transient build failure, needs retry), `ki84`, `mc202`, `mig3`, `p40e`, `p47n`, then bombers `g10n1`, `g10n2`, `he111`.

## Base-aircraft inventory, settled

**24 base aircraft** (`data/warfare_wings/aircraft/*.json` excluding `_scheme` files), **90 aircraft EntityTypes** (24 base + 66 livery variants), role split **14 fighter / 5 bomber / 4 attacker / 1 torpedo_bomber**.

The historical "26" is 24 plus `immersive_aircraft:biplane` and `immersive_aircraft:bamboo_hopper`, because `BenchmarkManager.discover()` (`BenchmarkManager.java:160`) iterates the whole `ENTITY_TYPE` registry with no namespace filter. There is no 25th Warfare Wings aircraft; `mig21` exists as an unregistered `.bbmodel` and texture only.

## Known architectural defects, evidence-backed

1. `ControlAuthorityArbiter` is a **sequencer, not an arbiter**: `ControlAuthorityArbiter.java:48-53` calls four subsystems unconditionally in fixed order and infers the winner afterwards. Its own Javadoc at `:10-13` concedes lower-priority controllers may apply output first. This must be converted before any bomber, attacker or torpedo doctrine is layered on top.
2. Player exclusion — the top requirement of Issue #7 — is enforced by **13 copy-pasted `instanceof Player` checks across 11 production classes**, with no single gate.
3. `MissionOrder` is a data shell: `MissionOrder.type()` has **zero behavioral readers**; every payload field is read only by `MissionOrderCodec` for NBT.
4. Doctrine is behaviorally implemented for **2 of the 6** doctrines Issue #7 requires; `AirCombatDoctrineTuning.resolve` switches only on `turn_fighter` and `energy_fighter`. The 5 bombers plus G4M carry a semantically empty `escort`.
5. `EnergyFighterReengagementAdapter.java` is **603 lines of dead code** — verified zero references outside its own class declaration and private constructor.
6. Reruns can produce **false passes**: nothing purges `run-gametest/world|logs|crash-reports` between runs and the Python verifiers select telemetry by newest mtime. A purge step was added to the migrated headless workflow; the route workflow still needs one.
7. Target priorities 2 and 3 (pilot lost, aircraft destroyed, critical damage) have **no implementation** — there is no health or damage logic anywhere in the autopilot package, although `MissionOrder.AbortCondition` already declares the constants.

## Open pull requests

| Branch | PR | Contents |
| --- | --- | --- |
| `agent/commit-measured-profiles-all24` | #80 | 24-aircraft measured profile fixture and provenance |
| `agent/deterministic-build-source` | #81 | bakes applied values, deletes all six source transforms |
| `agent/selfhosted-concurrency-safety` | — | concurrency groups, stage-1 self-hosted migration, transient-build retry |

The owner's local branch `agent/p47-local-validation` (505 commits behind main, 33 unpushed commits) was deliberately left untouched; all work happened in worktrees created off `origin/main`.

## Next exact actions

1. Finish the outstanding route qualifications to reach 24/24, retrying `fw190`.
2. Push `agent/selfhosted-concurrency-safety` **only while no qualification is running** — it edits `deploy-jolly-runner-hub.yml` and both stage-1 workflows, all of which start self-hosted jobs on push.
3. With stage-1 executable again, take PRs #80, #81 and the CI branch out of Draft, let the self-hosted checks run, and merge in that order.
4. Delete the dead `EnergyFighterReengagementAdapter`, then extract a single `MobPilotGate` and route every production writer plus both mixin injection points through it, with a GameTest asserting zero AI writes for a player-piloted aircraft.
5. Convert `ControlAuthorityArbiter` into a real arbiter across five bounded PRs before starting bomber, attacker or torpedo doctrine work.
