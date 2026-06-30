# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Coverage for the ciscoconfparse2-backed FTGConfig parser.

ciscoconfparse2 is the single FortiGate engine now (the AdvancedFTGConfig
subclass was merged into FTGConfig), so these tests exercise FTGConfig directly
on the sample fixtures and assert resolution/index/routing behaviour.
"""

import ipaddress
import unittest
from pathlib import Path

from parsers.fortigate.config import FTGConfig

FIXTURES = Path(__file__).parent / "fixtures" / "configs" / "fortigate"


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


class TestFTGSampleFixture(unittest.TestCase):
    """FTGConfig parses the sample fixture's objects/groups/VIPs/policies."""

    def setUp(self):
        self.cfg = FTGConfig(load_fixture("sample.conf"))

    def test_addresses_parsed(self):
        self.assertIn('WEB_SERVER', self.cfg.addresses)

    def test_addrgrps_parsed(self):
        self.assertIn('BACKEND_SERVERS', self.cfg.addrgrps)

    def test_resolve_addr_token_object_name(self):
        result = self.cfg.resolve_addr_token('WEB_SERVER')
        self.assertIn(ipaddress.ip_network('10.1.1.10/32'), result)

    def test_resolve_addr_token_addrgrp(self):
        result = self.cfg.resolve_addr_token('BACKEND_SERVERS')
        self.assertIn(ipaddress.ip_network('10.1.1.10/32'), result)
        self.assertIn(ipaddress.ip_network('10.1.1.20/32'), result)

    def test_resolve_addr_token_vip(self):
        result = self.cfg.resolve_addr_token('VIP_WEB')
        self.assertIn(ipaddress.ip_address('203.0.113.1'), result)

    def test_ip_to_objects_reverse_index(self):
        net = ipaddress.ip_network('10.1.1.10/32')
        self.assertIn(net, self.cfg.ip_to_objects)
        self.assertIn('WEB_SERVER', self.cfg.ip_to_objects[net])

    def test_deny_policy_parsed(self):
        deny = [p for p in self.cfg.policies if p.get('action') == 'deny']
        self.assertEqual(len(deny), 1)
        self.assertEqual(deny[0]['id'], '100')

    def test_flatten_policies_non_empty(self):
        flat = self.cfg.flatten_policies()
        self.assertTrue(flat)
        for entry in flat:
            self.assertIn('action', entry)
            self.assertIn('src', entry)
            self.assertIn('dst', entry)


class TestFTGBasicInstantiation(unittest.TestCase):

    def test_available(self):
        cfg = FTGConfig(load_fixture("sample.conf"))
        self.assertIsNotNone(cfg)

    def test_empty_config_does_not_crash(self):
        cfg = FTGConfig("")
        self.assertEqual(cfg.addresses, {})
        self.assertEqual(cfg.policies, [])

    def test_explicit_vdom_arg_parses_correctly(self):
        """vdom= exercises the textwrap.dedent path on the VDOM-nested fixture."""
        cfg = FTGConfig(load_fixture("advanced_policy_nat.conf"), vdom="root")
        self.assertEqual(cfg.vdom, "root")
        self.assertTrue(cfg.addresses)
        self.assertTrue(cfg.policies)


class TestFTGAdvancedFixture(unittest.TestCase):
    """Parsing the richer advanced_policy_nat fixture."""

    def setUp(self):
        self.cfg = FTGConfig(load_fixture("advanced_policy_nat.conf"))

    def test_addresses_parsed(self):
        self.assertTrue(self.cfg.addresses)

    def test_vips_parsed(self):
        # The advanced fixture defines at least one VIP.
        self.assertTrue(self.cfg.vips)

    def test_flatten_policies_carry_nat_flag(self):
        flat = self.cfg.flatten_policies()
        self.assertTrue(flat)
        for entry in flat:
            self.assertIn('nat', entry)


if __name__ == '__main__':
    unittest.main()
