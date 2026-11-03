"""The opt-in observer policy is deterministic without starting Minecraft."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[2] / (
    "src/main/java/com/wwdebug/autopilot/MutualDogfightObservationPolicy.java")

HARNESS = r"""
package com.wwdebug.autopilot;

public final class ObservationPolicyHarness {
    private static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }
    public static void main(String[] args) {
        String scenario = "dogfight_mutual", target = "warfare_wings:a6m";
        try {
            var gate = MutualDogfightObservationPolicy.class.getDeclaredMethod("enabled", boolean.class,
                    String.class, String.class, String.class, String.class);
            check(!(Boolean) gate.invoke(null, true, scenario, target, "warfare_wings:p47n", "true"),
                  "configured A6M must not enable observation of a different entity type");
            check(!(Boolean) gate.invoke(null, true, scenario, target, null, "true"),
                  "an unavailable registry ID must not enable observation");
            check((Boolean) gate.invoke(null, true, scenario, target, target, "true"),
                  "matching actual A6M registry ID enables explicit observation");
        } catch (ReflectiveOperationException e) {
            throw new AssertionError("actual aircraft identity must be checked", e);
        }
        check(!MutualDogfightObservationPolicy.enabled(true, scenario, target, target, null), "unset flag");
        check(!MutualDogfightObservationPolicy.enabled(true, scenario, target, target, "false"), "false flag");
        check(!MutualDogfightObservationPolicy.enabled(true, scenario, target, target, "TRUE"), "explicit exact flag");
        check(!MutualDogfightObservationPolicy.enabled(false, scenario, target, target, "true"), "ordinary server");
        check(!MutualDogfightObservationPolicy.enabled(true, "full", target, target, "true"), "wrong scenario");
        check(!MutualDogfightObservationPolicy.enabled(true, scenario, "all", target, "true"), "wrong aircraft");
        check(MutualDogfightObservationPolicy.enabled(true, scenario, target, target, "true"), "explicit test opt-in");
        check(!MutualDogfightObservationPolicy.sample(false, 20), "not started");
        check(!MutualDogfightObservationPolicy.sample(true, 19), "between samples");
        check(MutualDogfightObservationPolicy.sample(true, 20), "20 tick cadence");
        check(!MutualDogfightObservationPolicy.sample(true, -20), "invalid tick");
        check("unknown".equals(MutualDogfightObservationPolicy.state(null)), "unknown is not false");
        check("false".equals(MutualDogfightObservationPolicy.state(false)), "known false");
        check("true".equals(MutualDogfightObservationPolicy.state(true)), "known true");
        Object ref = new Object();
        check("unknown".equals(MutualDogfightObservationPolicy.lookup(null, null)), "no reference");
        check("not_visible".equals(MutualDogfightObservationPolicy.lookup(ref, null)), "not visible");
        check("same".equals(MutualDogfightObservationPolicy.lookup(ref, ref)), "same object");
        check("different".equals(MutualDogfightObservationPolicy.lookup(ref, new Object())), "different object");
        check("after_fixture_direct_apply_before_opening".equals(MutualDogfightObservationPolicy.stage(true)), "initial stage");
        check("before_rebind".equals(MutualDogfightObservationPolicy.stage(false)), "periodic stage");
    }
}
"""


class MutualObservationPolicyTests(unittest.TestCase):
    def test_gate_cadence_and_unknown_values(self):
        self.assertTrue(SOURCE.is_file(), "the GameTest observation policy must exist")
        javac, java = shutil.which("javac"), shutil.which("java")
        if not javac or not java:
            self.skipTest("JDK 17 is required")
        with tempfile.TemporaryDirectory() as work:
            harness = Path(work) / "ObservationPolicyHarness.java"
            harness.write_text(HARNESS, encoding="utf-8")
            subprocess.run([javac, "--release", "17", "-d", work, str(SOURCE), str(harness)],
                           check=True, capture_output=True, text=True)
            result = subprocess.run([java, "-cp", work, "com.wwdebug.autopilot.ObservationPolicyHarness"],
                                    check=False, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
