package com.wwdebug.autopilot;

import com.wwdebug.benchmark.BenchmarkManager;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.player.Player;

/**
 * Single entry point for aircraft control ownership.
 *
 * <p>Lower-priority controllers may prepare or apply their normal output first, but only the
 * highest eligible layer is allowed to remain the final writer for the tick. This preserves the
 * established order while giving future mission, bomber, fuel and landing controllers one shared
 * place to request authority.</p>
 */
public final class ControlAuthorityArbiter {
    private ControlAuthorityArbiter() {
    }

    public enum Authority {
        NONE,
        PLAYER_CONTROLLED,
        BASE_AUTONOMY,
        TERRAIN_AVOIDANCE,
        COLLISION_AVOIDANCE,
        OFFENSIVE_COMBAT,
        DEFENSIVE_COMBAT,
        ENERGY_FIGHTER_REENGAGEMENT
    }

    /**
     * Applies the established control stack and returns the final owner for this tick.
     *
     * <p>Priority, highest last: base benchmark/mission control, formation, offensive combat,
     * defensive combat, energy-fighter re-engagement and aircraft collision avoidance. Terrain
     * avoidance remains inside base autonomy and is also checked independently by every combat
     * controller. Player control is absolute and bypasses every automated writer.</p>
     */
    public static Authority applyControl(Entity aircraft) {
        if (aircraft.level().isClientSide) {
            return Authority.NONE;
        }

        if (aircraft.getControllingPassenger() instanceof Player) {
            clearAutomatedControl(aircraft);
            return Authority.PLAYER_CONTROLLED;
        }

        BenchmarkManager.applyControl(aircraft);
        AutonomousFlightManager.applyControl(aircraft);
        MutualDogfightMissionHoldAdapter.apply(aircraft);
        FormationFlightManager.applyControl(aircraft);

        boolean collisionRisk = AirspaceSafetyProbe.collisionRisk(aircraft);
        boolean energyFighterControl = false;
        if (!collisionRisk) {
            energyFighterControl = EnergyFighterApexYawAdapter.applyControl(aircraft);
            if (!energyFighterControl) {
                DefensiveAirCombatManager.applyControl(aircraft);
                if (!DefensiveAirCombatManager.active(aircraft)) {
                    AirCombatManeuverManager.applyControl(aircraft);
                }
            }
        }

        if (collisionRisk) {
            return Authority.COLLISION_AVOIDANCE;
        }
        if (energyFighterControl) {
            return Authority.ENERGY_FIGHTER_REENGAGEMENT;
        }
        if (DefensiveAirCombatManager.active(aircraft)) {
            return Authority.DEFENSIVE_COMBAT;
        }
        if (AirCombatManeuverManager.active(aircraft)) {
            return Authority.OFFENSIVE_COMBAT;
        }
        if (TerrainAvoidancePlanner.active(aircraft)) {
            return Authority.TERRAIN_AVOIDANCE;
        }
        return AutonomousFlightManager.status(aircraft.getUUID()).isPresent()
                ? Authority.BASE_AUTONOMY : Authority.NONE;
    }

    private static void clearAutomatedControl(Entity aircraft) {
        // These calls take their existing player-controlled rejection paths, clearing any stale
        // session or manoeuvre state without writing aircraft input.
        AutonomousFlightManager.applyControl(aircraft);
        FormationFlightManager.applyControl(aircraft);
        EnergyFighterApexYawAdapter.applyControl(aircraft);
        DefensiveAirCombatManager.applyControl(aircraft);
        AirCombatManeuverManager.applyControl(aircraft);
    }
}
