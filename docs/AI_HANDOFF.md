# AI development handoff

Last updated: 2026-07-25 (Asia/Tokyo)

Follow `/AGENTS.md` before changing code. Live GitHub state overrides older notes.

## Active operating mode

`Jolly Endurance Mode` / `ジョリー長航続モード` is active by explicit owner instruction.

This mode removes the default duration and remote-run stop limits only. Safety invariants, one immutable request at a time, one behavioral hypothesis per commit, evidence checkpoints, and the 10-file / 800-line patch ceiling remain authoritative. This is resumable interactive work, not background execution.

## Current production baseline

Production owned-route guidance remains below player-control, emergency, terrain, collision, and combat authority. No weapon, timeout, waypoint-radius, landing-geometry, or minimum-separation rule has been relaxed.

Merged route milestones include:

- PR #53: live owned-route guidance integrated into the single final aircraft-input path;
- PR #58: G4M metadata recovery and `torpedo_bomber` common-flight admission;
- PR #59: IL-2 attacker representative route proof;
- PR #60: B-17 level-bomber compact route proof;
- PR #63: Windows self-hosted generic route workflow;
- PR #64: profile-driven compact route geometry and arbitrary-aircraft strict evidence;
- PR #65: route-workflow post-processing hardening;
- PR #73: disconnected `PatternRejoinBudget` feasibility foundation;
- PR #70: owned-route clock accounting plus measured pattern-rejoin speed, merged after exact-head Windows validation;
- PR #76: truthful JollyRunnerHub GitHub-connection state classification, merged as `9dce7f08fee66255b7979d986f2b713c00b6c5b5`.

`MissionRouteClockPolicy` allows owned `CRUISE_OUTBOUND` travel to satisfy the fixed 240-tick sample while the overall mission timeout remains frozen. `PatternRejoinSpeedPolicy` commands at least measured `turnSpeedFloorBps` only during `RETURN_TO_PATTERN`. `PatternRejoinBudget` remains disconnected from live control.

## Windows self-hosted runner operation

- Runner name: `ジョリー`.
- Owner PC runner root: `C:\actions-runner`.
- Owner-facing manager: desktop `JollyRunnerHub.exe`.
- Required workflow labels: `[self-hosted, Windows, X64]`.
- Route workflow: `.github/workflows/ww-local-route-validation.yml`.
- Request file: `.github/local-route-validation-request.txt`.
- Status file: `.github/local-route-validation-status.json`.

PR #76 corrected an operational ambiguity: a live `Runner.Listener.exe` process alone no longer displays as proof of GitHub job readiness. The Hub now classifies log-backed states such as starting, connected-starting, listening, running-job, post-job confirmation, and reconnecting. Qualification acceptance still requires a new matching `run_id` and `status: in_progress` in the repository status file.

PR #76 exact head `4326c0d8aeaaa1f979a8aedad67104cc87df6810` passed Windows Run `30151239678`. The successful job completed PowerShell 5.1 syntax validation, deterministic classifier samples, runtime injection, generated-script syntax validation, launcher compilation, hidden WinForms startup smoke testing, and portable artifact upload. No aircraft behavior, route request, timeout, geometry, landing, combat, weapon, terrain, collision, player-control, or acceptance rule changed.

## Exact-physics route qualification evidence

Fully qualified with terminal `PARKED`:

- A6M — Run `30106085402`;
- G4M — Run `30113770224`;
- IL-2 — Run `30115029120`;
- B-17 — Run `30115815404`;
- P-51D — Run `30118532513`;
- Spitfire — Run `30120064170`;
- B-29 — Run `30120521495`;
- Ju 87 — Run `30147903349`;
- SBD — Run `30148395384`;
- D4Y — Run `30148766789`;
- Yak-3 — Run `30149217195`.

Current coverage is 11 of 24 base aircraft. All four attackers and all three turn fighters have exact-physics generic-route evidence.

Each qualification requires ordered waypoint progression `3,2,1,0`, release to the ordinary mission, return, landing, braking, final `PARKED`, summary 1/1, Gradle status 0, and no crash report.

## Current live request

The current request remains:

- request commit: `bb9665eb6b0bc0c4e22a777127c1013335de9aec`;
- immutable behavior ref: `bc790bca60267a7339103c6ed5d29b95eae3ceac`;
- aircraft: `warfare_wings:bf109`.

At this checkpoint `.github/local-route-validation-status.json` still records completed Yak-3 Run `30149217195`. There is no repository-side Bf 109 start record yet. Do not rewrite, duplicate, or no-op-trigger the Bf 109 request while this remains true.

## Remaining base-aircraft route qualifications

Energy fighters, in current execution order:

- `warfare_wings:bf109` — already requested, awaiting matching start record;
- `warfare_wings:f4u`;
- `warfare_wings:f6f`;
- `warfare_wings:fw190`;
- `warfare_wings:ki61`;
- `warfare_wings:ki84`;
- `warfare_wings:mc202`;
- `warfare_wings:mig3`;
- `warfare_wings:p40e`;
- `warfare_wings:p47n`.

Bombers:

- `warfare_wings:g10n1`;
- `warfare_wings:g10n2`;
- `warfare_wings:he111`.

## Repository state

- Parent roadmap: Issue #7 is the only open issue.
- PR #76 is merged as `9dce7f08fee66255b7979d986f2b713c00b6c5b5`.
- No behavior pull request is currently open.
- Latest completed route status remains Yak-3 Run `30149217195`.
- `ジョリー長航続モード` remains active.

## Preserved invariants

- player-controlled aircraft receive no AI input;
- terrain, collision, combat, and emergency control remain above route guidance;
- there is one final aircraft-input write;
- noncombat route orders do not grant weapon authority;
- fixed-gun, line-of-sight, range, friendly-fire, and minimum 8-block separation rules are unchanged;
- no return timeout, waypoint radius, landing geometry, or safety threshold was relaxed.

## Next exact action

1. Read `.github/local-route-validation-status.json`, the request file, and recent commits.
2. If no matching Bf 109 `in_progress` or completed Run ID exists, do not alter or retrigger the request.
3. Once a matching fresh Bf 109 Run ID appears, follow only that run through build, exact-physics route, return, landing, diagnostics, and finish persistence.
4. On success, record artifact-backed evidence and continue serially with `warfare_wings:f4u` from the then-current `main`.
5. On failure, fetch logs and artifact once, identify the first meaningful acceptance failure, and create one focused Draft PR only when a code change is necessary. Do not weaken timeouts, geometry, radii, firing gates, or safety thresholds.
