# AI development handoff

Last updated: 2026-07-25 (Asia/Tokyo)

Follow `/AGENTS.md` before changing code. Live GitHub state overrides older notes.

## Current production baseline

Production owned-route guidance remains below player-control, emergency, terrain, collision, and combat authority. No weapon or minimum-separation rule was relaxed.

Merged route milestones:

- PR #53: live owned-route guidance integrated into the single final aircraft-input path;
- PR #58: G4M legacy metadata recovery and `torpedo_bomber` common-flight admission;
- PR #59: IL-2 attacker representative route proof;
- PR #60: B-17 level-bomber compact route proof;
- PR #63: dedicated Windows self-hosted generic `route` validation workflow;
- PR #64: profile-driven compact route geometry and arbitrary-aircraft strict evidence, merged as `a91c610b970721e3508dca4c1460e75b262ec3d0`.

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

Each completed generic qualification required ordered waypoint progression `3,2,1,0`, no ground contact during route ownership, release to the ordinary mission, return, landing, braking, final `PARKED`, passed summary, Gradle status 0, and no crash reports.

B-29 specifically performed a safe go-around before the successful final landing.

## Current infrastructure exception

Ju 87 generic route Run `30121385930` checked out exact behavior SHA `a91c610b970721e3508dca4c1460e75b262ec3d0` on Windows runner `ジョリー`.

Observed workflow result:

- build and deterministic simulation: success;
- exact-physics route scenario and strict GameTest evidence: success;
- artifact upload: failure;
- automatic finish-status write: failure;
- final job conclusion: failure only because the two GitHub post-processing steps failed.

No diagnostics artifact was created, so Ju 87 must not yet be counted as fully qualified even though the strict route scenario itself passed. Do not retune aircraft control from this run. `.github/local-route-validation-status.json` was manually corrected to record `conclusion=infrastructure_failure` and both successful behavior outcomes.

## Repository state

- Parent roadmap: Issue #7 remains the only open issue.
- No behavior PR is currently open.
- Obsolete Draft PR #61 was closed as superseded by merged PR #64.
- Windows self-hosted runner was online and executed Run `30121385930`.
- Current main includes status checkpoint commit `d7c6395c1422306acc12b08b5418462138e0039e` or a later metadata/documentation commit.

## Preserved invariants

- player-controlled aircraft receive no AI input;
- terrain, collision, combat, and emergency control remain above route guidance;
- there is one final aircraft-input write;
- noncombat route orders do not grant weapon authority;
- fixed-gun, line-of-sight, range, friendly-fire, and minimum 8-block separation rules are unchanged;
- no return timeout or safety threshold was relaxed.

## Next exact action

1. Do not issue another Ju 87 behavior run immediately.
2. Inspect the failed `Upload route diagnostics` and `Persist route validation finish` steps from Run `30121385930`; treat them as infrastructure/network/storage failures unless logs prove otherwise.
3. Make one focused workflow-only fix if a deterministic root cause is found. Do not change aircraft geometry or control thresholds.
4. After the post-processing path is healthy, re-run Ju 87 once on exact production behavior SHA and require artifact-backed `PARKED` plus crash-report inspection.
5. Continue the 24-aircraft route matrix with an unqualified base aircraft selected to broaden role/physics coverage. Keep each request exact-SHA and sequential on the self-hosted runner.
