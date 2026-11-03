package com.wwdebug.benchmark;

import java.util.List;

/** JDK-only regression for selecting the sole dedicated GameTest. */
public final class BenchmarkProbeRegistrationTest {
    private static final BenchmarkProbeRegistration.TestId EXPECTED = new BenchmarkProbeRegistration.TestId(
            "benchmarkphaseresetrespectsplayer", "benchmark_player_reset_probe_only",
            "wwdebug_benchmark_reset_probe:empty");

    public static void main(String[] args) {
        check(BenchmarkProbeRegistration.isExpected(List.of(EXPECTED)), "observed v3 name is accepted");
        check(!BenchmarkProbeRegistration.isExpected(List.of()), "zero tests are rejected");
        check(!BenchmarkProbeRegistration.isExpected(List.of(EXPECTED, EXPECTED)), "multiple tests are rejected");
        reject("other_test", EXPECTED.batch(), EXPECTED.structure());
        reject("other.benchmarkphaseresetrespectsplayer", EXPECTED.batch(), EXPECTED.structure());
        reject(EXPECTED.name(), "another_batch", EXPECTED.structure());
        reject(EXPECTED.name(), EXPECTED.batch(), "another:empty");
        reject(null, EXPECTED.batch(), EXPECTED.structure());
        System.out.println("BenchmarkProbeRegistrationTest PASS");
    }

    private static void reject(String name, String batch, String structure) {
        check(!BenchmarkProbeRegistration.isExpected(List.of(
                new BenchmarkProbeRegistration.TestId(name, batch, structure))), "incorrect test rejected");
    }

    private static void check(boolean result, String message) {
        if (!result) throw new AssertionError(message);
    }
}
