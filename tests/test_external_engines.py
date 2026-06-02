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
        """ConfigLoadError with install hint when fortios_xutils is missing."""
        with patch.dict(sys.modules, {'fortios_xutils': None}):
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

    def test_fortigate_advanced_parser_scaffolding(self):
        """AdvancedFTGConfig scaffolding raises ConfigLoadError (not yet implemented)."""
        with patch.dict(sys.modules, {'fortios_xutils': MagicMock()}):
            with patch('sys.stdin', new=io.StringIO("!")):
                with self.assertRaises(ConfigLoadError) as cm:
                    load_config("-", vendor='fortigate', use_external_engines=True)
                self.assertIn("not yet implemented", str(cm.exception))

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


if __name__ == '__main__':
    unittest.main()
