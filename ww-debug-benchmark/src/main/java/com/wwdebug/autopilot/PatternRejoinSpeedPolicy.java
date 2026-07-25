package com.wwdebug.autopilot;

import java.util.Objects;

/** Pure measured-profile policy for the long transit back to the landing pattern. */
public final class PatternRejoinSpeedPolicy {
    private PatternRejoinSpeedPolicy() {
    }

    /**
     * Pattern rejoin begins with an arbitrary heading change and may cover a long distance. Keep the
     * existing approach margin and climb target, but never command below the measured turn-speed
     * floor while navigating toward the downwind entry.
     */
    public static double targetSpeedBps(FlightProfile profile) {
        Objects.requireNonNull(profile, "profile");
        return Math.max(profile.turnSpeedFloorBps(),
                Math.max(profile.approachSpeedBps() * 1.25, profile.climbTargetSpeedBps()));
    }
}
