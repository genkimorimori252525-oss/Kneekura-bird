package com.wwdebug.autopilot;

import java.util.Objects;

/** Selects a measured speed target for the long transit back to the landing pattern. */
public final class ReturnToPatternSpeedPolicy {
    private ReturnToPatternSpeedPolicy() {
    }

    /**
     * Keeps the existing approach and climb margins while ensuring that a large-heading-change
     * pattern rejoin does not command less than the measured sustainable turn-speed floor.
     */
    public static double targetSpeedBps(FlightProfile profile) {
        Objects.requireNonNull(profile, "profile");
        return Math.max(
                Math.max(profile.approachSpeedBps() * 1.25, profile.climbTargetSpeedBps()),
                profile.turnSpeedFloorBps());
    }
}
