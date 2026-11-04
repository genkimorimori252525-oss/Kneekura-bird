#!/usr/bin/env python3
"""Small, synthetic checks for the standalone built-class evidence utilities."""
import importlib.util
from pathlib import Path
import unittest
import tempfile
import zipfile

MODULE = Path(__file__).with_name('defensive_built_tools.py')

def load_tools():
    if not MODULE.is_file():
        return None
    spec = importlib.util.spec_from_file_location('defensive_built_tools', MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EvidenceContracts(unittest.TestCase):
    def setUp(self):
        self.tools = load_tools()
        self.assertIsNotNone(self.tools, 'built evidence utility is not implemented')

    def test_transform_requires_exactly_one_anchor(self):
        self.assertEqual(self.tools.replace_once('before anchor after', 'anchor', 'new'), 'before new after')
        for text in ('missing', 'anchor anchor'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.tools.replace_once(text, 'anchor', 'new')

    def test_origin_rejects_authority_noncanonical_and_different_path(self):
        expected = Path('/tmp/class-origin')
        self.assertTrue(self.tools.same_dir_uri('file:/tmp/class-origin/', expected))
        for uri in ('file://host/tmp/class-origin/', 'http:/tmp/class-origin/',
                    'file:tmp/class-origin/', 'file:/tmp/x/../class-origin/',
                    'file:/tmp/class-origin/?q=1', 'file:/tmp/class-origin/#x',
                    'file:/tmp/class-origin-else/', 'file:/tmp%2Fclass-origin/',
                    'file:/tmp/class-origin/%xx'):
            with self.subTest(uri=uri):
                self.assertFalse(self.tools.same_dir_uri(uri, expected))

    def test_classpath_directory_content_and_symlink(self):
        self.assertTrue(hasattr(self.tools, 'classpath_inventory'), 'classpath inventory not implemented')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'empty').mkdir()
            target = root / 'One.class'
            target.write_bytes(b'one')
            first = self.tools.classpath_inventory([root])
            self.assertEqual(set(first), {str(target)})
            target.write_bytes(b'two')
            self.assertNotEqual(first, self.tools.classpath_inventory([root]))
            (root / 'alias.class').symlink_to(target)
            with self.assertRaises(ValueError):
                self.tools.classpath_inventory([root])

    def test_jar_bounds_reject_large_entry_before_reading(self):
        self.assertTrue(hasattr(self.tools, 'bounded_jar_entries'), 'bounded jar inventory not implemented')
        with tempfile.TemporaryDirectory() as temporary:
            jar = Path(temporary) / 'fixture.jar'
            with zipfile.ZipFile(jar, 'w') as archive:
                archive.writestr('safe.class', b'12345')
            with zipfile.ZipFile(jar) as archive:
                self.assertEqual(len(self.tools.bounded_jar_entries(archive, 2, 10, 10)), 1)
                with self.assertRaises(ValueError):
                    self.tools.bounded_jar_entries(archive, 2, 4, 10)
                with self.assertRaises(ValueError):
                    self.tools.bounded_jar_entries(archive, 2, 10, 4)
                with self.assertRaises(ValueError):
                    self.tools.bounded_jar_entries(archive, 0, 10, 10)

    def test_suites_require_the_fixed_cases(self):
        self.assertTrue(hasattr(self.tools, 'case_names'), 'fixed suite cases not implemented')
        cases = self.tools.case_names('matrix')
        self.assertEqual(len(cases), 19)
        self.assertIn('defense-same-uuid', cases)
        self.assertEqual(len(self.tools.case_names('exceptions')), 12)
        with self.assertRaises(ValueError):
            self.tools.case_names('unknown')

    def test_expected_sentinel_must_match_the_case(self):
        classify = self.tools.expected_case
        self.assertTrue(classify('exceptions', 'defense-throw-def-pilot-runtime', 1,
                                 '', 'SENTINEL:defense-throw-def-pilot-runtime'))
        self.assertFalse(classify('exceptions', 'defense-throw-def-pilot-runtime', 1,
                                  '', 'other failure'))
        self.assertTrue(classify('exceptions', 'defense-throw-rejected-pilot-runtime', 0,
                                 'OBSERVATION_NO_SENTINEL_THROW', ''))
        self.assertFalse(classify('exceptions', 'defense-throw-rejected-pilot-runtime', 0,
                                  '', ''))
        self.assertTrue(classify('matrix', 'defense-swap', 0, '', ''))
        self.assertFalse(classify('matrix', 'defense-swap', 1, '', ''))

if __name__ == '__main__':
    unittest.main()
