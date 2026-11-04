package com.wwdebug.autopilot;

import com.wwdebug.benchmark.WWDebugBenchmarkMod;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.ListTag;
import net.minecraft.nbt.Tag;
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

        MissionOrder emptyAborts = MissionOrder.builder(MissionOrder.Type.HOLD_POSITION)
                .targetPosition(new Vec3(1.0, 80.0, 1.0), 8.0)
                .build();
        check(MissionOrderCodec.read(MissionOrderCodec.write(emptyAborts)).equals(emptyAborts),
                "an empty abort-condition list must remain valid");

        MissionOrderManager.restore(restoredData.snapshot());
        MissionOrderManager.Assignment next = MissionOrderManager.assign(
                UUID.fromString("00000000-0000-0000-0000-000000000506"), emptyAborts);
        check(next.revision() > assignment.revision(),
                "restored revisions must remain monotonic after restart");

        MissionOrderManager.clearAll();
        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "mission_order_contract")
    public static void returnHomeWithoutRunwayCodecContract(GameTestHelper helper) {
        checkReturnHomeWithoutRunwayCodec();
        helper.succeed();
    }

    static void checkReturnHomeWithoutRunwayCodec() {
        MissionOrder order = MissionOrder.builder(MissionOrder.Type.RETURN_TO_BASE)
                .orderId(UUID.fromString("00000000-0000-0000-0000-000000000801"))
                .home(new Vec3(18.0, 73.0, -24.0), null)
                .build();
        CompoundTag encoded = MissionOrderCodec.write(order);
        check(encoded.contains("home_position", Tag.TAG_COMPOUND)
                        && !encoded.contains("runway_direction"),
                "home-only return must serialize without inventing a runway");
        check(order.equals(MissionOrderCodec.read(encoded)),
                "home-only return must round-trip without changing the order");
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "mission_order_contract")
    public static void holdWithoutRunwayCodecContract(GameTestHelper helper) {
        checkHoldWithoutRunwayCodec();
        helper.succeed();
    }

    static void checkHoldWithoutRunwayCodec() {
        MissionOrder hold = MissionOrder.builder(MissionOrder.Type.HOLD_POSITION)
                .orderId(UUID.fromString("00000000-0000-0000-0000-000000000802"))
                .home(new Vec3(4.0, 65.0, 6.0), null)
                .build();
        check(hold.equals(MissionOrderCodec.read(MissionOrderCodec.write(hold))),
                "home-only non-landing orders must also round-trip");
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "mission_order_contract")
    public static void homeAndRunwayCodecContract(GameTestHelper helper) {
        checkHomeAndRunwayCodec();
        helper.succeed();
    }

    static void checkHomeAndRunwayCodec() {
        Vec3 home = new Vec3(18.0, 73.0, -24.0);
        Vec3 runway = new Vec3(0.0, 0.0, 1.0);
        for (MissionOrder.Type type : new MissionOrder.Type[]{
                MissionOrder.Type.RETURN_TO_BASE, MissionOrder.Type.LAND}) {
            MissionOrder order = MissionOrder.builder(type).home(home, runway).build();
            check(order.equals(MissionOrderCodec.read(MissionOrderCodec.write(order))),
                    type + " with home and runway must continue to round-trip");
        }
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "mission_order_contract")
    public static void returnHomeWithoutRunwaySavedDataContract(GameTestHelper helper) {
        checkReturnHomeWithoutRunwaySavedData();
        helper.succeed();
    }

    static void checkReturnHomeWithoutRunwaySavedData() {
        UUID returnAircraft = UUID.fromString("00000000-0000-0000-0000-000000000811");
        UUID otherAircraft = UUID.fromString("00000000-0000-0000-0000-000000000812");
        MissionOrder returnOrder = MissionOrder.builder(MissionOrder.Type.RETURN_TO_BASE)
                .orderId(UUID.fromString("00000000-0000-0000-0000-000000000813"))
                .home(new Vec3(-18.0, 70.0, 32.0), null)
                .build();
        MissionOrder otherOrder = MissionOrder.builder(MissionOrder.Type.HOLD_POSITION)
                .orderId(UUID.fromString("00000000-0000-0000-0000-000000000814"))
                .targetPosition(new Vec3(3.0, 90.0, 7.0), 8.0)
                .build();
        MissionOrderManager.Assignment returning = new MissionOrderManager.Assignment(41L, returnOrder);
        MissionOrderManager.Assignment other = new MissionOrderManager.Assignment(42L, otherOrder);
        MissionOrderSavedData initial = new MissionOrderSavedData();
        initial.replace(Map.of(returnAircraft, returning, otherAircraft, other));
        Map<UUID, MissionOrderManager.Assignment> loaded =
                MissionOrderSavedData.load(initial.save(new CompoundTag())).snapshot();
        check(other.equals(loaded.get(otherAircraft)),
                "saving and loading must retain an unrelated assignment");
        check(returning.equals(loaded.get(returnAircraft)),
                "saving and loading must retain the home-only return assignment");
        check(loaded.size() == 2, "saving and loading must retain exactly both assignments");
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "mission_order_contract")
    public static void partialHomeVectorsRemainInvalidContract(GameTestHelper helper) {
        checkPartialHomeVectorsRemainInvalid();
        helper.succeed();
    }

    static void checkPartialHomeVectorsRemainInvalid() {
        MissionOrder land = MissionOrder.builder(MissionOrder.Type.LAND)
                .home(new Vec3(2.0, 64.0, 3.0), new Vec3(0.0, 0.0, 1.0))
                .build();
        CompoundTag landWithoutRunway = MissionOrderCodec.write(land);
        landWithoutRunway.remove("runway_direction");
        expectInvalid(() -> MissionOrderCodec.read(landWithoutRunway),
                "LAND without a runway must remain invalid");

        CompoundTag runwayWithoutHome = MissionOrderCodec.write(land);
        runwayWithoutHome.remove("home_position");
        expectInvalid(() -> MissionOrderCodec.read(runwayWithoutHome),
                "a persisted runway without a home must remain invalid");

        CompoundTag malformedHome = MissionOrderCodec.write(land);
        malformedHome.getCompound("home_position").remove("z");
        expectInvalid(() -> MissionOrderCodec.read(malformedHome),
                "a home vector with missing coordinates must remain invalid");
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "mission_order_contract")
    public static void malformedMissionOrderDoesNotDiscardValidAssignments(GameTestHelper helper) {
        UUID validAircraft = UUID.fromString("00000000-0000-0000-0000-000000000601");
        UUID malformedVectorAircraft = UUID.fromString("00000000-0000-0000-0000-000000000602");
        UUID malformedScalarAircraft = UUID.fromString("00000000-0000-0000-0000-000000000604");
        MissionOrder validOrder = MissionOrder.builder(MissionOrder.Type.HOLD_POSITION)
                .orderId(UUID.fromString("00000000-0000-0000-0000-000000000603"))
                .targetPosition(new Vec3(15.0, 90.0, -12.0), 10.0)
                .build();
        MissionOrderManager.Assignment validAssignment = new MissionOrderManager.Assignment(7L, validOrder);

        MissionOrderSavedData initial = new MissionOrderSavedData();
        initial.replace(Map.of(validAircraft, validAssignment));
        CompoundTag serialized = initial.save(new CompoundTag());
        ListTag entries = serialized.getList("assignments", Tag.TAG_COMPOUND);

        CompoundTag malformedVectorOrder = MissionOrderCodec.write(validOrder);
        malformedVectorOrder.getCompound("target_position").remove("z");
        entries.add(assignmentEntry(malformedVectorAircraft, 8L, malformedVectorOrder));

        CompoundTag malformedScalarOrder = MissionOrderCodec.write(validOrder);
        malformedScalarOrder.putString("minimum_return_fuel_fraction", "not-a-number");
        entries.add(assignmentEntry(malformedScalarAircraft, 9L, malformedScalarOrder));

        expectInvalid(() -> MissionOrderCodec.read(malformedVectorOrder),
                "missing vector components must be rejected");
        expectInvalid(() -> MissionOrderCodec.read(malformedScalarOrder),
                "incorrectly typed scalar fields must be rejected");
        MissionOrderSavedData restored = MissionOrderSavedData.load(serialized);
        check(validAssignment.equals(restored.snapshot().get(validAircraft)),
                "a valid assignment must survive beside malformed entries");
        check(!restored.snapshot().containsKey(malformedVectorAircraft),
                "the malformed vector assignment must be isolated");
        check(!restored.snapshot().containsKey(malformedScalarAircraft),
                "the malformed scalar assignment must be isolated");

        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "mission_order_contract")
    public static void duplicateAndOverflowedRevisionsAreIsolated(GameTestHelper helper) {
        UUID duplicateAircraft = UUID.fromString("00000000-0000-0000-0000-000000000701");
        UUID conflictAircraft = UUID.fromString("00000000-0000-0000-0000-000000000702");
        UUID validAircraft = UUID.fromString("00000000-0000-0000-0000-000000000703");
        UUID overflowAircraft = UUID.fromString("00000000-0000-0000-0000-000000000704");
        UUID nearOverflowAircraft = UUID.fromString("00000000-0000-0000-0000-000000000705");

        MissionOrder older = MissionOrder.builder(MissionOrder.Type.HOLD_POSITION)
                .targetPosition(new Vec3(10.0, 80.0, 10.0), 8.0)
                .build();
        MissionOrder newer = MissionOrder.builder(MissionOrder.Type.HOLD_POSITION)
                .targetPosition(new Vec3(20.0, 85.0, 20.0), 12.0)
                .build();
        MissionOrder valid = MissionOrder.builder(MissionOrder.Type.RETURN_TO_BASE)
                .home(new Vec3(0.0, 64.0, 0.0), new Vec3(0.0, 0.0, 1.0))
                .build();

        CompoundTag serialized = new CompoundTag();
        ListTag entries = new ListTag();
        entries.add(assignmentEntry(duplicateAircraft, 12L, MissionOrderCodec.write(newer)));
        entries.add(assignmentEntry(duplicateAircraft, 11L, MissionOrderCodec.write(older)));
        entries.add(assignmentEntry(conflictAircraft, 20L, MissionOrderCodec.write(older)));
        entries.add(assignmentEntry(conflictAircraft, 20L, MissionOrderCodec.write(newer)));
        entries.add(assignmentEntry(validAircraft, 30L, MissionOrderCodec.write(valid)));
        entries.add(assignmentEntry(overflowAircraft, Long.MAX_VALUE, MissionOrderCodec.write(valid)));
        entries.add(assignmentEntry(nearOverflowAircraft, Long.MAX_VALUE - 1L, MissionOrderCodec.write(valid)));
        serialized.put("assignments", entries);

        MissionOrderSavedData restored = MissionOrderSavedData.load(serialized);
        MissionOrderManager.Assignment duplicate = restored.snapshot().get(duplicateAircraft);
        check(duplicate != null && duplicate.revision() == 12L && duplicate.order().equals(newer),
                "the greatest valid duplicate revision must win independent of list order");
        check(!restored.snapshot().containsKey(conflictAircraft),
                "equal revisions with different orders must isolate that aircraft");
        check(restored.snapshot().containsKey(validAircraft),
                "an unrelated valid assignment must survive duplicate and overflow corruption");
        check(!restored.snapshot().containsKey(overflowAircraft),
                "Long.MAX_VALUE must not enter the revision counter");
        check(!restored.snapshot().containsKey(nearOverflowAircraft),
                "a persisted revision without safe increment room must be rejected");

        MissionOrderManager.restore(restored.snapshot());
        MissionOrderManager.Assignment next = MissionOrderManager.assign(
                UUID.fromString("00000000-0000-0000-0000-000000000706"), older);
        check(next.revision() > 30L && next.revision() > 0L,
                "the next revision must remain positive and exceed the restored valid maximum");

        MissionOrderManager.clearAll();
        helper.succeed();
    }

    private static CompoundTag assignmentEntry(UUID aircraftId, long revision, CompoundTag order) {
        CompoundTag entry = new CompoundTag();
        entry.putUUID("aircraft_id", aircraftId);
        entry.putLong("revision", revision);
        entry.put("order", order);
        return entry;
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
