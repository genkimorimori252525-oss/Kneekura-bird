package com.wwdebug.autopilot;

import com.wwdebug.benchmark.ReflectiveAircraft;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.phys.Vec3;

import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Admits an energy-fighter counterattack only after the defensive extension is genuinely complete.
 *
 * <p>A useful re-entry needs more than a maximum range. The fighter must have opened meaningful
 * spacing, still be inside the recoverable envelope, be rapidly increasing that spacing, and have
 * forced the attacker well away from a firing solution. Once the counterattack controller accepts
 * a start, this gate keeps calling it until that controller releases ownership, so the admission
 * limits never interrupt a valid high yo-yo already in progress.</p>
 */
public final class EnergyFighterCounterattackGate {
    private static final double MIN_START_DISTANCE = 105.0;
    private static final double MAX_START_DISTANCE = 175.0;
    private static final double MAX_START_CLOSURE_BPS = -20.0;
    private static final double MIN_ATTACKER_AIM_ERROR_DEG = 45.0;
    private static final Set<UUID> ACTIVE = ConcurrentHashMap.newKeySet();

    private EnergyFighterCounterattackGate() {
    }

    public static boolean applyControl(Entity aircraft) {
        UUID aircraftUuid = aircraft.getUUID();
        if (ACTIVE.contains(aircraftUuid)) {
            boolean owned = EnergyFighterCounterattackManager.applyControl(aircraft);
            if (!owned) {
                ACTIVE.remove(aircraftUuid);
            }
            return owned;
        }

        if (!(aircraft.level() instanceof ServerLevel level)
                || aircraft.level().isClientSide
                || !ReflectiveAircraft.isAirplane(aircraft)
                || !startGeometryReady(level, aircraft)) {
            return false;
        }

        boolean owned = EnergyFighterCounterattackManager.applyControl(aircraft);
        if (owned) {
            ACTIVE.add(aircraftUuid);
        }
        return owned;
    }

    private static boolean startGeometryReady(ServerLevel level, Entity aircraft) {
        StartGeometry geometry = startGeometry(level, aircraft).orElse(null);
        return geometry != null
                && geometry.distance() >= MIN_START_DISTANCE
                && geometry.distance() <= MAX_START_DISTANCE
                && geometry.closureBps() <= MAX_START_CLOSURE_BPS
                && geometry.attackerAimErrorDeg() >= MIN_ATTACKER_AIM_ERROR_DEG;
    }

    private static Optional<StartGeometry> startGeometry(ServerLevel level, Entity aircraft) {
        Entity defenderPilot = aircraft.getControllingPassenger();
        if (!(defenderPilot instanceof LivingEntity livingDefender)) {
            return Optional.empty();
        }
        return CombatAwarenessManager.currentSolution(aircraft.getUUID())
                .map(solution -> level.getEntity(solution.targetUuid()))
                .filter(LivingEntity.class::isInstance)
                .map(LivingEntity.class::cast)
                .map(targetPilot -> {
                    Entity attacker = targetPilot.getVehicle();
                    if (attacker == null || !ReflectiveAircraft.isAirplane(attacker)) {
                        attacker = targetPilot;
                    }
                    double distance = aircraft.distanceTo(attacker);
                    double closure = relativeClosureBps(aircraft, attacker);
                    double attackerAimError = attackerAimErrorDeg(
                            attacker, livingDefender.getUUID());
                    return new StartGeometry(distance, closure, attackerAimError);
                });
    }

    private static double attackerAimErrorDeg(Entity attacker, UUID defenderPilotUuid) {
        Optional<AirCombatManeuverManager.AimSolution> aim =
                AirCombatManeuverManager.currentAim(attacker.getUUID(), defenderPilotUuid);
        if (aim.isPresent()) {
            return aim.get().angleOffNoseDeg();
        }
        Optional<CombatTargetSelector.Solution> selected =
                CombatAwarenessManager.currentSolution(attacker.getUUID());
        if (selected.isPresent() && selected.get().targetUuid().equals(defenderPilotUuid)) {
            return selected.get().angleOffNoseDeg();
        }
        return 180.0;
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

    public static void clear(UUID aircraftUuid) {
        ACTIVE.remove(aircraftUuid);
        EnergyFighterCounterattackManager.clear(aircraftUuid);
    }

    private record StartGeometry(double distance, double closureBps,
                                 double attackerAimErrorDeg) {
    }
}
