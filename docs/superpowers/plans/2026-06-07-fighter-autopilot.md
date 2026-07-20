# Fighter Autopilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an attack-free autonomous fighter flight AI for mob-piloted Warfare Wings fighters, using the exported telemetry to stabilize takeoff, climb, cruise, turning, terrain avoidance, and stall recovery.

**Architecture:** Keep the existing mob pilot mount path and `AirplaneEntity.tickMobPilot` entry point. Split flight intent, control law, profile estimation, and debug snapshots out of the current large `AirplaneAutopilot` class so each part can be compiled and tuned independently. Do not fire weapons in this plan.

**Tech Stack:** Java 17, Minecraft Forge/Architectury 1.20.1 source at `C:\Users\genki\Downloads\Airforce\source_repo`, debug mod at `C:\Users\genki\Downloads\warfare_wings-1.1.4-1.20.1-forge\ww-debug`, Gradle.

---

## Confirmed Baseline

- Exported log: `C:\Users\genki\AppData\Roaming\.minecraft\wwdebug_telemetry.json`
- `aiTestCount`: 14
- All sessions: 2400 frames
- All sessions: `pilotPresent=true` and `pilotPassenger=true`
- New telemetry fields are present: `inputs`, `smoothedInputs`, `canTurnOnEngine`, `canBoost`, `boostTicks`, `weaponSlotCount`, `weaponCount`, orientation vectors, fuel state, inventory state
- Fighters that stayed airborne for the full 2400 ticks: `a6m`, `fw190`, `ki61`, `mc202`, `mig3`, `p40e`, `p47n`, `spitfire`
- Fighters that landed and reached `disembark_ready`: `bf109`, `f4u`, `f6f`, `ki84`, `p51d`, `yak3`

## Acceptance Criteria

- `/wwdebug aitestfighters 2400` records 14 fighter sessions.
- No fighter reaches `immersive_aircraft.operation.disembark_ready` during the 2400 tick autonomous flight test unless an explicit return or landing mode is enabled.
- Each fighter has at least 2000 airborne frames after the takeoff phase.
- Each fighter avoids long low-speed unrecovered flight: no more than 80 consecutive airborne ticks below its computed stall guard speed.
- Each fighter maintains terrain clearance above its computed safe altitude after climb, except during takeoff roll and rotation.
- `aiDecision` appears in exported debug frames and includes phase, desired direction, altitude error, speed error, terrain risk, stall risk, and clamp reasons.
- Weapon firing remains disabled. `firePilotWeapons` is not called by the new attack-free patrol path.

## File Structure

### Source repo

- Modify: `C:\Users\genki\Downloads\Airforce\source_repo\common\src\main\java\immersive_aircraft\entity\AirplaneEntity.java`
  - Keep `tickMobPilot(Entity pilot)` as the integration point.
  - Add a small public debug snapshot accessor for the debug mod.

- Modify: `C:\Users\genki\Downloads\Airforce\source_repo\common\src\main\java\immersive_aircraft\entity\ai\AirplaneAutopilot.java`
  - Keep pilot eligibility, home reference, target perception, and operation state translation.
  - Route fighter patrol operation states into the new flight planner and controller.
  - Keep existing attack logic dormant for this plan.

- Create: `C:\Users\genki\Downloads\Airforce\source_repo\common\src\main\java\immersive_aircraft\entity\ai\FighterFlightProfile.java`
  - Computes per-aircraft flight limits from `VehicleStat`, aircraft doctrine, and observed telemetry ranges.

- Create: `C:\Users\genki\Downloads\Airforce\source_repo\common\src\main\java\immersive_aircraft\entity\ai\FighterFlightContext.java`
  - Immutable per-tick snapshot of position, velocity, orientation vectors, speed, altitude, terrain clearance, engine state, and operation state.

- Create: `C:\Users\genki\Downloads\Airforce\source_repo\common\src\main\java\immersive_aircraft\entity\ai\FighterFlightIntent.java`
  - Immutable desired flight target: direction, throttle target, altitude target, speed target, and phase.

- Create: `C:\Users\genki\Downloads\Airforce\source_repo\common\src\main\java\immersive_aircraft\entity\ai\FighterControlOutput.java`
  - Immutable result sent to `plane.setInputs(x, y, z)`.

- Create: `C:\Users\genki\Downloads\Airforce\source_repo\common\src\main\java\immersive_aircraft\entity\ai\FighterFlightController.java`
  - Converts `FighterFlightIntent` and `FighterFlightContext` into bounded `x/y/z` controls.

- Create: `C:\Users\genki\Downloads\Airforce\source_repo\common\src\main\java\immersive_aircraft\entity\ai\FighterPatrolPlanner.java`
  - Attack-free state machine: startup, takeoff, rotate, climb, patrol, turn, recovery.

- Create: `C:\Users\genki\Downloads\Airforce\source_repo\common\src\main\java\immersive_aircraft\entity\ai\FighterAutopilotDebugSnapshot.java`
  - Exportable debug record for the debug mod.

### Debug mod

- Modify: `C:\Users\genki\Downloads\warfare_wings-1.1.4-1.20.1-forge\ww-debug\src\main\java\com\wwdebug\collector\AiTelemetryCollector.java`
  - Read `getMobAutopilotDebugSnapshot` through reflection.
  - Add the result as `aiDecision` on each frame.

## Design Decisions

- Prefer a new attack-free patrol path over patching combat tactics first. The current logs show the main problem is flight stability and premature landing, not weapon timing.
- Keep `AirplaneAutopilot` as the owner of lifecycle state. New classes handle calculation only.
- Do not use raw pitch angles as the main control signal because Minecraft rotations wrap and can exceed intuitive aircraft ranges. Use forward/up/right vectors and velocity instead.
- Keep throttle control through existing `movementY` behavior. The controller sets `movementY` to `1`, `0`, or `-1` based on target engine power error.
- Cap roll and pitch control indirectly through input clamps. The AI cannot command physical angles directly; it can only feed `setInputs`.
- Use doctrine as behavior flavor:
  - `TURN_FIGHTER`: tighter patrol turns, lower climb bias, higher willingness to hold level turns.
  - `ENERGY_FIGHTER`: wider turns, higher altitude target, stronger speed recovery before hard turns.

## Task 1: Add Flight Profile and Context Types

**Files:**
- Create: `C:\Users\genki\Downloads\Airforce\source_repo\common\src\main\java\immersive_aircraft\entity\ai\FighterFlightProfile.java`
- Create: `C:\Users\genki\Downloads\Airforce\source_repo\common\src\main\java\immersive_aircraft\entity\ai\FighterFlightContext.java`
- Modify only if needed for imports: `C:\Users\genki\Downloads\Airforce\source_repo\common\src\main\java\immersive_aircraft\entity\ai\AirplaneAutopilot.java`

- [ ] Step 1: Create `FighterFlightProfile` as an immutable record.

Required fields:

```java
record FighterFlightProfile(
        double stallGuardSpeed,
        double cruiseSpeed,
        double climbSpeed,
        double patrolAltitude,
        double safeAltitude,
        double maxTurnInput,
        double maxPitchInput,
        boolean turnFighter
) {
}
```

- [ ] Step 2: Add `from(AirplaneEntity plane, boolean turnFighter)` factory.

Use these initial formulas:

```java
double engine = plane.getProperties().get(VehicleStat.ENGINE_SPEED);
double lift = plane.getProperties().get(VehicleStat.LIFT);
double pitch = plane.getProperties().get(VehicleStat.PITCH_SPEED);
double yaw = plane.getProperties().get(VehicleStat.YAW_SPEED);
double mass = Math.max(0.35, plane.getProperties().get(VehicleStat.MASS));
double cruiseSpeed = Mth.clamp(0.55 + engine * 2.2 + lift * 0.02 - mass * 0.02, 0.60, 1.35);
double stallGuardSpeed = Mth.clamp(cruiseSpeed * 0.45, 0.28, 0.65);
double climbSpeed = Mth.clamp(cruiseSpeed * 0.82, 0.50, 1.05);
double safeAltitude = turnFighter ? 45.0 : 60.0;
double patrolAltitude = turnFighter ? 95.0 : 135.0;
double maxTurnInput = Mth.clamp(0.35 + yaw * 3.0, 0.35, turnFighter ? 0.90 : 0.72);
double maxPitchInput = Mth.clamp(0.25 + pitch * 2.0, 0.28, 0.75);
```

- [ ] Step 3: Create `FighterFlightContext` with position, velocity, forward, right, up, speed, horizontal speed, ground clearance, on-ground flag, engine target, engine power, and tick count.

- [ ] Step 4: Compile.

Run:

```powershell
cd C:\Users\genki\Downloads\Airforce\source_repo
.\gradlew.bat --no-daemon :common:compileJava
```

Expected: `BUILD SUCCESSFUL`.

## Task 2: Add Attack-Free Flight Intent and Control Output

**Files:**
- Create: `C:\Users\genki\Downloads\Airforce\source_repo\common\src\main\java\immersive_aircraft\entity\ai\FighterFlightIntent.java`
- Create: `C:\Users\genki\Downloads\Airforce\source_repo\common\src\main\java\immersive_aircraft\entity\ai\FighterControlOutput.java`

- [ ] Step 1: Create `FighterFlightIntent`.

Required fields:

```java
record FighterFlightIntent(
        Phase phase,
        Vec3 desiredDirection,
        double targetAltitude,
        double targetSpeed,
        float throttleTarget
) {
    enum Phase {
        STARTUP,
        TAKEOFF_ROLL,
        ROTATE,
        CLIMB,
        PATROL,
        TURN,
        RECOVER
    }
}
```

- [ ] Step 2: Create `FighterControlOutput`.

Required fields:

```java
record FighterControlOutput(
        float x,
        float y,
        float z,
        double altitudeError,
        double speedError,
        boolean terrainRisk,
        boolean stallRisk,
        String clampReason
) {
}
```

- [ ] Step 3: Compile.

Run:

```powershell
cd C:\Users\genki\Downloads\Airforce\source_repo
.\gradlew.bat --no-daemon :common:compileJava
```

Expected: `BUILD SUCCESSFUL`.

## Task 3: Implement FighterFlightController

**Files:**
- Create: `C:\Users\genki\Downloads\Airforce\source_repo\common\src\main\java\immersive_aircraft\entity\ai\FighterFlightController.java`

- [ ] Step 1: Implement control conversion.

Core behavior:

```java
double turnError = -intent.desiredDirection().normalize().dot(context.right().normalize());
double climbError = intent.targetAltitude() - context.groundClearance();
double speedError = intent.targetSpeed() - context.speed();
boolean terrainRisk = context.groundClearance() < profile.safeAltitude();
boolean stallRisk = !context.onGround() && context.speed() < profile.stallGuardSpeed();

float x = (float) Mth.clamp(turnError * 1.35, -profile.maxTurnInput(), profile.maxTurnInput());
float z = (float) Mth.clamp(climbError * -0.012 - context.velocity().y * 0.65, -profile.maxPitchInput(), profile.maxPitchInput());
float y = throttleStep(intent.throttleTarget(), context.engineTarget());
```

Emergency priority:

```java
if (terrainRisk) {
    z = (float) -profile.maxPitchInput();
    y = 1.0f;
}
if (stallRisk) {
    x *= 0.45f;
    z = Math.max(z, 0.15f);
    y = 1.0f;
}
```

Important: preserve sign conventions from observed logs:

- `x`: left/right turn input
- `y`: engine target up/down input
- `z`: push/pull pitch input as used by existing aircraft physics

- [ ] Step 2: Add `throttleStep(float target, float current)`.

Required behavior:

```java
if (target - current > 0.06f) return 1.0f;
if (target - current < -0.06f) return -1.0f;
return 0.0f;
```

- [ ] Step 3: Compile.

Run:

```powershell
cd C:\Users\genki\Downloads\Airforce\source_repo
.\gradlew.bat --no-daemon :common:compileJava
```

Expected: `BUILD SUCCESSFUL`.

## Task 4: Implement FighterPatrolPlanner

**Files:**
- Create: `C:\Users\genki\Downloads\Airforce\source_repo\common\src\main\java\immersive_aircraft\entity\ai\FighterPatrolPlanner.java`

- [ ] Step 1: Add state fields.

Required mutable fields:

```java
private FighterFlightIntent.Phase phase = FighterFlightIntent.Phase.STARTUP;
private int phaseTicks;
private int patrolTurnSign = 1;
```

- [ ] Step 2: Add `tick(FighterFlightContext context, FighterFlightProfile profile, Vec3 homePoint, Vec3 homeForward)`.

Phase transitions:

- `STARTUP` to `TAKEOFF_ROLL`: engine target reaches `0.85` or phase exceeds 80 ticks.
- `TAKEOFF_ROLL` to `ROTATE`: horizontal speed reaches `profile.climbSpeed() * 0.72`.
- `ROTATE` to `CLIMB`: ground clearance exceeds `8`.
- `CLIMB` to `PATROL`: ground clearance exceeds `profile.patrolAltitude() * 0.75`.
- Any airborne phase to `RECOVER`: terrain risk or stall risk.
- `RECOVER` back to `CLIMB`: speed exceeds `profile.climbSpeed()` and ground clearance exceeds `profile.safeAltitude()`.

- [ ] Step 3: Define patrol geometry.

Use home-relative orbit without returning to base:

```java
Vec3 offset = context.position().subtract(homePoint);
Vec3 radial = new Vec3(offset.x, 0.0, offset.z);
Vec3 tangent = radial.lengthSqr() > 16.0
        ? new Vec3(-radial.z, 0.0, radial.x).normalize().scale(patrolTurnSign)
        : homeForward;
Vec3 desired = tangent.add(0.0, altitudeBias, 0.0).normalize();
```

Doctrine tuning:

- Turn fighters: orbit radius target around 95 blocks, target speed near cruise.
- Energy fighters: orbit radius target around 145 blocks, target altitude higher, avoid tight turn below climb speed.

- [ ] Step 4: Return `FighterFlightIntent` with no weapon or target fields.

- [ ] Step 5: Compile.

Run:

```powershell
cd C:\Users\genki\Downloads\Airforce\source_repo
.\gradlew.bat --no-daemon :common:compileJava
```

Expected: `BUILD SUCCESSFUL`.

## Task 5: Wire New Planner into AirplaneAutopilot

**Files:**
- Modify: `C:\Users\genki\Downloads\Airforce\source_repo\common\src\main\java\immersive_aircraft\entity\ai\AirplaneAutopilot.java`

- [ ] Step 1: Add fields.

```java
private final FighterPatrolPlanner fighterPatrolPlanner = new FighterPatrolPlanner();
private final FighterFlightController fighterFlightController = new FighterFlightController();
private FighterAutopilotDebugSnapshot lastFighterDebugSnapshot = FighterAutopilotDebugSnapshot.empty();
```

- [ ] Step 2: Add a fighter-only branch in `tick(Entity pilot)` after `PilotContext context` is built and before combat tactic selection.

Condition:

```java
if (plane.getAircraftArchetype() == AircraftArchetype.FIGHTER && context.target() == null) {
    tickAttackFreeFighterPatrol(context);
    return;
}
```

- [ ] Step 3: Implement `tickAttackFreeFighterPatrol(PilotContext context)`.

Required sequence:

```java
FighterFlightProfile profile = FighterFlightProfile.from(plane, context.profile().turnFighter());
FighterFlightContext flightContext = FighterFlightContext.from(plane, currentOperationState, operationStateTicks);
FighterFlightIntent intent = fighterPatrolPlanner.tick(flightContext, profile, homePoint, homeForward);
FighterControlOutput output = fighterFlightController.control(flightContext, profile, intent);
plane.setInputs(output.x(), output.y(), output.z());
currentObjective = Objective.GAIN_ENERGY;
currentState = output.stallRisk() || output.terrainRisk() ? FlightState.RECOVER : FlightState.CRUISE;
currentOperationState = mapPhaseToOperationState(intent.phase());
lastFighterDebugSnapshot = FighterAutopilotDebugSnapshot.from(intent, output, profile);
```

- [ ] Step 4: Add `mapPhaseToOperationState`.

Mapping:

- `STARTUP` -> `STARTUP`
- `TAKEOFF_ROLL` -> `TAKEOFF_ROLL`
- `ROTATE` -> `ROTATE`
- `CLIMB` -> `INITIAL_CLIMB`
- `PATROL` -> `MISSION_CRUISE`
- `TURN` -> `MISSION_CRUISE`
- `RECOVER` -> `MISSION_CRUISE`

- [ ] Step 5: Keep weapons disabled in this path.

Do not create any call to `firePilotWeapons` from `tickAttackFreeFighterPatrol`.

- [ ] Step 6: Compile.

Run:

```powershell
cd C:\Users\genki\Downloads\Airforce\source_repo
.\gradlew.bat --no-daemon :common:compileJava
```

Expected: `BUILD SUCCESSFUL`.

## Task 6: Add Debug Snapshot Export

**Files:**
- Create: `C:\Users\genki\Downloads\Airforce\source_repo\common\src\main\java\immersive_aircraft\entity\ai\FighterAutopilotDebugSnapshot.java`
- Modify: `C:\Users\genki\Downloads\Airforce\source_repo\common\src\main\java\immersive_aircraft\entity\ai\AirplaneAutopilot.java`
- Modify: `C:\Users\genki\Downloads\Airforce\source_repo\common\src\main\java\immersive_aircraft\entity\AirplaneEntity.java`

- [ ] Step 1: Create `FighterAutopilotDebugSnapshot`.

Required fields:

```java
record FighterAutopilotDebugSnapshot(
        String phase,
        double desiredX,
        double desiredY,
        double desiredZ,
        double targetAltitude,
        double targetSpeed,
        float throttleTarget,
        double altitudeError,
        double speedError,
        boolean terrainRisk,
        boolean stallRisk,
        String clampReason
) {
    static FighterAutopilotDebugSnapshot empty() {
        return new FighterAutopilotDebugSnapshot("none", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0f, 0.0, 0.0, false, false, "none");
    }
}
```

- [ ] Step 2: Add `AirplaneAutopilot.getDebugSnapshotForDebug()`.

Return `lastFighterDebugSnapshot`.

- [ ] Step 3: Add `AirplaneEntity.getMobAutopilotDebugSnapshot()`.

Return `mobAutopilot.getDebugSnapshotForDebug()`.

- [ ] Step 4: Compile.

Run:

```powershell
cd C:\Users\genki\Downloads\Airforce\source_repo
.\gradlew.bat --no-daemon :common:compileJava
```

Expected: `BUILD SUCCESSFUL`.

## Task 7: Update ww-debug to Record aiDecision

**Files:**
- Modify: `C:\Users\genki\Downloads\warfare_wings-1.1.4-1.20.1-forge\ww-debug\src\main\java\com\wwdebug\collector\AiTelemetryCollector.java`

- [ ] Step 1: Add reflective snapshot extraction.

Call `getMobAutopilotDebugSnapshot` on the aircraft. Convert Java record accessors to a `Map<String, Object>` using reflection.

- [ ] Step 2: Add `aiDecision` to `AiFrame.toMap()`.

Required JSON key:

```java
map.put("aiDecision", aiDecision);
```

- [ ] Step 3: Compile debug mod.

Run:

```powershell
cd C:\Users\genki\Downloads\warfare_wings-1.1.4-1.20.1-forge\ww-debug
& 'C:\Users\genki\.gradle\wrapper\dists\gradle-8.13-bin\5xuhj0ry160q40clulazy9h7d\gradle-8.13\bin\gradle.bat' --no-daemon compileJava -x test
```

Expected: `BUILD SUCCESSFUL`.

## Task 8: Build and Package

**Files:**
- Build output from source repo
- Debug output: `C:\Users\genki\Downloads\warfare_wings-1.1.4-1.20.1-forge\制作過程ボックスWW\ww-debug-1.0.0.jar`

- [ ] Step 1: Build source repo common and forge artifacts.

Run:

```powershell
cd C:\Users\genki\Downloads\Airforce\source_repo
.\gradlew.bat --no-daemon :common:compileJava :forge:build
```

Expected: `BUILD SUCCESSFUL`.

- [ ] Step 2: Build debug jar.

Run:

```powershell
cd C:\Users\genki\Downloads\warfare_wings-1.1.4-1.20.1-forge\ww-debug
& 'C:\Users\genki\.gradle\wrapper\dists\gradle-8.13-bin\5xuhj0ry160q40clulazy9h7d\gradle-8.13\bin\gradle.bat' --no-daemon jar
```

Expected: `BUILD SUCCESSFUL`.

- [ ] Step 3: Copy debug jar.

Run:

```powershell
Copy-Item -LiteralPath 'C:\Users\genki\Downloads\warfare_wings-1.1.4-1.20.1-forge\ww-debug\build\libs\ww-debug-1.0.0.jar' -Destination 'C:\Users\genki\Downloads\warfare_wings-1.1.4-1.20.1-forge\制作過程ボックスWW\ww-debug-1.0.0.jar' -Force
```

Expected: file timestamp updates.

## Task 9: In-Game Validation

**Files:**
- Exported log: `C:\Users\genki\AppData\Roaming\.minecraft\wwdebug_telemetry.json`

- [ ] Step 1: Run A6M single-aircraft validation.

Commands:

```mcfunction
/wwdebug clear
/wwdebug aitest a6m 2400
/wwdebug export
```

Expected:

- `aiTestCount` is `1`.
- A6M has 2400 frames.
- `aiDecision.phase` transitions through startup, takeoff, climb, and patrol.
- No `disembark_ready` state appears.
- `terrainRisk` and `stallRisk` are false for most cruise frames.

- [ ] Step 2: Run all-fighter validation.

Commands:

```mcfunction
/wwdebug clear
/wwdebug aitestfighters 2400
/wwdebug export
```

Expected:

- `aiTestCount` is `14`.
- Every session has 2400 frames.
- Every session has `pilotPresent=true` and `pilotPassenger=true`.
- No session reaches `disembark_ready`.
- Every session includes `aiDecision`.

- [ ] Step 3: Compare old and new summaries.

Use a local Python summary script against `wwdebug_telemetry.json` and report:

- airborne frames
- final operation state
- max ground clearance
- average speed
- longest stall-risk streak
- longest terrain-risk streak
- whether `aiDecision` is present

## Risk Controls

- Keep attack out of scope. No new firing path.
- Keep public gameplay behavior outside mob-piloted fighter AI unchanged.
- Leave bomber and non-fighter aircraft on the existing path.
- Make every calculation class compile independently before wiring.
- Keep debug export reflective so the debug mod can fail open if the core snapshot method is absent.
- Tune using telemetry after first build rather than trying to solve all aircraft perfectly in one edit.

## Execution Order

1. Add profile/context records.
2. Add intent/output records.
3. Add controller.
4. Add planner.
5. Wire fighter-only attack-free patrol into `AirplaneAutopilot`.
6. Add debug snapshot accessor.
7. Update `ww-debug` export.
8. Build source and debug jars.
9. Run A6M validation.
10. Run all-fighter validation.
11. Tune constants once from the new exported telemetry.
