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
 * vertical. The underlying re-engagement controller still owns maneuver entry and all safety
 * gates. This adapter replaces horizontal steering with actual-forward-vector error during the
 * wingover and recovery, while reducing azimuth authority when the predicted target direction is
 * nearly vertical and horizontal bearing is physically ill-conditioned.</p>
 */
public final class EnergyFighterWingoverVectorAdapter {
    private static final double TURN_START_ANGLE_DEG = 95.0;
    private static final double TURN_FULL_ANGLE_DEG = 145.0;
    private static final double MAX_WINGOVER_TURN_INPUT = 0.58;
    private static final double MAX_RECOVERY_TURN_INPUT = 0.96;
    private static final double MIN_HORIZONTAL_LENGTH_SQR = 0.04;
    private static final double RECOVERY_HORIZONTAL_DEADBAND = 0.10;
    private static final double RECOVERY_HORIZONTAL_FULL_AUTHORITY = 0.65;
    private static final double LEAD_TICKS = 10.0;
    private static final double WINGOVER_TARGET_SPEED_BPS = 34.0;

    private static final Field STATES = field(EnergyFighterReengagementAdapter.class, "STATES");
    private static final Class<?> STATE_CLASS = nestedStateClass();
    private static final Field STATE_STAGE = field(STATE_CLASS, "stage");
    private static final Field STATE_WINGOVER_ANGLE = field(STATE_CLASS, "wingoverAngle");
    private static final Field STATE_WINGOVER_START_ALTITUDE =
            field(STATE_CLASS, "wingoverStartAltitude");

    private EnergyFighterWingoverVectorAdapter() {
    }

    /** @return true when WINGOVER or RECOVERY input was replaced for this tick. */
    public static boolean applyControl(Entity aircraft) {
        if (!(aircraft.level() instanceof ServerLevel level) || aircraft.level().isClientSide
                || !ReflectiveAircraft.isAirplane(aircraft)
                || !ReflectiveAircraft.isControllable(aircraft)
                || TerrainAvoidancePlanner.active(aircraft)
                || AirspaceSafetyProbe.collisionRisk(aircraft)) {
            return false;
        }

        Object state = state(aircraft.getUUID()).orElse(null);
        String stage = state == null ? "NONE" : stageName(state);
        if (!"WINGOVER".equals(stage) && !"RECOVERY".equals(stage)) {
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
        double headingError = horizontalForward.lengthSqr() < MIN_HORIZONTAL_LENGTH_SQR
                ? 0.0 : signedHorizontalAngle(horizontalForward, horizontalDesired);

        FlightControlOutput output;
        String description;
        if ("WINGOVER".equals(stage)) {
            double wingoverAngle = doubleField(STATE_WINGOVER_ANGLE, state);
            double turnProgress = Mth.clamp(
                    (wingoverAngle - TURN_START_ANGLE_DEG)
                            / (TURN_FULL_ANGLE_DEG - TURN_START_ANGLE_DEG),
                    0.0, 1.0);
            float x = (float) (Mth.clamp(headingError / 30.0,
                    -MAX_WINGOVER_TURN_INPUT, MAX_WINGOVER_TURN_INPUT) * turnProgress);
            double startAltitude = doubleField(STATE_WINGOVER_START_ALTITUDE, state);
            double targetAltitude = startAltitude + 90.0;
            output = new FlightControlOutput(
                    x, 0.0f, -0.95f, 1.0f,
                    horizontalDesired, targetAltitude, WINGOVER_TARGET_SPEED_BPS,
                    headingError, targetAltitude - snapshot.position().y,
                    WINGOVER_TARGET_SPEED_BPS - snapshot.speedBps(),
                    snapshot.speedBps() < profile.stallGuardSpeedBps(), false,
                    "energy_vector_heading_wingover",
                    "actual_forward_vector_turn_after_vertical");
            description = "stage=WINGOVER"
                    + ":wingover_angle=" + round(wingoverAngle)
                    + ":actual_horizontal_error=" + round(headingError)
                    + ":turn_progress=" + round(turnProgress);
        } else {
            double horizontalTargetMagnitude = horizontal(predictedLead).length();
            double horizontalAuthority = Mth.clamp(
                    (horizontalTargetMagnitude - RECOVERY_HORIZONTAL_DEADBAND)
                            / (RECOVERY_HORIZONTAL_FULL_AUTHORITY
                            - RECOVERY_HORIZONTAL_DEADBAND),
                    0.0, 1.0);
            float x = (float) (Mth.clamp(headingError / 28.0,
                    -MAX_RECOVERY_TURN_INPUT, MAX_RECOVERY_TURN_INPUT)
                    * horizontalAuthority);
            double targetAltitude = target.getBoundingBox().getCenter().y;
            double altitudeError = targetAltitude - snapshot.position().y;
            double verticalDirectionError = predictedLead.y - snapshot.forward().y;
            float z = (float) Mth.clamp(verticalDirectionError * 1.80
                    + snapshot.verticalSpeedBps() * 0.018, -0.88, 0.88);
            double targetSpeed = recoveryTargetSpeed(profile, target);
            float engineTarget = snapshot.speedBps() < targetSpeed - 1.0 ? 1.0f
                    : snapshot.speedBps() > targetSpeed + 3.0 ? 0.35f : 0.65f;
            output = new FlightControlOutput(
                    x, 0.0f, z, engineTarget,
                    predictedLead, targetAltitude, targetSpeed,
                    headingError, altitudeError, targetSpeed - snapshot.speedBps(),
                    snapshot.speedBps() < profile.stallGuardSpeedBps(), false,
                    "energy_vector_recovery_weighted_azimuth",
                    "vertical_target_priority_during_recovery");
            description = "stage=RECOVERY"
                    + ":actual_horizontal_error=" + round(headingError)
                    + ":horizontal_target_magnitude=" + round(horizontalTargetMagnitude)
                    + ":horizontal_authority=" + round(horizontalAuthority)
                    + ":vertical_direction_error=" + round(verticalDirectionError);
        }

        ReflectiveAircraft.applyControl(aircraft, -output.x(), output.y(), output.z(),
                output.engineTarget());
        AutopilotLogManager.writeControlAdapter(level.getServer(), aircraft,
                AutonomousFlightManager.status(aircraft.getUUID())
                        .map(AutonomousFlightManager.SessionStatus::phase)
                        .orElse(FlightPhase.ABORTED),
                description, snapshot, baseline(snapshot), output);
        return true;
    }

    private static double recoveryTargetSpeed(FlightProfile profile, Entity target) {
        double measuredManeuverSpeed = Math.max(profile.cruiseSpeedBps(),
                profile.turnSpeedFloorBps() * 0.90);
        return Math.max(measuredManeuverSpeed,
                target.getDeltaMovement().horizontalDistance() * 20.0 + 3.0);
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
                0.0, 0.0, 0.0, false, false, "energy_vertical_reversal_control", "none");
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
