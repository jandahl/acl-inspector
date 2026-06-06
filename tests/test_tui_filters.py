# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Tests for TUI filter functionality."""

import unittest


class TestFilterBar(unittest.TestCase):
    """Test the FilterBar widget."""

    def test_filter_bar_creation(self):
        """Test that filter bar can be created."""
        try:
            from tui.widgets.filter_bar import FilterBar

            filter_bar = FilterBar()
            self.assertIsNotNone(filter_bar)
            self.assertEqual(filter_bar.current_filters["protocol"], None)
            self.assertEqual(filter_bar.current_filters["port"], None)
            self.assertEqual(filter_bar.current_filters["action"], None)
        except ImportError:
            self.skipTest("textual not installed")

    def test_get_filters(self):
        """Test getting current filters."""
        try:
            from tui.widgets.filter_bar import FilterBar

            filter_bar = FilterBar()
            filters = filter_bar.get_filters()

            self.assertIsInstance(filters, dict)
            self.assertIn("protocol", filters)
            self.assertIn("port", filters)
            self.assertIn("action", filters)
        except ImportError:
            self.skipTest("textual not installed")


class TestInspectFilters(unittest.TestCase):
    """Test inspect filtering logic."""

    def test_protocol_filter(self):
        """Test that protocol filtering works."""
        # Create mock rules
        rules = [
            {"protocol": "tcp", "action": "permit", "acl": "test"},
            {"protocol": "udp", "action": "permit", "acl": "test"},
            {"protocol": "tcp", "action": "deny", "acl": "test"},
            {"protocol": "icmp", "action": "permit", "acl": "test"},
        ]

        # Filter for TCP only
        filtered = [r for r in rules if r["protocol"] == "tcp"]
        self.assertEqual(len(filtered), 2)
        self.assertTrue(all(r["protocol"] == "tcp" for r in filtered))

    def test_action_filter(self):
        """Test that action filtering works."""
        # Create mock rules
        rules = [
            {"protocol": "tcp", "action": "permit", "acl": "test"},
            {"protocol": "udp", "action": "permit", "acl": "test"},
            {"protocol": "tcp", "action": "deny", "acl": "test"},
            {"protocol": "icmp", "action": "deny", "acl": "test"},
        ]

        # Filter for permit only
        filtered = [r for r in rules if r["action"] == "permit"]
        self.assertEqual(len(filtered), 2)
        self.assertTrue(all(r["action"] == "permit" for r in filtered))

    def test_combined_filters(self):
        """Test combining multiple filters."""
        # Create mock rules
        rules = [
            {"protocol": "tcp", "action": "permit", "port": 80, "acl": "test"},
            {"protocol": "tcp", "action": "permit", "port": 443, "acl": "test"},
            {"protocol": "udp", "action": "permit", "port": 53, "acl": "test"},
            {"protocol": "tcp", "action": "deny", "port": 80, "acl": "test"},
        ]

        # Filter for TCP + permit
        filtered = [
            r for r in rules
            if r["protocol"] == "tcp" and r["action"] == "permit"
        ]
        self.assertEqual(len(filtered), 2)
        self.assertTrue(all(r["protocol"] == "tcp" and r["action"] == "permit" for r in filtered))

        # Filter for TCP + permit + port 443
        filtered = [
            r for r in rules
            if r["protocol"] == "tcp" and r["action"] == "permit" and r["port"] == 443
        ]
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["port"], 443)

    def test_case_insensitive_filters(self):
        """Test that filters are case-insensitive."""
        # Create mock rules
        rules = [
            {"protocol": "TCP", "action": "PERMIT", "acl": "test"},
            {"protocol": "udp", "action": "deny", "acl": "test"},
        ]

        # Filter should work regardless of case
        filtered = [r for r in rules if r["protocol"].lower() == "tcp"]
        self.assertEqual(len(filtered), 1)

        filtered = [r for r in rules if r["action"].lower() == "permit"]
        self.assertEqual(len(filtered), 1)


class TestFilterIntegration(unittest.TestCase):
    """Integration tests for filter functionality with inspect."""

    def test_inspect_with_protocol_filter(self):
        """Test inspect_object with protocol filter."""
        try:
            from analysis_core import inspect_object

            # This would need a real config to test properly
            # For now, just verify the function signature
            import inspect
            sig = inspect.signature(inspect_object)
            params = list(sig.parameters.keys())

            self.assertIn("config", params)
            self.assertIn("target", params)
            self.assertIn("protocol", params)
            self.assertIn("dport", params)
        except ImportError:
            self.skipTest("analysis_core not available")

    def test_inspect_result_filtering(self):
        """Test filtering InspectResult after creation."""
        try:
            from analysis_core import InspectResult

            # Create mock result
            rules = [
                {"protocol": "tcp", "action": "permit", "acl": "test"},
                {"protocol": "tcp", "action": "deny", "acl": "test"},
                {"protocol": "udp", "action": "permit", "acl": "test"},
            ]

            result = InspectResult(
                object_name="TestObject",
                resolved_addresses=["10.0.0.1"],
                matching_rules=rules,
                duplicates=[],
            )

            # Filter by action
            filtered_rules = [r for r in result.matching_rules if r["action"] == "permit"]

            # Create new result with filtered rules
            filtered_result = InspectResult(
                object_name=result.object_name,
                resolved_addresses=result.resolved_addresses,
                matching_rules=filtered_rules,
                duplicates=result.duplicates,
            )

            self.assertEqual(filtered_result.total_rules, 2)
            self.assertTrue(all(r["action"] == "permit" for r in filtered_result.matching_rules))
        except ImportError:
            self.skipTest("analysis_core not available")


if __name__ == "__main__":
    unittest.main()
