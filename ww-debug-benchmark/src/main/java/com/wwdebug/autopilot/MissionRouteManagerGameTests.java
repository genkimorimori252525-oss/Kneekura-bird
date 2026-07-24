package com.wwdebug.autopilot;

import com.wwdebug.benchmark.WWDebugBenchmarkMod;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.world.phys.Vec3;
import net.minecraftforge.gametest.GameTestHolder;
import net.minecraftforge.gametest.PrefixGameTestTemplate;

import java.util.List;
import java.util.Map;
import java.util.UUID;

/** Deterministic contract checks for mission-guarded route ownership and progress. */
@GameTestHolder(WWDebugBenchmarkMod.MOD_ID)
@PrefixGameTestTemplate(false)
public final class MissionRouteManagerGameTests {
    private MissionRouteManagerGameTests() {
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "mission_route_manager_contract")
    public static void missionRouteOwnershipPreventsStaleRewind(GameTestHelper helper) {
        MissionOrderManager.clearAll();
        MissionRouteManager.clearAll();
        UUID aircraft = UUID.fromString("00000000-0000-0000-0000-000000000901");
        UUID firstOrder = UUID.fromString("00000000-0000-0000-0000-000000000902");
        UUID secondOrder = UUID.fromString("00000000-0000-0000-0000-000000000903");
        UUID firstRouteId = UUID.fromString("00000000-0000-0000-0000-000000000904");
        UUID secondRouteId = UUID.fromString("00000000-0000-0000-0000-000000000905");

        MissionOrderManager.Assignment firstMission = new MissionOrderManager.Assignment(
                10L,
                MissionOrder.builder(MissionOrder.Type.HOLD_POSITION)
                        .orderId(firstOrder)
                        .targetPosition(new Vec3(40.0, 90.0, 0.0), 12.0)
                        .build());
        MissionOrderManager.restore(Map.of(aircraft, firstMission));

        WaypointRoute firstRoute = WaypointRoute.start(firstRouteId, List.of(
                new WaypointRoute.Waypoint(new Vec3(10.0, 80.0, 10.0), 4.0),
                new WaypointRoute.Waypoint(new Vec3(12.0, 80.0, 10.0), 4.0),
                new WaypointRoute.Waypoint(new Vec3(40.0, 90.0, 0.0), 3.0)));
        MissionRouteManager.Assignment initial = MissionRouteManager
                .bind(aircraft, firstMission, firstRoute).orElseThrow();
        check(initial.route().nextIndex() == 0, "a new mission route must start at index zero");

        MissionRouteManager.Assignment outside = MissionRouteManager
                .advance(aircraft, 10L, firstOrder, new Vec3(0.0, 80.0, 0.0)).orElseThrow();
        check(outside == initial, "an unreached waypoint must preserve the assignment instance");

        MissionRouteManager.Assignment progressed = MissionRouteManager
                .advance(aircraft, 10L, firstOrder, new Vec3(11.0, 80.0, 10.0)).orElseThrow();
        check(progressed.route().nextIndex() == 1,
                "one matching call must advance at most one overlapping waypoint");

        MissionRouteManager.Assignment idempotentRebind = MissionRouteManager
                .bind(aircraft, firstMission, firstRoute).orElseThrow();
        check(idempotentRebind.route().nextIndex() == 1,
                "rebinding the same mission and route must not rewind progress");

        MissionRouteManager.Assignment secondProgress = MissionRouteManager
                .advance(aircraft, 10L, firstOrder, new Vec3(11.0, 80.0, 10.0)).orElseThrow();
        check(secondProgress.route().nextIndex() == 2,
                "a second explicit call may advance the second overlapping waypoint");

        WaypointRoute staleRoute = WaypointRoute.start(secondRouteId, List.of(
                new WaypointRoute.Waypoint(Vec3.ZERO, 8.0)));
        check(MissionRouteManager.bindOwned(aircraft, 9L, secondOrder, staleRoute).isEmpty(),
                "an older mission revision must not replace current route progress");
        check(MissionRouteManager.bindOwned(aircraft, 10L, secondOrder, staleRoute).isEmpty(),
                "an equal-revision order conflict must be rejected");
        check(MissionRouteManager.current(aircraft).orElseThrow().route().nextIndex() == 2,
                "rejected binds must leave current route progress unchanged");

        MissionOrderManager.Assignment secondMission = new MissionOrderManager.Assignment(
                11L,
                MissionOrder.builder(MissionOrder.Type.HOLD_POSITION)
                        .orderId(secondOrder)
                        .targetPosition(Vec3.ZERO, 8.0)
                        .build());
        MissionOrderManager.restore(Map.of(aircraft, secondMission));
        MissionRouteManager.Assignment replacement = MissionRouteManager
                .bind(aircraft, secondMission, staleRoute).orElseThrow();
        check(replacement.missionRevision() == 11L && replacement.route().nextIndex() == 0,
                "a newer current mission must replace the prior route");
        check(MissionRouteManager.advance(aircraft, 10L, firstOrder, Vec3.ZERO).isEmpty(),
                "a stale mission must not advance the replacement route");
        check(MissionRouteManager.current(aircraft).orElseThrow().equals(replacement),
                "stale advancement must not mutate the replacement route");

        check(!MissionRouteManager.clear(aircraft, 10L, firstOrder),
                "a stale mission must not clear the current route");
        check(MissionRouteManager.clear(aircraft, 11L, secondOrder),
                "the current mission owner must be able to clear its route");
        check(MissionRouteManager.current(aircraft).isEmpty(),
                "a cleared route must no longer be visible");

        MissionRouteManager.clearAll();
        MissionOrderManager.clearAll();
        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "mission_route_manager_contract")
    public static void missionRouteManagerRequiresCurrentMissionAndCopiesSnapshot(GameTestHelper helper) {
        MissionOrderManager.clearAll();
        MissionRouteManager.clearAll();
        UUID aircraft = UUID.fromString("00000000-0000-0000-0000-000000000911");
        UUID orderId = UUID.fromString("00000000-0000-0000-0000-000000000912");
        MissionOrder order = MissionOrder.builder(MissionOrder.Type.HOLD_POSITION)
                .orderId(orderId)
                .targetPosition(Vec3.ZERO, 8.0)
                .build();
        MissionOrderManager.Assignment mission = new MissionOrderManager.Assignment(1L, order);
        WaypointRoute route = WaypointRoute.start(
                UUID.fromString("00000000-0000-0000-0000-000000000913"),
                List.of(new WaypointRoute.Waypoint(Vec3.ZERO, 8.0)));

        expectInvalid(() -> MissionRouteManager.bindOwned(aircraft, 0L, orderId, route),
                "a non-positive mission revision must be rejected");
        check(MissionRouteManager.bind(aircraft, mission, route).isEmpty(),
                "a route must not bind before its mission becomes current");
        MissionOrderManager.restore(Map.of(aircraft, mission));
        MissionRouteManager.bind(aircraft, mission, route).orElseThrow();
        MissionOrderManager.Assignment forgedNewer = new MissionOrderManager.Assignment(2L, order);
        check(MissionRouteManager.bind(aircraft, forgedNewer, route).isEmpty(),
                "a supplied assignment that is not current must be rejected");

        Map<UUID, MissionRouteManager.Assignment> snapshot = MissionRouteManager.snapshot();
        MissionRouteManager.clearAll();
        check(snapshot.containsKey(aircraft),
                "a snapshot must remain stable after the manager is cleared");
        expectUnsupported(() -> snapshot.clear(),
                "the exposed snapshot must be immutable");

        MissionOrderManager.clearAll();
        helper.succeed();
    }

    private static void expectInvalid(Runnable action, String message) {
        try {
            action.run();
            throw new IllegalStateException(message);
        } catch (IllegalArgumentException expected) {
            // Expected contract rejection.
        }
    }

    private static void expectUnsupported(Runnable action, String message) {
        try {
            action.run();
            throw new IllegalStateException(message);
        } catch (UnsupportedOperationException expected) {
            // Expected immutable view.
        }
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }
}
