package com.wwdebug.benchmark;

import java.util.ArrayList;
import java.util.List;

/** JDK-only checks for the isolated GameTest cleanup collector. */
public final class BenchmarkProbeCleanupTest {
    public static void main(String[] args) {
        List<String> ran = new ArrayList<>();
        RuntimeException primary = new RuntimeException("primary");
        RuntimeException dismount = new RuntimeException("dismount");
        RuntimeException chunkQuery = new RuntimeException("chunk query unknown");
        BenchmarkProbeCleanup cleanup = new BenchmarkProbeCleanup();
        cleanup.run("dismount", () -> { ran.add("dismount"); throw dismount; });
        cleanup.run("abort", () -> ran.add("abort"));
        cleanup.run("chunk_query", () -> { ran.add("chunk_query"); throw chunkQuery; });
        cleanup.run("report", () -> ran.add("report"));
        check(ran.equals(List.of("dismount", "abort", "chunk_query", "report")), "all actions run");
        check(cleanup.failures().size() == 2, "both cleanup failures recorded");
        check(cleanup.combine(primary) == primary, "primary preserved");
        check(List.of(primary.getSuppressed()).equals(List.of(dismount, chunkQuery)),
                "cleanup failures suppressed in order");
        BenchmarkProbeCleanup noPrimary = new BenchmarkProbeCleanup();
        noPrimary.run("only", () -> { throw dismount; });
        check(noPrimary.combine(null) == dismount, "cleanup-only failure remains failure");
        BenchmarkProbeCleanup noFailure = new BenchmarkProbeCleanup();
        noFailure.run("ok", () -> {});
        check(noFailure.combine(null) == null, "success stays successful");
        BenchmarkProbeCleanup repeated = new BenchmarkProbeCleanup();
        repeated.run("same", () -> { throw primary; });
        check(repeated.combine(primary) == primary, "same throwable does not self-suppress");
        System.out.println("BenchmarkProbeCleanupTest PASS");
    }

    private static void check(boolean result, String message) {
        if (!result) throw new AssertionError(message);
    }
}
