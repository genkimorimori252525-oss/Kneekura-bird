"""Synthetic javap listing contract, without loading Forge or starting a server."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / 'tools' / 'verify_gametest_function_bytecode.py'
spec = importlib.util.spec_from_file_location('function_contract', TOOL)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)

FUNCTION = 'net.minecraft.gametest.framework.TestFunction'
CONSTRUCTOR_DESC = ('(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;'
                    'Lnet/minecraft/world/level/block/Rotation;IJZIILjava/util/function/Consumer;)V')
REG_HEADER = '  private static net.minecraft.gametest.framework.TestFunction turnMethodIntoTestFunction(java.lang.reflect.Method);\n'
REG_DESC = '(Ljava/lang/reflect/Method;)Lnet/minecraft/gametest/framework/TestFunction;'
CTOR_HEADER = ('  public net.minecraft.gametest.framework.TestFunction(java.lang.String, java.lang.String, '
               'java.lang.String, net.minecraft.world.level.block.Rotation, int, long, boolean, int, int, '
               'java.util.function.Consumer<net.minecraft.gametest.framework.GameTestHelper>);\n')
RUN_HEADER = '  public void run(net.minecraft.gametest.framework.GameTestHelper);\n'
RUN_DESC = '(Lnet/minecraft/gametest/framework/GameTestHelper;)V'
REG_CALLS = [
    '     178: invokestatic  #205 // Method turnMethodIntoConsumer:(Ljava/lang/reflect/Method;)Ljava/util/function/Consumer;\n',
    '     181: invokespecial #419 // Method net/minecraft/gametest/framework/TestFunction."<init>":' + CONSTRUCTOR_DESC + '\n',
]
CTOR_FIELD = '      52: putfield      #74 // Field function:Ljava/util/function/Consumer;\n'
RUN_CALLS = [
    '       1: getfield      #74 // Field function:Ljava/util/function/Consumer;\n',
    '       5: invokeinterface #94,  2 // InterfaceMethod java/util/function/Consumer.accept:(Ljava/lang/Object;)V\n',
]

def registry(calls=None):
    calls = REG_CALLS if calls is None else calls
    return ('Compiled from "GameTestRegistry.java"\npublic class net.minecraft.gametest.framework.GameTestRegistry {\n'
            + REG_HEADER + '    descriptor: ' + REG_DESC + '\n    Code:\n       0: aload_0\n'
            + ''.join(calls) + '     184: areturn\n'
            + '  private static void other();\n    descriptor: ()V\n    Code:\n       0: return\n}\n')

def function(ctor=None, run=None):
    ctor = [CTOR_FIELD] if ctor is None else ctor
    run = RUN_CALLS if run is None else run
    return ('Compiled from "TestFunction.java"\npublic class ' + FUNCTION + ' {\n'
            + '  private final java.util.function.Consumer<net.minecraft.gametest.framework.GameTestHelper> function;\n'
            + '    descriptor: Ljava/util/function/Consumer;\n\n'
            + CTOR_HEADER + '    descriptor: ' + CONSTRUCTOR_DESC + '\n    Code:\n       0: aload_0\n'
            + ''.join(ctor) + '      61: return\n'
            + RUN_HEADER + '    descriptor: ' + RUN_DESC + '\n    Code:\n       0: aload_0\n'
            + ''.join(run) + '      10: return\n'
            + '  private void other();\n    descriptor: ()V\n    Code:\n       0: return\n}\n')

def at(line, old, new):
    return line.replace(f'{old}:', f'{new}:', 1)

class FunctionContractTests(unittest.TestCase):
    def reject_registry(self, text):
        self.assertTrue(verifier.check_registry_listing(text), 'registry mutation must be rejected')
    def reject_function(self, text):
        self.assertTrue(verifier.check_function_listing(text), 'function mutation must be rejected')

    def test_valid_registry_and_function(self):
        self.assertEqual(verifier.check_registry_listing(registry()), [])
        self.assertEqual(verifier.check_function_listing(function()), [])

    def test_registry_missing_and_duplicate(self):
        for index in range(2):
            with self.subTest(index=index, mutation='missing'):
                self.reject_registry(registry(REG_CALLS[:index] + REG_CALLS[index + 1:]))
            with self.subTest(index=index, mutation='duplicate'):
                duplicate = at(REG_CALLS[index], [178, 181][index], [179, 182][index])
                self.reject_registry(registry(REG_CALLS[:index+1] + [duplicate] + REG_CALLS[index+1:]))

    def test_registry_wrong_owner_name_descriptor_and_opcode(self):
        for old, new in [
            ('turnMethodIntoConsumer:', 'otherConsumer:'),
            ('(Ljava/lang/reflect/Method;)Ljava/util/function/Consumer;', '(Ljava/lang/Object;)Ljava/util/function/Consumer;'),
            ('invokestatic  #205', 'invokevirtual #205'),
            ('net/minecraft/gametest/framework/TestFunction."<init>"', 'other/TestFunction."<init>"'),
            ('invokespecial #419', 'invokestatic  #419'),
            (CONSTRUCTOR_DESC, CONSTRUCTOR_DESC.replace('IJZII', 'IJZI')),
        ]:
            with self.subTest(old=old): self.reject_registry(registry().replace(old, new))

    def test_registry_additional_wrong_descriptor_and_opcode(self):
        for wrong in [
            at(REG_CALLS[0], 178, 179).replace('(Ljava/lang/reflect/Method;)', '(Ljava/lang/Object;)'),
            at(REG_CALLS[0], 178, 179).replace('invokestatic', 'invokevirtual'),
        ]:
            with self.subTest(wrong=wrong): self.reject_registry(registry([REG_CALLS[0], wrong, REG_CALLS[1]]))

    def test_registry_reversed_with_monotone_offsets(self):
        self.reject_registry(registry([at(REG_CALLS[1], 181, 178), at(REG_CALLS[0], 178, 181)]))

    def test_registry_other_method_cannot_supply_missing_call(self):
        self.reject_registry(registry([REG_CALLS[0]]).replace('       0: return\n}', REG_CALLS[1] + '       0: return\n}'))

    def test_registry_method_descriptor_and_name(self):
        self.reject_registry(registry().replace(REG_DESC, '()V', 1))
        self.reject_registry(registry().replace('turnMethodIntoTestFunction(', 'other(', 1))

    def test_function_missing_or_duplicate_each_instruction(self):
        self.reject_function(function(ctor=[]))
        self.reject_function(function(ctor=[CTOR_FIELD, at(CTOR_FIELD, 52, 53)]))
        for i in range(2):
            with self.subTest(index=i, mutation='missing'):
                self.reject_function(function(run=RUN_CALLS[:i] + RUN_CALLS[i+1:]))
            with self.subTest(index=i, mutation='duplicate'):
                duplicate = at(RUN_CALLS[i], [1, 5][i], [2, 6][i])
                self.reject_function(function(run=RUN_CALLS[:i+1] + [duplicate] + RUN_CALLS[i+1:]))

    def test_function_wrong_field_descriptor_opcode_and_accept(self):
        for old, new in [
            ('putfield      #74', 'getfield      #74'),
            ('getfield      #74', 'putfield      #74'),
            ('function:Ljava/util/function/Consumer;', 'function:Ljava/lang/Object;'),
            ('invokeinterface #94,  2', 'invokevirtual #94'),
            ('java/util/function/Consumer.accept:(Ljava/lang/Object;)V', 'java/util/function/Consumer.accept:(Ljava/lang/String;)V'),
            ('java/util/function/Consumer.accept:', 'java/util/function/Consumer.other:'),
        ]:
            with self.subTest(old=old): self.reject_function(function().replace(old, new))

    def test_function_extra_wrong_descriptor_or_opcode(self):
        for wrong in [
            at(RUN_CALLS[1], 5, 6).replace('(Ljava/lang/Object;)V', '(Ljava/lang/String;)V'),
            at(RUN_CALLS[1], 5, 6).replace('invokeinterface #94,  2', 'invokevirtual #94'),
        ]:
            with self.subTest(wrong=wrong): self.reject_function(function(run=[*RUN_CALLS, wrong]))

    def test_function_run_reversed_with_monotone_offsets(self):
        self.reject_function(function(run=[at(RUN_CALLS[1], 5, 1), at(RUN_CALLS[0], 1, 5)]))

    def test_function_other_method_cannot_supply_missing_instruction(self):
        self.reject_function(function(run=[RUN_CALLS[0]]).replace('       0: return\n}', RUN_CALLS[1] + '       0: return\n}'))

    def test_function_method_descriptors(self):
        self.reject_function(function().replace('    descriptor: ' + CONSTRUCTOR_DESC, '    descriptor: ()V', 1))
        self.reject_function(function().replace('    descriptor: ' + RUN_DESC, '    descriptor: ()V', 1))

    def test_function_field_declaration_descriptor(self):
        self.reject_function(function().replace('    descriptor: Ljava/util/function/Consumer;',
                                               '    descriptor: Ljava/lang/Object;', 1))

    def test_javap_disassembly_failure_is_nonzero(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake = root / 'javap'
            fake.write_text('#!/bin/sh\nif [ "$1" = "-version" ]; then echo 17.0.17; exit 0; fi\necho failed >&2\nexit 23\n', encoding='utf-8')
            fake.chmod(0o700)
            registry_class = root / 'GameTestRegistry.class'
            function_class = root / 'TestFunction.class'
            registry_class.write_bytes(b'\xca\xfe\xba\xbe')
            function_class.write_bytes(b'\xca\xfe\xba\xbe')
            result = subprocess.run([sys.executable, str(TOOL), '--registry-class', str(registry_class),
                                     '--function-class', str(function_class), '--javap', str(fake)],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)

if __name__ == '__main__':
    unittest.main()
