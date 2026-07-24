package com.wwdebug.autopilot;

import net.minecraft.server.MinecraftServer;

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
    private static volatile MissionOrderSavedData persistentData;

    private MissionOrderManager() {
    }

    public static Assignment assign(UUID aircraftId, MissionOrder order) {
        Objects.requireNonNull(aircraftId, "aircraftId");
        Objects.requireNonNull(order, "order");
        Assignment assignment = new Assignment(nextRevision(), order);
        ASSIGNMENTS.put(aircraftId, assignment);
        persist();
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
            Assignment next = new Assignment(nextRevision(), replacement);
            updated[0] = next;
            return next;
        });
        if (updated[0] != null) {
            persist();
        }
        return Optional.ofNullable(updated[0]);
    }

    public static boolean clear(UUID aircraftId, long expectedRevision) {
        Objects.requireNonNull(aircraftId, "aircraftId");
        Assignment current = ASSIGNMENTS.get(aircraftId);
        boolean removed = current != null && current.revision() == expectedRevision
                && ASSIGNMENTS.remove(aircraftId, current);
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

    public static void bind(MinecraftServer server) {
        MissionOrderSavedData data = MissionOrderSavedData.get(server);
        persistentData = data;
        restore(data.snapshot());
    }

    public static void unbind() {
        persist();
        persistentData = null;
        ASSIGNMENTS.clear();
        REVISIONS.set(0L);
    }

    static void restore(Map<UUID, Assignment> values) {
        ASSIGNMENTS.clear();
        ASSIGNMENTS.putAll(values);
        long highestRevision = values.values().stream()
                .mapToLong(Assignment::revision)
                .max()
                .orElse(0L);
        REVISIONS.set(highestRevision);
    }

    private static long nextRevision() {
        return REVISIONS.updateAndGet(current -> {
            if (current >= Long.MAX_VALUE - 1L) {
                throw new IllegalStateException("mission revision space exhausted");
            }
            return current + 1L;
        });
    }

    private static void persist() {
        MissionOrderSavedData data = persistentData;
        if (data != null) {
            data.replace(snapshot());
        }
    }

    public record Assignment(long revision, MissionOrder order) {
        public Assignment {
            if (revision <= 0 || revision == Long.MAX_VALUE) {
                throw new IllegalArgumentException("revision must be positive and incrementable");
            }
            order = Objects.requireNonNull(order, "order");
        }
    }
}
