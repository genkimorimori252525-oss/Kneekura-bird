"""Offline checks of the fixed GameTest startup call-site listing contract."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / 'tools' / 'verify_gametest_main_bytecode.py'
spec = importlib.util.spec_from_file_location('gametest_main_contract', TOOL)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)

DESCRIPTOR = ('(ZLjoptsimple/OptionSet;Ljoptsimple/OptionSpec;Lnet/minecraft/world/level/storage/'
    'LevelStorageSource$LevelStorageAccess;Lnet/minecraft/server/packs/repository/PackRepository;'
    'Lnet/minecraft/server/WorldStem;Lnet/minecraft/server/dedicated/DedicatedServerSettings;'
    'Lnet/minecraft/server/Services;Ljoptsimple/OptionSpec;Ljoptsimple/OptionSpec;'
    'Ljoptsimple/OptionSpec;Ljoptsimple/OptionSpec;Ljoptsimple/OptionSpec;'
    'Ljoptsimple/OptionSpec;Ljava/lang/Thread;)Lnet/minecraft/server/MinecraftServer;')
HEADER = ('  private static net.minecraft.server.MinecraftServer lambda$main$4(boolean, joptsimple.OptionSet, joptsimple.OptionSpec, net.minecraft.world.level.storage.LevelStorageSource$LevelStorageAccess, net.minecraft.server.packs.repository.PackRepository, net.minecraft.server.WorldStem, net.minecraft.server.dedicated.DedicatedServerSettings, net.minecraft.server.Services, joptsimple.OptionSpec, joptsimple.OptionSpec, joptsimple.OptionSpec, joptsimple.OptionSpec, joptsimple.OptionSpec, joptsimple.OptionSpec, java.lang.Thread);\n')
CALLS = [
    '       4: invokestatic  #797 // Method net/minecraftforge/gametest/ForgeGameTestHooks.registerGametests:()V\n',
    '       7: invokestatic  #803 // Method net/minecraft/gametest/framework/GameTestRegistry.getAllTestFunctions:()Ljava/util/Collection;\n',
    '      10: invokestatic  #809 // Method net/minecraft/gametest/framework/GameTestRunner.groupTestsIntoBatches:(Ljava/util/Collection;)Ljava/util/Collection;\n',
    '      40: invokespecial #814 // Method net/minecraft/gametest/framework/GameTestServer."<init>":(Ljava/lang/Thread;Lnet/minecraft/world/level/storage/LevelStorageSource$LevelStorageAccess;Lnet/minecraft/server/packs/repository/PackRepository;Lnet/minecraft/server/WorldStem;Ljava/util/Collection;Lnet/minecraft/core/BlockPos;)V\n',
]

def listing(calls=CALLS, descriptor=DESCRIPTOR):
    return ('Compiled from "Main.java"\npublic class net.minecraft.server.Main {\n'
            + HEADER + '    descriptor: ' + descriptor + '\n    Code:\n'
            + '       0: iload_0\n' + ''.join(calls) + '     219: aload         15\n     221: areturn\n'
            + '  private static void other();\n    descriptor: ()V\n    Code:\n       0: return\n}\n')


class MainContractTests(unittest.TestCase):
    def reject(self, text):
        self.assertTrue(verifier.check_listing(text), 'altered listing must be rejected')

    def test_positive(self):
        self.assertEqual(verifier.check_listing(listing()), [])

    def test_method_descriptor_must_match(self):
        self.reject(listing(descriptor='()V'))

    def test_method_name_must_match(self):
        self.reject(listing().replace('lambda$main$4', 'lambda$main$5'))

    def test_each_call_must_exist(self):
        for i in range(len(CALLS)):
            with self.subTest(missing=i):
                self.reject(listing(CALLS[:i] + CALLS[i+1:]))

    def test_each_call_must_be_unique(self):
        for i in range(len(CALLS)):
            with self.subTest(duplicate=i):
                original = CALLS[i]
                offset = int(original.split(':', 1)[0])
                duplicate = original.replace(f'{offset}:', f'{offset + 1}:', 1)
                self.reject(listing(CALLS[:i+1] + [duplicate] + CALLS[i+1:]))

    def test_calls_must_be_in_order(self):
        first = CALLS[1].replace('       7:', '       4:', 1)
        second = CALLS[0].replace('       4:', '       7:', 1)
        self.reject(listing([first, second, *CALLS[2:]]))

    def test_exact_owner_name_and_descriptor(self):
        for old, new in [
            ('ForgeGameTestHooks.registerGametests', 'Other.registerGametests'),
            ('GameTestRegistry.getAllTestFunctions', 'GameTestRegistry.getOtherTestFunctions'),
            ('groupTestsIntoBatches:(Ljava/util/Collection;)Ljava/util/Collection;',
             'groupTestsIntoBatches:(Ljava/util/List;)Ljava/util/Collection;'),
            ('GameTestServer."<init>"', 'OtherServer."<init>"'),
        ]:
            with self.subTest(change=old):
                self.reject(listing().replace(old, new))

    def test_additional_wrong_descriptor_same_name_rejected(self):
        wrong = CALLS[2].replace('      10:', '      11:', 1).replace('(Ljava/util/Collection;)Ljava/util/Collection;', '(Ljava/util/List;)Ljava/util/Collection;')
        self.reject(listing(CALLS[:3] + [wrong] + CALLS[3:]))

    def test_additional_wrong_opcode_same_name_rejected(self):
        wrong = CALLS[2].replace('      10:', '      11:', 1).replace('invokestatic', 'invokeinterface').replace('#809 //', '#809, 1 //').replace('// Method ', '// InterfaceMethod ')
        self.reject(listing(CALLS[:3] + [wrong] + CALLS[3:]))

    def test_truncated_or_invalid_listing_rejected(self):
        for altered in (listing().removesuffix('}\n'), listing().replace('    Code:\n', '', 1),
                        listing().replace('     221: areturn', '     221: return', 1),
                        listing().replace('public class net.minecraft.server.Main', 'public class Other', 1)):
            with self.subTest(listing=altered):
                self.reject(altered)

    def test_wrong_constructor_opcode_rejected(self):
        self.reject(listing().replace('invokespecial #814', 'invokestatic  #814'))

    def test_call_from_other_method_cannot_spoof_missing(self):
        value = listing(CALLS[:-1]).replace('  private static void other();',
                '  private static void other();').replace('       0: return\n}', CALLS[-1] + '       0: return\n}')
        self.reject(value)

    def test_duplicate_target_method_rejected(self):
        value = listing().replace('  private static void other();',
                 HEADER + '    descriptor: ' + DESCRIPTOR + '\n    Code:\n' + ''.join(CALLS)
                 + '     219: aload         15\n     221: areturn\n  private static void other();')
        self.reject(value)

    def test_javap_failure_is_nonzero(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake = root / 'javap'
            fake.write_text('#!/bin/sh\necho intentionally-failed >&2\nexit 23\n', encoding='utf-8')
            fake.chmod(0o700)
            target = root / 'Main.class'
            target.write_bytes(b'\xca\xfe\xba\xbe')
            result = subprocess.run([sys.executable, str(TOOL), '--class-file', str(target),
                                     '--javap', str(fake)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)

    def test_missing_javap_is_nonzero(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / 'Main.class'
            target.write_bytes(b'\xca\xfe\xba\xbe')
            result = subprocess.run([sys.executable, str(TOOL), '--class-file', str(target),
                                     '--javap', str(root / 'missing-javap')], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)

    def test_disassembly_failure_after_version_check_is_nonzero(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake = root / 'javap'
            fake.write_text('#!/bin/sh\nif [ "$1" = "-version" ]; then echo 17.0.17; exit 0; fi\nexit 23\n', encoding='utf-8')
            fake.chmod(0o700)
            target = root / 'Main.class'
            target.write_bytes(b'\xca\xfe\xba\xbe')
            result = subprocess.run([sys.executable, str(TOOL), '--class-file', str(target),
                                     '--javap', str(fake)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)

if __name__ == '__main__':
    unittest.main()
