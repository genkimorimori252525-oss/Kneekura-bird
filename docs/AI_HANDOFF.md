# AI development handoff

Last updated: 2026-07-24 (Asia/Tokyo)

## Read first

Follow `/AGENTS.md` before changing code. The hard session limits are 60 minutes, 8 remote CI attempts, 10 changed files, and 800 added/changed lines, with a mandatory checkpoint at 30 minutes or 4 CI attempts.

GitHub state, merged commits, open PRs, and current workflow results override older notes in this file.

## Current repository state

- `main` contains merged PR #21 at commit `8b533fa0817e83762e6ef973b3b1e58a6179fb98`.
- PR #21 extends the measured-profile autonomous-flight stack to level bombers while keeping fighter-only awareness, defensive manoeuvre, re-engagement, and weapons behind `FighterCombatFacade`.
- `ControlAuthorityArbiter` is already integrated and must not be reimplemented.
- The reciprocal A6M/P-47N qualification is complete and must not be retuned unless a later change causes a measured regression.
- Old fighter experiment PRs and branches are research history, not coding baselines.

## Latest validated milestone: PR #21

PR: `#21 Enable measured-profile noncombat level bomber autonomy`

Final main-relative commit: `f2839fe99ab452eda393ed5d4e17761fbfd0542b`
Merged commit: `8b533fa0817e83762e6ef973b3b1e58a6179fb98`

### B-17 full autonomous mission

Windows self-hosted run: `30037836662`

- build and deterministic simulation passed;
- measured BOMBER profiles were generated for B-17, B-29, He 111, G10N1, G10N2, and G4M;
- 6,215 autonomous frames;
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

The repository now has validated pieces of the intended stack:

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

Start the common mission-order and navigation foundation as a small, noncombat PR.

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

The first mission-order PR should be plumbing only. It must not grant new weapon authority, alter existing dogfight geometry, or change the validated B-17 flight path.

## Follow-on slices after the mission-order model

Proceed in separate PRs:

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

Create a clean `agent/mission-order-foundation` branch from current `main`, inspect existing package conventions and persistence helpers, then implement the smallest mission-order model plus manager and deterministic tests. Keep it Draft until build and deterministic checks pass.

## Useful references

- parent roadmap: Issue #7
- merged reciprocal fighter qualification: PR #17 and PR #18 history
- merged level-bomber autonomy: PR #21
- B-17 validation run: `30037836662`
- fighter regression run: `30038437329`
- current merged baseline: `8b533fa0817e83762e6ef973b3b1e58a6179fb98`
