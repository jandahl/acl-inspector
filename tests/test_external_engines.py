# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
import unittest
import sys
from unittest.mock import patch, MagicMock
from parsers.loader import load_config, ConfigLoadError

class TestExternalEngines(unittest.TestCase):
    def test_asa_external_engine_import_error(self):
        """Test that ASA external engine raises ConfigLoadError with helpful message if deps missing."""
        # Force ImportError when ciscoconfparse is imported
        with patch.dict(sys.modules, {'ciscoconfparse': None}):
            with self.assertRaises(ConfigLoadError) as cm:
                load_config("configs/fixtures/asa-path-sample.conf", vendor='asa', use_external_engines=True)
            self.assertIn("pip install .[external]", str(cm.exception))

    def test_fortigate_external_engine_import_error(self):
        """Test that FortiGate external engine raises ConfigLoadError with helpful message if deps missing."""
        # Force ImportError when fortios_xutils is imported
        with patch.dict(sys.modules, {'fortios_xutils': None}):
            with self.assertRaises(ConfigLoadError) as cm:
                load_config("configs/fixtures/forti-path-sample.conf", vendor='fortigate', use_external_engines=True)
            self.assertIn("pip install .[external]", str(cm.exception))

    def test_asa_advanced_parser_scaffolding(self):
        """Test that AdvancedASAConfig scaffolding raises NotImplementedError."""
        mock_parse = MagicMock()
        # Mocking the module itself to avoid import error during patch setup
        with patch.dict(sys.modules, {'ciscoconfparse': MagicMock()}):
            from parsers.cisco.asa.advanced_parser import AdvancedASAConfig
            with patch('ciscoconfparse.CiscoConfParse', return_value=mock_parse):
                with self.assertRaises(NotImplementedError):
                    cfg = AdvancedASAConfig("object network OBJ1\n host 1.1.1.1")

    def test_fortigate_advanced_parser_scaffolding(self):
        """Test that AdvancedFTGConfig scaffolding raises NotImplementedError."""
        with patch.dict(sys.modules, {'fortios_xutils': MagicMock()}):
            from parsers.fortigate.advanced_parser import AdvancedFTGConfig
            with self.assertRaises(NotImplementedError):
                cfg = AdvancedFTGConfig("config firewall address\n edit ADDR1\n end")

if __name__ == '__main__':
    unittest.main()
