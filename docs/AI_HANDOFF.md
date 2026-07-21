# AI development handoff

Last updated: 2026-07-22 (Asia/Tokyo)

## Read first

Follow `/AGENTS.md` before changing code. The hard session limits are 60 minutes, 8 remote CI attempts, 10 changed files, and 800 added/changed lines, with a mandatory checkpoint at 30 minutes or 4 CI attempts.

## Repository state

- `main` contains merged PR #4 at commit `8a91e7e44d8050505cd3ec948a2ed3c263ec342c`.
- PR #4 established doctrine-specific fighter combat, the neutral opposed opening, stale rear-threat release, fixed-gun rear-target rejection, and initial P-47N re-engagement safeguards.
- The remaining acceptance gap is `dogfight_mutual`: the A6M fires legitimately, but the P-47N has not fired in the same passing run.

## Active behavior PR

- PR #6: `Add bounded P-47N re-engagement`
- Draft branch: `agent/mutual-p47-counterattack-minimal`
- Recommended current head: `257d300feccf9087e5c1804bc035a37b2542dc5a`
- Scope: 3 changed files, 725 additions, 5 deletions.
- Normal benchmark build and deterministic mission simulation pass.
- Keep PR #6 Draft. Do not merge until both aircraft fire in one run and the result is repeated for stability.

The branch was intentionally returned to `257d300f` after the eight-attempt session. Later experiment commits and artifacts remain evidence only; they are not the recommended behavior baseline.

## Current best behavior candidate

Commit: `257d300feccf9087e5c1804bc035a37b2542dc5a`

Observed targeted result:

- A6M fire count: 7
- P-47N fire count: 0
- minimum separation: 11.79 blocks
- maximum separation: 158.44 blocks
- no ground contact for either aircraft
- primary mission returned to a passing parked result
- only behavioral acceptance failure: P-47N produced no firing event

This candidate adaptively hands off near the measured 83–90 degree crossing minimum. It is the smallest stable point from the session, although the ordinary energy-fighter doctrine then selects `REPOSITION` and loses the geometry.

Useful artifact:

- workflow run: `29855959212`
- results artifact: `8505326040`

## Eight behavior experiments and conclusions

1. `257d300f` — adaptive handoff activated near the broadside minimum, but ordinary doctrine selected `REPOSITION`; retained as the smallest stable baseline.
2. `0e68272d` — same-direction lead pursuit worsened lead/raw angle toward roughly 132 degrees.
3. `63b89ace` — reversing the horizontal turn worsened raw angle toward roughly 170 degrees.
4. `eec52a6f` — late high-yoyo reduced closure but lost turn authority; best angle remained near 95 degrees.
5. `cf9664fb` — earlier capture exposed contradictory start/release thresholds; best angle remained near 95 degrees.
6. `78902005` — sustained high-yoyo reduced closure to roughly 2.3 bps, but speed protection reduced yaw authority.
7. `1ee8f962` — powered high-yoyo preserved yaw rate and reached 79.83 degrees, but closure rose to roughly 17.4 bps and the P-47N passed the geometry without firing.
8. `f35cca44` — vertical zoom reduced closure from 14.35 to -2.0 bps, but raw angle regressed from 86.91 to 121.52 degrees; later lead re-entry recovered only to 108.96 degrees.

Attempt 7 artifact:

- workflow run: `29859047267`
- results artifact: `8506580265`

Attempt 8 artifact:

- workflow run: `29859888869`
- results artifact: `8506900520`

## Root cause established

This is not primarily a threshold-selection problem.

- Horizontal pursuit preserves bearing progress but cannot remove closure before overshoot.
- Reversing the horizontal turn loses the geometry immediately.
- Continuous high-yoyo control remains inside the A6M turning circle; powered variants preserve turn rate but closure still grows.
- A wings-level vertical zoom removes closure but discards too much bearing.

The missing behavior is a coupled three-dimensional trajectory that controls closure and bearing together. It must retain useful angular progress, convert some excess horizontal closure into altitude, preserve speed and yaw authority, and re-enter only when the predicted lead solution is genuinely usable.

## Deterministic telemetry replay

Focused analysis branch:

- branch: `agent/p47-oblique-yoyo-replay`
- initial tool commit: `ef05c7ef27a7d73affb9e804adc7ea30f94e40f1`
- tool: `ww-debug-benchmark/tools/analyze_reentry_geometry.py`

The tool is standard-library-only and evaluates 2,880 oblique lag-yoyo candidates against recorded JSONL telemetry. The target follows its recorded path while the candidate P-47N uses measured speed plus capped measured yaw/pitch response.

The model is deliberately only a pre-GameTest filter:

- the replayed target does not react to the counterfactual trajectory;
- the P-47N is a capped-rate point mass, not full Immersive Aircraft physics;
- all real collision, terrain, weapon, line-of-sight, friendly-fire, and rear-target checks remain authoritative.

### Attempt 7 replay

Start tick: `1403`

Recorded baseline over 320 ticks:

- minimum separation: 44.00 blocks
- minimum raw angle: 79.67 degrees
- attack-sector ticks: 0
- narrow-sector ticks: 0
- final raw angle: 145.70 degrees
- final closure: -14.76 bps

### Attempt 8 replay

Start tick: `1387`

Recorded baseline over 320 ticks:

- minimum separation: 40.39 blocks
- minimum raw angle: 86.91 degrees
- attack-sector ticks: 0
- narrow-sector ticks: 0
- final raw angle: 137.12 degrees
- final closure: -11.96 bps

## Replay-selected conservative candidate

The highest raw-scoring 15 bps candidates sometimes approached the 8-block safety limit. Prefer the following more conservative family for the next production hypothesis:

- lag duration: `20 ticks` (1.0 second)
- yaw authority during lag: `0.50` of normal
- climb target: `8 degrees`
- predicted-lead horizon after lag: `0.50 seconds`
- speed floor: `18 bps`

Attempt 7 replay result:

- first narrow-sector tick offset: 237
- narrow-sector duration: 70 ticks
- minimum separation: 20.80 blocks
- final raw angle: 19.46 degrees
- final closure: 24.84 bps

Attempt 8 replay result:

- first narrow-sector tick offset: 257
- narrow-sector duration: 64 ticks
- minimum separation: 52.44 blocks
- final raw angle: 6.55 degrees
- final closure: 13.37 bps

The replay therefore finds a shared candidate family that improves both preserved failures instead of fitting only one run. It does not yet prove that the real aircraft will preserve the predicted yaw authority at 18 bps.

## Next single production hypothesis

From the clean PR #6 behavior baseline or a clean successor based on it:

1. At the measured crossing minimum, enter a bounded one-second oblique lag phase.
2. During that phase, use half normal yaw authority, target a shallow 8-degree climb, and preserve at least 18 bps.
3. After 20 ticks, transition to a 0.5-second predicted-lead pursuit.
4. Hand ordinary doctrine or final alignment control back only when the predicted lead angle is inside the existing attack sector.
5. Log lag elapsed ticks, commanded speed, raw angle, predicted lead angle, closure, altitude difference, and handoff reason.

Do not simultaneously change opening geometry, collision thresholds, terrain priority, defensive emergency priority, or any actual firing gate.

Validation order:

1. static inspection and replay against attempts 7 and 8;
2. normal build and deterministic mission simulation;
3. one targeted `dogfight_mutual` GameTest;
4. repeat only if the result is materially different and safe;
5. full regression only after reciprocal firing passes.

## Closed experiment directions

- Do not change the neutral opening offset. Lateral 75 was unsafe and lateral 110 caused excessive separation; retain the merged 55-block opening.
- Do not bypass collision avoidance.
- Do not weaken the real firing gates.
- Do not retry simple same-turn pursuit, simple opposite-turn pursuit, or wings-level vertical zoom as standalone fixes.
- Do not append experiments to oversized PR #5.

## Safety and acceptance criteria

A candidate is not complete until one run satisfies all of the following:

- neutral opposed opening; no initial rear free shot;
- A6M fires at least once through the real weapon manager;
- P-47N fires at least once through the real weapon manager;
- no fixed-gun firing at a target behind the aircraft;
- both aircraft perform autonomous attack and defensive behavior;
- no ground contact or aircraft collision;
- minimum separation at least 8 blocks;
- maximum separation at most 480 blocks;
- P-47N remains inside the useful simulation area;
- primary aircraft resumes the normal mission and returns, lands, and parks;
- the targeted result is repeated for stability before the full regression matrix.

## Useful references

- merged behavior baseline: `8a91e7e44d8050505cd3ec948a2ed3c263ec342c`
- active behavior PR: `#6`
- recommended behavior head: `257d300feccf9087e5c1804bc035a37b2542dc5a`
- telemetry replay branch: `agent/p47-oblique-yoyo-replay`
- replay tool commit: `ef05c7ef27a7d73affb9e804adc7ea30f94e40f1`
- research PR: `#5`
- research branch: `agent/energy-fighter-counterattack-recovery`
