# AI development handoff

Last updated: 2026-07-25 (Asia/Tokyo)

Follow `/AGENTS.md` before changing code. Live GitHub state overrides older notes.

## Current production baseline

Production owned-route guidance remains below player-control, emergency, terrain, collision, and combat authority. No weapon, timeout, waypoint-radius, landing-geometry, or minimum-separation rule has been relaxed.

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

Fully qualified with terminal `PARKED`:

- A6M terrain-precedence proof — Run `30106085402`;
- G4M compact torpedo-bomber route — Run `30113770224`;
- IL-2 compact attacker route — Run `30115029120`;
- B-17 compact level-bomber route — Run `30115815404`;
- P-51D generic profile-driven route — Run `30118532513`;
- Spitfire generic turn-fighter route — Run `30120064170`;
- B-29 generic bomber route — Run `30120521495`.

Each completed generic qualification required ordered waypoint progression `3,2,1,0`, no ground contact during route ownership, release to the ordinary mission, return, landing, braking, final `PARKED`, passed summary, Gradle status 0, and no crash reports. B-29 performed a safe go-around before its successful final landing.

## Ju 87 investigation

### Established evidence

Run `30122172937` used production route behavior and completed the ordered route, but ended `ABORTED:return_to_pattern_timeout`. RETURN_TO_PATTERN began about 1,567 blocks from downwind entry and ended about 275 blocks away under the unchanged 1,800-tick budget.

Ju 87 measured profile values relevant to the investigation:

- climb target: about 15.69 BPS;
- turn-speed floor: about 18.75 BPS;
- measured top speed: about 22.27 BPS.

### Isolated hypotheses

PR #66 / Run `30123421732` proved that owned outbound route travel was not credited toward the ordinary 240-tick outbound sample. Its clock policy reduced rejoin start distance to about 1,371 blocks and ended about 78 blocks from downwind entry. It was insufficient alone and was closed without merge.

PR #67 / Run `30124721947` proved that RETURN_TO_PATTERN could command the measured turn-speed floor, raising the target from about 15.69 BPS to about 18.75 BPS. Because that branch did not include PR #66's clock correction, rejoin again began about 1,567 blocks away and ended about 152 blocks short. It was insufficient alone and was closed without merge.

### Current focused hypothesis — Draft PR #70

Draft PR #70 combines only the two previously observed effects on a clean branch:

- `MissionRouteClockPolicy` credits owned `CRUISE_OUTBOUND` travel toward the fixed 240-tick sample while freezing the overall mission timeout;
- `PatternRejoinSpeedPolicy` commands at least measured `turnSpeedFloorBps` only during RETURN_TO_PATTERN;
- both mixin injection points use `require = 1`;
- no timeout, route geometry, waypoint radius, landing-pattern geometry, terrain, collision, stall, combat, weapon, player-control, or separation threshold changes.

Exact behavior head:

`bdce17573f0da5e1b90bf5566115013ec4d2734c`

The validation request is present on `main` in `.github/local-route-validation-request.txt`, committed as `62607f75c95685dc98ab69f16af041225ab12f14`:

- aircraft: `warfare_wings:ju87`;
- scenario: `route`;
- exact ref: PR #70 behavior head above.

At this checkpoint no new route-validation start commit, status update, check, or Run ID exists after the request. The previous status file still records completed failed Run `30124721947`. Treat the Windows self-hosted runner as unavailable or not assigned for this request. Do not edit the request file, retrigger, or create a no-op commit while this remains true.

## Repository state

- Parent roadmap: Issue #7 is the only open issue.
- Draft PR #70 is the only open pull request.
- Current request commit: `62607f75c95685dc98ab69f16af041225ab12f14`.
- Current pending behavior head: `bdce17573f0da5e1b90bf5566115013ec4d2734c`.
- Latest completed route status remains Run `30124721947`: build success, GameTest failure, artifact success.
- No new Windows run has accepted the PR #70 request yet.

## Preserved invariants

- player-controlled aircraft receive no AI input;
- terrain, collision, combat, and emergency control remain above route guidance;
- there is one final aircraft-input write;
- noncombat route orders do not grant weapon authority;
- fixed-gun, line-of-sight, range, friendly-fire, and minimum 8-block separation rules are unchanged;
- no return timeout, waypoint radius, landing geometry, or safety threshold was relaxed.

## Next exact action

1. Read `.github/local-route-validation-status.json` and recent commits before touching the request.
2. If a new Run ID appears for exact head `bdce17573f0da5e1b90bf5566115013ec4d2734c`, inspect that run once and do not duplicate it.
3. If no Run ID exists and the runner remains unavailable, perform only GitHub-side review, deterministic-test inspection, or documentation work; do not retrigger.
4. If the run succeeds, verify both deterministic policy batches, route `3,2,1,0`, immediate ordinary mission release, RETURN_TO_PATTERN target near 18.7537 BPS, downwind/base/final transitions, landing, final `PARKED`, summary 1/1, Gradle status 0, and no crash report.
5. If the run fails, fetch logs and artifact once, identify the first meaningful acceptance failure, and record one materially different next hypothesis without changing thresholds blindly.
6. Only after exact-head success, rebuild the validated blobs from the latest `main` if metadata drift makes PR #70 stale, then mark ready and squash merge.
