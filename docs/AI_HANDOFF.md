# AI development handoff

Last updated: 2026-07-25 (Asia/Tokyo)

Follow `/AGENTS.md` before changing code. Live GitHub state overrides older notes.

## Current production baseline

Production owned-route guidance remains below player-control, emergency, terrain, collision, and combat authority. No weapon, timeout, waypoint-radius, or minimum-separation rule was relaxed.

Merged route milestones:

- PR #53: live owned-route guidance integrated into the single final aircraft-input path;
- PR #58: G4M legacy metadata recovery and `torpedo_bomber` common-flight admission;
- PR #59: IL-2 attacker representative route proof;
- PR #60: B-17 level-bomber compact route proof;
- PR #63: dedicated Windows self-hosted generic `route` validation workflow;
- PR #64: profile-driven compact route geometry and arbitrary-aircraft strict evidence, merged as `a91c610b970721e3508dca4c1460e75b262ec3d0`;
- PR #65: route-workflow post-processing hardening, merged as `9ee8e899c74a49cf20313e5eb6f18eabe14bffb6`.

The generic route plan derives four waypoints from measured `FlightProfile` role, cruise speed, live position, and live heading. Supported roles are fighter, bomber, attacker, and torpedo bomber. Unknown roles and malformed geometry inputs are rejected deterministically.

## Exact-physics qualification evidence

Fully qualified with artifacts and terminal `PARKED`:

- A6M terrain-precedence proof — Run `30106085402`;
- G4M compact torpedo-bomber route — Run `30113770224`;
- IL-2 compact attacker route — Run `30115029120`;
- B-17 compact level-bomber route — Run `30115815404`;
- P-51D generic profile-driven route — Run `30118532513`;
- Spitfire generic turn-fighter route — Run `30120064170`;
- B-29 generic bomber route — Run `30120521495`.

Each completed generic qualification required ordered waypoint progression `3,2,1,0`, no ground contact during route ownership, release to the ordinary mission, return, landing, braking, final `PARKED`, passed summary, Gradle status 0, and no crash reports. B-29 performed a safe go-around before its successful final landing.

## Ju 87 investigation

### Post-processing incident

Run `30121385930` checked out exact production behavior SHA `a91c610b970721e3508dca4c1460e75b262ec3d0`. Build, deterministic simulation, and strict route GameTest passed, but artifact upload and finish-status persistence failed. PR #65 fixed only that workflow post-processing path.

### Artifact-backed production-behavior failure

Retry Run `30122172937` used the same production behavior SHA and produced diagnostics. The route completed in ordered `3,2,1,0`, released to the ordinary mission, then ended `ABORTED:return_to_pattern_timeout`.

Telemetry proved direct guidance rather than steering failure:

- RETURN_TO_PATTERN started about 1,567 blocks from downwind entry;
- the aircraft continuously reduced that distance to about 275 blocks;
- unchanged acceptance requires under 30 blocks within 1,800 ticks;
- Ju 87 profile: climb target about 15.69 BPS, turn floor about 18.75 BPS, measured top speed about 22.27 BPS.

### Insufficient clock-accounting hypothesis

Draft PR #66 (`73f396048d14b3dc3612259169c9d0c8ad874d7b`) counted owned-route outbound travel toward the ordinary 240-tick cruise sample without increasing any timeout.

Exact-head Run `30123421732` passed build and deterministic clock-policy tests. The route completed at tick 3971 and ordinary `CRUISE_OUTBOUND -> TURN_LEFT` occurred at tick 3973 instead of 240 ticks later. RETURN_TO_PATTERN therefore began about 236 ticks earlier and about 1,371 blocks from downwind entry, but still ended about 78 blocks away and failed the unchanged 30-block acceptance. PR #66 was closed as insufficient and not merged.

### Current single hypothesis

Draft PR #67 (`7315a4062cc52a2667a370341e22f0b48f15aedb`) starts cleanly from current `main` and changes only landing-pattern rejoin target speed:

- preserve the existing approach-speed margin and climb target;
- require RETURN_TO_PATTERN target speed to be at least measured `turnSpeedFloorBps`;
- apply through a require=1 mixin only to the long rejoin waypoint-control call;
- leave downwind, base, final, flare, touchdown, braking, route geometry, timeouts, and safety authority unchanged;
- add deterministic profile-policy GameTests.

Exact-head Windows Run `30124721947` is active for Ju 87 `route`. Request resolution and checkout succeeded. At this checkpoint it remained in `Set up Gradle 8.8`; no build or targeted-scenario result was available yet. Do not trigger another run while it is active.

## Repository state

- Parent roadmap: Issue #7 remains open.
- Draft behavior PR #67 is the only current Ju 87 hypothesis.
- Draft PR #66 is closed and preserved as failed-hypothesis evidence.
- Windows self-hosted runner `ジョリー` accepted Run `30124721947`.
- Current `main` includes the PR #67 validation request/status metadata or later documentation metadata.

## Preserved invariants

- player-controlled aircraft receive no AI input;
- terrain, collision, combat, and emergency control remain above route guidance;
- there is one final aircraft-input write;
- noncombat route orders do not grant weapon authority;
- fixed-gun, line-of-sight, range, friendly-fire, and minimum 8-block separation rules are unchanged;
- no return timeout, waypoint radius, landing geometry, or safety threshold was relaxed.

## Next exact action

1. Read `.github/local-route-validation-status.json` and Run `30124721947` before any new request.
2. If the run fails, fetch the artifact immediately and identify the first meaningful failure; do not retry or adjust thresholds without a materially different design.
3. If the run succeeds, verify the applied RETURN_TO_PATTERN target speed, ordered route evidence, downwind/base/final transitions, final `PARKED`, summary 1/1, Gradle status 0, and no crash report.
4. Rebuild the exact validated PR #67 blobs from the latest `main` if metadata drift makes the branch stale, then mark ready and squash merge.
5. After Ju 87 is fully qualified, continue the 24-aircraft route matrix with an unqualified aircraft selected to broaden physics coverage.
