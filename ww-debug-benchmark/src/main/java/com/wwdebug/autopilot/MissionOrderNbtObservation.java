package com.wwdebug.autopilot;

import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.NbtAccounter;
import net.minecraft.nbt.NbtIo;
import net.minecraft.nbt.Tag;

import java.io.ByteArrayInputStream;
import java.io.DataInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Objects;
import java.util.Optional;
import java.util.zip.GZIPInputStream;

/**
 * Diagnostic assessment of caller-provided NBT bytes; this class never accesses a file or server.
 * The caller must exclusively own the input until inspect returns. The hash and result
 * describe that copy, not a path, current storage contents, restore state or weapon permission.
 * This intentionally does not run the server's DataFixer or claim equivalent loader behavior.
 */
public final class MissionOrderNbtObservation {
    static final int MAX_BYTES = 4 * 1024 * 1024;

    public enum Status { INVALID, TOO_LARGE, UNVERIFIED, ASSESSED_CLEAN, ASSESSED_UNKNOWN }

    public static final class Result {
        private final Status status;
        private final String contentSha256;
        private final Optional<MissionOrderLoadAssessment.Result> assessment;

        private Result(Status status, String contentSha256,
                       Optional<MissionOrderLoadAssessment.Result> assessment) {
            this.status = status;
            this.contentSha256 = contentSha256;
            this.assessment = assessment;
        }

        public Status status() { return status; }
        /** SHA-256 of the full captured bytes, or null if input exceeds the capture limit. */
        public String contentSha256() { return contentSha256; }
        public Optional<MissionOrderLoadAssessment.Result> assessment() { return assessment; }
    }

    private MissionOrderNbtObservation() { }

    public static Result inspect(byte[] input) {
        return inspect(input, () -> { });
    }

    /** Package-private test hook runs after the input copy and before its evaluation. */
    static Result inspect(byte[] input, Runnable afterSnapshot) {
        Objects.requireNonNull(input, "input");
        Objects.requireNonNull(afterSnapshot, "afterSnapshot");
        if (input.length > MAX_BYTES) {
            return result(Status.TOO_LARGE, null);
        }
        byte[] captured = input.clone();
        afterSnapshot.run();
        String hash = sha256(captured);
        try {
            byte[] nbt = captured;
            if (captured.length >= 2 && (captured[0] & 0xff) == 0x1f && (captured[1] & 0xff) == 0x8b) {
                try (InputStream gzip = new GZIPInputStream(new ByteArrayInputStream(captured))) {
                    nbt = gzip.readNBytes(MAX_BYTES + 1);
                }
                if (nbt.length > MAX_BYTES) {
                    return result(Status.TOO_LARGE, hash);
                }
            }
            try (DataInputStream stream = new DataInputStream(new ByteArrayInputStream(nbt))) {
                CompoundTag root = NbtIo.read(stream, new NbtAccounter(MAX_BYTES));
                if (stream.read() != -1 || !root.contains("data", Tag.TAG_COMPOUND)) {
                    return result(Status.INVALID, hash);
                }
                MissionOrderLoadAssessment.Result assessment =
                        MissionOrderLoadAssessment.assess(root.getCompound("data"));
                Status status = assessment.status() == MissionOrderLoadAssessment.Status.CLEAN
                        ? Status.ASSESSED_CLEAN : Status.ASSESSED_UNKNOWN;
                return new Result(status, hash, Optional.of(assessment));
            }
        } catch (IOException exception) {
            return result(Status.INVALID, hash);
        } catch (RuntimeException exception) {
            // The mapped NBT reader can report quota exhaustion as a runtime exception.
            return result(Status.UNVERIFIED, hash);
        }
    }

    private static Result result(Status status, String hash) {
        return new Result(status, hash, Optional.empty());
    }

    private static String sha256(byte[] bytes) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 unavailable", exception);
        }
    }
}
