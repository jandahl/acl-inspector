# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
import os
import tempfile
import unittest
import importlib.util

from common.project_paths import cli_path

_MOD_PATH = str(cli_path('access-list-web.py'))
spec = importlib.util.spec_from_file_location('access_list_web', _MOD_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)  # type: ignore


ASA_SAMPLE = """
interface GigabitEthernet0/0
 nameif INSIDE
 ip address 10.1.0.1 255.255.255.0
interface GigabitEthernet0/1
 nameif DMZ
 ip address 192.168.10.1 255.255.255.0
object network OBJ_APP
 host 10.1.0.20
object network OBJ_WEB
 host 192.168.10.50
""".strip()

ASA_SAMPLE_2 = """
interface GigabitEthernet0/2
 nameif BRANCH
 ip address 172.16.5.1 255.255.255.0
object network OBJ_SHARED
 host 10.1.0.20
""".strip()


class DummyServer:
    def __init__(self, config_dirs):
        self.config_dirs = config_dirs
        self.cache_dir = None
        self.index_cache = {}
        self.search_limit = 50
        self.theme_dir = ''
        self.themes = mod.DEFAULT_THEMES


class TestFindHost(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.dir = self._tmpdir.name
        with open(os.path.join(self.dir, 'fw1.conf'), 'w', encoding='utf-8') as fh:
            fh.write(ASA_SAMPLE)
        with open(os.path.join(self.dir, 'fw2.conf'), 'w', encoding='utf-8') as fh:
            fh.write(ASA_SAMPLE_2)
        self.server = DummyServer({'asa': self.dir, 'fortigate': ''})
        self.handler = mod.WebHandler.__new__(mod.WebHandler)
        self.handler.server = self.server

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_find_host_matches_across_files(self):
        results = self.handler._find_host('OBJ_APP')
        self.assertTrue(any(r['file'] == 'fw1.conf' and 'OBJ_APP' in r['objects'] for r in results))
        self.assertTrue(any(r['file'] == 'fw2.conf' and 'OBJ_SHARED' in r['objects'] for r in results))
        best = next((r for r in results if r.get('best')), None)
        self.assertIsNotNone(best)
        self.assertIn('OBJ_APP', best['objects'])
        self.assertTrue(best['interfaces'])

    def test_find_host_by_ip(self):
        results = self.handler._find_host('10.1.0.20')
        self.assertTrue(any('OBJ_APP' in r['objects'] for r in results))
        best = next((r for r in results if r.get('best')), None)
        self.assertIsNotNone(best)
        self.assertIn('10.1.0.20', ' '.join(best['literals']))


if __name__ == '__main__':
    unittest.main()
