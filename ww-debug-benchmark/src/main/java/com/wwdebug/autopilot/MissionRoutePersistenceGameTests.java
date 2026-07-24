package com.wwdebug.autopilot;

import com.wwdebug.benchmark.WWDebugBenchmarkMod;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.ListTag;
import net.minecraft.nbt.Tag;
import net.minecraft.world.phys.Vec3;
import net.minecraftforge.gametest.GameTestHolder;
import net.minecraftforge.gametest.PrefixGameTestTemplate;

import java.util.List;
import java.util.Map;
import java.util.UUID;

/** Deterministic contracts for persisted mission-owned route progress. */
@GameTestHolder(WWDebugBenchmarkMod.MOD_ID)
@PrefixGameTestTemplate(false)
public final class MissionRoutePersistenceGameTests {
    private MissionRoutePersistenceGameTests() {
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "mission_route_persistence_contract")
    public static void routeProgressRoundTripsAndMatchesLoadedMission(GameTestHelper helper) {
        UUID aircraft = UUID.fromString("00000000-0000-0000-0000-000000000b01");
        UUID orderId = UUID.fromString("00000000-0000-0000-0000-000000000b02");
        MissionOrder mission = MissionOrder.builder(MissionOrder.Type.HOLD_POSITION)
                .orderId(orderId)
                .targetPosition(new Vec3(80.0, 100.0, -20.0), 16.0)
                .build();
        MissionOrderManager.Assignment missionAssignment =
                new MissionOrderManager.Assignment(42L, mission);
        WaypointRoute route = new WaypointRoute(
                UUID.fromString("00000000-0000-0000-0000-000000000b03"),
                List.of(
                        new WaypointRoute.Waypoint(new Vec3(20.0, 90.0, 0.0), 8.0),
                        new WaypointRoute.Waypoint(new Vec3(80.0, 100.0, -20.0), 12.0)),
                1);
        MissionRouteManager.Assignment routeAssignment =
                new MissionRouteManager.Assignment(42L, orderId, route);

        MissionRouteSavedData initial = new MissionRouteSavedData();
        initial.replace(Map.of(aircraft, routeAssignment));
        MissionRouteSavedData restoredData = MissionRouteSavedData.load(initial.save(new CompoundTag()));
        check(routeAssignment.equals(restoredData.snapshot().get(aircraft)),
                "mission-owned route progress must round-trip exactly");

        Map<UUID, MissionRouteManager.Assignment> matched = MissionRouteManager.matchingAssignments(
                restoredData.snapshot(), Map.of(aircraft, missionAssignment));
        check(routeAssignment.equals(matched.get(aircraft)),
                "a route must restore when revision and order ID match the loaded mission");

        MissionOrderManager.Assignment newerMission =
                new MissionOrderManager.Assignment(43L, mission);
        check(MissionRouteManager.matchingAssignments(
                        restoredData.snapshot(), Map.of(aircraft, newerMission)).isEmpty(),
                "route progress from an older mission revision must not restore");

        MissionOrder replacementOrder = MissionOrder.builder(MissionOrder.Type.HOLD_POSITION)
                .orderId(UUID.fromString("00000000-0000-0000-0000-000000000b04"))
                .targetPosition(new Vec3(80.0, 100.0, -20.0), 16.0)
                .build();
        check(MissionRouteManager.matchingAssignments(
                        restoredData.snapshot(),
                        Map.of(aircraft, new MissionOrderManager.Assignment(42L, replacementOrder)))
                        .isEmpty(),
                "an equal-revision route for another order must not restore");

        MissionRouteManager.restore(matched);
        check(routeAssignment.equals(MissionRouteManager.current(aircraft).orElseThrow()),
                "matched persisted routes must be restorable into the manager");
        MissionRouteManager.clearAll();
        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "mission_route_persistence_contract")
    public static void malformedAndConflictingRoutesAreIsolated(GameTestHelper helper) {
        UUID validAircraft = UUID.fromString("00000000-0000-0000-0000-000000000b11");
        UUID duplicateAircraft = UUID.fromString("00000000-0000-0000-0000-000000000b12");
        UUID conflictAircraft = UUID.fromString("00000000-0000-0000-0000-000000000b13");
        UUID malformedAircraft = UUID.fromString("00000000-0000-0000-0000-000000000b14");
        UUID wrongRevisionAircraft = UUID.fromString("00000000-0000-0000-0000-000000000b15");
        UUID overflowAircraft = UUID.fromString("00000000-0000-0000-0000-000000000b16");
        UUID orderId = UUID.fromString("00000000-0000-0000-0000-000000000b17");

        WaypointRoute older = WaypointRoute.start(
                UUID.fromString("00000000-0000-0000-0000-000000000b18"),
                List.of(new WaypointRoute.Waypoint(new Vec3(10.0, 80.0, 0.0), 8.0)));
        WaypointRoute newer = new WaypointRoute(
                UUID.fromString("00000000-0000-0000-0000-000000000b19"),
                List.of(
                        new WaypointRoute.Waypoint(new Vec3(20.0, 90.0, 0.0), 8.0),
                        new WaypointRoute.Waypoint(new Vec3(40.0, 100.0, 0.0), 8.0)),
                1);
        MissionRouteManager.Assignment valid =
                new MissionRouteManager.Assignment(30L, orderId, older);

        MissionRouteSavedData initial = new MissionRouteSavedData();
        initial.replace(Map.of(validAircraft, valid));
        CompoundTag serialized = initial.save(new CompoundTag());
        ListTag entries = serialized.getList("assignments", Tag.TAG_COMPOUND);

        entries.add(assignmentEntry(duplicateAircraft, 12L, orderId, newer));
        entries.add(assignmentEntry(duplicateAircraft, 11L, orderId, older));
        entries.add(assignmentEntry(conflictAircraft, 20L, orderId, older));
        entries.add(assignmentEntry(conflictAircraft, 20L, orderId, newer));

        CompoundTag malformed = assignmentEntry(malformedAircraft, 21L, orderId, older);
        malformed.getCompound("route").getList("waypoints", Tag.TAG_COMPOUND)
                .getCompound(0).getCompound("position").remove("z");
        entries.add(malformed);

        CompoundTag wrongRevision = assignmentEntry(wrongRevisionAircraft, 22L, orderId, older);
        wrongRevision.putInt("mission_revision", 22);
        entries.add(wrongRevision);
        entries.add(assignmentEntry(overflowAircraft, Long.MAX_VALUE - 1L, orderId, older));

        MissionRouteSavedData restored = MissionRouteSavedData.load(serialized);
        check(valid.equals(restored.snapshot().get(validAircraft)),
                "an unrelated valid route must survive malformed neighbors");
        MissionRouteManager.Assignment duplicate = restored.snapshot().get(duplicateAircraft);
        check(duplicate != null && duplicate.missionRevision() == 12L
                        && duplicate.route().equals(newer),
                "the greatest valid duplicate mission revision must win");
        check(!restored.snapshot().containsKey(conflictAircraft),
                "equal-revision conflicting routes must isolate that aircraft");
        check(!restored.snapshot().containsKey(malformedAircraft),
                "a malformed route must be isolated");
        check(!restored.snapshot().containsKey(wrongRevisionAircraft),
                "a non-long mission revision must be rejected");
        check(!restored.snapshot().containsKey(overflowAircraft),
                "a non-incrementable mission revision must be rejected");

        helper.succeed();
    }

    private static CompoundTag assignmentEntry(UUID aircraftId, long revision,
                                                UUID orderId, WaypointRoute route) {
        CompoundTag entry = new CompoundTag();
        entry.putUUID("aircraft_id", aircraftId);
        entry.putLong("mission_revision", revision);
        entry.putUUID("order_id", orderId);
        entry.put("route", WaypointRouteCodec.write(route));
        return entry;
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }
}
