package com.wwdebug.autopilot;

import net.minecraft.world.phys.Vec3;

import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * UUID-keyed route progress tied to a specific immutable mission assignment.
 *
 * <p>This manager stores navigation intent only. It does not write aircraft inputs, request control
 * authority, or enable weapons.</p>
 */
public final class MissionRouteManager {
    private static final Map<UUID, Assignment> ASSIGNMENTS = new ConcurrentHashMap<>();

    private MissionRouteManager() {
    }

    /**
     * Bind a route to a mission assignment.
     *
     * <p>A newer mission revision replaces the previous route. Rebinding the same mission is
     * idempotent and preserves route progress. Older revisions and equal-revision conflicts are
     * rejected so stale command delivery cannot rewind navigation.</p>
     */
    public static Optional<Assignment> bind(UUID aircraftId, long missionRevision,
                                            UUID orderId, WaypointRoute route) {
        Objects.requireNonNull(aircraftId, "aircraftId");
        Assignment candidate = new Assignment(missionRevision, orderId, route);
        Assignment[] accepted = new Assignment[1];
        ASSIGNMENTS.compute(aircraftId, (id, existing) -> {
            if (existing == null || candidate.missionRevision() > existing.missionRevision()) {
                accepted[0] = candidate;
                return candidate;
            }
            if (candidate.missionRevision() == existing.missionRevision()
                    && candidate.orderId().equals(existing.orderId())
                    && candidate.route().routeId().equals(existing.route().routeId())) {
                accepted[0] = existing;
                return existing;
            }
            return existing;
        });
        return Optional.ofNullable(accepted[0]);
    }

    public static Optional<Assignment> current(UUID aircraftId) {
        return Optional.ofNullable(ASSIGNMENTS.get(Objects.requireNonNull(aircraftId, "aircraftId")));
    }

    /** Advance at most one waypoint when the caller still owns the current mission assignment. */
    public static Optional<Assignment> advance(UUID aircraftId, long expectedMissionRevision,
                                               UUID expectedOrderId, Vec3 aircraftPosition) {
        Objects.requireNonNull(aircraftId, "aircraftId");
        Objects.requireNonNull(expectedOrderId, "expectedOrderId");
        Objects.requireNonNull(aircraftPosition, "aircraftPosition");
        Assignment[] matched = new Assignment[1];
        ASSIGNMENTS.computeIfPresent(aircraftId, (id, existing) -> {
            if (existing.missionRevision() != expectedMissionRevision
                    || !existing.orderId().equals(expectedOrderId)) {
                return existing;
            }
            WaypointRoute advanced = existing.route().advanceIfReached(aircraftPosition);
            Assignment result = advanced == existing.route()
                    ? existing
                    : new Assignment(existing.missionRevision(), existing.orderId(), advanced);
            matched[0] = result;
            return result;
        });
        return Optional.ofNullable(matched[0]);
    }

    public static boolean clear(UUID aircraftId, long expectedMissionRevision, UUID expectedOrderId) {
        Objects.requireNonNull(aircraftId, "aircraftId");
        Objects.requireNonNull(expectedOrderId, "expectedOrderId");
        Assignment existing = ASSIGNMENTS.get(aircraftId);
        return existing != null
                && existing.missionRevision() == expectedMissionRevision
                && existing.orderId().equals(expectedOrderId)
                && ASSIGNMENTS.remove(aircraftId, existing);
    }

    public static void clear(UUID aircraftId) {
        ASSIGNMENTS.remove(Objects.requireNonNull(aircraftId, "aircraftId"));
    }

    public static Map<UUID, Assignment> snapshot() {
        return Map.copyOf(ASSIGNMENTS);
    }

    public static void clearAll() {
        ASSIGNMENTS.clear();
    }

    public record Assignment(long missionRevision, UUID orderId, WaypointRoute route) {
        public Assignment {
            if (missionRevision <= 0) {
                throw new IllegalArgumentException("missionRevision must be positive");
            }
            orderId = Objects.requireNonNull(orderId, "orderId");
            route = Objects.requireNonNull(route, "route");
        }
    }
}
