# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Verification that the core package has no hidden dependency on scripts/."""

import sys
import tempfile
import unittest
from pathlib import Path


class PackagingIntegrityTest(unittest.TestCase):
    def test_loader_without_scripts_on_path(self):
        """Verify that parsers.loader works even if scripts/ is not in sys.path."""
        # Force a reload of the module to ensure we aren't using a cached version
        # that already did the sys.path manipulation
        if "parsers.loader" in sys.modules:
            del sys.modules["parsers.loader"]
            
        # Ensure 'scripts' is NOT in sys.path
        original_path = sys.path.copy()
        scripts_path = str(Path(__file__).parent.parent / "scripts")
        sys.path = [p for p in sys.path if str(Path(p).resolve()) != str(Path(scripts_path).resolve())]
        
        try:
            # Import and use loader
            from parsers.loader import load_config
            
            # Simple ASA config in a temporary file
            config_text = "ASA Version 9.8(2)\ninterface GigabitEthernet0/0\n nameif outside"
            with tempfile.NamedTemporaryFile(suffix=".conf", mode="w", delete=False) as tmp:
                tmp.write(config_text)
                config_path = Path(tmp.name)
            
            try:
                # This should NOT trigger a ModuleNotFoundError for 'index_repo'
                cfg, vendor, score = load_config(config_path)
                self.assertEqual(vendor, 'asa')
                self.assertGreaterEqual(score, 80)
            finally:
                if config_path.exists():
                    config_path.unlink()
                    
            # Also verify that parsers.loader didn't add scripts to sys.path
            for p in sys.path:
                self.assertNotEqual(str(Path(p).resolve()), str(Path(scripts_path).resolve()), 
                                    "parsers.loader should not add scripts/ to sys.path")
                                    
        finally:
            # Restore path
            sys.path = original_path


if __name__ == "__main__":
    unittest.main()
