# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Parity tests: AdvancedFTGConfig must produce identical output to FTGConfig."""

import ipaddress
import unittest
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "configs" / "fortigate"


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


try:
    import ciscoconfparse2  # noqa: F401 — explicit check so HAS_ADVANCED reflects library availability
    from parsers.fortigate.advanced_parser import AdvancedFTGConfig
    HAS_ADVANCED = True
except ImportError:
    HAS_ADVANCED = False

requires_advanced = unittest.skipUnless(HAS_ADVANCED, "ciscoconfparse2 not installed")


@requires_advanced
class TestAdvancedFTGParityAddresses(unittest.TestCase):
    """AdvancedFTGConfig address/group/VIP parsing matches FTGConfig."""

    def setUp(self):
        from parsers.fortigate.config import FTGConfig
        text = load_fixture("sample.conf")
        self.base = FTGConfig(text)
        self.adv = AdvancedFTGConfig(text)

    def test_addresses_match(self):
        self.assertEqual(self.adv.addresses, self.base.addresses)

    def test_addrgrps_match(self):
        self.assertEqual(self.adv.addrgrps, self.base.addrgrps)

    def test_services_match(self):
        self.assertEqual(self.adv.services, self.base.services)

    def test_service_groups_match(self):
        self.assertEqual(self.adv.service_groups, self.base.service_groups)

    def test_vips_match(self):
        self.assertEqual(self.adv.vips, self.base.vips)

    def test_vipgrps_match(self):
        self.assertEqual(self.adv.vipgrps, self.base.vipgrps)

    def test_zones_match(self):
        self.assertEqual(self.adv.zones, self.base.zones)

    def test_interfaces_match(self):
        self.assertEqual(self.adv.interfaces, self.base.interfaces)

    def test_ippools_match(self):
        self.assertEqual(self.adv.ippools, self.base.ippools)

    def test_central_snat_match(self):
        self.assertEqual(self.adv.central_snat_map, self.base.central_snat_map)

    def test_policies_count_match(self):
        self.assertEqual(len(self.adv.policies), len(self.base.policies))

    def test_policy_ids_match(self):
        adv_ids = [p.get('id') for p in self.adv.policies]
        base_ids = [p.get('id') for p in self.base.policies]
        self.assertEqual(adv_ids, base_ids)

    def test_flatten_policies_parity(self):
        base_flat = self.base.flatten_policies()
        adv_flat = self.adv.flatten_policies()
        self.assertEqual(len(adv_flat), len(base_flat))
        for i, (b, a) in enumerate(zip(base_flat, adv_flat)):
            for key in ('policy_id', 'action', 'src', 'dst', 'nat'):
                self.assertEqual(a.get(key), b.get(key),
                    msg=f"policy[{i}].{key}: adv={a.get(key)!r} base={b.get(key)!r}")

    def test_resolve_addr_token_object_name(self):
        result = self.adv.resolve_addr_token('WEB_SERVER')
        self.assertIn(ipaddress.ip_network('10.1.1.10/32'), result)

    def test_resolve_addr_token_addrgrp(self):
        result = self.adv.resolve_addr_token('BACKEND_SERVERS')
        self.assertIn(ipaddress.ip_network('10.1.1.10/32'), result)
        self.assertIn(ipaddress.ip_network('10.1.1.20/32'), result)

    def test_resolve_addr_token_vip(self):
        result = self.adv.resolve_addr_token('VIP_WEB')
        self.assertIn(ipaddress.ip_address('203.0.113.1'), result)

    def test_ip_to_objects_reverse_index(self):
        net = ipaddress.ip_network('10.1.1.10/32')
        self.assertIn(net, self.adv.ip_to_objects)
        self.assertIn('WEB_SERVER', self.adv.ip_to_objects[net])

    def test_deny_policy_parsed(self):
        deny = [p for p in self.adv.policies if p.get('action') == 'deny']
        self.assertEqual(len(deny), 1)
        self.assertEqual(deny[0]['id'], '100')


@requires_advanced
class TestAdvancedFTGBasicInstantiation(unittest.TestCase):
    """AdvancedFTGConfig instantiates successfully when ciscoconfparse2 is present."""

    def test_available(self):
        text = load_fixture("sample.conf")
        cfg = AdvancedFTGConfig(text)
        self.assertIsNotNone(cfg)


@requires_advanced
class TestAdvancedFTGAdvancedFixture(unittest.TestCase):
    """Parity on the richer advanced_policy_nat fixture."""

    def setUp(self):
        from parsers.fortigate.config import FTGConfig
        text = load_fixture("advanced_policy_nat.conf")
        self.base = FTGConfig(text)
        self.adv = AdvancedFTGConfig(text)

    def test_addresses_match(self):
        self.assertEqual(self.adv.addresses, self.base.addresses)

    def test_services_match(self):
        self.assertEqual(self.adv.services, self.base.services)

    def test_vips_match(self):
        self.assertEqual(self.adv.vips, self.base.vips)

    def test_zones_match(self):
        self.assertEqual(self.adv.zones, self.base.zones)

    def test_interfaces_match(self):
        self.assertEqual(self.adv.interfaces, self.base.interfaces)

    def test_ippools_match(self):
        self.assertEqual(self.adv.ippools, self.base.ippools)

    def test_central_snat_match(self):
        self.assertEqual(self.adv.central_snat_map, self.base.central_snat_map)

    def test_flatten_policies_parity(self):
        base_flat = self.base.flatten_policies()
        adv_flat = self.adv.flatten_policies()
        self.assertEqual(len(adv_flat), len(base_flat))
        for i, (b, a) in enumerate(zip(base_flat, adv_flat)):
            for key in ('policy_id', 'action', 'nat'):
                self.assertEqual(a.get(key), b.get(key),
                    msg=f"policy[{i}].{key}: adv={a.get(key)!r} base={b.get(key)!r}")


if __name__ == '__main__':
    unittest.main()
