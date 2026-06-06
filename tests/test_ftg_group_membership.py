# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Tests for FTGConfig.group_membership() and its surfacing in inspect_host()."""

import unittest
from parsers.fortigate.config import FTGConfig
from parsers.fortigate.inspect import inspect_host

_CFG = """\
config firewall address
    edit "HOST_A"
        set subnet 10.1.1.1 255.255.255.255
    next
    edit "HOST_B"
        set subnet 10.1.1.2 255.255.255.255
    next
end
config firewall addrgrp
    edit "SERVERS"
        set member "HOST_A" "HOST_B"
    next
    edit "ALL_SERVERS"
        set member "SERVERS"
    next
end
"""


class TestFTGGroupMembership(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = FTGConfig(_CFG)

    def test_direct_member(self):
        m = self.cfg.group_membership()
        self.assertEqual(m["HOST_A"], ["SERVERS"])
        self.assertEqual(m["HOST_B"], ["SERVERS"])

    def test_nested_group_object(self):
        m = self.cfg.group_membership()
        self.assertIn("ALL_SERVERS", m["SERVERS"])

    def test_nested_not_in_direct_parents(self):
        m = self.cfg.group_membership()
        self.assertNotIn("ALL_SERVERS", m.get("HOST_A", []))

    def test_result_is_sorted(self):
        m = self.cfg.group_membership()
        for parents in m.values():
            self.assertEqual(parents, sorted(parents))

    def test_copy_does_not_corrupt_cache(self):
        m1 = self.cfg.group_membership()
        m1.get("HOST_A", []).append("ROGUE")
        m2 = self.cfg.group_membership()
        self.assertNotIn("ROGUE", m2.get("HOST_A", []))

    def test_object_not_in_any_group(self):
        cfg = FTGConfig(_CFG + 'config firewall address\n    edit "HOST_C"\n        set subnet 10.1.1.3 255.255.255.255\n    next\nend\n')
        self.assertEqual(cfg.group_membership().get("HOST_C", []), [])

    def test_empty_config(self):
        self.assertEqual(FTGConfig("").group_membership(), {})

    def test_inspect_host_surfaces_parent_groups(self):
        cfg_with_policy = _CFG + (
            'config firewall policy\n'
            '    edit 1\n'
            '        set srcintf "any"\n'
            '        set dstintf "any"\n'
            '        set srcaddr "all"\n'
            '        set dstaddr "HOST_A"\n'
            '        set action accept\n'
            '    next\nend\n'
        )
        report = inspect_host(cfg_with_policy, "HOST_A")
        self.assertIn("parent_groups", report)
        self.assertEqual(report["parent_groups"], ["SERVERS"])

    def test_inspect_host_ip_target_has_empty_parent_groups(self):
        cfg_with_policy = _CFG + (
            'config firewall policy\n'
            '    edit 1\n'
            '        set srcintf "any"\n'
            '        set dstintf "any"\n'
            '        set srcaddr "all"\n'
            '        set dstaddr "HOST_A"\n'
            '        set action accept\n'
            '    next\nend\n'
        )
        report = inspect_host(cfg_with_policy, "10.1.1.1")
        self.assertEqual(report["parent_groups"], [])


if __name__ == "__main__":
    unittest.main()
