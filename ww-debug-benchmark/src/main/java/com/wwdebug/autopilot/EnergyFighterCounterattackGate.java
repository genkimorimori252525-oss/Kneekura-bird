package com.wwdebug.autopilot;

import com.wwdebug.benchmark.ReflectiveAircraft;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.LivingEntity;

import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Prevents an energy-fighter counterattack from starting after the opponent has already escaped the
 * useful re-entry envelope.
 *
 * <p>Once the counterattack controller has accepted a start, this gate keeps calling it until that
 * controller releases ownership. The distance limit therefore applies only to a new start and does
 * not interrupt a valid high-yo-yo merely because the range briefly grows during the reversal.</p>
 */
public final class EnergyFighterCounterattackGate {
    private static final double MAX_START_DISTANCE = 155.0;
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
                || startTargetDistance(level, aircraft) > MAX_START_DISTANCE) {
            return false;
        }

        boolean owned = EnergyFighterCounterattackManager.applyControl(aircraft);
        if (owned) {
            ACTIVE.add(aircraftUuid);
        }
        return owned;
    }

    private static double startTargetDistance(ServerLevel level, Entity aircraft) {
        return CombatAwarenessManager.currentSolution(aircraft.getUUID())
                .map(solution -> level.getEntity(solution.targetUuid()))
                .filter(LivingEntity.class::isInstance)
                .map(LivingEntity.class::cast)
                .map(target -> {
                    Entity pursuitTarget = target.getVehicle();
                    return pursuitTarget != null && ReflectiveAircraft.isAirplane(pursuitTarget)
                            ? pursuitTarget : target;
                })
                .map(aircraft::distanceTo)
                .orElse(Double.POSITIVE_INFINITY);
    }

    public static void clear(UUID aircraftUuid) {
        ACTIVE.remove(aircraftUuid);
        EnergyFighterCounterattackManager.clear(aircraftUuid);
    }
}
