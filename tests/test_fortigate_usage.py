# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""FortiGate-specific ACL usage tests."""

import unittest

from analysis_core import find_object_usage
from parsers.fortigate.config import FTGConfig


class TestFortigateUsage(unittest.TestCase):
    """Ensure FortiGate policies are reflected in ACL usage output."""

    def setUp(self):
        self.sample_config = """
config vdom
    edit alpha
        config firewall address
            edit "ADDR_WEB"
                set subnet 10.1.1.10 255.255.255.255
            next
            edit "ADDR_DB"
                set subnet 10.1.1.20 255.255.255.255
            next
        end
        config firewall addrgrp
            edit "WEB-GRP"
                set member "ADDR_WEB"
            next
        end
        config firewall service custom
            edit "HTTP"
                set tcp-portrange 80
            next
            edit "HTTPS"
                set tcp-portrange 443
            next
        end
        config firewall policy
            edit 10
                set name "allow-web"
                set srcintf "port1"
                set dstintf "port2"
                set srcaddr "ADDR_WEB"
                set dstaddr "ADDR_DB"
                set service "HTTP"
                set action accept
            next
            edit 20
                set name "allow-group"
                set srcaddr "WEB-GRP"
                set dstaddr "ADDR_DB"
                set service "HTTPS"
                set action accept
            next
        end
    next
end
"""

    def test_usage_reports_direct_and_indirect_refs(self):
        cfg = FTGConfig(self.sample_config)

        result = find_object_usage(cfg, "ADDR_WEB")

        # Membership should be detected
        self.assertIn("WEB-GRP", result.group_memberships)

        # Direct reference via policy 10 and indirect via policy 20 (group)
        self.assertEqual(len(result.direct_acl_references), 1)
        self.assertEqual(len(result.indirect_acl_references), 1)
        self.assertGreater(result.total_references, 0)

        direct = result.direct_acl_references[0]
        self.assertIn("allow-web", direct["raw"])
        self.assertEqual(direct["action"], "permit")

        indirect = result.indirect_acl_references[0]
        self.assertEqual(indirect.get("via_group"), "WEB-GRP")
        self.assertEqual(indirect["acl"], "allow-group")

    def test_usage_reports_vip_and_vipgrp(self):
        cfg = FTGConfig(
            """
config vdom
    edit alpha
        config firewall vip
            edit "VIP_WEB"
                set extip 203.0.113.10
                set mappedip "10.10.10.10"
            next
        end
        config firewall vipgrp
            edit "VIP_GROUP"
                set member "VIP_WEB"
            next
        end
        config firewall policy
            edit 1
                set name "vip-direct"
                set srcintf "port1"
                set dstintf "port2"
                set srcaddr "all"
                set dstaddr "VIP_WEB"
                set action accept
                set service "HTTP"
            next
            edit 2
                set name "vip-group"
                set srcintf "port1"
                set dstintf "port2"
                set srcaddr "all"
                set dstaddr "VIP_GROUP"
                set action accept
                set service "HTTPS"
            next
        end
    next
end
"""
        )

        # Direct VIP usage
        res_vip = find_object_usage(cfg, "VIP_WEB")
        self.assertGreaterEqual(res_vip.total_references, 1)
        self.assertIn("VIP_GROUP", res_vip.group_memberships)
        self.assertTrue(any("vip-direct" in ref["raw"] for ref in res_vip.direct_acl_references))

        # VIP group usage
        res_group = find_object_usage(cfg, "VIP_GROUP")
        self.assertGreaterEqual(res_group.total_references, 1)
        self.assertTrue(any("vip-group" in ref["raw"] for ref in res_group.direct_acl_references))

    def test_usage_reports_nested_addrgrp(self):
        cfg = FTGConfig(
            """
config vdom
    edit alpha
        config firewall address
            edit "LEAF_HOST"
                set subnet 10.0.0.50 255.255.255.255
            next
        end
        config firewall addrgrp
            edit "INNER_GRP"
                set member "LEAF_HOST"
            next
            edit "OUTER_GRP"
                set member "INNER_GRP"
            next
        end
        config firewall policy
            edit 1
                set name "nested-group-policy"
                set srcintf "port1"
                set dstintf "port2"
                set srcaddr "all"
                set dstaddr "OUTER_GRP"
                set action accept
                set service "HTTP"
            next
        end
    next
end
"""
        )

        res = find_object_usage(cfg, "LEAF_HOST")
        self.assertIn("INNER_GRP", res.group_memberships)
        self.assertIn("OUTER_GRP", res.group_memberships)
        self.assertGreaterEqual(res.total_references, 1)
        self.assertTrue(any("nested-group-policy" in ref["raw"] for ref in res.indirect_acl_references))

    def test_usage_handles_addrgrp_cycle(self):
        cfg = FTGConfig(
            """
config vdom
    edit alpha
        config firewall address
            edit "LEAF"
                set subnet 10.0.0.60 255.255.255.255
            next
        end
        config firewall addrgrp
            edit "A"
                set member "LEAF" "B"
            next
            edit "B"
                set member "A"
            next
        end
        config firewall policy
            edit 1
                set name "cycle-policy"
                set srcintf "port1"
                set dstintf "port2"
                set srcaddr "A"
                set dstaddr "all"
                set action accept
                set service "HTTP"
            next
        end
    next
end
"""
        )

        res = find_object_usage(cfg, "LEAF")
        # Should return quickly without recursion errors
        self.assertIsInstance(res.total_references, int)


if __name__ == "__main__":
    unittest.main()
