"""Tests for the index manager."""

import tempfile
import unittest
from pathlib import Path

from webui.indexer import IndexManager
from webui.state import DiskCache, SearchIndex


ASA_SAMPLE = """!
object network OBJ_WEB
 host 192.0.2.10
object network OBJ_DB
 host 198.51.100.5
object-group network OG-SERVERS
 network-object object OBJ_WEB
 network-object object OBJ_DB
"""


class IndexManagerTest(unittest.TestCase):
    def test_builds_and_caches_indexes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_dir = Path(tmpdir)
            cfg_path = cfg_dir / "sample.cfg"
            cfg_path.write_text(ASA_SAMPLE, encoding="utf-8")

            disk_cache = DiskCache(tmpdir)
            search_cache = SearchIndex()
            manager = IndexManager(disk_cache=disk_cache, search_cache=search_cache)

            entry = manager.get_index("asa", "ASA", "auto", str(cfg_path))
            self.assertIn("OBJ_WEB", entry.index["objects"])
            self.assertIn("OG-SERVERS", entry.index["groups"])
            self.assertGreater(len(disk_cache.list_files()), 0)

            suggestions = manager.suggest(entry.index, "obj", "prefix", 5)
            values = {item["value"] for item in suggestions}
            self.assertIn("OBJ_WEB", values)

            status = manager.status()
            self.assertEqual(status["in_memory"]["entries"], 1)

            # New manager should repopulate from disk cache
            new_cache = SearchIndex()
            manager2 = IndexManager(disk_cache=disk_cache, search_cache=new_cache)
            entry2 = manager2.get_index("asa", "ASA", "auto", str(cfg_path))
            self.assertEqual(entry2.index, entry.index)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
