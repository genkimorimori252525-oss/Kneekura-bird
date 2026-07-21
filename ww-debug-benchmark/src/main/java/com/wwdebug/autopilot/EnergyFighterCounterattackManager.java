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
 * Converts a completed energy-fighter extension into a high-yo-yo counterattack.
 *
 * <p>The controller starts while range is opening, speed has recovered, and the attacker has lost
 * a credible firing solution. It climbs while reversing by the shortest useful side, automatically
 * flips the reversal once if the target angle is getting worse, and then hands control to the
 * normal lead-aimed offensive selector. Terrain and predicted aircraft separation remain above
 * this layer.</p>
 */
public final class EnergyFighterCounterattackManager {
    private static final double SEARCH_HORIZONTAL = 230.0;
    private static final double SEARCH_VERTICAL = 140.0;
    private static final double START_MIN_DISTANCE = 88.0;
    private static final double START_MAX_CLOSURE_BPS = 0.0;
    private static final double START_MIN_ATTACKER_AIM_ERROR_DEG = 8.0;
    private static final double START_MIN_ENERGY_RATIO = 1.02;
    private static final double ATTACK_SETUP_RAW_ANGLE_DEG = 48.0;
    private static final double OFFENSIVE_HANDOFF_RAW_ANGLE_DEG = 34.0;
    private static final double MAX_OFFENSIVE_LEAD_ANGLE_DEG = 105.0;
    private static final int MIN_ZOOM_REVERSAL_TICKS = 18;
    private static final int TURN_FLIP_CHECK_TICKS = 12;
    private static final int ATTACKER_TRACK_GRACE_TICKS = 24;
    private static final int MAX_RECOVERY_TICKS = 280;
    private static final Map<UUID, State> STATES = new ConcurrentHashMap<>();

    private EnergyFighterCounterattackManager() {
    }

    /**
     * @return true when this controller owns combat input for the current tick
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
        State state = STATES.get(aircraft.getUUID());
        Threat observed = findThreat(level, aircraft, pilot).orElse(null);

        if (state == null) {
            boolean priorCombatControl = DefensiveAirCombatManager.active(aircraft)
                    || AirCombatManeuverManager.active(aircraft);
            if (!priorCombatControl || observed == null
                    || !staleOpening(observed, snapshot, profile)) {
                return false;
            }

            Vec3 targetDirection = directionTo(aircraft, observed.attacker(), snapshot.forward());
            double rawTargetAngle = angleDegrees(snapshot.forward(), targetDirection);
            double turnSign = shortestTurnSign(snapshot, targetDirection, observed.attacker());
            state = new State(observed.attacker().getUUID(), observed.attackerPilotUuid(),
                    ReflectiveArmament.estimatedShotsRemaining(aircraft), turnSign,
                    snapshot.position().y, rawTargetAngle);
            STATES.put(aircraft.getUUID(), state);
            DefensiveAirCombatManager.clear(aircraft.getUUID());
            AirCombatManeuverManager.clear(aircraft.getUUID());
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "energy_counterattack_start",
                    description(state, observed, rawTargetAngle)
                            + ":reason=opening_range_high_yoyo",
                    status.get().phase());
        }

        Threat threat = observed;
        if (threat == null || !threat.attacker().getUUID().equals(state.attackerUuid)) {
            state.missingThreatTicks++;
            threat = fallbackThreat(level, aircraft, state).orElse(null);
            if (threat == null || state.missingThreatTicks > ATTACKER_TRACK_GRACE_TICKS) {
                finish(level, aircraft, status.get().phase(), state, threat,
                        "attacker_tracking_grace_expired");
                return false;
            }
        } else {
            state.missingThreatTicks = 0;
        }

        Entity target = threat.attacker();
        Vec3 targetDirection = directionTo(aircraft, target, snapshot.forward());
        double rawTargetAngle = angleDegrees(snapshot.forward(), targetDirection);
        int shotsRemaining = ReflectiveArmament.estimatedShotsRemaining(aircraft);

        if (shotsRemaining < state.initialShotsRemaining) {
            finish(level, aircraft, status.get().phase(), state, threat,
                    "counterattack_weapon_fire_confirmed");
            return false;
        }
        if (hardThreat(threat, rawTargetAngle)) {
            AirCombatManeuverManager.clear(aircraft.getUUID());
            finish(level, aircraft, status.get().phase(), state, threat,
                    "credible_close_firing_threat_restored");
            return false;
        }
        if (state.recoveryTicks >= MAX_RECOVERY_TICKS) {
            finish(level, aircraft, status.get().phase(), state, threat,
                    "counterattack_window_timeout");
            return false;
        }

        DefensiveAirCombatManager.clear(aircraft.getUUID());
        Optional<AirCombatManeuverManager.AimSolution> ownAim = Optional.empty();

        if (state.stage == Stage.ZOOM_REVERSAL) {
            updateTurnDirection(level, aircraft, status.get().phase(), state, threat,
                    rawTargetAngle);
            applyZoomReversalControl(level, aircraft, target, snapshot, profile,
                    targetDirection, rawTargetAngle, state);
            if (state.stageTicks >= MIN_ZOOM_REVERSAL_TICKS
                    && rawTargetAngle <= ATTACK_SETUP_RAW_ANGLE_DEG
                    && threat.distance() >= 22.0 && threat.distance() <= 165.0) {
                transition(level, aircraft, status.get().phase(), state, Stage.ATTACK_SETUP,
                        threat, rawTargetAngle, "target_entered_forward_crossing_sector");
                AirCombatManeuverManager.clear(aircraft.getUUID());
            }
        } else {
            if (rawTargetAngle > OFFENSIVE_HANDOFF_RAW_ANGLE_DEG) {
                applyAttackSetupControl(level, aircraft, target, snapshot, profile,
                        rawTargetAngle, state);
            } else {
                AirCombatManeuverManager.applyControl(aircraft);
                ownAim = AirCombatManeuverManager.currentAim(
                        aircraft.getUUID(), state.attackerPilotUuid);
                if (state.stageTicks >= 14
                        && ownAim.map(AirCombatManeuverManager.AimSolution::angleOffNoseDeg)
                        .orElse(180.0) > MAX_OFFENSIVE_LEAD_ANGLE_DEG) {
                    AirCombatManeuverManager.clear(aircraft.getUUID());
                    state.bestRawTargetAngle = rawTargetAngle;
                    state.worseningTicks = 0;
                    transition(level, aircraft, status.get().phase(), state, Stage.ZOOM_REVERSAL,
                            threat, rawTargetAngle, "lead_solution_moved_behind_fixed_guns");
                }
            }
        }

        state.recoveryTicks++;
        state.stageTicks++;
        if (state.statusTicks++ % 10 == 0) {
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

    private static void updateTurnDirection(ServerLevel level, Entity aircraft, FlightPhase phase,
                                            State state, Threat threat, double rawTargetAngle) {
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
                    "energy_counterattack_turn_flip",
                    description(state, threat, rawTargetAngle)
                            + ":reason=initial_reversal_increased_target_angle",
                    phase);
        }
    }

    private static void applyZoomReversalControl(ServerLevel level, Entity aircraft, Entity target,
                                                 FlightSnapshot snapshot, FlightProfile profile,
                                                 Vec3 targetDirection, double rawTargetAngle,
                                                 State state) {
        Vec3 shortLeadPoint = target.getBoundingBox().getCenter()
                .add(target.getDeltaMovement().scale(7.0));
        Vec3 leadDirection = safeNormalize(
                shortLeadPoint.subtract(aircraft.getBoundingBox().getCenter()), targetDirection);
        Vec3 horizontalDesired = safeNormalize(horizontal(leadDirection),
                snapshot.horizontalForward());
        double desiredYaw = Math.toDegrees(Math.atan2(-horizontalDesired.x, horizontalDesired.z));
        double headingError = Mth.wrapDegrees((float) (desiredYaw - snapshot.yawDeg()));

        float x = (float) (state.turnSign * 0.86);
        double zoomGain = state.stageTicks < 52 ? 32.0 : 18.0;
        double targetAltitude = Math.max(target.position().y + 10.0,
                state.startAltitude + zoomGain);
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
                "energy_counterattack_high_yoyo", "energy_counterattack_zoom_reversal");
        applyAndLog(level, aircraft, snapshot, output, state, rawTargetAngle);
    }

    private static void applyAttackSetupControl(ServerLevel level, Entity aircraft, Entity target,
                                                FlightSnapshot snapshot, FlightProfile profile,
                                                double rawTargetAngle, State state) {
        Vec3 leadPoint = target.getBoundingBox().getCenter()
                .add(target.getDeltaMovement().scale(6.0));
        Vec3 desired = safeNormalize(leadPoint.subtract(aircraft.getBoundingBox().getCenter()),
                snapshot.forward());
        Vec3 horizontalDesired = safeNormalize(horizontal(desired), snapshot.horizontalForward());
        double desiredYaw = Math.toDegrees(Math.atan2(-horizontalDesired.x, horizontalDesired.z));
        double headingError = Mth.wrapDegrees((float) (desiredYaw - snapshot.yawDeg()));
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

        FlightControlOutput output = new FlightControlOutput(x, 0.0f, z, 0.92f,
                horizontalDesired, targetAltitude, targetSpeed, headingError, altitudeError,
                targetSpeed - snapshot.speedBps(),
                snapshot.speedBps() < profile.stallGuardSpeedBps(), false,
                "energy_counterattack_attack_setup", "energy_counterattack_crossing_setup");
        applyAndLog(level, aircraft, snapshot, output, state, rawTargetAngle);
    }

    private static void applyAndLog(ServerLevel level, Entity aircraft, FlightSnapshot snapshot,
                                    FlightControlOutput output, State state,
                                    double rawTargetAngle) {
        ReflectiveAircraft.applyControl(aircraft, -output.x(), output.y(), output.z(),
                output.engineTarget());
        AutopilotLogManager.writeControlAdapter(level.getServer(), aircraft,
                AutonomousFlightManager.status(aircraft.getUUID())
                        .map(AutonomousFlightManager.SessionStatus::phase)
                        .orElse(FlightPhase.ABORTED),
                "stage=" + state.stage
                        + ":recovery_ticks=" + state.recoveryTicks
                        + ":turn_sign=" + state.turnSign
                        + ":turn_flipped=" + state.turnFlipped
                        + ":raw_target_angle=" + round(rawTargetAngle),
                snapshot, baseline(snapshot), output);
    }

    private static double shortestTurnSign(FlightSnapshot snapshot, Vec3 targetDirection,
                                           Entity attacker) {
        Vec3 horizontalTarget = safeNormalize(horizontal(targetDirection),
                snapshot.horizontalForward());
        double desiredYaw = Math.toDegrees(Math.atan2(-horizontalTarget.x, horizontalTarget.z));
        double headingError = Mth.wrapDegrees((float) (desiredYaw - snapshot.yawDeg()));
        if (Math.abs(headingError) >= 3.0) {
            return headingError > 0.0 ? 1.0 : -1.0;
        }
        FlightSnapshot attackerSnapshot = FlightSnapshot.capture(attacker);
        if (Math.abs(attackerSnapshot.rollDeg()) >= 4.0) {
            return attackerSnapshot.rollDeg() < 0.0 ? 1.0 : -1.0;
        }
        return 1.0;
    }

    private static Optional<Threat> findThreat(ServerLevel level, Entity defender,
                                                LivingEntity defenderPilot) {
        AABB area = defender.getBoundingBox().inflate(
                SEARCH_HORIZONTAL, SEARCH_VERTICAL, SEARCH_HORIZONTAL);
        return level.getEntities(defender, area,
                        candidate -> ReflectiveAircraft.isAirplane(candidate)
                                && !candidate.isRemoved())
                .stream()
                .map(candidate -> observedThreat(candidate, defender, defenderPilot))
                .flatMap(Optional::stream)
                .max(Comparator.comparingDouble(Threat::score));
    }

    private static Optional<Threat> observedThreat(Entity attacker, Entity defender,
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
        double aimAngle = AirCombatManeuverManager
                .currentAim(attacker.getUUID(), defenderPilot.getUUID())
                .map(AirCombatManeuverManager.AimSolution::angleOffNoseDeg)
                .orElse(selected.get().angleOffNoseDeg());
        double closure = relativeClosureBps(defender, attacker);
        boolean imminent = selected.get().lineOfSight()
                && distance >= 18.0 && distance <= 135.0 && aimAngle <= 4.5;
        double score = (SEARCH_HORIZONTAL - Math.min(SEARCH_HORIZONTAL, distance))
                + Math.max(0.0, 30.0 - aimAngle)
                + Math.max(0.0, closure) * 2.0
                + (imminent ? 200.0 : 0.0);
        return Optional.of(new Threat(attacker, attackerPilot.getUUID(), distance,
                aimAngle, closure, selected.get().lineOfSight(), imminent, score));
    }

    private static Optional<Threat> fallbackThreat(ServerLevel level, Entity defender,
                                                   State state) {
        Entity attacker = level.getEntity(state.attackerUuid);
        if (attacker == null || attacker.isRemoved()) {
            return Optional.empty();
        }
        Entity pilot = attacker.getControllingPassenger();
        UUID pilotUuid = pilot == null ? state.attackerPilotUuid : pilot.getUUID();
        double distance = attacker.distanceTo(defender);
        double closure = relativeClosureBps(defender, attacker);
        return Optional.of(new Threat(attacker, pilotUuid, distance,
                180.0, closure, false, false, 0.0));
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

    private static boolean hardThreat(Threat threat, double rawTargetAngle) {
        if (!threat.lineOfSight() || rawTargetAngle <= 58.0) {
            return false;
        }
        boolean closeAligned = threat.distance() <= 82.0
                && threat.attackerAimAngleDeg() <= 3.2;
        boolean closingAligned = threat.distance() <= 105.0
                && threat.closureBps() >= 8.0
                && threat.attackerAimAngleDeg() <= 5.0;
        return closeAligned || closingAligned;
    }

    private static Vec3 directionTo(Entity from, Entity to, Vec3 fallback) {
        return safeNormalize(to.getBoundingBox().getCenter()
                .subtract(from.getBoundingBox().getCenter()), fallback);
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
                + ":turn_flipped=" + state.turnFlipped
                + ":missing_threat_ticks=" + state.missingThreatTicks
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
        ZOOM_REVERSAL,
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
        private final double startAltitude;
        private double turnSign;
        private double bestRawTargetAngle;
        private Stage stage = Stage.ZOOM_REVERSAL;
        private int stageTicks;
        private int recoveryTicks;
        private int statusTicks;
        private int worseningTicks;
        private int missingThreatTicks;
        private boolean turnFlipped;

        private State(UUID attackerUuid, UUID attackerPilotUuid,
                      int initialShotsRemaining, double turnSign,
                      double startAltitude, double initialRawTargetAngle) {
            this.attackerUuid = attackerUuid;
            this.attackerPilotUuid = attackerPilotUuid;
            this.initialShotsRemaining = initialShotsRemaining;
            this.turnSign = turnSign;
            this.startAltitude = startAltitude;
            this.bestRawTargetAngle = initialRawTargetAngle;
        }
    }
}
