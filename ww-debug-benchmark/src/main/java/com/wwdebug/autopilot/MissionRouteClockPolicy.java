package com.wwdebug.autopilot;

import java.util.Objects;

/**
 * Pure clock policy for an owned route running inside the fixed demonstration mission.
 *
 * <p>The mission timeout remains frozen while a route owns navigation. During
 * {@link FlightPhase#CRUISE_OUTBOUND}, however, real route travel is allowed to satisfy the fixed
 * outbound-cruise sample. The counter saturates below the ordinary transition threshold so the
 * route cannot advance the phase underneath route ownership. Once the route completes, the
 * completion tick and next ordinary tick release the mission into {@code TURN_LEFT} without
 * replaying the whole cruise sample.</p>
 */
public final class MissionRouteClockPolicy {
    private static final int OUTBOUND_TRANSITION_TICKS = 240;
    private static final int OUTBOUND_HELD_END_TICKS = OUTBOUND_TRANSITION_TICKS - 2;

    private MissionRouteClockPolicy() {
    }

    /** Adjusts {@code phaseTicks} after {@link AutopilotSession#tick} incremented it. */
    public static int phaseTicksAfterHeldTick(FlightPhase phase, int phaseTicks) {
        Objects.requireNonNull(phase, "phase");
        requireNonNegative(phaseTicks, "phaseTicks");
        if (phase == FlightPhase.CRUISE_OUTBOUND) {
            return Math.min(phaseTicks, OUTBOUND_HELD_END_TICKS);
        }
        return Math.max(0, phaseTicks - 1);
    }

    /** Freezes the overall fixed-mission timeout while route navigation remains active. */
    public static int missionTicksAfterHeldTick(int missionTicks) {
        requireNonNegative(missionTicks, "missionTicks");
        return Math.max(0, missionTicks - 1);
    }

    static int outboundTransitionTicks() {
        return OUTBOUND_TRANSITION_TICKS;
    }

    static int outboundHeldEndTicks() {
        return OUTBOUND_HELD_END_TICKS;
    }

    private static void requireNonNegative(int value, String name) {
        if (value < 0) {
            throw new IllegalArgumentException(name + " must be non-negative");
        }
    }
}
