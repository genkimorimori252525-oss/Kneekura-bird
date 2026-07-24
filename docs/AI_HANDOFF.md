# AI development handoff

Last updated: 2026-07-25 (Asia/Tokyo)

## Read first

Follow `/AGENTS.md` before changing code. Live GitHub state, merged commits, open PRs, and terminal workflow results override older notes in this file.

## Current production baseline

- Current `main` before PR #53 behavior merge: validation request/status commits after `85b0b7b4496a60d8a41633016487c1364409436f`.
- Reciprocal A6M/P-47N combat qualification and `ControlAuthorityArbiter` are complete. Do not reimplement them.
- Measured-profile common noncombat flight is enabled for fighters, level bombers, attackers, and G4M without granting non-fighters fighter weapon authority.
- Immutable mission orders, mission persistence, immutable waypoint routes, route ownership, strict route NBT, route persistence, startup reconciliation, pure waypoint planning, pure control conversion, and owned-route proposal are merged.
- Strike, dive-bomb, ground-attack, torpedo, fuel, damage, ammunition, and multi-formation mission execution remain unfinished.

## PR #53 — live owned-route integration

Branch: `agent/live-owned-route-guidance`

Validated exact behavior head: `c2bfd2a4c90827bdf1ceaed0e90351ff0ae5c6d7`

Windows self-hosted run: `30106085402`

### Implemented behavior

- The ordinary `AutopilotSession.tick(...)` output remains the base proposal.
- `MissionRouteGuidanceAdapter.plan(...)` replaces that proposal only while an owned route is active.
- Route proposal insertion occurs before the existing terrain planner, native-flight adaptation, combat overrides, and the single final `ReflectiveAircraft.applyControl` write.
- The fixed demonstration mission's `phaseTicks` and `missionTicks` are held only while a valid owned route controls an eligible cruise/turn phase.
- Safety transitions run before the clock hold and release route ownership by entering a non-route-eligible phase.
- Session cleanup clears route logging and test-only setup state.

### Exact real-physics proof

The A6M-only `full` validation assigns a noncombat `HOLD_POSITION` mission with four ordered waypoints at longitudinal offsets 1100, 1280, 1440, and 1580 blocks. A floating obstacle is placed at 970 blocks so terrain avoidance must override route guidance after route ownership begins.

Forge GameTest requires telemetry proving:

- exactly one route assignment, route start, and route completion;
- waypoint remaining counts exactly `3, 2, 1, 0`;
- live route controls applied;
- terrain avoidance overwrote the route proposal later in the same tick;
- the ordinary mission phase did not advance while route ownership was active;
- no ground contact during route guidance;
- completion released the aircraft to the ordinary mission;
- the full mission ended inside the runway corridor at `PARKED`.

### Validation result

Run `30106085402` checked out exact head `c2bfd2a4c90827bdf1ceaed0e90351ff0ae5c6d7`.

- normal build and deterministic simulation: passed;
- exact runtime aircraft preparation: passed;
- real-physics A6M `full` Forge GameTest: passed;
- scenario verification: passed, Gradle status 0;
- crash reports: none;
- validation summary: 1/1 passed;
- telemetry frames: 5,360;
- route guidance start: tick 771, `CRUISE_OUTBOUND`;
- waypoint progression: ticks 946, 1085, 1244, 1347 with remaining `3,2,1,0`;
- route/terrain precedence: tick 771 route proposal logged before predictive terrain override in the same tick;
- route completion: tick 1347, still `CRUISE_OUTBOUND`;
- ordinary mission release: tick 1587, `CRUISE_OUTBOUND -> TURN_LEFT`;
- final state: tick 5366, `PARKED`;
- session cleanup completed normally.

The earlier run `30105432787` failed only because the verifier treated a phase transition logged earlier in the same tick as occurring after route ownership began. Commit `c2bfd2a4c90827bdf1ceaed0e90351ff0ae5c6d7` corrected the test-only boundary to use JSONL event ordering; production flight behavior was unchanged.

## Prior validated guidance stack

- PR #48 pure waypoint planner: merged as `db81a6e5beaea61c8c768302fa1aeb26881c6edf`; run `30099518522` passed.
- PR #50 pure control conversion: merged as `172c47dadfbda218a47b5f88b18b99e47d860261`; run `30100564075` passed.
- PR #51 owned mission-route proposal: merged as `b4b8bb30fe701be8f9f19683b2e8226a70a6cc43`; run `30101541976` passed.

## Validation routing lesson

- `.github/local-validation-request.txt` is the reciprocal-dogfight-only gate.
- `.github/local-flight-validation-request.txt` is the selectable aircraft/scenario gate.
- Use the selectable gate for mission, route, persistence, and ordinary flight work.

## Runner Hub

The desktop Jolly Runner Hub has six selectable live charts, dynamic aircraft discovery, persistent per-run history, an 8-block safety line, responsive layout, vertical scrolling, and startup smoke testing. This UI work is complete enough for continued AI validation.

## Preserved safety invariants

Never weaken these to make a validation pass:

- player-controlled aircraft receive no AI input;
- terrain and collision avoidance remain above ordinary route guidance;
- combat and defensive emergency authority remain above ordinary navigation;
- fixed forward guns never fire behind the aircraft;
- line-of-sight, range, friendly-fire, and weapon-specific gates remain authoritative;
- reciprocal-dogfight separation acceptance remains at least 8 blocks;
- non-fighters do not inherit fighter targeting or fixed-gun authority;
- a route or mission without explicit attack authority does not enable weapons.

## Next exact action after PR #53 merge

Generalize the validated live route execution across measured aircraft profiles with a small matrix of representative fighter, bomber, attacker, and torpedo-bomber profiles. Keep the same noncombat route authority and safety precedence before beginning role-specific strike policies.
