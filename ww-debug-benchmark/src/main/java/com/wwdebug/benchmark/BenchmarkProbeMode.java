package com.wwdebug.benchmark;

/** Test fixture mode; absence preserves the original reset scenario. */
enum BenchmarkProbeMode {
    RESET, DIRECT;

    static BenchmarkProbeMode parse(String input) {
        if (input == null || input.equals("reset")) return RESET;
        if (input.equals("direct")) return DIRECT;
        throw new IllegalArgumentException("unknown benchmark player probe mode: " + input);
    }
}
