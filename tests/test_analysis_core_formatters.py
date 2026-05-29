# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Unit tests for analysis_core.formatters module."""

import unittest
from parsers.cisco.asa import ASAConfig
from analysis_core import inspect_object, compare_objects, InspectResult

# Skip all tests if rich is not available
try:
    from analysis_core import (
        format_inspect_rich,
        format_compare_rich,
        format_inspect_json,
        format_compare_json,
    )
    from rich.console import Group
    from rich.table import Table
    from rich.panel import Panel
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


@unittest.skipUnless(RICH_AVAILABLE, "rich module not installed")
class TestAnalysisCoreFormatters(unittest.TestCase):
    """Test the formatting functions from analysis_core."""

    def setUp(self):
        """Set up test fixtures."""
        self.sample_config = """
interface GigabitEthernet0/0
 nameif INSIDE
 ip address 10.1.0.1 255.255.255.0

object network OBJ_SERVER_A
 host 10.1.0.10

object network OBJ_SERVER_B
 host 10.1.0.20

access-list INSIDE_IN extended permit tcp any host 10.1.0.10 eq 443
access-list INSIDE_IN extended permit tcp any host 10.1.0.10 eq 22
access-list INSIDE_IN extended permit tcp any host 10.1.0.20 eq 443
access-list INSIDE_IN extended deny ip any any
"""
        self.config = ASAConfig(self.sample_config)

    def test_format_inspect_rich_returns_renderable(self):
        """Test that format_inspect_rich returns a Rich renderable."""
        result = inspect_object(self.config, "OBJ_SERVER_A")
        formatted = format_inspect_rich(result)

        # Should return a Rich Group
        self.assertIsInstance(formatted, Group)

    def test_format_inspect_rich_contains_content(self):
        """Test that formatted output contains expected content."""
        result = inspect_object(self.config, "OBJ_SERVER_A")
        formatted = format_inspect_rich(result)

        # Group should contain renderables (Panel, Table, etc.)
        self.assertGreater(len(formatted.renderables), 0, "Should contain at least one renderable")

    def test_format_inspect_rich_handles_set_endpoints(self):
        """Ensure formatting tolerates set-based endpoints."""
        rules = [
            {
                "acl": "INSIDE_IN",
                "action": "permit",
                "src": {"10.0.0.0/24"},
                "dst": {"192.168.0.10"},
                "proto": "tcp",
            }
        ]
        result = InspectResult(
            object_name="OBJ_SERVER_A",
            resolved_addresses=["10.1.0.10"],
            matching_rules=rules,
            duplicates=[],
            total_rules=len(rules),
        )
        formatted = format_inspect_rich(result)
        self.assertIsInstance(formatted, Group)

    def test_format_service_handles_fortigate_rule(self):
        """Ensure Forti-style svc dict renders meaningfully."""
        from analysis_core.formatters import _format_service

        rule = {
            "svc": {
                "proto": "tcp",
                "dst_ports": [("range", (80, 81)), ("eq", (443, 443))],
                "dst_service_groups": {"HTTP-HTTPS"},
                "dst_service_objects": {"HTTPS"},
            }
        }
        text = _format_service(rule)
        self.assertIn("tcp", text)
        self.assertIn("80-81", text)
        self.assertIn("443", text)
        self.assertIn("group:HTTP-HTTPS", text)

    def test_format_compare_rich_returns_renderable(self):
        """Test that format_compare_rich returns a Rich renderable."""
        result = compare_objects(self.config, "OBJ_SERVER_A", "OBJ_SERVER_B")
        formatted = format_compare_rich(result)

        # Should return a Rich Group
        self.assertIsInstance(formatted, Group)

    def test_format_compare_rich_contains_summary(self):
        """Test that comparison output contains summary."""
        result = compare_objects(self.config, "OBJ_SERVER_A", "OBJ_SERVER_B")
        formatted = format_compare_rich(result)

        # Should contain at least the summary panel
        self.assertGreater(len(formatted.renderables), 0, "Should contain summary panel")

    def test_format_inspect_json_returns_dict(self):
        """Test that format_inspect_json returns a dictionary."""
        result = inspect_object(self.config, "OBJ_SERVER_A")
        formatted = format_inspect_json(result)

        self.assertIsInstance(formatted, dict)
        self.assertIn("object_name", formatted)
        self.assertIn("resolved_addresses", formatted)
        self.assertIn("total_rules", formatted)
        self.assertIn("duplicates", formatted)
        self.assertIn("matching_rules", formatted)

    def test_format_inspect_json_has_correct_values(self):
        """Test that JSON format contains correct values."""
        result = inspect_object(self.config, "OBJ_SERVER_A")
        formatted = format_inspect_json(result)

        self.assertEqual(formatted["object_name"], "OBJ_SERVER_A")
        self.assertIsInstance(formatted["resolved_addresses"], list)
        self.assertIsInstance(formatted["total_rules"], int)
        self.assertIsInstance(formatted["duplicates"], list)
        self.assertIsInstance(formatted["matching_rules"], list)

    def test_format_compare_json_returns_dict(self):
        """Test that format_compare_json returns a dictionary."""
        result = compare_objects(self.config, "OBJ_SERVER_A", "OBJ_SERVER_B")
        formatted = format_compare_json(result)

        self.assertIsInstance(formatted, dict)
        self.assertIn("old_name", formatted)
        self.assertIn("new_name", formatted)
        self.assertIn("old_only_rules", formatted)
        self.assertIn("new_only_rules", formatted)
        self.assertIn("common_rules", formatted)
        self.assertIn("summary", formatted)

    def test_format_compare_json_summary(self):
        """Test that comparison JSON includes summary statistics."""
        result = compare_objects(self.config, "OBJ_SERVER_A", "OBJ_SERVER_B")
        formatted = format_compare_json(result)

        self.assertIn("summary", formatted)
        summary = formatted["summary"]
        self.assertIn("removed", summary)
        self.assertIn("added", summary)
        self.assertIn("common", summary)
        self.assertIsInstance(summary["removed"], int)
        self.assertIsInstance(summary["added"], int)
        self.assertIsInstance(summary["common"], int)

    def test_format_inspect_rich_with_no_rules(self):
        """Test formatting when no rules are found."""
        result = inspect_object(self.config, "NONEXISTENT")
        formatted = format_inspect_rich(result)

        # Should still return a valid renderable even with no rules
        self.assertIsInstance(formatted, Group)

    def test_format_compare_rich_with_no_differences(self):
        """Test formatting when comparing identical objects."""
        result = compare_objects(self.config, "OBJ_SERVER_A", "OBJ_SERVER_A")
        formatted = format_compare_rich(result)

        # Should still return a valid renderable
        self.assertIsInstance(formatted, Group)

    def test_format_inspect_json_serializable(self):
        """Test that JSON output is actually JSON serializable."""
        import json

        result = inspect_object(self.config, "OBJ_SERVER_A")
        formatted = format_inspect_json(result)

        # Should be able to serialize to JSON without errors
        try:
            json_str = json.dumps(formatted)
            self.assertIsInstance(json_str, str)
        except (TypeError, ValueError) as e:
            self.fail(f"JSON formatting failed: {e}")

    def test_format_compare_json_serializable(self):
        """Test that comparison JSON is serializable."""
        import json

        result = compare_objects(self.config, "OBJ_SERVER_A", "OBJ_SERVER_B")
        formatted = format_compare_json(result)

        # Should be able to serialize to JSON
        try:
            json_str = json.dumps(formatted)
            self.assertIsInstance(json_str, str)
        except (TypeError, ValueError) as e:
            self.fail(f"JSON formatting failed: {e}")


if __name__ == '__main__':
    unittest.main()
