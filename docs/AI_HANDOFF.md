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
- SBD generic attacker route — Run `30148395384`;
- D4Y generic attacker route — Run `30148766789`.

Current coverage is 10 of 24 base aircraft. All four attackers — Ju 87, SBD, IL-2, and D4Y — now have exact-physics generic-route evidence.

Each completed qualification required ordered waypoint progression `3,2,1,0`, release to the ordinary mission, return, landing, braking, final `PARKED`, passed summary, Gradle status 0, and no crash reports. B-29 performed a safe go-around before its successful final landing. Ju 87, SBD, and D4Y each used two bounded native flare extensions below 20 blocks before normal touchdown.

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

No timeout, route geometry, waypoint radius, landing-pattern geometry, terrain, collision, stall, combat, weapon, player-control, or separation threshold changed.

## Remaining base-aircraft route qualifications

Unqualified fighters:

- turn fighter: `warfare_wings:yak3`;
- energy fighters: `warfare_wings:bf109`, `warfare_wings:f4u`, `warfare_wings:f6f`, `warfare_wings:fw190`, `warfare_wings:ki61`, `warfare_wings:ki84`, `warfare_wings:mc202`, `warfare_wings:mig3`, `warfare_wings:p40e`, `warfare_wings:p47n`.

Unqualified bombers:

- `warfare_wings:g10n1`;
- `warfare_wings:g10n2`;
- `warfare_wings:he111`.

## Repository state

- Parent roadmap: Issue #7 is the only open issue.
- PR #70 is merged as `dd2dc9c7e9d3042b3dd4a0511a7ea5da935e5860`.
- No behavior pull request is currently open.
- Latest completed route status is D4Y Run `30148766789`: build success, GameTest success, artifact success.
- Diagnostic artifact: `ww-local-route-30148766789`.
- Three consecutive exact-head requests completed successfully in this session: Ju 87, SBD, and D4Y.

## Preserved invariants

- player-controlled aircraft receive no AI input;
- terrain, collision, combat, and emergency control remain above route guidance;
- there is one final aircraft-input write;
- noncombat route orders do not grant weapon authority;
- fixed-gun, line-of-sight, range, friendly-fire, and minimum 8-block separation rules are unchanged;
- no return timeout, waypoint radius, landing geometry, or safety threshold was relaxed.

## Next exact action

1. Pause new remote runs at this checkpoint; three exact-physics runs and one behavior merge completed successfully.
2. On resume, qualify `warfare_wings:yak3` on the then-current `main` using scenario `route`, without behavior changes.
3. Require build success, deterministic contracts, route `3,2,1,0`, ordinary mission release, return, landing, final `PARKED`, summary 1/1, Gradle status 0, and no crash report.
4. If Yak-3 passes, all three turn fighters A6M, Spitfire, and Yak-3 have route evidence. Continue with energy fighters one exact-head request at a time, beginning with `warfare_wings:bf109`.
5. If any aircraft fails, fetch its logs and artifact once, identify the first meaningful acceptance failure, and open one focused draft PR only if a code change is necessary. Do not change timeouts, geometry, radii, or safety thresholds blindly.
