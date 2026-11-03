"""Pure tests for the read-only, opt-in force-loop observation policy."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[2] / (
    "src/main/java/com/wwdebug/autopilot/MutualTicketObservationPolicy.java")
HARNESS = r"""
package com.wwdebug.autopilot;

public final class TicketObservationHarness {
    private static void check(boolean value, String reason) {
        if (!value) throw new AssertionError(reason);
    }
    public static void main(String[] args) {
        String s = "dogfight_mutual", a = "warfare_wings:a6m";
        check(!MutualTicketObservationPolicy.enabled(true, s, a, a, null), "unset flag");
        check(!MutualTicketObservationPolicy.enabled(false, s, a, a, "true"), "not GameTest");
        check(!MutualTicketObservationPolicy.enabled(true, "full", a, a, "true"), "wrong scenario");
        check(!MutualTicketObservationPolicy.enabled(true, s, "all", a, "true"), "wrong config");
        check(!MutualTicketObservationPolicy.enabled(true, s, a, "warfare_wings:p47n", "true"), "wrong entity");
        check(!MutualTicketObservationPolicy.enabled(true, s, a, null, "true"), "unknown entity");
        check(MutualTicketObservationPolicy.enabled(true, s, a, a, "true"), "explicit opt-in");
        check("unknown".equals(MutualTicketObservationPolicy.state(null)), "unknown differs from false");
        check("false".equals(MutualTicketObservationPolicy.state(false)), "known false");
        check("unknown".equals(MutualTicketObservationPolicy.action(false, false, null, null)), "incomplete loop");
        check("not_encountered".equals(MutualTicketObservationPolicy.action(false, true, null, null)), "outside grid");
        check("already_forced".equals(MutualTicketObservationPolicy.action(true, true, true, null)), "already forced");
        check("attempt_incomplete".equals(MutualTicketObservationPolicy.action(true, false, false, null)), "no return");
        check("attempt_returned_true".equals(MutualTicketObservationPolicy.action(true, true, false, true)), "true result");
        check("attempt_returned_false".equals(MutualTicketObservationPolicy.action(true, true, false, false)), "false result");
        check(MutualTicketObservationPolicy.emit(null, "a", 1), "first sample");
        check(!MutualTicketObservationPolicy.emit("a", "a", 19), "unchanged not heartbeat");
        check(MutualTicketObservationPolicy.emit("a", "a", 20), "periodic heartbeat");
        check(MutualTicketObservationPolicy.emit("a", "b", 21), "changed state");
    }
}
"""


class MutualTicketObservationPolicyTests(unittest.TestCase):
    def test_gate_unknown_action_and_change_cadence(self):
        self.assertTrue(SOURCE.is_file(), "the force-loop observation policy must exist")
        javac, java = shutil.which("javac"), shutil.which("java")
        if not javac or not java:
            self.skipTest("JDK 17 is required")
        with tempfile.TemporaryDirectory() as work:
            harness = Path(work) / "TicketObservationHarness.java"
            harness.write_text(HARNESS, encoding="utf-8")
            subprocess.run([javac, "--release", "17", "-d", work, str(SOURCE), str(harness)],
                           check=True, capture_output=True, text=True)
            result = subprocess.run([java, "-cp", work, "com.wwdebug.autopilot.TicketObservationHarness"],
                                    check=False, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
