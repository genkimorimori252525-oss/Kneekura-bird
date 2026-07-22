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
 * Converts recovered separation into an early powered reversal and high-energy lead recovery.
 * Safety and actual weapon gates remain authoritative outside this controller.
 */
public final class EnergyFighterReengagementAdapter {
    private static final double START_MIN_DISTANCE = 88.0;
    private static final double START_MAX_DISTANCE = 155.0;
    private static final double START_MIN_ENERGY_RATIO = 1.02;

    private static final double FORWARD_HANDOFF_ANGLE_DEG = 60.0;
    private static final double EARLY_WINGOVER_RAW_ANGLE_DEG = 115.0;
    private static final double EARLY_WINGOVER_MIN_CLOSURE_BPS = 0.0;
    private static final double EARLY_WINGOVER_MIN_DISTANCE = 70.0;
    private static final double EARLY_WINGOVER_MAX_DISTANCE = 150.0;
    private static final double ADAPTIVE_HANDOFF_MAX_ANGLE_DEG = 90.0;
    private static final double IMPROVEMENT_EPSILON_DEG = 0.35;
    private static final double ADAPTIVE_MAX_REGRESSION_DEG = 2.5;
    private static final int ADAPTIVE_STALL_TICKS = 6;
    private static final int MIN_CROSS_TICKS = 20;
    private static final int MAX_CROSS_TICKS = 150;

    private static final int MIN_WINGOVER_TICKS = 70;
    private static final int MAX_WINGOVER_TICKS = 170;
    private static final double WINGOVER_COMPLETE_ANGLE_DEG = 150.0;
    private static final double WINGOVER_DESCENDING_FORWARD_Y = -0.10;
    private static final double WINGOVER_SPEED_BPS = 34.0;
    private static final double WINGOVER_TURN_START_ANGLE_DEG = 95.0;
    private static final double WINGOVER_TURN_FULL_ANGLE_DEG = 145.0;
    private static final double WINGOVER_MAX_TURN_INPUT = 0.58;
    private static final double LEAD_TICKS = 10.0;
    private static final int MAX_RECOVERY_TICKS = 220;

    private static final double ATTACK_MAX_RAW_ANGLE_DEG = 45.0;
    private static final double ATTACK_MAX_LEAD_ANGLE_DEG = 12.0;
    private static final double ATTACK_MIN_DISTANCE = 24.0;
    private static final double ATTACK_MAX_DISTANCE = 125.0;
    private static final double ATTACK_MIN_CLOSURE_BPS = -6.0;
    private static final double ATTACK_MAX_CLOSURE_BPS = 28.0;
    private static final int MAX_TOTAL_TICKS = 430;

    private static final Map<UUID, State> STATES = new ConcurrentHashMap<>();

    private EnergyFighterReengagementAdapter() {
    }

    /** @return true when this controller owns combat input for the current tick */
    public static boolean applyControl(Entity aircraft) {
        if (!(aircraft.level() instanceof ServerLevel level) || aircraft.level().isClientSide
                || !ReflectiveAircraft.isAirplane(aircraft)
                || !ReflectiveAircraft.isControllable(aircraft)) {
            clear(aircraft.getUUID());
            return false;
        }

        Entity pilotEntity = aircraft.getControllingPassenger();
        Optional<AutonomousFlightManager.SessionStatus> status =
                AutonomousFlightManager.status(aircraft.getUUID());
        FlightProfile profile = AutopilotProfileRegistry.resolve(level.getServer(), aircraft)
                .orElse(null);
        if (pilotEntity instanceof Player || !(pilotEntity instanceof Mob pilot)
                || status.isEmpty() || profile == null || aircraft.onGround()
                || !eligiblePhase(status.get().phase())
                || !"energy_fighter".equalsIgnoreCase(profile.doctrine())
                || TerrainAvoidancePlanner.active(aircraft)
                || AirspaceSafetyProbe.collisionRisk(aircraft)) {
            finish(level, aircraft, status.map(AutonomousFlightManager.SessionStatus::phase)
                    .orElse(FlightPhase.ABORTED), "not_eligible");
            return false;
        }

        Target target = target(level, aircraft).orElse(null);
        State state = STATES.get(aircraft.getUUID());
        if (target == null) {
            finish(level, aircraft, status.get().phase(), "target_lost");
            return false;
        }

        FlightSnapshot snapshot = FlightSnapshot.capture(aircraft);
        Vec3 targetDirection = directionTo(aircraft, target.aircraft(), snapshot.forward());
        Vec3 predictedLeadDirection =
                leadDirection(aircraft, target.aircraft(), targetDirection, LEAD_TICKS);
        double rawAngle = angleDegrees(snapshot.forward(), targetDirection);
        double predictedLeadAngle = angleDegrees(snapshot.forward(), predictedLeadDirection);
        double distance = aircraft.distanceTo(target.aircraft());
        double closure = relativeClosureBps(aircraft, target.aircraft());
        ThreatView threat = attackerThreat(target.aircraft(), pilot.getUUID());

        if (state == null) {
            double energyRatio = snapshot.speedBps() / Math.max(1.0, profile.cruiseSpeedBps());
            boolean priorCombat = DefensiveAirCombatManager.active(aircraft)
                    || AirCombatManeuverManager.active(aircraft);
            if (!priorCombat || !target.lineOfSight()
                    || distance < START_MIN_DISTANCE || distance > START_MAX_DISTANCE
                    || closure > 0.0 || threat.aimAngleDeg() < 8.0
                    || energyRatio < START_MIN_ENERGY_RATIO
                    || rawAngle < FORWARD_HANDOFF_ANGLE_DEG) {
                return false;
            }

            double targetRoll = FlightSnapshot.capture(target.aircraft()).rollDeg();
            state = new State(target.pilotUuid(),
                    ReflectiveArmament.estimatedShotsRemaining(aircraft),
                    crossingTurnSign(snapshot, targetDirection, targetRoll),
                    snapshot.position().y, targetRoll, rawAngle, snapshot.forward());
            STATES.put(aircraft.getUUID(), state);
            DefensiveAirCombatManager.clear(aircraft.getUUID());
            AirCombatManeuverManager.clear(aircraft.getUUID());
            writeEvent(level, aircraft, status.get().phase(), "energy_crossing_reentry_start",
                    state, snapshot, distance, rawAngle, predictedLeadAngle, closure,
                    threat.aimAngleDeg(), "safe_extension");
        }

        if (!state.targetPilotUuid.equals(target.pilotUuid())) {
            finish(level, aircraft, status.get().phase(), "target_changed");
            return false;
        }
        if (ReflectiveArmament.estimatedShotsRemaining(aircraft) < state.initialShots) {
            finish(level, aircraft, status.get().phase(), "fire_confirmed");
            return false;
        }
        if (state.totalTicks >= MAX_TOTAL_TICKS) {
            finish(level, aircraft, status.get().phase(), "total_timeout");
            return false;
        }
        if (credibleThreat(distance, closure, rawAngle, threat)) {
            AirCombatManeuverManager.clear(aircraft.getUUID());
            finish(level, aircraft, status.get().phase(), "credible_threat_restored");
            return false;
        }

        DefensiveAirCombatManager.clear(aircraft.getUUID());

        if (state.stage == Stage.CROSSING) {
            updateCrossingProgress(state, rawAngle);
            boolean forwardHandoff = state.stageTicks >= MIN_CROSS_TICKS
                    && rawAngle <= FORWARD_HANDOFF_ANGLE_DEG
                    && distance >= 22.0 && distance <= 170.0;
            boolean earlyWingover = state.stageTicks >= MIN_CROSS_TICKS
                    && rawAngle <= EARLY_WINGOVER_RAW_ANGLE_DEG
                    && closure >= EARLY_WINGOVER_MIN_CLOSURE_BPS
                    && distance >= EARLY_WINGOVER_MIN_DISTANCE
                    && distance <= EARLY_WINGOVER_MAX_DISTANCE;
            boolean localMinimumWingover = state.stageTicks >= MIN_CROSS_TICKS
                    && state.bestRawAngle <= ADAPTIVE_HANDOFF_MAX_ANGLE_DEG
                    && rawAngle <= state.bestRawAngle + ADAPTIVE_MAX_REGRESSION_DEG
                    && state.stalledTicks >= ADAPTIVE_STALL_TICKS
                    && distance >= 22.0 && distance <= 170.0
                    && closure > 0.0;
            if (forwardHandoff) {
                transition(level, aircraft, status.get().phase(), state, snapshot,
                        distance, rawAngle, predictedLeadAngle, closure,
                        threat.aimAngleDeg(), Stage.DOCTRINE, "forward_sector_reached");
            } else if (earlyWingover || localMinimumWingover) {
                state.wingoverStartForward = snapshot.forward();
                state.wingoverStartAltitude = snapshot.position().y;
                transition(level, aircraft, status.get().phase(), state, snapshot,
                        distance, rawAngle, predictedLeadAngle, closure,
                        threat.aimAngleDeg(), Stage.WINGOVER,
                        earlyWingover ? "closure_positive_wingover_entry"
                                : "best_crossing_geometry_stalled");
            } else if (state.stageTicks >= MAX_CROSS_TICKS || distance > 190.0) {
                finish(level, aircraft, status.get().phase(), "crossing_window_expired");
                return false;
            }
        }

        if (state.stage == Stage.WINGOVER) {
            state.wingoverAngle = angleDegrees(state.wingoverStartForward, snapshot.forward());
            boolean descendingReversal = state.stageTicks >= MIN_WINGOVER_TICKS
                    && state.wingoverAngle >= WINGOVER_COMPLETE_ANGLE_DEG
                    && snapshot.forward().y <= WINGOVER_DESCENDING_FORWARD_Y;
            if (descendingReversal) {
                transition(level, aircraft, status.get().phase(), state, snapshot,
                        distance, rawAngle, predictedLeadAngle, closure,
                        threat.aimAngleDeg(), Stage.RECOVERY,
                        "phased_turn_vertical_reversal_complete");
            } else if (state.stageTicks >= MAX_WINGOVER_TICKS) {
                finish(level, aircraft, status.get().phase(), "wingover_reversal_incomplete");
                return false;
            }
        }

        if (state.stage == Stage.RECOVERY) {
            boolean attackSector = target.lineOfSight()
                    && rawAngle <= ATTACK_MAX_RAW_ANGLE_DEG
                    && predictedLeadAngle <= ATTACK_MAX_LEAD_ANGLE_DEG
                    && distance >= ATTACK_MIN_DISTANCE && distance <= ATTACK_MAX_DISTANCE
                    && closure >= ATTACK_MIN_CLOSURE_BPS
                    && closure <= ATTACK_MAX_CLOSURE_BPS;
            if (attackSector) {
                transition(level, aircraft, status.get().phase(), state, snapshot,
                        distance, rawAngle, predictedLeadAngle, closure,
                        threat.aimAngleDeg(), Stage.DOCTRINE,
                        "high_energy_recovery_reached_attack_sector");
            } else if (state.stageTicks >= MAX_RECOVERY_TICKS || distance > 190.0) {
                finish(level, aircraft, status.get().phase(), "high_energy_recovery_expired");
                return false;
            }
        }

        if (state.stage == Stage.CROSSING) {
            applyCrossing(level, aircraft, target.aircraft(), snapshot, profile,
                    targetDirection, rawAngle, predictedLeadAngle, closure,
                    state, status.get().phase());
        } else if (state.stage == Stage.WINGOVER) {
            applyWingover(level, aircraft, snapshot, profile, predictedLeadDirection, rawAngle,
                    predictedLeadAngle, closure, state, status.get().phase());
        } else if (state.stage == Stage.RECOVERY) {
            applyRecovery(level, aircraft, target.aircraft(), snapshot, profile,
                    predictedLeadDirection, rawAngle, predictedLeadAngle, closure,
                    state, status.get().phase());
        } else {
            AirCombatManeuverManager.applyControl(aircraft);
            applyFinalAlignment(level, aircraft, target, snapshot, profile,
                    rawAngle, closure, state, status.get().phase());
        }

        state.totalTicks++;
        state.stageTicks++;
        if (state.statusTicks++ % 10 == 0) {
            writeEvent(level, aircraft, status.get().phase(), "energy_crossing_reentry_status",
                    state, snapshot, distance, rawAngle, predictedLeadAngle, closure,
                    threat.aimAngleDeg(), "active");
        }
        return true;
    }

    private static void updateCrossingProgress(State state, double rawAngle) {
        if (rawAngle + IMPROVEMENT_EPSILON_DEG < state.bestRawAngle) {
            state.bestRawAngle = rawAngle;
            state.stalledTicks = 0;
        } else if (state.bestRawAngle <= ADAPTIVE_HANDOFF_MAX_ANGLE_DEG) {
            state.stalledTicks++;
        }
    }

    private static void transition(ServerLevel level, Entity aircraft, FlightPhase phase,
                                   State state, FlightSnapshot snapshot, double distance,
                                   double rawAngle, double predictedLeadAngle, double closure,
                                   double attackerAim, Stage next, String reason) {
        state.stage = next;
        state.stageTicks = 0;
        AirCombatManeuverManager.clear(aircraft.getUUID());
        writeEvent(level, aircraft, phase, "energy_crossing_reentry_transition",
                state, snapshot, distance, rawAngle, predictedLeadAngle, closure,
                attackerAim, reason);
    }

    private static void applyCrossing(ServerLevel level, Entity aircraft, Entity target,
                                      FlightSnapshot snapshot, FlightProfile profile,
                                      Vec3 targetDirection, double rawAngle,
                                      double predictedLeadAngle, double closure,
                                      State state, FlightPhase phase) {
        Vec3 desired = leadDirection(aircraft, target, targetDirection, 5.0);
        Vec3 horizontalDesired = safeNormalize(horizontal(desired), snapshot.horizontalForward());
        double headingError = headingError(snapshot, horizontalDesired);
        float x = (float) (state.turnSign * 0.92);
        double targetAltitude = Math.max(target.position().y + 8.0, state.startAltitude + 14.0);
        double altitudeError = targetAltitude - snapshot.position().y;
        double desiredPitch = Mth.clamp(-altitudeError * 0.22
                + snapshot.verticalSpeedBps() * 0.25, -12.0, 8.0);
        double targetSpeed = Math.max(profile.stallGuardSpeedBps() * 2.15,
                profile.cruiseSpeedBps() + 1.0);
        float engineTarget = snapshot.speedBps() > targetSpeed + 3.0 ? 0.20f
                : snapshot.speedBps() < targetSpeed - 1.0 ? 1.0f : 0.58f;
        if (snapshot.speedBps() < profile.turnSpeedFloorBps() * 0.82) {
            desiredPitch = Math.max(desiredPitch, -2.0);
            x *= 0.62f;
            engineTarget = 1.0f;
        }
        float z = (float) Mth.clamp((desiredPitch - snapshot.pitchDeg()) / 14.0,
                -0.84, 0.80);
        FlightControlOutput output = new FlightControlOutput(x, 0.0f, z, engineTarget,
                horizontalDesired, targetAltitude, targetSpeed, headingError, altitudeError,
                targetSpeed - snapshot.speedBps(),
                snapshot.speedBps() < profile.stallGuardSpeedBps(), false,
                "energy_crossing_reentry", "opposite_turn_crossing");
        applyAndLog(level, aircraft, snapshot, output, state, rawAngle,
                predictedLeadAngle, closure, phase);
    }

    private static void applyWingover(ServerLevel level, Entity aircraft,
                                      FlightSnapshot snapshot, FlightProfile profile,
                                      Vec3 predictedLeadDirection, double rawAngle,
                                      double predictedLeadAngle, double closure,
                                      State state, FlightPhase phase) {
        Vec3 horizontalDesired = safeNormalize(horizontal(predictedLeadDirection),
                snapshot.horizontalForward());
        double headingError = headingError(snapshot, horizontalDesired);
        double turnProgress = Mth.clamp(
                (state.wingoverAngle - WINGOVER_TURN_START_ANGLE_DEG)
                        / (WINGOVER_TURN_FULL_ANGLE_DEG - WINGOVER_TURN_START_ANGLE_DEG),
                0.0, 1.0);
        float x = (float) (Mth.clamp(headingError / 30.0,
                -WINGOVER_MAX_TURN_INPUT, WINGOVER_MAX_TURN_INPUT) * turnProgress);
        double targetAltitude = state.wingoverStartAltitude + 90.0;
        FlightControlOutput output = new FlightControlOutput(
                x, 0.0f, -0.95f, 1.0f,
                state.wingoverStartForward.scale(-1.0), targetAltitude, WINGOVER_SPEED_BPS,
                headingError, targetAltitude - snapshot.position().y,
                WINGOVER_SPEED_BPS - snapshot.speedBps(),
                snapshot.speedBps() < profile.stallGuardSpeedBps(), false,
                "energy_phased_turn_vertical_reversal",
                turnProgress > 0.0 ? "turn_toward_predicted_lead_after_apex"
                        : "pure_vertical_pull_before_apex");
        applyAndLog(level, aircraft, snapshot, output, state, rawAngle,
                predictedLeadAngle, closure, phase);
    }

    private static void applyRecovery(ServerLevel level, Entity aircraft, Entity target,
                                      FlightSnapshot snapshot, FlightProfile profile,
                                      Vec3 predictedLeadDirection, double rawAngle,
                                      double predictedLeadAngle, double closure,
                                      State state, FlightPhase phase) {
        Vec3 horizontalDesired = safeNormalize(horizontal(predictedLeadDirection),
                snapshot.horizontalForward());
        double headingError = headingError(snapshot, horizontalDesired);
        float x = (float) Mth.clamp(headingError / 12.0, -0.94, 0.94);
        double targetAltitude = target.getBoundingBox().getCenter().y;
        double altitudeError = targetAltitude - snapshot.position().y;
        double desiredPitch = Mth.clamp(-altitudeError * 0.28
                + snapshot.verticalSpeedBps() * 0.22, -15.0, 12.0);
        float z = (float) Mth.clamp((desiredPitch - snapshot.pitchDeg()) / 11.0,
                -0.90, 0.90);
        double targetSpeed = recoveryTargetSpeed(profile, target);
        float engineTarget = snapshot.speedBps() < targetSpeed - 1.0 ? 1.0f
                : snapshot.speedBps() > targetSpeed + 3.0 ? 0.35f : 0.65f;
        FlightControlOutput output = new FlightControlOutput(x, 0.0f, z, engineTarget,
                predictedLeadDirection, targetAltitude, targetSpeed,
                headingError, altitudeError, targetSpeed - snapshot.speedBps(),
                snapshot.speedBps() < profile.stallGuardSpeedBps(), false,
                "energy_high_energy_recovery", "accelerating_descent_to_predicted_lead");
        applyAndLog(level, aircraft, snapshot, output, state, rawAngle,
                predictedLeadAngle, closure, phase);
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
        Vec3 horizontalDesired = safeNormalize(horizontal(aim.get().direction()),
                snapshot.horizontalForward());
        double headingError = headingError(snapshot, horizontalDesired);
        float x = (float) Mth.clamp(headingError / 9.0, -0.94, 0.94);
        double targetAltitude = aim.get().aimPoint().y;
        double altitudeError = targetAltitude - snapshot.position().y;
        double desiredPitch = Mth.clamp(-altitudeError * 0.26
                + snapshot.verticalSpeedBps() * 0.25, -12.0, 10.0);
        if (snapshot.speedBps() < profile.stallGuardSpeedBps() * 1.30) {
            desiredPitch = Math.max(desiredPitch, -2.0);
            x *= 0.65f;
        }
        float z = (float) Mth.clamp((desiredPitch - snapshot.pitchDeg()) / 12.0,
                -0.86, 0.86);
        double targetSpeed = recoveryTargetSpeed(profile, target.aircraft());
        float engineTarget = closure > 24.0 ? 0.18f
                : snapshot.speedBps() < targetSpeed - 1.0 ? 0.90f : 0.45f;
        FlightControlOutput output = new FlightControlOutput(x, 0.0f, z, engineTarget,
                horizontalDesired, targetAltitude, targetSpeed, headingError, altitudeError,
                targetSpeed - snapshot.speedBps(),
                snapshot.speedBps() < profile.stallGuardSpeedBps(), false,
                "energy_high_energy_final_alignment", "forward_alignment");
        applyAndLog(level, aircraft, snapshot, output, state, rawAngle,
                aim.get().angleOffNoseDeg(), closure, phase);
    }

    private static double recoveryTargetSpeed(FlightProfile profile, Entity target) {
        double measuredManeuverSpeed = Math.max(profile.cruiseSpeedBps(),
                profile.turnSpeedFloorBps() * 0.90);
        return Math.max(measuredManeuverSpeed,
                target.getDeltaMovement().horizontalDistance() * 20.0 + 3.0);
    }

    private static void applyAndLog(ServerLevel level, Entity aircraft, FlightSnapshot snapshot,
                                    FlightControlOutput output, State state, double rawAngle,
                                    double predictedLeadAngle, double closure,
                                    FlightPhase phase) {
        ReflectiveAircraft.applyControl(aircraft, -output.x(), output.y(), output.z(),
                output.engineTarget());
        AutopilotLogManager.writeControlAdapter(level.getServer(), aircraft, phase,
                description(state, rawAngle, predictedLeadAngle, closure, snapshot.speedBps()),
                snapshot, baseline(snapshot), output);
    }

    private static String description(State state, double rawAngle,
                                      double predictedLeadAngle, double closure, double speed) {
        return "stage=" + state.stage
                + ":total_ticks=" + state.totalTicks
                + ":stage_ticks=" + state.stageTicks
                + ":best_raw_target_angle=" + round(state.bestRawAngle)
                + ":stalled_ticks=" + state.stalledTicks
                + ":raw_target_angle=" + round(rawAngle)
                + ":predicted_lead_angle=" + round(predictedLeadAngle)
                + ":closure=" + round(closure)
                + ":speed_bps=" + round(speed)
                + ":wingover_angle=" + round(state.wingoverAngle);
    }

    private static Optional<Target> target(ServerLevel level, Entity aircraft) {
        return CombatAwarenessManager.currentSolution(aircraft.getUUID())
                .map(solution -> {
                    Entity entity = level.getEntity(solution.targetUuid());
                    if (!(entity instanceof LivingEntity pilot) || !pilot.isAlive()) {
                        return null;
                    }
                    Entity targetAircraft = pilot.getVehicle();
                    return targetAircraft != null && ReflectiveAircraft.isAirplane(targetAircraft)
                            ? new Target(pilot.getUUID(), targetAircraft, solution.lineOfSight())
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
        Vec3 horizontalTarget = safeNormalize(horizontal(direction),
                snapshot.horizontalForward());
        double error = headingError(snapshot, horizontalTarget);
        return error >= 0.0 ? 1.0 : -1.0;
    }

    private static double headingError(FlightSnapshot snapshot, Vec3 desired) {
        double yaw = Math.toDegrees(Math.atan2(-desired.x, desired.z));
        return Mth.wrapDegrees((float) (yaw - snapshot.yawDeg()));
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

    private static void writeEvent(ServerLevel level, Entity aircraft, FlightPhase phase,
                                   String event, State state, FlightSnapshot snapshot,
                                   double distance, double rawAngle,
                                   double predictedLeadAngle, double closure,
                                   double attackerAim, String reason) {
        AutopilotLogManager.writeEvent(level.getServer(), aircraft, event,
                description(state, rawAngle, predictedLeadAngle, closure, snapshot.speedBps())
                        + ":distance=" + round(distance)
                        + ":attacker_aim_angle=" + round(attackerAim)
                        + ":turn_sign=" + state.turnSign
                        + ":target_roll=" + round(state.targetRoll)
                        + ":altitude=" + round(snapshot.position().y)
                        + ":wingover_start_altitude=" + round(state.wingoverStartAltitude)
                        + ":reason=" + reason,
                phase);
    }

    private static void finish(ServerLevel level, Entity aircraft,
                               FlightPhase phase, String reason) {
        State removed = STATES.remove(aircraft.getUUID());
        if (removed != null) {
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "energy_crossing_reentry_end",
                    "stage=" + removed.stage
                            + ":total_ticks=" + removed.totalTicks
                            + ":best_raw_target_angle=" + round(removed.bestRawAngle)
                            + ":wingover_angle=" + round(removed.wingoverAngle)
                            + ":reason=" + reason,
                    phase);
        }
    }

    public static boolean active(Entity aircraft) {
        return STATES.containsKey(aircraft.getUUID());
    }

    public static void clear(UUID aircraftUuid) {
        STATES.remove(aircraftUuid);
    }

    private static double round(double value) {
        return Math.rint(value * 100.0) / 100.0;
    }

    private enum Stage {
        CROSSING,
        WINGOVER,
        RECOVERY,
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
        private final double targetRoll;
        private Stage stage = Stage.CROSSING;
        private double bestRawAngle;
        private Vec3 wingoverStartForward;
        private double wingoverStartAltitude;
        private double wingoverAngle;
        private int stalledTicks;
        private int totalTicks;
        private int stageTicks;
        private int statusTicks;

        private State(UUID targetPilotUuid, int initialShots, double turnSign,
                      double startAltitude, double targetRoll, double initialRawAngle,
                      Vec3 initialForward) {
            this.targetPilotUuid = targetPilotUuid;
            this.initialShots = initialShots;
            this.turnSign = turnSign;
            this.startAltitude = startAltitude;
            this.targetRoll = targetRoll;
            this.bestRawAngle = initialRawAngle;
            this.wingoverStartForward = initialForward;
            this.wingoverStartAltitude = startAltitude;
        }
    }
}
