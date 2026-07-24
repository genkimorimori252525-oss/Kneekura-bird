package com.wwdebug.autopilot;

import com.wwdebug.benchmark.WWDebugBenchmarkMod;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.phys.Vec3;
import net.minecraftforge.gametest.GameTestHolder;
import net.minecraftforge.gametest.PrefixGameTestTemplate;

/** Deterministic contracts for the pure waypoint-guidance control conversion. */
@GameTestHolder(WWDebugBenchmarkMod.MOD_ID)
@PrefixGameTestTemplate(false)
public final class WaypointGuidanceControlAdapterGameTests {
    private WaypointGuidanceControlAdapterGameTests() {
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "waypoint_guidance_control_contract")
    public static void adapterUsesEstablishedHeadingAltitudeAndSpeedEnvelope(GameTestHelper helper) {
        FlightProfile profile = profile();
        FlightSnapshot snapshot = snapshot(
                new Vec3(0.0, 80.0, 0.0),
                20.0,
                0.0,
                80.0,
                false,
                0.0f,
                0.0f);
        WaypointGuidancePlanner.GuidanceTarget target =
                new WaypointGuidancePlanner.GuidanceTarget(
                        new Vec3(1.0, 0.0, 0.0),
                        100.0,
                        30.0,
                        10.0,
                        20.0);

        FlightControlOutput output = WaypointGuidanceControlAdapter.adapt(snapshot, profile, target);
        check(Math.abs(output.x() + 0.78f) < 1.0e-6,
                "a ninety-degree left target must use the established steering clamp");
        check(Math.abs(output.z() - (-4.8 / 18.0)) < 1.0e-6,
                "altitude control must use the established proportional and damping gains");
        check(output.engineTarget() == 1.0f,
                "speed below the measured target envelope must request full engine power");
        check(output.desiredDirection().equals(target.horizontalDirection())
                        && output.targetAltitude() == 100.0
                        && output.targetSpeedBps() == 30.0,
                "adapter output must preserve the planner's direction, altitude, and measured speed");
        check(output.headingErrorDeg() == -90.0
                        && output.altitudeError() == 20.0
                        && output.speedErrorBps() == 10.0,
                "adapter telemetry must expose exact control errors");
        check(!output.stallRisk() && !output.terrainRisk(),
                "safe altitude and speed must not invent safety risks");
        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "waypoint_guidance_control_contract")
    public static void adapterPreservesSafetySignalsWithoutApplyingAuthority(GameTestHelper helper) {
        FlightProfile profile = profile();
        FlightSnapshot snapshot = snapshot(
                new Vec3(0.0, 20.0, 0.0),
                10.0,
                -2.0,
                10.0,
                false,
                0.0f,
                3.0f);
        WaypointGuidancePlanner.GuidanceTarget target =
                new WaypointGuidancePlanner.GuidanceTarget(
                        new Vec3(0.0, 0.0, 1.0),
                        30.0,
                        20.0,
                        20.0,
                        10.0);

        FlightControlOutput output = WaypointGuidanceControlAdapter.adapt(snapshot, profile, target);
        check(output.stallRisk(),
                "speed below the measured stall guard must remain visible to later safety layers");
        check(output.terrainRisk(),
                "low AGL must remain visible to the established terrain-avoidance layer");
        check(output.y() == 0.0f && "none".equals(output.safetyOverride()),
                "the pure adapter must neither brake nor claim safety authority");
        check("follow_owned_waypoint_route".equals(output.reason()),
                "route guidance must remain observable in telemetry");
        helper.succeed();
    }

    private static FlightProfile profile() {
        return new FlightProfile(
                new ResourceLocation("wwdebug_benchmark", "adapter_test"),
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

    private static FlightSnapshot snapshot(Vec3 position,
                                           double speedBps,
                                           double verticalSpeedBps,
                                           double agl,
                                           boolean onGround,
                                           float yaw,
                                           float pitch) {
        Vec3 forward = Vec3.directionFromRotation(pitch, yaw).normalize();
        Vec3 horizontal = new Vec3(forward.x, 0.0, forward.z).normalize();
        return new FlightSnapshot(
                position,
                new Vec3(0.0, verticalSpeedBps / 20.0, speedBps / 20.0),
                forward,
                horizontal,
                new Vec3(-horizontal.z, 0.0, horizontal.x),
                speedBps,
                speedBps,
                verticalSpeedBps,
                agl,
                onGround,
                yaw,
                pitch,
                0.0,
                yaw,
                "south",
                0.68,
                0.68,
                1.0);
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }
}
