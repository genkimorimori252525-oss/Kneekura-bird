package com.wwdebug.autopilot;

import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.Mob;

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
        return evaluateWithDefensivePilot(aircraft, collisionRisk).outcome();
    }

    record CombatEvaluation(ControlOutcome outcome, Mob defensivePilot, ServerLevel defensiveLevel,
                            boolean defensiveProposal, AirCombatManeuverManager.OffensiveEvaluation offensive,
                            EnergyFighterApexYawAdapter.EnergyEvaluation energy) {
        CombatEvaluation(ControlOutcome outcome, Mob defensivePilot, ServerLevel defensiveLevel,
                         boolean defensiveProposal) {
            this(outcome, defensivePilot, defensiveLevel, defensiveProposal, null, null);
        }
        CombatEvaluation(ControlOutcome outcome, Mob defensivePilot, ServerLevel defensiveLevel,
                         boolean defensiveProposal, AirCombatManeuverManager.OffensiveEvaluation offensive) {
            this(outcome, defensivePilot, defensiveLevel, defensiveProposal, offensive, null);
        }
    }

    static CombatEvaluation evaluateWithDefensivePilot(Entity aircraft, boolean collisionRisk) {
        if (collisionRisk) {
            return new CombatEvaluation(ControlOutcome.none(), null, null, false);
        }
        if (!isFighter(aircraft)) {
            clear(aircraft.getUUID());
            return new CombatEvaluation(ControlOutcome.none(), null, null, false);
        }

        EnergyFighterApexYawAdapter.EnergyEvaluation energy = EnergyFighterApexYawAdapter.evaluateWithPilot(aircraft);
        if (energy.proposal().isPresent()) {
            return new CombatEvaluation(ControlOutcome.proposed(energy.proposal().get()), null, null, false, null, energy);
        }
        if (EnergyFighterApexYawAdapter.active(aircraft)) {
            // The state machine still owns this tick even when its DOCTRINE stage deliberately
            // produces no proposal. Lower combat layers must remain suppressed as before.
            return new CombatEvaluation(ControlOutcome.claimedWithoutProposal(
                    ControlAuthorityArbiter.Authority.ENERGY_FIGHTER_REENGAGEMENT), null, null, false);
        }

        DefensiveAirCombatManager.DefensiveEvaluation defensive = DefensiveAirCombatManager.evaluateWithPilot(aircraft);
        if (defensive.proposal().isPresent()) {
            return new CombatEvaluation(ControlOutcome.proposed(defensive.proposal().get()),
                    defensive.pilot(), defensive.level(), true);
        }
        if (DefensiveAirCombatManager.active(aircraft)) {
            // The layer holds a live defensive action but declined the tick, so nothing may be
            // written on its behalf. It still owns the tick for reporting purposes.
            return new CombatEvaluation(ControlOutcome.claimedWithoutProposal(
                    ControlAuthorityArbiter.Authority.DEFENSIVE_COMBAT), null, null, false);
        }

        AirCombatManeuverManager.OffensiveEvaluation offensive = AirCombatManeuverManager.evaluateWithPilot(aircraft);
        return new CombatEvaluation(offensive.proposal().map(ControlOutcome::proposed).orElseGet(ControlOutcome::none),
                null, null, false, offensive);

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
