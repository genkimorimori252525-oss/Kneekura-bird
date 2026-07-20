from pathlib import Path
import re


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def regex_once(text: str, pattern: str, replacement: str, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE | re.DOTALL)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return updated


root = Path(__file__).resolve().parents[1]
manager_path = root / "ww-debug-benchmark/src/main/java/com/wwdebug/benchmark/BenchmarkManager.java"
reflective_path = root / "ww-debug-benchmark/src/main/java/com/wwdebug/benchmark/ReflectiveAircraft.java"

manager = manager_path.read_text(encoding="utf-8")
reflective = reflective_path.read_text(encoding="utf-8")

reflective = replace_once(
    reflective,
    """    public static void resetInternalState(Entity entity) {\n        Accessors accessors = accessors(entity);\n        invoke(accessors.chill, entity);\n        invoke(accessors.setEngineTarget, entity, 0.0f);\n    }\n\n    public static void setRoll(Entity entity, float roll) {""",
    """    public static void resetInternalState(Entity entity) {\n        Accessors accessors = accessors(entity);\n        invoke(accessors.chill, entity);\n        invoke(accessors.setEngineTarget, entity, 0.0f);\n    }\n\n    public static double enginePower(Entity entity) {\n        Object value = invoke(accessors(entity).getEnginePower, entity);\n        return value instanceof Number number ? number.doubleValue() : Double.NaN;\n    }\n\n    public static void setRoll(Entity entity, float roll) {""",
    "add engine power accessor",
)
reflective = replace_once(
    reflective,
    """                findMethod(type, "setInputs", float.class, float.class, float.class),\n                findMethod(type, "setEngineTarget", float.class),\n                findMethod(type, "setZRot", float.class),""",
    """                findMethod(type, "setInputs", float.class, float.class, float.class),\n                findMethod(type, "setEngineTarget", float.class),\n                findMethod(type, "getEnginePower"),\n                findMethod(type, "setZRot", float.class),""",
    "resolve engine power accessor",
)
reflective = replace_once(
    reflective,
    """            Method setInputs,\n            Method setEngineTarget,\n            Method setZRot,""",
    """            Method setInputs,\n            Method setEngineTarget,\n            Method getEnginePower,\n            Method setZRot,""",
    "record engine power accessor",
)

manager = replace_once(
    manager,
    "import net.minecraft.world.entity.decoration.ArmorStand;\nimport net.minecraft.world.level.storage.LevelResource;",
    "import net.minecraft.world.entity.decoration.ArmorStand;\nimport net.minecraft.world.level.ChunkPos;\nimport net.minecraft.world.level.storage.LevelResource;",
    "import ChunkPos",
)
manager = replace_once(manager, "PREPARE(40),", "PREPARE(220),", "extend prepare")
manager = replace_once(manager, "BRAKE(260),", "BRAKE(600),", "extend brake")
manager = replace_once(
    manager,
    """        private final Map<String, Double> effectiveStats;\n        private final List<Double> accelerationSpeeds = new ArrayList<>();\n        private Phase phase = Phase.PREPARE;""",
    """        private final Map<String, Double> effectiveStats;\n        private final List<Double> accelerationSpeeds = new ArrayList<>();\n        private final Set<Long> ownedForcedChunks = new HashSet<>();\n        private Phase phase = Phase.PREPARE;""",
    "add forced chunk ownership",
)
manager = replace_once(
    manager,
    """        private int phaseTick;\n        private boolean finished;\n        private String error = \"\";\n        private double topSpeed;""",
    """        private int phaseTick;\n        private int stablePrepareTicks;\n        private boolean finished;\n        private String error = \"\";\n        private double accelerationInitialSpeed = Double.NaN;\n        private double accelerationInitialEnginePower = Double.NaN;\n        private double topSpeed;""",
    "add preparation diagnostics",
)
manager = replace_once(
    manager,
    """        private double turnDegrees;\n        private double turnSpeedSum;\n        private int turnSamples;""",
    """        private double turnDegrees;\n        private double turnSpeedSum;\n        private double turnVerticalSpeedSum;\n        private double turnStartY;\n        private double turnEndY;\n        private int turnSamples;""",
    "add turn energy diagnostics",
)
manager = replace_once(
    manager,
    """        private double brakeTime50 = Double.NaN;\n        private double brakeTime10 = Double.NaN;\n        private int brakeLowSpeedTicks;""",
    """        private double brakeTime50 = Double.NaN;\n        private double brakeTime10 = Double.NaN;\n        private boolean brakeReachedTenPercent;\n        private int brakeLowSpeedTicks;""",
    "add brake completion flag",
)
manager = replace_once(
    manager,
    """            this.effectiveStats = ReflectiveAircraft.effectiveStats(aircraft);\n            CONTROLS.put(aircraft.getUUID(), new ControlInput(0, 0, 0, 0));""",
    """            this.effectiveStats = ReflectiveAircraft.effectiveStats(aircraft);\n            keepChunksLoaded();\n            CONTROLS.put(aircraft.getUUID(), new ControlInput(0, 0, 0, 0));""",
    "force initial chunks",
)
manager = replace_once(
    manager,
    """            if (finished) {\n                return;\n            }\n            if (aircraft.isRemoved() || pilot.isRemoved() || !pilot.isPassengerOfSameVehicle(aircraft)) {""",
    """            if (finished) {\n                return;\n            }\n            keepChunksLoaded();\n            if (aircraft.isRemoved() || pilot.isRemoved() || !pilot.isPassengerOfSameVehicle(aircraft)) {""",
    "keep active chunks loaded",
)
manager = replace_once(
    manager,
    """            if (phase == Phase.PREPARE && phaseTick >= 30 && !CONTROL_HEARTBEATS.contains(aircraft.getUUID())) {\n                fail(\"VehicleEntity.tickPilot control hook was not observed\");\n                return;\n            }\n\n            ReflectiveAircraft.fillFuel(aircraft);""",
    """            if (phase == Phase.PREPARE) {\n                boolean heartbeat = CONTROL_HEARTBEATS.contains(aircraft.getUUID());\n                double speed = aircraft.getDeltaMovement().length() * 20.0;\n                double enginePower = ReflectiveAircraft.enginePower(aircraft);\n                boolean engineSettled = !Double.isFinite(enginePower) || enginePower <= 0.02;\n                if (heartbeat && speed <= 0.25 && engineSettled) {\n                    stablePrepareTicks++;\n                } else {\n                    stablePrepareTicks = 0;\n                }\n                if (phaseTick >= 180 && !heartbeat) {\n                    fail(\"VehicleEntity.tickPilot control hook was not observed\");\n                    return;\n                }\n                if (phaseTick >= phase.maximumTicks && stablePrepareTicks < 20) {\n                    fail(\"Aircraft did not settle before acceleration sampling\");\n                    return;\n                }\n            }\n\n            ReflectiveAircraft.fillFuel(aircraft);""",
    "wait for a clean acceleration start",
)
manager = replace_once(
    manager,
    """                case STRAIGHT_ACCELERATION -> {\n                    accelerationSpeeds.add(horizontalSpeed);\n                    topSpeed = Math.max(topSpeed, horizontalSpeed);\n                }""",
    """                case STRAIGHT_ACCELERATION -> {\n                    if (phaseTick == 0) {\n                        accelerationInitialSpeed = horizontalSpeed;\n                        accelerationInitialEnginePower = ReflectiveAircraft.enginePower(aircraft);\n                    }\n                    accelerationSpeeds.add(horizontalSpeed);\n                    topSpeed = Math.max(topSpeed, horizontalSpeed);\n                }""",
    "record acceleration starting state",
)
manager = replace_once(
    manager,
    """                        turnDegrees += Math.abs(Mth.wrapDegrees(aircraft.getYRot() - previousYaw));\n                        turnSpeedSum += horizontalSpeed;\n                        turnSamples++;""",
    """                        turnDegrees += Math.abs(Mth.wrapDegrees(aircraft.getYRot() - previousYaw));\n                        turnSpeedSum += horizontalSpeed;\n                        turnVerticalSpeedSum += velocity.y * 20.0;\n                        turnSamples++;""",
    "record turn vertical speed",
)
manager = replace_once(
    manager,
    """                        if (Double.isNaN(brakeTime10) && horizontalSpeed <= brakeInitialSpeed * 0.1) {\n                            brakeTime10 = phaseTick / 20.0;\n                        }""",
    """                        if (Double.isNaN(brakeTime10) && horizontalSpeed <= brakeInitialSpeed * 0.1) {\n                            brakeTime10 = phaseTick / 20.0;\n                            brakeReachedTenPercent = true;\n                        }""",
    "record brake completion",
)
manager = replace_once(
    manager,
    """        private boolean shouldAdvance() {\n            if (phase == Phase.STRAIGHT_ACCELERATION""",
    """        private boolean shouldAdvance() {\n            if (phase == Phase.PREPARE && stablePrepareTicks >= 20) {\n                return true;\n            }\n            if (phase == Phase.STRAIGHT_ACCELERATION""",
    "advance only after stable prepare",
)
manager = replace_once(
    manager,
    """                case TURN_WARMUP -> {\n                    previousYaw = aircraft.getYRot();\n                    yield Phase.SUSTAINED_TURN;\n                }\n                case SUSTAINED_TURN -> {\n                    resetFlight();""",
    """                case TURN_WARMUP -> {\n                    previousYaw = aircraft.getYRot();\n                    turnStartY = aircraft.getY();\n                    yield Phase.SUSTAINED_TURN;\n                }\n                case SUSTAINED_TURN -> {\n                    turnEndY = aircraft.getY();\n                    resetFlight();""",
    "record turn altitude change",
)
manager = replace_once(
    manager,
    """        private void fail(String message) {""",
    """        private void keepChunksLoaded() {\n            ChunkPos center = aircraft.chunkPosition();\n            for (int dx = -2; dx <= 2; dx++) {\n                for (int dz = -2; dz <= 2; dz++) {\n                    int chunkX = center.x + dx;\n                    int chunkZ = center.z + dz;\n                    long key = ChunkPos.asLong(chunkX, chunkZ);\n                    if (!level.getForcedChunks().contains(key)) {\n                        level.setChunkForced(chunkX, chunkZ, true);\n                        ownedForcedChunks.add(key);\n                    }\n                }\n            }\n        }\n\n        private void releaseOwnedChunks() {\n            for (long key : ownedForcedChunks) {\n                ChunkPos chunk = new ChunkPos(key);\n                level.setChunkForced(chunk.x, chunk.z, false);\n            }\n            ownedForcedChunks.clear();\n        }\n\n        private void fail(String message) {""",
    "add chunk forcing helpers",
)
manager = replace_once(
    manager,
    """        private void cleanup() {\n            CONTROLS.remove(aircraft.getUUID());""",
    """        private void cleanup() {\n            releaseOwnedChunks();\n            CONTROLS.remove(aircraft.getUUID());""",
    "release benchmark chunks",
)
manager = replace_once(
    manager,
    """            double pitchResponse = pitchSamples == 0 ? Double.NaN : pitchDegrees / pitchSamples * 20.0;\n            double turnRetention = topSpeed <= 0.0 ? Double.NaN : turnSpeed / topSpeed;\n\n            values.put(\"top_speed_bps\", finite(topSpeed));""",
    """            double pitchResponse = pitchSamples == 0 ? Double.NaN : pitchDegrees / pitchSamples * 20.0;\n            double turnRetention = topSpeed <= 0.0 ? Double.NaN : turnSpeed / topSpeed;\n            double turnVerticalRate = turnSamples == 0 ? Double.NaN : turnVerticalSpeedSum / turnSamples;\n            boolean cleanAccelerationStart = accelerationInitialSpeed <= 0.50\n                    && (!Double.isFinite(accelerationInitialEnginePower) || accelerationInitialEnginePower <= 0.05);\n            List<String> qualityFlags = new ArrayList<>();\n            if (!cleanAccelerationStart) {\n                qualityFlags.add(\"contaminated_acceleration_start\");\n            }\n            if (!brakeReachedTenPercent) {\n                qualityFlags.add(\"brake_10_percent_not_reached\");\n            }\n            if (Double.isFinite(turnRetention) && turnRetention > 1.02) {\n                qualityFlags.add(\"turn_speed_exceeded_straight_speed\");\n            }\n\n            values.put(\"profile_eligible\", error.isEmpty() && cleanAccelerationStart);\n            values.put(\"quality_flags\", String.join(\"|\", qualityFlags));\n            values.put(\"accel_initial_speed_bps\", finite(accelerationInitialSpeed));\n            values.put(\"accel_initial_engine_power\", finite(accelerationInitialEnginePower));\n            values.put(\"top_speed_bps\", finite(topSpeed));""",
    "add quality diagnostics",
)
manager = replace_once(
    manager,
    """            values.put(\"turn_speed_retention\", finite(turnRetention));\n            values.put(\"climb_rate_bps\", finite(climbRate));""",
    """            values.put(\"turn_speed_retention\", finite(turnRetention));\n            values.put(\"turn_vertical_rate_bps\", finite(turnVerticalRate));\n            values.put(\"turn_altitude_change_blocks\", finite(turnEndY - turnStartY));\n            values.put(\"climb_rate_bps\", finite(climbRate));""",
    "write turn energy diagnostics",
)
manager = replace_once(
    manager,
    """            values.put(\"brake_time_50_s\", finite(brakeTime50));\n            values.put(\"brake_time_10_s\", finite(brakeTime10));""",
    """            values.put(\"brake_time_50_s\", finite(brakeTime50));\n            values.put(\"brake_time_10_s\", finite(brakeTime10));\n            values.put(\"brake_reached_10_percent\", brakeReachedTenPercent);""",
    "write brake completion",
)
manager = replace_once(
    manager,
    """            Path runDirectory = root.resolve(runId);\n            Path latestFile = root.resolve(\"latest.json\");\n\n            try {\n                Files.createDirectories(runDirectory);\n                List<Map<String, Object>> previous = readPrevious(latestFile);""",
    """            Path runDirectory = root.resolve(runId);\n            Path latestFile = root.resolve(\"latest.json\");\n            Path latestSuccessfulFile = root.resolve(\"latest_successful.json\");\n\n            try {\n                Files.createDirectories(runDirectory);\n                List<Map<String, Object>> previous = readPrevious(latestSuccessfulFile);""",
    "use successful comparison baseline",
)
manager = replace_once(
    manager,
    """                Files.writeString(latestFile, GSON.toJson(results), StandardCharsets.UTF_8);\n\n                source.sendSuccess""",
    """                Files.writeString(latestFile, GSON.toJson(results), StandardCharsets.UTF_8);\n                boolean fullyValid = results.stream().allMatch(row -> \"ok\".equals(row.get(\"status\"))\n                        && Boolean.TRUE.equals(row.get(\"profile_eligible\")));\n                if (fullyValid) {\n                    Files.writeString(latestSuccessfulFile, GSON.toJson(results), StandardCharsets.UTF_8);\n                }\n\n                source.sendSuccess""",
    "preserve only fully valid baseline",
)
manager = replace_once(
    manager,
    """                \"entity_id\", \"variant_group\", \"category\", \"role\", \"faction\", \"doctrine\", \"status\", \"error\",\n                \"width\", \"height\", \"passenger_space\",""",
    """                \"entity_id\", \"variant_group\", \"category\", \"role\", \"faction\", \"doctrine\", \"status\", \"error\",\n                \"profile_eligible\", \"quality_flags\", \"width\", \"height\", \"passenger_space\",""",
    "add quality CSV columns",
)
manager = replace_once(
    manager,
    """                \"top_speed_bps\", \"accel_time_50_s\", \"accel_time_90_s\", \"accel_time_95_s\",\n                \"turn_rate_deg_s\", \"turn_radius_blocks\", \"turn_speed_bps\", \"turn_speed_retention\",\n                \"climb_rate_bps\", \"climb_speed_bps\", \"pitch_response_deg_s\", \"stall_proxy_speed_bps\",\n                \"brake_initial_speed_bps\", \"brake_distance_blocks\", \"brake_time_50_s\", \"brake_time_10_s\"""",
    """                \"accel_initial_speed_bps\", \"accel_initial_engine_power\",\n                \"top_speed_bps\", \"accel_time_50_s\", \"accel_time_90_s\", \"accel_time_95_s\",\n                \"turn_rate_deg_s\", \"turn_radius_blocks\", \"turn_speed_bps\", \"turn_speed_retention\",\n                \"turn_vertical_rate_bps\", \"turn_altitude_change_blocks\",\n                \"climb_rate_bps\", \"climb_speed_bps\", \"pitch_response_deg_s\", \"stall_proxy_speed_bps\",\n                \"brake_initial_speed_bps\", \"brake_distance_blocks\", \"brake_time_50_s\", \"brake_time_10_s\",\n                \"brake_reached_10_percent\"""",
    "add diagnostic CSV metrics",
)
manager = replace_once(
    manager,
    """        for (Map<String, Object> row : current) {\n            String id = String.valueOf(row.get(\"entity_id\"));""",
    """        for (Map<String, Object> row : current) {\n            if (!\"ok\".equals(row.get(\"status\")) || !Boolean.TRUE.equals(row.get(\"profile_eligible\"))) {\n                continue;\n            }\n            String id = String.valueOf(row.get(\"entity_id\"));""",
    "skip invalid current comparison rows",
)
manager = replace_once(
    manager,
    """            Map<String, Object> old = oldById.get(id);\n            if (old == null) {""",
    """            Map<String, Object> old = oldById.get(id);\n            if (old == null || !\"ok\".equals(old.get(\"status\"))\n                    || !Boolean.TRUE.equals(old.get(\"profile_eligible\"))) {""",
    "skip invalid previous comparison rows",
)
manager = replace_once(
    manager,
    """            if (!\"ok\".equals(row.get(\"status\"))) {\n                continue;\n            }""",
    """            if (!\"ok\".equals(row.get(\"status\")) || !Boolean.TRUE.equals(row.get(\"profile_eligible\"))) {\n                continue;\n            }""",
    "exclude invalid profiles",
)

manager_path.write_text(manager, encoding="utf-8")
reflective_path.write_text(reflective, encoding="utf-8")
print("Applied validation-driven benchmark hardening")
