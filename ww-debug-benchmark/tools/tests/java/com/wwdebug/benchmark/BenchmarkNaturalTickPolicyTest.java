package com.wwdebug.benchmark;

/** Run directly with JDK 17: exercises only the natural-tick evidence policy. */
public final class BenchmarkNaturalTickPolicyTest {
    private static final class Pair {
        final BenchmarkNaturalTickPolicy.Sample pre;
        final BenchmarkNaturalTickPolicy.Sample post;
        Pair(long index, int server, long time, int entity, long elapsed) {
            pre = new BenchmarkNaturalTickPolicy.Sample(index, server, time, entity, elapsed);
            post = new BenchmarkNaturalTickPolicy.Sample(index, server, time, entity, elapsed + 1);
        }
    }

    private static void check(boolean condition, String detail) {
        if (!condition) throw new AssertionError(detail);
    }

    private static BenchmarkNaturalTickPolicy.Sample sample(long i, int s, long t, int e, long l) {
        return new BenchmarkNaturalTickPolicy.Sample(i, s, t, e, l);
    }

    private static void pair(BenchmarkNaturalTickPolicy policy, long i, int s, long t, int e, long l) {
        Pair pair = new Pair(i, s, t, e, l);
        check(policy.accept(pair.pre, pair.post), "valid pair rejected");
    }

    private static void testThreePairsPerPhase() {
        for (int phase = 0; phase < 2; phase++) {
            BenchmarkNaturalTickPolicy policy = new BenchmarkNaturalTickPolicy();
            check(!policy.complete(), "empty phase accepted");
            pair(policy, 11, 90, 700, 30, 5);
            check(!policy.complete(), "baseline pair is not a natural transition");
            pair(policy, 12, 91, 701, 31, 6);
            check(!policy.complete(), "one transition is insufficient");
            pair(policy, 13, 92, 702, 32, 7);
            check(policy.complete(), "two transitions must establish phase continuity");
        }
    }

    private static void rejectsPair(BenchmarkNaturalTickPolicy.Sample pre,
                                    BenchmarkNaturalTickPolicy.Sample post, String what) {
        BenchmarkNaturalTickPolicy policy = new BenchmarkNaturalTickPolicy();
        check(!policy.accept(pre, post), what + " must fail");
        pairMustFailPermanently(policy);
    }

    private static void pairMustFailPermanently(BenchmarkNaturalTickPolicy policy) {
        Pair valid = new Pair(1, 1, 1, 1, 1);
        check(!policy.accept(valid.pre, valid.post), "invalid phase must remain failed");
        check(!policy.complete(), "invalid phase must not complete");
    }

    private static void testBadPairs() {
        var pre = sample(10, 20, 30, 40, 50);
        rejectsPair(null, sample(10, 20, 30, 40, 51), "missing pre");
        rejectsPair(pre, null, "missing post");
        rejectsPair(pre, sample(11, 20, 30, 40, 51), "different pair index");
        rejectsPair(pre, sample(10, 21, 30, 40, 51), "different server tick");
        rejectsPair(pre, sample(10, 20, 31, 40, 51), "different game time");
        rejectsPair(pre, sample(10, 20, 30, 41, 51), "different entity tick");
        for (long elapsed : new long[] {49, 50, 52})
            rejectsPair(pre, sample(10, 20, 30, 40, elapsed), "elapsed is not exactly +1");
        rejectsPair(sample(-1, 20, 30, 40, 50), sample(-1, 20, 30, 40, 51), "negative index");
        rejectsPair(sample(10, -1, 30, 40, 50), sample(10, -1, 30, 40, 51), "negative server tick");
        rejectsPair(sample(10, 20, -1, 40, 50), sample(10, 20, -1, 40, 51), "negative game time");
        rejectsPair(sample(10, 20, 30, -1, 50), sample(10, 20, 30, -1, 51), "negative entity tick");
        rejectsPair(sample(10, 20, 30, 40, -1), sample(10, 20, 30, 40, 0), "negative elapsed");
        rejectsPair(sample(10, 20, 30, 40, Long.MAX_VALUE),
                    sample(10, 20, 30, 40, Long.MIN_VALUE), "elapsed overflow");
    }

    private static void rejectsSecond(long index, int server, long time, int entity, long elapsed, String what) {
        BenchmarkNaturalTickPolicy policy = new BenchmarkNaturalTickPolicy();
        pair(policy, 10, 20, 30, 40, 50);
        Pair next = new Pair(index, server, time, entity, elapsed);
        check(!policy.accept(next.pre, next.post), what + " must fail");
        pairMustFailPermanently(policy);
    }

    private static void testMissingDuplicateReverseAndDiscontinuousTransitions() {
        rejectsSecond(10, 21, 31, 41, 51, "duplicate index");
        rejectsSecond(9, 21, 31, 41, 51, "reverse index");
        rejectsSecond(12, 21, 31, 41, 51, "missing index");
        rejectsSecond(11, 20, 31, 41, 51, "duplicate server tick");
        rejectsSecond(11, 19, 31, 41, 51, "reverse server tick");
        rejectsSecond(11, 22, 31, 41, 51, "missing server tick");
        rejectsSecond(11, 21, 30, 41, 51, "duplicate game time");
        rejectsSecond(11, 21, 29, 41, 51, "reverse game time");
        rejectsSecond(11, 21, 32, 41, 51, "missing game time");
        rejectsSecond(11, 21, 31, 40, 51, "duplicate entity visit");
        rejectsSecond(11, 21, 31, 39, 51, "reverse entity visit");
        rejectsSecond(11, 21, 31, 42, 51, "missing entity visit");
        rejectsSecond(11, 21, 31, 41, 50, "duplicate elapsed");
        rejectsSecond(11, 21, 31, 41, 52, "missing elapsed");
    }

    private static void testCounterOverflow() {
        BenchmarkNaturalTickPolicy s = new BenchmarkNaturalTickPolicy();
        pair(s, 10, Integer.MAX_VALUE, 30, 40, 50);
        check(!s.accept(sample(11, Integer.MIN_VALUE, 31, 41, 51),
                        sample(11, Integer.MIN_VALUE, 31, 41, 52)), "server tick overflow");
        BenchmarkNaturalTickPolicy e = new BenchmarkNaturalTickPolicy();
        pair(e, 10, 20, 30, Integer.MAX_VALUE, 50);
        check(!e.accept(sample(11, 21, 31, Integer.MIN_VALUE, 51),
                        sample(11, 21, 31, Integer.MIN_VALUE, 52)), "entity tick overflow");
        BenchmarkNaturalTickPolicy t = new BenchmarkNaturalTickPolicy();
        pair(t, 10, 20, Long.MAX_VALUE, 40, 50);
        check(!t.accept(sample(11, 21, Long.MIN_VALUE, 41, 51),
                        sample(11, 21, Long.MIN_VALUE, 41, 52)), "game time overflow");
        BenchmarkNaturalTickPolicy i = new BenchmarkNaturalTickPolicy();
        pair(i, Long.MAX_VALUE, 20, 30, 40, 50);
        check(!i.accept(sample(Long.MIN_VALUE, 21, 31, 41, 51),
                        sample(Long.MIN_VALUE, 21, 31, 41, 52)), "index overflow");
    }

    private static void testFiniteSnapshots() {
        check(!BenchmarkNaturalTickPolicy.finiteValues((double[]) null), "null snapshot accepted");
        check(!BenchmarkNaturalTickPolicy.finiteValues(1.0), "short snapshot accepted");
        double[] valid = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10};
        check(BenchmarkNaturalTickPolicy.finiteValues(valid), "finite snapshot rejected");
        for (int i = 0; i < valid.length; i++) {
            for (double invalid : new double[]{Double.NaN, Double.POSITIVE_INFINITY, Double.NEGATIVE_INFINITY}) {
                double[] values = valid.clone();
                values[i] = invalid;
                check(!BenchmarkNaturalTickPolicy.finiteValues(values), "nonfinite component accepted: " + i);
            }
        }
    }
    public static void main(String[] args) {
        testFiniteSnapshots();
        testThreePairsPerPhase();
        testBadPairs();
        testMissingDuplicateReverseAndDiscontinuousTransitions();
        testCounterOverflow();
        System.out.println("BenchmarkNaturalTickPolicyTest passed");
    }
}
