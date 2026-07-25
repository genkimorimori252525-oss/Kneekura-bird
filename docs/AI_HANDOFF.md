# AI development handoff

Last updated: 2026-07-25 (Asia/Tokyo)

Follow `/AGENTS.md` before changing code. Live GitHub state overrides older notes.

## Active operating mode

`Jolly Endurance Mode` / `ジョリー長航続モード` is active by explicit owner instruction.

Activation baseline:

- mode-definition commit: `fa729e2824bbc9adcc52d0ce41da7828503705ce`;
- last fully qualified aircraft: Yak-3, Run `30149217195`;
- current qualification request commit: `bb9665eb6b0bc0c4e22a777127c1013335de9aec`;
- requested immutable behavior head: `bc790bca60267a7339103c6ed5d29b95eae3ceac`;
- requested aircraft: `warfare_wings:bf109`;
- status at activation still showed the completed Yak-3 run, so the Bf 109 request must not be duplicated while awaiting a fresh start record.

While this mode remains active, the default 60-minute / 8-run stop and 30-minute / 4-run approval pause are suspended. Continue serial aircraft qualification and focused hypothesis work without waiting for another owner message. Preserve a durable checkpoint every four remote runs or at every merge, major qualification milestone, terminal failure, or hypothesis change. Duration limits are lifted; safety, evidence, one-request-at-a-time operation, one-hypothesis-per-commit discipline, and patch-size limits remain authoritative. This is resumable interactive work, not background execution; record the exact state before every interaction ends.

## Current production baseline

Production owned-route guidance remains below player-control, emergency, terrain, collision, and combat authority. No weapon, timeout, waypoint-radius, landing-geometry, or minimum-separation rule has been relaxed.

Merged route milestones:

- PR #53: live owned-route guidance integrated into the single final aircraft-input path;
- PR #58: G4M legacy metadata recovery and `torpedo_bomber` common-flight admission;
- PR #59: IL-2 attacker representative route proof;
- PR #60: B-17 level-bomber compact route proof;
- PR #63: dedicated Windows self-hosted generic `route` validation workflow;
- PR #64: profile-driven compact route geometry and arbitrary-aircraft strict evidence, merged as `a91c610b970721e3508dca4c1460e75b262ec3d0`;
- PR #65: route-workflow post-processing hardening, merged as `9ee8e899c74a49cf20313e5eb6f18eabe14bffb6`;
- PR #73: disconnected `PatternRejoinBudget` feasibility foundation, merged as `c55b764b833b8fb70a995c3dcc57246cd3fb7e61`;
- PR #70: owned-route clock accounting plus measured pattern-rejoin speed, squash-merged as `dd2dc9c7e9d3042b3dd4a0511a7ea5da935e5860` after exact-head Windows validation.

The generic route plan derives four waypoints from measured `FlightProfile` role, cruise speed, live position, and live heading. Supported roles are fighter, bomber, attacker, and torpedo bomber. Unknown roles and malformed geometry inputs are rejected deterministically.

`MissionRouteClockPolicy` allows owned `CRUISE_OUTBOUND` travel to satisfy the fixed 240-tick sample while the overall mission timeout remains frozen. `PatternRejoinSpeedPolicy` commands at least the measured `turnSpeedFloorBps` only during `RETURN_TO_PATTERN`. `PatternRejoinBudget` remains disconnected from live control and reports ideal reach, required speed, block margin, and margin ratio.

## Windows self-hosted runner reference

- Runner name: `ジョリー`.
- Owner PC runner root: `C:\actions-runner`.
- Owner-facing manager: desktop `JollyRunnerHub.exe`.
- Expected UI when locally connected: `Runner: 接続中`; the validation count may remain zero until GitHub assigns a job.
- Required workflow labels: `[self-hosted, Windows, X64]`.
- Generic route workflow: `.github/workflows/ww-local-route-validation.yml`.
- Request file: `.github/local-route-validation-request.txt`.
- Status file: `.github/local-route-validation-status.json`.
- Diagnostics artifact name: `ww-local-route-<run_id>`.

Operational interpretation:

1. `JollyRunnerHub.exe` showing connected means the runner process is online; it does not itself prove that GitHub accepted the current request.
2. A request is accepted only when the status file changes to a new `run_id` with `status: in_progress`, matching `event_sha`, requested ref, and aircraft.
3. Before writing a request, read the request file, status file, recent commits, and this handoff. If the status is already `in_progress`, do not touch the request.
4. Trigger exactly once by writing an immutable 40-character behavior commit and one aircraft ID. Never use a no-op commit or duplicate update merely because assignment is delayed.
5. The status file can temporarily remain on the previous completed run after a new request commit. This assignment delay is not evidence that the runner is offline.
6. `Set up Gradle 8.8` may remain in progress for several minutes on this Windows runner. Do not cancel or duplicate an otherwise live job because that step is slow.
7. Follow the same run through build, exact-physics GameTest, diagnostics upload, and finish persistence. On failure, fetch logs and artifact once and stop before selecting a materially different hypothesis.
8. A successful workflow step alone is insufficient for qualification; verify route order, ordinary mission release, return, landing, final `PARKED`, summary 1/1, Gradle status 0, and crash count 0 from the artifact/verifier evidence.

The recent requests for Ju 87 Run `30147903349`, SBD Run `30148395384`, D4Y Run `30148766789`, and Yak-3 Run `30149217195` were accepted and completed successfully by this runner. Therefore the self-hosted path is proven operational; future sessions must not describe it as unavailable solely because a fresh request has not yet received its start-status commit.

## Exact-physics qualification evidence

Fully qualified with terminal `PARKED`:

- A6M terrain-precedence proof — Run `30106085402`;
- G4M compact torpedo-bomber route — Run `30113770224`;
- IL-2 compact attacker route — Run `30115029120`;
- B-17 compact level-bomber route — Run `30115815404`;
- P-51D generic profile-driven route — Run `30118532513`;
- Spitfire generic turn-fighter route — Run `30120064170`;
- B-29 generic bomber route — Run `30120521495`;
- Ju 87 generic attacker route — Run `30147903349`;
- SBD generic attacker route — Run `30148395384`;
- D4Y generic attacker route — Run `30148766789`;
- Yak-3 generic turn-fighter route — Run `30149217195`.

Current coverage is 11 of 24 base aircraft. All four attackers — Ju 87, SBD, IL-2, and D4Y — and all three turn fighters — A6M, Spitfire, and Yak-3 — now have exact-physics generic-route evidence.

Each completed qualification required ordered waypoint progression `3,2,1,0`, release to the ordinary mission, return, landing, braking, final `PARKED`, passed summary, Gradle status 0, and no crash reports. B-29 performed a safe go-around before its successful final landing. Ju 87, SBD, D4Y, and Yak-3 each used two bounded native flare extensions below 20 blocks before normal touchdown.

## Ju 87 resolution and attacker follow-through

Earlier production Run `30122172937` completed the route but timed out during `RETURN_TO_PATTERN`. Isolated Runs `30123421732` and `30124721947` proved two independent contributors:

- owned outbound route travel was not credited toward the fixed 240-tick outbound sample;
- long pattern rejoin commanded the lower climb target instead of the measured turn-speed floor.

PR #70 combined only those two established effects. Exact behavior head `361078f30f1dd348fa274050f89cdf413525d49e` passed Windows Run `30147903349`:

- route advanced `3 -> 2 -> 1 -> 0`;
- route completed at server tick `3969` and ordinary `CRUISE_OUTBOUND -> TURN_LEFT` followed at tick `3971`;
- `RETURN_TO_PATTERN` commanded `18.75373230144395 BPS` and reached `DOWNWIND` inside the unchanged 1,800-tick timeout;
- landing progressed through `DOWNWIND -> BASE -> FINAL -> FLARE -> TOUCHDOWN -> BRAKE -> PARKED`;
- verifier passed with Gradle status 0, summary 1/1, and zero crash reports.

The merged behavior then qualified the remaining attackers without further code changes:

- SBD Run `30148395384`: route completed at tick `3804`, ordinary mission resumed at `3806`, final `PARKED`, elapsed `4789` ticks, summary 1/1, crash 0;
- D4Y Run `30148766789`: route completed at tick `3515`, ordinary mission resumed at `3574`, final `PARKED`, elapsed `3938` ticks, summary 1/1, crash 0.

D4Y retained the ordinary outbound clock until tick 3574 because its compact route completed before the held counter reached the fixed release threshold; this is expected and does not replay the 240-tick sample from zero.

## Yak-3 turn-fighter qualification

Yak-3 used behavior head `e1174b4947acba0dedec30b964e87d43a8d3570a` and passed Windows Run `30149217195` without behavior changes:

- route ownership began at server tick `645`;
- remaining waypoints advanced `3,2,1,0` at ticks `685`, `732`, `785`, and `811`;
- ordinary `CRUISE_OUTBOUND -> TURN_LEFT` occurred at tick `885`, using the fixed outbound sample without replaying it from zero;
- `RETURN_TO_PATTERN` began at tick `1738`, followed by `DOWNWIND` at `2870`, `BASE` at `2988`, and `FINAL` at `3069`;
- two bounded native flare extensions occurred at ticks `3442` and `3663`, followed by `TOUCHDOWN` at `3669`, `BRAKE` at `3679`, and `PARKED` at `3728`;
- final reason was `complete_stop_stable_for_40_ticks`;
- verifier passed with elapsed `3723` ticks, Gradle status 0, summary 1/1, and zero crash reports.

No timeout, route geometry, waypoint radius, landing-pattern geometry, terrain, collision, stall, combat, weapon, player-control, or separation threshold changed.

## Remaining base-aircraft route qualifications

Unqualified energy fighters, in current execution order:

- `warfare_wings:bf109` — request already committed and awaiting acceptance;
- `warfare_wings:f4u`;
- `warfare_wings:f6f`;
- `warfare_wings:fw190`;
- `warfare_wings:ki61`;
- `warfare_wings:ki84`;
- `warfare_wings:mc202`;
- `warfare_wings:mig3`;
- `warfare_wings:p40e`;
- `warfare_wings:p47n`.

Unqualified bombers:

- `warfare_wings:g10n1`;
- `warfare_wings:g10n2`;
- `warfare_wings:he111`.

## Repository state

- Parent roadmap: Issue #7 is the only open issue.
- PR #70 is merged as `dd2dc9c7e9d3042b3dd4a0511a7ea5da935e5860`.
- No behavior pull request is currently open.
- Latest completed route status is Yak-3 Run `30149217195`: build success, GameTest success, artifact success.
- Diagnostic artifact: `ww-local-route-30149217195`.
- All three turn fighters have route evidence.
- `ジョリー長航続モード` is active.
- Bf 109 request commit `bb9665eb6b0bc0c4e22a777127c1013335de9aec` points to behavior head `bc790bca60267a7339103c6ed5d29b95eae3ceac`; do not duplicate it while the status file still shows the previous Yak-3 completion.

## Preserved invariants

- player-controlled aircraft receive no AI input;
- terrain, collision, combat, and emergency control remain above route guidance;
- there is one final aircraft-input write;
- noncombat route orders do not grant weapon authority;
- fixed-gun, line-of-sight, range, friendly-fire, and minimum 8-block separation rules are unchanged;
- no return timeout, waypoint radius, landing geometry, or safety threshold was relaxed.

## Next exact action

1. Read `.github/local-route-validation-status.json` and recent commits for acceptance of Bf 109 request commit `bb9665eb6b0bc0c4e22a777127c1013335de9aec`.
2. Once a fresh Bf 109 Run ID appears, follow that single run through build, exact-physics route, return, landing, diagnostics, and finish persistence.
3. If Bf 109 passes, record artifact-backed evidence and immediately continue with `warfare_wings:f4u` on the then-current `main` without another approval pause.
4. Continue the listed energy fighters serially. At four completed remote runs, write a durable checkpoint and continue under `ジョリー長航続モード`.
5. On any failure, fetch logs and artifact once, identify the first meaningful acceptance failure, and open one focused draft PR only if a code change is necessary. Do not change timeouts, geometry, radii, or safety thresholds blindly.