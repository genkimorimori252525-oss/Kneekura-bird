package com.wwdebug.autopilot;

import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;

import java.util.UUID;

/** Keeps fighter-only awareness, manoeuvre and weapon policy out of noncombat aircraft roles. */
public final class FighterCombatFacade {
    private FighterCombatFacade() {
    }

    public static ControlAuthorityArbiter.Authority applyControl(Entity aircraft,
                                                                  boolean collisionRisk) {
        if (collisionRisk) {
            return ControlAuthorityArbiter.Authority.COLLISION_AVOIDANCE;
        }
        if (!isFighter(aircraft)) {
            clear(aircraft.getUUID());
            return ControlAuthorityArbiter.Authority.NONE;
        }

        boolean energyFighterControl = EnergyFighterApexYawAdapter.applyControl(aircraft);
        if (energyFighterControl) {
            return ControlAuthorityArbiter.Authority.ENERGY_FIGHTER_REENGAGEMENT;
        }

        DefensiveAirCombatManager.applyControl(aircraft);
        if (DefensiveAirCombatManager.active(aircraft)) {
            return ControlAuthorityArbiter.Authority.DEFENSIVE_COMBAT;
        }

        AirCombatManeuverManager.applyControl(aircraft);
        if (AirCombatManeuverManager.active(aircraft)) {
            return ControlAuthorityArbiter.Authority.OFFENSIVE_COMBAT;
        }
        return ControlAuthorityArbiter.Authority.NONE;
    }

    public static void tick(Entity aircraft) {
        if (!isFighter(aircraft)) {
            clear(aircraft.getUUID());
            return;
        }
        CombatAwarenessManager.tick(aircraft);
        CombatWeaponManager.tick(aircraft);
    }

    public static boolean isFighter(Entity aircraft) {
        if (!(aircraft.level() instanceof ServerLevel level) || aircraft.level().isClientSide) {
            return false;
        }
        return AutopilotProfileRegistry.resolve(level.getServer(), aircraft)
                .map(FlightProfile::isFighter)
                .orElse(false);
    }

    public static void clear(UUID aircraftUuid) {
        CombatAwarenessManager.clear(aircraftUuid);
        CombatWeaponManager.clear(aircraftUuid);
        DefensiveAirCombatManager.clear(aircraftUuid);
        AirCombatManeuverManager.clear(aircraftUuid);
    }
}
