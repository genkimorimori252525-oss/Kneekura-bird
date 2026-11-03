package com.wwdebug.benchmark;

import java.util.List;

/** Selection and identity guards for the disposable-world stop probe. */
final class BenchmarkSilentStopProbePolicy {
    record TestId(String name, String batch, String structure) { }
    private static final TestId EXPECTED = new TestId("benchmarksilentstoprespectsplayer",
            "benchmark_player_silent_stop_probe_only", "wwdebug_benchmark_silent_stop_probe:empty");
    static boolean isExpected(List<TestId> selected) {
        return selected.size() == 1 && EXPECTED.equals(selected.get(0));
    }
    static boolean mayStop(Object owned, Object current) {
        return owned != null && owned == current;
    }
}
