import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "verify_arbiter_bytecode.py"
SPEC = importlib.util.spec_from_file_location("verify_arbiter_bytecode", SCRIPT)
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)

DESCRIPTOR = "(Lnet/minecraft/world/entity/Entity;)Lcom/wwdebug/autopilot/ControlAuthorityArbiter$Authority;"
CALLS = (
    "com/wwdebug/autopilot/MobPilotGate.isPlayerControlled:(Lnet/minecraft/world/entity/Entity;)Z",
    "com/wwdebug/autopilot/AutonomousFlightManager.applyControl:(Lnet/minecraft/world/entity/Entity;)V",
    "com/wwdebug/autopilot/MutualDogfightMissionHoldAdapter.apply:(Lnet/minecraft/world/entity/Entity;)V",
    "com/wwdebug/autopilot/FormationFlightManager.applyControl:(Lnet/minecraft/world/entity/Entity;)Lcom/wwdebug/autopilot/ControlOutcome;",
    "com/wwdebug/autopilot/AirspaceSafetyProbe.collisionRisk:(Lnet/minecraft/world/entity/Entity;)Z",
)


def method(name, descriptor, calls):
    result = "com.wwdebug.autopilot.ControlAuthorityArbiter$Authority" if name == "decide" else "void"
    lines = [f"  private static {result} {name}(net.minecraft.world.entity.Entity);",
             f"    descriptor: {descriptor}", "    Code:"]
    lines.extend(f"      {i * 4}: invokestatic  #{i + 1} // Method {call}"
                 for i, call in enumerate(calls))
    lines.append(f"      {len(calls) * 4}: {'areturn' if name == 'decide' else 'return'}")
    return "\n".join(lines)


def listing(calls=CALLS):
    # A different method deliberately has the same calls: scanning the class
    # as a whole would miss a changed or absent decide body.
    return ("public final class com.wwdebug.autopilot.ControlAuthorityArbiter {\n"
            + method("decide", DESCRIPTOR, calls) + "\n\n"
            + method("clearAutomatedControl", "(Lnet/minecraft/world/entity/Entity;)V", CALLS)
            + "\n}\n")


class ArbiterBytecodeContractTest(unittest.TestCase):
    def test_expected_method_calls_once_in_order(self):
        self.assertEqual(VERIFIER.check_listing(listing()), [])

    def test_other_method_cannot_supply_missing_decide_call(self):
        errors = VERIFIER.check_listing(listing(CALLS[:3] + CALLS[4:]))
        self.assertTrue(any("FormationFlightManager" in error for error in errors), errors)

    def test_missing_or_wrong_descriptor_fails(self):
        for text in (listing().replace(" decide(", " renamed("),
                     listing().replace(DESCRIPTOR, "(Ljava/lang/Object;)V", 1)):
            with self.subTest(text=text):
                self.assertTrue(VERIFIER.check_listing(text))

    def test_duplicate_selected_method_fails(self):
        text = listing().replace("\n}\n", "\n" + method("decide", DESCRIPTOR, CALLS) + "\n}\n")
        self.assertTrue(VERIFIER.check_listing(text))

    def test_duplicate_and_out_of_order_calls_fail(self):
        for calls in (CALLS[:2] + CALLS[1:], (CALLS[0], CALLS[2], CALLS[1], *CALLS[3:])):
            with self.subTest(calls=calls):
                self.assertTrue(VERIFIER.check_listing(listing(calls)))

    def test_wrong_invocation_kind_or_call_descriptor_fails(self):
        for text in (listing().replace("invokestatic", "invokevirtual", 1),
                     listing().replace(CALLS[2], CALLS[2].replace(")V", ")Z"), 1)):
            with self.subTest(text=text):
                self.assertTrue(VERIFIER.check_listing(text))

    def test_invalid_class_or_missing_code_fails(self):
        for text in (listing().replace("com.wwdebug.autopilot.ControlAuthorityArbiter {", "Other {", 1),
                     listing().replace("    Code:\n", "", 1),
                     listing().replace("    Code:\n", "    descriptor: ()V\n    Code:\n", 1)):
            with self.subTest(text=text):
                self.assertTrue(VERIFIER.check_listing(text))

    def test_truncated_class_or_nonstatic_target_fails(self):
        for text in (listing().removesuffix("}\n"), listing().replace("private static", "private", 1)):
            with self.subTest(text=text):
                self.assertTrue(VERIFIER.check_listing(text))

    def test_invalid_instruction_offsets_or_missing_terminal_return_fails(self):
        for text in (listing().replace("      4: invokestatic", "      0: invokestatic", 1),
                     listing().replace("      20: areturn", "      20: nop", 1),
                     listing().replace("      0: invokestatic", "      1: invokestatic", 1)):
            with self.subTest(text=text):
                self.assertTrue(VERIFIER.check_listing(text))

    def test_cli_fails_when_javap_is_unavailable_or_wrong_version(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing-javap"
            for executable in (missing, Path(sys.executable)):
                with self.subTest(executable=executable):
                    process = subprocess.run(
                        [sys.executable, str(SCRIPT), "--javap", str(executable),
                         "--class-file", str(Path(directory) / "missing.class")],
                        capture_output=True, text=True, check=False)
                    self.assertEqual(process.returncode, 1)
                    self.assertFalse(json.loads(process.stdout)["passed"])


if __name__ == "__main__":
    unittest.main()
