# Measured flight-profile provenance for all 24 base aircraft

Recorded: 2026-07-26 (Asia/Tokyo)

## Why this record exists

`AutopilotProfileRegistry.locateProfileFile` resolves measured profiles from, in order:

1. `<config>/warfare_wings/flight_profiles.json`;
2. otherwise the newest `flight_profiles.json` found under `<world>/wwdebug/benchmarks/**`.

`ww-debug-benchmark/build.gradle` stages the tracked fixture into location 1 before every
headless GameTest, so the fixture is the only profile source that a clean checkout can
reproduce. Until this change the fixture held **fighters only (14 keys)**.

`AutonomousFlightManager` (lines 55-65) refuses to open an autopilot session when no measured
profile resolves, emitting `missing_measured_flight_profile` and `FlightPhase.ABORTED`.
Consequently every non-fighter qualification depended on a profile that existed **only inside
expiring CI artifacts**, not in version control. Seven already-accepted qualifications
(G4M, IL-2, B-17, B-29, Ju 87, SBD, D4Y) rested on that unreproducible evidence.

This change commits the measured profiles for the remaining 10 aircraft so that all 24 base
aircraft resolve a profile from a clean checkout.

## Source of each profile

Fighters (14) — unchanged values, carried over from
`validated_fighter_profiles-20260720-141003.json` (measured 2026-07-20 14:10:03):

`a6m`, `bf109`, `f4u`, `f6f`, `fw190`, `ki61`, `ki84`, `mc202`, `mig3`, `p40e`, `p47n`,
`p51d`, `spitfire`, `yak3`.

Non-fighters (10) — recovered from the CI artifacts of the runs listed below. Each artifact
contained both `run-gametest/config/warfare_wings/flight_profiles.json` and the corresponding
`run-gametest/world/wwdebug/benchmarks/<session>/flight_profiles.json`.

| Aircraft | Role | Benchmark session | Recovered from run |
| --- | --- | --- | --- |
| `warfare_wings:g4m` | torpedo_bomber | `20260724-174852-torpedo_bomber-representatives` | 30113770224 |
| `warfare_wings:il2` | attacker | `20260724-180212-attacker-representatives` | 30115029120 |
| `warfare_wings:b17` | bomber | `20260724-182204-bomber-representatives` | 30115815404 |
| `warfare_wings:b29` | bomber | `20260724-193649-bomber-representatives` | 30120521495 |
| `warfare_wings:g10n1` | bomber | `20260724-182204-bomber-representatives` | 30115815404 |
| `warfare_wings:g10n2` | bomber | `20260724-182204-bomber-representatives` | 30115815404 |
| `warfare_wings:he111` | bomber | `20260724-182204-bomber-representatives` | 30115815404 |
| `warfare_wings:ju87` | attacker | `20260725-065111-attacker-representatives` | 30147903349 |
| `warfare_wings:sbd` | attacker | `20260725-070543-attacker-representatives` | 30148395384 |
| `warfare_wings:d4y` | attacker | `20260725-071435-attacker-representatives` | 30148766789 |

The bomber session measured all five bombers together and the attacker sessions measured all
four attackers together, so `g10n1`, `g10n2` and `he111` already had measured profiles even
though they have not yet completed a route qualification.

## Integrity checks performed before committing

- Every one of the 10 profiles appeared in **4 to 8 independent artifact copies**
  (`config` and `world` copies across several runs). All copies were compared field by field:
  **0 conflicting value sets**.
- All five fields required by `AutopilotProfileRegistry.parse` — `stall_guard_speed_bps`,
  `cruise_speed_bps`, `climb_target_speed_bps`, `turn_speed_floor_bps`,
  `measured_top_speed_bps` — are present and finite for all 24 entries: **0 incomplete**.
- Every recovered `role` is one of `bomber`, `attacker`, `torpedo_bomber`, so
  `FlightProfile.supportsAutonomousFlight()` returns true for all 24.
- Resulting role split is **14 fighter / 5 bomber / 4 attacker / 1 torpedo_bomber**, matching
  the base-aircraft inventory in Issue #7.

## Values that were deliberately NOT changed

- No measured number was edited, rounded, or recomputed. Values are byte-equal to the
  artifacts they came from.
- The recovered non-fighter profiles carry `"doctrine": "unknown"` exactly as measured.
  Assigning real doctrines (`level_bomber`, `dive_bomber`, `ground_attacker`,
  `torpedo_attack`) is a separate behavioral change and is not part of this commit.
- No flight-control, timeout, route geometry, waypoint radius, landing geometry, firing gate,
  terrain, collision, player-control, or minimum-separation rule was touched.

## Follow-up this enables

- Non-fighter route qualifications no longer need a live measurement phase before the route
  scenario, because the profile is staged from version control.
- `g10n1`, `g10n2` and `he111` can be qualified directly.
- The seven previously artifact-dependent qualifications become reproducible from a clean
  checkout.
