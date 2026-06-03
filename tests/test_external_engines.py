# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
import unittest
import sys
import io
import ipaddress
from pathlib import Path
from unittest.mock import patch, MagicMock
from parsers.loader import load_config, get_engine, ConfigLoadError

# Compute project root to reliably find configs/fixtures regardless of CWD
PROJECT_ROOT = Path(__file__).parent.parent


class TestExternalEngines(unittest.TestCase):

    def test_asa_external_engine_import_error(self):
        """ConfigLoadError with install hint when ciscoconfparse2 is missing."""
        with patch.dict(sys.modules, {'ciscoconfparse2': None}):
            with patch('sys.stdin', new=io.StringIO("!")):
                with self.assertRaises(ConfigLoadError) as cm:
                    load_config("-", vendor='asa', use_external_engines=True)
                self.assertIn("ciscoconfparse2", str(cm.exception))

    def test_fortigate_external_engine_import_error(self):
        """ConfigLoadError with install hint when ciscoconfparse2 is missing."""
        with patch.dict(sys.modules, {'ciscoconfparse2': None}):
            with patch('sys.stdin', new=io.StringIO("!")):
                with self.assertRaises(ConfigLoadError) as cm:
                    load_config("-", vendor='fortigate', use_external_engines=True)
                self.assertIn("pip install .[external]", str(cm.exception))

    def test_asa_advanced_engine_parses_objects(self):
        """AdvancedASAConfig resolves network objects correctly (end-to-end)."""
        cfg_text = (
            "object network WEBSERVER\n"
            " host 10.0.0.1\n"
            "access-list TEST extended permit tcp any host 10.0.0.1 eq 443\n"
        )
        cfg = get_engine('asa', cfg_text, use_external_engines=True)
        from parsers.cisco.asa.advanced_parser import AdvancedASAConfig
        self.assertIsInstance(cfg, AdvancedASAConfig)
        self.assertEqual(cfg.resolve_network('WEBSERVER'), {ipaddress.ip_address('10.0.0.1')})

    def test_asa_advanced_engine_flatten_acl(self):
        """AdvancedASAConfig.flatten_acl returns expected entries."""
        cfg_text = (
            "object network WEBSERVER\n"
            " host 10.0.0.1\n"
            "access-list TEST extended permit tcp any host 10.0.0.1 eq 443\n"
        )
        cfg = get_engine('asa', cfg_text, use_external_engines=True)
        entries = cfg.flatten_acl()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['action'], 'permit')
        self.assertIn(ipaddress.ip_address('10.0.0.1'), entries[0]['dst'])

    def test_fortigate_advanced_engine_parses_policies(self):
        """AdvancedFTGConfig successfully parses a FortiGate config end-to-end."""
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
            cfg, vendor, _ = load_config("-", vendor='fortigate', use_external_engines=True)
        from parsers.fortigate.advanced_parser import AdvancedFTGConfig
        self.assertIsInstance(cfg, AdvancedFTGConfig)
        self.assertIn('HOST_A', cfg.addresses)
        self.assertEqual(len(cfg.policies), 1)

    def test_default_engine_regression(self):
        """use_external_engines=False (default) still returns the legacy ASAConfig."""
        cfg_text = "access-list test permit ip host 1.1.1.1 any"
        with patch('sys.stdin', new=io.StringIO(cfg_text)):
            cfg, vendor, confidence = load_config("-", vendor='asa', use_external_engines=False)
            self.assertEqual(vendor, 'asa')
            from parsers.cisco.asa.parser import ASAConfig
            self.assertIsInstance(cfg, ASAConfig)
            resolved = cfg.resolve_network("1.1.1.1")
            self.assertEqual(resolved, {ipaddress.ip_address("1.1.1.1")})

    def test_advanced_engine_isinstance_of_legacy(self):
        """AdvancedASAConfig is a subclass of ASAConfig (drop-in replacement)."""
        from parsers.cisco.asa.parser import ASAConfig
        from parsers.cisco.asa.advanced_parser import AdvancedASAConfig
        self.assertTrue(issubclass(AdvancedASAConfig, ASAConfig))
        cfg = get_engine('asa', "access-list TEST extended permit ip any any",
                         use_external_engines=True)
        self.assertIsInstance(cfg, ASAConfig)

    def test_advanced_engine_static_route_keys_match_legacy(self):
        """AdvancedASAConfig static_routes use the same key schema as ASAConfig.

        ir_export.to_ir() and path.py both access 'destination', 'next_hop',
        and 'distance' — wrong keys produce silent None values in IR output.
        """
        from parsers.cisco.asa.parser import ASAConfig
        cfg_text = (
            "interface GigabitEthernet0/0\n"
            " nameif inside\n"
            " ip address 10.0.0.1 255.255.255.0\n"
            "route inside 192.168.1.0 255.255.255.0 10.0.0.254 1\n"
        )
        legacy = ASAConfig(cfg_text)
        advanced = get_engine('asa', cfg_text, use_external_engines=True)
        self.assertEqual(len(advanced.static_routes), 1)
        self.assertEqual(set(legacy.static_routes[0].keys()),
                         set(advanced.static_routes[0].keys()))
        r = advanced.static_routes[0]
        self.assertEqual(r['destination'], '192.168.1.0/24')
        self.assertEqual(r['next_hop'], '10.0.0.254')
        self.assertEqual(r['distance'], 1)
        self.assertIsNone(r['track'])
        self.assertFalse(r['tunneled'])

    def test_advanced_engine_acl_ignorecase(self):
        """AdvancedASAConfig matches ACCESS-LIST lines regardless of case.

        Passing re_acl (compiled Pattern) rather than re_acl.pattern (plain
        string) to find_objects() is what preserves the IGNORECASE flag.
        """
        cfg_text = "ACCESS-LIST OUTSIDE EXTENDED PERMIT TCP ANY HOST 10.0.0.1 EQ 443\n"
        cfg = get_engine('asa', cfg_text, use_external_engines=True)
        self.assertIn('OUTSIDE', cfg.acls)
        self.assertEqual(len(cfg.acls['OUTSIDE']), 1)

    def test_advanced_engine_static_route_no_metric(self):
        """Route without explicit distance stores distance=None, not a default int.

        ASAConfig and AdvancedASAConfig both use None when no metric token is
        present; an old bug stored 1 unconditionally.
        """
        cfg_text = "route inside 10.10.10.0 255.255.255.0 10.0.0.254\n"
        cfg = get_engine('asa', cfg_text, use_external_engines=True)
        self.assertEqual(len(cfg.static_routes), 1)
        self.assertIsNone(cfg.static_routes[0]['distance'])

    def test_advanced_engine_static_route_track_and_tunneled(self):
        """Route with 'track N tunneled' keywords sets both fields correctly."""
        cfg_text = "route outside 0.0.0.0 0.0.0.0 192.0.2.1 1 track 5 tunneled\n"
        cfg = get_engine('asa', cfg_text, use_external_engines=True)
        self.assertEqual(len(cfg.static_routes), 1)
        r = cfg.static_routes[0]
        self.assertEqual(r['distance'], 1)
        self.assertEqual(r['track'], 5)
        self.assertTrue(r['tunneled'])

    def test_advanced_engine_static_route_bad_mask_fallback(self):
        """Malformed mask stores raw 'ip/mask' string instead of silently dropping.

        Legacy ASAConfig falls back to f'{dest_ip}/{mask}' on to_ip_network
        failure; AdvancedASAConfig must do the same so callers see the route.
        """
        cfg_text = "route inside 10.0.0.0 notamask 10.0.0.1\n"
        cfg = get_engine('asa', cfg_text, use_external_engines=True)
        self.assertEqual(len(cfg.static_routes), 1)
        self.assertEqual(cfg.static_routes[0]['destination'], '10.0.0.0/notamask')

    def test_advanced_engine_static_route_dhcp_nexthop(self):
        """Route with 'dhcp' gateway stores next_hop=None, not the string 'dhcp'."""
        cfg_text = "route outside 0.0.0.0 0.0.0.0 dhcp\n"
        cfg = get_engine('asa', cfg_text, use_external_engines=True)
        self.assertEqual(len(cfg.static_routes), 1)
        self.assertIsNone(cfg.static_routes[0]['next_hop'])
        self.assertIsNone(cfg.static_routes[0]['distance'])


if __name__ == '__main__':
    unittest.main()
