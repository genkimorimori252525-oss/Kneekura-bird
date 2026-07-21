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
 * Converts a completed energy-fighter extension into one bounded high-yo-yo re-entry.
 *
 * <p>This adapter owns only the P-47N-style energy-fighter recovery window. It never fires and it
 * never relaxes weapon safety. Once the target reaches the forward sector it hands control to the
 * ordinary offensive manager, applying only a brief final alignment while the existing lead
 * solution remains just outside the fixed-gun cone.</p>
 */
public final class EnergyFighterReengagementAdapter {
    private static final double START_MIN_DISTANCE = 88.0;
    private static final double START_MAX_DISTANCE = 155.0;
    private static final double START_MAX_CLOSURE_BPS = 0.0;
    private static final double START_MIN_ATTACKER_AIM_ERROR_DEG = 8.0;
    private static final double START_MIN_ENERGY_RATIO = 1.02;
    private static final double SETUP_RAW_ANGLE_DEG = 48.0;
    private static final double OFFENSIVE_HANDOFF_RAW_ANGLE_DEG = 34.0;
    private static final double FINAL_MIN_LEAD_ANGLE_DEG = 3.0;
    private static final double FINAL_MAX_LEAD_ANGLE_DEG = 8.0;
    private static final double FINAL_MAX_RAW_ANGLE_DEG = 35.0;
    private static final double FINAL_MIN_CLOSURE_BPS = 20.0;
    private static final int MIN_REVERSAL_TICKS = 18;
    private static final int TURN_FLIP_CHECK_TICKS = 12;
    private static final int MAX_REENGAGEMENT_TICKS = 260;
    private static final Map<UUID, State> STATES = new ConcurrentHashMap<>();

    private EnergyFighterReengagementAdapter() {
    }

    /**
     * @return true when this adapter owns combat control for the current tick
     */
    public static boolean applyControl(Entity aircraft) {
        if (aircraft.level().isClientSide || !(aircraft.level() instanceof ServerLevel level)
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
                || status.isEmpty() || !eligiblePhase(status.get().phase())
                || aircraft.onGround() || profile == null
                || !"energy_fighter".equalsIgnoreCase(profile.doctrine())
                || TerrainAvoidancePlanner.active(aircraft)
                || AirspaceSafetyProbe.collisionRisk(aircraft)) {
            finish(level, aircraft, status.map(AutonomousFlightManager.SessionStatus::phase)
                    .orElse(FlightPhase.ABORTED), "reengagement_not_eligible");
            return false;
        }

        Target target = target(level, aircraft).orElse(null);
        State state = STATES.get(aircraft.getUUID());
        if (target == null) {
            finish(level, aircraft, status.get().phase(), "reengagement_target_lost");
            return false;
        }

        FlightSnapshot snapshot = FlightSnapshot.capture(aircraft);
        Vec3 targetDirection = directionTo(aircraft, target.aircraft(), snapshot.forward());
        double rawTargetAngle = angleDegrees(snapshot.forward(), targetDirection);
        double distance = aircraft.distanceTo(target.aircraft());
        double closure = relativeClosureBps(aircraft, target.aircraft());
        double attackerAimAngle = attackerAimAngle(target.aircraft(), pilot.getUUID());

        if (state == null) {
            boolean priorCombatControl = DefensiveAirCombatManager.active(aircraft)
                    || AirCombatManeuverManager.active(aircraft);
            double energyRatio = snapshot.speedBps() / Math.max(1.0, profile.cruiseSpeedBps());
            if (!priorCombatControl || !target.lineOfSight()
                    || distance < START_MIN_DISTANCE || distance > START_MAX_DISTANCE
                    || closure > START_MAX_CLOSURE_BPS
                    || attackerAimAngle < START_MIN_ATTACKER_AIM_ERROR_DEG
                    || energyRatio < START_MIN_ENERGY_RATIO
                    || rawTargetAngle < SETUP_RAW_ANGLE_DEG) {
                return false;
            }

            double turnSign = shortestTurnSign(snapshot, targetDirection, target.aircraft());
            state = new State(target.pilotUuid(),
                    ReflectiveArmament.estimatedShotsRemaining(aircraft), turnSign,
                    snapshot.position().y, rawTargetAngle);
            STATES.put(aircraft.getUUID(), state);
            DefensiveAirCombatManager.clear(aircraft.getUUID());
            AirCombatManeuverManager.clear(aircraft.getUUID());
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "energy_reengagement_start",
                    description(state, distance, rawTargetAngle, closure, attackerAimAngle)
                            + ":energy_ratio=" + round(energyRatio),
                    status.get().phase());
        }

        if (!state.targetPilotUuid.equals(target.pilotUuid())) {
            finish(level, aircraft, status.get().phase(), "reengagement_target_changed");
            return false;
        }
        if (ReflectiveArmament.estimatedShotsRemaining(aircraft) < state.initialShotsRemaining) {
            finish(level, aircraft, status.get().phase(), "reengagement_weapon_fire_confirmed");
            return false;
        }
        if (state.ticks >= MAX_REENGAGEMENT_TICKS) {
            finish(level, aircraft, status.get().phase(), "reengagement_timeout");
            return false;
        }
        if (credibleThreatRestored(target, distance, closure, attackerAimAngle, rawTargetAngle)) {
            AirCombatManeuverManager.clear(aircraft.getUUID());
            finish(level, aircraft, status.get().phase(), "credible_firing_threat_restored");
            return false;
        }

        DefensiveAirCombatManager.clear(aircraft.getUUID());
        if (state.stage == Stage.REVERSAL) {
            updateTurnDirection(level, aircraft, status.get().phase(), state,
                    distance, rawTargetAngle, closure, attackerAimAngle);
            applyReversal(level, aircraft, target.aircraft(), snapshot, profile,
                    targetDirection, rawTargetAngle, state, status.get().phase());
            if (state.stageTicks >= MIN_REVERSAL_TICKS
                    && rawTargetAngle <= SETUP_RAW_ANGLE_DEG
                    && distance >= 22.0 && distance <= 165.0) {
                state.stage = Stage.ATTACK_SETUP;
                state.stageTicks = 0;
                AirCombatManeuverManager.clear(aircraft.getUUID());
                AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                        "energy_reengagement_transition",
                        "from=REVERSAL:to=ATTACK_SETUP:distance=" + round(distance)
                                + ":raw_target_angle=" + round(rawTargetAngle),
                        status.get().phase());
            }
        } else if (rawTargetAngle > OFFENSIVE_HANDOFF_RAW_ANGLE_DEG) {
            applyAttackSetup(level, aircraft, target.aircraft(), snapshot, profile,
                    rawTargetAngle, state, status.get().phase());
        } else {
            AirCombatManeuverManager.applyControl(aircraft);
            applyFinalAlignment(level, aircraft, target, snapshot, profile,
                    rawTargetAngle, closure, status.get().phase());
        }

        state.ticks++;
        state.stageTicks++;
        if (state.statusTicks++ % 10 == 0) {
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "energy_reengagement_status",
                    description(state, distance, rawTargetAngle, closure, attackerAimAngle),
                    status.get().phase());
        }
        return true;
    }

    private static void updateTurnDirection(ServerLevel level, Entity aircraft, FlightPhase phase,
                                            State state, double distance, double rawTargetAngle,
                                            double closure, double attackerAimAngle) {
        if (rawTargetAngle + 1.0 < state.bestRawTargetAngle) {
            state.bestRawTargetAngle = rawTargetAngle;
            state.worseningTicks = 0;
            return;
        }
        state.worseningTicks++;
        if (!state.turnFlipped && state.stageTicks >= TURN_FLIP_CHECK_TICKS
                && state.worseningTicks >= TURN_FLIP_CHECK_TICKS
                && rawTargetAngle >= state.bestRawTargetAngle + 7.0) {
            state.turnSign = -state.turnSign;
            state.turnFlipped = true;
            state.worseningTicks = 0;
            state.bestRawTargetAngle = rawTargetAngle;
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "energy_reengagement_turn_flip",
                    description(state, distance, rawTargetAngle, closure, attackerAimAngle), phase);
        }
    }

    private static void applyReversal(ServerLevel level, Entity aircraft, Entity target,
                                      FlightSnapshot snapshot, FlightProfile profile,
                                      Vec3 targetDirection, double rawTargetAngle,
                                      State state, FlightPhase phase) {
        Vec3 leadPoint = target.getBoundingBox().getCenter()
                .add(target.getDeltaMovement().scale(7.0));
        Vec3 desired = safeNormalize(leadPoint.subtract(aircraft.getBoundingBox().getCenter()),
                targetDirection);
        Vec3 horizontalDesired = safeNormalize(horizontal(desired), snapshot.horizontalForward());
        double headingError = headingError(snapshot, horizontalDesired);
        float x = (float) (state.turnSign * 0.86);
        double altitudeGain = state.stageTicks < 52 ? 32.0 : 18.0;
        double targetAltitude = Math.max(target.position().y + 10.0,
                state.startAltitude + altitudeGain);
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
        apply(level, aircraft, snapshot, new FlightControlOutput(x, 0.0f, z, 1.0f,
                horizontalDesired, targetAltitude, targetSpeed, headingError, altitudeError,
                targetSpeed - snapshot.speedBps(),
                snapshot.speedBps() < profile.stallGuardSpeedBps(), false,
                "energy_reengagement_high_yoyo", "energy_reengagement_reversal"),
                state, rawTargetAngle, phase);
    }

    private static void applyAttackSetup(ServerLevel level, Entity aircraft, Entity target,
                                         FlightSnapshot snapshot, FlightProfile profile,
                                         double rawTargetAngle, State state, FlightPhase phase) {
        Vec3 leadPoint = target.getBoundingBox().getCenter()
                .add(target.getDeltaMovement().scale(6.0));
        Vec3 desired = safeNormalize(leadPoint.subtract(aircraft.getBoundingBox().getCenter()),
                snapshot.forward());
        Vec3 horizontalDesired = safeNormalize(horizontal(desired), snapshot.horizontalForward());
        double headingError = headingError(snapshot, horizontalDesired);
        float x = (float) Mth.clamp(headingError / 30.0, -0.86, 0.86);
        double targetAltitude = target.position().y + 8.0;
        double altitudeError = targetAltitude - snapshot.position().y;
        double desiredPitch = Mth.clamp(-altitudeError * 0.18
                + snapshot.verticalSpeedBps() * 0.28, -10.0, 8.0);
        if (snapshot.speedBps() < profile.stallGuardSpeedBps() * 1.28) {
            desiredPitch = Math.max(desiredPitch, -2.5);
            x *= 0.60f;
        }
        float z = (float) Mth.clamp((desiredPitch - snapshot.pitchDeg()) / 17.0,
                -0.74, 0.74);
        double targetSpeed = Math.max(profile.cruiseSpeedBps() + 4.0,
                target.getDeltaMovement().horizontalDistance() * 20.0 + 2.0);
        apply(level, aircraft, snapshot, new FlightControlOutput(x, 0.0f, z, 0.92f,
                horizontalDesired, targetAltitude, targetSpeed, headingError, altitudeError,
                targetSpeed - snapshot.speedBps(),
                snapshot.speedBps() < profile.stallGuardSpeedBps(), false,
                "energy_reengagement_attack_setup", "energy_reengagement_attack_setup"),
                state, rawTargetAngle, phase);
    }

    private static void applyFinalAlignment(ServerLevel level, Entity aircraft, Target target,
                                            FlightSnapshot snapshot, FlightProfile profile,
                                            double rawTargetAngle, double closure,
                                            FlightPhase phase) {
        Optional<AirCombatManeuverManager.AimSolution> aim =
                AirCombatManeuverManager.currentAim(aircraft.getUUID(), target.pilotUuid());
        if (aim.isEmpty() || aim.get().distanceBlocks() < 38.0
                || aim.get().distanceBlocks() > 170.0
                || aim.get().angleOffNoseDeg() < FINAL_MIN_LEAD_ANGLE_DEG
                || aim.get().angleOffNoseDeg() > FINAL_MAX_LEAD_ANGLE_DEG
                || rawTargetAngle > FINAL_MAX_RAW_ANGLE_DEG
                || closure < FINAL_MIN_CLOSURE_BPS) {
            return;
        }

        Vec3 horizontalDesired = safeNormalize(horizontal(aim.get().direction()),
                snapshot.horizontalForward());
        double headingError = headingError(snapshot, horizontalDesired);
        float x = (float) Mth.clamp(headingError / 10.0, -0.92, 0.92);
        double targetAltitude = aim.get().aimPoint().y;
        double altitudeError = targetAltitude - snapshot.position().y;
        double desiredPitch = Mth.clamp(-altitudeError * 0.24
                + snapshot.verticalSpeedBps() * 0.25, -12.0, 10.0);
        if (snapshot.speedBps() < profile.stallGuardSpeedBps() * 1.30) {
            desiredPitch = Math.max(desiredPitch, -2.5);
            x *= 0.62f;
        }
        float z = (float) Mth.clamp((desiredPitch - snapshot.pitchDeg()) / 12.0,
                -0.86, 0.86);
        double targetSpeed = Math.max(profile.stallGuardSpeedBps() * 1.65,
                target.aircraft().getDeltaMovement().horizontalDistance() * 20.0);
        float engineTarget = closure > 45.0 ? 0.18f : 0.38f;
        FlightControlOutput output = new FlightControlOutput(x, 0.0f, z, engineTarget,
                horizontalDesired, targetAltitude, targetSpeed, headingError, altitudeError,
                targetSpeed - snapshot.speedBps(),
                snapshot.speedBps() < profile.stallGuardSpeedBps(), false,
                "energy_reengagement_final_alignment", "fixed_gun_final_alignment");
        ReflectiveAircraft.applyControl(aircraft, -output.x(), output.y(), output.z(),
                output.engineTarget());
        AutopilotLogManager.writeControlAdapter(level.getServer(), aircraft, phase,
                "lead_angle=" + round(aim.get().angleOffNoseDeg())
                        + ":raw_target_angle=" + round(rawTargetAngle)
                        + ":closure=" + round(closure),
                snapshot, baseline(snapshot), output);
    }

    private static void apply(ServerLevel level, Entity aircraft, FlightSnapshot snapshot,
                              FlightControlOutput output, State state,
                              double rawTargetAngle, FlightPhase phase) {
        ReflectiveAircraft.applyControl(aircraft, -output.x(), output.y(), output.z(),
                output.engineTarget());
        AutopilotLogManager.writeControlAdapter(level.getServer(), aircraft, phase,
                "stage=" + state.stage + ":ticks=" + state.ticks
                        + ":raw_target_angle=" + round(rawTargetAngle),
                snapshot, baseline(snapshot), output);
    }

    private static Optional<Target> target(ServerLevel level, Entity aircraft) {
        return CombatAwarenessManager.currentSolution(aircraft.getUUID())
                .filter(CombatTargetSelector.Solution::lineOfSight)
                .map(solution -> level.getEntity(solution.targetUuid()))
                .filter(LivingEntity.class::isInstance)
                .map(LivingEntity.class::cast)
                .filter(LivingEntity::isAlive)
                .map(pilot -> {
                    Entity targetAircraft = pilot.getVehicle();
                    return targetAircraft != null && ReflectiveAircraft.isAirplane(targetAircraft)
                            ? new Target(pilot.getUUID(), targetAircraft, true) : null;
                });
    }

    private static double attackerAimAngle(Entity attacker, UUID defenderPilotUuid) {
        return AirCombatManeuverManager.currentAim(attacker.getUUID(), defenderPilotUuid)
                .map(AirCombatManeuverManager.AimSolution::angleOffNoseDeg)
                .orElseGet(() -> CombatAwarenessManager.currentSolution(attacker.getUUID())
                        .filter(solution -> solution.targetUuid().equals(defenderPilotUuid))
                        .map(CombatTargetSelector.Solution::angleOffNoseDeg)
                        .orElse(180.0));
    }

    private static boolean credibleThreatRestored(Target target, double distance, double closure,
                                                   double attackerAimAngle,
                                                   double rawTargetAngle) {
        if (!target.lineOfSight() || rawTargetAngle <= 58.0) {
            return false;
        }
        return (distance <= 82.0 && attackerAimAngle <= 3.2)
                || (distance <= 105.0 && closure >= 8.0 && attackerAimAngle <= 5.0);
    }

    private static double shortestTurnSign(FlightSnapshot snapshot, Vec3 targetDirection,
                                           Entity target) {
        Vec3 horizontalTarget = safeNormalize(horizontal(targetDirection),
                snapshot.horizontalForward());
        double error = headingError(snapshot, horizontalTarget);
        if (Math.abs(error) >= 3.0) {
            return error > 0.0 ? 1.0 : -1.0;
        }
        FlightSnapshot targetSnapshot = FlightSnapshot.capture(target);
        return Math.abs(targetSnapshot.rollDeg()) >= 4.0
                ? (targetSnapshot.rollDeg() < 0.0 ? 1.0 : -1.0) : 1.0;
    }

    private static double headingError(FlightSnapshot snapshot, Vec3 horizontalDesired) {
        double desiredYaw = Math.toDegrees(Math.atan2(-horizontalDesired.x, horizontalDesired.z));
        return Mth.wrapDegrees((float) (desiredYaw - snapshot.yawDeg()));
    }

    private static Vec3 directionTo(Entity from, Entity to, Vec3 fallback) {
        return safeNormalize(to.getBoundingBox().getCenter()
                .subtract(from.getBoundingBox().getCenter()), fallback);
    }

    private static double relativeClosureBps(Entity defender, Entity attacker) {
        Vec3 line = attacker.position().subtract(defender.position());
        if (line.lengthSqr() < 1.0e-8) {
            return 0.0;
        }
        Vec3 relativeVelocity = attacker.getDeltaMovement().subtract(defender.getDeltaMovement())
                .scale(20.0);
        return -relativeVelocity.dot(line.normalize());
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

    private static String description(State state, double distance, double rawTargetAngle,
                                      double closure, double attackerAimAngle) {
        return "stage=" + state.stage + ":ticks=" + state.ticks
                + ":stage_ticks=" + state.stageTicks
                + ":distance=" + round(distance)
                + ":raw_target_angle=" + round(rawTargetAngle)
                + ":best_raw_target_angle=" + round(state.bestRawTargetAngle)
                + ":closure=" + round(closure)
                + ":attacker_aim_angle=" + round(attackerAimAngle)
                + ":turn_sign=" + state.turnSign
                + ":turn_flipped=" + state.turnFlipped;
    }

    private static void finish(ServerLevel level, Entity aircraft, FlightPhase phase,
                               String reason) {
        State removed = STATES.remove(aircraft.getUUID());
        if (removed != null) {
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "energy_reengagement_end",
                    "stage=" + removed.stage + ":ticks=" + removed.ticks
                            + ":reason=" + reason,
                    phase);
        }
    }

    public static void clear(UUID aircraftUuid) {
        STATES.remove(aircraftUuid);
    }

    private static double round(double value) {
        return Math.rint(value * 100.0) / 100.0;
    }

    private enum Stage {
        REVERSAL,
        ATTACK_SETUP
    }

    private record Target(UUID pilotUuid, Entity aircraft, boolean lineOfSight) {
    }

    private static final class State {
        private final UUID targetPilotUuid;
        private final int initialShotsRemaining;
        private final double startAltitude;
        private double turnSign;
        private double bestRawTargetAngle;
        private Stage stage = Stage.REVERSAL;
        private int ticks;
        private int stageTicks;
        private int statusTicks;
        private int worseningTicks;
        private boolean turnFlipped;

        private State(UUID targetPilotUuid, int initialShotsRemaining, double turnSign,
                      double startAltitude, double initialRawTargetAngle) {
            this.targetPilotUuid = targetPilotUuid;
            this.initialShotsRemaining = initialShotsRemaining;
            this.turnSign = turnSign;
            this.startAltitude = startAltitude;
            this.bestRawTargetAngle = initialRawTargetAngle;
        }
    }
}
