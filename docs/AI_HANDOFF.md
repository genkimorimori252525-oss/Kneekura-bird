# AI development handoff

Last updated: 2026-07-24 (Asia/Tokyo)

## Read first

Follow `/AGENTS.md` before changing code. The hard session limits are 60 minutes, 8 remote CI attempts, 10 changed files, and 800 added/changed lines, with a mandatory checkpoint at 30 minutes or 4 CI attempts.

GitHub state, merged commits, open PRs, and current workflow results override older notes in this file.

## Current repository state

- The production baseline is merged PR #21 at commit `8b533fa0817e83762e6ef973b3b1e58a6179fb98`.
- PR #21 extends measured-profile autonomous flight to level bombers while keeping fighter-only awareness, defensive manoeuvre, re-engagement, and weapons behind `FighterCombatFacade`.
- `ControlAuthorityArbiter` is already integrated and must not be reimplemented.
- The reciprocal A6M/P-47N qualification is complete and must not be retuned unless a later change causes a measured regression.
- Old fighter experiment PRs and branches are research history, not coding baselines.
- Commits after the PR #21 merge currently consist of self-hosted validation request/status records; they do not change production flight behaviour.

## Validated milestones

### B-17 full autonomous mission

Windows self-hosted run: `30037836662`

- build and deterministic simulation passed;
- measured BOMBER profiles were generated for B-17, B-29, He 111, G10N1, G10N2, and G4M;
- both 170-degree turns passed;
- controlled stall and recovery passed;
- return, pattern entry, final, flare/go-around recovery, touchdown, braking, and parking passed;
- final phase `PARKED`;
- final speed `0.0 bps`;
- verifier `passed=true`;
- no crash report.

### Reciprocal fighter regression

Windows self-hosted run: `30038437329`

- build and deterministic simulation passed;
- real-physics reciprocal dogfight passed;
- A6M fire count: 5;
- P-47N fire count: 1;
- minimum separation: 11.75 blocks;
- maximum separation: 189.12 blocks;
- ground-contact frames: 0 / 0;
- primary A6M resumed the ordinary mission and ended `PARKED`.

### Level-bomber generality checks

The same merged production ref, `8b533fa0817e83762e6ef973b3b1e58a6179fb98`, is being exercised across the remaining level-bomber entities without production-code changes.

- B-29: a retry validation completed successfully before the current G10N sequence.
- G10N1: Windows self-hosted run `30043071124` completed successfully for `scenario=full`.
- G10N2: request commit `822e675ea6c7beae8b218f5aae38562e0a94f995` is present on `main`; at this handoff update, no matching completed status record has yet replaced the G10N1 status file.
- He 111 remains to be confirmed in the same matrix.

Do not call a requested aircraft validated until its status record and result artifact both identify the requested production ref and end in success.

Hosted PR jobs for this period sometimes ended before executing any step because hosted Actions capacity was unavailable. Do not treat a zero-step hosted job as a code failure. Prefer the Windows self-hosted path while that condition persists.

## Preserved safety invariants

Never weaken these to make a validation pass:

- player-controlled aircraft receive no AI flight input;
- fixed forward guns never fire at a target behind the aircraft;
- line-of-sight, range, friendly-fire, terrain, and collision checks remain authoritative;
- reciprocal dogfight minimum separation remains at least 8 blocks;
- no ground contact or aircraft collision during the combat window;
- bombers do not inherit fighter targeting, defensive manoeuvre, re-engagement, or fixed-gun combat authority;
- an aircraft without an explicit attack-capable mission order must not attack by default.

## Architecture already present

```text
Mob pilot eligibility
    -> measured FlightProfile resolution
    -> role gating
    -> ControlAuthorityArbiter
    -> fighter-only FighterCombatFacade when applicable
    -> terrain/collision-safe flight guidance
    -> real aircraft inputs
```

Do not create a second control-authority dispatcher or a parallel fighter combat tick path.

## Next focused milestone

Start the common mission-order and navigation foundation as a small, noncombat PR only after the current level-bomber validation request has reached a terminal result and been recorded.

Recommended first slice:

1. Introduce an immutable mission-order data model and order type enum.
2. Add a server-side `MissionOrderManager` keyed by aircraft UUID.
3. Support only safe initial commands:
   - `HOLD_POSITION`
   - `RETURN_TO_BASE`
   - `LAND`
4. Store optional target position, home-base/runway reference, mission altitude, engagement permission, and abort reason without changing current flight behaviour yet.
5. Add deterministic tests for assignment, replacement, clearing, and default no-order behaviour.
6. Keep persistence, chunk reload, fuel prediction, formation data, and attack orders out of the first slice unless they can be added without expanding beyond one focused hypothesis.

The first mission-order PR should be plumbing only. It must not grant new weapon authority, alter existing dogfight geometry, or change the validated bomber flight path.

## Follow-on slices

1. `WaypointRoute` and route-progress state.
2. Home base and runway registration.
3. Safe route guidance using measured `flight_profiles`.
4. Fuel, ammunition, and damage-based return decisions.
5. Save/load restoration and chunk-boundary continuity.
6. Noncombat all-aircraft flight matrix.
7. Role-specific bomber, attacker, and torpedo-bomber mission execution.
8. Escort, formation, target allocation, and multi-aircraft runway sequencing.

## Validation order for the next code PR

1. Static inspection and deterministic tests.
2. Normal benchmark build.
3. Existing fighter deterministic regression.
4. One targeted noncombat mission-order scenario only after the data model and manager are stable.
5. Real-physics GameTest only when the change actually affects live flight behaviour.

A pure data-model/manager PR should not consume a Windows GameTest run unless it connects to the live controller.

## Current single next action

First inspect the terminal result for the G10N2 request on `main`. If successful, record its exact run/result artifact and request He 111 only if no existing successful record exists. Once the level-bomber matrix is settled, create `agent/mission-order-foundation` from then-current `main` and implement the smallest mission-order model plus manager and deterministic tests.

## Useful references

- parent roadmap: Issue #7
- merged reciprocal fighter qualification: PR #17 and PR #18 history
- merged level-bomber autonomy: PR #21
- B-17 validation run: `30037836662`
- fighter regression run: `30038437329`
- G10N1 validation run: `30043071124`
- current production behavior baseline: `8b533fa0817e83762e6ef973b3b1e58a6179fb98`
