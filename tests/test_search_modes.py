import unittest
import importlib.util
import os

from common.project_paths import cli_path

_MOD_PATH = str(cli_path('access-list-web.py'))
spec = importlib.util.spec_from_file_location('access_list_web', _MOD_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)  # type: ignore


class TestSearchModes(unittest.TestCase):
    def setUp(self):
        self.index = {
            'objects': ['Sidzvsql05', 'webfrontend', 'sql-svc', 'HR-NET', 'db01', 'DB02'],
            'groups': ['DB-SERVERS', 'Web-Servers'],
            'literals': ['10.10.10.10', '10.0.0.0/8'],
        }

    def test_prefix(self):
        res = mod.match_candidates_for_tests(self.index, 'sid', mode='prefix')
        vals = [r['value'] for r in res]
        self.assertIn('Sidzvsql05', vals)
        self.assertNotIn('sql-svc', vals)  # not prefix

    def test_substring(self):
        res = mod.match_candidates_for_tests(self.index, 'sql', mode='substring')
        vals = [r['value'] for r in res]
        self.assertIn('Sidzvsql05', vals)  # case-insensitive contains
        self.assertIn('sql-svc', vals)

    def test_fuzzy(self):
        res = mod.match_candidates_for_tests(self.index, 'SQL', mode='fuzzy')
        vals = [r['value'] for r in res]
        self.assertIn('Sidzvsql05', vals)  # subsequence match
        # Ensure objects rank before groups given equal score
        if 'DB-SERVERS' in vals:
            self.assertLess(vals.index('db01') if 'db01' in vals else 9999, vals.index('DB-SERVERS'))


if __name__ == '__main__':
    unittest.main()
