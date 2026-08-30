# AI development handoff

Last updated: 2026-08-30 (Asia/Tokyo)

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
