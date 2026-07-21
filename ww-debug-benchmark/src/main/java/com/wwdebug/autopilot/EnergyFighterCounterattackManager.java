package com.wwdebug.autopilot;

import com.wwdebug.benchmark.ReflectiveAircraft;
import com.wwdebug.benchmark.ReflectiveArmament;
import net.minecraft.server.level.ServerLevel;
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
 * Lets an energy fighter convert a successful defensive extension into a counterattack.
 *
 * <p>The normal defensive controller remains authoritative while an attacker is closing or has a
 * credible firing solution. This adapter only intervenes after the aircraft has opened meaningful
 * distance, the attacker is moving away relative to the defender, and the attacker has lost its
 * nose solution. During that recovery window, stale defensive reacquisition is suppressed and the
 * offensive selector is reset once so it cannot remain trapped in the extension that preceded the
 * defensive manoeuvre.</p>
 */
public final class EnergyFighterCounterattackManager {
    private static final double SEARCH_HORIZONTAL = 210.0;
    private static final double SEARCH_VERTICAL = 110.0;
    private static final double START_MIN_DISTANCE = 48.0;
    private static final double START_MAX_CLOSURE_BPS = -4.0;
    private static final double START_MIN_ATTACKER_AIM_ERROR_DEG = 5.5;
    private static final double IMMINENT_FIRE_ANGLE_DEG = 4.5;
    private static final double RENEWED_THREAT_MAX_AIM_ERROR_DEG = 8.0;
    private static final double RENEWED_THREAT_MIN_CLOSURE_BPS = 4.0;
    private static final double RENEWED_THREAT_MAX_DISTANCE = 105.0;
    private static final int MAX_RECOVERY_TICKS = 220;
    private static final Map<UUID, State> STATES = new ConcurrentHashMap<>();

    private EnergyFighterCounterattackManager() {
    }

    public static void applyControl(Entity aircraft) {
        if (aircraft.level().isClientSide || !(aircraft.level() instanceof ServerLevel level)
                || !ReflectiveAircraft.isAirplane(aircraft)
                || !ReflectiveAircraft.isControllable(aircraft)) {
            clear(aircraft.getUUID());
            return;
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
            return;
        }

        Threat threat = findThreat(level, aircraft, pilot).orElse(null);
        State state = STATES.get(aircraft.getUUID());
        if (state == null) {
            if (!DefensiveAirCombatManager.active(aircraft)
                    || threat == null || !staleOpening(threat)) {
                return;
            }
            state = new State(threat.attacker().getUUID(),
                    ReflectiveArmament.estimatedShotsRemaining(aircraft));
            STATES.put(aircraft.getUUID(), state);
            AirCombatManeuverManager.clear(aircraft.getUUID());
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "energy_counterattack_start",
                    description(state, threat)
                            + ":reason=stale_opening_rear_threat",
                    status.get().phase());
        }

        if (threat == null || !threat.attacker().getUUID().equals(state.attackerUuid)) {
            finish(level, aircraft, status.get().phase(), state, threat,
                    "attacker_no_longer_tracking");
            return;
        }
        int shotsRemaining = ReflectiveArmament.estimatedShotsRemaining(aircraft);
        if (shotsRemaining < state.initialShotsRemaining) {
            finish(level, aircraft, status.get().phase(), state, threat,
                    "counterattack_weapon_fire_confirmed");
            return;
        }
        if (threat.imminentFire() || renewedThreat(threat)) {
            AirCombatManeuverManager.clear(aircraft.getUUID());
            finish(level, aircraft, status.get().phase(), state, threat,
                    threat.imminentFire() ? "attacker_firing_solution_restored"
                            : "attacker_closure_restored");
            return;
        }
        if (state.recoveryTicks >= MAX_RECOVERY_TICKS) {
            finish(level, aircraft, status.get().phase(), state, threat,
                    "counterattack_window_timeout");
            return;
        }

        boolean defensiveWasActive = DefensiveAirCombatManager.active(aircraft);
        if (defensiveWasActive) {
            DefensiveAirCombatManager.clear(aircraft.getUUID());
            AirCombatManeuverManager.applyControl(aircraft);
            state.suppressedDefensiveTicks++;
        }
        state.recoveryTicks++;
        if (state.statusTicks++ % 20 == 0) {
            Optional<AirCombatManeuverManager.AimSolution> ownAim =
                    AirCombatManeuverManager.currentAim(aircraft.getUUID(), threat.attackerPilotUuid());
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "energy_counterattack_status",
                    description(state, threat)
                            + ":defensive_was_active=" + defensiveWasActive
                            + ":offensive_active=" + AirCombatManeuverManager.active(aircraft)
                            + ":own_lead_angle=" + ownAim
                            .map(AirCombatManeuverManager.AimSolution::angleOffNoseDeg)
                            .map(EnergyFighterCounterattackManager::round).orElse(-1.0)
                            + ":shots_remaining=" + shotsRemaining,
                    status.get().phase());
        }
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
        UUID attackerPilotUuid = attackerPilot == null
                ? selected.get().targetUuid() : attackerPilot.getUUID();
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
        return Optional.of(new Threat(attacker, attackerPilotUuid, distance,
                attackerAimAngle, closure, selected.get().lineOfSight(), imminentFire, score));
    }

    private static boolean staleOpening(Threat threat) {
        return threat.lineOfSight()
                && threat.distance() >= START_MIN_DISTANCE
                && threat.closureBps() <= START_MAX_CLOSURE_BPS
                && threat.attackerAimAngleDeg() >= START_MIN_ATTACKER_AIM_ERROR_DEG
                && !threat.imminentFire();
    }

    private static boolean renewedThreat(Threat threat) {
        return threat.lineOfSight()
                && threat.distance() <= RENEWED_THREAT_MAX_DISTANCE
                && threat.closureBps() >= RENEWED_THREAT_MIN_CLOSURE_BPS
                && threat.attackerAimAngleDeg() <= RENEWED_THREAT_MAX_AIM_ERROR_DEG;
    }

    private static void finish(ServerLevel level, Entity aircraft, FlightPhase phase,
                               State state, Threat threat, String reason) {
        STATES.remove(aircraft.getUUID());
        AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                "energy_counterattack_end",
                (threat == null ? stateDescription(state) : description(state, threat))
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

    private static String description(State state, Threat threat) {
        return stateDescription(state)
                + ":attacker_uuid=" + threat.attacker().getUUID()
                + ":distance=" + round(threat.distance())
                + ":attacker_aim_angle=" + round(threat.attackerAimAngleDeg())
                + ":closure=" + round(threat.closureBps())
                + ":line_of_sight=" + threat.lineOfSight()
                + ":imminent_fire=" + threat.imminentFire();
    }

    private static String stateDescription(State state) {
        return "recovery_ticks=" + state.recoveryTicks
                + ":suppressed_defensive_ticks=" + state.suppressedDefensiveTicks
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

    private static double round(double value) {
        return Math.rint(value * 100.0) / 100.0;
    }

    private record Threat(Entity attacker, UUID attackerPilotUuid, double distance,
                          double attackerAimAngleDeg, double closureBps,
                          boolean lineOfSight, boolean imminentFire, double score) {
    }

    private static final class State {
        private final UUID attackerUuid;
        private final int initialShotsRemaining;
        private int recoveryTicks;
        private int suppressedDefensiveTicks;
        private int statusTicks;

        private State(UUID attackerUuid, int initialShotsRemaining) {
            this.attackerUuid = attackerUuid;
            this.initialShotsRemaining = initialShotsRemaining;
        }
    }
}
