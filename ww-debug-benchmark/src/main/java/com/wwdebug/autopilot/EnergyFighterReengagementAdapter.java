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
 * Converts a completed energy-fighter extension into a bounded crossing re-entry.
 *
 * <p>When the opponent is already established in a turn, the energy fighter reverses across that
 * turn instead of joining the same large-radius orbit. Once the opponent reaches the forward sector,
 * control returns to the ordinary doctrine manager. All separation and final firing checks remain
 * outside this controller.</p>
 */
public final class EnergyFighterReengagementAdapter {
    private static final double START_MIN_DISTANCE = 88.0;
    private static final double START_MAX_DISTANCE = 155.0;
    private static final double START_MIN_ENERGY_RATIO = 1.02;
    private static final double APPROACH_RAW_ANGLE_DEG = 60.0;
    private static final int MIN_CROSS_TICKS = 20;
    private static final int MAX_CROSS_TICKS = 150;
    private static final int MAX_TOTAL_TICKS = 240;
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
                    || energyRatio < START_MIN_ENERGY_RATIO
                    || rawAngle < APPROACH_RAW_ANGLE_DEG) {
                return false;
            }

            FlightSnapshot targetSnapshot = FlightSnapshot.capture(target.aircraft());
            double targetRoll = targetSnapshot.rollDeg();
            double turnSign = crossingTurnSign(snapshot, targetDirection, targetRoll);
            state = new State(target.pilotUuid(),
                    ReflectiveArmament.estimatedShotsRemaining(aircraft), turnSign,
                    snapshot.position().y, targetRoll);
            STATES.put(aircraft.getUUID(), state);
            DefensiveAirCombatManager.clear(aircraft.getUUID());
            AirCombatManeuverManager.clear(aircraft.getUUID());
            writeEvent(level, aircraft, status.get().phase(), "energy_crossing_reentry_start",
                    state, distance, rawAngle, closure, threat.aimAngleDeg());
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
            if (state.stageTicks >= MIN_CROSS_TICKS
                    && rawAngle <= APPROACH_RAW_ANGLE_DEG
                    && distance >= 22.0 && distance <= 170.0) {
                state.stage = Stage.APPROACH;
                state.stageTicks = 0;
                AirCombatManeuverManager.clear(aircraft.getUUID());
                writeEvent(level, aircraft, status.get().phase(),
                        "energy_crossing_reentry_transition",
                        state, distance, rawAngle, closure, threat.aimAngleDeg());
            } else if (state.stageTicks >= MAX_CROSS_TICKS || distance > 190.0) {
                finish(level, aircraft, status.get().phase(), "crossing_window_expired");
                return false;
            }
        }

        if (state.stage == Stage.CROSSING) {
            applyCrossing(level, aircraft, target.aircraft(), snapshot, profile,
                    targetDirection, rawAngle, state, status.get().phase());
        } else {
            AirCombatManeuverManager.applyControl(aircraft);
            applyFinalAlignment(level, aircraft, target, snapshot, profile,
                    rawAngle, closure, status.get().phase());
        }

        state.totalTicks++;
        state.stageTicks++;
        if (state.statusTicks++ % 10 == 0) {
            writeEvent(level, aircraft, status.get().phase(), "energy_crossing_reentry_status",
                    state, distance, rawAngle, closure, threat.aimAngleDeg());
        }
        return true;
    }

    private static void applyCrossing(ServerLevel level, Entity aircraft, Entity target,
                                      FlightSnapshot snapshot, FlightProfile profile,
                                      Vec3 targetDirection, double rawAngle,
                                      State state, FlightPhase phase) {
        Vec3 leadPoint = target.getBoundingBox().getCenter()
                .add(target.getDeltaMovement().scale(5.0));
        Vec3 desired = safeNormalize(leadPoint.subtract(aircraft.getBoundingBox().getCenter()),
                targetDirection);
        Vec3 horizontalDesired = safeNormalize(horizontal(desired), snapshot.horizontalForward());
        double headingError = headingError(snapshot, horizontalDesired);

        float x = (float) (state.turnSign * 0.92);
        double targetAltitude = Math.max(target.position().y + 8.0, state.startAltitude + 14.0);
        double altitudeError = targetAltitude - snapshot.position().y;
        double desiredPitch = Mth.clamp(-altitudeError * 0.22
                + snapshot.verticalSpeedBps() * 0.25, -12.0, 8.0);
        double targetSpeed = Math.max(profile.stallGuardSpeedBps() * 2.15,
                profile.cruiseSpeedBps() + 1.0);
        float engineTarget;
        if (snapshot.speedBps() > targetSpeed + 3.0) {
            engineTarget = 0.20f;
        } else if (snapshot.speedBps() < targetSpeed - 1.0) {
            engineTarget = 1.0f;
        } else {
            engineTarget = 0.58f;
        }
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
        ReflectiveAircraft.applyControl(aircraft, -output.x(), output.y(), output.z(),
                output.engineTarget());
        AutopilotLogManager.writeControlAdapter(level.getServer(), aircraft, phase,
                "stage=" + state.stage
                        + ":stage_ticks=" + state.stageTicks
                        + ":turn_sign=" + state.turnSign
                        + ":target_roll=" + round(state.targetRoll)
                        + ":raw_target_angle=" + round(rawAngle),
                snapshot, baseline(snapshot), output);
    }

    private static void applyFinalAlignment(ServerLevel level, Entity aircraft, Target target,
                                            FlightSnapshot snapshot, FlightProfile profile,
                                            double rawAngle, double closure, FlightPhase phase) {
        Optional<AirCombatManeuverManager.AimSolution> aim =
                AirCombatManeuverManager.currentAim(aircraft.getUUID(), target.pilotUuid());
        if (aim.isEmpty() || !target.lineOfSight()
                || aim.get().distanceBlocks() < 24.0 || aim.get().distanceBlocks() > 170.0
                || aim.get().angleOffNoseDeg() < 3.0 || aim.get().angleOffNoseDeg() > 12.0
                || rawAngle > 45.0 || closure < -6.0) {
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
        double targetSpeed = Math.max(profile.stallGuardSpeedBps() * 1.70,
                target.aircraft().getDeltaMovement().horizontalDistance() * 20.0);
        float engineTarget = closure > 40.0 ? 0.18f : 0.38f;

        FlightControlOutput output = new FlightControlOutput(x, 0.0f, z, engineTarget,
                horizontalDesired, targetAltitude, targetSpeed, headingError, altitudeError,
                targetSpeed - snapshot.speedBps(),
                snapshot.speedBps() < profile.stallGuardSpeedBps(), false,
                "energy_crossing_final_alignment", "forward_alignment");
        ReflectiveAircraft.applyControl(aircraft, -output.x(), output.y(), output.z(),
                output.engineTarget());
        AutopilotLogManager.writeControlAdapter(level.getServer(), aircraft, phase,
                "lead_angle=" + round(aim.get().angleOffNoseDeg())
                        + ":raw_target_angle=" + round(rawAngle)
                        + ":closure=" + round(closure),
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
                                   String event, State state, double distance,
                                   double rawAngle, double closure, double attackerAim) {
        AutopilotLogManager.writeEvent(level.getServer(), aircraft, event,
                "stage=" + state.stage
                        + ":total_ticks=" + state.totalTicks
                        + ":stage_ticks=" + state.stageTicks
                        + ":distance=" + round(distance)
                        + ":raw_target_angle=" + round(rawAngle)
                        + ":closure=" + round(closure)
                        + ":attacker_aim_angle=" + round(attackerAim)
                        + ":turn_sign=" + state.turnSign
                        + ":target_roll=" + round(state.targetRoll),
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
        APPROACH
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
        private int totalTicks;
        private int stageTicks;
        private int statusTicks;

        private State(UUID targetPilotUuid, int initialShots, double turnSign,
                      double startAltitude, double targetRoll) {
            this.targetPilotUuid = targetPilotUuid;
            this.initialShots = initialShots;
            this.turnSign = turnSign;
            this.startAltitude = startAltitude;
            this.targetRoll = targetRoll;
        }
    }
}
