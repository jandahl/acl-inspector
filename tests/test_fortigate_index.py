# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Tests for the FortiGate predictive-search index adapter."""

import unittest
from pathlib import Path

from analysis_core.adapters import build_fortigate_index

FIXTURES = Path(__file__).parent / "fixtures" / "configs" / "fortigate"


class FortigateIndexTest(unittest.TestCase):
    def setUp(self):
        self.index = build_fortigate_index((FIXTURES / "sample.conf").read_text())

    def test_objects_include_addresses_and_vips(self):
        self.assertIn("WEB_SERVER", self.index["objects"])
        self.assertIn("DB_SERVER", self.index["objects"])
        # VIPs are searchable address-like objects.
        self.assertIn("VIP_WEB", self.index["objects"])

    def test_groups_include_addrgrps(self):
        self.assertIn("BACKEND_SERVERS", self.index["groups"])

    def test_literals_resolved(self):
        self.assertIn("10.1.1.10/32", self.index["literals"])

    def test_object_details_carry_addresses(self):
        self.assertIn("WEB_SERVER", self.index["object_details"])
        self.assertIn("10.1.1.10/32", self.index["object_details"]["WEB_SERVER"]["addresses"])

    def test_popularity_seeded_and_boosted(self):
        pop = self.index["popularity"]
        self.assertIn("object", pop)
        self.assertIn("group", pop)
        # Every object carries at least the base popularity.
        self.assertGreaterEqual(pop["object"].get("WEB_SERVER", 0), 1.0)
        # A group referenced/used scores above the base weight.
        self.assertGreaterEqual(pop["group"].get("BACKEND_SERVERS", 0), 1.0)

    def test_empty_config_is_safe(self):
        idx = build_fortigate_index("")
        self.assertEqual(idx["objects"], [])
        self.assertEqual(idx["groups"], [])
        self.assertEqual(idx["literals"], [])


if __name__ == "__main__":
    unittest.main()
