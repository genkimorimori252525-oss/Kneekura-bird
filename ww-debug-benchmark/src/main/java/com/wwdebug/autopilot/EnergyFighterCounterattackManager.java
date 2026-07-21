package com.wwdebug.autopilot;

import com.wwdebug.benchmark.ReflectiveAircraft;
import com.wwdebug.benchmark.ReflectiveArmament;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.util.Mth;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;

import java.util.Comparator;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Converts a completed energy-fighter extension into a crossing counterattack.
 *
 * <p>The recovery starts only after the fighter has gained useful separation and speed while the
 * attacker has lost its firing solution. Instead of joining the turn fighter's circle, the energy
 * fighter reverses against the attacker's bank direction, performs a zooming turn-back, and hands
 * control to the normal lead-aimed offensive selector once the target reaches the forward quarter.
 * Terrain and predicted aircraft separation remain higher-priority controls.</p>
 */
public final class EnergyFighterCounterattackManager {
    private static final double SEARCH_HORIZONTAL = 220.0;
    private static final double SEARCH_VERTICAL = 120.0;
    private static final double START_MIN_DISTANCE = 96.0;
    private static final double START_MAX_CLOSURE_BPS = 2.0;
    private static final double START_MIN_ATTACKER_AIM_ERROR_DEG = 10.0;
    private static final double START_MIN_ENERGY_RATIO = 1.08;
    private static final double IMMINENT_FIRE_ANGLE_DEG = 4.5;
    private static final double RENEWED_THREAT_MAX_AIM_ERROR_DEG = 6.0;
    private static final double RENEWED_THREAT_MIN_CLOSURE_BPS = 12.0;
    private static final double RENEWED_THREAT_MAX_DISTANCE = 90.0;
    private static final double ATTACK_SETUP_RAW_ANGLE_DEG = 42.0;
    private static final double ATTACK_SETUP_MAX_LEAD_ANGLE_DEG = 95.0;
    private static final int MIN_TURN_BACK_TICKS = 20;
    private static final int MAX_RECOVERY_TICKS = 240;
    private static final Map<UUID, State> STATES = new ConcurrentHashMap<>();

    private EnergyFighterCounterattackManager() {
    }

    /**
     * @return true when this controller owns the combat input for the current tick
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
            clearWithLog(level, aircraft, status.map(AutonomousFlightManager.SessionStatus::phase)
                    .orElse(FlightPhase.ABORTED), "counterattack_not_eligible");
            return false;
        }

        FlightSnapshot snapshot = FlightSnapshot.capture(aircraft);
        Threat threat = findThreat(level, aircraft, pilot).orElse(null);
        State state = STATES.get(aircraft.getUUID());
        if (state == null) {
            boolean priorCombatControl = DefensiveAirCombatManager.active(aircraft)
                    || AirCombatManeuverManager.active(aircraft);
            if (!priorCombatControl || threat == null
                    || !staleOpening(threat, snapshot, profile)) {
                return false;
            }
            double turnSign = oppositeAttackerTurn(threat.attacker(), snapshot);
            state = new State(threat.attacker().getUUID(), threat.attackerPilotUuid(),
                    ReflectiveArmament.estimatedShotsRemaining(aircraft), turnSign);
            STATES.put(aircraft.getUUID(), state);
            DefensiveAirCombatManager.clear(aircraft.getUUID());
            AirCombatManeuverManager.clear(aircraft.getUUID());
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "energy_counterattack_start",
                    description(state, threat, -1.0)
                            + ":reason=energy_and_spacing_recovered",
                    status.get().phase());
        }

        if (threat == null || !threat.attacker().getUUID().equals(state.attackerUuid)) {
            finish(level, aircraft, status.get().phase(), state, threat,
                    "attacker_no_longer_tracking");
            return false;
        }

        Vec3 targetDirection = safeNormalize(threat.attacker().getBoundingBox().getCenter()
                .subtract(aircraft.getBoundingBox().getCenter()), snapshot.forward());
        double rawTargetAngle = angleDegrees(snapshot.forward(), targetDirection);
        int shotsRemaining = ReflectiveArmament.estimatedShotsRemaining(aircraft);
        if (shotsRemaining < state.initialShotsRemaining) {
            finish(level, aircraft, status.get().phase(), state, threat,
                    "counterattack_weapon_fire_confirmed");
            return false;
        }
        // A real rear-quarter firing solution still wins. During a nearly reciprocal crossing,
        // however, allow the energy fighter to finish bringing its own guns through the target.
        if ((threat.imminentFire() && rawTargetAngle > 55.0)
                || (renewedThreat(threat) && rawTargetAngle > 70.0)) {
            AirCombatManeuverManager.clear(aircraft.getUUID());
            finish(level, aircraft, status.get().phase(), state, threat,
                    threat.imminentFire() ? "attacker_firing_solution_restored"
                            : "attacker_closure_restored");
            return false;
        }
        if (state.recoveryTicks >= MAX_RECOVERY_TICKS) {
            finish(level, aircraft, status.get().phase(), state, threat,
                    "counterattack_window_timeout");
            return false;
        }

        DefensiveAirCombatManager.clear(aircraft.getUUID());
        Optional<AirCombatManeuverManager.AimSolution> ownAim = Optional.empty();
        if (state.stage == Stage.TURN_BACK) {
            applyTurnBackControl(level, aircraft, threat.attacker(), snapshot, profile,
                    targetDirection, rawTargetAngle, state);
            if (state.stageTicks >= MIN_TURN_BACK_TICKS
                    && rawTargetAngle <= ATTACK_SETUP_RAW_ANGLE_DEG
                    && threat.distance() >= 20.0 && threat.distance() <= 155.0) {
                transition(level, aircraft, status.get().phase(), state, Stage.ATTACK_SETUP,
                        threat, rawTargetAngle, "crossing_target_entered_forward_quarter");
                AirCombatManeuverManager.clear(aircraft.getUUID());
            }
        } else {
            AirCombatManeuverManager.applyControl(aircraft);
            ownAim = AirCombatManeuverManager.currentAim(
                    aircraft.getUUID(), state.attackerPilotUuid);
            if (state.stageTicks >= 12
                    && ownAim.map(AirCombatManeuverManager.AimSolution::angleOffNoseDeg)
                    .orElse(180.0) > ATTACK_SETUP_MAX_LEAD_ANGLE_DEG) {
                AirCombatManeuverManager.clear(aircraft.getUUID());
                transition(level, aircraft, status.get().phase(), state, Stage.TURN_BACK,
                        threat, rawTargetAngle, "lead_solution_moved_behind_fighter");
            }
        }

        state.recoveryTicks++;
        state.stageTicks++;
        if (state.statusTicks++ % 20 == 0) {
            double ownLeadAngle = ownAim
                    .map(AirCombatManeuverManager.AimSolution::angleOffNoseDeg)
                    .map(EnergyFighterCounterattackManager::round).orElse(-1.0);
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "energy_counterattack_status",
                    description(state, threat, rawTargetAngle)
                            + ":offensive_active=" + AirCombatManeuverManager.active(aircraft)
                            + ":own_lead_angle=" + ownLeadAngle
                            + ":shots_remaining=" + shotsRemaining,
                    status.get().phase());
        }
        return true;
    }

    private static void applyTurnBackControl(ServerLevel level, Entity aircraft, Entity target,
                                             FlightSnapshot snapshot, FlightProfile profile,
                                             Vec3 targetDirection, double rawTargetAngle,
                                             State state) {
        Vec3 horizontalDesired = safeNormalize(horizontal(targetDirection),
                snapshot.horizontalForward());
        double desiredYaw = Math.toDegrees(Math.atan2(-horizontalDesired.x, horizontalDesired.z));
        double headingError = Mth.wrapDegrees((float) (desiredYaw - snapshot.yawDeg()));
        float x = (float) (state.turnSign * 0.82);
        double targetAltitude = state.stageTicks < 65
                ? snapshot.position().y + 30.0 : target.position().y + 12.0;
        double altitudeError = targetAltitude - snapshot.position().y;
        double desiredPitch = Mth.clamp(-altitudeError * 0.18
                + snapshot.verticalSpeedBps() * 0.30, -11.0, 8.0);
        if (snapshot.speedBps() < profile.turnSpeedFloorBps() * 0.92) {
            desiredPitch = Math.max(desiredPitch, -2.5);
            x *= 0.55f;
        }
        float z = (float) Mth.clamp((desiredPitch - snapshot.pitchDeg()) / 17.0,
                -0.72, 0.72);
        double targetSpeed = Math.max(profile.cruiseSpeedBps() + 8.0,
                snapshot.speedBps() + 3.0);
        FlightControlOutput output = new FlightControlOutput(x, 0.0f, z, 1.0f,
                horizontalDesired, targetAltitude, targetSpeed, headingError, altitudeError,
                targetSpeed - snapshot.speedBps(),
                snapshot.speedBps() < profile.stallGuardSpeedBps(), false,
                "energy_counterattack_opposite_reversal", "energy_counterattack_turn_back");
        ReflectiveAircraft.applyControl(aircraft, -output.x(), output.y(), output.z(),
                output.engineTarget());
        AutopilotLogManager.writeControlAdapter(level.getServer(), aircraft,
                AutonomousFlightManager.status(aircraft.getUUID())
                        .map(AutonomousFlightManager.SessionStatus::phase)
                        .orElse(FlightPhase.ABORTED),
                "stage=" + state.stage
                        + ":recovery_ticks=" + state.recoveryTicks
                        + ":turn_sign=" + state.turnSign
                        + ":raw_target_angle=" + round(rawTargetAngle),
                snapshot, baseline(snapshot), output);
    }

    private static double oppositeAttackerTurn(Entity attacker, FlightSnapshot defenderSnapshot) {
        FlightSnapshot attackerSnapshot = FlightSnapshot.capture(attacker);
        if (Math.abs(attackerSnapshot.rollDeg()) >= 4.0) {
            return attackerSnapshot.rollDeg() < 0.0 ? 1.0 : -1.0;
        }
        Vec3 direction = safeNormalize(attacker.getBoundingBox().getCenter()
                .subtract(defenderSnapshot.position()), defenderSnapshot.forward());
        double desiredYaw = Math.toDegrees(Math.atan2(-direction.x, direction.z));
        double shortestHeading = Mth.wrapDegrees((float) (desiredYaw - defenderSnapshot.yawDeg()));
        return shortestHeading < 0.0 ? 1.0 : -1.0;
    }

    private static Optional<Threat> findThreat(ServerLevel level, Entity defender,
                                                LivingEntity defenderPilot) {
        AABB area = defender.getBoundingBox().inflate(
                SEARCH_HORIZONTAL, SEARCH_VERTICAL, SEARCH_HORIZONTAL);
        return level.getEntities(defender, area,
                        candidate -> ReflectiveAircraft.isAirplane(candidate)
                                && !candidate.isRemoved())
                .stream()
                .map(candidate -> threat(candidate, defender, defenderPilot))
                .flatMap(Optional::stream)
                .max(Comparator.comparingDouble(Threat::score));
    }

    private static Optional<Threat> threat(Entity attacker, Entity defender,
                                           LivingEntity defenderPilot) {
        Optional<CombatTargetSelector.Solution> selected =
                CombatAwarenessManager.currentSolution(attacker.getUUID());
        if (selected.isEmpty()
                || !selected.get().targetUuid().equals(defenderPilot.getUUID())) {
            return Optional.empty();
        }
        Entity attackerPilot = attacker.getControllingPassenger();
        if (!(attackerPilot instanceof LivingEntity)) {
            return Optional.empty();
        }
        double distance = attacker.distanceTo(defender);
        double attackerAimAngle = AirCombatManeuverManager
                .currentAim(attacker.getUUID(), defenderPilot.getUUID())
                .map(AirCombatManeuverManager.AimSolution::angleOffNoseDeg)
                .orElse(selected.get().angleOffNoseDeg());
        double closure = relativeClosureBps(defender, attacker);
        boolean imminentFire = distance >= 18.0 && distance <= 135.0
                && attackerAimAngle <= IMMINENT_FIRE_ANGLE_DEG
                && selected.get().lineOfSight();
        double score = (SEARCH_HORIZONTAL - Math.min(SEARCH_HORIZONTAL, distance))
                + Math.max(0.0, 30.0 - attackerAimAngle)
                + Math.max(0.0, closure) * 2.0
                + (imminentFire ? 200.0 : 0.0);
        return Optional.of(new Threat(attacker, attackerPilot.getUUID(), distance,
                attackerAimAngle, closure, selected.get().lineOfSight(), imminentFire, score));
    }

    private static boolean staleOpening(Threat threat, FlightSnapshot snapshot,
                                        FlightProfile profile) {
        double energyRatio = snapshot.speedBps() / Math.max(1.0, profile.cruiseSpeedBps());
        return threat.lineOfSight()
                && threat.distance() >= START_MIN_DISTANCE
                && threat.closureBps() <= START_MAX_CLOSURE_BPS
                && threat.attackerAimAngleDeg() >= START_MIN_ATTACKER_AIM_ERROR_DEG
                && energyRatio >= START_MIN_ENERGY_RATIO
                && !threat.imminentFire();
    }

    private static boolean renewedThreat(Threat threat) {
        return threat.lineOfSight()
                && threat.distance() <= RENEWED_THREAT_MAX_DISTANCE
                && threat.closureBps() >= RENEWED_THREAT_MIN_CLOSURE_BPS
                && threat.attackerAimAngleDeg() <= RENEWED_THREAT_MAX_AIM_ERROR_DEG;
    }

    private static void transition(ServerLevel level, Entity aircraft, FlightPhase phase,
                                   State state, Stage next, Threat threat,
                                   double rawTargetAngle, String reason) {
        Stage previous = state.stage;
        state.stage = next;
        state.stageTicks = 0;
        AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                "energy_counterattack_transition",
                "from=" + previous + ":to=" + next
                        + ":reason=" + reason
                        + ":distance=" + round(threat.distance())
                        + ":raw_target_angle=" + round(rawTargetAngle)
                        + ":attacker_aim_angle=" + round(threat.attackerAimAngleDeg())
                        + ":closure=" + round(threat.closureBps())
                        + ":turn_sign=" + state.turnSign,
                phase);
    }

    private static void finish(ServerLevel level, Entity aircraft, FlightPhase phase,
                               State state, Threat threat, String reason) {
        STATES.remove(aircraft.getUUID());
        AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                "energy_counterattack_end",
                (threat == null ? stateDescription(state)
                        : description(state, threat, -1.0))
                        + ":reason=" + reason,
                phase);
    }

    private static void clearWithLog(ServerLevel level, Entity aircraft,
                                     FlightPhase phase, String reason) {
        State removed = STATES.remove(aircraft.getUUID());
        if (removed != null) {
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "energy_counterattack_end",
                    stateDescription(removed) + ":reason=" + reason,
                    phase);
        }
    }

    public static void clear(UUID aircraftUuid) {
        STATES.remove(aircraftUuid);
    }

    private static String description(State state, Threat threat, double rawTargetAngle) {
        return stateDescription(state)
                + ":attacker_uuid=" + threat.attacker().getUUID()
                + ":distance=" + round(threat.distance())
                + ":raw_target_angle=" + round(rawTargetAngle)
                + ":attacker_aim_angle=" + round(threat.attackerAimAngleDeg())
                + ":closure=" + round(threat.closureBps())
                + ":line_of_sight=" + threat.lineOfSight()
                + ":imminent_fire=" + threat.imminentFire();
    }

    private static String stateDescription(State state) {
        return "stage=" + state.stage
                + ":stage_ticks=" + state.stageTicks
                + ":recovery_ticks=" + state.recoveryTicks
                + ":turn_sign=" + state.turnSign
                + ":initial_shots=" + state.initialShotsRemaining;
    }

    private static boolean eligiblePhase(FlightPhase phase) {
        return phase.isAirborneMissionPhase() && !phase.isLandingPhase()
                && phase != FlightPhase.STALL_ENTRY && phase != FlightPhase.STALL_RECOVERY;
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

    private static double round(double value) {
        return Math.rint(value * 100.0) / 100.0;
    }

    private enum Stage {
        TURN_BACK,
        ATTACK_SETUP
    }

    private record Threat(Entity attacker, UUID attackerPilotUuid, double distance,
                          double attackerAimAngleDeg, double closureBps,
                          boolean lineOfSight, boolean imminentFire, double score) {
    }

    private static final class State {
        private final UUID attackerUuid;
        private final UUID attackerPilotUuid;
        private final int initialShotsRemaining;
        private final double turnSign;
        private Stage stage = Stage.TURN_BACK;
        private int stageTicks;
        private int recoveryTicks;
        private int statusTicks;

        private State(UUID attackerUuid, UUID attackerPilotUuid,
                      int initialShotsRemaining, double turnSign) {
            this.attackerUuid = attackerUuid;
            this.attackerPilotUuid = attackerPilotUuid;
            this.initialShotsRemaining = initialShotsRemaining;
            this.turnSign = turnSign;
        }
    }
}
