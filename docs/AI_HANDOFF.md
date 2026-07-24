# AI development handoff

Last updated: 2026-07-25 (Asia/Tokyo)

## Read first

Follow `/AGENTS.md` before changing code. Live GitHub state, merged commits, open PRs, and terminal workflow results override older notes in this file.

## Current production baseline

- Current `main` before PR #53 behavior merge: `85b0b7b4496a60d8a41633016487c1364409436f` plus validation request/status commits.
- Reciprocal A6M/P-47N combat qualification and `ControlAuthorityArbiter` are complete. Do not reimplement them.
- Measured-profile common noncombat flight is enabled for fighters, level bombers, attackers, and G4M without granting non-fighters fighter weapon authority.
- Immutable mission orders, mission persistence, immutable waypoint routes, route ownership, strict route NBT, route persistence, startup reconciliation, pure waypoint planning, pure control conversion, and owned-route proposal are merged.
- Strike, dive-bomb, ground-attack, torpedo, fuel, damage, ammunition, and multi-formation mission execution remain unfinished.

## Active PR #53 — live owned-route integration

Branch: `agent/live-owned-route-guidance`

Validated exact head currently running: `0ab6ce1c7e807a98cbc58a7c525c815ad6d932ab`

Windows self-hosted run: `30105432787`

### Implemented hypothesis

- The ordinary `AutopilotSession.tick(...)` output remains the base proposal.
- `MissionRouteGuidanceAdapter.plan(...)` may replace that proposal only while an owned route is active.
- Route proposal insertion occurs before the existing terrain planner, native-flight adaptation, combat overrides, and the single final `ReflectiveAircraft.applyControl` write.
- The fixed demonstration mission's `phaseTicks` and `missionTicks` are held only while a valid owned route controls an eligible cruise/turn phase.
- Safety transitions are evaluated before the clock hold and release route ownership by entering a non-route-eligible phase.
- Session cleanup clears route logging and test-only setup state.

### Exact real-physics proof

The A6M-only `full` validation assigns a noncombat `HOLD_POSITION` mission with four ordered waypoints at longitudinal offsets 1100, 1280, 1440, and 1580 blocks. A floating obstacle is placed at 970 blocks so terrain avoidance must override route guidance after route ownership begins.

The Forge GameTest now fails unless telemetry proves all of the following:

- exactly one route assignment, route start, and route completion;
- waypoint remaining counts are exactly `3, 2, 1, 0`;
- live route controls were applied;
- terrain avoidance overwrote the route proposal later in the same tick;
- the ordinary mission phase did not advance while route ownership was active;
- no ground contact occurred during route guidance;
- completion released the aircraft to the ordinary mission;
- the existing full-flight contract still ends inside the runway corridor at `PARKED`.

### Current validation state

Run `30105432787` checked out exact head `0ab6ce1c7e807a98cbc58a7c525c815ad6d932ab`.

- request parsing and exact checkout: passed;
- Java/Gradle setup: passed;
- normal build and deterministic simulation: passed;
- exact runtime aircraft download: passed;
- real-physics A6M `full` GameTest: in progress at this checkpoint.

Do not merge PR #53 until the terminal run and artifact evidence are inspected. If the run fails, analyze this run before changing code or issuing another request.

## Prior validated guidance stack

### PR #48 — pure waypoint planner

Merged as `db81a6e5beaea61c8c768302fa1aeb26881c6edf`.

Windows self-hosted run `30099518522` passed build, deterministic simulation, all required GameTests, and A6M `full` through `PARKED`.

### PR #50 — pure control conversion

Merged as `172c47dadfbda218a47b5f88b18b99e47d860261`.

Windows self-hosted run `30100564075` passed build, deterministic simulation, all required GameTests, and A6M `full` through `PARKED`.

### PR #51 — owned mission-route proposal

Merged as `b4b8bb30fe701be8f9f19683b2e8226a70a6cc43`.

Windows self-hosted run `30101541976` passed build, deterministic simulation, all required GameTests, and A6M `full` through `PARKED`.

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

## Next exact action

1. Read terminal state and jobs for run `30105432787`.
2. On failure, fetch its logs/artifacts and report the exact failed evidence condition before editing.
3. On success, inspect the route telemetry artifact, mark PR #53 ready, squash-merge it, update this handoff on `main`, and checkpoint Issue #7.
4. After merge, generalize common route execution across measured profiles before beginning role-specific strike policies.
