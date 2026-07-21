package com.wwdebug.autopilot;

import com.wwdebug.benchmark.ReflectiveAircraft;
import com.wwdebug.benchmark.WWDebugBenchmarkMod;
import net.minecraft.core.BlockPos;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.util.Mth;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.monster.Zombie;
import net.minecraft.world.entity.npc.Villager;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.phys.Vec3;

import java.lang.reflect.Field;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * GameTest-only checkpoint injector. It keeps the real autonomous-flight controller and real
 * Immersive Aircraft physics, but starts a validation aircraft near the phase currently being
 * tuned instead of replaying every earlier phase on every commit.
 */
final class AutopilotValidationCheckpoint {
    private static final String PROPERTY = "wwdebug.flightGameTestScenario";
    private static final String VALIDATION_NAME_PREFIX = "AUTOPILOT TEST ";
    private static final Set<UUID> APPLIED = ConcurrentHashMap.newKeySet();

    private static final Field PHASE = field("phase");
    private static final Field PHASE_TICKS = field("phaseTicks");
    private static final Field MISSION_TICKS = field("missionTicks");
    private static final Field STABLE_TICKS = field("stableTicks");
    private static final Field FALLING_TICKS = field("fallingTicks");
    private static final Field PHASE_TARGET_YAW = field("phaseTargetYaw");
    private static final Field PHASE_DIRECTION = field("phaseDirection");
    private static final Field RECOVERY_PULL_OUT = field("recoveryPullOut");
    private static final Field TRANSITION_REASON = field("transitionReason");
    private static final Field LAST_OUTPUT = field("lastOutput");

    private AutopilotValidationCheckpoint() {
    }

    static boolean applyIfRequested(MinecraftServer server, Entity aircraft, AutopilotSession session) {
        String scenario = System.getProperty(PROPERTY, "full").trim().toLowerCase();
        if (scenario.isEmpty() || "full".equals(scenario)) {
            return false;
        }
        if (!aircraft.getName().getString().startsWith(VALIDATION_NAME_PREFIX)) {
            return false;
        }
        if (!APPLIED.add(aircraft.getUUID())) {
            return false;
        }

        Vec3 home = aircraft.position();
        Vec3 runwayForward = horizontal(aircraft.getLookAngle());
        if (runwayForward.lengthSqr() < 1.0e-8) {
            runwayForward = horizontal(Vec3.directionFromRotation(0.0f, aircraft.getYRot()));
        }
        runwayForward = runwayForward.normalize();
        FlightProfile profile = session.profile();

        FlightPhase initialPhase;
        Vec3 position;
        double speedBps;
        float engineTarget;
        int initialMissionTicks;
        switch (scenario) {
            case "landing" -> {
                initialPhase = FlightPhase.FINAL;
                position = home.subtract(runwayForward.scale(150.0)).add(0.0, 36.0, 0.0);
                speedBps = profile.approachSpeedBps() * 1.10;
                engineTarget = 0.72f;
                initialMissionTicks = 14_500;
            }
            case "stall" -> {
                initialPhase = FlightPhase.STALL_ENTRY;
                position = home.add(0.0, 125.0, 0.0);
                speedBps = profile.climbTargetSpeedBps();
                engineTarget = 0.0f;
                initialMissionTicks = 14_800;
            }
            case "turn" -> {
                initialPhase = FlightPhase.TURN_LEFT;
                position = home.add(0.0, 100.0, 0.0);
                speedBps = Math.max(profile.turnSpeedFloorBps(), profile.cruiseSpeedBps());
                engineTarget = 0.72f;
                initialMissionTicks = 15_400;
            }
            case "terrain" -> {
                initialPhase = FlightPhase.CRUISE_OUTBOUND;
                position = home.subtract(runwayForward.scale(180.0)).add(0.0, 78.0, 0.0);
                speedBps = profile.cruiseSpeedBps();
                engineTarget = 0.72f;
                initialMissionTicks = 15_200;
                buildTerrainObstacle((ServerLevel) aircraft.level(), home, runwayForward);
            }
            case "targeting" -> {
                initialPhase = FlightPhase.CRUISE_OUTBOUND;
                position = home.subtract(runwayForward.scale(160.0)).add(0.0, 78.0, 0.0);
                speedBps = profile.cruiseSpeedBps();
                engineTarget = 0.72f;
                initialMissionTicks = 15_400;
                buildTargetingScene((ServerLevel) aircraft.level(), home, runwayForward);
            }
            default -> {
                APPLIED.remove(aircraft.getUUID());
                WWDebugBenchmarkMod.LOGGER.warn(
                        "Unknown headless flight scenario '{}'; running the full mission instead", scenario);
                return false;
            }
        }

        seedSession(session, initialPhase, runwayForward, aircraft.getYRot(), scenario, initialMissionTicks);
        ReflectiveAircraft.warmEngine(aircraft, engineTarget);
        aircraft.moveTo(position.x, position.y, position.z, aircraft.getYRot(), 0.0f);
        aircraft.setDeltaMovement(runwayForward.scale(speedBps / 20.0));
        ReflectiveAircraft.setRoll(aircraft, 0.0f);
        ReflectiveAircraft.applyControl(aircraft, 0.0f, 0.0f, 0.0f, engineTarget);

        AutopilotLogManager.writeEvent(server, aircraft, "validation_checkpoint",
                scenario + "_checkpoint_seeded", initialPhase);
        WWDebugBenchmarkMod.LOGGER.info(
                "Seeded headless autonomous-flight checkpoint scenario={} phase={} position={} speed_bps={} engine_power={} mission_tick_offset={} home={} runway_forward={}",
                scenario, initialPhase, position, speedBps, ReflectiveAircraft.enginePower(aircraft),
                initialMissionTicks, home, runwayForward);
        return true;
    }

    private static void buildTerrainObstacle(ServerLevel level, Vec3 home, Vec3 runwayForward) {
        Vec3 runwayRight = new Vec3(-runwayForward.z, 0.0, runwayForward.x).normalize();
        Vec3 center = home.subtract(runwayForward.scale(75.0)).add(0.0, 78.0, 0.0);
        for (int lateral = -22; lateral <= 22; lateral++) {
            for (int depth = -2; depth <= 2; depth++) {
                for (int vertical = -30; vertical <= 30; vertical++) {
                    Vec3 point = center
                            .add(runwayRight.scale(lateral))
                            .add(runwayForward.scale(depth))
                            .add(0.0, vertical, 0.0);
                    level.setBlock(BlockPos.containing(point), Blocks.STONE.defaultBlockState(), 2);
                }
            }
        }
        WWDebugBenchmarkMod.LOGGER.info(
                "Built terrain-avoidance test wall center={} width={} height={} depth={}",
                center, 45, 61, 5);
    }

    private static void buildTargetingScene(ServerLevel level, Vec3 home, Vec3 runwayForward) {
        Vec3 neutralPosition = home.subtract(runwayForward.scale(90.0)).add(0.0, 78.0, 0.0);
        Vec3 hostilePosition = home.subtract(runwayForward.scale(55.0)).add(0.0, 78.0, 0.0);

        Villager neutral = EntityType.VILLAGER.create(level);
        if (neutral == null) {
            throw new IllegalStateException("Could not create neutral targeting-test villager");
        }
        neutral.setNoAi(true);
        neutral.setNoGravity(true);
        neutral.setSilent(true);
        neutral.setInvulnerable(true);
        neutral.moveTo(neutralPosition.x, neutralPosition.y, neutralPosition.z, 180.0f, 0.0f);
        level.addFreshEntity(neutral);

        Zombie hostile = EntityType.ZOMBIE.create(level);
        if (hostile == null) {
            throw new IllegalStateException("Could not create hostile targeting-test zombie");
        }
        hostile.setNoAi(true);
        hostile.setNoGravity(true);
        hostile.setSilent(true);
        hostile.setInvulnerable(true);
        hostile.moveTo(hostilePosition.x, hostilePosition.y, hostilePosition.z, 180.0f, 0.0f);
        level.addFreshEntity(hostile);

        WWDebugBenchmarkMod.LOGGER.info(
                "Built targeting test scene neutral_villager={} hostile_zombie={}",
                neutralPosition, hostilePosition);
    }

    static void forget(UUID aircraftUuid) {
        APPLIED.remove(aircraftUuid);
    }

    private static void seedSession(AutopilotSession session, FlightPhase phase, Vec3 direction,
                                    float currentYaw, String scenario, int missionTicks) {
        try {
            PHASE.set(session, phase);
            PHASE_TICKS.setInt(session, 0);
            MISSION_TICKS.setInt(session, missionTicks);
            STABLE_TICKS.setInt(session, 0);
            FALLING_TICKS.setInt(session, 0);
            PHASE_DIRECTION.set(session, direction);
            RECOVERY_PULL_OUT.setBoolean(session, false);
            TRANSITION_REASON.set(session, "validation_checkpoint_" + scenario);
            LAST_OUTPUT.set(session, null);
            float targetYaw = switch (phase) {
                case TURN_LEFT -> Mth.wrapDegrees(currentYaw - 170.0f);
                case TURN_RIGHT -> Mth.wrapDegrees(currentYaw + 170.0f);
                default -> currentYaw;
            };
            PHASE_TARGET_YAW.setFloat(session, targetYaw);
        } catch (IllegalAccessException exception) {
            throw new IllegalStateException("Could not seed autonomous-flight validation checkpoint", exception);
        }
    }

    private static Field field(String name) {
        try {
            Field value = AutopilotSession.class.getDeclaredField(name);
            value.setAccessible(true);
            return value;
        } catch (NoSuchFieldException exception) {
            throw new ExceptionInInitializerError(exception);
        }
    }

    private static Vec3 horizontal(Vec3 vector) {
        return new Vec3(vector.x, 0.0, vector.z);
    }
}
