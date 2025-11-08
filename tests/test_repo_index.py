import os
import shutil
import tempfile
import json
import unittest
import importlib.util


class TestRepoIndex(unittest.TestCase):
    def setUp(self):
        self.tmp_root = tempfile.mkdtemp(prefix='idxroot_')
        self.tmp_cache = tempfile.mkdtemp(prefix='idxcache_')
        # Sample ASA config
        asa = """
ASA Version 9.10(1)
object network OBJ_HOST
  host 10.1.2.3
object-group network NETS
  network-object host 10.2.2.2
access-list OUT extended permit tcp any object OBJ_HOST eq 443
"""
        with open(os.path.join(self.tmp_root, 'asa1.conf'), 'w') as f:
            f.write(asa)

    def tearDown(self):
        shutil.rmtree(self.tmp_root, ignore_errors=True)
        shutil.rmtree(self.tmp_cache, ignore_errors=True)

    def test_index_repo(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts', 'index_repo.py')
        spec = importlib.util.spec_from_file_location('index_repo', path)
        mod = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(mod)  # type: ignore
        count, errors, vendor_counts = mod.index_repo(self.tmp_root, self.tmp_cache)
        self.assertGreaterEqual(count, 1)
        self.assertEqual(errors, 0)
        self.assertIn('asa', vendor_counts)
        # manifest exists
        mf = os.path.join(self.tmp_cache, 'manifest.json')
        self.assertTrue(os.path.isfile(mf))
        with open(mf, 'r') as fh:
            j = json.load(fh)
        self.assertEqual(j.get('count'), count)
        self.assertIn('vendor_counts', j)
        self.assertIn('asa', j.get('vendor_counts', {}))

        # Verify enhanced manifest metadata
        self.assertIn('confidence_counts', j)
        self.assertIsInstance(j.get('confidence_counts'), dict)
        self.assertIn('files', j)
        files_list = j.get('files', [])
        self.assertGreaterEqual(len(files_list), 1)

        # Verify file entry has new metadata
        first_file = files_list[0]
        self.assertIn('vendor', first_file)
        self.assertIn('os', first_file)
        self.assertIn('score', first_file)
        self.assertIn('reason', first_file)
        self.assertIn('confidence', first_file)
        self.assertIn(first_file['confidence'], ['high', 'medium', 'low'])

        # at least one cache file besides manifest
        cache_files = [f for f in os.listdir(self.tmp_cache) if f.endswith('.json') and f != 'manifest.json']
        self.assertGreaterEqual(len(cache_files), 1)


if __name__ == '__main__':
    unittest.main()
