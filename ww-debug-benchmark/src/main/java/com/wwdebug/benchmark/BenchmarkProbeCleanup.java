package com.wwdebug.benchmark;

import java.util.ArrayList;
import java.util.List;

/** Test-only collector: cleanup failures must not prevent later cleanup or replace the test error. */
final class BenchmarkProbeCleanup {
    @FunctionalInterface
    interface Action { void run() throws Throwable; }
    record Failure(String step, Throwable error) { }

    private final List<Failure> failures = new ArrayList<>();

    void run(String step, Action action) {
        try {
            action.run();
        } catch (Throwable failure) {
            failures.add(new Failure(step, failure));
        }
    }

    List<Failure> failures() { return List.copyOf(failures); }

    Throwable combine(Throwable primary) {
        Throwable result = primary;
        for (Failure failure : failures) {
            if (result == null) result = failure.error();
            else if (failure.error() != result) result.addSuppressed(failure.error());
        }
        return result;
    }
}
