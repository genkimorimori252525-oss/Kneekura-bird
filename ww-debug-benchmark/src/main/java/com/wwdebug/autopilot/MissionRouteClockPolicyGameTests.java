package com.wwdebug.autopilot;

import com.wwdebug.benchmark.WWDebugBenchmarkMod;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraftforge.gametest.GameTestHolder;
import net.minecraftforge.gametest.PrefixGameTestTemplate;

/** Deterministic contracts for fixed-mission clocks while an owned route controls navigation. */
@GameTestHolder(WWDebugBenchmarkMod.MOD_ID)
@PrefixGameTestTemplate(false)
public final class MissionRouteClockPolicyGameTests {
    private MissionRouteClockPolicyGameTests() {
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "mission_route_clock_policy")
    public static void outboundRouteEarnsCruiseWithoutPrematureTransition(GameTestHelper helper) {
        int phaseTicks = 0;
        for (int tick = 0; tick < 500; tick++) {
            phaseTicks++;
            phaseTicks = MissionRouteClockPolicy.phaseTicksAfterHeldTick(
                    FlightPhase.CRUISE_OUTBOUND, phaseTicks);
        }
        check(phaseTicks == MissionRouteClockPolicy.outboundHeldEndTicks(),
                "held outbound route must saturate below the ordinary transition threshold");

        // The route completes during this tick, so the RETURN injection no longer applies the hold.
        phaseTicks++;
        check(phaseTicks == MissionRouteClockPolicy.outboundTransitionTicks() - 1,
                "completion tick must arm but not perform the ordinary phase transition");

        // The next ordinary session tick reaches the existing CRUISE_OUTBOUND transition threshold.
        phaseTicks++;
        check(phaseTicks == MissionRouteClockPolicy.outboundTransitionTicks(),
                "ordinary mission must resume without replaying the full outbound cruise sample");
        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "mission_route_clock_policy")
    public static void nonOutboundRoutePhasesRetainPreviousFreezeBehavior(GameTestHelper helper) {
        for (FlightPhase phase : new FlightPhase[]{
                FlightPhase.TURN_LEFT, FlightPhase.CRUISE_CROSS, FlightPhase.TURN_RIGHT}) {
            int phaseTicks = 57;
            for (int tick = 0; tick < 200; tick++) {
                phaseTicks++;
                phaseTicks = MissionRouteClockPolicy.phaseTicksAfterHeldTick(phase, phaseTicks);
            }
            check(phaseTicks == 57, phase + " clock must remain frozen while route-owned");
        }
        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "mission_route_clock_policy")
    public static void missionTimeoutRemainsFrozen(GameTestHelper helper) {
        int missionTicks = 9_000;
        for (int tick = 0; tick < 500; tick++) {
            missionTicks++;
            missionTicks = MissionRouteClockPolicy.missionTicksAfterHeldTick(missionTicks);
        }
        check(missionTicks == 9_000, "owned route must not consume the fixed mission timeout");
        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "mission_route_clock_policy")
    public static void invalidNegativeCountersAreRejected(GameTestHelper helper) {
        expectInvalid(() -> MissionRouteClockPolicy.phaseTicksAfterHeldTick(
                FlightPhase.CRUISE_OUTBOUND, -1), "negative phase ticks must be rejected");
        expectInvalid(() -> MissionRouteClockPolicy.missionTicksAfterHeldTick(-1),
                "negative mission ticks must be rejected");
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
