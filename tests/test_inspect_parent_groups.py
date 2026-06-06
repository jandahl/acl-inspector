# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Tests that inspect_host() surfaces parent_groups for named targets."""

import unittest
from parsers.cisco.asa.inspect import inspect_host

_CFG = """\
object network HOST_A
 host 10.1.1.1
object network HOST_B
 host 10.1.1.2
object-group network MANAGERS
 network-object object HOST_A
object-group network SERVERS
 network-object object HOST_A
 network-object object HOST_B
object-group network ALL_SERVERS
 group-object SERVERS
access-list OUTSIDE_IN extended permit ip any object HOST_A
access-list OUTSIDE_IN extended permit ip any object HOST_B
"""


class TestInspectParentGroups(unittest.TestCase):
    def test_named_target_returns_parent_groups(self):
        report = inspect_host(_CFG, "HOST_A")
        self.assertIn("parent_groups", report)
        self.assertEqual(set(report["parent_groups"]), {"MANAGERS", "SERVERS"})

    def test_nested_group_not_in_direct_parents(self):
        # ALL_SERVERS contains SERVERS (group-object), not HOST_A directly
        report = inspect_host(_CFG, "HOST_A")
        self.assertNotIn("ALL_SERVERS", report["parent_groups"])

    def test_ip_target_has_empty_parent_groups(self):
        report = inspect_host(_CFG, "10.1.1.1")
        self.assertEqual(report.get("parent_groups", []), [])

    def test_orphan_object_has_empty_parent_groups(self):
        cfg = "object network ORPHAN\n host 9.9.9.9\naccess-list TEST extended permit ip any object ORPHAN\n"
        report = inspect_host(cfg, "ORPHAN")
        self.assertEqual(report["parent_groups"], [])

    def test_parent_groups_is_sorted(self):
        # HOST_A belongs to MANAGERS and SERVERS — two parents, sort is meaningful
        report = inspect_host(_CFG, "HOST_A")
        self.assertEqual(len(report["parent_groups"]), 2)
        self.assertEqual(report["parent_groups"], sorted(report["parent_groups"]))


if __name__ == "__main__":
    unittest.main()
