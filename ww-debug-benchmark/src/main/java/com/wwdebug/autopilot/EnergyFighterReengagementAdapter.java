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

/** Bounded high-yo-yo recovery for energy fighters after a safe extension. */
public final class EnergyFighterReengagementAdapter {
    private static final double START_MIN_DISTANCE = 88.0;
    private static final double START_MAX_DISTANCE = 155.0;
    private static final double START_MIN_ENERGY_RATIO = 1.02;
    private static final double SETUP_RAW_ANGLE_DEG = 48.0;
    private static final double HANDOFF_RAW_ANGLE_DEG = 34.0;
    private static final int MIN_REVERSAL_TICKS = 18;
    private static final int PLATEAU_OBSERVATION_TICKS = 60;
    private static final int PLATEAU_TICKS = 14;
    private static final int MAX_TICKS = 260;
    private static final Map<UUID, State> STATES = new ConcurrentHashMap<>();

    private EnergyFighterReengagementAdapter() {
    }

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
        double rawAngle = angleDegrees(snapshot.forward(), targetDirection);
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
                    || energyRatio < START_MIN_ENERGY_RATIO || rawAngle < SETUP_RAW_ANGLE_DEG) {
                return false;
            }
            state = new State(target.pilotUuid(),
                    ReflectiveArmament.estimatedShotsRemaining(aircraft),
                    shortestTurnSign(snapshot, targetDirection, target.aircraft()),
                    snapshot.position().y, rawAngle);
            STATES.put(aircraft.getUUID(), state);
            DefensiveAirCombatManager.clear(aircraft.getUUID());
            AirCombatManeuverManager.clear(aircraft.getUUID());
            log(level, aircraft, status.get().phase(), "energy_reengagement_start",
                    state, distance, rawAngle, closure, threat.aimAngleDeg());
        }

        if (!state.targetPilotUuid.equals(target.pilotUuid())) {
            finish(level, aircraft, status.get().phase(), "target_changed");
            return false;
        }
        if (ReflectiveArmament.estimatedShotsRemaining(aircraft) < state.initialShots) {
            finish(level, aircraft, status.get().phase(), "weapon_fire_confirmed");
            return false;
        }
        if (state.ticks >= MAX_TICKS) {
            finish(level, aircraft, status.get().phase(), "timeout");
            return false;
        }
        if (credibleThreat(distance, closure, rawAngle, threat)) {
            AirCombatManeuverManager.clear(aircraft.getUUID());
            finish(level, aircraft, status.get().phase(), "credible_threat_restored");
            return false;
        }

        DefensiveAirCombatManager.clear(aircraft.getUUID());
        updateProgress(level, aircraft, status.get().phase(), state,
                distance, rawAngle, closure, threat.aimAngleDeg());

        if (state.stage == Stage.REVERSAL && state.stageTicks >= MIN_REVERSAL_TICKS
                && rawAngle <= SETUP_RAW_ANGLE_DEG && distance >= 22.0 && distance <= 165.0) {
            state.stage = Stage.ATTACK_SETUP;
            state.stageTicks = 0;
            AirCombatManeuverManager.clear(aircraft.getUUID());
            log(level, aircraft, status.get().phase(), "energy_reengagement_transition",
                    state, distance, rawAngle, closure, threat.aimAngleDeg());
        }

        if (state.stage == Stage.REVERSAL) {
            applyReversal(level, aircraft, target.aircraft(), snapshot, profile,
                    targetDirection, rawAngle, state, status.get().phase());
        } else if (rawAngle > HANDOFF_RAW_ANGLE_DEG) {
            applySetup(level, aircraft, target.aircraft(), snapshot, profile,
                    rawAngle, state, status.get().phase());
        } else {
            AirCombatManeuverManager.applyControl(aircraft);
            applyFinalAlignment(level, aircraft, target, snapshot, profile,
                    rawAngle, closure, status.get().phase());
        }

        state.ticks++;
        state.stageTicks++;
        if (state.statusTicks++ % 10 == 0) {
            log(level, aircraft, status.get().phase(), "energy_reengagement_status",
                    state, distance, rawAngle, closure, threat.aimAngleDeg());
        }
        return true;
    }

    private static void updateProgress(ServerLevel level, Entity aircraft, FlightPhase phase,
                                       State state, double distance, double rawAngle,
                                       double closure, double attackerAim) {
        if (rawAngle + 0.7 < state.bestRawAngle) {
            state.bestRawAngle = rawAngle;
            state.worseningTicks = 0;
            return;
        }
        state.worseningTicks++;
        if (!state.directCut && state.stageTicks >= PLATEAU_OBSERVATION_TICKS
                && state.bestRawAngle <= 105.0
                && rawAngle <= state.bestRawAngle + 10.0
                && state.worseningTicks >= PLATEAU_TICKS) {
            state.directCut = true;
            state.worseningTicks = 0;
            log(level, aircraft, phase, "energy_reengagement_direct_cut",
                    state, distance, rawAngle, closure, attackerAim);
        }
    }

    private static void applyReversal(ServerLevel level, Entity aircraft, Entity target,
                                      FlightSnapshot snapshot, FlightProfile profile,
                                      Vec3 targetDirection, double rawAngle,
                                      State state, FlightPhase phase) {
        double leadTicks = state.directCut ? 5.0 : 7.0;
        Vec3 leadPoint = target.getBoundingBox().getCenter()
                .add(target.getDeltaMovement().scale(leadTicks));
        Vec3 desired = safeNormalize(leadPoint.subtract(aircraft.getBoundingBox().getCenter()),
                targetDirection);
        Vec3 horizontalDesired = safeNormalize(horizontal(desired), snapshot.horizontalForward());
        double headingError = headingError(snapshot, horizontalDesired);
        float x = state.directCut
                ? (float) Mth.clamp(headingError / 15.0, -0.92, 0.92)
                : (float) (state.turnSign * 0.86);
        double targetAltitude = state.directCut
                ? target.position().y + 8.0
                : Math.max(target.position().y + 10.0,
                state.startAltitude + (state.stageTicks < 52 ? 32.0 : 18.0));
        double altitudeError = targetAltitude - snapshot.position().y;
        double desiredPitch = Mth.clamp(-altitudeError * (state.directCut ? 0.22 : 0.19)
                + snapshot.verticalSpeedBps() * 0.28, -12.0, 8.0);
        if (snapshot.speedBps() < profile.turnSpeedFloorBps() * 0.90) {
            desiredPitch = Math.max(desiredPitch, -2.0);
            x *= 0.58f;
        }
        float z = (float) Mth.clamp((desiredPitch - snapshot.pitchDeg()) / 15.0,
                -0.82, 0.76);
        double targetSpeed = state.directCut
                ? Math.max(profile.stallGuardSpeedBps() * 2.2, profile.cruiseSpeedBps())
                : Math.max(profile.cruiseSpeedBps() + 7.0, snapshot.speedBps() + 2.0);
        float engine = state.directCut ? 0.62f : 1.0f;
        apply(level, aircraft, snapshot, new FlightControlOutput(x, 0.0f, z, engine,
                horizontalDesired, targetAltitude, targetSpeed, headingError, altitudeError,
                targetSpeed - snapshot.speedBps(),
                snapshot.speedBps() < profile.stallGuardSpeedBps(), false,
                state.directCut ? "energy_reengagement_direct_cut" : "energy_reengagement_high_yoyo",
                "energy_reengagement_reversal"), state, rawAngle, phase);
    }

    private static void applySetup(ServerLevel level, Entity aircraft, Entity target,
                                   FlightSnapshot snapshot, FlightProfile profile,
                                   double rawAngle, State state, FlightPhase phase) {
        Vec3 leadPoint = target.getBoundingBox().getCenter()
                .add(target.getDeltaMovement().scale(6.0));
        Vec3 desired = safeNormalize(leadPoint.subtract(aircraft.getBoundingBox().getCenter()),
                snapshot.forward());
        Vec3 horizontalDesired = safeNormalize(horizontal(desired), snapshot.horizontalForward());
        double headingError = headingError(snapshot, horizontalDesired);
        float x = (float) Mth.clamp(headingError / 24.0, -0.90, 0.90);
        double targetAltitude = target.position().y + 8.0;
        double altitudeError = targetAltitude - snapshot.position().y;
        double desiredPitch = Mth.clamp(-altitudeError * 0.18
                + snapshot.verticalSpeedBps() * 0.28, -10.0, 8.0);
        float z = (float) Mth.clamp((desiredPitch - snapshot.pitchDeg()) / 15.0,
                -0.78, 0.78);
        double targetSpeed = Math.max(profile.cruiseSpeedBps() + 3.0,
                target.getDeltaMovement().horizontalDistance() * 20.0 + 2.0);
        apply(level, aircraft, snapshot, new FlightControlOutput(x, 0.0f, z, 0.82f,
                horizontalDesired, targetAltitude, targetSpeed, headingError, altitudeError,
                targetSpeed - snapshot.speedBps(),
                snapshot.speedBps() < profile.stallGuardSpeedBps(), false,
                "energy_reengagement_attack_setup", "energy_reengagement_attack_setup"),
                state, rawAngle, phase);
    }

    private static void applyFinalAlignment(ServerLevel level, Entity aircraft, Target target,
                                            FlightSnapshot snapshot, FlightProfile profile,
                                            double rawAngle, double closure, FlightPhase phase) {
        Optional<AirCombatManeuverManager.AimSolution> aim =
                AirCombatManeuverManager.currentAim(aircraft.getUUID(), target.pilotUuid());
        if (aim.isEmpty() || !target.lineOfSight()
                || aim.get().distanceBlocks() < 38.0 || aim.get().distanceBlocks() > 170.0
                || aim.get().angleOffNoseDeg() < 3.0 || aim.get().angleOffNoseDeg() > 8.0
                || rawAngle > 35.0 || closure < 20.0) {
            return;
        }
        Vec3 horizontalDesired = safeNormalize(horizontal(aim.get().direction()),
                snapshot.horizontalForward());
        double headingError = headingError(snapshot, horizontalDesired);
        float x = (float) Mth.clamp(headingError / 10.0, -0.92, 0.92);
        double altitudeError = aim.get().aimPoint().y - snapshot.position().y;
        double desiredPitch = Mth.clamp(-altitudeError * 0.24
                + snapshot.verticalSpeedBps() * 0.25, -12.0, 10.0);
        float z = (float) Mth.clamp((desiredPitch - snapshot.pitchDeg()) / 12.0,
                -0.86, 0.86);
        double targetSpeed = Math.max(profile.stallGuardSpeedBps() * 1.65,
                target.aircraft().getDeltaMovement().horizontalDistance() * 20.0);
        FlightControlOutput output = new FlightControlOutput(x, 0.0f, z,
                closure > 45.0 ? 0.18f : 0.38f, horizontalDesired,
                aim.get().aimPoint().y, targetSpeed, headingError, altitudeError,
                targetSpeed - snapshot.speedBps(),
                snapshot.speedBps() < profile.stallGuardSpeedBps(), false,
                "energy_reengagement_final_alignment", "fixed_gun_final_alignment");
        ReflectiveAircraft.applyControl(aircraft, -output.x(), output.y(), output.z(),
                output.engineTarget());
        AutopilotLogManager.writeControlAdapter(level.getServer(), aircraft, phase,
                "lead_angle=" + round(aim.get().angleOffNoseDeg())
                        + ":raw_target_angle=" + round(rawAngle),
                snapshot, baseline(snapshot), output);
    }

    private static void apply(ServerLevel level, Entity aircraft, FlightSnapshot snapshot,
                              FlightControlOutput output, State state,
                              double rawAngle, FlightPhase phase) {
        ReflectiveAircraft.applyControl(aircraft, -output.x(), output.y(), output.z(),
                output.engineTarget());
        AutopilotLogManager.writeControlAdapter(level.getServer(), aircraft, phase,
                "stage=" + state.stage + ":ticks=" + state.ticks
                        + ":direct_cut=" + state.directCut
                        + ":raw_target_angle=" + round(rawAngle),
                snapshot, baseline(snapshot), output);
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
                            ? new Target(pilot.getUUID(), targetAircraft, solution.lineOfSight()) : null;
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

    private static double shortestTurnSign(FlightSnapshot snapshot, Vec3 direction, Entity target) {
        double error = headingError(snapshot,
                safeNormalize(horizontal(direction), snapshot.horizontalForward()));
        if (Math.abs(error) >= 3.0) {
            return error > 0.0 ? 1.0 : -1.0;
        }
        double roll = FlightSnapshot.capture(target).rollDeg();
        return Math.abs(roll) >= 4.0 ? (roll < 0.0 ? 1.0 : -1.0) : 1.0;
    }

    private static double headingError(FlightSnapshot snapshot, Vec3 desired) {
        double yaw = Math.toDegrees(Math.atan2(-desired.x, desired.z));
        return Mth.wrapDegrees((float) (yaw - snapshot.yawDeg()));
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

    private static void log(ServerLevel level, Entity aircraft, FlightPhase phase, String event,
                            State state, double distance, double rawAngle,
                            double closure, double attackerAim) {
        AutopilotLogManager.writeEvent(level.getServer(), aircraft, event,
                "stage=" + state.stage + ":ticks=" + state.ticks
                        + ":stage_ticks=" + state.stageTicks
                        + ":distance=" + round(distance)
                        + ":raw_target_angle=" + round(rawAngle)
                        + ":best_raw_target_angle=" + round(state.bestRawAngle)
                        + ":closure=" + round(closure)
                        + ":attacker_aim_angle=" + round(attackerAim)
                        + ":direct_cut=" + state.directCut,
                phase);
    }

    private static void finish(ServerLevel level, Entity aircraft, FlightPhase phase, String reason) {
        State removed = STATES.remove(aircraft.getUUID());
        if (removed != null) {
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "energy_reengagement_end",
                    "stage=" + removed.stage + ":ticks=" + removed.ticks
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

    private enum Stage { REVERSAL, ATTACK_SETUP }

    private record Target(UUID pilotUuid, Entity aircraft, boolean lineOfSight) { }

    private record ThreatView(double aimAngleDeg, boolean lineOfSight) { }

    private static final class State {
        private final UUID targetPilotUuid;
        private final int initialShots;
        private final double turnSign;
        private final double startAltitude;
        private double bestRawAngle;
        private Stage stage = Stage.REVERSAL;
        private int ticks;
        private int stageTicks;
        private int statusTicks;
        private int worseningTicks;
        private boolean directCut;

        private State(UUID targetPilotUuid, int initialShots, double turnSign,
                      double startAltitude, double initialRawAngle) {
            this.targetPilotUuid = targetPilotUuid;
            this.initialShots = initialShots;
            this.turnSign = turnSign;
            this.startAltitude = startAltitude;
            this.bestRawAngle = initialRawAngle;
        }
    }
}
