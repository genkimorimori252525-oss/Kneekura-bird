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

/** Persistent world storage for mission-owned waypoint progress. */
public final class MissionRouteSavedData extends SavedData {
    private static final String DATA_NAME = "wwdebug_mission_routes";
    private final Map<UUID, MissionRouteManager.Assignment> assignments = new LinkedHashMap<>();

    public static MissionRouteSavedData get(MinecraftServer server) {
        return server.overworld().getDataStorage().computeIfAbsent(
                MissionRouteSavedData::load, MissionRouteSavedData::new, DATA_NAME);
    }

    public static MissionRouteSavedData load(CompoundTag root) {
        MissionRouteSavedData data = new MissionRouteSavedData();
        Set<UUID> conflictedAircraft = new HashSet<>();
        Tag assignmentsTag = root.get("assignments");
        if (!(assignmentsTag instanceof ListTag entries)
                || (!entries.isEmpty() && entries.getElementType() != Tag.TAG_COMPOUND)) {
            return data;
        }

        for (int index = 0; index < entries.size(); index++) {
            CompoundTag entry = entries.getCompound(index);
            if (!entry.hasUUID("aircraft_id")
                    || !entry.contains("mission_revision", Tag.TAG_LONG)
                    || !entry.hasUUID("order_id")
                    || !entry.contains("route", Tag.TAG_COMPOUND)) {
                continue;
            }
            try {
                UUID aircraftId = entry.getUUID("aircraft_id");
                if (conflictedAircraft.contains(aircraftId)) {
                    continue;
                }
                long revision = entry.getLong("mission_revision");
                if (revision <= 0 || revision >= Long.MAX_VALUE - 1L) {
                    continue;
                }
                MissionRouteManager.Assignment candidate = new MissionRouteManager.Assignment(
                        revision,
                        entry.getUUID("order_id"),
                        WaypointRouteCodec.read(entry.getCompound("route")));
                MissionRouteManager.Assignment existing = data.assignments.get(aircraftId);
                if (existing == null || candidate.missionRevision() > existing.missionRevision()) {
                    data.assignments.put(aircraftId, candidate);
                } else if (candidate.missionRevision() == existing.missionRevision()
                        && !candidate.equals(existing)) {
                    data.assignments.remove(aircraftId);
                    conflictedAircraft.add(aircraftId);
                }
            } catch (IllegalArgumentException ignored) {
                // Isolate only the malformed aircraft route; keep unrelated valid entries.
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
                    value.putLong("mission_revision", entry.getValue().missionRevision());
                    value.putUUID("order_id", entry.getValue().orderId());
                    value.put("route", WaypointRouteCodec.write(entry.getValue().route()));
                    entries.add(value);
                });
        root.put("assignments", entries);
        return root;
    }

    Map<UUID, MissionRouteManager.Assignment> snapshot() {
        return Map.copyOf(assignments);
    }

    void replace(Map<UUID, MissionRouteManager.Assignment> values) {
        assignments.clear();
        assignments.putAll(values);
        setDirty();
    }
}
