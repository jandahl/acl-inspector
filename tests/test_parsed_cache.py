# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Tests for analysis_core.parsed_cache.ParsedConfigCache."""

import os
import tempfile
import unittest

from analysis_core.parsed_cache import ParsedConfigCache
from tests.fixtures.cisco_asa_example import ASA_EXAMPLE


class ParsedConfigCacheTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "fw.conf")
        with open(self.path, "w") as fh:
            fh.write(ASA_EXAMPLE)

    def _write(self, text):
        with open(self.path, "w") as fh:
            fh.write(text)

    def test_path_hit_returns_same_object(self):
        cache = ParsedConfigCache()
        a = cache.get("asa", self.path)
        b = cache.get("asa", self.path)
        self.assertIs(a, b, "unchanged file should return the cached object")
        self.assertEqual(cache.status()["configs"], 1)

    def test_path_rebuild_on_change(self):
        cache = ParsedConfigCache()
        a = cache.get("asa", self.path)
        # Change content so size (and almost certainly mtime) differs.
        self._write(ASA_EXAMPLE + "\nobject network EXTRA\n host 10.9.9.9\n")
        b = cache.get("asa", self.path)
        self.assertIsNot(a, b, "changed file should be re-parsed")
        self.assertIn("EXTRA", b.network_objects)

    def test_text_key_hit(self):
        cache = ParsedConfigCache()
        a = cache.get_from_text("asa", ASA_EXAMPLE)
        b = cache.get_from_text("asa", ASA_EXAMPLE)
        self.assertIs(a, b)
        c = cache.get_from_text("asa", ASA_EXAMPLE + "\n! comment\n")
        self.assertIsNot(a, c, "different text should produce a distinct entry")

    def test_get_device_returns_ir(self):
        cache = ParsedConfigCache()
        device = cache.get_device("asa", self.path)
        self.assertEqual(device.vendor, "asa")
        self.assertTrue(device.acls, "IR device should carry parsed ACLs")
        # Second call is cached and identical.
        self.assertIs(device, cache.get_device("asa", self.path))

    def test_eviction_is_bounded(self):
        cache = ParsedConfigCache(max_entries=2)
        for i in range(5):
            cache.get_from_text("asa", ASA_EXAMPLE + f"\n! variant {i}\n")
        self.assertLessEqual(cache.status()["configs"], 2)

    def test_clear(self):
        cache = ParsedConfigCache()
        cache.get("asa", self.path)
        cache.get_device("asa", self.path)
        cleared = cache.clear()
        self.assertEqual(cleared, 1)
        self.assertEqual(cache.status()["configs"], 0)
        self.assertEqual(cache.status()["devices"], 0)


if __name__ == "__main__":
    unittest.main()
