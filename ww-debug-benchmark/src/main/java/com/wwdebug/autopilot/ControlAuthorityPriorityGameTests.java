package com.wwdebug.autopilot;

import com.wwdebug.autopilot.ControlAuthorityArbiter.Authority;
import com.wwdebug.benchmark.WWDebugBenchmarkMod;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraftforge.gametest.GameTestHolder;
import net.minecraftforge.gametest.PrefixGameTestTemplate;

/**
 * Pins the control-authority priority stack declared in Issue #7.
 *
 * <p>Priority used to exist only as the order of statements inside
 * {@code ControlAuthorityArbiter.applyControl}, where reordering two lines silently reorders
 * safety. These tests make the intended stack a checked contract, so the coming conversion to a
 * proposal-based arbiter cannot quietly change who wins.</p>
 */
@GameTestHolder(WWDebugBenchmarkMod.MOD_ID)
@PrefixGameTestTemplate(false)
public final class ControlAuthorityPriorityGameTests {
    private ControlAuthorityPriorityGameTests() {
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "control_authority_priority")
    public static void playerControlOutranksEveryAutomatedLayer(GameTestHelper helper) {
        for (Authority other : Authority.values()) {
            if (other == Authority.PLAYER_CONTROLLED) {
                continue;
            }
            check(Authority.PLAYER_CONTROLLED.outranks(other),
                    "player control must outrank " + other.name()
                            + " — Issue #7 requires zero AI input while a player flies");
        }
        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "control_authority_priority")
    public static void safetyOutranksCombatWhichOutranksNavigation(GameTestHelper helper) {
        // Highest first. Peers at the same level are grouped.
        check(Authority.TERRAIN_AVOIDANCE.outranks(Authority.COLLISION_AVOIDANCE),
                "terrain avoidance is level 4 and must outrank aircraft separation at level 5");
        check(Authority.COLLISION_AVOIDANCE.outranks(Authority.DEFENSIVE_COMBAT),
                "aircraft separation must outrank the defensive manoeuvre it would otherwise fight");
        check(Authority.DEFENSIVE_COMBAT.outranks(Authority.OFFENSIVE_COMBAT),
                "an aircraft under attack must defend before it presses its own attack");
        check(Authority.OFFENSIVE_COMBAT.outranks(Authority.BASE_AUTONOMY),
                "role mission must outrank ordinary navigation");
        check(Authority.BASE_AUTONOMY.outranks(Authority.NONE),
                "any owner must outrank no owner");
        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "control_authority_priority")
    public static void roleMissionLayersArePeersNotRivals(GameTestHelper helper) {
        // Both are level 8. Whichever the facade selects wins on its own merits; neither may
        // silently pre-empt the other on priority alone.
        check(!Authority.OFFENSIVE_COMBAT.outranks(Authority.ENERGY_FIGHTER_REENGAGEMENT),
                "offensive combat must not outrank energy-fighter re-engagement");
        check(!Authority.ENERGY_FIGHTER_REENGAGEMENT.outranks(Authority.OFFENSIVE_COMBAT),
                "energy-fighter re-engagement must not outrank offensive combat");
        check(Authority.OFFENSIVE_COMBAT.priority()
                        == Authority.ENERGY_FIGHTER_REENGAGEMENT.priority(),
                "both are level 8 role-mission layers and must share a priority");
        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "control_authority_priority")
    public static void nothingOutranksItselfAndNoneIsTheFloor(GameTestHelper helper) {
        for (Authority authority : Authority.values()) {
            check(!authority.outranks(authority),
                    authority.name() + " must not outrank itself");
            if (authority != Authority.NONE) {
                check(authority.priority() > Authority.NONE.priority(),
                        authority.name() + " must sit above NONE");
                check(authority.outranks(null),
                        authority.name() + " must outrank an absent previous owner");
            }
        }
        check(Authority.NONE.priority() == 0, "NONE is the floor of the stack");
        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "control_authority_priority")
    public static void declarationOrderIsNotPriorityOrder(GameTestHelper helper) {
        // Guards a real hazard: ordinal() reads as a priority and is wrong. PLAYER_CONTROLLED is
        // declared last and is highest, but the pairs below disagree between the two orderings, so
        // any code that compares with ordinal() would invert safety.
        check(Authority.TERRAIN_AVOIDANCE.ordinal() < Authority.PLAYER_CONTROLLED.ordinal()
                        && Authority.PLAYER_CONTROLLED.outranks(Authority.TERRAIN_AVOIDANCE),
                "declaration order and priority order must be treated as unrelated");
        check(Authority.BASE_AUTONOMY.ordinal() < Authority.OFFENSIVE_COMBAT.ordinal()
                        && Authority.OFFENSIVE_COMBAT.outranks(Authority.BASE_AUTONOMY),
                "base autonomy is declared early and ranks lowest; do not compare with ordinal()");
        helper.succeed();
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }
}
