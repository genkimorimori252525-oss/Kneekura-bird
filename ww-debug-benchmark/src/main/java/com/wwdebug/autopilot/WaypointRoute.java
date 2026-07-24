package com.wwdebug.autopilot;

import net.minecraft.world.phys.Vec3;

import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;

/**
 * Immutable ordered navigation intent.
 *
 * <p>This type deliberately owns no aircraft controls. Progression is explicit and advances at most
 * one waypoint per call so overlapping arrival regions cannot skip ordered route intent.</p>
 */
public record WaypointRoute(UUID routeId, List<Waypoint> waypoints, int nextIndex) {
    public static final double MAX_ARRIVAL_RADIUS_BLOCKS = 512.0;

    public WaypointRoute {
        routeId = Objects.requireNonNull(routeId, "routeId");
        Objects.requireNonNull(waypoints, "waypoints");
        if (waypoints.isEmpty()) {
            throw new IllegalArgumentException("waypoints must not be empty");
        }
        waypoints = List.copyOf(waypoints);
        if (waypoints.stream().anyMatch(Objects::isNull)) {
            throw new IllegalArgumentException("waypoints must not contain null values");
        }
        if (nextIndex < 0 || nextIndex > waypoints.size()) {
            throw new IllegalArgumentException("nextIndex must be within the route bounds");
        }
    }

    public static WaypointRoute start(UUID routeId, List<Waypoint> waypoints) {
        return new WaypointRoute(routeId, waypoints, 0);
    }

    public Optional<Waypoint> currentWaypoint() {
        return completed() ? Optional.empty() : Optional.of(waypoints.get(nextIndex));
    }

    public int remainingWaypoints() {
        return waypoints.size() - nextIndex;
    }

    public boolean completed() {
        return nextIndex == waypoints.size();
    }

    public WaypointRoute advanceIfReached(Vec3 aircraftPosition) {
        requireFinite(aircraftPosition, "aircraftPosition");
        if (completed()) {
            return this;
        }
        Waypoint current = waypoints.get(nextIndex);
        double radiusSquared = current.arrivalRadius() * current.arrivalRadius();
        if (aircraftPosition.distanceToSqr(current.position()) > radiusSquared) {
            return this;
        }
        return new WaypointRoute(routeId, waypoints, nextIndex + 1);
    }

    private static Vec3 requireFinite(Vec3 value, String name) {
        Objects.requireNonNull(value, name);
        if (!Double.isFinite(value.x) || !Double.isFinite(value.y) || !Double.isFinite(value.z)) {
            throw new IllegalArgumentException(name + " must contain finite coordinates");
        }
        return value;
    }

    public record Waypoint(Vec3 position, double arrivalRadius) {
        public Waypoint {
            position = requireFinite(position, "position");
            if (!Double.isFinite(arrivalRadius)
                    || arrivalRadius <= 0.0
                    || arrivalRadius > MAX_ARRIVAL_RADIUS_BLOCKS) {
                throw new IllegalArgumentException(
                        "arrivalRadius must be finite, positive, and no greater than "
                                + MAX_ARRIVAL_RADIUS_BLOCKS);
            }
        }
    }
}
