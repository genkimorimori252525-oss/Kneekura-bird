package com.wwdebug.benchmark;

import java.util.Arrays;
import java.util.List;

/** JDK-only checks for exact selection of the natural-tick GameTest. */
public final class BenchmarkNaturalTickRegistrationTest {
    public static void main(String[] args) {
        var expected = new BenchmarkNaturalTickRegistration.TestId("benchmarkstopnaturalrespectsplayer",
                "benchmark_player_stop_natural_probe_only", "wwdebug_benchmark_stop_natural_probe:empty");
        check(BenchmarkNaturalTickRegistration.isExpected(List.of(expected)), "expected registration accepted");
        check(!BenchmarkNaturalTickRegistration.isExpected(null), "null list rejected");
        check(!BenchmarkNaturalTickRegistration.isExpected(List.of()), "zero tests rejected");
        check(!BenchmarkNaturalTickRegistration.isExpected(Arrays.asList((BenchmarkNaturalTickRegistration.TestId) null)),
                "null item rejected");
        check(!BenchmarkNaturalTickRegistration.isExpected(List.of(expected, expected)), "duplicate registration rejected");
        check(!BenchmarkNaturalTickRegistration.isExpected(List.of(new BenchmarkNaturalTickRegistration.TestId(
                "other.benchmarkstopnaturalrespectsplayer", expected.batch(), expected.structure()))), "similar name rejected");
        check(!BenchmarkNaturalTickRegistration.isExpected(List.of(new BenchmarkNaturalTickRegistration.TestId(
                null, expected.batch(), expected.structure()))), "null name rejected");
        check(!BenchmarkNaturalTickRegistration.isExpected(List.of(new BenchmarkNaturalTickRegistration.TestId(
                expected.name(), "wrong_batch", expected.structure()))), "wrong batch rejected");
        check(!BenchmarkNaturalTickRegistration.isExpected(List.of(new BenchmarkNaturalTickRegistration.TestId(
                expected.name(), expected.batch(), "other:empty"))), "wrong structure rejected");
        System.out.println("BenchmarkNaturalTickRegistrationTest PASS");
    }
    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
