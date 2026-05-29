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
        # Force a reload of the modules to ensure we aren't using a cached version
        # that already did the sys.path manipulation or holds references to scripts
        for mod in ("parsers.loader", "parsers.detector"):
            sys.modules.pop(mod, None)
            
        # Ensure 'scripts' is NOT in sys.path
        original_path = sys.path.copy()
        scripts_path = str(Path(__file__).parent.parent / "scripts")
        resolved_scripts = Path(scripts_path).resolve()
        
        new_path = []
        for p in sys.path:
            try:
                if Path(p).resolve() != resolved_scripts:
                    new_path.append(p)
            except Exception:
                # If path is invalid, keep it as is
                new_path.append(p)
        sys.path = new_path
        
        config_path = None
        try:
            # Import and use loader
            from parsers.loader import load_config
            
            # Simple ASA config in a temporary file
            config_text = "ASA Version 9.8(2)\ninterface GigabitEthernet0/0\n nameif outside"
            
            # Consolidated try-finally for file creation and test execution
            try:
                with tempfile.NamedTemporaryFile(suffix=".conf", mode="w", delete=False) as tmp:
                    tmp.write(config_text)
                    config_path = Path(tmp.name)
                
                # This should NOT trigger a ModuleNotFoundError for 'index_repo'
                cfg, vendor, score = load_config(config_path)
                self.assertEqual(vendor, 'asa')
                self.assertGreaterEqual(score, 80)
            finally:
                if config_path and config_path.exists():
                    config_path.unlink()
                    
            # Also verify that parsers.loader didn't add scripts to sys.path
            for p in sys.path:
                try:
                    resolved_p = Path(p).resolve()
                except Exception:
                    continue
                self.assertNotEqual(resolved_p, resolved_scripts, 
                                    "parsers.loader should not add scripts/ to sys.path")
                                    
        finally:
            # Restore path
            sys.path = original_path


if __name__ == "__main__":
    unittest.main()
