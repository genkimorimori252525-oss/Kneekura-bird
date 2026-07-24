package com.wwdebug.autopilot;

import com.wwdebug.benchmark.WWDebugBenchmarkMod;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.resources.ResourceLocation;
import net.minecraftforge.gametest.GameTestHolder;
import net.minecraftforge.gametest.PrefixGameTestTemplate;

/** Deterministic contracts for measured pattern-rejoin speed selection. */
@GameTestHolder(WWDebugBenchmarkMod.MOD_ID)
@PrefixGameTestTemplate(false)
public final class ReturnToPatternSpeedPolicyGameTests {
    private ReturnToPatternSpeedPolicyGameTests() {
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "return_pattern_speed_policy")
    public static void measuredTurnFloorCanDominateLongRejoin(GameTestHelper helper) {
        FlightProfile profile = profile(10.0, 14.0, 15.69, 18.75, 24.0);
        checkClose(ReturnToPatternSpeedPolicy.targetSpeedBps(profile), 18.75,
                "Ju 87-like rejoin must not command below measured turn floor");
        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "return_pattern_speed_policy")
    public static void existingApproachMarginRemainsAuthoritative(GameTestHelper helper) {
        FlightProfile profile = profile(10.0, 25.0, 16.0, 18.0, 30.0);
        double expected = profile.approachSpeedBps() * 1.25;
        checkClose(ReturnToPatternSpeedPolicy.targetSpeedBps(profile), expected,
                "approach margin must remain authoritative when it is highest");
        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "return_pattern_speed_policy")
    public static void existingClimbTargetRemainsAuthoritative(GameTestHelper helper) {
        FlightProfile profile = profile(10.0, 18.0, 24.0, 17.0, 28.0);
        checkClose(ReturnToPatternSpeedPolicy.targetSpeedBps(profile), 24.0,
                "climb target must remain authoritative when it is highest");
        helper.succeed();
    }

    private static FlightProfile profile(double stall, double cruise, double climb,
                                         double turnFloor, double topSpeed) {
        return new FlightProfile(
                new ResourceLocation("wwdebug", "return_pattern_policy_test"),
                "attacker", "dive_bomber", stall, cruise, climb, turnFloor,
                null, null, topSpeed);
    }

    private static void checkClose(double actual, double expected, String message) {
        if (Math.abs(actual - expected) > 1.0e-9) {
            throw new IllegalStateException(message + ": expected=" + expected + ", actual=" + actual);
        }
    }
}
