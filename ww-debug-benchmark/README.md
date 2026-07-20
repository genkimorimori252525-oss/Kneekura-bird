# WW Debug Benchmark

A Forge 1.20.1 companion mod for Warfare Wings / Immersive Aircraft. It complements the existing frame-by-frame WW Debug telemetry with repeatable fixed-input performance measurements.

The module intentionally uses reflection and a soft Mixin target. It does not require Warfare Wings source code and does not replace the existing autonomous-flight telemetry.

## Build

Use Java 17.

```powershell
cd ww-debug-benchmark
gradle build
```

The jar is written to `build/libs/wwdebug_benchmark-1.0.0.jar`.

## Commands

All commands require permission level 2.

```mcfunction
/wwdebug benchmark list
/wwdebug benchmark list_variants
/wwdebug benchmark run
/wwdebug benchmark run fighter
/wwdebug benchmark run attacker
/wwdebug benchmark run bomber
/wwdebug benchmark run torpedo_bomber
/wwdebug benchmark run other
/wwdebug benchmark run_variants all
/wwdebug benchmark status
/wwdebug benchmark stop
```

`run` benchmarks one representative per livery group. For example, `p51d`, `p51d_scheme1`, `p51d_scheme2`, and `p51d_scheme3` normally count as one physics profile. Use `run_variants` when the variants themselves must be checked.

Aircraft are processed in automatic batches of at most six. This avoids loading every Warfare Wings entity at once and reduces collisions and TPS spikes.

## Classification

Classification priority:

1. `data/<namespace>/aircraft/<entity>.json` → `ai.role`
2. The base aircraft JSON when the entity has a `_schemeN` suffix
3. A small registry-name fallback for older data

The exported metadata retains:

- `role`
- `faction`
- `doctrine`
- `variant_group`
- declared JSON properties
- effective runtime properties, when the installed Immersive Aircraft build exposes them

## Measurement sequence

Each aircraft receives the same post-pilot control inputs through a soft Mixin injection at the end of `VehicleEntity.tickPilot()`.

1. Straight full-throttle acceleration until speed stabilizes or the safety timeout is reached
2. Full-input sustained turn after a separate warm-up
3. 15-degree climb after a separate warm-up
4. Power-off level deceleration for a conservative stall-risk proxy
5. Full braking after a separate warm-up

The benchmark resets position, velocity, orientation, engine target, and controller smoothing between independent phases. It does not teleport the plane during a measurement phase.

## Output

Results are stored in the active world:

```text
wwdebug/benchmarks/<UTC timestamp>-<category>-<mode>/
```

Files:

- `benchmark.json` — complete result rows
- `benchmark.csv` — direct spreadsheet comparison
- `flight_profiles.json` — measured starting values for autonomous-flight tuning
- `comparison.csv` — deltas against the previous benchmark run
- `run_metadata.json` — mod versions, dimension, weather, mode, and elapsed ticks

The latest complete result set is also copied to:

```text
wwdebug/benchmarks/latest.json
```

## Relationship to existing WW Debug telemetry

Use both modes for different questions:

- Existing `/wwdebug aitest...`: validates the real mob autopilot, operation states, terrain handling, and decisions.
- `/wwdebug benchmark...`: isolates the aircraft physics under controlled inputs.

A poor autopilot result with a normal fixed-input benchmark points to control/state logic. A poor result in both modes points to the flight envelope or aircraft data.

## Important limitations

- `stall_proxy_speed_bps` is a conservative game-AI threshold, not a real aerodynamic stall definition.
- The generated `flight_profiles.json` contains recommended starting values; final controller constants still require autonomous-flight validation.
- Build and in-game validation must be performed with the same Immersive Aircraft build used by the private project.
