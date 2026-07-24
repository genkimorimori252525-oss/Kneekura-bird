# AI development handoff

Last updated: 2026-07-25 (Asia/Tokyo)

Follow `/AGENTS.md` before changing code. Live GitHub state overrides older notes.

## Current state

PR #53 implements live owned-route guidance and passed exact real-physics validation. The validated behavior head is `c2bfd2a4c90827bdf1ceaed0e90351ff0ae5c6d7`; later PR commits only update this handoff document.

Windows self-hosted run `30106085402` passed:

- normal build and deterministic simulation;
- real-physics A6M `full` Forge GameTest;
- route assignment/start/completion evidence;
- ordered waypoint progression `3,2,1,0`;
- route proposal followed by terrain override in the same tick;
- no ordinary phase advancement during route ownership;
- no ground contact during route guidance;
- release to ordinary mission after route completion;
- return, landing, braking, and final `PARKED`;
- Gradle status 0, validation summary 1/1, 5,360 frames, no crash reports.

Key telemetry:

- route start: tick 771, `CRUISE_OUTBOUND`;
- waypoint advances: ticks 946, 1085, 1244, 1347;
- route completion: tick 1347, still `CRUISE_OUTBOUND`;
- ordinary mission release: tick 1587, `CRUISE_OUTBOUND -> TURN_LEFT`;
- final `PARKED`: tick 5366.

## Preserved invariants

- player-controlled aircraft receive no AI input;
- terrain, collision, combat, and emergency control remain above route guidance;
- there is still one final `ReflectiveAircraft.applyControl` write;
- noncombat route orders do not grant weapon authority;
- existing fixed-gun, line-of-sight, range, friendly-fire, and separation rules remain unchanged.

## Completed foundations

- reciprocal A6M/P-47N qualification;
- `ControlAuthorityArbiter`;
- measured-profile common noncombat flight;
- immutable mission orders and persistence;
- immutable waypoint routes, ownership, codecs, persistence, and reconciliation;
- pure waypoint planner;
- pure guidance-to-control conversion;
- owned-route proposal;
- live route integration in PR #53.

## Next exact action

After PR #53 merges, generalize the validated route execution across a small representative profile matrix: fighter, level bomber, attacker, and torpedo bomber. Keep it noncombat and preserve the same safety precedence before adding role-specific strike behavior.
