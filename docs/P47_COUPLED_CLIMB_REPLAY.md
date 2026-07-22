# P-47N coupled-climb trajectory replay

Date: 2026-07-22

## Purpose

This branch replaces blind remote threshold tuning with a deterministic pre-flight model derived from the Immersive Aircraft 1.20.1 update order. GitHub-hosted Actions minutes are exhausted, so replay, build and real Forge GameTest validation run locally without dispatching workflows.

The model does **not** replace Forge GameTest. The P-47N position, velocity, orientation, input smoothing, thrust, drag, glide and gravity are resimulated; the A6M retains its preserved real-physics trajectory. Target response, line of sight, terrain, collision and threat arbitration remain authoritative only in the real server test.

## Physics calibration

`tools/test_coupled_climb_trajectory.py` fixes both one consecutive PR #9 telemetry step and a 94-tick local P-47N pivot trace as regression fixtures.

The modeled tick reproduces:

- yaw and pitch to five decimal places;
- engine power to six decimal places;
- position within 0.005 blocks;
- velocity within 0.005 blocks/tick.

The calibration covers the P-47N constants used by the trajectory replay:

- engine speed `0.102`;
- yaw speed `2.5 deg/tick`;
- pitch speed `2.4 deg/tick`;
- lift `0.165`;
- friction/drift drag `0.013`;
- glide factor `0.055`;
- horizontal and vertical decay `0.97`;
- rotation decay `0.97`;
- 10-tick X/Z input interpolation;
- 100-step engine-power response observed in the preserved run.

The missing production behavior in the earlier model was the control decay performed by `InventoryVehicleEntity.applyFriction()` before `AircraftEntity.updateController()`:

```text
control_decay = (1 - 0.013) * 0.97 = 0.95739 per tick
```

With interpolation included, a sustained `-0.96` logical yaw command converges to an effective input of about `-0.664`, not `-0.96`. The corrected replay matches the 105-frame local pivot with yaw error below `1 deg` and pitch error below `0.2 deg`. The one-tick position and velocity checks remain within `0.005`; the longer replay can drift by about four blocks because it does not model wind and all server-side state.

## Current production baseline

The machine-readable source of truth is `tools/p47_coupled_climb_candidate.json`.

The current modeled candidate is deliberately shallow and coupled:

- climb target pitch: `-22 deg`;
- yaw trigger pitch: `-2 deg`, after the minimum eight-tick commitment;
- pivot hands to lead capture at `65 deg` horizontal lead error;
- pivot input divisor: `22`;
- capture pitch divisor: `10`;
- capture pitch-rate damping: `0.10`;
- yaw-rate damping: `0.05`;
- lead horizon: `8 ticks`.

These values remain synchronized with Java, but they are now marked as a rejected baseline in the JSON. They must not be presented as a passing pre-flight candidate.

## Corrected local result

The earlier claim that this baseline reached the static attack sector in nine of nine preserved trajectories is invalid. That result omitted the per-tick control decay and overestimated P-47N yaw authority by roughly 30 to 40 percent.

The corrected model reproduces the latest local `pivot_timeout` at both observed re-entry starts:

- start tick `5351`: no attack sector, `105` samples, minimum speed `35.72 bps`, distance `82.97..112.37` blocks;
- start tick `5575`: no attack sector, `108` samples, minimum speed `34.18 bps`, distance `114.85..135.20` blocks.

The local headless `dogfight_mutual` run completed the physical GameTest and the primary A6M returned, landed and parked. The scenario verifier correctly failed only because the A6M fired three times and the P-47N fired zero times. Minimum and maximum separation were `10.86` and `158.44` blocks, with no combat ground contact.

The plan's proposed handoff at approximately `90 deg` raw angle with positive closure was evaluated in the corrected replay. It reached capture but still did not produce an attack sector. A separate diagnostic that limited capture pitch during the crossing also failed at both starts. Neither rejected experiment was applied to Java.

This is a controller-design limitation rather than justification for changing firing, separation, terrain or collision gates.

## Required next validation

Do not merge from this replay alone.

When an execution path is available:

1. preserve the corrected multi-tick physics regression;
2. design a distinct crossing-to-approach controller that accounts for the effective yaw authority;
3. reject it in replay unless both observed starts enter the unchanged attack sector safely;
4. run the ordinary build and deterministic mission simulation;
5. run one targeted local `dogfight_mutual` only after the pre-flight gate passes;
6. inspect legitimate A6M and P-47N fire counts, minimum/maximum separation, ground contact, AGL, speed and control-stage transitions;
7. repeat only after the first safe reciprocal-firing pass, then run the full regression matrix.

All existing terrain, collision, line-of-sight, range, friendly-fire, fixed-gun cone, rear-target and credible-threat safeguards remain non-negotiable.
