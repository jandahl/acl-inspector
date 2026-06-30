# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Behavioural coverage for the ciscoconfparse2-backed parsing engine.

ciscoconfparse2 is now a core dependency and the single parsing engine, so these
tests exercise the default ASAConfig/FTGConfig directly (there is no longer a
separate "advanced" subclass or a use_external_engines flag). They guard the
parent-child tree-walk behaviour that used to live in the advanced parsers.
"""
import io
import ipaddress
import unittest
from pathlib import Path
from unittest.mock import patch

from parsers.loader import load_config, get_engine

PROJECT_ROOT = Path(__file__).parent.parent


class TestParsingEngine(unittest.TestCase):

    def test_asa_engine_parses_objects(self):
        """ASAConfig resolves network objects correctly (end-to-end)."""
        cfg_text = (
            "object network WEBSERVER\n"
            " host 10.0.0.1\n"
            "access-list TEST extended permit tcp any host 10.0.0.1 eq 443\n"
        )
        cfg = get_engine('asa', cfg_text)
        from parsers.cisco.asa.parser import ASAConfig
        self.assertIsInstance(cfg, ASAConfig)
        self.assertEqual(cfg.resolve_network('WEBSERVER'), {ipaddress.ip_address('10.0.0.1')})

    def test_asa_engine_flatten_acl(self):
        """flatten_acl returns expected entries."""
        cfg_text = (
            "object network WEBSERVER\n"
            " host 10.0.0.1\n"
            "access-list TEST extended permit tcp any host 10.0.0.1 eq 443\n"
        )
        cfg = get_engine('asa', cfg_text)
        entries = cfg.flatten_acl()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['action'], 'permit')
        self.assertIn(ipaddress.ip_address('10.0.0.1'), entries[0]['dst'])

    def test_asa_engine_parses_dynamic_routing(self):
        """router ospf/bgp blocks are captured (a gap in the old advanced engine)."""
        cfg_text = (
            "interface inside\n"
            " nameif inside\n"
            " ip address 10.0.0.1 255.255.255.0\n"
            "router ospf 1\n"
            " router-id 1.1.1.1\n"
            " network 10.0.0.0 255.255.255.0 area 0\n"
            " passive-interface inside\n"
        )
        cfg = get_engine('asa', cfg_text)
        self.assertIn('ospf_1', cfg.dynamic_routing)
        ospf = cfg.dynamic_routing['ospf_1']
        self.assertEqual(ospf['router_id'], '1.1.1.1')
        self.assertEqual(ospf['passive_interfaces'], ['inside'])
        self.assertEqual(ospf['networks'][0]['area'], '0')

    def test_fortigate_engine_parses_policies(self):
        """FTGConfig parses a FortiGate config end-to-end."""
        cfg_text = (
            "config firewall address\n"
            '    edit "HOST_A"\n'
            "        set subnet 10.0.0.1 255.255.255.255\n"
            "    next\n"
            "end\n"
            "config firewall policy\n"
            "    edit 1\n"
            '        set action accept\n'
            '        set srcaddr "HOST_A"\n'
            '        set dstaddr "all"\n'
            '        set service "ALL"\n'
            "    next\n"
            "end\n"
        )
        with patch('sys.stdin', new=io.StringIO(cfg_text)):
            cfg, vendor, _ = load_config("-", vendor='fortigate')
        from parsers.fortigate.config import FTGConfig
        self.assertIsInstance(cfg, FTGConfig)
        self.assertIn('HOST_A', cfg.addresses)
        self.assertEqual(len(cfg.policies), 1)

    def test_default_engine_regression(self):
        """load_config returns a parsed ASAConfig with working resolution."""
        cfg_text = "access-list test permit ip host 1.1.1.1 any"
        with patch('sys.stdin', new=io.StringIO(cfg_text)):
            cfg, vendor, confidence = load_config("-", vendor='asa')
            self.assertEqual(vendor, 'asa')
            from parsers.cisco.asa.parser import ASAConfig
            self.assertIsInstance(cfg, ASAConfig)
            resolved = cfg.resolve_network("1.1.1.1")
            self.assertEqual(resolved, {ipaddress.ip_address("1.1.1.1")})

    def test_engine_acl_ignorecase(self):
        """ACCESS-LIST lines match regardless of case (re_acl IGNORECASE preserved)."""
        cfg_text = "ACCESS-LIST OUTSIDE EXTENDED PERMIT TCP ANY HOST 10.0.0.1 EQ 443\n"
        cfg = get_engine('asa', cfg_text)
        self.assertIn('OUTSIDE', cfg.acls)
        self.assertEqual(len(cfg.acls['OUTSIDE']), 1)

    def test_engine_static_route_keys(self):
        """static_routes carry the keys ir_export/path.py rely on."""
        cfg_text = (
            "interface GigabitEthernet0/0\n"
            " nameif inside\n"
            " ip address 10.0.0.1 255.255.255.0\n"
            "route inside 192.168.1.0 255.255.255.0 10.0.0.254 1\n"
        )
        cfg = get_engine('asa', cfg_text)
        self.assertEqual(len(cfg.static_routes), 1)
        r = cfg.static_routes[0]
        self.assertEqual(r['destination'], '192.168.1.0/24')
        self.assertEqual(r['next_hop'], '10.0.0.254')
        self.assertEqual(r['distance'], 1)
        self.assertIsNone(r['track'])
        self.assertFalse(r['tunneled'])

    def test_engine_static_route_no_metric(self):
        """Route without explicit distance stores distance=None."""
        cfg_text = "route inside 10.10.10.0 255.255.255.0 10.0.0.254\n"
        cfg = get_engine('asa', cfg_text)
        self.assertEqual(len(cfg.static_routes), 1)
        self.assertIsNone(cfg.static_routes[0]['distance'])

    def test_engine_static_route_track_and_tunneled(self):
        """Route with 'track N tunneled' keywords sets both fields."""
        cfg_text = "route outside 0.0.0.0 0.0.0.0 192.0.2.1 1 track 5 tunneled\n"
        cfg = get_engine('asa', cfg_text)
        r = cfg.static_routes[0]
        self.assertEqual(r['distance'], 1)
        self.assertEqual(r['track'], 5)
        self.assertTrue(r['tunneled'])

    def test_engine_static_route_bad_mask_fallback(self):
        """Malformed mask stores raw 'ip/mask' string instead of dropping the route."""
        cfg_text = "route inside 10.0.0.0 notamask 10.0.0.1\n"
        cfg = get_engine('asa', cfg_text)
        self.assertEqual(len(cfg.static_routes), 1)
        self.assertEqual(cfg.static_routes[0]['destination'], '10.0.0.0/notamask')

    def test_engine_static_route_dhcp_nexthop(self):
        """Route with 'dhcp' gateway stores next_hop=None."""
        cfg_text = "route outside 0.0.0.0 0.0.0.0 dhcp\n"
        cfg = get_engine('asa', cfg_text)
        self.assertIsNone(cfg.static_routes[0]['next_hop'])


if __name__ == '__main__':
    unittest.main()
