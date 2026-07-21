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
 * Protects a successful energy-fighter reversal from stalling just outside attack setup.
 *
 * <p>The ordinary counterattack controller remains authoritative while the target angle is
 * improving. A broadside plateau may be tightened with a higher yo-yo, but once the fighter reaches
 * the near-setup sector this adapter stops all additional reversal logic and briefly points toward a
 * short future target position. The counterattack manager can then cross its normal 48-degree
 * transition boundary without a one-tick angle wobble causing a destructive turn flip.</p>
 */
public final class EnergyFighterAdaptiveReversalAdapter {
    private static final int MIN_OBSERVATION_TICKS = 60;
    private static final int PLATEAU_TICKS = 10;
    private static final int MAX_OVERRIDE_TICKS = 120;
    private static final double REQUIRED_PROGRESS_DEG = 18.0;
    private static final double MAX_BEST_RAW_ANGLE_DEG = 105.0;
    private static final double MAX_START_RAW_ANGLE_DEG = 112.0;
    private static final double NEAR_SETUP_CAPTURE_ANGLE_DEG = 55.0;
    private static final double NEAR_SETUP_MAX_RAW_ANGLE_DEG = 64.0;
    private static final double MANAGER_HANDOFF_RAW_ANGLE_DEG = 48.0;
    private static final double YOYO_ALTITUDE_GAIN = 40.0;
    private static final Map<UUID, State> STATES = new ConcurrentHashMap<>();

    private EnergyFighterAdaptiveReversalAdapter() {
    }

    /**
     * @return true when this adapter replaces the ordinary counterattack input for this tick
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
                new State(rawTargetAngle, snapshot.position().y));
        state.ticks++;

        if (rawTargetAngle + 0.5 < state.bestRawTargetAngle) {
            state.bestRawTargetAngle = rawTargetAngle;
            state.plateauTicks = 0;
        } else {
            state.plateauTicks++;
        }

        // The manager evaluates first in the same tick. Once it can see <=48 degrees, stop
        // overriding and let its normal ATTACK_SETUP transition and lead-aimed handoff proceed.
        if (rawTargetAngle <= MANAGER_HANDOFF_RAW_ANGLE_DEG) {
            if (state.overrideActive || state.nearSetupCapture) {
                AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                        "energy_adaptive_reversal_handoff",
                        description(state, rawTargetAngle)
                                + ":reason=manager_attack_setup_boundary_reached",
                        status.get().phase());
            }
            state.handedOff = true;
            return false;
        }
        if (state.handedOff) {
            return false;
        }

        // A fighter that has already reached roughly fifty degrees must not begin another wide
        // reversal. Capture the nearly complete solution and drive it across the manager boundary.
        if (!state.nearSetupCapture
                && state.bestRawTargetAngle <= NEAR_SETUP_CAPTURE_ANGLE_DEG
                && rawTargetAngle <= NEAR_SETUP_MAX_RAW_ANGLE_DEG) {
            state.nearSetupCapture = true;
            state.overrideActive = false;
            state.overrideTicks = 0;
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "energy_near_setup_capture_start",
                    description(state, rawTargetAngle)
                            + ":reason=protect_nearly_complete_counterattack_solution",
                    status.get().phase());
        }
        if (state.nearSetupCapture) {
            applyNearSetupCapture(level, aircraft, target.aircraft(), snapshot, profile,
                    targetDirection, rawTargetAngle, state, status.get().phase());
            state.overrideTicks++;
            return true;
        }

        if (!state.overrideActive) {
            double progress = state.initialRawTargetAngle - state.bestRawTargetAngle;
            boolean measuredPlateau = state.ticks >= MIN_OBSERVATION_TICKS
                    && progress >= REQUIRED_PROGRESS_DEG
                    && state.bestRawTargetAngle > NEAR_SETUP_CAPTURE_ANGLE_DEG
                    && state.bestRawTargetAngle <= MAX_BEST_RAW_ANGLE_DEG
                    && rawTargetAngle <= MAX_START_RAW_ANGLE_DEG
                    && state.plateauTicks >= PLATEAU_TICKS;
            if (!measuredPlateau) {
                return false;
            }
            state.overrideActive = true;
            state.overrideTicks = 0;
            state.turnSign = retainedTurnSign(snapshot, targetDirection);
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "energy_adaptive_reversal_start",
                    description(state, rawTargetAngle)
                            + ":reason=broadside_plateau_tighten_high_yoyo",
                    status.get().phase());
        }

        if (state.overrideTicks >= MAX_OVERRIDE_TICKS) {
            state.handedOff = true;
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "energy_adaptive_reversal_handoff",
                    description(state, rawTargetAngle)
                            + ":reason=tightened_high_yoyo_timeout",
                    status.get().phase());
            return false;
        }

        applyTightenedHighYoyo(level, aircraft, target.aircraft(), snapshot, profile,
                targetDirection, rawTargetAngle, state, status.get().phase());
        state.overrideTicks++;
        if (state.statusTicks++ % 10 == 0) {
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "energy_adaptive_reversal_status",
                    description(state, rawTargetAngle), status.get().phase());
        }
        return true;
    }

    private static void applyNearSetupCapture(ServerLevel level, Entity aircraft, Entity target,
                                              FlightSnapshot snapshot, FlightProfile profile,
                                              Vec3 targetDirection, double rawTargetAngle,
                                              State state, FlightPhase phase) {
        Vec3 shortLeadPoint = target.getBoundingBox().getCenter()
                .add(target.getDeltaMovement().scale(5.0));
        Vec3 desired = safeNormalize(shortLeadPoint
                .subtract(aircraft.getBoundingBox().getCenter()), targetDirection);
        Vec3 horizontalDesired = safeNormalize(horizontal(desired), snapshot.horizontalForward());
        double desiredYaw = Math.toDegrees(Math.atan2(-horizontalDesired.x, horizontalDesired.z));
        double headingError = Mth.wrapDegrees((float) (desiredYaw - snapshot.yawDeg()));
        float x = (float) Mth.clamp(headingError / 15.0, -0.92, 0.92);

        double targetAltitude = target.position().y + 8.0;
        double altitudeError = targetAltitude - snapshot.position().y;
        double desiredPitch = Mth.clamp(-altitudeError * 0.22
                + snapshot.verticalSpeedBps() * 0.24, -12.0, 8.0);
        if (snapshot.speedBps() < profile.stallGuardSpeedBps() * 1.30) {
            desiredPitch = Math.max(desiredPitch, -2.5);
            x *= 0.62f;
        }
        float z = (float) Mth.clamp((desiredPitch - snapshot.pitchDeg()) / 14.0,
                -0.84, 0.78);
        double targetSpeed = Math.max(profile.stallGuardSpeedBps() * 2.4,
                target.getDeltaMovement().horizontalDistance() * 20.0 + 1.0);
        float engineTarget = snapshot.speedBps() > targetSpeed + 3.0 ? 0.22f : 0.68f;

        FlightControlOutput output = new FlightControlOutput(x, 0.0f, z, engineTarget,
                horizontalDesired, targetAltitude, targetSpeed, headingError, altitudeError,
                targetSpeed - snapshot.speedBps(),
                snapshot.speedBps() < profile.stallGuardSpeedBps(), false,
                "energy_near_setup_capture", "protect_counterattack_transition_boundary");
        ReflectiveAircraft.applyControl(aircraft, -output.x(), output.y(), output.z(),
                output.engineTarget());
        AutopilotLogManager.writeControlAdapter(level.getServer(), aircraft, phase,
                description(state, rawTargetAngle), snapshot, baseline(snapshot), output);
        if (state.statusTicks++ % 5 == 0) {
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "energy_near_setup_capture_status",
                    description(state, rawTargetAngle), phase);
        }
    }

    private static void applyTightenedHighYoyo(ServerLevel level, Entity aircraft, Entity target,
                                                FlightSnapshot snapshot, FlightProfile profile,
                                                Vec3 targetDirection, double rawTargetAngle,
                                                State state, FlightPhase phase) {
        Vec3 shortLeadPoint = target.getBoundingBox().getCenter()
                .add(target.getDeltaMovement().scale(8.0));
        Vec3 desired = safeNormalize(shortLeadPoint
                .subtract(aircraft.getBoundingBox().getCenter()), targetDirection);
        Vec3 horizontalDesired = safeNormalize(horizontal(desired), snapshot.horizontalForward());
        double desiredYaw = Math.toDegrees(Math.atan2(-horizontalDesired.x, horizontalDesired.z));
        double headingError = Mth.wrapDegrees((float) (desiredYaw - snapshot.yawDeg()));

        float x = (float) (state.turnSign * 0.92);
        double targetAltitude = Math.max(target.position().y + 16.0,
                state.startAltitude + YOYO_ALTITUDE_GAIN);
        double altitudeError = targetAltitude - snapshot.position().y;
        double desiredPitch = Mth.clamp(-altitudeError * 0.30
                + snapshot.verticalSpeedBps() * 0.18, -17.0, 6.0);

        double targetSpeed = Math.max(profile.stallGuardSpeedBps() * 2.8,
                profile.turnSpeedFloorBps() * 0.90);
        float engineTarget;
        if (snapshot.speedBps() > targetSpeed + 1.5) {
            engineTarget = 0.25f;
        } else if (snapshot.speedBps() < targetSpeed - 1.0) {
            engineTarget = 1.0f;
        } else {
            engineTarget = 0.72f;
        }
        if (snapshot.speedBps() < profile.turnSpeedFloorBps() * 0.82) {
            desiredPitch = Math.max(desiredPitch, -2.0);
            x *= 0.62f;
            engineTarget = 1.0f;
        }

        float z = (float) Mth.clamp((desiredPitch - snapshot.pitchDeg()) / 13.0,
                -0.90, 0.76);
        FlightControlOutput output = new FlightControlOutput(x, 0.0f, z, engineTarget,
                horizontalDesired, targetAltitude, targetSpeed, headingError, altitudeError,
                targetSpeed - snapshot.speedBps(),
                snapshot.speedBps() < profile.stallGuardSpeedBps(), false,
                "energy_adaptive_high_yoyo", "broadside_plateau_turn_radius_tightening");
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
                    return new Target(living.getUUID(), targetAircraft);
                });
    }

    private static double retainedTurnSign(FlightSnapshot snapshot, Vec3 targetDirection) {
        if (Math.abs(snapshot.rollDeg()) >= 6.0) {
            return snapshot.rollDeg() >= 0.0 ? 1.0 : -1.0;
        }
        Vec3 horizontalTarget = safeNormalize(horizontal(targetDirection),
                snapshot.horizontalForward());
        double desiredYaw = Math.toDegrees(Math.atan2(-horizontalTarget.x, horizontalTarget.z));
        double headingError = Mth.wrapDegrees((float) (desiredYaw - snapshot.yawDeg()));
        return headingError >= 0.0 ? 1.0 : -1.0;
    }

    private static String description(State state, double rawTargetAngle) {
        return "ticks=" + state.ticks
                + ":override_ticks=" + state.overrideTicks
                + ":initial_raw_target_angle=" + round(state.initialRawTargetAngle)
                + ":best_raw_target_angle=" + round(state.bestRawTargetAngle)
                + ":raw_target_angle=" + round(rawTargetAngle)
                + ":progress=" + round(state.initialRawTargetAngle - state.bestRawTargetAngle)
                + ":plateau_ticks=" + state.plateauTicks
                + ":turn_sign=" + state.turnSign
                + ":near_setup_capture=" + state.nearSetupCapture
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

    private record Target(UUID pilotUuid, Entity aircraft) {
    }

    private static final class State {
        private final double initialRawTargetAngle;
        private final double startAltitude;
        private double bestRawTargetAngle;
        private double turnSign;
        private int ticks;
        private int plateauTicks;
        private int overrideTicks;
        private int statusTicks;
        private boolean overrideActive;
        private boolean nearSetupCapture;
        private boolean handedOff;

        private State(double initialRawTargetAngle, double startAltitude) {
            this.initialRawTargetAngle = initialRawTargetAngle;
            this.startAltitude = startAltitude;
            this.bestRawTargetAngle = initialRawTargetAngle;
        }
    }
}
