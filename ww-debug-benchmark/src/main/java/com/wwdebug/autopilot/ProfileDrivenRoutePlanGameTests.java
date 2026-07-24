package com.wwdebug.autopilot;

import com.wwdebug.benchmark.WWDebugBenchmarkMod;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.phys.Vec3;
import net.minecraftforge.gametest.GameTestHolder;
import net.minecraftforge.gametest.PrefixGameTestTemplate;

import java.util.UUID;

/** Deterministic contracts for profile-driven compact route geometry. */
@GameTestHolder(WWDebugBenchmarkMod.MOD_ID)
@PrefixGameTestTemplate(false)
public final class ProfileDrivenRoutePlanGameTests {
    private ProfileDrivenRoutePlanGameTests() {
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "profile_route_plan_contract")
    public static void supportedRolesProduceOrderedCompactRoutes(GameTestHelper helper) {
        assertRoute(profile("fighter", 50.0), "fighter", 160.0, 58.0);
        assertRoute(profile("attacker", 45.0), "attacker", 153.0, 62.0);
        assertRoute(profile("bomber", 38.0), "bomber", 117.8, 82.0);
        assertRoute(profile("torpedo-bomber", 40.0), "torpedo_bomber", 124.0, 76.0);
        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "profile_route_plan_contract")
    public static void measuredSpeedScalingIsBounded(GameTestHelper helper) {
        check(close(ProfileDrivenRoutePlan.plan(profile("fighter", 20.0)).legBlocks(), 130.0),
                "slow fighter leg must use the lower safety bound");
        check(close(ProfileDrivenRoutePlan.plan(profile("fighter", 90.0)).legBlocks(), 180.0),
                "fast fighter leg must use the upper compact bound");
        check(close(ProfileDrivenRoutePlan.plan(profile("bomber", 20.0)).legBlocks(), 110.0),
                "slow bomber leg must use the heavy lower bound");
        check(close(ProfileDrivenRoutePlan.plan(profile("bomber", 70.0)).legBlocks(), 145.0),
                "fast bomber leg must use the heavy upper bound");
        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "profile_route_plan_contract")
    public static void invalidInputsAndUnknownRolesAreRejected(GameTestHelper helper) {
        expectInvalid(() -> ProfileDrivenRoutePlan.plan(profile("observer", 40.0)),
                "unknown roles must not enter the route matrix");
        expectInvalid(() -> ProfileDrivenRoutePlan.build(
                        UUID.randomUUID(), Vec3.ZERO, new Vec3(0.0, 1.0, 0.0),
                        profile("fighter", 40.0)),
                "vertical-only headings must be rejected");
        expectInvalid(() -> ProfileDrivenRoutePlan.build(
                        UUID.randomUUID(), new Vec3(Double.NaN, 0.0, 0.0), Vec3.SOUTH,
                        profile("fighter", 40.0)),
                "non-finite origins must be rejected");
        helper.succeed();
    }

    private static void assertRoute(FlightProfile profile, String expectedRole,
                                    double expectedLeg, double expectedRadius) {
        ProfileDrivenRoutePlan.Plan plan = ProfileDrivenRoutePlan.plan(profile);
        check(expectedRole.equals(plan.role()), "role normalization was not preserved");
        check(close(plan.legBlocks(), expectedLeg), "measured cruise speed produced the wrong leg");
        check(close(plan.arrivalRadiusBlocks(), expectedRadius), "role radius was not preserved");

        Vec3 origin = new Vec3(10.0, 80.0, -5.0);
        WaypointRoute route = ProfileDrivenRoutePlan.build(
                UUID.fromString("00000000-0000-0000-0000-000000000901"),
                origin, new Vec3(0.0, 0.2, 4.0), profile);
        check(route.waypoints().size() == 4 && route.nextIndex() == 0,
                "profile route must contain four ordered waypoints");
        check(close(route.waypoints().get(0).position().z, origin.z + expectedLeg),
                "first waypoint must follow normalized horizontal heading");
        check(route.waypoints().get(1).position().x < origin.x,
                "second waypoint must offset to the route right for a +Z heading");
        check(route.waypoints().get(2).position().x > origin.x,
                "third waypoint must cross to the opposite side");
        check(route.waypoints().get(3).arrivalRadius() > expectedRadius,
                "final waypoint must use a wider release radius");
    }

    private static FlightProfile profile(String role, double cruiseSpeed) {
        return new FlightProfile(
                new ResourceLocation("wwdebug", role.replace('-', '_')),
                role,
                "representative",
                Math.max(10.0, cruiseSpeed * 0.45),
                cruiseSpeed,
                Math.max(14.0, cruiseSpeed * 0.75),
                Math.max(12.0, cruiseSpeed * 0.65),
                null,
                null,
                Math.max(cruiseSpeed * 1.25, cruiseSpeed + 1.0));
    }

    private static void expectInvalid(Runnable action, String message) {
        try {
            action.run();
            throw new IllegalStateException(message);
        } catch (IllegalArgumentException expected) {
            // Expected contract rejection.
        }
    }

    private static boolean close(double actual, double expected) {
        return Math.abs(actual - expected) < 1.0e-6;
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }
}
