package com.wwdebug.autopilot;

import com.wwdebug.autopilot.ControlAuthorityArbiter.Authority;
import com.wwdebug.benchmark.WWDebugBenchmarkMod;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraftforge.gametest.GameTestHolder;
import net.minecraftforge.gametest.PrefixGameTestTemplate;
import net.minecraft.world.phys.Vec3;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/**
 * Contract for proposal selection.
 *
 * <p>The load-bearing test here is {@link #selectionReproducesTheCurrentWriteOrder}: seven layers
 * currently write in fixed statement order and the last one wins, so the conversion is only safe if
 * priority selection picks the same layer the write order would have left in place.</p>
 */
@GameTestHolder(WWDebugBenchmarkMod.MOD_ID)
@PrefixGameTestTemplate(false)
public final class ControlProposalGameTests {
    private ControlProposalGameTests() {
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "control_proposal_contract")
    public static void selectionReproducesTheCurrentWriteOrder(GameTestHelper helper) {
        // Production write order today, earliest first. Whoever writes last wins, so the expected
        // winner of any subset is simply its last member.
        Authority[] writeOrder = {
                Authority.BENCHMARK_CONTROL,     // BenchmarkManager:82
                Authority.BASE_AUTONOMY,         // AutonomousFlightManager:104
                Authority.FORMATION,             // FormationFlightManager:212, formation slot
                Authority.DEFENSIVE_COMBAT,      // DefensiveAirCombatManager:77
        };

        for (int end = 1; end <= writeOrder.length; end++) {
            List<ControlProposal> bids = new ArrayList<>();
            for (int i = 0; i < end; i++) {
                bids.add(bid(writeOrder[i]));
            }
            Authority lastWriter = writeOrder[end - 1];
            Authority selected = ControlAuthorityArbiter.select(bids).orElseThrow().authority();
            check(selected == lastWriter,
                    "selection must pick " + lastWriter + " -- the layer the write order would have"
                            + " left in place -- but picked " + selected);
        }
        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "control_proposal_contract")
    public static void collisionAvoidanceBeatsCombatBecauseCombatIsSuppressed(GameTestHelper helper) {
        // FighterCombatFacade refuses to write while AirspaceSafetyProbe reports risk, so the
        // avoidance manoeuvre FormationFlightManager wrote survives the tick. Selection must reach
        // the same outcome without depending on that refusal.
        Authority selected = ControlAuthorityArbiter.select(List.of(
                bid(Authority.BASE_AUTONOMY),
                bid(Authority.COLLISION_AVOIDANCE),
                bid(Authority.OFFENSIVE_COMBAT),
                bid(Authority.DEFENSIVE_COMBAT))).orElseThrow().authority();
        check(selected == Authority.COLLISION_AVOIDANCE,
                "separation must win over both combat layers, not merely suppress them");
        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "control_proposal_contract")
    public static void peersDoNotSwapOwnershipOnSubmissionOrder(GameTestHelper helper) {
        ControlProposal offensive = bid(Authority.OFFENSIVE_COMBAT);
        ControlProposal energy = bid(Authority.ENERGY_FIGHTER_REENGAGEMENT);

        check(ControlAuthorityArbiter.select(List.of(offensive, energy)).orElseThrow() == offensive,
                "the first peer to bid must keep the tick");
        check(ControlAuthorityArbiter.select(List.of(energy, offensive)).orElseThrow() == energy,
                "reversing submission order must reverse nothing but which peer bid first");
        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "control_proposal_contract")
    public static void noBidsMeansNoOwner(GameTestHelper helper) {
        check(ControlAuthorityArbiter.select(List.of()).isEmpty(),
                "an empty tick must yield no owner rather than a default");
        check(ControlAuthorityArbiter.select(null).isEmpty(),
                "a missing proposal list must not throw inside the control path");

        List<ControlProposal> withHole = new ArrayList<>();
        withHole.add(null);
        withHole.add(bid(Authority.BASE_AUTONOMY));
        Optional<ControlProposal> selected = ControlAuthorityArbiter.select(withHole);
        check(selected.isPresent() && selected.get().authority() == Authority.BASE_AUTONOMY,
                "an abstaining layer must not prevent a real bid from winning");
        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "control_proposal_contract")
    public static void guidanceProposalsCorrectTheRollSign(GameTestHelper helper) {
        // Six of the seven writers negate roll on the way out; BenchmarkManager does not. The
        // asymmetry is real, so it lives in the factory rather than at each call site.
        FlightControlOutput output = new FlightControlOutput(
                0.5f, 0.25f, -0.125f, 0.8f, Vec3.ZERO,
                100.0, 40.0, 0.0, 0.0, 0.0, false, false, "test_reason", "none");

        ControlProposal guided = ControlProposal.fromGuidance(Authority.BASE_AUTONOMY, output);
        check(guided.x() == -0.5f, "guidance proposals must negate roll as the writers do");
        check(guided.y() == 0.25f && guided.z() == -0.125f,
                "pitch and yaw must pass through unchanged");
        check("test_reason".equals(guided.reason()), "the output's reason must reach telemetry");

        ControlProposal raw = ControlProposal.ofRawInputs(
                Authority.BENCHMARK_CONTROL, 0.5f, 0.25f, -0.125f, 0.8f, "stored_input");
        check(raw.x() == 0.5f, "raw proposals must not negate; BenchmarkManager writes unnegated");
        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "control_proposal_contract")
    public static void proposalsAreClampedAndCannotAbstainByAuthority(GameTestHelper helper) {
        ControlProposal clamped = ControlProposal.ofRawInputs(
                Authority.BASE_AUTONOMY, 4.0f, -9.0f, 0.0f, 7.0f, null);
        check(clamped.x() == 1.0f && clamped.y() == -1.0f,
                "control inputs must be clamped to the same range FlightControlOutput enforces");
        check(clamped.engineTarget() == 1.0f, "engine target must be clamped to 0..1");
        check("unspecified".equals(clamped.reason()), "a missing reason must not reach telemetry as null");

        check(rejects(() -> ControlProposal.ofRawInputs(
                        Authority.NONE, 0f, 0f, 0f, 0f, "abstain")),
                "NONE is not a bid; a layer that declines must return Optional.empty()");
        check(rejects(() -> ControlProposal.ofRawInputs(null, 0f, 0f, 0f, 0f, "null")),
                "a proposal without an authority must be rejected at construction");
        helper.succeed();
    }

    private static ControlProposal bid(Authority authority) {
        return ControlProposal.ofRawInputs(authority, 0.0f, 0.0f, 0.0f, 0.5f,
                authority.name().toLowerCase(java.util.Locale.ROOT));
    }

    private static boolean rejects(Runnable action) {
        try {
            action.run();
            return false;
        } catch (IllegalArgumentException expected) {
            return true;
        }
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }
}
