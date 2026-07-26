package com.wwdebug.autopilot;

import com.wwdebug.benchmark.BenchmarkManager;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Single entry point for aircraft control ownership.
 *
 * <p>Lower-priority controllers may prepare or apply their normal output first, but only the
 * highest eligible layer is allowed to remain the final writer for the tick. This preserves the
 * established order while giving future mission, bomber, fuel and landing controllers one shared
 * place to request authority.</p>
 */
public final class ControlAuthorityArbiter {
    private static final Map<UUID, Authority> LAST_AUTHORITY = new ConcurrentHashMap<>();

    private ControlAuthorityArbiter() {
    }

    /**
     * Control layers with their position in the Issue #7 priority stack.
     *
     * <p>{@link #priority()} is the authoritative ordering; declaration order is unchanged and
     * carries no meaning. Nothing may compare authority with {@code ordinal()}.</p>
     *
     * <p>Four documented levels have no constant because nothing implements them yet:</p>
     * <ul>
     *   <li>level 2, pilot lost or aircraft destroyed;</li>
     *   <li>level 3, critical damage;</li>
     *   <li>level 6, weapon-release safety, currently enforced inside
     *       {@code CombatWeaponManager} rather than as an authority;</li>
     *   <li>level 9, formation keeping — {@code FormationFlightManager} writes control, but the
     *       arbiter reports {@link #BASE_AUTONOMY} while it does, which is a misreport this
     *       numbering leaves room to fix.</li>
     * </ul>
     *
     * <p>The gaps in the numbers are deliberate so those levels can be inserted later without
     * renumbering everything around them.</p>
     */
    public enum Authority {
        /** No layer owns the tick. */
        NONE(0),
        /** Level 10 — ordinary navigation. */
        BASE_AUTONOMY(10),
        /** Level 8 — role mission. Peer of {@link #ENERGY_FIGHTER_REENGAGEMENT}. */
        OFFENSIVE_COMBAT(40),
        /** Level 8 — role mission. Peer of {@link #OFFENSIVE_COMBAT}. */
        ENERGY_FIGHTER_REENGAGEMENT(40),
        /** Level 7 — defensive manoeuvre. */
        DEFENSIVE_COMBAT(50),
        /** Level 5 — aircraft-to-aircraft separation. */
        COLLISION_AVOIDANCE(70),
        /** Level 4 — terrain and building avoidance. */
        TERRAIN_AVOIDANCE(80),
        /** Level 1 — absolute; no automated writer may run. */
        PLAYER_CONTROLLED(110);

        private final int priority;

        Authority(int priority) {
            this.priority = priority;
        }

        /** Higher wins. Equal values are peers at the same level of the stack. */
        public int priority() {
            return priority;
        }

        /** Strictly higher priority. Peers do not outrank each other. */
        public boolean outranks(Authority other) {
            return other == null || priority > other.priority;
        }
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
        Authority authority = decide(aircraft);
        recordAuthorityChange(aircraft, authority);
        return authority;
    }

    private static Authority decide(Entity aircraft) {
        if (aircraft.level().isClientSide) {
            return Authority.NONE;
        }

        if (MobPilotGate.isPlayerControlled(aircraft)) {
            clearAutomatedControl(aircraft);
            return Authority.PLAYER_CONTROLLED;
        }

        BenchmarkManager.applyControl(aircraft);
        AutonomousFlightManager.applyControl(aircraft);
        MutualDogfightMissionHoldAdapter.apply(aircraft);
        FormationFlightManager.applyControl(aircraft);

        Authority combatAuthority = FighterCombatFacade.applyControl(
                aircraft, AirspaceSafetyProbe.collisionRisk(aircraft));
        if (combatAuthority != Authority.NONE) {
            return combatAuthority;
        }
        if (TerrainAvoidancePlanner.active(aircraft)) {
            return Authority.TERRAIN_AVOIDANCE;
        }
        return AutonomousFlightManager.status(aircraft.getUUID()).isPresent()
                ? Authority.BASE_AUTONOMY : Authority.NONE;
    }

    /**
     * Records ownership handovers so a priority inversion becomes visible.
     *
     * <p>{@code applyControl}'s return value had no reader anywhere — the mixin that calls it
     * discards the result — so which layer actually owned a tick was unobservable. Verifying that
     * the coming arbiter conversion preserves behaviour is not possible without this.</p>
     *
     * <p>Only transitions are written. A row per aircraft per tick would swamp the log while
     * adding nothing: the interesting event is the handover, not the steady state.</p>
     */
    private static void recordAuthorityChange(Entity aircraft, Authority authority) {
        UUID aircraftUuid = aircraft.getUUID();
        if (aircraft.isRemoved()) {
            LAST_AUTHORITY.remove(aircraftUuid);
            return;
        }
        if (!(aircraft.level() instanceof ServerLevel level)) {
            return;
        }

        Authority previous = authority == Authority.NONE
                ? LAST_AUTHORITY.remove(aircraftUuid)
                : LAST_AUTHORITY.put(aircraftUuid, authority);
        if (previous == authority || (previous == null && authority == Authority.NONE)) {
            return;
        }

        Authority from = previous == null ? Authority.NONE : previous;
        FlightPhase phase = AutonomousFlightManager.status(aircraftUuid)
                .map(AutonomousFlightManager.SessionStatus::phase)
                .orElse(FlightPhase.ABORTED);
        AutopilotLogManager.writeEvent(level.getServer(), aircraft, "control_authority_change",
                "from=" + from.name() + ":to=" + authority.name()
                        + ":from_priority=" + from.priority()
                        + ":to_priority=" + authority.priority()
                        + ":escalation=" + authority.outranks(from),
                phase);
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
