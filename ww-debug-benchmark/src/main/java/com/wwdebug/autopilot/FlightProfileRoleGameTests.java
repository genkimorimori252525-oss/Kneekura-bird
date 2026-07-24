package com.wwdebug.autopilot;

import com.wwdebug.benchmark.WWDebugBenchmarkMod;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.resources.ResourceLocation;
import net.minecraftforge.gametest.GameTestHolder;
import net.minecraftforge.gametest.PrefixGameTestTemplate;

/** Deterministic role-admission contracts for measured autonomous-flight profiles. */
@GameTestHolder(WWDebugBenchmarkMod.MOD_ID)
@PrefixGameTestTemplate(false)
public final class FlightProfileRoleGameTests {
    private FlightProfileRoleGameTests() {
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "flight_profile_role_contract")
    public static void torpedoBomberUsesCommonFlightWithoutFighterAuthority(GameTestHelper helper) {
        FlightProfile profile = new FlightProfile(
                new ResourceLocation("warfare_wings", "g4m"),
                "torpedo-bomber",
                "escort",
                15.0,
                24.0,
                22.0,
                40.0,
                null,
                null,
                32.0);

        check(profile.isTorpedoBomber(), "torpedo-bomber role aliases must normalize consistently");
        check(profile.supportsAutonomousFlight(),
                "torpedo bombers must participate in common noncombat autonomous flight");
        check(!profile.isFighter() && !profile.isLevelBomber() && !profile.isAttacker(),
                "common flight admission must not grant fighter, level-bomber, or attacker identity");
        check(Math.abs(profile.turnSpeedFloorBps() - 21.6) < 1.0e-9,
                "heavy-aircraft turn floor must be bounded by measured cruise safety margin");
        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "flight_profile_role_contract")
    public static void unknownRoleRemainsExcluded(GameTestHelper helper) {
        FlightProfile profile = new FlightProfile(
                new ResourceLocation("wwdebug_benchmark", "unsupported_role"),
                "transport",
                "none",
                15.0,
                24.0,
                22.0,
                20.0,
                null,
                null,
                32.0);

        check(!profile.supportsAutonomousFlight(),
                "unqualified roles must not silently enter autonomous flight");
        helper.succeed();
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }
}
