# Remaining bomber route qualification preflight

Date: 2026-07-25

This document is disconnected planning evidence for G10N1, G10N2, and He 111. It is **not** exact-physics qualification evidence.

## Evidence sources

- measured bomber `flight_profiles.json` from successful B-29 artifact `ww-local-route-30120521495`;
- current `FlightProfile` heavy-bomber turn-floor normalization;
- current `ProfileDrivenRoutePlan` and `PatternRejoinSpeedPolicy` behavior;
- B-29 exact-physics Run `30120521495`, where the horizontal/three-dimensional displacement between `RETURN_TO_PATTERN` start and `DOWNWIND` entry was about 1,395.6 blocks;
- conservative stress comparison of 1,567 blocks from the earlier Ju 87 investigation.

## Method

For each level bomber:

- effective turn floor is `min(measuredTurnFloor, max(stallGuard * 1.15, cruise * 0.90))`;
- approach speed is `min(cruise * 0.82, max(stallGuard * 1.25, effectiveTurnFloor))`;
- current pattern-rejoin target is `max(effectiveTurnFloor, approach * 1.25, climbTarget)`;
- ideal reach uses the unchanged 1,800-tick / 90-second return budget;
- bomber route leg is `clamp(cruise * 3.1, 110, 145)`.

## Results

| Aircraft | Cruise BPS | Climb BPS | Raw turn BPS | Effective turn BPS | Approach BPS | Rejoin target BPS | Ideal reach, 90 s | Margin vs B-29 1,395.6 | Margin vs 1,567 | Route leg |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| G10N1 | 18.016 | 17.685 | 22.033 | 16.215 | 14.773 | 18.467 | 1,662.015 | 266.4 / 19.1% | 95.0 / 6.1% | 110 |
| G10N2 | 18.867 | 17.707 | 22.324 | 16.980 | 15.471 | 19.338 | 1,740.456 | 344.9 / 24.7% | 173.5 / 11.1% | 110 |
| He 111 | 18.202 | 16.338 | 20.567 | 16.382 | 14.926 | 18.657 | 1,679.165 | 283.6 / 20.3% | 112.2 / 7.2% | 110 |

## Interpretation

- All three remaining bombers have positive ideal return margin without changing the existing 1,800-tick timeout.
- G10N1 has the narrowest conservative margin and should receive the closest artifact review.
- All three use the minimum 110-block bomber route leg, reducing route-driven displacement relative to the fighter and attacker plans.
- G10N1 and G10N2 are much larger than B-29 in wingspan and may expose landing-pattern or collision-envelope behavior even when the pure travel budget is sufficient. That risk must be measured, not pre-emptively solved by increasing thresholds.
- No timeout, waypoint radius, route geometry, landing geometry, terrain, collision, stall, weapon, player-control, or separation threshold change is justified by this preflight.

## Planned execution

After the remaining energy fighters complete:

`g10n1 -> g10n2 -> he111`

Each aircraft requires one serial exact-head Windows run with route `3,2,1,0`, ordinary mission release, return, landing, final `PARKED`, summary 1/1, Gradle status 0, and crash count 0.