package com.wwdebug.autopilot;

import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.ListTag;
import net.minecraft.nbt.Tag;

import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

/**
 * Assesses an already-decoded assignment compound without modifying it or accessing storage.
 * CLEAN means all inspected entries are decodable; it does not prove file provenance, restore
 * completion, durable persistence, or permission to operate weapons.
 */
public final class MissionOrderLoadAssessment {
    public enum Status { CLEAN, UNKNOWN }

    public static final class Result {
        private final Status status;
        private final Map<UUID, MissionOrderManager.Assignment> assignments;

        private Result(Status status, Map<UUID, MissionOrderManager.Assignment> assignments) {
            this.status = status;
            this.assignments = Map.copyOf(assignments);
        }

        public Status status() { return status; }
        public Map<UUID, MissionOrderManager.Assignment> assignments() { return assignments; }
    }

    private record RevisionKey(UUID aircraft, long revision) { }

    private static final Result UNKNOWN = new Result(Status.UNKNOWN, Map.of());

    private MissionOrderLoadAssessment() { }

    public static Result assess(CompoundTag root) {
        if (root == null || !(root.get("assignments") instanceof ListTag entries)
                || (!entries.isEmpty() && entries.getElementType() != Tag.TAG_COMPOUND)) {
            return UNKNOWN;
        }

        Map<UUID, MissionOrderManager.Assignment> latest = new HashMap<>();
        Map<RevisionKey, MissionOrder> revisions = new HashMap<>();
        for (int index = 0; index < entries.size(); index++) {
            CompoundTag entry = entries.getCompound(index);
            if (!entry.hasUUID("aircraft_id") || !entry.contains("revision", Tag.TAG_LONG)
                    || !entry.contains("order", Tag.TAG_COMPOUND)) {
                return UNKNOWN;
            }
            long revision = entry.getLong("revision");
            if (revision <= 0 || revision >= Long.MAX_VALUE - 1L) {
                return UNKNOWN;
            }
            CompoundTag orderTag = entry.getCompound("order");
            if (invalidOptionalUuid(orderTag, "target_entity")
                    || invalidOptionalUuid(orderTag, "formation_id")
                    || invalidOptionalUuid(orderTag, "leader_aircraft")) {
                return UNKNOWN;
            }
            try {
                UUID aircraft = entry.getUUID("aircraft_id");
                MissionOrder order = MissionOrderCodec.read(orderTag);
                RevisionKey key = new RevisionKey(aircraft, revision);
                MissionOrder previous = revisions.putIfAbsent(key, order);
                if (previous != null && !previous.equals(order)) {
                    return UNKNOWN;
                }
                MissionOrderManager.Assignment candidate = new MissionOrderManager.Assignment(revision, order);
                MissionOrderManager.Assignment old = latest.get(aircraft);
                if (old == null || revision > old.revision()) {
                    latest.put(aircraft, candidate);
                }
            } catch (IllegalArgumentException exception) {
                return UNKNOWN;
            }
        }
        return new Result(Status.CLEAN, latest);
    }

    private static boolean invalidOptionalUuid(CompoundTag tag, String key) {
        return tag.contains(key) && !tag.hasUUID(key);
    }
}
