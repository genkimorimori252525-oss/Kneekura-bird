# P-47N coupled-climb trajectory replay

Date: 2026-07-22

## Purpose

This branch replaces blind remote threshold tuning with a deterministic pre-flight model derived from the exact Immersive Aircraft 1.20.1 update order. GitHub-hosted Actions minutes are exhausted, so this work prepares one materially justified candidate for the next available real Forge GameTest rather than creating repeated unstarted workflow runs.

The model does **not** replace Forge GameTest. The P-47N position, velocity, orientation, input smoothing, thrust, drag, glide and gravity are resimulated; the A6M retains its preserved real-physics trajectory. Target response, line of sight, terrain, collision and threat arbitration remain authoritative only in the real server test.

## Physics calibration

`tools/test_coupled_climb_trajectory.py` fixes one consecutive PR #9 telemetry step as a regression fixture.

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
- 10-tick X/Z input interpolation;
- 100-step engine-power response observed in the preserved run.

## Selected candidate

The current modeled candidate is deliberately shallow and coupled:

- climb target pitch: `-22 deg`;
- yaw begins after the minimum eight-tick commitment, without waiting for a near-vertical apex;
- pivot hands to lead capture at `65 deg` horizontal lead error;
- pivot input divisor: `38`;
- capture pitch divisor: `12`;
- capture pitch-rate damping: `0.10`;
- yaw-rate damping: `0.0`.

This is not a loop. It starts turning while converting a limited amount of horizontal closure into altitude, then lets the lead-capture controller finish the intercept.

## Preserved-run replay result

Ten downloaded artifacts were examined. PR #8 attempts 4 and 5 contain the same P-47N trajectory, leaving **nine unique trajectories**. The selected candidate reached the static attack sector in all nine:

- raw target angle `<= 45 deg`;
- predicted lead angle `<= 12 deg`;
- distance `24..125 blocks`;
- closure `-6..28 blocks/second`.

Aggregate modeled safety envelope across the nine unique trajectories:

- minimum speed: `18.55 bps`;
- minimum separation: `17.36 blocks`;
- maximum separation: `149.65 blocks`;
- modeled firing-window delay: `135..245 ticks` after re-entry start.

Representative modeled firing windows ranged from:

- fast capture: range about `50..57`, closure about `26`, speed about `41 bps`;
- slower recovered capture: range about `60..116`, closure about `5..20`, speed about `18.6..21.6 bps`.

## Why this supersedes the previous candidate

The earlier `-34 deg / -20 deg / 28 deg` coupled-climb candidate still held the climb too long and frequently timed out in pivot. The subsequent `-30 deg / -8 deg / 35 deg` candidate improved angular capture but remained inconsistent once the P-47N trajectory itself was resimulated.

The selected `-22 deg / immediate-overlap / 65 deg` candidate succeeded across every unique preserved trajectory in the calibrated model while staying above stall guard and within the accepted separation envelope.

## Required next validation

Do not merge from this replay alone.

When an execution path is available:

1. run the Python calibration test;
2. run the ordinary benchmark build and deterministic mission simulation;
3. apply the selected constants to the production adapter;
4. run one targeted `dogfight_mutual` Forge GameTest;
5. inspect legitimate A6M and P-47N fire counts, minimum/maximum separation, ground contact, AGL, speed and control-stage transitions;
6. repeat only after the first safe reciprocal-firing pass;
7. run the full regression matrix before merge.

All existing terrain, collision, line-of-sight, range, friendly-fire, fixed-gun cone, rear-target and credible-threat safeguards remain non-negotiable.
