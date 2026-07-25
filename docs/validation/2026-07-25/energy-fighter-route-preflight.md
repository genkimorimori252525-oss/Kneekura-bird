# Energy-fighter route qualification preflight

Date: 2026-07-25

This document is a disconnected preflight for the ten remaining base energy fighters. It is **not** exact-physics qualification evidence and does not replace a Windows self-hosted GameTest.

## Evidence sources

- measured `flight_profiles.json` captured in Yak-3 diagnostic artifact `ww-local-route-30149217195`;
- `ProfileDrivenRoutePlan` from behavior head `bc790bca60267a7339103c6ed5d29b95eae3ceac`;
- `PatternRejoinSpeedPolicy` from production `main`;
- conservative comparison distance: 1,567 blocks, the longest pattern-rejoin start distance observed during the Ju 87 investigation before the owned-route clock correction.

## Method

For each aircraft:

- fighter route leg is `clamp(cruiseSpeedBps * 3.2, 130, 180)`;
- approach speed is `min(cruise * 0.82, max(stallGuard * 1.25, turnFloor))`;
- `RETURN_TO_PATTERN` target is `max(turnFloor, approach * 1.25, climbTarget)`;
- ideal reach uses the unchanged 1,800-tick / 90-second return budget;
- margin is ideal reach minus 1,567 blocks.

## Results

| Aircraft | Cruise BPS | Climb BPS | Turn floor BPS | Approach BPS | Rejoin target BPS | Ideal reach, 90 s | Margin vs 1,567 | Margin ratio | Route leg |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Bf 109 | 31.701 | 31.980 | 34.607 | 25.994 | 34.607 | 3,114.657 | 1,547.657 | 98.8% | 130 |
| F4U | 33.378 | 32.212 | 36.067 | 27.370 | 36.067 | 3,246.007 | 1,679.007 | 107.1% | 130 |
| F6F | 30.036 | 29.192 | 32.002 | 24.630 | 32.002 | 2,880.202 | 1,313.202 | 83.8% | 130 |
| Fw 190 | 33.383 | 32.216 | 35.628 | 27.374 | 35.628 | 3,206.559 | 1,639.559 | 104.6% | 130 |
| Ki-61 | 31.700 | 30.631 | 34.317 | 25.994 | 34.317 | 3,088.568 | 1,521.568 | 97.1% | 130 |
| Ki-84 | 23.330 | 20.943 | 24.931 | 19.131 | 24.931 | 2,243.813 | 676.813 | 43.2% | 130 |
| MC.202 | 28.369 | 32.421 | 30.281 | 23.263 | 32.421 | 2,917.903 | 1,350.903 | 86.2% | 130 |
| MiG-3 | 30.731 | 30.137 | 33.197 | 25.200 | 33.197 | 2,987.747 | 1,420.747 | 90.7% | 130 |
| P-40E | 28.369 | 27.839 | 30.281 | 23.263 | 30.281 | 2,725.299 | 1,158.299 | 73.9% | 130 |
| P-47N | 33.674 | 33.628 | 37.358 | 27.613 | 37.358 | 3,362.180 | 1,795.180 | 114.6% | 130 |

## Interpretation

- Every remaining energy fighter has positive ideal return margin against the conservative 1,567-block comparison distance without changing the existing 1,800-tick timeout.
- Ki-84 has the smallest margin and should receive particular artifact review, but its ideal margin is still about 677 blocks / 43.2%.
- MC.202 is the only remaining fighter in this set whose calculated rejoin target is climb-target-dominant rather than turn-floor-dominant.
- All ten route plans clamp to the minimum 130-block fighter leg, so route geometry is identical in scale; differences should primarily arise from measured control and landing behavior.
- No timeout, waypoint radius, route geometry, landing geometry, terrain, collision, stall, weapon, player-control, or separation threshold change is justified by this preflight.

## Execution order under Jolly Endurance Mode

`bf109 -> f4u -> f6f -> fw190 -> ki61 -> ki84 -> mc202 -> mig3 -> p40e -> p47n`

Each aircraft still requires one serial exact-head Windows run with route `3,2,1,0`, ordinary mission release, return, landing, final `PARKED`, summary 1/1, Gradle status 0, and crash count 0.