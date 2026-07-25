package com.wwdebug.autopilot;

import java.util.Objects;

/**
 * Pure feasibility calculation for returning from a route endpoint to the landing pattern.
 *
 * <p>This class does not change aircraft control, mission timeouts, route geometry, or landing
 * acceptance. It only compares a measured speed against a remaining distance and an existing
 * tick budget so validation can reject physically implausible scenarios before an expensive
 * real-physics run.</p>
 */
public final class PatternRejoinBudget {
    public static final double DEFAULT_TICKS_PER_SECOND = 20.0;

    private PatternRejoinBudget() {
    }

    public static Assessment atMeasuredTurnFloor(FlightProfile profile, double distanceBlocks,
                                                  int timeoutTicks) {
        Objects.requireNonNull(profile, "profile");
        return assess(distanceBlocks, profile.turnSpeedFloorBps(), timeoutTicks,
                DEFAULT_TICKS_PER_SECOND);
    }

    public static Assessment assess(double distanceBlocks, double targetSpeedBps,
                                    int timeoutTicks, double ticksPerSecond) {
        requireFinitePositive(distanceBlocks, "distanceBlocks");
        requireFinitePositive(targetSpeedBps, "targetSpeedBps");
        requireFinitePositive(ticksPerSecond, "ticksPerSecond");
        if (timeoutTicks <= 0) {
            throw new IllegalArgumentException("timeoutTicks must be positive");
        }

        double availableSeconds = timeoutTicks / ticksPerSecond;
        double idealReachBlocks = targetSpeedBps * availableSeconds;
        double marginBlocks = idealReachBlocks - distanceBlocks;
        double marginRatio = marginBlocks / distanceBlocks;
        double requiredSpeedBps = distanceBlocks / availableSeconds;
        return new Assessment(distanceBlocks, targetSpeedBps, timeoutTicks, ticksPerSecond,
                availableSeconds, idealReachBlocks, requiredSpeedBps, marginBlocks, marginRatio);
    }

    private static void requireFinitePositive(double value, String name) {
        if (!Double.isFinite(value) || value <= 0.0) {
            throw new IllegalArgumentException(name + " must be finite and positive");
        }
    }

    public record Assessment(double distanceBlocks, double targetSpeedBps, int timeoutTicks,
                             double ticksPerSecond, double availableSeconds,
                             double idealReachBlocks, double requiredSpeedBps,
                             double marginBlocks, double marginRatio) {
        public Assessment {
            requireFinitePositive(distanceBlocks, "distanceBlocks");
            requireFinitePositive(targetSpeedBps, "targetSpeedBps");
            requireFinitePositive(ticksPerSecond, "ticksPerSecond");
            requireFinitePositive(availableSeconds, "availableSeconds");
            requireFinitePositive(idealReachBlocks, "idealReachBlocks");
            requireFinitePositive(requiredSpeedBps, "requiredSpeedBps");
            if (timeoutTicks <= 0 || !Double.isFinite(marginBlocks)
                    || !Double.isFinite(marginRatio)) {
                throw new IllegalArgumentException("budget assessment values must be valid");
            }
        }

        public boolean canReachIdeally() {
            return marginBlocks >= 0.0;
        }

        public boolean hasMargin(double minimumRatio) {
            if (!Double.isFinite(minimumRatio) || minimumRatio < 0.0) {
                throw new IllegalArgumentException("minimumRatio must be finite and non-negative");
            }
            return marginRatio >= minimumRatio;
        }
    }
}
