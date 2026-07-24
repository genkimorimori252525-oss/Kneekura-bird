# AI development handoff

Last updated: 2026-07-24 (Asia/Tokyo)

## Read first

Follow `/AGENTS.md` before changing code. Hard limits are 60 minutes, 8 remote CI attempts, 10 changed files, and 800 added/changed lines, with a mandatory checkpoint at 30 minutes or 4 CI attempts.

Current GitHub state, merged commits, open PRs, and terminal workflow results override older notes in this file.

## Current production baseline

- Current `main` checkpoint: `3da5938c0cdbcc47c1a3bb6fb68896f51ffdce1e`.
- PR #21 enabled measured-profile noncombat autonomous flight for level bombers.
- PR #25 enabled the same common noncombat flight path for measured attacker profiles.
- PR #27 merged the immutable `MissionOrder` model, all 11 roadmap order types, and the UUID/revision-guarded `MissionOrderManager`.
- `ControlAuthorityArbiter` is already integrated. Do not create a second authority dispatcher.
- Reciprocal A6M/P-47N combat qualification is complete. Do not retune it unless a later change produces a measured regression.
- Fighter targeting, defensive manoeuvre, re-engagement, and weapon authority remain fighter-only.
- Bombers, attackers, and G4M currently have common noncombat flight authority only. Strike, ground-attack, dive-bomb, and torpedo execution are not implemented.

## Validated milestones

### Fighter and common-flight baseline

- Reciprocal A6M/P-47N regression passed after attacker integration in run `30050199123`.
- The existing acceptance invariants remained satisfied: both aircraft fired through the real weapon path, minimum separation stayed above 8 blocks, no ground contact or collision occurred, and the primary aircraft returned to `PARKED`.
- Level-bomber common flight has passed for B-17, B-29, G10N1, G10N2, and He 111 through the shared measured-profile path.
- Attacker common flight has passed for D4Y, Ju 87, SBD, and IL-2.
- G4M common noncombat flight passed in run `30050488243`; this does not qualify torpedo targeting or release.

### Mission-order foundation

PR #27 was validated by Windows self-hosted run `30054141737` against source commit `81294ffea0e41a003046b5b7c5b56640d3607d72`.

Passing checks:

- benchmark build and deterministic flight simulation;
- MissionOrder contract GameTest;
- A6M real-physics `full` mission;
- diagnostics and crash-report checks.

The final one-commit integration was merged as PR #27. Mission orders still do not write aircraft controls and are not connected to weapons or `ControlAuthorityArbiter`.

## Active focused PR

PR #28: `Persist mission orders across server restarts`

- branch: `agent/mission-order-persistence`;
- current head: `bb12d55744b6ac8d8ae728b94c5ea73919c66061`;
- state: Draft;
- scope: 5 files, 309 additions, 4 deletions;
- adds NBT codec, overworld `SavedData`, server bind/unbind, dirty marking, restoration, revision continuity, and deterministic persistence tests;
- does not connect mission intent to live flight, weapons, or control authority.

The branch is behind `main` only because validation request/status commits accumulated after its base. Rebuild the focused change on current `main` before final validation instead of merging the stale history directly.

## Validation capacity state

GitHub-hosted Actions minutes are exhausted.

- Hosted runs `30056676801` and `30056676735` created no executable steps or logs.
- Treat those as capacity failures, not code failures.
- Do not trigger more GitHub-hosted runs until the allowance or billing state changes.

Windows self-hosted run `30056967328` targeted the exact PR #28 head and reached Gradle setup, then terminated when the owner PC lost network access.

- request resolution and checkout succeeded;
- Java and Python setup succeeded;
- the run ended during `Set up Gradle 8.8`;
- no compile, deterministic test, GameTest, or real-physics result was produced;
- do not treat this as a behavioral or code regression.

While the runner is offline, continue only with static inspection, documentation, deterministic-test design, and code-independent checkpoints. Do not create repeated validation requests.

## Static audit finding for PR #28

The persistence design is correctly isolated from flight control, but the NBT corruption boundary needs one focused hardening change before validation.

`MissionOrderCodec.readVec` currently accepts any compound and reads missing or incorrectly typed `x`, `y`, or `z` fields through `getDouble`, which silently returns zero. A malformed vector can therefore become a plausible zero-valued position instead of causing only that saved assignment to be isolated.

Required correction:

1. Require `x`, `y`, and `z` to exist as numeric NBT values.
2. Reject non-finite vector components.
3. Keep the failure as `IllegalArgumentException` so `MissionOrderSavedData.load` skips only the corrupt entry.
4. Add deterministic coverage proving a malformed vector entry is skipped while a valid neighboring assignment survives.
5. Do not change order semantics, flight guidance, weapons, terrain/collision checks, or the 8-block separation invariant.

Do not push this source correction while hosted workflows would be triggered without capacity unless an available self-hosted/local validation path can immediately check it. Preserve the exact patch plan in PR #28 and Issue #7 in the meantime.

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

1. Keep PR #28 Draft.
2. Record the interrupted runner result and malformed-vector audit finding in PR #28 and Issue #7.
3. When a validation path is available, rebuild PR #28 from current `main` as one focused commit.
4. Apply only the strict vector-decoding correction and malformed-neighbor isolation test.
5. Run checks in order: static/deterministic contract tests, normal build, MissionOrder GameTest, then one A6M `full` real-physics regression.
6. Mark ready and squash-merge only after those checks pass.
7. After persistence merges, the next production slice is one noncombat order guidance adapter; do not enable strike or weapon behavior in the same PR.

## Useful references

- parent roadmap: Issue #7;
- active persistence PR: #28;
- merged mission-order foundation: PR #27;
- mission-order validation: run `30054141737`;
- interrupted persistence validation: run `30056967328`;
- passing fighter regression: run `30050199123`;
- passing G4M common-flight validation: run `30050488243`.
