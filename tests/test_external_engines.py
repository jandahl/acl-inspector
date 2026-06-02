# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
import unittest
import sys
import io
import ipaddress
from pathlib import Path
from unittest.mock import patch, MagicMock
from parsers.loader import load_config, ConfigLoadError

# Compute project root to reliably find configs/fixtures regardless of CWD
PROJECT_ROOT = Path(__file__).parent.parent


class TestExternalEngines(unittest.TestCase):

    def test_asa_external_engine_import_error(self):
        """Test that ASA external engine raises ConfigLoadError with helpful message if deps missing."""
        # Use patch('sys.stdin', ...) to make test hermetic and avoid file dependencies
        with patch.dict(sys.modules, {'ciscoconfparse': None}):
            with patch('sys.stdin', new=io.StringIO("!")):
                with self.assertRaises(ConfigLoadError) as cm:
                    # We use vendor='asa' to bypass detection and go straight to engine loading
                    load_config("-", vendor='asa', use_external_engines=True)
                self.assertIn("pip install .[external]", str(cm.exception))

    def test_fortigate_external_engine_import_error(self):
        """Test that FortiGate external engine raises ConfigLoadError with helpful message if deps missing."""
        with patch.dict(sys.modules, {'fortios_xutils': None}):
            with patch('sys.stdin', new=io.StringIO("!")):
                with self.assertRaises(ConfigLoadError) as cm:
                    load_config("-", vendor='fortigate', use_external_engines=True)
                self.assertIn("pip install .[external]", str(cm.exception))

    def test_asa_advanced_parser_scaffolding(self):
        """Test that AdvancedASAConfig scaffolding raises NotImplementedError."""
        from parsers.cisco.asa.advanced_parser import AdvancedASAConfig
        # We mock the library existence so we get past the ImportError
        with patch.dict(sys.modules, {'ciscoconfparse': MagicMock()}):
            with self.assertRaises(NotImplementedError) as cm:
                AdvancedASAConfig("!")
            self.assertIn("not yet implemented", str(cm.exception))

    def test_fortigate_advanced_parser_scaffolding(self):
        """Test that AdvancedFTGConfig scaffolding raises NotImplementedError."""
        from parsers.fortigate.advanced_parser import AdvancedFTGConfig
        with patch.dict(sys.modules, {'fortios_xutils': MagicMock()}):
            with self.assertRaises(NotImplementedError) as cm:
                AdvancedFTGConfig("!")
            self.assertIn("not yet implemented", str(cm.exception))

    def test_default_engine_regression(self):
        """Test that loading with use_external_engines=False (default) still returns legacy parser."""
        cfg_text = "access-list test permit ip host 1.1.1.1 any"
        with patch('sys.stdin', new=io.StringIO(cfg_text)):
            # Basic sanity check that we get a working ASAConfig back for ASA-like text
            cfg, vendor, confidence = load_config("-", vendor='asa', use_external_engines=False)
            self.assertEqual(vendor, 'asa')
            from parsers.cisco.asa.parser import ASAConfig
            self.assertIsInstance(cfg, ASAConfig)
            
            # Functional round-trip: resolve a network
            resolved = cfg.resolve_network("1.1.1.1")
            self.assertEqual(resolved, {ipaddress.ip_address("1.1.1.1")})

if __name__ == '__main__':
    unittest.main()
