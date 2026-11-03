package com.wwdebug.benchmark;

import java.util.HashSet;
import java.util.Set;

/** JDK-only contract for the fixed GameTest structure's forced-chunk footprint. */
public final class BenchmarkProbeForcedChunksTest {
    public static void main(String[] args) {
        Set<BenchmarkProbeForcedChunks.Chunk> expected = BenchmarkProbeForcedChunks.expected(-1, -3);
        check(expected.size() == 25, "exactly 25 chunks");
        for (int x = -2; x <= 2; x++) {
            for (int z = -4; z <= 0; z++) {
                check(expected.contains(new BenchmarkProbeForcedChunks.Chunk(x, z)), "expected coordinate missing");
            }
        }
        check(BenchmarkProbeForcedChunks.matches(-1, -3, expected), "exact footprint accepted");
        Set<BenchmarkProbeForcedChunks.Chunk> missing = new HashSet<>(expected);
        missing.remove(new BenchmarkProbeForcedChunks.Chunk(-2, -4));
        check(!BenchmarkProbeForcedChunks.matches(-1, -3, missing), "missing chunk rejected");
        Set<BenchmarkProbeForcedChunks.Chunk> extra = new HashSet<>(expected);
        extra.add(new BenchmarkProbeForcedChunks.Chunk(-3, -4));
        check(!BenchmarkProbeForcedChunks.matches(-1, -3, extra), "extra chunk rejected");
        Set<BenchmarkProbeForcedChunks.Chunk> substituted = new HashSet<>(missing);
        substituted.add(new BenchmarkProbeForcedChunks.Chunk(-3, -4));
        check(!BenchmarkProbeForcedChunks.matches(-1, -3, substituted), "same-size substitute rejected");
        check(!BenchmarkProbeForcedChunks.matches(0, -3, expected), "different center rejected");
        System.out.println("BenchmarkProbeForcedChunksTest PASS");
    }

    private static void check(boolean result, String message) {
        if (!result) throw new AssertionError(message);
    }
}
