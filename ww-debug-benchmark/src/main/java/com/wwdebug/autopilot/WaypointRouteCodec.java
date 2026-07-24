package com.wwdebug.autopilot;

import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.ListTag;
import net.minecraft.nbt.Tag;
import net.minecraft.world.phys.Vec3;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

/** Stable, strict NBT boundary for immutable waypoint routes. */
public final class WaypointRouteCodec {
    private WaypointRouteCodec() {
    }

    public static CompoundTag write(WaypointRoute route) {
        CompoundTag root = new CompoundTag();
        root.putUUID("route_id", route.routeId());
        root.putInt("next_index", route.nextIndex());

        ListTag entries = new ListTag();
        for (WaypointRoute.Waypoint waypoint : route.waypoints()) {
            CompoundTag entry = new CompoundTag();
            CompoundTag position = new CompoundTag();
            position.putDouble("x", waypoint.position().x);
            position.putDouble("y", waypoint.position().y);
            position.putDouble("z", waypoint.position().z);
            entry.put("position", position);
            entry.putDouble("arrival_radius", waypoint.arrivalRadius());
            entries.add(entry);
        }
        root.put("waypoints", entries);
        return root;
    }

    public static WaypointRoute read(CompoundTag root) {
        UUID routeId = requiredUuid(root, "route_id");
        int nextIndex = requiredInt(root, "next_index");

        Tag waypointTag = root.get("waypoints");
        if (!(waypointTag instanceof ListTag entries)
                || (!entries.isEmpty() && entries.getElementType() != Tag.TAG_COMPOUND)) {
            throw new IllegalArgumentException("Invalid compound-list field: waypoints");
        }

        List<WaypointRoute.Waypoint> waypoints = new ArrayList<>(entries.size());
        for (int index = 0; index < entries.size(); index++) {
            CompoundTag entry = entries.getCompound(index);
            Vec3 position = requiredVec(entry, "position");
            double arrivalRadius = requiredFiniteDouble(entry, "arrival_radius");
            waypoints.add(new WaypointRoute.Waypoint(position, arrivalRadius));
        }
        return new WaypointRoute(routeId, waypoints, nextIndex);
    }

    private static UUID requiredUuid(CompoundTag tag, String key) {
        if (!tag.hasUUID(key)) {
            throw new IllegalArgumentException("Missing UUID field: " + key);
        }
        return tag.getUUID(key);
    }

    private static int requiredInt(CompoundTag tag, String key) {
        if (!tag.contains(key, Tag.TAG_INT)) {
            throw new IllegalArgumentException("Missing integer field: " + key);
        }
        return tag.getInt(key);
    }

    private static Vec3 requiredVec(CompoundTag tag, String key) {
        if (!tag.contains(key, Tag.TAG_COMPOUND)) {
            throw new IllegalArgumentException("Missing compound vector field: " + key);
        }
        CompoundTag vector = tag.getCompound(key);
        return new Vec3(
                requiredFiniteDouble(vector, "x"),
                requiredFiniteDouble(vector, "y"),
                requiredFiniteDouble(vector, "z"));
    }

    private static double requiredFiniteDouble(CompoundTag tag, String key) {
        if (!tag.contains(key, Tag.TAG_ANY_NUMERIC)) {
            throw new IllegalArgumentException("Missing numeric field: " + key);
        }
        double value = tag.getDouble(key);
        if (!Double.isFinite(value)) {
            throw new IllegalArgumentException("Non-finite numeric field: " + key);
        }
        return value;
    }
}
