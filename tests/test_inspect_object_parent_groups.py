# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Tests for InspectResult.parent_groups via inspect_object() (#96, #97)."""

import unittest
from parsers.cisco.asa.parser import ASAConfig
from analysis_core.inspect import inspect_object, InspectResult

_CFG = """\
object network HOST_A
 host 10.1.1.1
object-group network SERVERS
 network-object object HOST_A
object-group network MANAGERS
 network-object object HOST_A
access-list OUTSIDE_IN extended permit ip host 10.2.2.2 object HOST_A
"""


class TestInspectObject(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = ASAConfig(_CFG)

    def test_parent_groups_forwarded(self):
        result = inspect_object(self.cfg, "HOST_A")
        self.assertIsInstance(result, InspectResult)
        self.assertEqual(set(result.parent_groups), {"MANAGERS", "SERVERS"})

    def test_total_rules_derived(self):
        result = inspect_object(self.cfg, "HOST_A")
        self.assertEqual(result.total_rules, 1)
        self.assertEqual(result.total_rules, len(result.matching_rules))

    def test_ip_target_has_empty_parent_groups(self):
        result = inspect_object(self.cfg, "10.1.1.1")
        self.assertEqual(result.parent_groups, [])


if __name__ == "__main__":
    unittest.main()
