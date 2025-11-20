import os
import json
import tempfile
import unittest
import importlib.util
_MOD_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cli', 'cli/access-list-web.py')
spec = importlib.util.spec_from_file_location('access_list_web', _MOD_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)  # type: ignore
index_status_for_tests = mod.index_status_for_tests


class TestIndexStatus(unittest.TestCase):
    def test_no_cache_dir(self):
        status = index_status_for_tests(None, {})
        self.assertIn('in_memory', status)
        self.assertIn('disk', status)
        self.assertEqual(status['in_memory']['entries'], 0)
        self.assertEqual(status['in_memory']['keys'], [])
        self.assertFalse(status['disk']['enabled'])
        self.assertEqual(status['disk']['path'], '')

    def test_in_memory_keys_cap(self):
        cache = {f'k{i}': {'dummy': i} for i in range(30)}
        status = index_status_for_tests(None, cache)
        self.assertEqual(status['in_memory']['entries'], 30)
        self.assertLessEqual(len(status['in_memory']['keys']), 20)

    def test_disk_status_with_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            # Create some dummy json cache files and manifest
            for i in range(3):
                with open(os.path.join(d, f'asa-ASA-{i}.json'), 'w') as f:
                    json.dump({'i': i}, f)
            manifest = {'root': '/tmp', 'count': 3, 'errors': 0, 'files': []}
            with open(os.path.join(d, 'manifest.json'), 'w') as mf:
                json.dump(manifest, mf)
            status = index_status_for_tests(d, {})
            self.assertTrue(status['disk']['enabled'])
            self.assertEqual(status['disk']['path'], d)
            # files should count all json files (including manifest)
            self.assertEqual(status['disk']['files'], 4)
            self.assertIsInstance(status['disk']['manifest'], dict)
            self.assertEqual(status['disk']['manifest'].get('count'), 3)


if __name__ == '__main__':
    unittest.main()
