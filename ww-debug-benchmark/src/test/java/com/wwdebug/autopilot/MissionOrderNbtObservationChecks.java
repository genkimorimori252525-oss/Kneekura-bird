package com.wwdebug.autopilot;

import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.ListTag;
import net.minecraft.nbt.NbtIo;

import java.io.ByteArrayOutputStream;
import java.io.DataOutput;
import java.io.DataOutputStream;
import java.io.IOException;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.Map;
import java.util.UUID;
import java.util.zip.GZIPOutputStream;

/** Standalone NBT observation checks; never accesses a file or a server. */
public final class MissionOrderNbtObservationChecks {
    private static final UUID AIRCRAFT = UUID.fromString("00000000-0000-0000-0000-000000000b01");
    private static final UUID ORDER = UUID.fromString("00000000-0000-0000-0000-000000000b02");
    private MissionOrderNbtObservationChecks() { }

    public static void main(String[] args) throws Exception {
        String scenario = args[0];
        CompoundTag valid = validRoot();
        byte[] gzip = encode(valid, true);
        byte[] input;
        MissionOrderNbtObservation.Status expected;
        switch (scenario) {
            case "gzip", "source-after-copy", "source-after-return" -> {
                input = gzip;
                expected = MissionOrderNbtObservation.Status.ASSESSED_CLEAN;
            }
            case "plain" -> {
                input = encode(valid, false);
                expected = MissionOrderNbtObservation.Status.ASSESSED_CLEAN;
            }
            case "root-not-compound" -> {
                input = new byte[] {8, 0, 0, 0, 0};
                expected = MissionOrderNbtObservation.Status.INVALID;
            }
            case "missing-data" -> {
                input = encode(new CompoundTag(), true);
                expected = MissionOrderNbtObservation.Status.INVALID;
            }
            case "wrong-data" -> {
                CompoundTag root = new CompoundTag();
                root.putString("data", "not a compound");
                input = encode(root, true);
                expected = MissionOrderNbtObservation.Status.INVALID;
            }
            case "empty-data" -> {
                CompoundTag root = new CompoundTag();
                root.put("data", new CompoundTag());
                input = encode(root, true);
                expected = MissionOrderNbtObservation.Status.ASSESSED_UNKNOWN;
            }
            case "bad-assignment" -> {
                CompoundTag root = validRoot();
                root.getCompound("data").getList("assignments", 10).getCompound(0)
                        .getCompound("order").putString("weapons_free", "false");
                input = encode(root, true);
                expected = MissionOrderNbtObservation.Status.ASSESSED_UNKNOWN;
            }
            case "cross-gzip-two", "cross-gzip-minus-one", "cross-plain-two", "cross-plain-minus-one",
                    "cross-gzip-newer", "cross-gzip-newer-reversed",
                    "cross-plain-newer", "cross-plain-newer-reversed" -> {
                CompoundTag root = validRoot();
                ListTag entries = root.getCompound("data").getList("assignments", 10);
                CompoundTag older = entries.getCompound(0);
                if (scenario.contains("newer")) {
                    CompoundTag newer = older.copy();
                    newer.putLong("revision", 8L);
                    newer.getCompound("order").putByte("weapons_free", (byte) 2);
                    if (scenario.endsWith("reversed")) {
                        entries.add(0, newer);
                    } else {
                        entries.add(newer);
                    }
                } else {
                    older.getCompound("order").putByte("weapons_free",
                            (byte) (scenario.endsWith("minus-one") ? -1 : 2));
                }
                input = encode(root, scenario.startsWith("cross-gzip"));
                expected = MissionOrderNbtObservation.Status.ASSESSED_UNKNOWN;
            }
            case "bad-gzip" -> {
                input = new byte[] {31, (byte) 139, 8, 0, 1};
                expected = MissionOrderNbtObservation.Status.INVALID;
            }
            case "gzip-crc" -> {
                input = gzip.clone();
                input[input.length - 8] ^= 1;
                expected = MissionOrderNbtObservation.Status.INVALID;
            }
            case "gzip-expanded" -> {
                ByteArrayOutputStream bytes = new ByteArrayOutputStream();
                try (GZIPOutputStream out = new GZIPOutputStream(bytes)) {
                    out.write(new byte[MissionOrderNbtObservation.MAX_BYTES + 1]);
                }
                input = bytes.toByteArray();
                expected = MissionOrderNbtObservation.Status.TOO_LARGE;
            }
            case "trailing-plain" -> {
                byte[] raw = encode(valid, false);
                input = Arrays.copyOf(raw, raw.length + 1);
                input[raw.length] = 42;
                expected = MissionOrderNbtObservation.Status.INVALID;
            }
            case "oversized" -> {
                input = new byte[MissionOrderNbtObservation.MAX_BYTES + 1];
                expected = MissionOrderNbtObservation.Status.TOO_LARGE;
            }
            case "nbt-quota" -> {
                ByteArrayOutputStream bytes = new ByteArrayOutputStream();
                DataOutputStream out = new DataOutputStream(bytes);
                out.writeByte(10);
                out.writeUTF("");
                out.writeByte(11);
                out.writeUTF("array");
                out.writeInt(1_048_577); // Mapped NBT quota check occurs before array allocation.
                input = bytes.toByteArray();
                expected = MissionOrderNbtObservation.Status.UNVERIFIED;
            }
            case "source-before-copy" -> {
                input = gzip;
                input[0] = 0; // External change before observation; hash must represent this version.
                expected = MissionOrderNbtObservation.Status.INVALID;
            }
            case "null-input" -> {
                try {
                    MissionOrderNbtObservation.inspect(null);
                    throw new AssertionError("null is not evidence of an absent file");
                } catch (NullPointerException expectedNull) {
                    System.out.println("PASS null-input");
                    return;
                }
            }
            default -> throw new IllegalArgumentException("unknown scenario " + scenario);
        }
        byte[] before = input.clone();
        String expectedHash = input.length <= MissionOrderNbtObservation.MAX_BYTES ? hash(before) : null;
        MissionOrderNbtObservation.Result result;
        if (scenario.equals("source-after-copy")) {
            result = MissionOrderNbtObservation.inspect(input, () -> Arrays.fill(input, (byte) 0));
            check(!Arrays.equals(before, input), "test must mutate caller's bytes after snapshot");
        } else {
            result = MissionOrderNbtObservation.inspect(input);
            check(Arrays.equals(before, input), scenario + ": observation changed input");
        }
        check(result.status() == expected, scenario + ": status was " + result.status());
        check(java.util.Objects.equals(result.contentSha256(), expectedHash), scenario + ": incorrect snapshot hash");
        if (expected == MissionOrderNbtObservation.Status.ASSESSED_CLEAN) {
            check(result.assessment().isPresent(), scenario + ": missing assessment");
            check(result.assessment().orElseThrow().assignments()
                            .equals(Map.of(AIRCRAFT, new MissionOrderManager.Assignment(7, order()))),
                    scenario + ": decoded wrong assignment");
        } else if (expected == MissionOrderNbtObservation.Status.ASSESSED_UNKNOWN) {
            check(result.assessment().isPresent()
                            && result.assessment().orElseThrow().assignments().isEmpty(),
                    scenario + ": unsafe partial snapshot");
        } else {
            check(result.assessment().isEmpty(), scenario + ": unexpected assessment");
        }
        if (scenario.equals("source-after-return")) {
            Arrays.fill(input, (byte) 0);
            check(expectedHash.equals(result.contentSha256()), "result hash changed after return");
            check(result.assessment().orElseThrow().assignments().containsKey(AIRCRAFT),
                    "result snapshot changed after caller mutation");
        }
        System.out.println("PASS " + scenario + " snapshot_sha256=" + result.contentSha256());
    }

    private static CompoundTag validRoot() {
        CompoundTag entry = new CompoundTag();
        entry.putUUID("aircraft_id", AIRCRAFT);
        entry.putLong("revision", 7L);
        entry.put("order", MissionOrderCodec.write(order()));
        ListTag assignments = new ListTag();
        assignments.add(entry);
        CompoundTag data = new CompoundTag();
        data.put("assignments", assignments);
        CompoundTag root = new CompoundTag();
        root.put("data", data);
        return root;
    }

    private static MissionOrder order() {
        return MissionOrder.builder(MissionOrder.Type.CAP).orderId(ORDER).weaponsFree(true).build();
    }

    private static byte[] encode(CompoundTag root, boolean gzip) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        if (gzip) NbtIo.writeCompressed(root, out);
        else NbtIo.write(root, (DataOutput) new DataOutputStream(out));
        return out.toByteArray();
    }

    private static String hash(byte[] bytes) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
    }

    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
