# AI development handoff

Last updated: 2026-07-24 (Asia/Tokyo)

## Read first

Follow `/AGENTS.md` before changing code. Hard limits are 60 minutes, 8 remote CI attempts, 10 changed files, and 800 added/changed lines, with a mandatory checkpoint at 30 minutes or 4 CI attempts.

Current GitHub state, merged commits, open PRs, and terminal workflow results override older notes in this file.

## Current production baseline

- Current `main`: `e90b4b43d52e19be55d4ad40bfcdddfe62d9ead1`.
- PR #21 enabled measured-profile noncombat autonomous flight for level bombers.
- PR #25 enabled the same common noncombat flight path for measured attacker profiles.
- PR #27 merged the immutable `MissionOrder` model, all 11 roadmap order types, and the UUID/revision-guarded `MissionOrderManager`.
- PR #30 merged mission-order persistence across server save/load.
- `ControlAuthorityArbiter` is already integrated. Do not create a second authority dispatcher.
- Reciprocal A6M/P-47N combat qualification is complete. Do not retune it unless a later change produces a measured regression.
- Fighter targeting, defensive manoeuvre, re-engagement, and weapon authority remain fighter-only.
- Bombers, attackers, and G4M currently have common noncombat flight authority only. Strike, ground-attack, dive-bomb, and torpedo execution are not implemented.

## Validated milestones

- Reciprocal A6M/P-47N regression passed in run `30050199123`; both aircraft fired, minimum separation remained above 8 blocks, no ground contact or collision occurred, and the primary aircraft returned to `PARKED`.
- Level-bomber common flight passed for B-17, B-29, G10N1, G10N2, and He 111.
- Attacker common flight passed for D4Y, Ju 87, SBD, and IL-2.
- G4M common noncombat flight passed in run `30050488243`; torpedo targeting and release remain unimplemented.
- PR #27 passed build, deterministic simulation, MissionOrder GameTest, A6M real-physics `full`, diagnostics, and crash-report checks in Windows self-hosted run `30054141737`.
- PR #30 source content passed Windows self-hosted run `30083391316`:
  - exact validated source head `0cfda884f20ab8e93754ad1286185f5f7a0af57d`;
  - normal build passed;
  - deterministic autonomous-flight simulation passed 12/12;
  - all MissionOrder persistence GameTests passed;
  - A6M real-physics `full` passed in 4,326 ticks;
  - final phase `PARKED`;
  - scenario verifier passed 1/1;
  - crash reports none.

## Mission-order persistence now on main

PR #30 adds:

- stable NBT encoding for every immutable mission-order field;
- overworld `SavedData` keyed by aircraft UUID;
- server bind/unbind, dirty marking, and revision restoration;
- strict vector and scalar NBT validation;
- malformed-entry isolation;
- valid empty and non-empty abort-condition lists;
- greatest-valid-revision selection for duplicate aircraft UUIDs;
- equal-revision/different-order conflict isolation;
- rejection of revisions without safe increment room;
- overflow-safe manager revision allocation.

This layer owns stored intent only. It remains disconnected from live aircraft controls, role policy, combat logic, weapon authority, and `ControlAuthorityArbiter`.

## Validation capacity and runner state

- GitHub-hosted Actions minutes are exhausted. Zero-step hosted failures are capacity failures, not code failures.
- Windows self-hosted runner `ジョリー` is online again and completed run `30083391316` successfully.
- Do not create duplicate self-hosted requests for the same source head.
- Poll in-progress runs only a bounded number of times and record the exact run/head before pausing.

## Preserved safety invariants

Never weaken these to make a validation pass:

- player-controlled aircraft receive no AI flight input;
- fixed forward guns never fire at a target behind the aircraft;
- line-of-sight, range, friendly-fire, terrain, and collision checks remain authoritative;
- reciprocal dogfight minimum separation remains at least 8 blocks;
- no ground contact or aircraft collision during combat qualification;
- bombers and attackers do not inherit fighter targeting, defensive manoeuvre, re-engagement, or fixed-gun combat authority;
- an aircraft without an explicit attack-capable mission order does not attack by default;
- enabling a role for noncombat flight does not silently enable its weapons.

## Next exact workflow

Implement the next common-navigation slice as a separate Draft PR:

1. Add an immutable `WaypointRoute` data model only.
2. Represent an ordered, non-empty list of finite positions plus a bounded arrival radius per waypoint.
3. Define deterministic progression semantics without writing aircraft controls.
4. Add UUID-keyed route assignment/replacement/clear operations with optimistic revisions, or reuse the existing mission revision boundary where doing so avoids duplicate ownership.
5. Add deterministic contract tests for invalid vectors, empty routes, progression, stale revisions, and completion.
6. Do not connect the route to `AutonomousFlightManager`, `ControlAuthorityArbiter`, weapons, role policy, or live flight input in this slice.
7. Validate static contracts and normal build first. Run one A6M `full` self-hosted regression only after the focused tests pass.
8. Keep the change under 10 files and 800 added/changed lines.

After the route data boundary is validated and merged, the following slice may adapt one noncombat order (`HOLD_POSITION` or `RETURN_TO_BASE`) into guidance. Do not enable strike or weapon behavior at the same time.

## Useful references

- parent roadmap: Issue #7;
- merged mission-order foundation: PR #27;
- merged mission-order persistence: PR #30;
- persistence validation: run `30083391316`;
- mission-order foundation validation: run `30054141737`;
- passing fighter regression: run `30050199123`;
- passing G4M common-flight validation: run `30050488243`.
