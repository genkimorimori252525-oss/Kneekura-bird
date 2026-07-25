package com.wwdebug.autopilot;

import com.wwdebug.benchmark.WWDebugBenchmarkMod;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.resources.ResourceLocation;
import net.minecraftforge.gametest.GameTestHolder;
import net.minecraftforge.gametest.PrefixGameTestTemplate;

/** Deterministic contracts for measured pattern-rejoin feasibility calculations. */
@GameTestHolder(WWDebugBenchmarkMod.MOD_ID)
@PrefixGameTestTemplate(false)
public final class PatternRejoinBudgetGameTests {
    private PatternRejoinBudgetGameTests() {
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "pattern_rejoin_budget_contract")
    public static void ju87MeasuredTurnFloorHasClockFixedMargin(GameTestHelper helper) {
        PatternRejoinBudget.Assessment budget = PatternRejoinBudget.atMeasuredTurnFloor(
                profile(18.7537), 1371.0, 1800);

        check(budget.canReachIdeally(), "measured turn floor must cover the observed rejoin distance");
        check(budget.hasMargin(0.20), "Ju 87 combined hypothesis must retain at least 20% ideal margin");
        check(close(budget.availableSeconds(), 90.0), "1800 ticks must equal 90 seconds");
        check(budget.requiredSpeedBps() < budget.targetSpeedBps(),
                "required speed must remain below the measured target");
        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "pattern_rejoin_budget_contract")
    public static void exactBoundaryAndShortfallAreReported(GameTestHelper helper) {
        PatternRejoinBudget.Assessment exact = PatternRejoinBudget.assess(900.0, 10.0, 1800, 20.0);
        check(exact.canReachIdeally(), "exact reach must count as feasible");
        check(close(exact.marginBlocks(), 0.0), "exact reach must have zero block margin");
        check(exact.hasMargin(0.0), "zero margin must satisfy a zero-margin requirement");

        PatternRejoinBudget.Assessment shortfall = PatternRejoinBudget.assess(901.0, 10.0, 1800, 20.0);
        check(!shortfall.canReachIdeally(), "one-block shortfall must remain infeasible");
        check(shortfall.marginBlocks() < 0.0 && shortfall.marginRatio() < 0.0,
                "shortfall must be visible in both margin forms");
        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "pattern_rejoin_budget_contract")
    public static void invalidInputsAreRejected(GameTestHelper helper) {
        expectInvalid(() -> PatternRejoinBudget.assess(0.0, 10.0, 1800, 20.0));
        expectInvalid(() -> PatternRejoinBudget.assess(100.0, Double.NaN, 1800, 20.0));
        expectInvalid(() -> PatternRejoinBudget.assess(100.0, 10.0, 0, 20.0));
        expectInvalid(() -> PatternRejoinBudget.assess(100.0, 10.0, 1800, Double.POSITIVE_INFINITY));
        expectInvalid(() -> PatternRejoinBudget.assess(100.0, 10.0, 1800, 20.0).hasMargin(-0.01));
        helper.succeed();
    }

    private static FlightProfile profile(double turnSpeedFloor) {
        return new FlightProfile(
                new ResourceLocation("wwdebug", "ju87_budget"),
                "attacker",
                "dive_bomber",
                10.0,
                25.0,
                20.0,
                turnSpeedFloor,
                null,
                null,
                32.0);
    }

    private static void expectInvalid(Runnable action) {
        try {
            action.run();
            throw new IllegalStateException("invalid budget input must be rejected");
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
