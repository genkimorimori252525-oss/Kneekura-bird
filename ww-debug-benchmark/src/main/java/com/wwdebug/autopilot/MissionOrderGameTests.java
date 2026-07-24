package com.wwdebug.autopilot;

import com.wwdebug.benchmark.WWDebugBenchmarkMod;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.world.phys.Vec3;
import net.minecraftforge.gametest.GameTestHolder;
import net.minecraftforge.gametest.PrefixGameTestTemplate;

import java.util.Map;
import java.util.UUID;

/** Deterministic contract checks for the mission-order data boundary. */
@GameTestHolder(WWDebugBenchmarkMod.MOD_ID)
@PrefixGameTestTemplate(false)
public final class MissionOrderGameTests {
    private MissionOrderGameTests() {
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "mission_order_contract")
    public static void missionOrderRevisionAndValidationContract(GameTestHelper helper) {
        MissionOrderManager.clearAll();
        UUID aircraft = UUID.fromString("00000000-0000-0000-0000-000000000101");
        UUID formation = UUID.fromString("00000000-0000-0000-0000-000000000201");
        UUID leader = UUID.fromString("00000000-0000-0000-0000-000000000202");

        MissionOrder patrol = MissionOrder.builder(MissionOrder.Type.PATROL)
                .orderId(UUID.fromString("00000000-0000-0000-0000-000000000301"))
                .targetPosition(new Vec3(120.0, 95.0, -40.0), 45.0)
                .home(new Vec3(0.0, 64.0, 0.0), new Vec3(0.0, 0.0, 4.0))
                .formation(formation, leader)
                .minimumReturnFuelFraction(0.30)
                .missionAltitude(95.0)
                .ingressDirection(new Vec3(3.0, 2.0, 0.0))
                .abortOn(MissionOrder.AbortCondition.PLAYER_TAKES_CONTROL,
                        MissionOrder.AbortCondition.FUEL_BELOW_RESERVE)
                .build();

        check(Math.abs(patrol.runwayDirection().length() - 1.0) < 1.0e-9,
                "runway direction must be normalized");
        check(patrol.ingressDirection().y == 0.0,
                "ingress direction must be horizontal");
        check(patrol.abortConditions().size() == 2,
                "abort conditions must be retained");

        MissionOrderManager.Assignment first = MissionOrderManager.assign(aircraft, patrol);
        check(MissionOrderManager.current(aircraft).orElseThrow().equals(first),
                "assigned order must be readable by aircraft UUID");

        MissionOrder returnOrder = MissionOrder.builder(MissionOrder.Type.RETURN_TO_BASE)
                .orderId(UUID.fromString("00000000-0000-0000-0000-000000000302"))
                .home(new Vec3(0.0, 64.0, 0.0), new Vec3(0.0, 0.0, 1.0))
                .minimumReturnFuelFraction(0.20)
                .build();

        check(MissionOrderManager.replace(aircraft, first.revision() + 1, returnOrder).isEmpty(),
                "stale revisions must not replace an order");
        MissionOrderManager.Assignment second = MissionOrderManager
                .replace(aircraft, first.revision(), returnOrder).orElseThrow();
        check(second.revision() > first.revision(),
                "successful replacement must advance revision");
        check(!MissionOrderManager.clear(aircraft, first.revision()),
                "stale revisions must not clear an order");
        check(MissionOrderManager.clear(aircraft, second.revision()),
                "current revision must clear an order");
        check(MissionOrderManager.current(aircraft).isEmpty(),
                "cleared order must no longer be visible");

        expectInvalid(() -> MissionOrder.builder(MissionOrder.Type.BOMB_TARGET)
                .attackRuns(1)
                .weaponsFree(true)
                .build(), "strike order without target must fail");
        expectInvalid(() -> MissionOrder.builder(MissionOrder.Type.LAND)
                .build(), "land order without home and runway must fail");
        expectInvalid(() -> MissionOrder.builder(MissionOrder.Type.HOLD_POSITION)
                .weaponsFree(true)
                .build(), "non-engagement order cannot enable weapons");

        MissionOrder strike = MissionOrder.builder(MissionOrder.Type.GROUND_ATTACK)
                .targetEntity(UUID.fromString("00000000-0000-0000-0000-000000000401"))
                .attackRuns(2)
                .weaponsFree(true)
                .build();
        MissionOrderManager.Assignment strikeAssignment = MissionOrderManager.assign(aircraft, strike);
        MissionOrder oneRunLeft = strike.withRemainingAttackRuns(1);
        MissionOrderManager.Assignment replacement = MissionOrderManager
                .replace(aircraft, strikeAssignment.revision(), oneRunLeft).orElseThrow();
        check(replacement.order().remainingAttackRuns() == 1,
                "attack-run changes must use the same revision-guarded replacement boundary");

        MissionOrderManager.clearAll();
        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "mission_order_contract")
    public static void missionOrderPersistenceRoundTripContract(GameTestHelper helper) {
        UUID aircraft = UUID.fromString("00000000-0000-0000-0000-000000000501");
        MissionOrder order = MissionOrder.builder(MissionOrder.Type.ESCORT)
                .orderId(UUID.fromString("00000000-0000-0000-0000-000000000502"))
                .targetEntity(UUID.fromString("00000000-0000-0000-0000-000000000503"))
                .targetPosition(new Vec3(-320.5, 110.0, 88.25), 64.0)
                .home(new Vec3(12.0, 70.0, -9.0), new Vec3(4.0, 2.0, 0.0))
                .formation(UUID.fromString("00000000-0000-0000-0000-000000000504"),
                        UUID.fromString("00000000-0000-0000-0000-000000000505"))
                .minimumReturnFuelFraction(0.35)
                .weaponsFree(true)
                .missionAltitude(110.0)
                .ingressDirection(new Vec3(-2.0, 7.0, 5.0))
                .abortOn(MissionOrder.AbortCondition.PLAYER_TAKES_CONTROL,
                        MissionOrder.AbortCondition.TARGET_LOST,
                        MissionOrder.AbortCondition.FRIENDLY_FIRE_RISK)
                .build();
        MissionOrderManager.Assignment assignment = new MissionOrderManager.Assignment(42L, order);

        MissionOrderSavedData initial = new MissionOrderSavedData();
        initial.replace(Map.of(aircraft, assignment));
        CompoundTag serialized = initial.save(new CompoundTag());
        MissionOrderSavedData restoredData = MissionOrderSavedData.load(serialized);
        MissionOrderManager.Assignment restored = restoredData.snapshot().get(aircraft);

        check(assignment.equals(restored), "saved assignment must round-trip exactly");
        check(MissionOrderCodec.read(MissionOrderCodec.write(order)).equals(order),
                "mission order codec must preserve every immutable field");

        MissionOrderManager.restore(restoredData.snapshot());
        MissionOrderManager.Assignment next = MissionOrderManager.assign(
                UUID.fromString("00000000-0000-0000-0000-000000000506"),
                MissionOrder.builder(MissionOrder.Type.HOLD_POSITION)
                        .targetPosition(new Vec3(1.0, 80.0, 1.0), 8.0)
                        .build());
        check(next.revision() > assignment.revision(),
                "restored revisions must remain monotonic after restart");

        MissionOrderManager.clearAll();
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
