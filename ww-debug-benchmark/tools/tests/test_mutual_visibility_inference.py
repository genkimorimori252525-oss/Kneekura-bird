"""Pure checks for the additional opt-in, non-atomic visibility inference."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[2] / (
    "src/main/java/com/wwdebug/autopilot/MutualTicketObservationPolicy.java")
HARNESS = r"""
package com.wwdebug.autopilot;

public final class VisibilityInferenceHarness {
    private static void check(boolean ok, String reason) {
        if (!ok) throw new AssertionError(reason);
    }
    public static void main(String[] args) throws Exception {
        java.lang.reflect.Method visibility;
        java.lang.reflect.Method enabled;
        try {
            visibility = MutualTicketObservationPolicy.class.getDeclaredMethod("visibility", Boolean.class, Boolean.class);
            enabled = MutualTicketObservationPolicy.class.getDeclaredMethod("visibilityEnabled", String.class);
        } catch (NoSuchMethodException missing) {
            throw new AssertionError("visibility inference and its explicit flag must exist", missing);
        }
        check(!(Boolean) enabled.invoke(null, new Object[] {null}), "unset flag disabled");
        check(!(Boolean) enabled.invoke(null, "false"), "false flag disabled");
        check(!(Boolean) enabled.invoke(null, "TRUE"), "flag is exact");
        check((Boolean) enabled.invoke(null, "true"), "explicit true enabled");
        for (Object[] test : new Object[][] {
            {Boolean.TRUE, Boolean.TRUE, "true_if_stable"},
            {Boolean.TRUE, Boolean.FALSE, "false_if_stable"},
            {Boolean.FALSE, Boolean.FALSE, "unknown"},
            {Boolean.FALSE, Boolean.TRUE, "changed_or_inconsistent"},
            {null, Boolean.TRUE, "unknown"}, {Boolean.TRUE, null, "unknown"},
            {null, null, "unknown"}
        }) {
            check(test[2].equals(visibility.invoke(null, test[0], test[1])), "visibility " + java.util.Arrays.toString(test));
        }
        java.lang.reflect.Method atTicks;
        try {
            atTicks = MutualTicketObservationPolicy.class.getDeclaredMethod("visibilityAtTicks",
                    Boolean.class, Boolean.class, Long.class, Long.class);
        } catch (NoSuchMethodException missing) {
            throw new AssertionError("query tick mismatch must make inference unknown", missing);
        }
        check("false_if_stable".equals(atTicks.invoke(null, true, false, 20L, 20L)), "same tick is conditional");
        check("unknown".equals(atTicks.invoke(null, true, false, 20L, 21L)), "different ticks unknown");
        check("unknown".equals(atTicks.invoke(null, true, false, null, 20L)), "missing tick unknown");
        check("unknown".equals(atTicks.invoke(null, true, false, -1L, -1L)), "negative ticks unknown");
        java.lang.reflect.Method fingerprint;
        try {
            fingerprint = MutualTicketObservationPolicy.class.getDeclaredMethod("visibilityFingerprint",
                    String.class, Boolean.class, Boolean.class, String.class,
                    Boolean.class, String.class, boolean.class);
        } catch (NoSuchMethodException missing) {
            throw new AssertionError("fingerprint must contain only visibility state", missing);
        }
        String first = (String) fingerprint.invoke(null, "base", true, false, "false_if_stable", true, "true_if_stable", false);
        String same = (String) fingerprint.invoke(null, "base", true, false, "false_if_stable", true, "true_if_stable", false);
        String changed = (String) fingerprint.invoke(null, "base", true, true, "true_if_stable", true, "true_if_stable", false);
        check(!MutualTicketObservationPolicy.emit(first, same, 21), "unchanged fingerprint stays quiet");
        check(MutualTicketObservationPolicy.emit(first, same, 20), "unchanged fingerprint heartbeat");
        check(MutualTicketObservationPolicy.emit(first, changed, 21), "changed visibility emits");
        check(MutualTicketObservationPolicy.emit("v=unknown", "v=false_if_stable", 21),
              "visibility transition must emit even outside heartbeat");
        check(!MutualTicketObservationPolicy.emit("v=unknown", "v=unknown", 21), "unchanged is quiet");
    }
}
"""


class MutualVisibilityInferenceTests(unittest.TestCase):
    def test_exact_flag_and_non_atomic_truth_table(self):
        javac, java = shutil.which("javac"), shutil.which("java")
        if not javac or not java:
            self.skipTest("JDK 17 is required")
        with tempfile.TemporaryDirectory() as work:
            harness = Path(work) / "VisibilityInferenceHarness.java"
            harness.write_text(HARNESS, encoding="utf-8")
            subprocess.run([javac, "--release", "17", "-d", work, str(SOURCE), str(harness)],
                           check=True, capture_output=True, text=True)
            result = subprocess.run([java, "-cp", work, "com.wwdebug.autopilot.VisibilityInferenceHarness"],
                                    check=False, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
