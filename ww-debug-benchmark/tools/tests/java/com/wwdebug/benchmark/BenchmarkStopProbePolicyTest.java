package com.wwdebug.benchmark;

import java.util.List;

/** JDK-only checks for the isolated stop probe's selection and session guard. */
public final class BenchmarkStopProbePolicyTest {
    public static void main(String[] args) {
        var expected = new BenchmarkStopProbePolicy.TestId("benchmarkstoprespectsplayer",
                "benchmark_player_stop_probe_only", "wwdebug_benchmark_stop_probe:empty");
        check(BenchmarkStopProbePolicy.isExpected(List.of(expected)), "dedicated test accepted");
        check(!BenchmarkStopProbePolicy.isExpected(List.of()), "zero tests unverified");
        check(!BenchmarkStopProbePolicy.isExpected(List.of(expected, expected)), "multiple tests rejected");
        check(!BenchmarkStopProbePolicy.isExpected(List.of(new BenchmarkStopProbePolicy.TestId(
                "other.benchmarkstoprespectsplayer", expected.batch(), expected.structure()))), "similar test rejected");
        check(!BenchmarkStopProbePolicy.isExpected(List.of(new BenchmarkStopProbePolicy.TestId(
                expected.name(), "wrong_batch", expected.structure()))), "wrong batch rejected");
        check(!BenchmarkStopProbePolicy.isExpected(List.of(new BenchmarkStopProbePolicy.TestId(
                expected.name(), expected.batch(), "other:empty"))), "wrong structure rejected");
        Object ours = new Object(), other = new Object();
        check(BenchmarkStopProbePolicy.mayStop(ours, ours), "own registered session allowed");
        check(!BenchmarkStopProbePolicy.mayStop(ours, other), "other session must not be stopped");
        check(!BenchmarkStopProbePolicy.mayStop(ours, null), "missing session must not be stopped");
        check(!BenchmarkStopProbePolicy.mayStop(null, null), "unknown identity must not be stopped");
        System.out.println("BenchmarkStopProbePolicyTest PASS");
    }
    private static void check(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }
}
