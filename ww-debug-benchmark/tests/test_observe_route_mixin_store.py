import importlib.util
from pathlib import Path
import unittest

script = Path(__file__).resolve().parents[1] / 'tools/observe_route_mixin_store.py'
spec = importlib.util.spec_from_file_location('observe_route_mixin_store', script)
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)


class MethodIdentityTests(unittest.TestCase):
    def test_exact_descriptor_and_access(self):
        text = 'METHOD applyControl(Lentity;)V access=9\n0 VAR opcode=58 slot=4 ASTORE\nMAX stack=1 locals=5 instructions=1\n'
        self.assertEqual(observer.method_instructions(text, 'applyControl', '(Lentity;)V', 9),
                         ['0 VAR opcode=58 slot=4 ASTORE'])

    def test_duplicate_exact_descriptor_is_inconclusive(self):
        text = 'METHOD applyControl(Lentity;)V access=9\nMAX stack=0 locals=0 instructions=0\n' * 2
        with self.assertRaisesRegex(ValueError, 'INCONCLUSIVE.*exactly one method'):
            observer.method_instructions(text, 'applyControl', '(Lentity;)V', 9)

    def test_duplicate_descriptor_with_different_access_is_inconclusive(self):
        text = ('METHOD applyControl(Lentity;)V access=9\nMAX stack=0 locals=0 instructions=0\n'
                'METHOD applyControl(Lentity;)V access=8\nMAX stack=0 locals=0 instructions=0\n')
        with self.assertRaisesRegex(ValueError, 'INCONCLUSIVE.*exactly one method'):
            observer.method_instructions(text, 'applyControl', '(Lentity;)V', 9)

    def test_wrong_descriptor_is_inconclusive(self):
        text = 'METHOD applyControl(Lentity;)I access=9\nMAX stack=0 locals=0 instructions=0\n'
        with self.assertRaisesRegex(ValueError, 'INCONCLUSIVE.*exactly one method'):
            observer.method_instructions(text, 'applyControl', '(Lentity;)V', 9)

    def test_missing_end_is_inconclusive(self):
        text = 'METHOD applyControl(Lentity;)V access=9\nMETHOD other()V access=9\n'
        with self.assertRaisesRegex(ValueError, 'INCONCLUSIVE.*missing method end'):
            observer.method_instructions(text, 'applyControl', '(Lentity;)V', 9)


if __name__ == '__main__':
    unittest.main()
