package com.wwdebug.autopilot;

import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.ListTag;
import net.minecraft.nbt.StringTag;
import net.minecraft.nbt.Tag;
import net.minecraft.world.phys.Vec3;

import javax.annotation.Nullable;
import java.util.EnumSet;
import java.util.Set;
import java.util.UUID;

/** Stable NBT boundary for immutable mission orders. */
public final class MissionOrderCodec {
    private MissionOrderCodec() {
    }

    public static CompoundTag write(MissionOrder order) {
        CompoundTag tag = new CompoundTag();
        tag.putUUID("order_id", order.orderId());
        tag.putString("type", order.type().name());
        putUuid(tag, "target_entity", order.targetEntity());
        putVec(tag, "target_position", order.targetPosition());
        tag.putDouble("target_radius", order.targetRadius());
        putVec(tag, "home_position", order.homePosition());
        putVec(tag, "runway_direction", order.runwayDirection());
        putUuid(tag, "formation_id", order.formationId());
        putUuid(tag, "leader_aircraft", order.leaderAircraft());
        tag.putInt("remaining_attack_runs", order.remainingAttackRuns());
        tag.putDouble("minimum_return_fuel_fraction", order.minimumReturnFuelFraction());
        tag.putBoolean("weapons_free", order.weaponsFree());
        if (order.missionAltitude() != null) {
            tag.putDouble("mission_altitude", order.missionAltitude());
        }
        putVec(tag, "ingress_direction", order.ingressDirection());

        ListTag aborts = new ListTag();
        order.abortConditions().stream()
                .map(Enum::name)
                .sorted()
                .map(StringTag::valueOf)
                .forEach(aborts::add);
        tag.put("abort_conditions", aborts);
        return tag;
    }

    public static MissionOrder read(CompoundTag tag) {
        MissionOrder.Type type = enumValue(MissionOrder.Type.class, tag.getString("type"), "type");
        MissionOrder.Builder builder = MissionOrder.builder(type)
                .orderId(requiredUuid(tag, "order_id"))
                .minimumReturnFuelFraction(requiredFiniteDouble(tag, "minimum_return_fuel_fraction"))
                .weaponsFree(requiredBoolean(tag, "weapons_free"))
                .attackRuns(requiredInt(tag, "remaining_attack_runs"));

        if (tag.hasUUID("target_entity")) {
            builder.targetEntity(tag.getUUID("target_entity"));
        }
        Vec3 targetPosition = readVec(tag, "target_position");
        double targetRadius = requiredFiniteDouble(tag, "target_radius");
        if (targetPosition != null) {
            builder.targetPosition(targetPosition, targetRadius);
        }
        Vec3 home = readVec(tag, "home_position");
        Vec3 runway = readVec(tag, "runway_direction");
        if (home != null || runway != null) {
            if (home == null || runway == null) {
                throw new IllegalArgumentException("home_position and runway_direction must be stored together");
            }
            builder.home(home, runway);
        }
        if (tag.hasUUID("formation_id") || tag.hasUUID("leader_aircraft")) {
            if (!tag.hasUUID("formation_id") || !tag.hasUUID("leader_aircraft")) {
                throw new IllegalArgumentException("formation_id and leader_aircraft must be stored together");
            }
            builder.formation(tag.getUUID("formation_id"), tag.getUUID("leader_aircraft"));
        }
        if (tag.contains("mission_altitude")) {
            builder.missionAltitude(requiredFiniteDouble(tag, "mission_altitude"));
        }
        Vec3 ingress = readVec(tag, "ingress_direction");
        if (ingress != null) {
            builder.ingressDirection(ingress);
        }

        Tag abortTag = tag.get("abort_conditions");
        if (!(abortTag instanceof ListTag aborts) || aborts.getElementType() != Tag.TAG_STRING) {
            throw new IllegalArgumentException("Invalid string-list field: abort_conditions");
        }
        Set<MissionOrder.AbortCondition> conditions = EnumSet.noneOf(MissionOrder.AbortCondition.class);
        for (int index = 0; index < aborts.size(); index++) {
            conditions.add(enumValue(MissionOrder.AbortCondition.class, aborts.getString(index),
                    "abort_conditions[" + index + "]"));
        }
        builder.abortOn(conditions.toArray(MissionOrder.AbortCondition[]::new));
        return builder.build();
    }

    private static void putUuid(CompoundTag tag, String key, @Nullable UUID value) {
        if (value != null) {
            tag.putUUID(key, value);
        }
    }

    private static UUID requiredUuid(CompoundTag tag, String key) {
        if (!tag.hasUUID(key)) {
            throw new IllegalArgumentException("Missing UUID field: " + key);
        }
        return tag.getUUID(key);
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

    private static int requiredInt(CompoundTag tag, String key) {
        if (!tag.contains(key, Tag.TAG_ANY_NUMERIC)) {
            throw new IllegalArgumentException("Missing numeric field: " + key);
        }
        return tag.getInt(key);
    }

    private static boolean requiredBoolean(CompoundTag tag, String key) {
        if (!tag.contains(key, Tag.TAG_BYTE)) {
            throw new IllegalArgumentException("Missing boolean field: " + key);
        }
        return tag.getBoolean(key);
    }

    private static void putVec(CompoundTag root, String key, @Nullable Vec3 value) {
        if (value == null) {
            return;
        }
        CompoundTag vector = new CompoundTag();
        vector.putDouble("x", value.x);
        vector.putDouble("y", value.y);
        vector.putDouble("z", value.z);
        root.put(key, vector);
    }

    @Nullable
    private static Vec3 readVec(CompoundTag root, String key) {
        if (!root.contains(key)) {
            return null;
        }
        if (!root.contains(key, Tag.TAG_COMPOUND)) {
            throw new IllegalArgumentException("Invalid vector field: " + key);
        }
        CompoundTag vector = root.getCompound(key);
        double x = requiredFiniteComponent(vector, key, "x");
        double y = requiredFiniteComponent(vector, key, "y");
        double z = requiredFiniteComponent(vector, key, "z");
        return new Vec3(x, y, z);
    }

    private static double requiredFiniteComponent(CompoundTag vector, String field, String component) {
        if (!vector.contains(component, Tag.TAG_ANY_NUMERIC)) {
            throw new IllegalArgumentException("Missing numeric vector component: " + field + "." + component);
        }
        double value = vector.getDouble(component);
        if (!Double.isFinite(value)) {
            throw new IllegalArgumentException("Non-finite vector component: " + field + "." + component);
        }
        return value;
    }

    private static <E extends Enum<E>> E enumValue(Class<E> type, String value, String field) {
        try {
            return Enum.valueOf(type, value);
        } catch (IllegalArgumentException exception) {
            throw new IllegalArgumentException("Invalid " + field + ": " + value, exception);
        }
    }
}
