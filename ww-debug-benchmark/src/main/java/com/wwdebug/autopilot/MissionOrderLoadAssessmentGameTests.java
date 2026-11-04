package com.wwdebug.autopilot;

import com.wwdebug.benchmark.WWDebugBenchmarkMod;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.ListTag;
import net.minecraft.nbt.StringTag;
import net.minecraftforge.gametest.GameTestHolder;
import net.minecraftforge.gametest.PrefixGameTestTemplate;

import java.util.Map;
import java.util.UUID;

/** Contract for the read-only assessment, independent of world storage and weapon control. */
@GameTestHolder(WWDebugBenchmarkMod.MOD_ID)
@PrefixGameTestTemplate(false)
public final class MissionOrderLoadAssessmentGameTests {
    private MissionOrderLoadAssessmentGameTests() {
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "mission_order_contract")
    public static void loadAssessmentContract(GameTestHelper helper) {
        for (String scenario : scenarios()) {
            checkScenario(scenario);
        }
        helper.succeed();
    }

    static String[] scenarios() {
        return new String[] {"null-root", "missing-list", "wrong-list", "wrong-element", "empty",
                "valid", "valid-optional-uuids", "duplicate-identical", "newer-valid", "unknown-uuid", "missing-uuid",
                "bad-revision-type", "bad-revision-zero", "bad-revision-limit", "missing-order",
                "bad-order", "bad-formation-uuid", "bad-target-uuid", "conflicting-revision", "conflicting-revision-reversed",
                "bad-newer", "bad-newer-reversed", "input-unchanged",
                "weapons-byte-zero", "weapons-byte-one", "weapons-byte-two", "weapons-byte-minus-one",
                "weapons-byte-bad-newer", "weapons-byte-bad-newer-reversed"};
    }

    static void checkScenario(String scenario) {
        UUID aircraft = UUID.fromString("00000000-0000-0000-0000-000000000a01");
        UUID other = UUID.fromString("00000000-0000-0000-0000-000000000a02");
        MissionOrder permitted = MissionOrder.builder(MissionOrder.Type.CAP)
                .orderId(UUID.fromString("00000000-0000-0000-0000-000000000a03"))
                .weaponsFree(true).build();
        MissionOrder denied = MissionOrder.builder(MissionOrder.Type.CAP)
                .orderId(UUID.fromString("00000000-0000-0000-0000-000000000a04"))
                .weaponsFree(false).build();
        CompoundTag root = new CompoundTag();
        ListTag list = new ListTag();
        root.put("assignments", list);
        Map<UUID, MissionOrderManager.Assignment> expected = Map.of();
        boolean clean = false;
        switch (scenario) {
            case "null-root" -> root = null;
            case "missing-list" -> root.remove("assignments");
            case "wrong-list" -> root.putString("assignments", "not a list");
            case "wrong-element" -> list.add(StringTag.valueOf("not an assignment"));
            case "empty" -> clean = true;
            case "valid", "input-unchanged" -> {
                list.add(entry(aircraft, 3, permitted));
                list.add(entry(other, 2, denied));
                expected = Map.of(aircraft, new MissionOrderManager.Assignment(3, permitted),
                        other, new MissionOrderManager.Assignment(2, denied));
                clean = true;
            }
            case "valid-optional-uuids" -> {
                MissionOrder withUuids = MissionOrder.builder(MissionOrder.Type.CAP)
                        .orderId(UUID.fromString("00000000-0000-0000-0000-000000000a05"))
                        .targetEntity(other).formation(aircraft, other).build();
                list.add(entry(aircraft, 3, withUuids));
                expected = Map.of(aircraft, new MissionOrderManager.Assignment(3, withUuids));
                clean = true;
            }
            case "duplicate-identical" -> {
                list.add(entry(aircraft, 3, permitted));
                list.add(entry(aircraft, 3, permitted));
                expected = Map.of(aircraft, new MissionOrderManager.Assignment(3, permitted));
                clean = true;
            }
            case "newer-valid" -> {
                list.add(entry(aircraft, 2, permitted));
                list.add(entry(aircraft, 3, denied));
                expected = Map.of(aircraft, new MissionOrderManager.Assignment(3, denied));
                clean = true;
            }
            case "unknown-uuid" -> {
                CompoundTag invalid = entry(aircraft, 3, denied);
                invalid.putString("aircraft_id", "invalid");
                list.add(invalid);
            }
            case "missing-uuid" -> {
                CompoundTag invalid = entry(aircraft, 3, denied);
                invalid.remove("aircraft_id");
                list.add(invalid);
            }
            case "bad-revision-type" -> {
                CompoundTag invalid = entry(aircraft, 3, denied);
                invalid.putString("revision", "3");
                list.add(invalid);
            }
            case "bad-revision-zero" -> list.add(entry(aircraft, 0, denied));
            case "bad-revision-limit" -> list.add(entry(aircraft, Long.MAX_VALUE - 1, denied));
            case "missing-order" -> {
                CompoundTag invalid = entry(aircraft, 3, denied);
                invalid.remove("order");
                list.add(invalid);
            }
            case "bad-order" -> {
                CompoundTag invalid = entry(aircraft, 3, denied);
                invalid.getCompound("order").putString("weapons_free", "false");
                list.add(invalid);
            }
            case "bad-formation-uuid" -> {
                CompoundTag invalid = entry(aircraft, 3, denied);
                invalid.getCompound("order").putString("formation_id", "invalid");
                list.add(invalid);
            }
            case "bad-target-uuid" -> {
                CompoundTag invalid = entry(aircraft, 3, denied);
                invalid.getCompound("order").putIntArray("target_entity", new int[] {1, 2, 3});
                list.add(invalid);
            }
            case "weapons-byte-zero", "weapons-byte-one" -> {
                boolean enabled = scenario.equals("weapons-byte-one");
                MissionOrder order = enabled ? permitted : denied;
                CompoundTag validEntry = entry(aircraft, 3, order);
                validEntry.getCompound("order").putByte("weapons_free", (byte) (enabled ? 1 : 0));
                list.add(validEntry);
                expected = Map.of(aircraft, new MissionOrderManager.Assignment(3, order));
                clean = true;
            }
            case "weapons-byte-two", "weapons-byte-minus-one" -> {
                CompoundTag invalid = entry(aircraft, 3, denied);
                invalid.getCompound("order").putByte("weapons_free",
                        (byte) (scenario.equals("weapons-byte-two") ? 2 : -1));
                list.add(invalid);
            }
            case "weapons-byte-bad-newer", "weapons-byte-bad-newer-reversed" -> {
                CompoundTag older = entry(aircraft, 3, permitted);
                CompoundTag newer = entry(aircraft, 4, denied);
                newer.getCompound("order").putByte("weapons_free", (byte) 2);
                list.add(scenario.endsWith("reversed") ? newer : older);
                list.add(scenario.endsWith("reversed") ? older : newer);
            }
            case "conflicting-revision", "conflicting-revision-reversed" -> {
                CompoundTag first = entry(aircraft, 3, permitted);
                CompoundTag second = entry(aircraft, 3, denied);
                list.add(scenario.endsWith("reversed") ? second : first);
                list.add(scenario.endsWith("reversed") ? first : second);
                list.add(entry(other, 5, denied));
            }
            case "bad-newer", "bad-newer-reversed" -> {
                CompoundTag first = entry(aircraft, 3, permitted);
                CompoundTag second = entry(aircraft, 4, denied);
                second.getCompound("order").putString("weapons_free", "false");
                list.add(scenario.endsWith("reversed") ? second : first);
                list.add(scenario.endsWith("reversed") ? first : second);
            }
            default -> throw new IllegalArgumentException("unknown scenario " + scenario);
        }
        CompoundTag before = root == null ? null : root.copy();
        MissionOrderLoadAssessment.Result result = MissionOrderLoadAssessment.assess(root);
        check(root == null || root.equals(before), scenario + ": input changed");
        check(result.status() == (clean ? MissionOrderLoadAssessment.Status.CLEAN
                : MissionOrderLoadAssessment.Status.UNKNOWN), scenario + ": incorrect status");
        check(result.assignments().equals(expected), scenario + ": partial or incorrect snapshot");
        try {
            result.assignments().put(aircraft, new MissionOrderManager.Assignment(6, permitted));
            throw new AssertionError(scenario + ": snapshot must be immutable");
        } catch (UnsupportedOperationException expectedImmutable) {
            // A caller must not be able to change an assessed snapshot.
        }
    }

    private static CompoundTag entry(UUID aircraft, long revision, MissionOrder order) {
        CompoundTag entry = new CompoundTag();
        entry.putUUID("aircraft_id", aircraft);
        entry.putLong("revision", revision);
        entry.put("order", MissionOrderCodec.write(order));
        return entry;
    }

    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
