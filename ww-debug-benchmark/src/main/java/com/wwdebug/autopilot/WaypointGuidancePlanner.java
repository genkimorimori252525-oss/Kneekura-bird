package com.wwdebug.autopilot;

import net.minecraft.world.phys.Vec3;

import java.util.Objects;
import java.util.Optional;

/** Pure waypoint-to-guidance calculation with no aircraft input authority. */
public final class WaypointGuidancePlanner {
    private static final double MIN_HORIZONTAL_DIRECTION_SQUARED = 1.0e-8;

    private WaypointGuidancePlanner() {
    }

    /**
     * Advance at most one reached waypoint and calculate the next horizontal guidance target.
     *
     * @param targetSpeedBps measured-profile speed selected by the caller
     */
    public static Decision plan(Vec3 aircraftPosition, Vec3 aircraftForward,
                                WaypointRoute route, double targetSpeedBps) {
        Vec3 position = requireFinite(aircraftPosition, "aircraftPosition");
        Vec3 forward = requireFinite(aircraftForward, "aircraftForward");
        Objects.requireNonNull(route, "route");
        if (!Double.isFinite(targetSpeedBps) || targetSpeedBps <= 0.0) {
            throw new IllegalArgumentException("targetSpeedBps must be finite and positive");
        }

        WaypointRoute advanced = route.advanceIfReached(position);
        boolean waypointAdvanced = advanced != route;
        if (advanced.completed()) {
            return new Decision(advanced, Optional.empty(), waypointAdvanced);
        }

        WaypointRoute.Waypoint waypoint = advanced.currentWaypoint().orElseThrow();
        Vec3 offset = waypoint.position().subtract(position);
        Vec3 horizontal = new Vec3(offset.x, 0.0, offset.z);
        double horizontalDistance = horizontal.length();
        if (horizontal.lengthSqr() < MIN_HORIZONTAL_DIRECTION_SQUARED) {
            horizontal = new Vec3(forward.x, 0.0, forward.z);
            if (horizontal.lengthSqr() < MIN_HORIZONTAL_DIRECTION_SQUARED) {
                throw new IllegalArgumentException(
                        "aircraftForward must have a horizontal direction when waypoint bearing is undefined");
            }
        }

        GuidanceTarget target = new GuidanceTarget(
                horizontal.normalize(),
                waypoint.position().y,
                targetSpeedBps,
                horizontalDistance,
                waypoint.position().y - position.y);
        return new Decision(advanced, Optional.of(target), waypointAdvanced);
    }

    private static Vec3 requireFinite(Vec3 value, String name) {
        Objects.requireNonNull(value, name);
        if (!Double.isFinite(value.x) || !Double.isFinite(value.y) || !Double.isFinite(value.z)) {
            throw new IllegalArgumentException(name + " must contain finite coordinates");
        }
        return value;
    }

    public record Decision(WaypointRoute route, Optional<GuidanceTarget> target,
                           boolean waypointAdvanced) {
        public Decision {
            route = Objects.requireNonNull(route, "route");
            target = Objects.requireNonNull(target, "target");
            if (route.completed() != target.isEmpty()) {
                throw new IllegalArgumentException(
                        "completed route state and guidance target presence must agree");
            }
        }

        public boolean completed() {
            return target.isEmpty();
        }
    }

    public record GuidanceTarget(Vec3 horizontalDirection, double targetAltitude,
                                 double targetSpeedBps, double horizontalDistance,
                                 double verticalError) {
        public GuidanceTarget {
            horizontalDirection = requireFinite(horizontalDirection, "horizontalDirection");
            if (horizontalDirection.y != 0.0
                    || Math.abs(horizontalDirection.lengthSqr() - 1.0) > 1.0e-6) {
                throw new IllegalArgumentException(
                        "horizontalDirection must be a normalized horizontal vector");
            }
            if (!Double.isFinite(targetAltitude)) {
                throw new IllegalArgumentException("targetAltitude must be finite");
            }
            if (!Double.isFinite(targetSpeedBps) || targetSpeedBps <= 0.0) {
                throw new IllegalArgumentException("targetSpeedBps must be finite and positive");
            }
            if (!Double.isFinite(horizontalDistance) || horizontalDistance < 0.0) {
                throw new IllegalArgumentException("horizontalDistance must be finite and non-negative");
            }
            if (!Double.isFinite(verticalError)) {
                throw new IllegalArgumentException("verticalError must be finite");
            }
        }
    }
}
