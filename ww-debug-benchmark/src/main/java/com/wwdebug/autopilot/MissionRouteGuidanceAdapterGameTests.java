package com.wwdebug.autopilot;

import com.wwdebug.benchmark.WWDebugBenchmarkMod;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.phys.Vec3;
import net.minecraftforge.gametest.GameTestHolder;
import net.minecraftforge.gametest.PrefixGameTestTemplate;

import java.util.List;
import java.util.UUID;

/** Deterministic ownership and phase contracts for mission-route guidance proposals. */
@GameTestHolder(WWDebugBenchmarkMod.MOD_ID)
@PrefixGameTestTemplate(false)
public final class MissionRouteGuidanceAdapterGameTests {
    private MissionRouteGuidanceAdapterGameTests() {
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "mission_route_guidance_contract")
    public static void ownedRouteAdvancesOnceAndTargetsTheNextWaypoint(GameTestHelper helper) {
        clearManagers();
        try {
            UUID aircraftId = UUID.fromString("00000000-0000-0000-0000-000000000d01");
            MissionOrderManager.Assignment mission = MissionOrderManager.assign(
                    aircraftId,
                    MissionOrder.builder(MissionOrder.Type.HOLD_POSITION)
                            .orderId(UUID.fromString("00000000-0000-0000-0000-000000000d11"))
                            .build());
            WaypointRoute route = WaypointRoute.start(
                    UUID.fromString("00000000-0000-0000-0000-000000000d21"),
                    List.of(
                            new WaypointRoute.Waypoint(new Vec3(10.0, 90.0, 0.0), 2.0),
                            new WaypointRoute.Waypoint(new Vec3(40.0, 100.0, 0.0), 3.0)));
            check(MissionRouteManager.bind(aircraftId, mission, route).isPresent(),
                    "current mission must accept its owned route");

            FlightSnapshot snapshot = snapshot(new Vec3(10.0, 90.0, 0.0), 28.0, 90.0);
            FlightControlOutput base = baseOutput(snapshot);
            MissionRouteGuidanceAdapter.Decision decision = MissionRouteGuidanceAdapter.plan(
                    aircraftId,
                    FlightPhase.CRUISE_OUTBOUND,
                    snapshot,
                    profile(),
                    base);

            check(decision.routeActive() && decision.waypointAdvanced() && !decision.routeCompleted(),
                    "eligible cruise guidance must advance exactly one reached waypoint");
            check(MissionRouteManager.current(aircraftId).orElseThrow().route().nextIndex() == 1,
                    "persisted route progress must match the planner decision");
            check(decision.output().targetAltitude() == 100.0
                            && decision.output().desiredDirection().distanceTo(new Vec3(1.0, 0.0, 0.0)) < 1.0e-9,
                    "the next waypoint must become the live base-autonomy proposal");
            check("owned_route_waypoint_advanced".equals(decision.description()),
                    "waypoint progression must remain observable");
            helper.succeed();
        } finally {
            clearManagers();
        }
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "mission_route_guidance_contract")
    public static void safetyCriticalPhasesCannotConsumeRouteProgress(GameTestHelper helper) {
        clearManagers();
        try {
            UUID aircraftId = UUID.fromString("00000000-0000-0000-0000-000000000d02");
            MissionOrderManager.Assignment mission = MissionOrderManager.assign(
                    aircraftId,
                    MissionOrder.builder(MissionOrder.Type.RETURN_TO_BASE)
                            .orderId(UUID.fromString("00000000-0000-0000-0000-000000000d12"))
                            .home(new Vec3(0.0, 64.0, 0.0), new Vec3(0.0, 0.0, 1.0))
                            .build());
            WaypointRoute route = WaypointRoute.start(
                    UUID.fromString("00000000-0000-0000-0000-000000000d22"),
                    List.of(new WaypointRoute.Waypoint(new Vec3(10.0, 90.0, 0.0), 2.0)));
            MissionRouteManager.bind(aircraftId, mission, route).orElseThrow();

            FlightSnapshot snapshot = snapshot(new Vec3(10.0, 90.0, 0.0), 28.0, 90.0);
            FlightControlOutput base = baseOutput(snapshot);
            for (FlightPhase phase : List.of(
                    FlightPhase.TAKEOFF_ROLL,
                    FlightPhase.STALL_RECOVERY,
                    FlightPhase.RETURN_TO_PATTERN,
                    FlightPhase.FINAL,
                    FlightPhase.GO_AROUND)) {
                MissionRouteGuidanceAdapter.Decision decision = MissionRouteGuidanceAdapter.plan(
                        aircraftId, phase, snapshot, profile(), base);
                check(!decision.routeActive() && decision.output() == base,
                        phase + " must preserve the established base/safety output");
                check(MissionRouteManager.current(aircraftId).orElseThrow().route().nextIndex() == 0,
                        phase + " must not consume route progress");
            }
            helper.succeed();
        } finally {
            clearManagers();
        }
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "mission_route_guidance_contract")
    public static void completingRouteReleasesControlBackToBaseAutonomy(GameTestHelper helper) {
        clearManagers();
        try {
            UUID aircraftId = UUID.fromString("00000000-0000-0000-0000-000000000d03");
            MissionOrderManager.Assignment mission = MissionOrderManager.assign(
                    aircraftId,
                    MissionOrder.builder(MissionOrder.Type.HOLD_POSITION)
                            .orderId(UUID.fromString("00000000-0000-0000-0000-000000000d13"))
                            .build());
            WaypointRoute route = WaypointRoute.start(
                    UUID.fromString("00000000-0000-0000-0000-000000000d23"),
                    List.of(new WaypointRoute.Waypoint(new Vec3(10.0, 90.0, 0.0), 2.0)));
            MissionRouteManager.bind(aircraftId, mission, route).orElseThrow();

            FlightSnapshot snapshot = snapshot(new Vec3(10.0, 90.0, 0.0), 28.0, 90.0);
            FlightControlOutput base = baseOutput(snapshot);
            MissionRouteGuidanceAdapter.Decision decision = MissionRouteGuidanceAdapter.plan(
                    aircraftId,
                    FlightPhase.CRUISE_CROSS,
                    snapshot,
                    profile(),
                    base);

            check(!decision.routeActive() && decision.waypointAdvanced() && decision.routeCompleted(),
                    "the final arrival must complete the route without retaining control");
            check(decision.output() == base,
                    "completed routes must release the tick to established base autonomy");
            check(MissionRouteManager.current(aircraftId).orElseThrow().route().completed(),
                    "completion must persist through the owned route manager");
            helper.succeed();
        } finally {
            clearManagers();
        }
    }

    private static FlightProfile profile() {
        return new FlightProfile(
                new ResourceLocation("wwdebug_benchmark", "mission_route_test"),
                "fighter",
                "turn_fighter",
                15.0,
                30.0,
                24.0,
                20.0,
                null,
                null,
                40.0);
    }

    private static FlightSnapshot snapshot(Vec3 position, double speedBps, double agl) {
        return new FlightSnapshot(
                position,
                new Vec3(0.0, 0.0, speedBps / 20.0),
                new Vec3(0.0, 0.0, 1.0),
                new Vec3(0.0, 0.0, 1.0),
                new Vec3(-1.0, 0.0, 0.0),
                speedBps,
                speedBps,
                0.0,
                agl,
                false,
                0.0f,
                0.0f,
                0.0,
                0.0,
                "south",
                0.68,
                0.68,
                1.0);
    }

    private static FlightControlOutput baseOutput(FlightSnapshot snapshot) {
        return new FlightControlOutput(
                0.0f,
                0.0f,
                0.0f,
                0.68f,
                snapshot.horizontalForward(),
                snapshot.position().y,
                snapshot.speedBps(),
                0.0,
                0.0,
                0.0,
                false,
                false,
                "base_output",
                "none");
    }

    private static void clearManagers() {
        MissionRouteManager.clearAll();
        MissionOrderManager.clearAll();
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }
}
