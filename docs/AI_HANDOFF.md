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
- Active local validation branch: `agent/p47-local-validation`, based on and tracking
  `origin/agent/p47-coupled-climb-replay`.
- Production adapter: `EnergyFighterApexYawAdapter.java`.
- Latest selected-constant implementation commit: `5fee5f21e845753fb4d8949dd853191feeb3e5c0`.
- Local validation commits: `2115f049` (terrain-safety facade), `091fe1b9`
  (opponent combat-phase hold), and `45610883` (control-decay replay model).

The branch intentionally remains without a PR so changes under `ww-debug-benchmark/**` do not trigger more unstartable hosted workflows.

## Local execution path

The repository can now run both requested validation layers without GitHub Actions:

- JDK 17: `C:\Program Files\Java\jdk-17`;
- Gradle 8.8: cached locally and discovered by the VS Code tasks;
- lightweight checks: Python replay regressions plus the 12-case deterministic mission simulator;
- windowless Minecraft: Forge `runGameTestServer` with the exact Immersive Aircraft `1.3.3` and Warfare Wings `1.1.4` runtime jars;
- VS Code entry point: `.vscode/tasks.json`, especially `WW: Headless dogfight_mutual + verify`.

The headless verifier selects only the newest coherent A6M/P-47N telemetry session and treats a non-zero Gradle status as a failure. It no longer risks accepting stale telemetry from an earlier run.

## Established root cause

P-47N failure is not adequately explained by one bad angle threshold.

- Pure horizontal pursuit preserves bearing but overshoots because closure remains high.
- Reversing the horizontal turn discards bearing.
- A completed vertical loop or near-vertical climb converts too much useful separation into altitude and delays yaw because Immersive Aircraft smooths X/Z input over ten ticks.
- A **shallow coupled climbing turn** remains the useful energy-management basis, but the current direct pivot-to-capture controller cannot complete the crossing with the measured yaw authority. The next design needs an explicit crossing-to-approach policy rather than another isolated angle threshold.

The earlier replay omitted one critical step. `InventoryVehicleEntity.applyFriction()` decays the interpolated X/Z controls before `AircraftEntity.updateController()` consumes them:

```text
control_decay = (1 - 0.013) * 0.97 = 0.95739 per tick
```

Combined with 10-tick interpolation, a sustained `-0.96` command produces about `-0.664` effective yaw input. The old replay therefore overestimated P-47N yaw authority by roughly 30 to 40 percent. The corrected model reproduces the local 105-frame pivot with yaw error below `1 deg` and pitch error below `0.2 deg`.

## Current production baseline (rejected)

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

The production adapter contains the same values. Commit `5fee5f21` was inspected after the full-file update and changes only these seven constants; attack and safety gates were unchanged. The JSON now marks this parameter set `rejected_after_control_decay_correction`; it is a synchronized baseline, not a selected passing candidate.

## Pre-flight evidence

Tools on the active branch:

- `analyze_apex_yaw_replay.py`: exact 10-tick orientation/input replay;
- `batch_apex_yaw_replay.py`: multi-session angular and recorded static-gate replay;
- `analyze_coupled_climb_trajectory.py`: advances modeled P-47N position, velocity, attitude, thrust, drag, glide and gravity;
- `test_coupled_climb_trajectory.py`: one-tick calibration plus a 94-tick local pivot regression;
- `verify_p47_candidate_sync.py`: verifies JSON/Java candidate equality and pins safety/firing constants;
- `P47_COUPLED_CLIMB_REPLAY.md`: evidence and limitations.

The one-tick calibration reproduces preserved real physics to:

- yaw/pitch: five decimal places;
- engine power: six decimal places;
- position: within `0.005` blocks;
- velocity: within `0.005` blocks/tick.

The earlier nine-of-nine modeled attack-sector result is invalid because it omitted the control decay. With the corrected model, the current baseline reaches no attack sector at either local re-entry start (`5351`, `5575`) and reproduces `pivot_timeout`.

The latest local headless run completed the physical GameTest and the primary A6M returned, landed and parked. The verifier result was:

- A6M fire count: `3`;
- P-47N fire count: `0`;
- minimum/maximum separation: `10.86` / `158.44` blocks;
- combat ground-contact frames: `0` for both aircraft;
- sole verifier error: `P-47N never fired at the A6M`.

The proposed transition near `90 deg` raw angle with positive closure and a separate shallow-pitch capture diagnostic were tested only in the corrected replay. Neither produced an attack sector, so neither was applied to Java.

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

For the next controller hypothesis:

1. keep `python -B tools/test_coupled_climb_trajectory.py` passing;
2. design a distinct crossing-to-approach controller that accounts for effective yaw authority;
3. reject it locally unless both observed replay starts enter the unchanged attack sector safely;
4. run `python -B tools/verify_p47_candidate_sync.py`;
5. run the Gradle 8.8/JDK 17 build and deterministic mission simulation;
6. only then run exactly one targeted local `dogfight_mutual` Forge GameTest;
7. inspect legitimate A6M/P-47N fire counts, control transitions, minimum and maximum separation, minimum speed, AGL, ground contact and collision;
8. if both fighters fire safely, repeat the same targeted test for stability;
9. only after the repeat passes, run the full regression matrix;
10. build a clean focused PR from current `main`, carrying only the required production/controller, deterministic-opening and validation changes—not the research history.

If the targeted run fails, analyze its saved telemetry before changing code. Do not return to blind threshold tuning.

## Return to the 24-aircraft parent task

After reciprocal P-47N/A6M qualification and full regression pass:

1. verify all 24 measured profiles load correctly;
2. validate non-combat autonomy: takeoff, climb, cruise, turn, stall recovery;
3. validate doctrine split across all fighters: `turn_fighter`, `energy_fighter`, balanced fallback;
4. validate terrain avoidance, landing and fuel management;
5. validate targeting, pursuit, firing, defensive behavior and formation by role;
6. run the complete aircraft-by-scenario matrix and fix only profile/role-specific failures without weakening global safety.
