package com.wwdebug.benchmark;

/**
 * Test-fixture evidence for consecutive server END observations of one benchmark session.
 * An entity tick-count increment establishes a scheduler visit only; it does not prove
 * canUpdate, aircraft physics execution, or a continuous trajectory.
 * Create a separate instance for each observation interval.
 */
final class BenchmarkNaturalTickPolicy {
    record Sample(long index, int serverTick, long gameTime, int entityTick, long elapsed) {
    }

    private Sample previousPost;
    private int transitions;
    private boolean failed;

    /** Accept one pre/post pair from the same server END event; failures are permanent. */
    boolean accept(Sample pre, Sample post) {
        if (failed) {
            return false;
        }
        if (pre == null || post == null || !nonnegative(pre) || !nonnegative(post)
                || pre.index() != post.index()
                || pre.serverTick() != post.serverTick()
                || pre.gameTime() != post.gameTime()
                || pre.entityTick() != post.entityTick()
                || !next(pre.elapsed(), post.elapsed())) {
            failed = true;
            return false;
        }
        if (previousPost != null) {
            if (!next(previousPost.index(), pre.index())
                    || !next(previousPost.serverTick(), pre.serverTick())
                    || !next(previousPost.gameTime(), pre.gameTime())
                    || !next(previousPost.entityTick(), pre.entityTick())
                    || previousPost.elapsed() != pre.elapsed()) {
                failed = true;
                return false;
            }
            if (transitions < 2) {
                transitions++;
            }
        }
        previousPost = post;
        return true;
    }

    /** A baseline pair and at least two further consecutive pairs are required. */
    boolean complete() {
        return !failed && transitions >= 2;
    }

    static boolean finiteValues(double... values) {
        if (values == null || values.length != 10) return false;
        for (double value : values) if (!Double.isFinite(value)) return false;
        return true;
    }

    private static boolean nonnegative(Sample sample) {
        return sample.index() >= 0 && sample.serverTick() >= 0 && sample.gameTime() >= 0
                && sample.entityTick() >= 0 && sample.elapsed() >= 0;
    }

    private static boolean next(long previous, long current) {
        return previous != Long.MAX_VALUE && current == previous + 1;
    }
}
