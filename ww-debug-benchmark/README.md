# WW Debug Benchmark and Autonomous Flight Validation

A Forge 1.20.1 companion mod for Warfare Wings / Immersive Aircraft. It provides:

- repeatable fixed-input aircraft performance measurements;
- measured `flight_profiles.json` output;
- non-combat autonomous flight for mob-piloted fighters;
- per-tick, per-aircraft JSONL decision telemetry;
- a fast deterministic mission simulator;
- a headless real-physics Forge GameTest;
- sequential full-mission validation from takeoff through complete stop.

The module uses reflection and a soft Mixin target, so normal compilation does not require a compile-time dependency on Warfare Wings or Immersive Aircraft.

## Build and fast simulation

Use Java 17.

```powershell
cd ww-debug-benchmark
gradle build
```

`build` compiles the mod and runs the deterministic pre-flight simulator. Its report is written to:

```text
build/reports/flight-simulation/report.json
```

Without an external profile file, CI uses a synthetic boundary matrix representing a light turn fighter, an energy fighter, and a heavy fighter. Each profile is tested under nominal, weak-engine, turn-energy-loss, and long-brake conditions.

To run the same simulator against the measured profiles from Minecraft:

```powershell
gradle runFlightSimulation -PflightProfiles="C:\path\to\flight_profiles.json"
```

The simulator is a fast logic and envelope check. It checks phase reachability, timeouts, measured speed gates, stall recovery, landing progression, and complete stop. It does not replace the real Immersive Aircraft physics test.

The jar is written to `build/libs/wwdebug_benchmark-1.0.0.jar`.

## Headless real-physics GameTest

The Forge GameTest server runs the real Minecraft server, real Warfare Wings entities, real Immersive Aircraft physics, the real `tickPilot()` path, and the autonomous-flight Mixin without opening a game window.

Place the exact runtime jars in:

```text
ww-debug-benchmark/flight-test-mods/
├─ immersive_aircraft-1.3.3+1.20.1-forge.jar
└─ warfare_wings-1.1.4-1.20.1-forge.jar
```

These are production-obfuscated mod jars. The build loads them as ForgeGradle `fg.deobf` dependencies so they are remapped for the GameTest development runtime. They must not be copied directly into `run-gametest/mods`.

Run the A6M smoke test:

```powershell
gradle runGameTestServer -PflightTestAircraft=warfare_wings:a6m
```

Run every representative fighter sequentially:

```powershell
gradle runGameTestServer -PflightTestAircraft=all
```

An existing measured profile can be supplied:

```powershell
gradle runGameTestServer `
  -PflightTestAircraft=all `
  -PflightProfiles="C:\path\to\flight_profiles.json"
```

If no profile is supplied, the headless test performs the real fixed-input fighter benchmark first, installs the generated `flight_profiles.json`, reloads the AI profiles, and only then starts autonomous flight.

The GameTest automatically:

1. creates a 29-block-wide, approximately 930-block-long runway;
2. clears the immediate aircraft corridor;
3. measures fighter profiles when necessary;
4. spawns the selected fighter and a mob pilot;
5. runs startup, takeoff, climb, cruise, both turns, stall recovery, return, landing, and braking;
6. reads the validation summary and per-aircraft telemetry;
7. requires `PARKED`, full mission completion, and a final stop inside the runway corridor;
8. returns a non-zero process exit code on failure.

A headless CI run is considered successful only when all of the following exist and agree:

- no crash report;
- a completed `validation-summary-*.json`;
- every requested aircraft marked passed;
- a measured or staged `flight_profiles.json`;
- per-aircraft autonomous-flight JSONL telemetry.

GitHub Actions runs the A6M headless smoke test on pull requests. The `WW Headless Flight GameTest` workflow can be started manually with `aircraft=all` for the complete fighter suite. Runtime mods are downloaded transiently from their exact official Modrinth versions and are not uploaded as workflow artifacts.

## Fixed-input benchmark commands

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

## Autonomous-flight commands

```mcfunction
/wwdebug autopilot profiles reload
/wwdebug autopilot profiles source
/wwdebug autopilot status
/wwdebug autopilot logs
/wwdebug autopilot validate fighter warfare_wings:a6m
/wwdebug autopilot validate fighters
/wwdebug autopilot validate status
/wwdebug autopilot validate stop
```

### Activation rule

Autonomous flight is applied only when all of the following are true:

- the vehicle is an Immersive Aircraft airplane;
- the controlling passenger is a `Mob`;
- the controlling passenger is not a player;
- a measured fighter profile can be resolved for the aircraft.

Armor stands used by the fixed-input benchmark do not activate the autonomous-flight path. Player-controlled aircraft are never overwritten.

### Validation mission

The full validation mission is:

1. engine startup while holding brakes;
2. takeoff roll until measured rotate speed;
3. rotation and climb to safe altitude;
4. outbound cruise;
5. left turn;
6. stabilization cruise;
7. right turn;
8. controlled stall entry;
9. stall recovery;
10. return to a home-relative landing pattern;
11. downwind, base, final, and flare;
12. touchdown, explicit braking, and complete stop.

`validate fighters` discovers one representative per fighter livery group and runs them sequentially from the command source position and heading. Stand at the runway start while facing the intended takeoff direction. Use a long, flat, obstacle-free runway for manual validation.

## Flight profile loading

The autonomous controller does not estimate aircraft performance from raw stats.

Profile loading priority:

1. `config/warfare_wings/flight_profiles.json`;
2. the newest `flight_profiles.json` under the active world's `wwdebug/benchmarks/` directory.

If no measured profile is found, the autonomous controller remains disabled for that aircraft and writes a rejection event instead of guessing.

## Autonomous-flight logs

Logs are stored in the active world:

```text
wwdebug/autopilot/<UTC timestamp>/
├─ combined.jsonl
└─ aircraft/
   └─ <namespace>-<entity>-<aircraft UUID>.jsonl
```

Every frame includes enough information to reconstruct why the AI acted and how the aircraft responded:

- aircraft entity ID, UUID, name, pilot ID, and pilot UUID;
- phase, phase ticks, mission ticks, previous transition reason, current action reason;
- position, velocity, aircraft forward vector, desired direction, home position, runway direction;
- total, horizontal, and vertical speed in blocks per second;
- scalar and vector acceleration and per-frame displacement;
- movement yaw and human-readable movement direction;
- aircraft yaw, pitch, roll, and available angular rates;
- altitude above ground and ground-contact state;
- engine power, actual engine target, commanded engine target, and available fuel utilization;
- target speed, target altitude, heading error, altitude error, and speed error;
- final `x`, `y`, and `z` control inputs;
- stall risk, terrain risk, and any safety override;
- all measured profile thresholds used for the decision.

Reflective values that do not exist in the installed aircraft build are marked unavailable instead of disabling flight control.

The combined file is useful for comparing aircraft. The UUID-specific file isolates one aircraft even when several entities share the same model.

Validation also writes:

```text
wwdebug/autopilot/validation-summary-<epoch>.json
```

The summary records pass/fail, final phase, reason, elapsed ticks, mission ticks, aircraft UUID, variant group, and doctrine for every tested fighter.

## Fixed-input measurement sequence

Each benchmark aircraft receives the same post-pilot control inputs through a soft Mixin injection at the end of `VehicleEntity.tickPilot()`.

1. Straight full-throttle acceleration until speed stabilizes or the safety timeout is reached
2. Full-input sustained turn after a separate warm-up
3. 15-degree climb after a separate warm-up
4. Power-off level deceleration for a conservative stall-risk proxy
5. Full braking after a separate warm-up

The benchmark resets position, velocity, orientation, engine target, and controller smoothing between independent phases. It does not teleport the plane during a measurement phase.

## Benchmark output

Results are stored in:

```text
wwdebug/benchmarks/<UTC timestamp>-<category>-<mode>/
```

Files:

- `benchmark.json` — complete result rows
- `benchmark.csv` — direct spreadsheet comparison
- `flight_profiles.json` — measured autonomous-flight starting values
- `comparison.csv` — deltas against the previous valid benchmark run
- `run_metadata.json` — mod versions, dimension, weather, mode, and elapsed ticks

## Important limitations

- Terrain verifier `selected_log_parse_and_identity_checks_passed` means only that its selected log passed the implemented parsing, selection, summary and UUID checks. It does not prove overall safety, that all telemetry rows were emitted, or that the log and summary came from the same run. The verifier's exit status and overall result must also be checked; use a unique output path because a failed output write can leave an older result.
- The deterministic simulator is a pre-flight logic model, not an exact reimplementation of Minecraft physics.
- `stall_proxy_speed_bps` is a conservative game-AI threshold, not a real aerodynamic stall definition.
- The generated profile provides measured starting values; controller constants still require autonomous-flight validation.
- The initial landing test assumes the generated flat runway. General terrain avoidance and landing-site discovery remain later work.
- Bomber, attacker, torpedo-bomber, combat, weapon, target-selection, and formation policies are not part of this phase.
- Build and in-game validation must use the same Immersive Aircraft and Warfare Wings build used for the measured profiles.
