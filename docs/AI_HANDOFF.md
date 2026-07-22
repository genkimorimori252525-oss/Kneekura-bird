# AI development handoff

Last updated: 2026-07-22 (Asia/Tokyo)

## Read first

Follow `/AGENTS.md` before changing code. The user waived the normal session/time/CI-attempt limits for completing the current P-47N mutual-dogfight qualification, but all safety and firing invariants remain mandatory.

GitHub-hosted Actions capacity is currently exhausted. A workflow that ends before creating steps or logs is an execution-capacity failure, not a code result. Do not trigger repeated hosted runs, mark a behavior PR ready, or merge unexecuted behavior changes.

## Parent task

Complete autonomous flight, mission and combat AI for all 24 base aircraft.

The immediate blocker before returning to the 24-aircraft matrix is the reciprocal fighter qualification `dogfight_mutual`:

- the A6M has fired legitimately in preserved real-physics runs;
- the P-47N has not yet fired in the same passing run;
- safety, mission return, landing and parking have remained broadly stable;
- the missing capability is conversion of a safe P-47N extension into a legitimate firing pass against a reacting A6M.

## Current working line

Do not resume from the old oversized experimental PRs.

- Draft PR #9: full-loop and closure-release research history.
- Draft PR #13: near-vertical apex-yaw research history; its hosted checks never started because Actions minutes were exhausted.
- Active un-PR'd branch: `agent/p47-coupled-climb-replay`.
- Production adapter: `EnergyFighterApexYawAdapter.java`.
- Latest selected-constant implementation commit: `5fee5f21e845753fb4d8949dd853191feeb3e5c0`.

The branch intentionally remains without a PR so changes under `ww-debug-benchmark/**` do not trigger more unstartable hosted workflows.

## Established root cause

P-47N failure is not adequately explained by one bad angle threshold.

- Pure horizontal pursuit preserves bearing but overshoots because closure remains high.
- Reversing the horizontal turn discards bearing.
- A completed vertical loop or near-vertical climb converts too much useful separation into altitude and delays yaw because Immersive Aircraft smooths X/Z input over ten ticks.
- The required maneuver is a **shallow coupled climbing turn**: begin yaw while converting only a limited amount of closure into altitude, then finish with measured lead capture.

The exact Immersive Aircraft 1.20.1 input and physics order has been inspected and modeled: input interpolation, yaw/pitch, lift-based velocity conversion, glide, friction, horizontal/vertical decay, speed-dependent gravity, thrust and engine response.

## Selected candidate

Machine-readable source of truth:

`ww-debug-benchmark/tools/p47_coupled_climb_candidate.json`

Parameters:

- climb target pitch: `-22 deg`;
- yaw trigger pitch: `-2 deg`, after minimum 8-tick commitment;
- pivot-to-capture heading error: `65 deg`;
- pivot divisor: `22`;
- capture pitch divisor: `10`;
- capture pitch-rate damping: `0.10`;
- yaw-rate damping: `0.05`;
- lead horizon: `8 ticks`.

The production adapter contains the same values. Commit `5fee5f21` was inspected after the full-file update and changes only these seven constants; attack and safety gates were unchanged.

## Pre-flight evidence

Tools on the active branch:

- `analyze_apex_yaw_replay.py`: exact 10-tick orientation/input replay;
- `batch_apex_yaw_replay.py`: multi-session angular and recorded static-gate replay;
- `analyze_coupled_climb_trajectory.py`: advances modeled P-47N position, velocity, attitude, thrust, drag, glide and gravity;
- `test_coupled_climb_trajectory.py`: one-tick calibration against preserved PR #9 Forge telemetry;
- `verify_p47_candidate_sync.py`: verifies JSON/Java candidate equality and pins safety/firing constants;
- `P47_COUPLED_CLIMB_REPLAY.md`: evidence and limitations.

Calibration reproduces one preserved real-physics tick to:

- yaw/pitch: five decimal places;
- engine power: six decimal places;
- position: within `0.005` blocks;
- velocity: within `0.005` blocks/tick.

After removing a duplicate PR #8 trajectory, the selected candidate reaches the standard angle/range/closure attack sector in all nine unique preserved trajectories in the calibrated model.

Modeled aggregate envelope:

- minimum speed about `17.5 bps`;
- minimum separation about `17.2 blocks`;
- maximum separation about `149.7 blocks`;
- attack-sector arrival `135..245 ticks` after re-entry start.

This is not a qualification pass. The A6M reaction, real LOS, threat arbitration, terrain, collision and weapon release require the Forge server.

## Safety invariants

Never weaken these merely to make the qualification pass:

- terrain and collision avoidance retain control priority;
- no player-pilot takeover;
- credible close threats release the maneuver to defensive combat;
- real LOS, range, friendly-fire and fixed-gun cone checks remain authoritative;
- no rear-target firing;
- no scripted shot or free initial rear-quarter shot;
- minimum safe separation remains at least 8 blocks;
- no ground contact or aircraft collision;
- primary mission must resume and finish with return, landing and parking.

## Exact next validation

When any real execution path becomes available:

1. run `python tools/test_coupled_climb_trajectory.py`;
2. run `python tools/verify_p47_candidate_sync.py`;
3. run ordinary benchmark build and deterministic mission simulation;
4. run exactly one targeted `dogfight_mutual` Forge GameTest;
5. inspect legitimate A6M/P-47N fire counts, control transitions, minimum and maximum separation, minimum speed, AGL, ground contact and collision;
6. if both fighters fire safely, repeat the same targeted test for stability;
7. only after the repeat passes, run the full regression matrix;
8. build a clean focused PR from current `main`, carrying only the required production/controller, deterministic-opening and validation changes—not the research history.

If the targeted run fails, analyze its saved telemetry before changing code. Do not return to blind threshold tuning.

## Return to the 24-aircraft parent task

After reciprocal P-47N/A6M qualification and full regression pass:

1. verify all 24 measured profiles load correctly;
2. validate non-combat autonomy: takeoff, climb, cruise, turn, stall recovery;
3. validate doctrine split across all fighters: `turn_fighter`, `energy_fighter`, balanced fallback;
4. validate terrain avoidance, landing and fuel management;
5. validate targeting, pursuit, firing, defensive behavior and formation by role;
6. run the complete aircraft-by-scenario matrix and fix only profile/role-specific failures without weakening global safety.
