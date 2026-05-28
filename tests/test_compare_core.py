# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Regression tests for analysis_core.compare_objects across vendors."""

import unittest

from analysis_core import compare_objects, CompareResult
from parsers.cisco.asa import ASAConfig
from parsers.fortigate.config import FTGConfig


class TestCompareCore(unittest.TestCase):
    """Ensure compare_objects works for ASA and FortiGate."""

    def test_compare_asa_objects(self):
        cfg = ASAConfig(
            """
object network SRC1
 host 192.0.2.10
object network OLD_HOST
 host 10.0.0.1
object network NEW_HOST
 host 10.0.0.2

access-list ACL1 extended permit tcp host 192.0.2.10 host 10.0.0.1 eq 80
access-list ACL1 extended permit tcp host 192.0.2.10 host 10.0.0.2 eq 443
"""
        )

        result = compare_objects(cfg, "OLD_HOST", "NEW_HOST")
        self.assertIsInstance(result, CompareResult)
        self.assertEqual(result.old_name, "OLD_HOST")
        self.assertEqual(result.new_name, "NEW_HOST")
        self.assertEqual(len(result.old_only_rules), 1)
        self.assertEqual(len(result.new_only_rules), 1)
        self.assertEqual(result.total_old, len(result.old_only_rules))
        self.assertEqual(result.total_new, len(result.new_only_rules))

    def test_compare_fortigate_objects(self):
        cfg = FTGConfig(
            """
config vdom
    edit alpha
        config firewall address
            edit "SRC_TRUST"
                set subnet 192.0.2.0 255.255.255.0
            next
            edit "OLD_WEB"
                set subnet 10.10.10.10 255.255.255.255
            next
            edit "NEW_WEB"
                set subnet 10.10.10.20 255.255.255.255
            next
        end
        config firewall policy
            edit 1
                set name "web-old"
                set srcintf "port1"
                set dstintf "port2"
                set srcaddr "SRC_TRUST"
                set dstaddr "OLD_WEB"
                set action accept
                set service "HTTP"
            next
            edit 2
                set name "web-new"
                set srcintf "port1"
                set dstintf "port2"
                set srcaddr "SRC_TRUST"
                set dstaddr "NEW_WEB"
                set action accept
                set service "HTTP"
            next
        end
    next
end
"""
        )

        result = compare_objects(cfg, "OLD_WEB", "NEW_WEB")
        self.assertIsInstance(result, CompareResult)
        # Expect one removal, one addition, no common
        self.assertEqual(len(result.old_only_rules), 1)
        self.assertEqual(len(result.new_only_rules), 1)
        self.assertEqual(len(result.common_rules), 0)
        self.assertEqual(result.total_old, 1)
        self.assertEqual(result.total_new, 1)


if __name__ == "__main__":
    unittest.main()
