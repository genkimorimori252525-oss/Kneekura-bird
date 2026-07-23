package com.wwdebug.autopilot;

import com.wwdebug.benchmark.ReflectiveAircraft;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.player.Player;

import java.lang.reflect.Field;
import java.util.Map;
import java.util.UUID;

/**
 * Prevents the ordinary validation mission from advancing while the reciprocal dogfight scene owns
 * the aircraft.
 *
 * <p>The combat controllers still own flight input. This adapter only keeps the background
 * validation session in a neutral cruise phase so its turn, stall, and landing timeouts cannot
 * terminate either participant before the bounded combat window completes. Removing the mutual
 * faction tags releases the hold and lets the primary aircraft resume the normal mission.</p>
 */
public final class MutualDogfightMissionHoldAdapter {
    private static final String SCENARIO_PROPERTY = "wwdebug.flightGameTestScenario";
    private static final String SCENARIO = "dogfight_mutual";
    private static final String TEST_NAME_PREFIX = "AUTOPILOT TEST ";
    private static final String RED_FACTION = "wwcombat:faction:red";
    private static final String BLUE_FACTION = "wwcombat:faction:blue";
    private static final String HOSTILE_RED = "wwcombat:hostile:red";
    private static final String HOSTILE_BLUE = "wwcombat:hostile:blue";

    private static final Field SESSIONS = field(AutonomousFlightManager.class, "SESSIONS");
    private static final Field ENTRY_SESSION = sessionEntryField("session");
    private static final Field PHASE = field(AutopilotSession.class, "phase");
    private static final Field PHASE_TICKS = field(AutopilotSession.class, "phaseTicks");
    private static final Field STABLE_TICKS = field(AutopilotSession.class, "stableTicks");
    private static final Field FALLING_TICKS = field(AutopilotSession.class, "fallingTicks");
    private static final Field TRANSITION_REASON = field(AutopilotSession.class, "transitionReason");

    private MutualDogfightMissionHoldAdapter() {
    }

    public static void apply(Entity aircraft) {
        if (aircraft.level().isClientSide
                || !SCENARIO.equals(System.getProperty(SCENARIO_PROPERTY, "")
                .trim().toLowerCase())
                || !ReflectiveAircraft.isAirplane(aircraft)
                || !aircraft.getName().getString().startsWith(TEST_NAME_PREFIX)
                || !hasMutualCombatTags(aircraft)) {
            return;
        }

        Entity pilot = aircraft.getControllingPassenger();
        if (pilot instanceof Player || !(pilot instanceof Mob)) {
            return;
        }

        AutonomousFlightManager.status(aircraft.getUUID()).ifPresent(status -> {
            if (!status.phase().isTerminal() && !status.phase().isLandingPhase()) {
                holdNeutralCruise(aircraft.getUUID());
            }
        });
    }

    private static boolean hasMutualCombatTags(Entity aircraft) {
        boolean redParticipant = aircraft.getTags().contains(RED_FACTION)
                && aircraft.getTags().contains(HOSTILE_BLUE);
        boolean blueParticipant = aircraft.getTags().contains(BLUE_FACTION)
                && aircraft.getTags().contains(HOSTILE_RED);
        return redParticipant || blueParticipant;
    }

    @SuppressWarnings("unchecked")
    private static void holdNeutralCruise(UUID aircraftUuid) {
        try {
            Map<UUID, Object> sessions = (Map<UUID, Object>) SESSIONS.get(null);
            Object entry = sessions.get(aircraftUuid);
            if (entry == null) {
                return;
            }
            Object session = ENTRY_SESSION.get(entry);
            PHASE.set(session, FlightPhase.CRUISE_OUTBOUND);
            PHASE_TICKS.setInt(session, 0);
            STABLE_TICKS.setInt(session, 0);
            FALLING_TICKS.setInt(session, 0);
            TRANSITION_REASON.set(session, "mutual_dogfight_mission_hold");
        } catch (IllegalAccessException exception) {
            throw new IllegalStateException("Could not hold reciprocal-dogfight mission phase",
                    exception);
        }
    }

    private static Field field(Class<?> owner, String name) {
        try {
            Field field = owner.getDeclaredField(name);
            field.setAccessible(true);
            return field;
        } catch (NoSuchFieldException exception) {
            throw new ExceptionInInitializerError(exception);
        }
    }

    private static Field sessionEntryField(String name) {
        try {
            Class<?> entry = Class.forName(
                    "com.wwdebug.autopilot.AutonomousFlightManager$SessionEntry");
            Field field = entry.getDeclaredField(name);
            field.setAccessible(true);
            return field;
        } catch (ClassNotFoundException | NoSuchFieldException exception) {
            throw new ExceptionInInitializerError(exception);
        }
    }
}
