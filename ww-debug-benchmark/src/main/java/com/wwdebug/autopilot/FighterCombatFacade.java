package com.wwdebug.autopilot;

import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;

import java.util.Optional;
import java.util.UUID;

/** Keeps fighter-only awareness, manoeuvre and weapon policy out of noncombat aircraft roles. */
public final class FighterCombatFacade {
    private FighterCombatFacade() {
    }

    /**
     * Runs the combat layers in their established order and reports what happened.
     *
     * <p>The early returns are load-bearing: at most one combat layer acts per tick, which is why
     * layers can be converted to proposals individually without two of them bidding at once.</p>
     *
     * <p>Separation suppression is unchanged, but its <em>reporting</em> moves to the arbiter. This
     * method returns {@link ControlOutcome#none()} when combat is suppressed; it never claimed to
     * be flying the aircraft in that case, since the avoidance manoeuvre is written by
     * {@code FormationFlightManager} earlier in the tick.</p>
     */
    public static ControlOutcome applyControl(Entity aircraft, boolean collisionRisk) {
        if (collisionRisk) {
            return ControlOutcome.none();
        }
        if (!isFighter(aircraft)) {
            clear(aircraft.getUUID());
            return ControlOutcome.none();
        }

        boolean energyFighterControl = EnergyFighterApexYawAdapter.applyControl(aircraft);
        if (energyFighterControl) {
            return ControlOutcome.alreadyWrote(
                    ControlAuthorityArbiter.Authority.ENERGY_FIGHTER_REENGAGEMENT);
        }

        Optional<ControlProposal> defensive = DefensiveAirCombatManager.applyControl(aircraft);
        if (defensive.isPresent()) {
            return ControlOutcome.proposed(defensive.get());
        }
        if (DefensiveAirCombatManager.active(aircraft)) {
            // The layer holds a live defensive action but declined the tick, so nothing may be
            // written on its behalf. It still owns the tick for reporting purposes.
            return ControlOutcome.alreadyWrote(ControlAuthorityArbiter.Authority.DEFENSIVE_COMBAT);
        }

        AirCombatManeuverManager.applyControl(aircraft);
        if (AirCombatManeuverManager.active(aircraft)) {
            return ControlOutcome.alreadyWrote(ControlAuthorityArbiter.Authority.OFFENSIVE_COMBAT);
        }
        return ControlOutcome.none();
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
