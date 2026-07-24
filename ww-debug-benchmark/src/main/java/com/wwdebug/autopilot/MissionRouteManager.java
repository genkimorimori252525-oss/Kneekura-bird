package com.wwdebug.autopilot;

import net.minecraft.server.MinecraftServer;
import net.minecraft.world.phys.Vec3;

import java.util.LinkedHashMap;
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
    private static volatile MissionRouteSavedData persistentData;

    private MissionRouteManager() {
    }

    /** Bind a route only while the supplied assignment is still the aircraft's current mission. */
    public static Optional<Assignment> bind(UUID aircraftId,
                                            MissionOrderManager.Assignment mission,
                                            WaypointRoute route) {
        Objects.requireNonNull(aircraftId, "aircraftId");
        Objects.requireNonNull(mission, "mission");
        Objects.requireNonNull(route, "route");
        if (!MissionOrderManager.current(aircraftId).filter(mission::equals).isPresent()) {
            return Optional.empty();
        }
        Optional<Assignment> accepted = bindOwned(
                aircraftId, mission.revision(), mission.order().orderId(), route);
        if (!MissionOrderManager.current(aircraftId).filter(mission::equals).isPresent()) {
            clear(aircraftId, mission.revision(), mission.order().orderId());
            return Optional.empty();
        }
        return accepted;
    }

    /**
     * Internal ownership transition used by deterministic contracts and trusted restoration code.
     *
     * <p>A newer mission revision replaces the previous route. Rebinding the same mission is
     * idempotent and preserves route progress. Older revisions and equal-revision conflicts are
     * rejected so stale command delivery cannot rewind navigation.</p>
     */
    static Optional<Assignment> bindOwned(UUID aircraftId, long missionRevision,
                                          UUID orderId, WaypointRoute route) {
        Objects.requireNonNull(aircraftId, "aircraftId");
        Assignment candidate = new Assignment(missionRevision, orderId, route);
        Assignment[] accepted = new Assignment[1];
        boolean[] changed = new boolean[1];
        ASSIGNMENTS.compute(aircraftId, (id, existing) -> {
            if (existing == null || candidate.missionRevision() > existing.missionRevision()) {
                accepted[0] = candidate;
                changed[0] = true;
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
        if (changed[0]) {
            persist();
        }
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
        MissionOrderManager.Assignment mission = MissionOrderManager.current(aircraftId).orElse(null);
        if (mission == null
                || mission.revision() != expectedMissionRevision
                || !mission.order().orderId().equals(expectedOrderId)) {
            return Optional.empty();
        }

        Assignment[] matched = new Assignment[1];
        boolean[] changed = new boolean[1];
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
            changed[0] = result != existing;
            return result;
        });
        if (changed[0]) {
            persist();
        }
        return Optional.ofNullable(matched[0]);
    }

    public static boolean clear(UUID aircraftId, long expectedMissionRevision, UUID expectedOrderId) {
        Objects.requireNonNull(aircraftId, "aircraftId");
        Objects.requireNonNull(expectedOrderId, "expectedOrderId");
        Assignment existing = ASSIGNMENTS.get(aircraftId);
        boolean removed = existing != null
                && existing.missionRevision() == expectedMissionRevision
                && existing.orderId().equals(expectedOrderId)
                && ASSIGNMENTS.remove(aircraftId, existing);
        if (removed) {
            persist();
        }
        return removed;
    }

    public static void clear(UUID aircraftId) {
        if (ASSIGNMENTS.remove(Objects.requireNonNull(aircraftId, "aircraftId")) != null) {
            persist();
        }
    }

    public static Map<UUID, Assignment> snapshot() {
        return Map.copyOf(ASSIGNMENTS);
    }

    public static void clearAll() {
        if (!ASSIGNMENTS.isEmpty()) {
            ASSIGNMENTS.clear();
            persist();
        }
    }

    /** Restore only routes still owned by the mission assignments loaded for this server. */
    public static void bind(MinecraftServer server) {
        MissionRouteSavedData data = MissionRouteSavedData.get(server);
        Map<UUID, Assignment> stored = data.snapshot();
        Map<UUID, Assignment> matched = matchingAssignments(stored, MissionOrderManager.snapshot());
        persistentData = data;
        restore(matched);
        if (!matched.equals(stored)) {
            data.replace(matched);
        }
    }

    public static void unbind() {
        persist();
        persistentData = null;
        ASSIGNMENTS.clear();
    }

    static Map<UUID, Assignment> matchingAssignments(
            Map<UUID, Assignment> routes,
            Map<UUID, MissionOrderManager.Assignment> missions) {
        Map<UUID, Assignment> matched = new LinkedHashMap<>();
        routes.entrySet().stream()
                .sorted(Map.Entry.comparingByKey())
                .forEach(entry -> {
                    MissionOrderManager.Assignment mission = missions.get(entry.getKey());
                    Assignment route = entry.getValue();
                    if (mission != null
                            && mission.revision() == route.missionRevision()
                            && mission.order().orderId().equals(route.orderId())) {
                        matched.put(entry.getKey(), route);
                    }
                });
        return Map.copyOf(matched);
    }

    static void restore(Map<UUID, Assignment> values) {
        ASSIGNMENTS.clear();
        ASSIGNMENTS.putAll(values);
    }

    private static void persist() {
        MissionRouteSavedData data = persistentData;
        if (data != null) {
            data.replace(snapshot());
        }
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
