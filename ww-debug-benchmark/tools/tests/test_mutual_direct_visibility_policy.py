"""Pure guard and sparse-output policy checks for the direct visibility probe."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[2] / (
    "src/main/java/com/wwdebug/autopilot/MutualTicketObservationPolicy.java")
HARNESS = r"""
package com.wwdebug.autopilot;

public final class DirectVisibilityPolicyHarness {
    private static void check(boolean ok, String reason) {
        if (!ok) throw new AssertionError(reason);
    }
    public static void main(String[] args) throws Exception {
        java.lang.reflect.Method gate;
        java.lang.reflect.Method fingerprint;
        java.lang.reflect.Method valid;
        try {
            gate = MutualTicketObservationPolicy.class.getDeclaredMethod("directVisibilityEnabled",
                    boolean.class, String.class, boolean.class, String.class, String.class);
            fingerprint = MutualTicketObservationPolicy.class.getDeclaredMethod("directVisibilityFingerprint",
                    String.class, String.class, Boolean.class, Boolean.class, boolean.class);
            valid = MutualTicketObservationPolicy.class.getDeclaredMethod("directVisibilityAtTicks",
                    Boolean.class, Long.class, Long.class);
        } catch (NoSuchMethodException missing) {
            throw new AssertionError("direct visibility version guard and fingerprint must exist", missing);
        }
        for (Object[] values : new Object[][] {
            {false, "true", true, "1.20.1", "47.4.20", false},
            {true, null, true, "1.20.1", "47.4.20", false},
            {true, "TRUE", true, "1.20.1", "47.4.20", false},
            {true, "true", false, "1.20.1", "47.4.20", false},
            {true, "true", true, "1.20.2", "47.4.20", false},
            {true, "true", true, "1.20.1", "47.4.21", false},
            {true, "true", true, null, "47.4.20", false},
            {true, "true", true, "1.20.1", null, false},
            {true, "true", true, "1.20.1", "47.4.20", true}
        }) {
            check(values[5].equals(gate.invoke(null, values[0], values[1], values[2], values[3], values[4])),
                  "guard " + java.util.Arrays.toString(values));
        }
        String a = (String) fingerprint.invoke(null, "base", "supported", true, false, false);
        String b = (String) fingerprint.invoke(null, "base", "supported", true, false, false);
        String changed = (String) fingerprint.invoke(null, "base", "supported", false, false, false);
        String unknown = (String) fingerprint.invoke(null, "base", "unsupported", null, null, false);
        check(!MutualTicketObservationPolicy.emit(a, b, 21), "unchanged states quiet");
        check(MutualTicketObservationPolicy.emit(a, b, 20), "heartbeat preserved");
        check(MutualTicketObservationPolicy.emit(a, changed, 21), "changed direct result emits");
        check(unknown.contains("direct_before=unknown") && unknown.contains("direct_after=unknown"),
              "unsupported or unavailable must not appear false");
        check(Boolean.FALSE.equals(valid.invoke(null, false, 20L, 20L)), "same-tick false retained");
        check(Boolean.TRUE.equals(valid.invoke(null, true, 20L, 20L)), "same-tick true retained");
        check(valid.invoke(null, true, 20L, 21L) == null, "different ticks unknown");
        check(valid.invoke(null, false, null, 20L) == null, "missing tick unknown");
        check(valid.invoke(null, false, -1L, -1L) == null, "negative tick unknown");
    }
}
"""


class MutualDirectVisibilityPolicyTests(unittest.TestCase):
    def test_explicit_gate_versions_and_sparse_output(self):
        javac, java = shutil.which("javac"), shutil.which("java")
        if not javac or not java:
            self.skipTest("JDK 17 is required")
        with tempfile.TemporaryDirectory() as work:
            harness = Path(work) / "DirectVisibilityPolicyHarness.java"
            harness.write_text(HARNESS, encoding="utf-8")
            subprocess.run([javac, "--release", "17", "-d", work, str(SOURCE), str(harness)],
                           check=True, capture_output=True, text=True)
            result = subprocess.run([java, "-cp", work, "com.wwdebug.autopilot.DirectVisibilityPolicyHarness"],
                                    check=False, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
