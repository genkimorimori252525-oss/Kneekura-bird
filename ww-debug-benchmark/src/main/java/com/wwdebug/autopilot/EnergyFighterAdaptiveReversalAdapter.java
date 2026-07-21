package com.wwdebug.autopilot;

import com.wwdebug.benchmark.ReflectiveAircraft;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.util.Mth;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.phys.Vec3;

import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Corrects only a demonstrably slow energy-fighter reversal.
 *
 * <p>The ordinary counterattack controller gets the first forty ticks without interference. If the
 * raw target angle has improved by less than twenty degrees, this adapter reverses the turn side
 * and owns the high-yo-yo input until the target reaches the normal attack-setup sector. Fast,
 * already-successful reversals are never changed.</p>
 */
public final class EnergyFighterAdaptiveReversalAdapter {
    private static final int PROGRESS_CHECK_TICKS = 40;
    private static final double MIN_PROGRESS_DEG = 20.0;
    private static final double HANDOFF_RAW_ANGLE_DEG = 48.0;
    private static final Map<UUID, State> STATES = new ConcurrentHashMap<>();

    private EnergyFighterAdaptiveReversalAdapter() {
    }

    /**
     * @return true when this adapter replaced the counterattack manager's input for this tick
     */
    public static boolean applyControl(Entity aircraft) {
        if (aircraft.level().isClientSide || !(aircraft.level() instanceof ServerLevel level)
                || !ReflectiveAircraft.isAirplane(aircraft)
                || !ReflectiveAircraft.isControllable(aircraft)
                || aircraft.onGround()
                || TerrainAvoidancePlanner.active(aircraft)
                || AirspaceSafetyProbe.collisionRisk(aircraft)) {
            clear(aircraft.getUUID());
            return false;
        }

        Optional<AutonomousFlightManager.SessionStatus> status =
                AutonomousFlightManager.status(aircraft.getUUID());
        FlightProfile profile = AutopilotProfileRegistry.resolve(level.getServer(), aircraft)
                .orElse(null);
        if (status.isEmpty() || profile == null
                || !"energy_fighter".equalsIgnoreCase(profile.doctrine())) {
            clear(aircraft.getUUID());
            return false;
        }

        Target target = target(level, aircraft).orElse(null);
        if (target == null) {
            clear(aircraft.getUUID());
            return false;
        }

        FlightSnapshot snapshot = FlightSnapshot.capture(aircraft);
        Vec3 targetDirection = safeNormalize(target.aircraft().getBoundingBox().getCenter()
                .subtract(aircraft.getBoundingBox().getCenter()), snapshot.forward());
        double rawTargetAngle = angleDegrees(snapshot.forward(), targetDirection);
        State state = STATES.computeIfAbsent(aircraft.getUUID(), ignored ->
                new State(rawTargetAngle, shortestTurnSign(snapshot, targetDirection),
                        snapshot.position().y));
        state.ticks++;
        state.bestRawTargetAngle = Math.min(state.bestRawTargetAngle, rawTargetAngle);

        if (rawTargetAngle <= HANDOFF_RAW_ANGLE_DEG) {
            state.handedOff = true;
        }
        if (state.handedOff) {
            return false;
        }

        if (!state.overrideActive && state.ticks >= PROGRESS_CHECK_TICKS) {
            double progress = state.initialRawTargetAngle - state.bestRawTargetAngle;
            if (progress < MIN_PROGRESS_DEG) {
                state.overrideSign = -state.initialTurnSign;
                state.overrideActive = true;
                AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                        "energy_adaptive_reversal_start",
                        description(state, rawTargetAngle)
                                + ":reason=initial_reversal_progress_too_slow",
                        status.get().phase());
            } else {
                state.handedOff = true;
                AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                        "energy_adaptive_reversal_not_needed",
                        description(state, rawTargetAngle)
                                + ":reason=ordinary_reversal_progress_sufficient",
                        status.get().phase());
                return false;
            }
        }

        if (!state.overrideActive) {
            return false;
        }

        applyOverride(level, aircraft, target.aircraft(), snapshot, profile, targetDirection,
                rawTargetAngle, state, status.get().phase());
        if (state.statusTicks++ % 10 == 0) {
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "energy_adaptive_reversal_status",
                    description(state, rawTargetAngle), status.get().phase());
        }
        return true;
    }

    private static void applyOverride(ServerLevel level, Entity aircraft, Entity target,
                                      FlightSnapshot snapshot, FlightProfile profile,
                                      Vec3 targetDirection, double rawTargetAngle, State state,
                                      FlightPhase phase) {
        Vec3 shortLeadPoint = target.getBoundingBox().getCenter()
                .add(target.getDeltaMovement().scale(7.0));
        Vec3 leadDirection = safeNormalize(shortLeadPoint
                .subtract(aircraft.getBoundingBox().getCenter()), targetDirection);
        Vec3 horizontalDesired = safeNormalize(horizontal(leadDirection),
                snapshot.horizontalForward());
        double desiredYaw = Math.toDegrees(Math.atan2(-horizontalDesired.x, horizontalDesired.z));
        double headingError = Mth.wrapDegrees((float) (desiredYaw - snapshot.yawDeg()));

        float x = (float) (state.overrideSign * 0.86);
        double targetAltitude = Math.max(target.position().y + 10.0,
                state.startAltitude + 22.0);
        double altitudeError = targetAltitude - snapshot.position().y;
        double desiredPitch = Mth.clamp(-altitudeError * 0.19
                + snapshot.verticalSpeedBps() * 0.30, -12.0, 7.0);
        if (snapshot.speedBps() < profile.turnSpeedFloorBps() * 0.90) {
            desiredPitch = Math.max(desiredPitch, -2.0);
            x *= 0.58f;
        }
        float z = (float) Mth.clamp((desiredPitch - snapshot.pitchDeg()) / 16.0,
                -0.78, 0.72);
        double targetSpeed = Math.max(profile.cruiseSpeedBps() + 7.0,
                snapshot.speedBps() + 2.0);
        FlightControlOutput output = new FlightControlOutput(x, 0.0f, z, 1.0f,
                horizontalDesired, targetAltitude, targetSpeed, headingError, altitudeError,
                targetSpeed - snapshot.speedBps(),
                snapshot.speedBps() < profile.stallGuardSpeedBps(), false,
                "energy_adaptive_reversal", "slow_reversal_side_correction");
        ReflectiveAircraft.applyControl(aircraft, -output.x(), output.y(), output.z(),
                output.engineTarget());
        AutopilotLogManager.writeControlAdapter(level.getServer(), aircraft, phase,
                description(state, rawTargetAngle), snapshot, baseline(snapshot), output);
    }

    private static Optional<Target> target(ServerLevel level, Entity aircraft) {
        return CombatAwarenessManager.currentSolution(aircraft.getUUID())
                .map(solution -> level.getEntity(solution.targetUuid()))
                .filter(LivingEntity.class::isInstance)
                .map(LivingEntity.class::cast)
                .map(living -> {
                    Entity targetAircraft = living.getVehicle();
                    if (targetAircraft == null || !ReflectiveAircraft.isAirplane(targetAircraft)) {
                        targetAircraft = living;
                    }
                    return new Target(targetAircraft);
                });
    }

    private static double shortestTurnSign(FlightSnapshot snapshot, Vec3 targetDirection) {
        Vec3 horizontalTarget = safeNormalize(horizontal(targetDirection),
                snapshot.horizontalForward());
        double desiredYaw = Math.toDegrees(Math.atan2(-horizontalTarget.x, horizontalTarget.z));
        double headingError = Mth.wrapDegrees((float) (desiredYaw - snapshot.yawDeg()));
        return headingError >= 0.0 ? 1.0 : -1.0;
    }

    private static String description(State state, double rawTargetAngle) {
        return "ticks=" + state.ticks
                + ":initial_raw_target_angle=" + round(state.initialRawTargetAngle)
                + ":best_raw_target_angle=" + round(state.bestRawTargetAngle)
                + ":raw_target_angle=" + round(rawTargetAngle)
                + ":initial_turn_sign=" + state.initialTurnSign
                + ":override_sign=" + state.overrideSign
                + ":override_active=" + state.overrideActive;
    }

    public static void clear(UUID aircraftUuid) {
        STATES.remove(aircraftUuid);
    }

    private static double angleDegrees(Vec3 first, Vec3 second) {
        if (first.lengthSqr() < 1.0e-8 || second.lengthSqr() < 1.0e-8) {
            return 0.0;
        }
        return Math.toDegrees(Math.acos(Mth.clamp(
                first.normalize().dot(second.normalize()), -1.0, 1.0)));
    }

    private static Vec3 horizontal(Vec3 vector) {
        return new Vec3(vector.x, 0.0, vector.z);
    }

    private static Vec3 safeNormalize(Vec3 vector, Vec3 fallback) {
        if (vector.lengthSqr() > 1.0e-8) {
            return vector.normalize();
        }
        return fallback.lengthSqr() > 1.0e-8
                ? fallback.normalize() : new Vec3(0.0, 0.0, 1.0);
    }

    private static FlightControlOutput baseline(FlightSnapshot snapshot) {
        float engine = Double.isFinite(snapshot.engineTarget())
                ? (float) snapshot.engineTarget() : 0.0f;
        return new FlightControlOutput(0.0f, 0.0f, 0.0f, engine,
                snapshot.horizontalForward(), snapshot.position().y, snapshot.speedBps(),
                0.0, 0.0, 0.0, false, false, "previous_control", "none");
    }

    private static double round(double value) {
        return Math.rint(value * 100.0) / 100.0;
    }

    private record Target(Entity aircraft) {
    }

    private static final class State {
        private final double initialRawTargetAngle;
        private final double initialTurnSign;
        private final double startAltitude;
        private double bestRawTargetAngle;
        private double overrideSign;
        private int ticks;
        private int statusTicks;
        private boolean overrideActive;
        private boolean handedOff;

        private State(double initialRawTargetAngle, double initialTurnSign,
                      double startAltitude) {
            this.initialRawTargetAngle = initialRawTargetAngle;
            this.initialTurnSign = initialTurnSign;
            this.bestRawTargetAngle = initialRawTargetAngle;
            this.startAltitude = startAltitude;
        }
    }
}
