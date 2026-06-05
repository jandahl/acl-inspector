# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Tests for ASAConfig.group_membership() — parent-group reverse lookup."""

import unittest
from parsers.cisco.asa.parser import ASAConfig


_CFG = """\
object network HOST_A
 host 10.1.1.1
object network HOST_B
 host 10.1.1.2
object network HOST_C
 host 10.1.1.3
object-group network SERVERS
 network-object object HOST_A
 network-object object HOST_B
object-group network ALL_SERVERS
 group-object SERVERS
 network-object object HOST_C
object-group network ALSO_SERVERS
 network-object object HOST_A
object-group network YET_MORE_SERVERS
 network-object object HOST_A
"""


class TestGroupMembership(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = ASAConfig(_CFG)

    def test_direct_member(self):
        m = self.cfg.group_membership()
        self.assertEqual(m["HOST_B"], ["SERVERS"])

    def test_nested_group_object(self):
        m = self.cfg.group_membership()
        self.assertIn("ALL_SERVERS", m["SERVERS"])

    def test_other_direct_member(self):
        m = self.cfg.group_membership()
        self.assertEqual(m["HOST_C"], ["ALL_SERVERS"])

    def test_direct_member_excluded_from_sibling_group(self):
        # HOST_C is only a direct member of ALL_SERVERS, not of SERVERS
        m = self.cfg.group_membership()
        self.assertNotIn("SERVERS", m.get("HOST_C", []))

    def test_multi_parent(self):
        # HOST_A is in SERVERS, ALSO_SERVERS, and YET_MORE_SERVERS
        m = self.cfg.group_membership()
        self.assertIn("SERVERS", m["HOST_A"])
        self.assertIn("ALSO_SERVERS", m["HOST_A"])
        self.assertIn("YET_MORE_SERVERS", m["HOST_A"])
        self.assertEqual(len(m["HOST_A"]), 3)

    def test_parent_list_is_sorted(self):
        m = self.cfg.group_membership()
        self.assertEqual(m["HOST_A"], sorted(m["HOST_A"]))

    def test_object_with_no_membership(self):
        cfg = ASAConfig("object network ORPHAN\n host 1.2.3.4\n")
        m = cfg.group_membership()
        self.assertEqual(m.get("ORPHAN", []), [])

    def test_empty_config(self):
        cfg = ASAConfig("")
        self.assertEqual(cfg.group_membership(), {})

    def test_result_is_cached(self):
        m1 = self.cfg.group_membership()
        m2 = self.cfg.group_membership()
        self.assertEqual(m1, m2)

    def test_returned_copy_does_not_corrupt_cache(self):
        m1 = self.cfg.group_membership()
        m1.get("HOST_B", []).append("ROGUE")
        m2 = self.cfg.group_membership()
        self.assertNotIn("ROGUE", m2.get("HOST_B", []))


if __name__ == "__main__":
    unittest.main()
