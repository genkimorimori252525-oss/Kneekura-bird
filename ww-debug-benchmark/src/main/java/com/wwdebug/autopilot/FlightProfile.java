package com.wwdebug.autopilot;

import net.minecraft.resources.ResourceLocation;

import javax.annotation.Nullable;

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
    }

    public boolean isFighter() {
        return "fighter".equalsIgnoreCase(role);
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

    private static double positive(double value, String field) {
        if (!Double.isFinite(value) || value <= 0.0) {
            throw new IllegalArgumentException(field + " must be finite and positive");
        }
        return value;
    }
}