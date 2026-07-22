package com.wwdebug.autopilot;

import com.wwdebug.benchmark.ReflectiveAircraft;
import com.wwdebug.benchmark.ReflectiveArmament;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.util.Mth;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.phys.Vec3;

import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Converts a safe energy-fighter extension into a coupled climbing turn and lead capture.
 *
 * <p>Immersive Aircraft smooths X/Z input over ten ticks. Starting yaw only after reaching a
 * near-vertical apex therefore leaves the P-47N holding an energy-expensive attitude for too long.
 * This controller begins yaw during the latter part of a shallow climb, then uses damped pitch and
 * yaw control to capture the measured lead direction. A P-47N-only crossing plateau uses a bounded
 * lag before predictive approach; other energy fighters retain the original capture path. Terrain,
 * collision, threat, and real weapon gates remain authoritative.</p>
 */
public final class EnergyFighterApexYawAdapter {
    private static final double START_MIN_DISTANCE = 82.0;
    private static final double START_MAX_DISTANCE = 155.0;
    private static final double START_MAX_CLOSURE_BPS = 4.0;
    private static final double START_MIN_RAW_ANGLE_DEG = 70.0;
    private static final double START_MIN_ENERGY_RATIO = 1.0;
    private static final double START_MIN_AGL = 90.0;

    private static final double CLIMB_TARGET_PITCH_DEG = -22.0;
    private static final double YAW_TRIGGER_PITCH_DEG = -2.0;
    private static final int MIN_CLIMB_TICKS = 8;
    private static final int MAX_CLIMB_TICKS = 54;

    private static final double PIVOT_COMPLETE_HEADING_DEG = 65.0;
    private static final int MIN_PIVOT_TICKS = 8;
    private static final int MAX_PIVOT_TICKS = 96;
    private static final double PIVOT_INPUT_DIVISOR = 22.0;
    private static final double YAW_RATE_DAMPING = 0.05;

    private static final double CROSSING_ENTRY_MIN_RAW_ANGLE_DEG = 83.0;
    private static final double CROSSING_ENTRY_MAX_RAW_ANGLE_DEG = 90.0;
    private static final double CROSSING_ENTRY_MIN_CLOSURE_BPS = 0.0;
    private static final double CROSSING_IMPROVEMENT_EPSILON_DEG_PER_TICK = 0.10;
    private static final int CROSSING_STALL_TICKS = 2;
    private static final int LAG_TICKS = 30;
    private static final double LAG_YAW_FRACTION = 0.25;
    private static final double LAG_TARGET_PITCH_DEG = -32.0;
    private static final double APPROACH_LEAD_TICKS = 25.0;
    private static final double REENTRY_SPEED_FLOOR_BPS = 15.0;
    private static final double REENTRY_TARGET_SPEED_OFFSET_BPS = -6.0;
    private static final double REENTRY_MIN_AGL = 90.0;
    private static final double REENTRY_PULL_OUT_SECONDS = 4.2;

    private static final double LEAD_TICKS = 8.0;
    private static final double CAPTURE_PITCH_DIVISOR = 10.0;
    private static final double CAPTURE_PITCH_RATE_DAMPING = 0.10;
    private static final int MAX_CAPTURE_TICKS = 190;
    private static final int MAX_TOTAL_TICKS = 390;
    private static final int COOLDOWN_TICKS = 120;

    private static final double ATTACK_MAX_RAW_ANGLE_DEG = 45.0;
    private static final double ATTACK_MAX_LEAD_ANGLE_DEG = 12.0;
    private static final double ATTACK_MIN_DISTANCE = 24.0;
    private static final double ATTACK_MAX_DISTANCE = 125.0;
    private static final double ATTACK_MIN_CLOSURE_BPS = -6.0;
    private static final double ATTACK_MAX_CLOSURE_BPS = 28.0;

    private static final Map<UUID, State> STATES = new ConcurrentHashMap<>();
    private static final Map<UUID, Long> COOLDOWNS = new ConcurrentHashMap<>();

    private EnergyFighterApexYawAdapter() {
    }

    /** @return true when this controller owns aircraft input for the current tick */
    public static boolean applyControl(Entity aircraft) {
        if (!(aircraft.level() instanceof ServerLevel level) || aircraft.level().isClientSide
                || !ReflectiveAircraft.isAirplane(aircraft)
                || !ReflectiveAircraft.isControllable(aircraft)) {
            clear(aircraft.getUUID());
            return false;
        }

        Entity pilotEntity = aircraft.getControllingPassenger();
        Optional<AutonomousFlightManager.SessionStatus> session =
                AutonomousFlightManager.status(aircraft.getUUID());
        FlightProfile profile = AutopilotProfileRegistry.resolve(level.getServer(), aircraft)
                .orElse(null);
        if (pilotEntity instanceof Player || !(pilotEntity instanceof Mob pilot)
                || session.isEmpty() || profile == null || aircraft.onGround()
                || !eligiblePhase(session.get().phase())
                || !"energy_fighter".equalsIgnoreCase(profile.doctrine())
                || TerrainAvoidancePlanner.active(aircraft)
                || AirspaceSafetyProbe.collisionRisk(aircraft)) {
            finish(level, aircraft, session.map(AutonomousFlightManager.SessionStatus::phase)
                    .orElse(FlightPhase.ABORTED), "not_eligible", true);
            return false;
        }

        Target target = target(level, aircraft).orElse(null);
        State state = STATES.get(aircraft.getUUID());
        if (target == null) {
            finish(level, aircraft, session.get().phase(), "target_lost", true);
            return false;
        }

        FlightSnapshot snapshot = FlightSnapshot.capture(aircraft);
        Vec3 targetDirection = directionTo(aircraft, target.aircraft(), snapshot.forward());
        Vec3 leadDirection = leadDirection(aircraft, target.aircraft(), targetDirection, LEAD_TICKS);
        Vec3 approachLeadDirection = leadDirection(
                aircraft, target.aircraft(), targetDirection, APPROACH_LEAD_TICKS);
        double rawAngle = angleDegrees(snapshot.forward(), targetDirection);
        double leadAngle = angleDegrees(snapshot.forward(), leadDirection);
        double distance = aircraft.distanceTo(target.aircraft());
        double closure = relativeClosureBps(aircraft, target.aircraft());
        ThreatView threat = attackerThreat(target.aircraft(), pilot.getUUID());

        if (state == null) {
            if (!canStart(level, aircraft, target, snapshot, profile, rawAngle,
                    distance, closure, threat)) {
                return false;
            }
            Vec3 horizontalLead = safeNormalize(horizontal(leadDirection),
                    snapshot.horizontalForward());
            double headingError = signedHorizontalAngle(
                    snapshot.horizontalForward(), horizontalLead);
            double turnSign = Math.abs(headingError) > 1.0
                    ? Math.copySign(1.0, headingError)
                    : crossingTurnSign(snapshot, targetDirection,
                    FlightSnapshot.capture(target.aircraft()).rollDeg());
            state = new State(target.pilotUuid(),
                    ReflectiveArmament.estimatedShotsRemaining(aircraft), turnSign,
                    snapshot.position().y, snapshot.altitudeAboveGround(),
                    snapshot.yawDeg(), snapshot.pitchDeg(), rawAngle);
            STATES.put(aircraft.getUUID(), state);
            DefensiveAirCombatManager.clear(aircraft.getUUID());
            AirCombatManeuverManager.clear(aircraft.getUUID());
            writeEvent(level, aircraft, session.get().phase(), "energy_coupled_climb_start",
                    state, snapshot, distance, rawAngle, leadAngle, closure,
                    threat.aimAngleDeg(), "safe_extension");
        }

        if (!state.targetPilotUuid.equals(target.pilotUuid())) {
            finish(level, aircraft, session.get().phase(), "target_changed", true);
            return false;
        }
        if (ReflectiveArmament.estimatedShotsRemaining(aircraft) < state.initialShots) {
            finish(level, aircraft, session.get().phase(), "fire_confirmed", true);
            return false;
        }
        if (state.totalTicks >= MAX_TOTAL_TICKS) {
            finish(level, aircraft, session.get().phase(), "total_timeout", true);
            return false;
        }
        if (credibleThreat(distance, closure, rawAngle, threat)) {
            finish(level, aircraft, session.get().phase(), "credible_threat_restored", true);
            return false;
        }

        DefensiveAirCombatManager.clear(aircraft.getUUID());

        double pitchRateDegPerTick = snapshot.pitchDeg() - state.lastPitchDeg;
        double yawRateDegPerTick = Mth.wrapDegrees(
                (float) (snapshot.yawDeg() - state.lastYawDeg));
        state.lastRawAngleImprovementDeg = state.lastRawAngleDeg - rawAngle;
        state.lastRawAngleDeg = rawAngle;
        state.lastPitchDeg = snapshot.pitchDeg();
        state.lastYawDeg = snapshot.yawDeg();

        if (state.stage == Stage.PIVOT
                && rawAngle >= CROSSING_ENTRY_MIN_RAW_ANGLE_DEG
                && rawAngle <= CROSSING_ENTRY_MAX_RAW_ANGLE_DEG
                && Math.abs(state.lastRawAngleImprovementDeg)
                <= CROSSING_IMPROVEMENT_EPSILON_DEG_PER_TICK) {
            state.crossingStallTicks++;
        } else {
            state.crossingStallTicks = 0;
        }

        double horizontalLeadError = signedHorizontalAngle(
                snapshot.horizontalForward(),
                safeNormalize(horizontal(leadDirection), snapshot.horizontalForward()));
        double approachHorizontalLeadError = signedHorizontalAngle(
                snapshot.horizontalForward(),
                safeNormalize(horizontal(approachLeadDirection),
                        snapshot.horizontalForward()));

        if (state.stage == Stage.CLIMB) {
            boolean yawWindowReached = state.stageTicks >= MIN_CLIMB_TICKS
                    && snapshot.pitchDeg() <= YAW_TRIGGER_PITCH_DEG;
            boolean energyGuard = state.stageTicks >= MIN_CLIMB_TICKS
                    && snapshot.speedBps() <= profile.stallGuardSpeedBps() * 1.60;
            if (yawWindowReached || energyGuard) {
                state.pivotStartYaw = snapshot.yawDeg();
                transition(level, aircraft, session.get().phase(), state, snapshot,
                        distance, rawAngle, leadAngle, closure, threat.aimAngleDeg(),
                        Stage.PIVOT,
                        yawWindowReached ? "overlap_yaw_window_reached" : "climb_energy_guard");
            } else if (state.stageTicks >= MAX_CLIMB_TICKS) {
                finish(level, aircraft, session.get().phase(), "climb_timeout", true);
                return false;
            }
        }

        if (state.stage == Stage.PIVOT) {
            state.maxYawChangeDeg = Math.max(state.maxYawChangeDeg,
                    Math.abs(Mth.wrapDegrees(
                            (float) (snapshot.yawDeg() - state.pivotStartYaw))));
            boolean headingCaptured = state.stageTicks >= MIN_PIVOT_TICKS
                    && Math.abs(horizontalLeadError) <= PIVOT_COMPLETE_HEADING_DEG;
            boolean energyGuard = state.stageTicks >= MIN_PIVOT_TICKS
                    && snapshot.speedBps() <= profile.stallGuardSpeedBps() * 1.45;
            boolean crossingStalled = isP47n(profile)
                    && state.stageTicks >= MIN_PIVOT_TICKS
                    && state.crossingStallTicks >= CROSSING_STALL_TICKS
                    && closure >= CROSSING_ENTRY_MIN_CLOSURE_BPS;
            if (energyGuard) {
                transition(level, aircraft, session.get().phase(), state, snapshot,
                        distance, rawAngle, leadAngle, closure, threat.aimAngleDeg(),
                        Stage.CAPTURE, "pivot_energy_guard");
            } else if (crossingStalled) {
                transition(level, aircraft, session.get().phase(), state, snapshot,
                        distance, rawAngle, leadAngle, closure, threat.aimAngleDeg(),
                        Stage.LAG, "crossing_angle_stalled");
            } else if (headingCaptured) {
                transition(level, aircraft, session.get().phase(), state, snapshot,
                        distance, rawAngle, leadAngle, closure, threat.aimAngleDeg(),
                        Stage.CAPTURE, "horizontal_lead_captured");
            } else if (state.stageTicks >= MAX_PIVOT_TICKS) {
                finish(level, aircraft, session.get().phase(), "pivot_timeout", true);
                return false;
            }
        }

        if (state.stage == Stage.LAG && state.stageTicks >= LAG_TICKS) {
            transition(level, aircraft, session.get().phase(), state, snapshot,
                    distance, rawAngle, leadAngle, closure, threat.aimAngleDeg(),
                    Stage.APPROACH, "bounded_lag_complete");
        }

        if ((state.stage == Stage.LAG || state.stage == Stage.APPROACH)
                && snapshot.speedBps() <= profile.stallGuardSpeedBps() * 1.45) {
            finish(level, aircraft, session.get().phase(), "reentry_energy_guard", true);
            return false;
        }
        if ((state.stage == Stage.LAG || state.stage == Stage.APPROACH)
                && !hasPullOutMargin(snapshot)) {
            finish(level, aircraft, session.get().phase(), "reentry_pull_out_guard", true);
            return false;
        }

        if (state.stage == Stage.CAPTURE || state.stage == Stage.APPROACH) {
            boolean attackSector = target.lineOfSight()
                    && rawAngle <= ATTACK_MAX_RAW_ANGLE_DEG
                    && leadAngle <= ATTACK_MAX_LEAD_ANGLE_DEG
                    && distance >= ATTACK_MIN_DISTANCE && distance <= ATTACK_MAX_DISTANCE
                    && closure >= ATTACK_MIN_CLOSURE_BPS
                    && closure <= ATTACK_MAX_CLOSURE_BPS;
            if (attackSector) {
                transition(level, aircraft, session.get().phase(), state, snapshot,
                        distance, rawAngle, leadAngle, closure, threat.aimAngleDeg(),
                        Stage.DOCTRINE, "attack_sector_reached");
            } else if (state.stageTicks >= MAX_CAPTURE_TICKS || distance > 190.0) {
                finish(level, aircraft, session.get().phase(), "capture_timeout", true);
                return false;
            }
        }

        state.minimumAgl = Math.min(state.minimumAgl, snapshot.altitudeAboveGround());
        state.maximumAltitude = Math.max(state.maximumAltitude, snapshot.position().y);

        switch (state.stage) {
            case CLIMB -> applyClimb(level, aircraft, snapshot, profile, state,
                    pitchRateDegPerTick, rawAngle, leadAngle, closure,
                    session.get().phase());
            case PIVOT -> applyPivot(level, aircraft, snapshot, profile,
                    horizontalLeadError, yawRateDegPerTick, pitchRateDegPerTick,
                     state, rawAngle, leadAngle, closure, session.get().phase());
            case LAG -> applyLag(level, aircraft, target.aircraft(), snapshot, profile,
                    targetDirection, yawRateDegPerTick, pitchRateDegPerTick,
                    state, rawAngle, leadAngle, closure, session.get().phase());
            case CAPTURE -> applyCapture(level, aircraft, target.aircraft(), snapshot, profile,
                    leadDirection, horizontalLeadError, yawRateDegPerTick,
                    pitchRateDegPerTick, state, rawAngle, leadAngle, closure,
                    session.get().phase());
            case APPROACH -> applyApproach(level, aircraft, target.aircraft(), snapshot, profile,
                    approachLeadDirection, approachHorizontalLeadError, yawRateDegPerTick,
                    pitchRateDegPerTick, state, rawAngle, leadAngle, closure,
                    session.get().phase());
            case DOCTRINE -> {
                AirCombatManeuverManager.applyControl(aircraft);
                applyFinalAlignment(level, aircraft, target, snapshot, profile,
                        rawAngle, closure, state, session.get().phase());
            }
        }

        state.totalTicks++;
        state.stageTicks++;
        if (state.statusTicks++ % 10 == 0) {
            writeEvent(level, aircraft, session.get().phase(), "energy_coupled_climb_status",
                    state, snapshot, distance, rawAngle, leadAngle, closure,
                    threat.aimAngleDeg(), "active");
        }
        return true;
    }

    private static boolean canStart(ServerLevel level, Entity aircraft, Target target,
                                    FlightSnapshot snapshot, FlightProfile profile,
                                    double rawAngle, double distance, double closure,
                                    ThreatView threat) {
        long now = level.getGameTime();
        Long cooldown = COOLDOWNS.get(aircraft.getUUID());
        if (cooldown != null && now < cooldown) {
            return false;
        }
        if (cooldown != null) {
            COOLDOWNS.remove(aircraft.getUUID(), cooldown);
        }
        double energyRatio = snapshot.speedBps() / Math.max(1.0, profile.cruiseSpeedBps());
        boolean priorCombat = DefensiveAirCombatManager.active(aircraft)
                || AirCombatManeuverManager.active(aircraft);
        return priorCombat && target.lineOfSight()
                && distance >= START_MIN_DISTANCE && distance <= START_MAX_DISTANCE
                && closure <= START_MAX_CLOSURE_BPS
                && rawAngle >= START_MIN_RAW_ANGLE_DEG
                && energyRatio >= START_MIN_ENERGY_RATIO
                && snapshot.altitudeAboveGround() >= START_MIN_AGL
                && threat.aimAngleDeg() >= 8.0;
    }

    private static void applyClimb(ServerLevel level, Entity aircraft,
                                   FlightSnapshot snapshot, FlightProfile profile, State state,
                                   double pitchRate, double rawAngle, double leadAngle,
                                   double closure, FlightPhase phase) {
        float z = (float) Mth.clamp(
                (CLIMB_TARGET_PITCH_DEG - snapshot.pitchDeg()) / 12.0
                        - 0.25 * pitchRate,
                -0.95, 0.35);
        FlightControlOutput output = new FlightControlOutput(0.0f, 0.0f, z, 1.0f,
                snapshot.horizontalForward(), state.startAltitude + 35.0,
                Math.max(profile.climbTargetSpeedBps(), profile.cruiseSpeedBps()),
                0.0, state.startAltitude + 35.0 - snapshot.position().y,
                profile.climbTargetSpeedBps() - snapshot.speedBps(),
                snapshot.speedBps() < profile.stallGuardSpeedBps(), false,
                "energy_coupled_climb", "shallow_climb_before_yaw_overlap");
        applyAndLog(level, aircraft, snapshot, output, state,
                rawAngle, leadAngle, closure, phase);
    }

    private static void applyPivot(ServerLevel level, Entity aircraft,
                                   FlightSnapshot snapshot, FlightProfile profile,
                                   double headingError, double yawRate, double pitchRate,
                                   State state, double rawAngle, double leadAngle,
                                   double closure, FlightPhase phase) {
        float x = (float) Mth.clamp(
                headingError / PIVOT_INPUT_DIVISOR - YAW_RATE_DAMPING * yawRate,
                -0.96, 0.96);
        float z = (float) Mth.clamp(
                (CLIMB_TARGET_PITCH_DEG - snapshot.pitchDeg()) / 12.0
                        - 0.30 * pitchRate,
                -0.65, 0.65);
        FlightControlOutput output = new FlightControlOutput(x, 0.0f, z, 1.0f,
                snapshot.horizontalForward(), state.startAltitude + 35.0,
                Math.max(profile.climbTargetSpeedBps(), profile.turnSpeedFloorBps()),
                headingError, state.startAltitude + 35.0 - snapshot.position().y,
                profile.turnSpeedFloorBps() - snapshot.speedBps(),
                snapshot.speedBps() < profile.stallGuardSpeedBps(), false,
                "energy_coupled_pivot", "yaw_overlapped_with_shallow_climb");
        applyAndLog(level, aircraft, snapshot, output, state,
                rawAngle, leadAngle, closure, phase);
    }

    private static void applyLag(ServerLevel level, Entity aircraft, Entity target,
                                 FlightSnapshot snapshot, FlightProfile profile,
                                 Vec3 targetDirection, double yawRate, double pitchRate,
                                 State state, double rawAngle, double leadAngle,
                                 double closure, FlightPhase phase) {
        double headingError = signedHorizontalAngle(
                snapshot.horizontalForward(),
                safeNormalize(horizontal(targetDirection), snapshot.horizontalForward()));
        float fullYaw = (float) Mth.clamp(
                headingError / PIVOT_INPUT_DIVISOR - YAW_RATE_DAMPING * yawRate,
                -0.96, 0.96);
        float x = fullYaw * (float) LAG_YAW_FRACTION;
        float z = (float) Mth.clamp(
                (LAG_TARGET_PITCH_DEG - snapshot.pitchDeg()) / 12.0
                        - 0.30 * pitchRate,
                -0.95, 0.65);
        double targetAltitude = target.getBoundingBox().getCenter().y + 4.0;
        double targetSpeed = reentryTargetSpeed(target);
        float engine = reentryEngine(snapshot.speedBps(), targetSpeed);
        FlightControlOutput output = new FlightControlOutput(x, 0.0f, z, engine,
                targetDirection, targetAltitude, targetSpeed,
                headingError, targetAltitude - snapshot.position().y,
                targetSpeed - snapshot.speedBps(),
                snapshot.speedBps() < profile.stallGuardSpeedBps(), false,
                "energy_coupled_lag", "bounded_oblique_lag_after_crossing_stall");
        applyAndLog(level, aircraft, snapshot, output, state,
                rawAngle, leadAngle, closure, phase);
    }

    private static void applyApproach(ServerLevel level, Entity aircraft, Entity target,
                                      FlightSnapshot snapshot, FlightProfile profile,
                                      Vec3 approachLeadDirection, double headingError,
                                      double yawRate, double pitchRate, State state,
                                      double rawAngle, double leadAngle, double closure,
                                      FlightPhase phase) {
        float x = (float) Mth.clamp(
                headingError / 18.0 - YAW_RATE_DAMPING * yawRate,
                -0.94, 0.94);
        double desiredPitch = desiredPitchDegrees(approachLeadDirection);
        float z = (float) Mth.clamp(
                (desiredPitch - snapshot.pitchDeg()) / CAPTURE_PITCH_DIVISOR
                        - CAPTURE_PITCH_RATE_DAMPING * pitchRate,
                -0.88, 0.88);
        double targetAltitude = target.getBoundingBox().getCenter().y + 4.0;
        double targetSpeed = reentryTargetSpeed(target);
        float engine = reentryEngine(snapshot.speedBps(), targetSpeed);
        FlightControlOutput output = new FlightControlOutput(x, 0.0f, z, engine,
                approachLeadDirection, targetAltitude, targetSpeed,
                headingError, targetAltitude - snapshot.position().y,
                targetSpeed - snapshot.speedBps(),
                snapshot.speedBps() < profile.stallGuardSpeedBps(), false,
                "energy_coupled_approach", "predicted_lead_capture_after_bounded_lag");
        applyAndLog(level, aircraft, snapshot, output, state,
                rawAngle, leadAngle, closure, phase);
    }

    private static double reentryTargetSpeed(Entity target) {
        return Math.max(REENTRY_SPEED_FLOOR_BPS,
                target.getDeltaMovement().horizontalDistance() * 20.0
                        + REENTRY_TARGET_SPEED_OFFSET_BPS);
    }

    private static float reentryEngine(double speedBps, double targetSpeedBps) {
        if (speedBps < targetSpeedBps - 1.0) {
            return 1.0f;
        }
        return speedBps > targetSpeedBps + 3.0 ? 0.10f : 0.35f;
    }

    private static boolean hasPullOutMargin(FlightSnapshot snapshot) {
        return snapshot.altitudeAboveGround() >= requiredPullOutAgl(snapshot);
    }

    private static double requiredPullOutAgl(FlightSnapshot snapshot) {
        return Math.max(REENTRY_MIN_AGL,
                Math.max(0.0, -snapshot.verticalSpeedBps()) * REENTRY_PULL_OUT_SECONDS);
    }

    private static boolean isP47n(FlightProfile profile) {
        return "warfare_wings".equals(profile.profileId().getNamespace())
                && "p47n".equals(profile.profileId().getPath());
    }

    private static void applyCapture(ServerLevel level, Entity aircraft, Entity target,
                                     FlightSnapshot snapshot, FlightProfile profile,
                                     Vec3 leadDirection, double headingError,
                                     double yawRate, double pitchRate, State state,
                                     double rawAngle, double leadAngle, double closure,
                                     FlightPhase phase) {
        float x = (float) Mth.clamp(
                headingError / 18.0 - YAW_RATE_DAMPING * yawRate,
                -0.94, 0.94);
        double desiredPitch = desiredPitchDegrees(leadDirection);
        float z = (float) Mth.clamp(
                (desiredPitch - snapshot.pitchDeg()) / CAPTURE_PITCH_DIVISOR
                        - CAPTURE_PITCH_RATE_DAMPING * pitchRate,
                -0.88, 0.88);
        double targetAltitude = target.getBoundingBox().getCenter().y + 4.0;
        double altitudeError = targetAltitude - snapshot.position().y;
        double targetSpeed = Math.max(profile.cruiseSpeedBps(),
                target.getDeltaMovement().horizontalDistance() * 20.0 + 3.0);
        float engine = snapshot.speedBps() < targetSpeed - 1.0 ? 1.0f
                : snapshot.speedBps() > targetSpeed + 3.0 ? 0.30f : 0.65f;
        FlightControlOutput output = new FlightControlOutput(x, 0.0f, z, engine,
                leadDirection, targetAltitude, targetSpeed,
                headingError, altitudeError, targetSpeed - snapshot.speedBps(),
                snapshot.speedBps() < profile.stallGuardSpeedBps(), false,
                "energy_coupled_capture", "damped_vector_capture_after_climbing_turn");
        applyAndLog(level, aircraft, snapshot, output, state,
                rawAngle, leadAngle, closure, phase);
    }

    private static void applyFinalAlignment(ServerLevel level, Entity aircraft, Target target,
                                            FlightSnapshot snapshot, FlightProfile profile,
                                            double rawAngle, double closure, State state,
                                            FlightPhase phase) {
        Optional<AirCombatManeuverManager.AimSolution> aim =
                AirCombatManeuverManager.currentAim(aircraft.getUUID(), target.pilotUuid());
        if (aim.isEmpty() || !target.lineOfSight()
                || aim.get().distanceBlocks() < ATTACK_MIN_DISTANCE
                || aim.get().distanceBlocks() > 170.0
                || aim.get().angleOffNoseDeg() < 3.0
                || aim.get().angleOffNoseDeg() > ATTACK_MAX_LEAD_ANGLE_DEG
                || rawAngle > ATTACK_MAX_RAW_ANGLE_DEG
                || closure < ATTACK_MIN_CLOSURE_BPS) {
            return;
        }
        Vec3 desired = aim.get().direction();
        double headingError = signedHorizontalAngle(
                snapshot.horizontalForward(),
                safeNormalize(horizontal(desired), snapshot.horizontalForward()));
        float x = (float) Mth.clamp(headingError / 9.0, -0.94, 0.94);
        double desiredPitch = desiredPitchDegrees(desired);
        float z = (float) Mth.clamp(
                (desiredPitch - snapshot.pitchDeg()) / 10.0,
                -0.86, 0.86);
        double targetAltitude = aim.get().aimPoint().y;
        double altitudeError = targetAltitude - snapshot.position().y;
        double targetSpeed = Math.max(profile.cruiseSpeedBps(),
                target.aircraft().getDeltaMovement().horizontalDistance() * 20.0);
        float engine = closure > 24.0 ? 0.18f
                : snapshot.speedBps() < targetSpeed - 1.0 ? 0.90f : 0.45f;
        FlightControlOutput output = new FlightControlOutput(x, 0.0f, z, engine,
                desired, targetAltitude, targetSpeed,
                headingError, altitudeError, targetSpeed - snapshot.speedBps(),
                snapshot.speedBps() < profile.stallGuardSpeedBps(), false,
                "energy_coupled_final_alignment", "real_weapon_alignment");
        applyAndLog(level, aircraft, snapshot, output, state,
                rawAngle, aim.get().angleOffNoseDeg(), closure, phase);
    }

    private static void transition(ServerLevel level, Entity aircraft, FlightPhase phase,
                                   State state, FlightSnapshot snapshot, double distance,
                                   double rawAngle, double leadAngle, double closure,
                                   double attackerAim, Stage next, String reason) {
        state.stage = next;
        state.stageTicks = 0;
        AirCombatManeuverManager.clear(aircraft.getUUID());
        writeEvent(level, aircraft, phase, "energy_coupled_climb_transition",
                state, snapshot, distance, rawAngle, leadAngle, closure,
                attackerAim, reason);
    }

    private static void applyAndLog(ServerLevel level, Entity aircraft, FlightSnapshot snapshot,
                                    FlightControlOutput output, State state, double rawAngle,
                                    double leadAngle, double closure, FlightPhase phase) {
        ReflectiveAircraft.applyControl(aircraft, -output.x(), output.y(), output.z(),
                output.engineTarget());
        AutopilotLogManager.writeControlAdapter(level.getServer(), aircraft, phase,
                description(state, snapshot, rawAngle, leadAngle, closure),
                snapshot, baseline(snapshot), output);
    }

    private static String description(State state, FlightSnapshot snapshot,
                                      double rawAngle, double leadAngle, double closure) {
        return "stage=" + state.stage
                + ":total_ticks=" + state.totalTicks
                + ":stage_ticks=" + state.stageTicks
                + ":raw_target_angle=" + round(rawAngle)
                + ":raw_angle_improvement=" + round(state.lastRawAngleImprovementDeg)
                + ":crossing_stall_ticks=" + state.crossingStallTicks
                + ":predicted_lead_angle=" + round(leadAngle)
                + ":closure=" + round(closure)
                + ":speed_bps=" + round(snapshot.speedBps())
                + ":vertical_speed_bps=" + round(snapshot.verticalSpeedBps())
                + ":pitch=" + round(snapshot.pitchDeg())
                + ":yaw=" + round(snapshot.yawDeg())
                + ":roll=" + round(snapshot.rollDeg())
                + ":agl=" + round(snapshot.altitudeAboveGround())
                + ":required_pull_out_agl=" + round(requiredPullOutAgl(snapshot))
                + ":turn_sign=" + state.turnSign
                + ":max_yaw_change=" + round(state.maxYawChangeDeg);
    }

    private static void writeEvent(ServerLevel level, Entity aircraft, FlightPhase phase,
                                   String event, State state, FlightSnapshot snapshot,
                                   double distance, double rawAngle, double leadAngle,
                                   double closure, double attackerAim, String reason) {
        AutopilotLogManager.writeEvent(level.getServer(), aircraft, event,
                description(state, snapshot, rawAngle, leadAngle, closure)
                        + ":distance=" + round(distance)
                        + ":attacker_aim_angle=" + round(attackerAim)
                        + ":start_altitude=" + round(state.startAltitude)
                        + ":maximum_altitude=" + round(state.maximumAltitude)
                        + ":minimum_agl=" + round(state.minimumAgl)
                        + ":reason=" + reason,
                phase);
    }

    private static Optional<Target> target(ServerLevel level, Entity aircraft) {
        return CombatAwarenessManager.currentSolution(aircraft.getUUID())
                .map(solution -> {
                    Entity pilot = level.getEntity(solution.targetUuid());
                    if (!(pilot instanceof LivingEntity living) || !living.isAlive()) {
                        return null;
                    }
                    Entity targetAircraft = living.getVehicle();
                    return targetAircraft != null && ReflectiveAircraft.isAirplane(targetAircraft)
                            ? new Target(living.getUUID(), targetAircraft, solution.lineOfSight())
                            : null;
                });
    }

    private static ThreatView attackerThreat(Entity attacker, UUID defenderPilotUuid) {
        Optional<CombatTargetSelector.Solution> selected =
                CombatAwarenessManager.currentSolution(attacker.getUUID())
                        .filter(solution -> solution.targetUuid().equals(defenderPilotUuid));
        double aim = AirCombatManeuverManager.currentAim(attacker.getUUID(), defenderPilotUuid)
                .map(AirCombatManeuverManager.AimSolution::angleOffNoseDeg)
                .orElseGet(() -> selected.map(CombatTargetSelector.Solution::angleOffNoseDeg)
                        .orElse(180.0));
        return new ThreatView(aim, selected.map(CombatTargetSelector.Solution::lineOfSight)
                .orElse(false));
    }

    private static boolean credibleThreat(double distance, double closure, double rawAngle,
                                           ThreatView threat) {
        if (!threat.lineOfSight() || rawAngle <= 58.0) {
            return false;
        }
        return (distance <= 82.0 && threat.aimAngleDeg() <= 3.2)
                || (distance <= 105.0 && closure >= 8.0 && threat.aimAngleDeg() <= 5.0);
    }

    private static double crossingTurnSign(FlightSnapshot snapshot, Vec3 direction,
                                           double targetRoll) {
        if (Math.abs(targetRoll) >= 4.0) {
            return targetRoll < 0.0 ? -1.0 : 1.0;
        }
        return signedHorizontalAngle(snapshot.horizontalForward(),
                safeNormalize(horizontal(direction), snapshot.horizontalForward())) >= 0.0
                ? 1.0 : -1.0;
    }

    private static Vec3 directionTo(Entity from, Entity to, Vec3 fallback) {
        return safeNormalize(to.getBoundingBox().getCenter()
                .subtract(from.getBoundingBox().getCenter()), fallback);
    }

    private static Vec3 leadDirection(Entity aircraft, Entity target,
                                      Vec3 fallback, double leadTicks) {
        Vec3 leadPoint = target.getBoundingBox().getCenter()
                .add(target.getDeltaMovement().scale(leadTicks));
        return safeNormalize(leadPoint.subtract(aircraft.getBoundingBox().getCenter()), fallback);
    }

    private static double relativeClosureBps(Entity defender, Entity attacker) {
        Vec3 line = attacker.position().subtract(defender.position());
        if (line.lengthSqr() < 1.0e-8) {
            return 0.0;
        }
        return -attacker.getDeltaMovement().subtract(defender.getDeltaMovement())
                .scale(20.0).dot(line.normalize());
    }

    private static double desiredPitchDegrees(Vec3 direction) {
        Vec3 normalized = safeNormalize(direction, new Vec3(0.0, 0.0, 1.0));
        return -Math.toDegrees(Math.asin(Mth.clamp(normalized.y, -1.0, 1.0)));
    }

    private static double signedHorizontalAngle(Vec3 current, Vec3 desired) {
        Vec3 from = safeNormalize(horizontal(current), new Vec3(0.0, 0.0, 1.0));
        Vec3 to = safeNormalize(horizontal(desired), from);
        double dot = Mth.clamp(from.dot(to), -1.0, 1.0);
        double cross = from.x * to.z - from.z * to.x;
        return Math.toDegrees(Math.atan2(cross, dot));
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

    private static boolean eligiblePhase(FlightPhase phase) {
        return phase.isAirborneMissionPhase() && !phase.isLandingPhase()
                && phase != FlightPhase.STALL_ENTRY && phase != FlightPhase.STALL_RECOVERY;
    }

    private static void finish(ServerLevel level, Entity aircraft, FlightPhase phase,
                               String reason, boolean cooldown) {
        State removed = STATES.remove(aircraft.getUUID());
        if (removed != null) {
            if (cooldown) {
                COOLDOWNS.put(aircraft.getUUID(), level.getGameTime() + COOLDOWN_TICKS);
            }
            FlightSnapshot snapshot = FlightSnapshot.capture(aircraft);
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "energy_coupled_climb_end",
                    description(removed, snapshot, 0.0, 0.0, 0.0)
                            + ":start_altitude=" + round(removed.startAltitude)
                            + ":maximum_altitude=" + round(removed.maximumAltitude)
                            + ":minimum_agl=" + round(removed.minimumAgl)
                            + ":reason=" + reason,
                    phase);
        }
    }

    public static boolean active(Entity aircraft) {
        return STATES.containsKey(aircraft.getUUID());
    }

    public static void clear(UUID aircraftUuid) {
        STATES.remove(aircraftUuid);
        COOLDOWNS.remove(aircraftUuid);
    }

    private static double round(double value) {
        return Math.rint(value * 100.0) / 100.0;
    }

    private enum Stage {
        CLIMB,
        PIVOT,
        LAG,
        CAPTURE,
        APPROACH,
        DOCTRINE
    }

    private record Target(UUID pilotUuid, Entity aircraft, boolean lineOfSight) {
    }

    private record ThreatView(double aimAngleDeg, boolean lineOfSight) {
    }

    private static final class State {
        private final UUID targetPilotUuid;
        private final int initialShots;
        private final double turnSign;
        private final double startAltitude;
        private Stage stage = Stage.CLIMB;
        private double pivotStartYaw;
        private double maxYawChangeDeg;
        private double maximumAltitude;
        private double minimumAgl;
        private double lastYawDeg;
        private double lastPitchDeg;
        private double lastRawAngleDeg;
        private double lastRawAngleImprovementDeg;
        private int totalTicks;
        private int stageTicks;
        private int statusTicks;
        private int crossingStallTicks;

        private State(UUID targetPilotUuid, int initialShots, double turnSign,
                      double startAltitude, double startAgl,
                      double startYaw, double startPitch, double startRawAngle) {
            this.targetPilotUuid = targetPilotUuid;
            this.initialShots = initialShots;
            this.turnSign = turnSign;
            this.startAltitude = startAltitude;
            this.pivotStartYaw = startYaw;
            this.maximumAltitude = startAltitude;
            this.minimumAgl = startAgl;
            this.lastYawDeg = startYaw;
            this.lastPitchDeg = startPitch;
            this.lastRawAngleDeg = startRawAngle;
        }
    }
}
