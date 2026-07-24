# AI development handoff

Last updated: 2026-07-24 (Asia/Tokyo)

## Read first

Follow `/AGENTS.md` before changing code. Live GitHub state, merged commits, open PRs, and terminal workflow results override older notes in this file.

## Current production baseline

- Current `main`: `b4b8bb30fe701be8f9f19683b2e8226a70a6cc43`.
- Reciprocal A6M/P-47N combat qualification and `ControlAuthorityArbiter` are complete. Do not reimplement them.
- Measured-profile common noncombat flight is enabled for fighters, level bombers, attackers, and G4M without granting non-fighters fighter weapon authority.
- Immutable mission orders, mission persistence, immutable waypoint routes, route ownership, strict route NBT, route persistence, and startup reconciliation are merged.
- Strike, dive-bomb, ground-attack, torpedo, fuel, damage, ammunition, and multi-formation mission execution remain unfinished.

## Guidance stack now merged

### PR #48 — pure waypoint planner

Merged as `db81a6e5beaea61c8c768302fa1aeb26881c6edf`.

- advances at most one reached waypoint per call;
- returns normalized horizontal direction, waypoint altitude, measured-profile target speed, horizontal distance, and vertical error;
- preserves aircraft heading for vertically aligned waypoints;
- completed routes expose no live target;
- no aircraft input or authority access.

Windows self-hosted run `30099518522` on exact head `b1725bb7a3ae32ec33c27f81f33065a1715906d7`:

- normal build passed;
- deterministic simulation passed;
- all 15 required GameTests passed;
- A6M real-physics `full` passed 1/1 and produced 4,326 frames through `PARKED`;
- crash reports none.

### PR #50 — pure control conversion

Merged as `172c47dadfbda218a47b5f88b18b99e47d860261`.

- converts a guidance target into `FlightControlOutput`;
- reuses the established heading, altitude, vertical-speed damping, steering-clamp, and cruise-throttle envelope;
- preserves stall and terrain-risk signals for later safety layers;
- never calls `ReflectiveAircraft.applyControl` or requests authority.

Windows self-hosted run `30100564075` on exact head `e0626f2575d79ae4499ef29d3e1dbe1b47ee5ed5`:

- build and deterministic simulation passed;
- all 17 required GameTests passed;
- A6M real-physics `full` passed 1/1 with 4,326 frames;
- crash reports none.

### PR #51 — owned mission-route proposal

Merged as `b4b8bb30fe701be8f9f19683b2e8226a70a6cc43`.

- requires aircraft UUID, mission revision, and immutable order ID to match the route assignment;
- permits route proposals only during `CRUISE_OUTBOUND`, `TURN_LEFT`, `CRUISE_CROSS`, and `TURN_RIGHT`;
- advances route progress through `MissionRouteManager` at most once per call;
- rejects ownership changes during planning;
- releases completed routes back to the existing base-autonomy output;
- still performs no aircraft input write.

Windows self-hosted run `30101541976` on exact head `1ded7e3729edf34f4619712c723e3e27a13540a3`:

- build and deterministic simulation passed;
- all 20 required GameTests passed;
- A6M real-physics `full` passed 1/1 with 4,326 frames;
- crash reports none.

## Validation routing lesson

There are two distinct self-hosted request files:

- `.github/local-validation-request.txt` is the reciprocal-dogfight-only gate;
- `.github/local-flight-validation-request.txt` is the selectable aircraft/scenario gate.

A noncombat PR was briefly sent through the dogfight-only gate. Its unrelated dogfight sample reached 4.96 blocks, while the immediate current-main control run `30098543878` passed with minimum separation 10.85 blocks. The guidance PRs were therefore revalidated through the correct selectable `scenario=full` workflow before merge. Do not use the dogfight-only request file for ordinary mission, route, persistence, or UI changes.

## Runner Hub

The desktop Jolly Runner Hub now has:

- six selectable live charts;
- dynamic aircraft discovery;
- persistent per-run history;
- safety-line display for 8-block separation;
- responsive layout and vertical scrolling;
- Windows PowerShell startup smoke testing before deployment.

This UI work is complete enough for continued AI validation.

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

## Next exact implementation

Create a new branch from current `main` for one live-integration hypothesis:

1. In `AutonomousFlightManager.applyControl`, keep `entry.session.tick(...)` as the base proposal.
2. Capture the `FlightSnapshot` as today.
3. Call `MissionRouteGuidanceAdapter.plan(...)` after the base proposal and before `TerrainAvoidancePlanner.plan(...)`.
4. Replace `missionPlanned` only when `Decision.routeActive()` is true.
5. Log route selection, waypoint advancement, completion, and release through `AutopilotLogManager.writeControlAdapter` or a focused route event.
6. Leave terrain avoidance, native-flight adaptation, the single final `ReflectiveAircraft.applyControl`, combat overrides, and player exclusion unchanged.
7. Enable only one noncombat proof order, preferably `HOLD_POSITION`, in test-only setup.
8. Add a targeted real-physics scenario proving: takeoff, route ownership, multiple ordered waypoints, no skipped waypoint, terrain precedence, route completion, release to ordinary mission, return, landing, and `PARKED`.
9. Do not add weapons, strike behavior, fuel, damage, formation policy, or role-specific attack logic in the same PR.

After that live proof passes, generalize common route execution across the 24 measured profiles before beginning role-specific strike policies.

## Useful references

- parent roadmap: Issue #7;
- fighter qualification: PR #17;
- shared authority: PR #18;
- mission-order foundation/persistence: PR #27 and PR #30;
- route model/ownership/codec/persistence: PR #33, #35, #37, and #40;
- pure guidance stack: PR #48, #50, and #51;
- latest selectable flight validations: runs `30099518522`, `30100564075`, and `30101541976`.
