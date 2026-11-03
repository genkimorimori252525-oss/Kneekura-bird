package com.wwdebug.benchmark;

import java.util.List;

/** JDK-only checks for the isolated stop probe's selection and session guard. */
public final class BenchmarkStopRefusalProbePolicyTest {
    public static void main(String[] args) {
        var expected = new BenchmarkStopRefusalProbePolicy.TestId("benchmarkstoprefusalsuspendsplayer",
                "benchmark_player_stop_refusal_probe_only", "wwdebug_benchmark_stop_refusal_probe:empty");
        check(BenchmarkStopRefusalProbePolicy.isExpected(List.of(expected)), "dedicated test accepted");
        check(!BenchmarkStopRefusalProbePolicy.isExpected(List.of()), "zero tests unverified");
        check(!BenchmarkStopRefusalProbePolicy.isExpected(List.of(expected, expected)), "multiple tests rejected");
        check(!BenchmarkStopRefusalProbePolicy.isExpected(List.of(new BenchmarkStopRefusalProbePolicy.TestId(
                "other.benchmarkstoprefusalsuspendsplayer", expected.batch(), expected.structure()))), "similar test rejected");
        check(!BenchmarkStopRefusalProbePolicy.isExpected(List.of(new BenchmarkStopRefusalProbePolicy.TestId(
                expected.name(), "wrong_batch", expected.structure()))), "wrong batch rejected");
        check(!BenchmarkStopRefusalProbePolicy.isExpected(List.of(new BenchmarkStopRefusalProbePolicy.TestId(
                expected.name(), expected.batch(), "other:empty"))), "wrong structure rejected");
        Object ours = new Object(), other = new Object();
        check(BenchmarkStopRefusalProbePolicy.mayStop(ours, ours), "own registered session allowed");
        check(!BenchmarkStopRefusalProbePolicy.mayStop(ours, other), "other session must not be stopped");
        check(!BenchmarkStopRefusalProbePolicy.mayStop(ours, null), "missing session must not be stopped");
        check(!BenchmarkStopRefusalProbePolicy.mayStop(null, null), "unknown identity must not be stopped");
        System.out.println("BenchmarkStopRefusalProbePolicyTest PASS");
    }
    private static void check(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }
}
