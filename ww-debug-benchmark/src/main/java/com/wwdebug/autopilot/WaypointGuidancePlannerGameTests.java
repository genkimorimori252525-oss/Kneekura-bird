package com.wwdebug.autopilot;

import com.wwdebug.benchmark.WWDebugBenchmarkMod;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.world.phys.Vec3;
import net.minecraftforge.gametest.GameTestHolder;
import net.minecraftforge.gametest.PrefixGameTestTemplate;

import java.util.List;
import java.util.UUID;

/** Deterministic contracts for pure waypoint guidance calculation. */
@GameTestHolder(WWDebugBenchmarkMod.MOD_ID)
@PrefixGameTestTemplate(false)
public final class WaypointGuidancePlannerGameTests {
    private WaypointGuidancePlannerGameTests() {
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "waypoint_guidance_contract")
    public static void plannerTargetsOrderedWaypointsAtMeasuredSpeed(GameTestHelper helper) {
        WaypointRoute route = WaypointRoute.start(
                UUID.fromString("00000000-0000-0000-0000-000000000c01"),
                List.of(
                        new WaypointRoute.Waypoint(new Vec3(10.0, 90.0, 0.0), 2.0),
                        new WaypointRoute.Waypoint(new Vec3(12.0, 100.0, 0.0), 4.0)));

        WaypointGuidancePlanner.Decision outbound = WaypointGuidancePlanner.plan(
                new Vec3(0.0, 80.0, 0.0), new Vec3(0.0, 0.0, 1.0), route, 30.0);
        WaypointGuidancePlanner.GuidanceTarget outboundTarget = outbound.target().orElseThrow();
        check(!outbound.waypointAdvanced() && outbound.route() == route,
                "an unreached waypoint must preserve route state");
        check(outboundTarget.horizontalDirection().distanceTo(new Vec3(1.0, 0.0, 0.0)) < 1.0e-9,
                "guidance must point horizontally toward the current waypoint");
        check(outboundTarget.targetAltitude() == 90.0
                        && outboundTarget.targetSpeedBps() == 30.0,
                "guidance must preserve waypoint altitude and caller-selected measured speed");
        check(outboundTarget.horizontalDistance() == 10.0
                        && outboundTarget.verticalError() == 10.0,
                "guidance telemetry must expose horizontal and vertical errors");

        Vec3 overlappingPosition = new Vec3(9.0, 90.0, 0.0);
        WaypointGuidancePlanner.Decision firstReached = WaypointGuidancePlanner.plan(
                overlappingPosition, new Vec3(1.0, 0.0, 0.0), route, 30.0);
        check(firstReached.waypointAdvanced() && firstReached.route().nextIndex() == 1,
                "one planning call must advance exactly one reached waypoint");
        check(!firstReached.completed()
                        && firstReached.target().orElseThrow().targetAltitude() == 100.0,
                "overlapping arrival regions must target the second waypoint without skipping it");

        WaypointGuidancePlanner.Decision completed = WaypointGuidancePlanner.plan(
                overlappingPosition, new Vec3(1.0, 0.0, 0.0), firstReached.route(), 30.0);
        check(completed.waypointAdvanced() && completed.completed(),
                "a second explicit call may complete the overlapping final waypoint");
        check(completed.route().completed() && completed.target().isEmpty(),
                "completed route guidance must expose no live target");

        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "waypoint_guidance_contract")
    public static void plannerUsesForwardForVerticalBearingAndRejectsInvalidInputs(GameTestHelper helper) {
        WaypointRoute verticalRoute = WaypointRoute.start(
                UUID.fromString("00000000-0000-0000-0000-000000000c02"),
                List.of(new WaypointRoute.Waypoint(new Vec3(0.0, 100.0, 0.0), 1.0)));
        WaypointGuidancePlanner.GuidanceTarget vertical = WaypointGuidancePlanner.plan(
                new Vec3(0.0, 80.0, 0.0), new Vec3(4.0, 3.0, 0.0), verticalRoute, 25.0)
                .target().orElseThrow();
        check(vertical.horizontalDirection().distanceTo(new Vec3(1.0, 0.0, 0.0)) < 1.0e-9,
                "a vertically aligned waypoint must retain the aircraft's horizontal heading");
        check(vertical.horizontalDistance() == 0.0 && vertical.verticalError() == 20.0,
                "vertical-only guidance telemetry must remain finite and exact");

        expectInvalid(() -> WaypointGuidancePlanner.plan(
                        new Vec3(Double.NaN, 0.0, 0.0), Vec3.ZERO, verticalRoute, 25.0),
                "non-finite aircraft positions must be rejected");
        expectInvalid(() -> WaypointGuidancePlanner.plan(
                        Vec3.ZERO, new Vec3(0.0, Double.POSITIVE_INFINITY, 0.0), verticalRoute, 25.0),
                "non-finite forward vectors must be rejected");
        expectInvalid(() -> WaypointGuidancePlanner.plan(
                        new Vec3(0.0, 80.0, 0.0), new Vec3(0.0, 2.0, 0.0), verticalRoute, 25.0),
                "a vertical-only forward vector cannot resolve an undefined bearing");
        expectInvalid(() -> WaypointGuidancePlanner.plan(
                        Vec3.ZERO, new Vec3(1.0, 0.0, 0.0), verticalRoute, 0.0),
                "non-positive target speeds must be rejected");
        expectInvalid(() -> WaypointGuidancePlanner.plan(
                        Vec3.ZERO, new Vec3(1.0, 0.0, 0.0), verticalRoute, Double.NaN),
                "non-finite target speeds must be rejected");

        helper.succeed();
    }

    private static void expectInvalid(Runnable action, String message) {
        try {
            action.run();
            throw new IllegalStateException(message);
        } catch (IllegalArgumentException expected) {
            // Expected pure-boundary rejection.
        }
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }
}
