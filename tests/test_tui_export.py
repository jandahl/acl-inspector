# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Tests for TUI export functionality."""

import unittest
import json
import csv
import tempfile
from pathlib import Path
from datetime import datetime


class TestExportManager(unittest.TestCase):
    """Test the ExportManager utility class."""

    def setUp(self):
        """Set up test fixtures."""
        from tui.utils.export import ExportManager
        self.export_mgr = ExportManager()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_export_to_json(self):
        """Test JSON export."""
        from tui.utils.export import ExportManager

        test_data = {
            "name": "TestObject",
            "type": "object",
            "detail": "Test detail",
            "count": 5
        }

        filepath = Path(self.temp_dir) / "test.json"
        ExportManager.export_to_json(test_data, str(filepath))

        self.assertTrue(filepath.exists())
        with open(filepath, 'r') as f:
            loaded_data = json.load(f)
        self.assertEqual(loaded_data["name"], "TestObject")
        self.assertEqual(loaded_data["count"], 5)

    def test_export_to_text(self):
        """Test plain text export."""
        from tui.utils.export import ExportManager

        test_content = "Line 1\nLine 2\nLine 3"
        filepath = Path(self.temp_dir) / "test.txt"
        ExportManager.export_to_text(test_content, str(filepath))

        self.assertTrue(filepath.exists())
        with open(filepath, 'r') as f:
            content = f.read()
        self.assertEqual(content, test_content)

    def test_export_to_csv(self):
        """Test CSV export."""
        from tui.utils.export import ExportManager

        headers = ["Name", "Type", "Count"]
        rows = [
            ["Object1", "network", 5],
            ["Object2", "group", 10],
        ]

        filepath = Path(self.temp_dir) / "test.csv"
        ExportManager.export_to_csv(headers, rows, str(filepath))

        self.assertTrue(filepath.exists())
        with open(filepath, 'r') as f:
            reader = csv.reader(f)
            lines = list(reader)
        self.assertEqual(lines[0], headers)
        self.assertEqual(lines[1], ["Object1", "network", "5"])
        self.assertEqual(len(lines), 3)  # Header + 2 rows

    def test_get_export_filename(self):
        """Test filename generation."""
        from tui.utils.export import ExportManager

        filename = ExportManager.get_export_filename("inspect", "TestObject", "json")

        self.assertIn("acl_export_inspect", filename)
        self.assertIn("TestObject", filename)
        self.assertTrue(filename.endswith(".json"))
        # Should include timestamp
        self.assertIn(datetime.now().strftime("%Y%m%d"), filename)

    def test_get_export_filename_sanitization(self):
        """Test filename sanitization for special characters."""
        from tui.utils.export import ExportManager

        filename = ExportManager.get_export_filename("inspect", "Test/Object:Name", "json")

        # Special characters should be replaced
        self.assertIn("Test_Object_Name", filename)
        self.assertNotIn("/", filename)
        self.assertNotIn(":", filename)

    def test_format_details_for_export(self):
        """Test formatting object details for export."""
        from tui.utils.export import ExportManager

        obj = {
            "name": "TestObject",
            "type": "object",
            "detail": "Test detail",
            "source_file": "test.conf"
        }

        export_data = ExportManager.format_details_for_export(obj, None)

        self.assertEqual(export_data["name"], "TestObject")
        self.assertEqual(export_data["type"], "object")
        self.assertEqual(export_data["detail"], "Test detail")
        self.assertEqual(export_data["source_file"], "test.conf")
        self.assertIn("exported_at", export_data)

    def test_format_inspect_for_csv(self):
        """Test formatting inspect results for CSV."""
        from tui.utils.export import ExportManager

        # Create a mock InspectResult
        class MockInspectResult:
            def __init__(self):
                self.matching_rules = [
                    {
                        "acl": "outside_in",
                        "action": "permit",
                        "protocol": "tcp",
                        "src": "10.0.0.1",
                        "dst": "192.168.1.1",
                        "port": "443",
                        "raw": "access-list outside_in permit tcp 10.0.0.1 192.168.1.1 eq 443"
                    }
                ]

        result = MockInspectResult()
        headers, rows = ExportManager.format_inspect_for_csv(result)

        self.assertEqual(headers[0], "ACL")
        self.assertEqual(headers[1], "Action")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "outside_in")
        self.assertEqual(rows[0][1], "permit")

    def test_format_compare_for_csv(self):
        """Test formatting compare results for CSV."""
        from tui.utils.export import ExportManager

        # Create a mock CompareResult
        class MockCompareResult:
            def __init__(self):
                self.old_only_rules = [
                    {
                        "acl": "test",
                        "action": "deny",
                        "protocol": "tcp",
                        "src": "any",
                        "dst": "any",
                        "port": "80",
                        "raw": "access-list test deny tcp any any eq 80"
                    }
                ]
                self.new_only_rules = [
                    {
                        "acl": "test",
                        "action": "permit",
                        "protocol": "tcp",
                        "src": "any",
                        "dst": "any",
                        "port": "443",
                        "raw": "access-list test permit tcp any any eq 443"
                    }
                ]
                self.common_rules = []

        result = MockCompareResult()
        headers, rows = ExportManager.format_compare_for_csv(result)

        self.assertEqual(headers[0], "Status")
        self.assertEqual(len(rows), 2)  # 1 removed + 1 added
        self.assertEqual(rows[0][0], "REMOVED")
        self.assertEqual(rows[1][0], "ADDED")

    def test_format_usage_for_csv(self):
        """Test formatting ACL usage results for CSV."""
        from tui.utils.export import ExportManager

        # Create a mock UsageResult matching the actual structure
        class MockUsageResult:
            def __init__(self):
                self.object_name = "TestObject"
                self.direct_acl_references = [
                    {
                        "acl": "outside_in",
                        "action": "permit",
                        "line": 10,
                        "raw": "access-list outside_in permit tcp any any"
                    }
                ]
                self.group_memberships = ["WebServers"]
                self.indirect_acl_references = [
                    {
                        "acl": "inside_out",
                        "action": "deny",
                        "line": 20,
                        "raw": "access-list inside_out deny ip any any",
                        "via_group": "WebServers"
                    }
                ]
                self.total_references = 3

        result = MockUsageResult()
        headers, rows = ExportManager.format_usage_for_csv(result)

        self.assertEqual(headers[0], "Reference Type")
        self.assertEqual(len(rows), 3)  # 1 direct + 1 group + 1 indirect
        self.assertEqual(rows[0][0], "Direct")
        self.assertEqual(rows[0][1], "outside_in")
        self.assertEqual(rows[1][0], "Group")
        self.assertEqual(rows[1][1], "WebServers")


class TestExportIntegration(unittest.TestCase):
    """Integration tests for export functionality."""

    def test_export_screen_creation(self):
        """Test that export screen can be created."""
        try:
            from tui.screens.export_screen import ExportScreen

            def mock_callback(format_type, filename):
                pass

            screen = ExportScreen(
                tab_name="Details",
                object_name="TestObject",
                data={},
                export_callback=mock_callback
            )

            self.assertEqual(screen.tab_name, "Details")
            self.assertEqual(screen.object_name, "TestObject")
        except ImportError:
            self.skipTest("textual not installed")


if __name__ == "__main__":
    unittest.main()
