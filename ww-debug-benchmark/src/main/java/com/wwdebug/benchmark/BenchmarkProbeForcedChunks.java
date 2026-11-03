package com.wwdebug.benchmark;

import java.util.HashSet;
import java.util.Set;

/** Footprint of fixed Minecraft 1.20.1 StructureUtils.forceLoadChunks, not owner identity. */
final class BenchmarkProbeForcedChunks {
    record Chunk(int x, int z) implements Comparable<Chunk> {
        @Override public int compareTo(Chunk other) {
            int xOrder = Integer.compare(x, other.x);
            return xOrder != 0 ? xOrder : Integer.compare(z, other.z);
        }
    }

    static Set<Chunk> expected(int centerX, int centerZ) {
        Set<Chunk> result = new HashSet<>();
        for (int dx = -1; dx <= 3; dx++) {
            for (int dz = -1; dz <= 3; dz++) {
                result.add(new Chunk(centerX + dx, centerZ + dz));
            }
        }
        return Set.copyOf(result);
    }

    static boolean matches(int centerX, int centerZ, Set<Chunk> actual) {
        return expected(centerX, centerZ).equals(actual);
    }
}
