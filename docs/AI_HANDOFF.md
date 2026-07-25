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
- PR #65: route-workflow post-processing hardening, merged as `9ee8e899c74a49cf20313e5eb6f18eabe14bffb6`;
- PR #73: disconnected `PatternRejoinBudget` feasibility foundation, merged as `c55b764b833b8fb70a995c3dcc57246cd3fb7e61`;
- PR #70: owned-route clock accounting plus measured pattern-rejoin speed, squash-merged as `dd2dc9c7e9d3042b3dd4a0511a7ea5da935e5860` after exact-head Windows validation.

The generic route plan derives four waypoints from measured `FlightProfile` role, cruise speed, live position, and live heading. Supported roles are fighter, bomber, attacker, and torpedo bomber. Unknown roles and malformed geometry inputs are rejected deterministically.

`MissionRouteClockPolicy` allows owned `CRUISE_OUTBOUND` travel to satisfy the fixed 240-tick sample while the overall mission timeout remains frozen. `PatternRejoinSpeedPolicy` commands at least the measured `turnSpeedFloorBps` only during `RETURN_TO_PATTERN`. `PatternRejoinBudget` remains disconnected from live control and reports ideal reach, required speed, block margin, and margin ratio.

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
- SBD generic attacker route — Run `30148395384`.

Each completed generic qualification required ordered waypoint progression `3,2,1,0`, release to the ordinary mission, return, landing, braking, final `PARKED`, passed summary, Gradle status 0, and no crash reports. B-29 performed a safe go-around before its successful final landing. Ju 87 and SBD each used two bounded native flare extensions below 20 blocks before normal touchdown.

## Ju 87 resolution

Earlier production Run `30122172937` completed the route but timed out during `RETURN_TO_PATTERN`. Isolated Runs `30123421732` and `30124721947` proved two independent contributors:

- owned outbound route travel was not credited toward the fixed 240-tick outbound sample;
- long pattern rejoin commanded the lower climb target instead of the measured turn-speed floor.

PR #70 combined only those two established effects. Exact behavior head `361078f30f1dd348fa274050f89cdf413525d49e` passed Windows Run `30147903349`:

- build and deterministic simulation succeeded;
- route advanced `3 -> 2 -> 1 -> 0`;
- route completed at server tick `3969` and ordinary `CRUISE_OUTBOUND -> TURN_LEFT` followed at tick `3971`;
- `RETURN_TO_PATTERN` commanded `18.75373230144395 BPS` and reached `DOWNWIND` inside the unchanged 1,800-tick timeout;
- landing progressed through `DOWNWIND -> BASE -> FINAL -> FLARE -> TOUCHDOWN -> BRAKE -> PARKED`;
- final reason was `complete_stop_stable_for_40_ticks`;
- verifier passed with Gradle status 0, summary 1/1, and zero crash reports.

SBD then qualified without further behavior changes on Run `30148395384`:

- route advanced `3 -> 2 -> 1 -> 0` and completed at server tick `3804`;
- ordinary `CRUISE_OUTBOUND -> TURN_LEFT` followed at tick `3806`;
- return and landing progressed through `RETURN_TO_PATTERN -> DOWNWIND -> BASE -> FINAL -> FLARE -> TOUCHDOWN -> BRAKE -> PARKED`;
- final reason was `complete_stop_stable_for_40_ticks`, elapsed `4789` ticks;
- verifier passed with Gradle status 0, summary 1/1, and zero crash reports.

No timeout, route geometry, waypoint radius, landing-pattern geometry, terrain, collision, stall, combat, weapon, player-control, or separation threshold changed.

## Repository state

- Parent roadmap: Issue #7 is the only open issue.
- PR #70 is merged as `dd2dc9c7e9d3042b3dd4a0511a7ea5da935e5860`.
- No behavior pull request is currently open.
- Latest completed route status is SBD Run `30148395384`: build success, GameTest success, artifact success.
- Diagnostic artifact: `ww-local-route-30148395384`.
- The Windows self-hosted runner is online and completed two consecutive exact-head requests successfully.

## Preserved invariants

- player-controlled aircraft receive no AI input;
- terrain, collision, combat, and emergency control remain above route guidance;
- there is one final aircraft-input write;
- noncombat route orders do not grant weapon authority;
- fixed-gun, line-of-sight, range, friendly-fire, and minimum 8-block separation rules are unchanged;
- no return timeout, waypoint radius, landing geometry, or safety threshold was relaxed.

## Next exact action

1. Qualify `warfare_wings:d4y` on the latest `main` using scenario `route`, without behavior changes.
2. Require build success, deterministic contracts, route `3,2,1,0`, ordinary mission release, return, landing, final `PARKED`, summary 1/1, Gradle status 0, and no crash report.
3. If D4Y fails, fetch its logs and artifact once, identify the first meaningful acceptance failure, and open one focused draft PR only if a code change is necessary. Do not change timeouts, geometry, radii, or safety thresholds blindly.
4. If D4Y passes, the four attacker aircraft Ju 87, SBD, IL-2, and D4Y all have exact-physics generic-route evidence. Enumerate the remaining unqualified base aircraft by role and continue the same no-change-first qualification sequence.
