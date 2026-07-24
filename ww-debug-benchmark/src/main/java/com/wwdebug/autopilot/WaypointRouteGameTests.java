package com.wwdebug.autopilot;

import com.wwdebug.benchmark.WWDebugBenchmarkMod;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.world.phys.Vec3;
import net.minecraftforge.gametest.GameTestHolder;
import net.minecraftforge.gametest.PrefixGameTestTemplate;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

/** Deterministic contract checks for immutable waypoint progression. */
@GameTestHolder(WWDebugBenchmarkMod.MOD_ID)
@PrefixGameTestTemplate(false)
public final class WaypointRouteGameTests {
    private WaypointRouteGameTests() {
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "waypoint_route_contract")
    public static void waypointRouteProgressesInOrder(GameTestHelper helper) {
        UUID routeId = UUID.fromString("00000000-0000-0000-0000-000000000801");
        List<WaypointRoute.Waypoint> source = new ArrayList<>(List.of(
                new WaypointRoute.Waypoint(new Vec3(10.0, 80.0, 10.0), 4.0),
                new WaypointRoute.Waypoint(new Vec3(12.0, 80.0, 10.0), 4.0),
                new WaypointRoute.Waypoint(new Vec3(30.0, 90.0, -5.0), 2.0)));
        WaypointRoute route = WaypointRoute.start(routeId, source);
        source.clear();

        check(route.waypoints().size() == 3, "the route must defensively copy its waypoint list");
        check(route.nextIndex() == 0 && route.remainingWaypoints() == 3,
                "a new route must start at the first waypoint");
        check(route.currentWaypoint().orElseThrow().position().equals(new Vec3(10.0, 80.0, 10.0)),
                "the first waypoint must be current");

        WaypointRoute outside = route.advanceIfReached(new Vec3(5.0, 80.0, 10.0));
        check(outside == route, "an unreached waypoint must not create a new route state");

        WaypointRoute firstReached = route.advanceIfReached(new Vec3(11.0, 80.0, 10.0));
        check(firstReached.nextIndex() == 1 && firstReached.remainingWaypoints() == 2,
                "reaching the first waypoint must advance exactly once");
        check(firstReached.currentWaypoint().orElseThrow().position().equals(new Vec3(12.0, 80.0, 10.0)),
                "overlapping arrival regions must not skip the second waypoint");

        WaypointRoute secondReached = firstReached.advanceIfReached(new Vec3(11.0, 80.0, 10.0));
        check(secondReached.nextIndex() == 2,
                "a second explicit progression call may advance the overlapping waypoint");
        WaypointRoute completed = secondReached.advanceIfReached(new Vec3(30.0, 90.0, -5.0));
        check(completed.completed() && completed.remainingWaypoints() == 0,
                "reaching the final waypoint must complete the route");
        check(completed.currentWaypoint().isEmpty(),
                "a completed route must not expose a current waypoint");
        check(completed.advanceIfReached(Vec3.ZERO) == completed,
                "a completed route must remain stable");

        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "waypoint_route_contract")
    public static void waypointRouteRejectsInvalidData(GameTestHelper helper) {
        UUID routeId = UUID.fromString("00000000-0000-0000-0000-000000000802");
        WaypointRoute.Waypoint valid = new WaypointRoute.Waypoint(Vec3.ZERO, 8.0);

        expectInvalid(() -> WaypointRoute.start(routeId, List.of()),
                "an empty route must be rejected");
        expectInvalid(() -> new WaypointRoute(routeId, List.of(valid), -1),
                "a negative route index must be rejected");
        expectInvalid(() -> new WaypointRoute(routeId, List.of(valid), 2),
                "an index beyond route completion must be rejected");
        expectInvalid(() -> new WaypointRoute.Waypoint(new Vec3(Double.NaN, 0.0, 0.0), 8.0),
                "non-finite waypoint coordinates must be rejected");
        expectInvalid(() -> new WaypointRoute.Waypoint(Vec3.ZERO, 0.0),
                "a non-positive arrival radius must be rejected");
        expectInvalid(() -> new WaypointRoute.Waypoint(Vec3.ZERO,
                        WaypointRoute.MAX_ARRIVAL_RADIUS_BLOCKS + 1.0),
                "an unbounded arrival radius must be rejected");
        WaypointRoute route = WaypointRoute.start(routeId, List.of(valid));
        expectInvalid(() -> route.advanceIfReached(new Vec3(0.0, Double.POSITIVE_INFINITY, 0.0)),
                "non-finite observed positions must be rejected");

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

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }
}
