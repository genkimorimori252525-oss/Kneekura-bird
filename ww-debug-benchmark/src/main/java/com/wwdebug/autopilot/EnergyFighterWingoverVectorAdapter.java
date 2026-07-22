package com.wwdebug.autopilot;

import com.wwdebug.benchmark.ReflectiveAircraft;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.util.Mth;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.phys.Vec3;

import java.lang.reflect.Field;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

/**
 * Focused validation overlay for the energy-fighter vertical reversal.
 *
 * <p>Euler yaw ceases to describe the aircraft's horizontal nose direction once pitch passes the
 * vertical. The underlying re-engagement controller still owns the maneuver and its safety gates;
 * this adapter replaces only the WINGOVER horizontal input with an error measured from the actual
 * forward vector. Pitch, power, altitude target and speed target remain identical to the existing
 * powered reversal.</p>
 */
public final class EnergyFighterWingoverVectorAdapter {
    private static final double TURN_START_ANGLE_DEG = 95.0;
    private static final double TURN_FULL_ANGLE_DEG = 145.0;
    private static final double MAX_TURN_INPUT = 0.58;
    private static final double MIN_HORIZONTAL_LENGTH_SQR = 0.04;
    private static final double LEAD_TICKS = 10.0;
    private static final double TARGET_SPEED_BPS = 34.0;

    private static final Field STATES = field(EnergyFighterReengagementAdapter.class, "STATES");
    private static final Class<?> STATE_CLASS = nestedStateClass();
    private static final Field STATE_STAGE = field(STATE_CLASS, "stage");
    private static final Field STATE_WINGOVER_ANGLE = field(STATE_CLASS, "wingoverAngle");
    private static final Field STATE_WINGOVER_START_ALTITUDE =
            field(STATE_CLASS, "wingoverStartAltitude");

    private EnergyFighterWingoverVectorAdapter() {
    }

    /** @return true when the WINGOVER input was replaced for this tick. */
    public static boolean applyControl(Entity aircraft) {
        if (!(aircraft.level() instanceof ServerLevel level) || aircraft.level().isClientSide
                || !ReflectiveAircraft.isAirplane(aircraft)
                || !ReflectiveAircraft.isControllable(aircraft)
                || TerrainAvoidancePlanner.active(aircraft)
                || AirspaceSafetyProbe.collisionRisk(aircraft)) {
            return false;
        }

        Object state = state(aircraft.getUUID()).orElse(null);
        if (state == null || !"WINGOVER".equals(stageName(state))) {
            return false;
        }

        Entity target = targetAircraft(level, aircraft).orElse(null);
        FlightProfile profile = AutopilotProfileRegistry.resolve(level.getServer(), aircraft)
                .orElse(null);
        if (target == null || profile == null) {
            return false;
        }

        FlightSnapshot snapshot = FlightSnapshot.capture(aircraft);
        Vec3 leadPoint = target.getBoundingBox().getCenter()
                .add(target.getDeltaMovement().scale(LEAD_TICKS));
        Vec3 predictedLead = safeNormalize(
                leadPoint.subtract(aircraft.getBoundingBox().getCenter()), snapshot.forward());
        Vec3 horizontalForward = horizontal(snapshot.forward());
        Vec3 horizontalDesired = safeNormalize(horizontal(predictedLead),
                snapshot.horizontalForward());

        double wingoverAngle = doubleField(STATE_WINGOVER_ANGLE, state);
        double turnProgress = Mth.clamp(
                (wingoverAngle - TURN_START_ANGLE_DEG)
                        / (TURN_FULL_ANGLE_DEG - TURN_START_ANGLE_DEG),
                0.0, 1.0);
        double headingError = horizontalForward.lengthSqr() < MIN_HORIZONTAL_LENGTH_SQR
                ? 0.0 : signedHorizontalAngle(horizontalForward, horizontalDesired);
        float x = (float) (Mth.clamp(headingError / 30.0,
                -MAX_TURN_INPUT, MAX_TURN_INPUT) * turnProgress);

        double startAltitude = doubleField(STATE_WINGOVER_START_ALTITUDE, state);
        double targetAltitude = startAltitude + 90.0;
        FlightControlOutput output = new FlightControlOutput(
                x, 0.0f, -0.95f, 1.0f,
                horizontalDesired, targetAltitude, TARGET_SPEED_BPS,
                headingError, targetAltitude - snapshot.position().y,
                TARGET_SPEED_BPS - snapshot.speedBps(),
                snapshot.speedBps() < profile.stallGuardSpeedBps(), false,
                "energy_vector_heading_wingover",
                "actual_forward_vector_turn_after_vertical");

        ReflectiveAircraft.applyControl(aircraft, -output.x(), output.y(), output.z(),
                output.engineTarget());
        AutopilotLogManager.writeControlAdapter(level.getServer(), aircraft,
                AutonomousFlightManager.status(aircraft.getUUID())
                        .map(AutonomousFlightManager.SessionStatus::phase)
                        .orElse(FlightPhase.ABORTED),
                "wingover_angle=" + round(wingoverAngle)
                        + ":actual_horizontal_error=" + round(headingError)
                        + ":turn_progress=" + round(turnProgress),
                snapshot, baseline(snapshot), output);
        return true;
    }

    private static Optional<Entity> targetAircraft(ServerLevel level, Entity aircraft) {
        return CombatAwarenessManager.currentSolution(aircraft.getUUID())
                .map(solution -> level.getEntity(solution.targetUuid()))
                .filter(LivingEntity.class::isInstance)
                .map(LivingEntity.class::cast)
                .map(LivingEntity::getVehicle)
                .filter(target -> target != null && ReflectiveAircraft.isAirplane(target));
    }

    @SuppressWarnings("unchecked")
    private static Optional<Object> state(UUID aircraftUuid) {
        try {
            Map<UUID, Object> states = (Map<UUID, Object>) STATES.get(null);
            return Optional.ofNullable(states.get(aircraftUuid));
        } catch (IllegalAccessException exception) {
            throw new IllegalStateException("Could not read energy-fighter re-engagement state", exception);
        }
    }

    private static String stageName(Object state) {
        try {
            return String.valueOf(STATE_STAGE.get(state));
        } catch (IllegalAccessException exception) {
            throw new IllegalStateException("Could not read energy-fighter re-engagement stage", exception);
        }
    }

    private static double doubleField(Field field, Object owner) {
        try {
            return field.getDouble(owner);
        } catch (IllegalAccessException exception) {
            throw new IllegalStateException("Could not read energy-fighter wingover state", exception);
        }
    }

    private static double signedHorizontalAngle(Vec3 current, Vec3 desired) {
        Vec3 from = safeNormalize(horizontal(current), new Vec3(0.0, 0.0, 1.0));
        Vec3 to = safeNormalize(horizontal(desired), from);
        double dot = Mth.clamp(from.dot(to), -1.0, 1.0);
        double signedCross = from.x * to.z - from.z * to.x;
        return Math.toDegrees(Math.atan2(signedCross, dot));
    }

    private static Vec3 horizontal(Vec3 vector) {
        return new Vec3(vector.x, 0.0, vector.z);
    }

    private static Vec3 safeNormalize(Vec3 vector, Vec3 fallback) {
        if (vector != null && vector.lengthSqr() > 1.0e-8) {
            return vector.normalize();
        }
        return fallback != null && fallback.lengthSqr() > 1.0e-8
                ? fallback.normalize() : new Vec3(0.0, 0.0, 1.0);
    }

    private static FlightControlOutput baseline(FlightSnapshot snapshot) {
        float engine = Double.isFinite(snapshot.engineTarget())
                ? (float) snapshot.engineTarget() : 0.0f;
        return new FlightControlOutput(0.0f, 0.0f, 0.0f, engine,
                snapshot.horizontalForward(), snapshot.position().y, snapshot.speedBps(),
                0.0, 0.0, 0.0, false, false, "energy_wingover_control", "none");
    }

    private static Class<?> nestedStateClass() {
        try {
            return Class.forName(
                    "com.wwdebug.autopilot.EnergyFighterReengagementAdapter$State");
        } catch (ClassNotFoundException exception) {
            throw new ExceptionInInitializerError(exception);
        }
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

    private static double round(double value) {
        return Math.rint(value * 100.0) / 100.0;
    }
}
