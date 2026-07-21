# AI development handoff

Last updated: 2026-07-22 (Asia/Tokyo)

## Read first

Follow `/AGENTS.md` before changing code. The hard session limits are 60 minutes, 8 remote CI attempts, 10 changed files, and 800 added/changed lines, with a mandatory checkpoint at 30 minutes or 4 CI attempts.

## Repository state

- `main` contains merged PR #4 at commit `8a91e7e44d8050505cd3ec948a2ed3c263ec342c`.
- PR #4 established doctrine-specific fighter combat, the neutral opposed opening, stale rear-threat release, fixed-gun rear-target rejection, and initial P-47N re-engagement safeguards.
- The remaining acceptance gap is still `dogfight_mutual`: the A6M fires legitimately, but the P-47N has not fired in the same passing run.

## Active focused PR

- PR #6: `Add bounded P-47N re-engagement`
- Draft branch: `agent/mutual-p47-counterattack-minimal`
- Current head: `257d300feccf9087e5c1804bc035a37b2542dc5a`
- Current scope: 3 changed files, 725 additions, 5 deletions.
- Current files:
  - `EnergyFighterReengagementAdapter.java`
  - `EnergyFighterForwardAlignmentAdapter.java`
  - `VehicleEntityBenchmarkMixin.java`
- Normal benchmark build and deterministic simulation pass.
- Keep PR #6 Draft. Do not merge until both aircraft fire in one run and the result is repeated for stability.

The branch was intentionally returned to `257d300f` after the 8-attempt session. Later experiment commits and workflow artifacts remain available by SHA/run ID, but they are not the recommended coding baseline.

## Current best focused candidate

Commit: `257d300feccf9087e5c1804bc035a37b2542dc5a`

Observed targeted result:

- A6M fire count: 7
- P-47N fire count: 0
- minimum separation: 11.79 blocks
- maximum separation: 158.44 blocks
- no ground contact for either aircraft
- primary mission returned to a passing parked result
- only behavioral acceptance failure: P-47N produced no firing event

This candidate adaptively hands off the crossing near the measured 83–90 degree sector. It is the smallest stable point from the latest session, even though the ordinary energy-fighter doctrine then chooses `REPOSITION` and loses the geometry.

Useful artifact:

- workflow run: `29855959212`
- results artifact: `8505326040`

## Latest session: eight targeted CI attempts

### Attempt 1 — adaptive crossing handoff

- commit: `257d300feccf9087e5c1804bc035a37b2542dc5a`
- adaptive handoff activated near the broadside minimum
- A6M fired 7 times; P-47N fired 0 times
- ordinary energy doctrine selected `REPOSITION` and the raw target angle worsened
- retained as the current branch head because it was small, safe, and stable

### Attempt 2 — same-direction lead pursuit

- commit: `0e68272dedc1c414c1fc6c45411eaefe0ae5449e`
- a custom lead approach continued the crossing turn
- lead/raw angle worsened from roughly 89 degrees toward 132 degrees
- conclusion: following the same horizontal circle after the local minimum does not convert the geometry

### Attempt 3 — reverse horizontal turn

- commit: `63b89acee3484fdb7f963c8a65944d1326ea02bd`
- the controller reversed the turn at the local minimum
- raw target angle worsened from roughly 81 degrees toward 170 degrees
- conclusion: a simple left/right reversal is not the missing behavior

### Attempt 4 — late high-yoyo capture

- commit: `eec52a6f40fe7fa3207f10872d4d27d5482391ce`
- high-yoyo began around raw angle 99.5 degrees and closure 8.6 bps
- closure could be reduced, but turn authority fell and best angle stopped near 95 degrees
- conclusion: the maneuver started too late and coupled speed loss with insufficient turning

### Attempt 5 — earlier capture

- commit: `cf9664fb97f4cca121e7c09afd746f4cf2423d7d`
- capture began near raw angle 108.8 degrees and closure 3.2 bps
- a start/release threshold contradiction caused the energy-bleed phase to be skipped
- best angle reached about 94.8 degrees before defensive priority returned

### Attempt 6 — sustained high-yoyo

- commit: `78902005ec2fe29a479f3784ea8fd3d0682406ab`
- corrected the threshold contradiction
- closure was reduced from about 13.4 bps to 2.3 bps
- speed/turn protection then reduced yaw authority; best angle was about 92.3 degrees and later worsened

### Attempt 7 — powered high-yoyo

- commit: `1ee8f962f87d4a50520f01a2d5d12653e00f4ce0`
- preserved engine power and yaw rate during the climb
- best raw target angle reached 79.83 degrees
- closure still increased to roughly 17.4 bps while the P-47N remained in the same horizontal turning circle
- the aircraft passed the useful geometry without firing
- A6M fired 3 times; P-47N fired 0 times
- minimum separation 10.86 blocks; maximum separation 158.44 blocks; no ground contact

Useful artifact:

- workflow run: `29859047267`
- results artifact: `8506580265`

### Attempt 8 — vertical zoom and lead re-entry

- experiment commit: `f35cca4436e6bf73351e8f471862f309864068fc`
- the controller left the horizontal crossing circle in a short vertical zoom
- closure dropped from 14.35 bps to -2.0 bps
- raw target angle regressed from 86.91 degrees to 121.52 degrees during the zoom
- the later lead re-entry improved only to 108.96 degrees before timing out
- A6M fired 6 times; P-47N fired 0 times
- minimum separation 11.66 blocks; maximum separation 158.44 blocks
- no ground contact; primary mission returned and parked
- only verifier error remained `P-47N never fired at the A6M`

Useful artifact:

- workflow run: `29859888869`
- results artifact: `8506900520`

## Root cause now established

This is not primarily a threshold-selection problem.

- Horizontal pursuit can preserve bearing progress, but it cannot remove closure before overshoot.
- Reversing the horizontal turn loses the geometry immediately.
- Continuous high-yoyo control remains inside the A6M turning circle; powered variants preserve turn rate but closure still grows.
- A wings-level vertical zoom removes closure successfully, but discards too much bearing and leaves the target behind the usable attack sector.

The missing behavior is a coupled three-dimensional trajectory that controls **closure and bearing together**. It should retain the target near the measured 80–90 degree sector while converting excess horizontal closure into altitude, then re-enter with a genuine predicted lead solution.

## Mandatory next workflow

Do not immediately add another production controller and do not start with another remote GameTest.

1. Download the preserved attempt 7 and attempt 8 result artifacts.
2. Build a deterministic telemetry-replay or geometry-analysis tool under `ww-debug-benchmark/tools/`.
3. Feed it the P-47N and A6M JSONL frames around the crossing minimum.
4. Plot or calculate, tick by tick:
   - relative position and velocity;
   - raw target angle and predicted lead angle;
   - closure;
   - horizontal and vertical speed;
   - yaw rate, pitch rate, roll, and altitude difference.
5. Use the replay to compare an **oblique lag-yoyo** against the failed controls. The candidate should:
   - keep raw target angle approximately in the 80–90 degree sector;
   - drive closure toward zero;
   - avoid joining the A6M horizontal turning circle;
   - retain sufficient speed and yaw authority;
   - hand off only when predicted lead angle is inside a real attack sector.
6. Run static/deterministic checks first. Use one targeted remote GameTest only after the replay shows simultaneous improvement in closure and bearing.

Do not resume blind threshold tuning. If the replay cannot produce a plausible coupled trajectory, stop and reconsider the aircraft control model rather than adding another adapter layer.

## Closed experiment directions

- Do not change the neutral opening offset. Lateral 75 was unsafe and lateral 110 caused excessive separation; retain the merged 55-block opening.
- Do not bypass collision avoidance.
- Do not weaken the real firing gates.
- Do not retry simple same-turn pursuit, simple opposite-turn pursuit, or wings-level vertical zoom as standalone fixes.
- Do not append experiments to oversized PR #5.

## Oversized research PR

- PR #5, `Recover energy fighters from stale defensive extensions`, remains an open Draft research branch: `agent/energy-fighter-counterattack-recovery`.
- It grew to roughly 40 commits, 12 changed files, and more than 2,000 additions.
- Use it only for telemetry and comparison history.

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
- primary aircraft resumes the normal mission and returns/lands/parks;
- the targeted result is repeated for stability before the full regression matrix.

## Useful references

- merged baseline: `8a91e7e44d8050505cd3ec948a2ed3c263ec342c`
- active focused PR: `#6`
- active branch: `agent/mutual-p47-counterattack-minimal`
- recommended current head: `257d300feccf9087e5c1804bc035a37b2542dc5a`
- research PR: `#5`
- research branch: `agent/energy-fighter-counterattack-recovery`
