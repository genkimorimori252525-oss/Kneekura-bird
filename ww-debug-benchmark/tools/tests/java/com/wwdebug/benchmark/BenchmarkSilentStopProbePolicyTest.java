package com.wwdebug.benchmark;

import java.util.List;

/** JDK-only checks for the isolated stop probe's selection and session guard. */
public final class BenchmarkSilentStopProbePolicyTest {
    public static void main(String[] args) {
        var expected = new BenchmarkSilentStopProbePolicy.TestId("benchmarksilentstoprespectsplayer",
                "benchmark_player_silent_stop_probe_only", "wwdebug_benchmark_silent_stop_probe:empty");
        check(BenchmarkSilentStopProbePolicy.isExpected(List.of(expected)), "dedicated test accepted");
        check(!BenchmarkSilentStopProbePolicy.isExpected(List.of()), "zero tests unverified");
        check(!BenchmarkSilentStopProbePolicy.isExpected(List.of(expected, expected)), "multiple tests rejected");
        check(!BenchmarkSilentStopProbePolicy.isExpected(List.of(new BenchmarkSilentStopProbePolicy.TestId(
                "other.benchmarksilentstoprespectsplayer", expected.batch(), expected.structure()))), "similar test rejected");
        check(!BenchmarkSilentStopProbePolicy.isExpected(List.of(new BenchmarkSilentStopProbePolicy.TestId(
                expected.name(), "wrong_batch", expected.structure()))), "wrong batch rejected");
        check(!BenchmarkSilentStopProbePolicy.isExpected(List.of(new BenchmarkSilentStopProbePolicy.TestId(
                expected.name(), expected.batch(), "other:empty"))), "wrong structure rejected");
        Object ours = new Object(), other = new Object();
        check(BenchmarkSilentStopProbePolicy.mayStop(ours, ours), "own registered session allowed");
        check(!BenchmarkSilentStopProbePolicy.mayStop(ours, other), "other session must not be stopped");
        check(!BenchmarkSilentStopProbePolicy.mayStop(ours, null), "missing session must not be stopped");
        check(!BenchmarkSilentStopProbePolicy.mayStop(null, null), "unknown identity must not be stopped");
        System.out.println("BenchmarkSilentStopProbePolicyTest PASS");
    }
    private static void check(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }
}
