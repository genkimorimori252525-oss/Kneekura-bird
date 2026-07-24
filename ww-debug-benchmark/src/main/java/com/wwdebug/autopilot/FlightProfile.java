package com.wwdebug.autopilot;

import net.minecraft.resources.ResourceLocation;

import javax.annotation.Nullable;
import java.util.Locale;

public record FlightProfile(
        ResourceLocation profileId,
        String role,
        String doctrine,
        double stallGuardSpeedBps,
        double cruiseSpeedBps,
        double climbTargetSpeedBps,
        double turnSpeedFloorBps,
        @Nullable Double brakeLeadBlocks,
        @Nullable Double brakeDistanceLowerBoundBlocks,
        double measuredTopSpeedBps
) {
    public FlightProfile {
        role = role == null ? "unknown" : role;
        doctrine = doctrine == null ? "unknown" : doctrine;
        stallGuardSpeedBps = positive(stallGuardSpeedBps, "stallGuardSpeedBps");
        cruiseSpeedBps = positive(cruiseSpeedBps, "cruiseSpeedBps");
        climbTargetSpeedBps = positive(climbTargetSpeedBps, "climbTargetSpeedBps");
        turnSpeedFloorBps = positive(turnSpeedFloorBps, "turnSpeedFloorBps");
        measuredTopSpeedBps = positive(measuredTopSpeedBps, "measuredTopSpeedBps");

        if (isHeavyBomberRole(role)) {
            // A full-throttle sustained-turn sample is not a safe minimum-speed requirement.
            // Keep heavy aircraft above stall margin without making measured cruise immediately
            // trigger the turn-speed recovery limiter.
            double bomberFloor = Math.max(stallGuardSpeedBps * 1.15, cruiseSpeedBps * 0.90);
            turnSpeedFloorBps = Math.min(turnSpeedFloorBps, bomberFloor);
        }
    }

    public boolean isFighter() {
        return "fighter".equals(normalizedRole());
    }

    public boolean isLevelBomber() {
        return "bomber".equals(normalizedRole());
    }

    public boolean isAttacker() {
        return "attacker".equals(normalizedRole());
    }

    public boolean isTorpedoBomber() {
        return "torpedo_bomber".equals(normalizedRole());
    }

    public boolean supportsAutonomousFlight() {
        return isFighter() || isLevelBomber() || isAttacker() || isTorpedoBomber();
    }

    public double rotateSpeedBps() {
        return Math.max(stallGuardSpeedBps * 1.15, climbTargetSpeedBps * 0.82);
    }

    public double recoverySpeedBps() {
        return Math.max(climbTargetSpeedBps, stallGuardSpeedBps * 1.35);
    }

    public double approachSpeedBps() {
        return Math.min(cruiseSpeedBps * 0.82,
                Math.max(stallGuardSpeedBps * 1.25, turnSpeedFloorBps));
    }

    private String normalizedRole() {
        return normalizeRole(role);
    }

    private static boolean isHeavyBomberRole(String role) {
        String normalized = normalizeRole(role);
        return "bomber".equals(normalized) || "torpedo_bomber".equals(normalized);
    }

    private static String normalizeRole(String value) {
        return value == null ? "unknown"
                : value.trim().toLowerCase(Locale.ROOT).replace('-', '_').replace(' ', '_');
    }

    private static double positive(double value, String field) {
        if (!Double.isFinite(value) || value <= 0.0) {
            throw new IllegalArgumentException(field + " must be finite and positive");
        }
        return value;
    }
}
