package com.wwdebug.autopilot;

import com.wwdebug.benchmark.WWDebugBenchmarkMod;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.resources.ResourceLocation;
import net.minecraftforge.gametest.GameTestHolder;
import net.minecraftforge.gametest.PrefixGameTestTemplate;

/** Deterministic contracts for measured-profile landing-pattern rejoin speed. */
@GameTestHolder(WWDebugBenchmarkMod.MOD_ID)
@PrefixGameTestTemplate(false)
public final class PatternRejoinSpeedPolicyGameTests {
    private static final int RETURN_TO_PATTERN_TIMEOUT_TICKS = 1_800;
    private static final double TICKS_PER_SECOND = 20.0;

    private PatternRejoinSpeedPolicyGameTests() {
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "pattern_rejoin_speed_policy")
    public static void measuredTurnFloorProtectsSlowAttackerRejoin(GameTestHelper helper) {
        FlightProfile ju87Like = profile("attacker", 9.787183030570501,
                16.70264754545161, 15.68695168141023, 18.75373230144395,
                22.270196727268818);
        check(close(PatternRejoinSpeedPolicy.targetSpeedBps(ju87Like),
                        ju87Like.turnSpeedFloorBps()),
                "slow attacker rejoin must not command below measured turn floor");
        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "pattern_rejoin_speed_policy")
    public static void combinedJu87HypothesisFitsExistingRejoinBudget(GameTestHelper helper) {
        FlightProfile ju87Like = profile("attacker", 9.787183030570501,
                16.70264754545161, 15.68695168141023, 18.75373230144395,
                22.270196727268818);
        double measuredTarget = PatternRejoinSpeedPolicy.targetSpeedBps(ju87Like);
        double idealTravelBudget = measuredTarget
                * (RETURN_TO_PATTERN_TIMEOUT_TICKS / TICKS_PER_SECOND);
        double observedClockFixedRejoinDistance = 1_371.0;

        check(idealTravelBudget > observedClockFixedRejoinDistance * 1.20,
                "combined clock and measured-speed hypothesis must retain at least 20% ideal "
                        + "travel margin inside the unchanged rejoin timeout");
        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "pattern_rejoin_speed_policy")
    public static void ExistingApproachAndClimbMarginsRemainAuthoritative(GameTestHelper helper) {
        FlightProfile approachDominant = profile("fighter", 20.0, 40.0, 25.0, 30.0, 50.0);
        check(close(PatternRejoinSpeedPolicy.targetSpeedBps(approachDominant), 37.5),
                "existing approach margin must remain authoritative when highest");

        FlightProfile climbDominant = profile("attacker", 10.0, 20.0, 25.0, 18.0, 32.0);
        check(close(PatternRejoinSpeedPolicy.targetSpeedBps(climbDominant), 25.0),
                "existing climb target must remain authoritative when highest");
        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "pattern_rejoin_speed_policy")
    public static void NullProfileIsRejected(GameTestHelper helper) {
        try {
            PatternRejoinSpeedPolicy.targetSpeedBps(null);
            throw new IllegalStateException("null profile must be rejected");
        } catch (NullPointerException expected) {
            helper.succeed();
        }
    }

    private static FlightProfile profile(String role, double stallGuard, double cruise,
                                         double climb, double turnFloor, double topSpeed) {
        return new FlightProfile(
                new ResourceLocation("wwdebug", "pattern_rejoin_" + role),
                role,
                "representative",
                stallGuard,
                cruise,
                climb,
                turnFloor,
                null,
                null,
                topSpeed);
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
