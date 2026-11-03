package com.wwdebug.benchmark;

import java.util.List;

/** Exact test selection for the isolated natural-tick probe. */
final class BenchmarkNaturalTickRegistration {
    record TestId(String name, String batch, String structure) { }
    private static final TestId EXPECTED = new TestId("benchmarkstopnaturalrespectsplayer",
            "benchmark_player_stop_natural_probe_only", "wwdebug_benchmark_stop_natural_probe:empty");

    static boolean isExpected(List<TestId> selected) {
        return selected != null && selected.size() == 1 && EXPECTED.equals(selected.get(0));
    }
}
