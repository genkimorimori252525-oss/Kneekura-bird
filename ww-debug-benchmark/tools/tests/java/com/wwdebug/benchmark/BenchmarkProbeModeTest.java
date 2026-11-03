package com.wwdebug.benchmark;

/** JDK-only contract for the explicit direct-call test mode. */
public final class BenchmarkProbeModeTest {
    public static void main(String[] args) {
        check(BenchmarkProbeMode.parse(null) == BenchmarkProbeMode.RESET, "default must remain reset");
        check(BenchmarkProbeMode.parse("reset") == BenchmarkProbeMode.RESET, "explicit reset");
        check(BenchmarkProbeMode.parse("direct") == BenchmarkProbeMode.DIRECT, "explicit direct");
        for (String value : new String[] {"", "DIRECT", "direct ", "other"}) {
            try {
                BenchmarkProbeMode.parse(value);
                throw new AssertionError("unknown mode accepted: " + value);
            } catch (IllegalArgumentException expected) { }
        }
        System.out.println("BenchmarkProbeModeTest PASS");
    }
    private static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }
}
