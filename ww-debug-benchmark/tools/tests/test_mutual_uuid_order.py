"""Exercise the opt-in GameTest UUID plan without starting Minecraft or changing its physics."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[2] / (
    "src/main/java/com/wwdebug/autopilot/MutualDogfightUuidOrder.java")

HARNESS = r"""
package com.wwdebug.autopilot;

import java.util.HashSet;
import java.util.Set;
import java.util.UUID;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public final class UuidOrderHarness {
    private static void check(boolean value, String reason) {
        if (!value) throw new AssertionError(reason);
    }
    public static void main(String[] args) throws Exception {
        check(MutualDogfightUuidOrder.resolve(true, "dogfight_mutual", "warfare_wings:a6m", null).isEmpty(),
              "unset flag must retain random UUIDs");
        check(MutualDogfightUuidOrder.resolve(false, "dogfight_mutual", "warfare_wings:a6m", "a6m-low").isEmpty(),
              "ordinary servers must not enable fixture IDs");
        var low = MutualDogfightUuidOrder.resolve(true, "dogfight_mutual", "warfare_wings:a6m", "a6m-low").orElseThrow();
        var high = MutualDogfightUuidOrder.resolve(true, "dogfight_mutual", "warfare_wings:a6m", "a6m-high").orElseThrow();
        check(low.primaryAircraft().compareTo(low.opponentAircraft()) < 0, "low order");
        check(high.primaryAircraft().compareTo(high.opponentAircraft()) > 0, "high order");
        check(low.primaryAircraft().equals(high.opponentAircraft())
              && low.opponentAircraft().equals(high.primaryAircraft()), "only reverse the aircraft UUIDs");
        check(low.primaryAircraft().hashCode() == low.opponentAircraft().hashCode(), "equal aircraft hashes");
        check(low.primaryPilot().equals(high.primaryPilot()) && low.opponentPilot().equals(high.opponentPilot()),
              "pilot UUIDs must not change when order reverses");
        Set<UUID> ids = new HashSet<>(Set.of(low.primaryAircraft(), low.opponentAircraft(),
                                             low.primaryPilot(), low.opponentPilot()));
        check(ids.size() == 4, "four distinct IDs");
        for (UUID id : ids) check(id.version() == 4 && id.variant() == 2, "valid UUIDv4");
        for (UUID aircraft : Set.of(low.primaryAircraft(), low.opponentAircraft()))
            for (UUID pilot : Set.of(low.primaryPilot(), low.opponentPilot()))
                check(aircraft.compareTo(pilot) < 0, "pilot comparison must not reverse");
        for (String[] input : new String[][] {
                {"dogfight_mutual", "warfare_wings:a6m", "bad"},
                {"full", "warfare_wings:a6m", "a6m-low"},
                {"dogfight_mutual", "all", "a6m-low"},
                {"dogfight_mutual", "warfare_wings:a6m", ""}}) {
            boolean rejected = false;
            try { MutualDogfightUuidOrder.resolve(true, input[0], input[1], input[2]); }
            catch (IllegalArgumentException expected) { rejected = true; }
            check(rejected, "invalid explicit setup must fail closed");
        }
        Method registration;
        try {
            registration = MutualDogfightUuidOrder.class.getDeclaredMethod("registrationStatus",
                    boolean.class, boolean.class, boolean.class, UUID.class, UUID.class,
                    Object.class, Object.class);
        } catch (NoSuchMethodException missing) {
            throw new AssertionError("registration acceptance must be checked", missing);
        }
        Object expected = new Object();
        UUID id = low.primaryAircraft();
        check("visible".equals(registration.invoke(null, true, true, false, id, id, expected, expected)),
              "visible registration must be identified");
        check("hidden_or_unavailable".equals(registration.invoke(null, true, true, false, id, id, expected, null)),
              "accepted invisible entity is not a proven insertion failure");
        for (Object[] failure : new Object[][] {
                {false, true, false, id, id, expected, null},
                {true, false, false, id, id, expected, null},
                {true, true, true, id, id, expected, null},
                {true, true, false, null, id, expected, null},
                {true, true, false, id, id, null, null},
                {true, true, false, id, high.primaryAircraft(), expected, null},
                {true, true, false, id, id, expected, new Object()}}) {
            boolean rejected = false;
            try { registration.invoke(null, failure); }
            catch (InvocationTargetException cause) { rejected = cause.getCause() instanceof IllegalStateException; }
            check(rejected, "failed or mismatched registration must stop the fixture");
        }
    }
}
"""


class MutualUuidOrderTests(unittest.TestCase):
    def test_uuid_order_and_opt_in_guard(self):
        self.assertTrue(SOURCE.is_file(), "the GameTest UUID order selector must exist")
        javac = shutil.which("javac")
        java = shutil.which("java")
        if not javac or not java:
            self.skipTest("a JDK is required for the deterministic UUID selector test")
        with tempfile.TemporaryDirectory() as work:
            harness = Path(work) / "UuidOrderHarness.java"
            harness.write_text(HARNESS, encoding="utf-8")
            subprocess.run([javac, "--release", "17", "-d", work, str(SOURCE), str(harness)],
                           check=True, capture_output=True, text=True)
            result = subprocess.run([java, "-cp", work, "com.wwdebug.autopilot.UuidOrderHarness"],
                                    check=False, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
