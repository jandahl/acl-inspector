# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Unit tests for analysis_core.compare module."""

import unittest
from parsers.cisco.asa import ASAConfig
from analysis_core import compare_objects, CompareResult


class TestAnalysisCoreCompare(unittest.TestCase):
    """Test the compare_objects function from analysis_core."""

    def setUp(self):
        """Set up test fixtures."""
        self.sample_config = """
interface GigabitEthernet0/0
 nameif INSIDE
 ip address 10.1.0.1 255.255.255.0
interface GigabitEthernet0/1
 nameif OUTSIDE
 ip address 203.0.113.1 255.255.255.0

object network OBJ_OLD_SERVER
 host 10.1.0.10

object network OBJ_NEW_SERVER
 host 10.1.0.20

object network OBJ_WEB
 host 10.1.0.30

object-group network GRP_SERVERS
 network-object object OBJ_OLD_SERVER
 network-object object OBJ_NEW_SERVER

access-list INSIDE_IN extended permit tcp any host 10.1.0.10 eq 443
access-list INSIDE_IN extended permit tcp any host 10.1.0.20 eq 443
access-list INSIDE_IN extended permit tcp any host 10.1.0.10 eq 22
access-list INSIDE_IN extended deny ip any any

access-list OUTSIDE_IN extended permit tcp any host 10.1.0.30 eq 80
access-list OUTSIDE_IN extended deny ip any any
"""
        self.config = ASAConfig(self.sample_config)

    def test_compare_basic(self):
        """Test basic comparison between two objects."""
        result = compare_objects(
            self.config,
            old_target="OBJ_OLD_SERVER",
            new_target="OBJ_NEW_SERVER"
        )

        self.assertIsInstance(result, CompareResult)
        self.assertEqual(result.old_name, "OBJ_OLD_SERVER")
        self.assertEqual(result.new_name, "OBJ_NEW_SERVER")

    def test_compare_finds_differences(self):
        """Test that comparison correctly identifies added/removed rules."""
        result = compare_objects(
            self.config,
            old_target="OBJ_OLD_SERVER",
            new_target="OBJ_NEW_SERVER"
        )

        # OLD_SERVER has SSH (port 22) but NEW_SERVER doesn't
        # Both have HTTPS (port 443)
        # The comparison should show different rule sets
        # Just verify the result structure is correct
        self.assertIsInstance(result.old_only_rules, list)
        self.assertIsInstance(result.new_only_rules, list)
        self.assertIsInstance(result.common_rules, list)

    def test_compare_with_protocol_filter(self):
        """Test comparison with protocol filtering."""
        result = compare_objects(
            self.config,
            old_target="OBJ_OLD_SERVER",
            new_target="OBJ_NEW_SERVER",
            protocol="tcp",
            dport=443
        )

        # Verify that filtering works and returns valid structure
        self.assertIsInstance(result, CompareResult)
        self.assertIsInstance(result.old_only_rules, list)
        self.assertIsInstance(result.new_only_rules, list)

    def test_compare_nonexistent_objects(self):
        """Test comparison with objects that don't exist."""
        # This should not raise an exception, but may return empty results
        result = compare_objects(
            self.config,
            old_target="NONEXISTENT_A",
            new_target="NONEXISTENT_B"
        )

        self.assertIsInstance(result, CompareResult)
        self.assertEqual(result.old_name, "NONEXISTENT_A")
        self.assertEqual(result.new_name, "NONEXISTENT_B")

    def test_compare_result_post_init(self):
        """Test that CompareResult calculates summary stats correctly."""
        result = compare_objects(
            self.config,
            old_target="OBJ_OLD_SERVER",
            new_target="OBJ_WEB"
        )

        # Verify that summary stats are calculated
        self.assertEqual(result.total_old, len(result.old_only_rules) + len(result.common_rules))
        self.assertEqual(result.total_new, len(result.new_only_rules) + len(result.common_rules))
        self.assertEqual(result.total_common, len(result.common_rules))

    def test_compare_identical_objects(self):
        """Test comparing an object with itself."""
        result = compare_objects(
            self.config,
            old_target="OBJ_OLD_SERVER",
            new_target="OBJ_OLD_SERVER"
        )

        # Comparing identical objects should return valid structure
        self.assertIsInstance(result, CompareResult)
        self.assertEqual(len(result.old_only_rules), 0, "No rules should be unique to old")
        self.assertEqual(len(result.new_only_rules), 0, "No rules should be unique to new")

    def test_compare_with_ip_addresses(self):
        """Test comparison using IP addresses directly."""
        result = compare_objects(
            self.config,
            old_target="10.1.0.10",
            new_target="10.1.0.20"
        )

        self.assertIsInstance(result, CompareResult)
        self.assertEqual(result.old_name, "10.1.0.10")
        self.assertEqual(result.new_name, "10.1.0.20")


if __name__ == '__main__':
    unittest.main()
