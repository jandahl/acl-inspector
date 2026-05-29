# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""FortiGate parser regression tests."""

import ipaddress
import unittest
from pathlib import Path

from parsers.fortigate.config import FTGConfig
from parsers.fortigate import ir_export


FIXTURES = Path(__file__).parent / "fixtures" / "configs" / "fortigate"


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


class TestFortiGateAdvancedParsing(unittest.TestCase):
    """Validate Forti parser handles interfaces, VIPs, and NAT flags."""

    def setUp(self):
        self.cfg = FTGConfig(load_fixture("advanced_policy_nat.conf"))

    def test_interfaces_and_vips_parsed(self):
        self.assertIn("port1", self.cfg.interfaces)
        port1 = self.cfg.interfaces["port1"]
        self.assertIn("203.0.113.2", port1.get("ip", ""))

        self.assertEqual(self.cfg.interface_zones.get("port1"), "wan-zone")
        self.assertEqual(self.cfg.interface_zones.get("port2"), "lan-zone")

        self.assertIn("WEB-VIP", self.cfg.vips)
        vip = self.cfg.vips["WEB-VIP"]
        self.assertEqual(vip.get("extip"), ["198.51.100.10"])
        self.assertEqual(vip.get("extintf"), "port1")

        self.assertIn("DMZ_VIPS", self.cfg.vipgrps)
        self.assertIn("WEB-VIP", self.cfg.vipgrps["DMZ_VIPS"])

    def test_policy_nat_flags(self):
        policy = next((p for p in self.cfg.policies if p.get("id") == "20"), None)
        self.assertIsNotNone(policy)
        self.assertTrue(policy.get("nat"))
        self.assertTrue(policy.get("ippool"))
        self.assertEqual(policy.get("poolname"), ["OUT_POOL"])
        self.assertEqual(policy.get("srcintf"), ["port2"])
        self.assertEqual(policy.get("dstintf"), ["port1"])

    def test_vip_group_resolves_to_external_ip(self):
        resolved = self.cfg.resolve_addr_token("DMZ_VIPS")
        literals = {str(item) for item in resolved if not isinstance(item, str)}
        self.assertIn(str(ipaddress.ip_address("198.51.100.10")), literals)

    def test_ir_export_includes_interfaces_and_nats(self):
        device = ir_export.to_ir(self.cfg, device_name="forti-root")
        self.assertGreaterEqual(len(device.interfaces), 2)

        nat_types = {nat.detail.get("type") for nat in device.nats}
        self.assertIn("vip", nat_types)
        self.assertIn("policy-snat", nat_types)
        self.assertIn("central-snat", nat_types)
        vip_nat = next(nat for nat in device.nats if nat.detail.get("type") == "vip")
        self.assertIn("10", vip_nat.detail.get("policies"))

        policy_acl = next((acl for acl in device.acls if acl.name == "policy"), None)
        self.assertIsNotNone(policy_acl)
        entry = next((e for e in policy_acl.entries if "policy 10" in e.raw), policy_acl.entries[0])
        binding = entry.binding
        self.assertIn("srcintf", binding)
        self.assertIn("dstintf", binding)
        self.assertIn("srczone", binding)
        self.assertIn("dstzone", binding)
        self.assertIn("vip_refs", binding)
        self.assertEqual(binding["vip_refs"], ["WEB-VIP"])


if __name__ == "__main__":
    unittest.main()
