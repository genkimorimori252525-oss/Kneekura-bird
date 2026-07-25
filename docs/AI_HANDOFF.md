# AI development handoff

Last updated: 2026-07-25 (Asia/Tokyo)

Follow `/AGENTS.md` before changing code. Live GitHub state overrides older notes.

## Active operating mode

`Jolly Endurance Mode` / `ジョリー長航続モード` is active by explicit owner instruction.

This mode removes the default duration and remote-run stop limits only. Safety invariants, one immutable request at a time, one behavioral hypothesis per commit, evidence checkpoints, and the 10-file / 800-line patch ceiling remain authoritative. This is resumable interactive work, not background execution.

The first four-run endurance checkpoint focused on truthful Runner Hub state reporting. Runs `30150918047`, `30151020291`, and `30151136845` exposed three distinct Windows PowerShell 5.1 compatibility defects; exact-head Run `30151239678` passed the classifier samples, source/runtime syntax, launcher build, and hidden WinForms startup smoke test. PR #76 was then merged and main deployment Run `30151334839` succeeded.

## Current production baseline

Production owned-route guidance remains below player-control, emergency, terrain, collision, and combat authority. No weapon, timeout, waypoint-radius, landing-geometry, or minimum-separation rule has been relaxed.

Merged route and tooling milestones include:

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

PR #76 corrected the old process-only `接続中` ambiguity. The Hub now distinguishes stopped, starting, connected-starting, GitHub listening, GitHub job execution, post-job confirmation, and reconnecting from the listener process plus Hub/Actions Runner logs. Qualification acceptance still requires a new matching `run_id` and `status: in_progress` in the repository status file.

PR #76 exact head `4326c0d8aeaaa1f979a8aedad67104cc87df6810` passed Windows Run `30151239678`. Main deployment Run `30151334839` then installed or staged the updated desktop executable from merge `9dce7f08fee66255b7979d986f2b713c00b6c5b5`.

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
- Yak-3 — Run `30149217195`;
- Bf 109 — Run `30151410943`;
- F4U — Run `30151812704`.

Current coverage is 13 of 24 base aircraft. All four attackers, all three turn fighters, and Bf 109, P-51D, and F4U from the energy-fighter group have exact-physics generic-route evidence.

Each qualification requires ordered waypoint progression `3,2,1,0`, release to the ordinary mission, return, landing, braking, final `PARKED`, summary 1/1, Gradle status 0, and no crash report.

## Bf 109 energy-fighter qualification

The original Bf 109 request produced no start record even while the same runner completed four Hub PR runs and one main deployment. After that absence was recorded on Issue #7, a single justified recovery request commit `e2cc3cec67533d045c0e7fb72e9657ab5ce76d26` reused immutable behavior head `bc790bca60267a7339103c6ed5d29b95eae3ceac`.

Windows Run `30151410943` passed without behavior changes:

- ordered route remaining `3,2,1,0` at server ticks `678,724,777,803`;
- route completion at `803` and ordinary `CRUISE_OUTBOUND -> TURN_LEFT` at `879`;
- `RETURN_TO_PATTERN` at `1769`, commanding measured `34.607300034367945 BPS` from phase tick 1;
- `DOWNWIND` at `2918` after about `1664.23` horizontal / `1664.67` three-dimensional blocks over `1149` server ticks;
- `BASE` at `3034`, `FINAL` at `3118`, and `FLARE` at `3275`;
- bounded native flare extensions at `3496` and `3717`, at about `10.50` and `0.081` AGL, followed by normal ground contact;
- `TOUCHDOWN` at `3722`, `BRAKE` at `3732`, and `PARKED` at `3781`;
- final speed `0.0`, final reason `complete_stop_stable_for_40_ticks`;
- verifier passed with `3776` frames, Gradle status `0`, summary `1/1`, and zero crash reports.

No timeout, route geometry, waypoint radius, landing-pattern geometry, terrain, collision, stall, combat, weapon, player-control, or separation threshold changed.

## Remaining base-aircraft route qualifications

Energy fighters, in current execution order:

- `warfare_wings:f6f` (request committed; matching start record not yet observed);
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

Preflight and comparison evidence is preserved in:

- `docs/validation/2026-07-25/energy-fighter-route-preflight.md`;
- `docs/validation/2026-07-25/bomber-route-preflight.md`;
- `docs/validation/2026-07-25/route-qualification-signatures.md`.

## Repository state

- Parent roadmap: Issue #7 is the only open issue.
- No pull request was open at the start of this checkpoint.
- Latest completed route status is F4U Run `30151812704`, with build, GameTest, and artifact success.
- F6F request commit is `0c716db4d56a0f349f028adad350c471c5f81545`.
- F6F request uses immutable behavior ref `4092d096f17e7aac34e19696b8a63f62f96b6c53`.
- No matching F6F `in_progress` start record was present when this checkpoint was written; do not duplicate or rewrite the request during assignment delay.
- `ジョリー長航続モード` remains active.

## Preserved invariants

- player-controlled aircraft receive no AI input;
- terrain, collision, combat, and emergency control remain above route guidance;
- there is one final aircraft-input write;
- noncombat route orders do not grant weapon authority;
- fixed-gun, line-of-sight, range, friendly-fire, and minimum 8-block separation rules are unchanged;
- no return timeout, waypoint radius, landing geometry, or safety threshold was relaxed.

## Next exact action

1. Re-read `.github/local-route-validation-status.json`, `.github/local-route-validation-request.txt`, and recent commits.
2. If a new matching F6F start exists for request commit `0c716db4d56a0f349f028adad350c471c5f81545` and behavior ref `4092d096f17e7aac34e19696b8a63f62f96b6c53`, follow only that Run through build, exact-physics GameTest, verifier, artifact, and finish-status persistence.
3. Require route `3,2,1,0`, ordinary mission release, return, landing, final `PARKED`, summary 1/1, Gradle status 0, and no crash report.
4. If no matching start exists, do not retrigger or create a no-op commit; leave the existing request untouched and continue only with disconnected GitHub-side work.
5. On success, record artifact-backed evidence and continue serially with `warfare_wings:fw190`.
6. On failure, fetch logs and artifact once, identify the first meaningful acceptance failure, and create one focused Draft PR only when a code change is necessary. Do not weaken timeouts, geometry, radii, firing gates, or safety thresholds.
