package com.wwdebug.autopilot;

import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.ListTag;
import net.minecraft.nbt.Tag;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.level.saveddata.SavedData;

import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

/** Persistent world storage for mission assignments. */
public final class MissionOrderSavedData extends SavedData {
    private static final String DATA_NAME = "wwdebug_mission_orders";
    private final Map<UUID, MissionOrderManager.Assignment> assignments = new LinkedHashMap<>();

    public static MissionOrderSavedData get(MinecraftServer server) {
        return server.overworld().getDataStorage().computeIfAbsent(
                MissionOrderSavedData::load, MissionOrderSavedData::new, DATA_NAME);
    }

    public static MissionOrderSavedData load(CompoundTag root) {
        MissionOrderSavedData data = new MissionOrderSavedData();
        Set<UUID> conflictedAircraft = new HashSet<>();
        ListTag entries = root.getList("assignments", Tag.TAG_COMPOUND);
        for (int index = 0; index < entries.size(); index++) {
            CompoundTag entry = entries.getCompound(index);
            if (!entry.hasUUID("aircraft_id")
                    || !entry.contains("revision", Tag.TAG_LONG)
                    || !entry.contains("order", Tag.TAG_COMPOUND)) {
                continue;
            }
            try {
                UUID aircraftId = entry.getUUID("aircraft_id");
                if (conflictedAircraft.contains(aircraftId)) {
                    continue;
                }
                long revision = entry.getLong("revision");
                if (revision <= 0 || revision >= Long.MAX_VALUE - 1L) {
                    continue;
                }
                MissionOrder order = MissionOrderCodec.read(entry.getCompound("order"));
                MissionOrderManager.Assignment candidate = new MissionOrderManager.Assignment(revision, order);
                MissionOrderManager.Assignment existing = data.assignments.get(aircraftId);
                if (existing == null || candidate.revision() > existing.revision()) {
                    data.assignments.put(aircraftId, candidate);
                } else if (candidate.revision() == existing.revision()
                        && !candidate.order().equals(existing.order())) {
                    data.assignments.remove(aircraftId);
                    conflictedAircraft.add(aircraftId);
                }
            } catch (IllegalArgumentException ignored) {
                // Invalid entries are isolated so one corrupt assignment cannot discard all others.
            }
        }
        return data;
    }

    @Override
    public CompoundTag save(CompoundTag root) {
        ListTag entries = new ListTag();
        assignments.entrySet().stream()
                .sorted(Map.Entry.comparingByKey())
                .forEach(entry -> {
                    CompoundTag value = new CompoundTag();
                    value.putUUID("aircraft_id", entry.getKey());
                    value.putLong("revision", entry.getValue().revision());
                    value.put("order", MissionOrderCodec.write(entry.getValue().order()));
                    entries.add(value);
                });
        root.put("assignments", entries);
        return root;
    }

    Map<UUID, MissionOrderManager.Assignment> snapshot() {
        return Map.copyOf(assignments);
    }

    void replace(Map<UUID, MissionOrderManager.Assignment> values) {
        assignments.clear();
        assignments.putAll(values);
        setDirty();
    }
}
