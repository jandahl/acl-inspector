import unittest
import importlib.util
import os

from common.project_paths import cli_path

_MOD_PATH = str(cli_path('access-list-web.py'))
spec = importlib.util.spec_from_file_location('access_list_web', _MOD_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)  # type: ignore
extract_meta_for_tests = mod.extract_meta_for_tests
build_index_for_tests = mod.build_index_for_tests


ASA_SAMPLE = """
ASA Version 9.12(4)
object network OBJ_HOST1
  host 10.0.0.1
object network OBJ_NET1
  subnet 10.0.1.0 255.255.255.0
object-group network GRP_NET
  network-object object OBJ_NET1
  network-object host 10.0.2.2
access-list OUTSIDE extended permit tcp object OBJ_HOST1 any eq 443
"""


class TestWebHelpers(unittest.TestCase):
    def test_extract_meta_asa(self):
        meta = extract_meta_for_tests('asa', ASA_SAMPLE)
        self.assertEqual(meta.get('os'), 'ASA')
        self.assertEqual(meta.get('version'), '9.12(4)')

    def test_build_index_asa(self):
        idx = build_index_for_tests('asa', ASA_SAMPLE)
        self.assertIn('OBJ_HOST1', idx['objects'])
        self.assertIn('OBJ_NET1', idx['objects'])
        self.assertIn('GRP_NET', idx['groups'])
        # literals include host and subnet
        self.assertIn('10.0.0.1', idx['literals'])
        self.assertTrue(any(literal.startswith('10.0.1.0/') for literal in idx['literals']))


if __name__ == '__main__':
    unittest.main()
