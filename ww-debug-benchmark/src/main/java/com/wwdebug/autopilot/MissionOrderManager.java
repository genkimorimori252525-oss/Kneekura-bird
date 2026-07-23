package com.wwdebug.autopilot;

import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Thread-safe UUID keyed mission-order store with optimistic revision checks.
 *
 * <p>The manager owns intent only. It does not write aircraft controls and therefore cannot bypass
 * player, terrain, collision or weapon-safety authority.</p>
 */
public final class MissionOrderManager {
    private static final Map<UUID, Assignment> ASSIGNMENTS = new ConcurrentHashMap<>();
    private static final AtomicLong REVISIONS = new AtomicLong();

    private MissionOrderManager() {
    }

    public static Assignment assign(UUID aircraftId, MissionOrder order) {
        Objects.requireNonNull(aircraftId, "aircraftId");
        Objects.requireNonNull(order, "order");
        Assignment assignment = new Assignment(REVISIONS.incrementAndGet(), order);
        ASSIGNMENTS.put(aircraftId, assignment);
        return assignment;
    }

    public static Optional<Assignment> current(UUID aircraftId) {
        return Optional.ofNullable(ASSIGNMENTS.get(Objects.requireNonNull(aircraftId, "aircraftId")));
    }

    public static Optional<Assignment> replace(UUID aircraftId, long expectedRevision,
                                               MissionOrder replacement) {
        Objects.requireNonNull(aircraftId, "aircraftId");
        Objects.requireNonNull(replacement, "replacement");
        Assignment[] updated = new Assignment[1];
        ASSIGNMENTS.computeIfPresent(aircraftId, (id, existing) -> {
            if (existing.revision() != expectedRevision) {
                return existing;
            }
            Assignment next = new Assignment(REVISIONS.incrementAndGet(), replacement);
            updated[0] = next;
            return next;
        });
        return Optional.ofNullable(updated[0]);
    }

    public static boolean clear(UUID aircraftId, long expectedRevision) {
        Objects.requireNonNull(aircraftId, "aircraftId");
        Assignment current = ASSIGNMENTS.get(aircraftId);
        return current != null && current.revision() == expectedRevision
                && ASSIGNMENTS.remove(aircraftId, current);
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

    public record Assignment(long revision, MissionOrder order) {
        public Assignment {
            if (revision <= 0) {
                throw new IllegalArgumentException("revision must be positive");
            }
            order = Objects.requireNonNull(order, "order");
        }
    }
}
