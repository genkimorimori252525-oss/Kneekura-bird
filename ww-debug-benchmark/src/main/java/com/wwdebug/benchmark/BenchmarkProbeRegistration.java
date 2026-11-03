package com.wwdebug.benchmark;

import java.util.List;

/** Exact registration expected from this test's unprefixed Forge GameTest annotation. */
final class BenchmarkProbeRegistration {
    record TestId(String name, String batch, String structure) { }

    static boolean isExpected(List<TestId> tests) {
        if (tests.size() != 1 || tests.get(0) == null) return false;
        TestId test = tests.get(0);
        return "benchmarkphaseresetrespectsplayer".equals(test.name())
                && "benchmark_player_reset_probe_only".equals(test.batch())
                && "wwdebug_benchmark_reset_probe:empty".equals(test.structure());
    }
}
