"""Regression tests for ACL usage bugs.

These tests ensure specific bugs don't reoccur.
"""

import unittest
from analysis_core import find_object_usage, UsageResult


class TestACLUsageRegressions(unittest.TestCase):
    """Regression tests for ACL usage functionality."""

    def test_acl_tuple_format_parsing(self):
        """Regression: ACL entries as (raw_line, line_number) tuples.

        Bug: find_object_usage expected (action, rule_dict) but ASA parser
        returns (raw_line, line_number).

        This test ensures we correctly parse the tuple format.
        """
        # Create a mock config with tuple format ACL entries
        class MockConfig:
            def __init__(self):
                self.network_object_groups = {}
                # ASA parser format: (raw_line, line_number)
                self.acls = {
                    "outside_in": [
                        ("access-list outside_in permit tcp any object WebServer eq 443", 10),
                        ("access-list outside_in deny ip any any", 20),
                    ]
                }

        config = MockConfig()
        result = find_object_usage(config, "WebServer")

        # Should find the direct reference
        self.assertEqual(len(result.direct_acl_references), 1)
        self.assertEqual(result.direct_acl_references[0]['acl'], "outside_in")
        self.assertEqual(result.direct_acl_references[0]['action'], "permit")
        self.assertEqual(result.direct_acl_references[0]['line'], 10)
        self.assertIn("WebServer", result.direct_acl_references[0]['raw'])

    def test_group_member_object_key_parsing(self):
        """Regression: Group members with 'object' key instead of 'name'.

        Bug: find_object_usage looked for 'name' key but ASA parser uses
        'object' key for group member references.

        This test ensures we correctly parse the 'object' key.
        """
        # Create a mock config with 'object' key in group members
        class MockConfig:
            def __init__(self):
                # ASA parser format: {'object': 'object_name'}
                self.network_object_groups = {
                    "WebServers": [
                        {"object": "WebServer1"},
                        {"object": "WebServer2"},
                    ]
                }
                self.acls = {}

        config = MockConfig()
        result = find_object_usage(config, "WebServer1")

        # Should find group membership
        self.assertEqual(len(result.group_memberships), 1)
        self.assertEqual(result.group_memberships[0], "WebServers")

    def test_action_extraction_from_raw_line(self):
        """Test that action (permit/deny) is correctly extracted from raw ACL line.

        Related to bug fix: We need to parse the action from the raw line text
        since tuple format doesn't include it separately.
        """
        class MockConfig:
            def __init__(self):
                self.network_object_groups = {}
                self.acls = {
                    "test_acl": [
                        ("access-list test_acl permit tcp any object TestObj eq 80", 1),
                        ("access-list test_acl deny ip any object TestObj", 2),
                    ]
                }

        config = MockConfig()
        result = find_object_usage(config, "TestObj")

        self.assertEqual(len(result.direct_acl_references), 2)

        # Check permit rule
        permit_rule = result.direct_acl_references[0]
        self.assertEqual(permit_rule['action'], "permit")

        # Check deny rule
        deny_rule = result.direct_acl_references[1]
        self.assertEqual(deny_rule['action'], "deny")

    def test_indirect_references_via_groups(self):
        """Test that indirect ACL references via groups are found correctly.

        This is a comprehensive test ensuring all parts of the bug fix work together.
        """
        class MockConfig:
            def __init__(self):
                # Object is in a group
                self.network_object_groups = {
                    "WebServers": [
                        {"object": "WebServer1"},
                        {"object": "WebServer2"},
                    ]
                }
                # ACL references the group
                self.acls = {
                    "outside_in": [
                        ("access-list outside_in permit tcp any object-group WebServers eq 443", 10),
                    ]
                }

        config = MockConfig()
        result = find_object_usage(config, "WebServer1")

        # Should find group membership
        self.assertEqual(len(result.group_memberships), 1)
        self.assertEqual(result.group_memberships[0], "WebServers")

        # Should find indirect ACL reference
        self.assertEqual(len(result.indirect_acl_references), 1)
        self.assertEqual(result.indirect_acl_references[0]['acl'], "outside_in")
        self.assertEqual(result.indirect_acl_references[0]['via_group'], "WebServers")
        self.assertEqual(result.indirect_acl_references[0]['action'], "permit")

    def test_total_references_calculation(self):
        """Test that total_references is correctly calculated.

        Ensures __post_init__ correctly sums all reference types.
        """
        class MockConfig:
            def __init__(self):
                self.network_object_groups = {
                    "WebServers": [{"object": "WebServer1"}]
                }
                self.acls = {
                    "outside_in": [
                        ("access-list outside_in permit tcp any object WebServer1 eq 80", 1),
                        ("access-list outside_in permit tcp any object-group WebServers eq 443", 2),
                    ]
                }

        config = MockConfig()
        result = find_object_usage(config, "WebServer1")

        # Should have: 1 direct + 1 group + 1 indirect = 3 total
        self.assertEqual(result.total_references, 3)
        self.assertEqual(len(result.direct_acl_references), 1)
        self.assertEqual(len(result.group_memberships), 1)
        self.assertEqual(len(result.indirect_acl_references), 1)


class TestExportUsageResultRegression(unittest.TestCase):
    """Regression tests for UsageResult export functionality."""

    def test_usage_result_has_correct_attributes(self):
        """Regression: Export tried to access non-existent 'acl_usage' attribute.

        Bug: Export functions accessed result.acl_usage but UsageResult has:
        - direct_acl_references
        - group_memberships
        - indirect_acl_references

        This test verifies the actual structure.
        """
        result = UsageResult(
            object_name="TestObject",
            direct_acl_references=[{"acl": "test"}],
            group_memberships=["TestGroup"],
            indirect_acl_references=[{"acl": "test2"}],
            total_references=None  # Will be calculated
        )

        # Verify correct attributes exist
        self.assertTrue(hasattr(result, 'object_name'))
        self.assertTrue(hasattr(result, 'direct_acl_references'))
        self.assertTrue(hasattr(result, 'group_memberships'))
        self.assertTrue(hasattr(result, 'indirect_acl_references'))
        self.assertTrue(hasattr(result, 'total_references'))

        # Verify incorrect attribute does NOT exist
        self.assertFalse(hasattr(result, 'acl_usage'))

    def test_csv_export_uses_correct_attributes(self):
        """Test that CSV export function uses the correct UsageResult attributes."""
        from tui.utils.export import ExportManager

        result = UsageResult(
            object_name="TestObject",
            direct_acl_references=[
                {
                    "acl": "outside_in",
                    "action": "permit",
                    "line": 10,
                    "raw": "access-list outside_in permit tcp any any"
                }
            ],
            group_memberships=["WebServers"],
            indirect_acl_references=[
                {
                    "acl": "inside_out",
                    "action": "deny",
                    "line": 20,
                    "raw": "access-list inside_out deny ip any any",
                    "via_group": "WebServers"
                }
            ],
            total_references=None
        )

        # This should not raise AttributeError
        headers, rows = ExportManager.format_usage_for_csv(result)

        # Verify export works correctly
        self.assertEqual(len(rows), 3)  # 1 direct + 1 group + 1 indirect
        self.assertEqual(headers[0], "Reference Type")

        # Verify data is correct
        self.assertEqual(rows[0][0], "Direct")
        self.assertEqual(rows[0][1], "outside_in")
        self.assertEqual(rows[1][0], "Group")
        self.assertEqual(rows[1][1], "WebServers")

    def test_json_export_structure(self):
        """Test that JSON export returns correct structure."""
        try:
            from analysis_core import format_usage_json
        except ImportError:
            self.skipTest("rich module not installed")

        result = UsageResult(
            object_name="TestObject",
            direct_acl_references=[{"acl": "test"}],
            group_memberships=["TestGroup"],
            indirect_acl_references=[],
            total_references=None
        )

        # Should not raise AttributeError
        try:
            json_data = format_usage_json(result)
        except ImportError as e:
            if "rich module required" in str(e):
                self.skipTest("rich module not installed")
            raise

        # Verify structure
        self.assertIn("object_name", json_data)
        self.assertIn("direct_acl_references", json_data)
        self.assertIn("group_memberships", json_data)
        self.assertIn("indirect_acl_references", json_data)
        self.assertIn("total_references", json_data)
        self.assertIn("summary", json_data)

        # Should NOT have 'acl_usage'
        self.assertNotIn("acl_usage", json_data)


if __name__ == "__main__":
    unittest.main()
