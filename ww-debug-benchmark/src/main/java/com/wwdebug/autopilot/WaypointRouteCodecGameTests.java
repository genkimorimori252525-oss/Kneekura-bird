package com.wwdebug.autopilot;

import com.wwdebug.benchmark.WWDebugBenchmarkMod;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.ListTag;
import net.minecraft.nbt.StringTag;
import net.minecraft.nbt.Tag;
import net.minecraft.world.phys.Vec3;
import net.minecraftforge.gametest.GameTestHolder;
import net.minecraftforge.gametest.PrefixGameTestTemplate;

import java.util.List;
import java.util.UUID;

/** Deterministic contract checks for strict waypoint-route NBT serialization. */
@GameTestHolder(WWDebugBenchmarkMod.MOD_ID)
@PrefixGameTestTemplate(false)
public final class WaypointRouteCodecGameTests {
    private WaypointRouteCodecGameTests() {
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "waypoint_route_codec_contract")
    public static void waypointRouteCodecRoundTripsProgress(GameTestHelper helper) {
        UUID routeId = UUID.fromString("00000000-0000-0000-0000-000000000a01");
        List<WaypointRoute.Waypoint> waypoints = List.of(
                new WaypointRoute.Waypoint(new Vec3(-20.5, 96.0, 40.25), 12.0),
                new WaypointRoute.Waypoint(new Vec3(80.0, 110.5, -32.0), 6.5));
        WaypointRoute partial = new WaypointRoute(routeId, waypoints, 1);

        CompoundTag serialized = WaypointRouteCodec.write(partial);
        check(serialized.hasUUID("route_id"), "the writer must store a UUID route ID");
        check(serialized.contains("next_index", Tag.TAG_INT),
                "the writer must store next_index as an exact integer tag");
        check(serialized.contains("waypoints", Tag.TAG_LIST),
                "the writer must store the waypoint list");

        WaypointRoute restored = WaypointRouteCodec.read(serialized);
        check(restored.equals(partial), "a partially progressed route must round-trip exactly");
        serialized.getList("waypoints", Tag.TAG_COMPOUND)
                .getCompound(0).getCompound("position").putDouble("x", 999.0);
        check(restored.waypoints().get(0).position().x == -20.5,
                "decoded route state must not alias mutable NBT input");

        WaypointRoute completed = new WaypointRoute(routeId, waypoints, waypoints.size());
        check(WaypointRouteCodec.read(WaypointRouteCodec.write(completed)).equals(completed),
                "a completed route must retain its terminal index");

        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "waypoint_route_codec_contract")
    public static void waypointRouteCodecRejectsMalformedTags(GameTestHelper helper) {
        WaypointRoute valid = WaypointRoute.start(
                UUID.fromString("00000000-0000-0000-0000-000000000a02"),
                List.of(new WaypointRoute.Waypoint(new Vec3(10.0, 80.0, -4.0), 8.0)));
        CompoundTag serialized = WaypointRouteCodec.write(valid);

        CompoundTag missingId = serialized.copy();
        missingId.remove("route_id");
        expectInvalid(() -> WaypointRouteCodec.read(missingId),
                "a missing route UUID must be rejected");

        CompoundTag wrongIndexType = serialized.copy();
        wrongIndexType.putLong("next_index", 0L);
        expectInvalid(() -> WaypointRouteCodec.read(wrongIndexType),
                "next_index must not silently narrow from another numeric tag type");

        CompoundTag wrongListType = serialized.copy();
        wrongListType.putString("waypoints", "not-a-list");
        expectInvalid(() -> WaypointRouteCodec.read(wrongListType),
                "a non-list waypoint field must be rejected");

        CompoundTag wrongElementType = serialized.copy();
        ListTag strings = new ListTag();
        strings.add(StringTag.valueOf("not-a-waypoint"));
        wrongElementType.put("waypoints", strings);
        expectInvalid(() -> WaypointRouteCodec.read(wrongElementType),
                "a waypoint list with non-compound elements must be rejected");

        CompoundTag missingComponent = serialized.copy();
        missingComponent.getList("waypoints", Tag.TAG_COMPOUND)
                .getCompound(0).getCompound("position").remove("z");
        expectInvalid(() -> WaypointRouteCodec.read(missingComponent),
                "a missing vector component must be rejected");

        CompoundTag wrongRadiusType = serialized.copy();
        wrongRadiusType.getList("waypoints", Tag.TAG_COMPOUND)
                .getCompound(0).putString("arrival_radius", "large");
        expectInvalid(() -> WaypointRouteCodec.read(wrongRadiusType),
                "a non-numeric arrival radius must be rejected");

        CompoundTag nonFinite = serialized.copy();
        nonFinite.getList("waypoints", Tag.TAG_COMPOUND)
                .getCompound(0).getCompound("position").putDouble("y", Double.NaN);
        expectInvalid(() -> WaypointRouteCodec.read(nonFinite),
                "a non-finite coordinate must be rejected");

        CompoundTag empty = serialized.copy();
        empty.put("waypoints", new ListTag());
        expectInvalid(() -> WaypointRouteCodec.read(empty),
                "an empty persisted route must remain invalid");

        CompoundTag outOfBounds = serialized.copy();
        outOfBounds.putInt("next_index", 2);
        expectInvalid(() -> WaypointRouteCodec.read(outOfBounds),
                "an out-of-bounds progress index must be rejected");

        helper.succeed();
    }

    private static void expectInvalid(Runnable action, String message) {
        try {
            action.run();
            throw new IllegalStateException(message);
        } catch (IllegalArgumentException expected) {
            // Expected strict boundary rejection.
        }
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }
}
