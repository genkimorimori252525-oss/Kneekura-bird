# AI development handoff

Last updated: 2026-07-24 (Asia/Tokyo)

## Read first

Follow `/AGENTS.md` before changing code. Hard limits are 60 minutes, 8 remote CI attempts, 10 changed files, and 800 added/changed lines, with a mandatory checkpoint at 30 minutes or 4 CI attempts.

Current GitHub state, merged commits, open PRs, and terminal workflow results override older notes in this file.

## Current production baseline

- Current `main` checkpoint before this documentation refresh: `5036fc0394268cda4a9dbd41ef89db576e8ce631`.
- PR #21 enabled measured-profile noncombat autonomous flight for level bombers.
- PR #25 enabled the same common noncombat flight path for measured attacker profiles.
- PR #27 merged the immutable `MissionOrder` model, all 11 roadmap order types, and the UUID/revision-guarded `MissionOrderManager`.
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

## Active focused PR

PR #28: `Persist mission orders across server restarts`

- branch: `agent/mission-order-persistence`;
- current head: `2006fef256989b2eff8f1a7f90470218d9a42b07`;
- state: Draft;
- scope: 5 files, 362 additions, 4 deletions;
- adds the stable NBT codec, overworld `SavedData`, server bind/unbind, dirty marking, restoration, revision continuity, and deterministic persistence contracts;
- remains disconnected from live flight input, weapons, and `ControlAuthorityArbiter`.

The earlier static audit finding is now corrected on the PR branch:

- vector fields must be compounds;
- `x`, `y`, and `z` must exist as numeric NBT values;
- non-finite vector values are rejected;
- failures remain `IllegalArgumentException`, allowing `MissionOrderSavedData.load` to isolate only the malformed assignment;
- deterministic coverage proves a malformed assignment is skipped while a valid neighboring assignment survives.

Do not merge the branch history directly. Before final validation, rebuild the focused source change from current `main` as one commit.

## Validation capacity and runner state

GitHub-hosted Actions minutes are exhausted.

- Hosted runs that create zero executable steps and no logs are capacity failures, not code failures.
- Do not trigger additional GitHub-hosted runs until the allowance or billing state changes.

Windows self-hosted run `30056967328` targeted the predecessor head, reached Gradle setup, and ended after the owner PC lost network access.

- request resolution and checkout succeeded;
- Java and Python setup succeeded;
- no compile, deterministic test, GameTest, or real-physics result was produced;
- do not treat it as a code or behavior regression.

An existing self-hosted request for current PR head `2006fef256989b2eff8f1a7f90470218d9a42b07` was recorded on `main` by commit `5036fc0394268cda4a9dbd41ef89db576e8ce631`. The status file still reports interrupted run `30056967328`, so runner availability has not been established. Do not create a duplicate request.

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

1. Keep PR #28 Draft and do not create another validation request while the runner is unavailable.
2. When the Windows runner is online, allow the existing request for head `2006fef...` to run once.
3. Validate in order: build and deterministic simulation; MissionOrder GameTests including malformed-neighbor isolation; one A6M `full` real-physics regression; diagnostics and crash-report checks.
4. On success, rebuild PR #28 from the latest `main` as one focused commit with identical source content, then validate the exact rebuilt head if required by the repository merge discipline.
5. Mark ready and squash-merge only after required checks pass.
6. After persistence merges, implement one noncombat order guidance adapter in a separate Draft PR. Do not enable strike or weapon behavior in that slice.

## Useful references

- parent roadmap: Issue #7;
- active persistence PR: #28;
- merged mission-order foundation: PR #27;
- mission-order validation: run `30054141737`;
- interrupted persistence validation: run `30056967328`;
- existing current-head validation request: main commit `5036fc0394268cda4a9dbd41ef89db576e8ce631`;
- passing fighter regression: run `30050199123`;
- passing G4M common-flight validation: run `30050488243`.
