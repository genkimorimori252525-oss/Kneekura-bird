package com.wwdebug.autopilot;

import com.wwdebug.benchmark.ReflectiveAircraft;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;

import java.lang.reflect.Field;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Keeps the reciprocal GameTest inside an ordinary airborne cruise phase while combat is active.
 *
 * <p>Combat controllers intentionally replace normal mission steering. Without this test-only
 * adapter, a long dogfight can exhaust an unrelated turn-phase timeout and abort the validation
 * before the fixed combat window completes. Once the disposable opponent is removed, the primary
 * aircraft immediately resumes the normal mission state machine and must still return and park.</p>
 */
public final class MutualDogfightMissionHoldAdapter {
    private static final String SCENARIO_PROPERTY = "wwdebug.flightGameTestScenario";
    private static final String SCENARIO = "dogfight_mutual";
    private static final String TEST_NAME_PREFIX = "AUTOPILOT TEST ";
    private static final String OPPONENT_TAG = "wwcombat:mutual_opponent";
    private static final Set<UUID> LOGGED = ConcurrentHashMap.newKeySet();

    private static final Field SESSIONS = field(AutonomousFlightManager.class, "SESSIONS");
    private static final Field ENTRY_SESSION = sessionEntryField("session");
    private static final Field PHASE = field(AutopilotSession.class, "phase");
    private static final Field PHASE_TICKS = field(AutopilotSession.class, "phaseTicks");
    private static final Field STABLE_TICKS = field(AutopilotSession.class, "stableTicks");
    private static final Field FALLING_TICKS = field(AutopilotSession.class, "fallingTicks");
    private static final Field PHASE_TARGET_YAW = field(AutopilotSession.class, "phaseTargetYaw");
    private static final Field PHASE_DIRECTION = field(AutopilotSession.class, "phaseDirection");
    private static final Field TRANSITION_REASON = field(AutopilotSession.class, "transitionReason");
    private static final Field LAST_OUTPUT = field(AutopilotSession.class, "lastOutput");

    private MutualDogfightMissionHoldAdapter() {
    }

    @SuppressWarnings("unchecked")
    public static void beforeControl(Entity aircraft) {
        if (!SCENARIO.equals(System.getProperty(SCENARIO_PROPERTY, "").trim().toLowerCase())
                || aircraft.level().isClientSide
                || !(aircraft.level() instanceof ServerLevel level)
                || !ReflectiveAircraft.isAirplane(aircraft)
                || !participant(level, aircraft)) {
            LOGGED.remove(aircraft.getUUID());
            return;
        }
        try {
            Map<UUID, Object> sessions = (Map<UUID, Object>) SESSIONS.get(null);
            Object entry = sessions.get(aircraft.getUUID());
            if (entry == null) {
                return;
            }
            Object session = ENTRY_SESSION.get(entry);
            PHASE.set(session, FlightPhase.CRUISE_OUTBOUND);
            PHASE_TICKS.setInt(session, 0);
            STABLE_TICKS.setInt(session, 0);
            FALLING_TICKS.setInt(session, 0);
            PHASE_TARGET_YAW.setFloat(session, aircraft.getYRot());
            PHASE_DIRECTION.set(session, horizontalForward(aircraft));
            TRANSITION_REASON.set(session, "mutual_dogfight_combat_hold");
            LAST_OUTPUT.set(session, null);
            if (LOGGED.add(aircraft.getUUID())) {
                AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                        "mutual_dogfight_mission_hold",
                        "phase=CRUISE_OUTBOUND:reason=suspend_unrelated_mission_timeouts",
                        FlightPhase.CRUISE_OUTBOUND);
            }
        } catch (IllegalAccessException exception) {
            throw new IllegalStateException("Could not hold mutual-dogfight mission phase", exception);
        }
    }

    private static boolean participant(ServerLevel level, Entity aircraft) {
        if (aircraft.getTags().contains(OPPONENT_TAG)) {
            return true;
        }
        if (!aircraft.getName().getString().startsWith(TEST_NAME_PREFIX)) {
            return false;
        }
        AABB search = aircraft.getBoundingBox().inflate(260.0, 120.0, 260.0);
        return !level.getEntities(aircraft, search,
                entity -> !entity.isRemoved()
                        && entity.getTags().contains(OPPONENT_TAG)
                        && ReflectiveAircraft.isAirplane(entity)).isEmpty();
    }

    private static Vec3 horizontalForward(Entity aircraft) {
        Vec3 forward = aircraft.getLookAngle();
        Vec3 horizontal = new Vec3(forward.x, 0.0, forward.z);
        if (horizontal.lengthSqr() < 1.0e-8) {
            Vec3 motion = aircraft.getDeltaMovement();
            horizontal = new Vec3(motion.x, 0.0, motion.z);
        }
        return horizontal.lengthSqr() > 1.0e-8
                ? horizontal.normalize() : new Vec3(0.0, 0.0, 1.0);
    }

    private static Field field(Class<?> owner, String name) {
        try {
            Field field = owner.getDeclaredField(name);
            field.setAccessible(true);
            return field;
        } catch (NoSuchFieldException exception) {
            throw new ExceptionInInitializerError(exception);
        }
    }

    private static Field sessionEntryField(String name) {
        try {
            Class<?> entry = Class.forName(
                    "com.wwdebug.autopilot.AutonomousFlightManager$SessionEntry");
            Field field = entry.getDeclaredField(name);
            field.setAccessible(true);
            return field;
        } catch (ClassNotFoundException | NoSuchFieldException exception) {
            throw new ExceptionInInitializerError(exception);
        }
    }
}
