package com.wwdebug.autopilot;

import com.wwdebug.benchmark.WWDebugBenchmarkMod;
import net.minecraft.core.BlockPos;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.vehicle.Boat;
import net.minecraftforge.gametest.GameTestHolder;
import net.minecraftforge.gametest.PrefixGameTestTemplate;

/**
 * Contract for the single mob-pilot gate.
 *
 * <p>These use a vanilla boat rather than an aircraft on purpose: the gate reads only
 * {@code getControllingPassenger()}, so the contract must hold for any vehicle and must not
 * silently depend on Warfare Wings being present.</p>
 */
@GameTestHolder(WWDebugBenchmarkMod.MOD_ID)
@PrefixGameTestTemplate(false)
public final class MobPilotGateGameTests {
    private MobPilotGateGameTests() {
    }

    @GameTest(template = "empty", timeoutTicks = 40, batch = "mob_pilot_gate_contract")
    public static void emptySeatIsNeitherMobPilotedNorPlayerControlled(GameTestHelper helper) {
        Boat vehicle = helper.spawn(EntityType.BOAT, new BlockPos(1, 2, 1));

        check(MobPilotGate.pilotOf(vehicle).isEmpty(),
                "an empty seat must not resolve a pilot");
        check(!MobPilotGate.isMobPiloted(vehicle),
                "an empty seat must not admit automated control");
        check(!MobPilotGate.isPlayerControlled(vehicle),
                "an empty seat is not a player takeover; the two cases are handled differently");
        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 40, batch = "mob_pilot_gate_contract")
    public static void mobOccupantIsAdmittedAndIdentified(GameTestHelper helper) {
        Boat vehicle = helper.spawn(EntityType.BOAT, new BlockPos(1, 2, 1));
        Mob occupant = helper.spawn(EntityType.PIG, new BlockPos(1, 2, 1));
        check(occupant.startRiding(vehicle), "test setup must seat the mob");

        check(MobPilotGate.isMobPiloted(vehicle),
                "a mob at the controls must admit automated control");
        check(MobPilotGate.pilotOf(vehicle).orElse(null) == occupant,
                "the gate must return the actual controlling mob, not merely a boolean");
        check(!MobPilotGate.isPlayerControlled(vehicle),
                "a mob pilot must never be reported as a player takeover");
        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 40, batch = "mob_pilot_gate_contract")
    public static void nullAircraftIsRejectedRatherThanThrowing(GameTestHelper helper) {
        // Control writers run inside a tick loop where an entity can already be gone. The gate
        // must fail closed instead of propagating an exception into the control path.
        check(MobPilotGate.pilotOf(null).isEmpty(), "a missing aircraft must resolve no pilot");
        check(!MobPilotGate.isMobPiloted(null), "a missing aircraft must not admit control");
        check(!MobPilotGate.isPlayerControlled(null),
                "a missing aircraft must not be reported as player controlled");
        helper.succeed();
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }
}
