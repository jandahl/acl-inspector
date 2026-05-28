"""Smoke tests for the parser package facades."""

import importlib
import unittest


class ParserPackageExportTest(unittest.TestCase):
    def test_cisco_package_exports(self):
        asa_pkg = importlib.import_module("parsers.cisco.asa")
        self.assertTrue(hasattr(asa_pkg, "ASAConfig"))
        for attr in ("inspect_host", "compare_old_new", "path_check"):
            self.assertTrue(callable(getattr(asa_pkg, attr, None)), f"{attr} missing on parsers.cisco.asa")

    def test_fortigate_package_exports(self):
        ftg_pkg = importlib.import_module("parsers.fortigate")
        self.assertTrue(hasattr(ftg_pkg, "FTGConfig"))
        for attr in ("inspect_host", "compare_old_new", "evaluate"):
            self.assertTrue(callable(getattr(ftg_pkg, attr, None)), f"{attr} missing on parsers.fortigate")

    def test_loader_exports(self):
        loader_pkg = importlib.import_module("parsers.loader")
        expected = ["load_config", "load_config_to_ir", "ConfigLoadError"]
        for name in expected:
            self.assertTrue(hasattr(loader_pkg, name), f"{name} not exported by parsers.loader")
            self.assertIn(name, loader_pkg.__all__)

    def test_load_config_to_ir_asa_fixture(self):
        """load_config_to_ir returns a Device with the right vendor."""
        from parsers.loader import load_config_to_ir
        import os
        # Anchor path relative to this file
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        fixture_path = os.path.join(base_dir, "configs", "fixtures", "asa-compare-sample.conf")
        
        if not os.path.exists(fixture_path):
            self.skipTest(f"Fixture missing: {fixture_path}")
            
        device = load_config_to_ir(fixture_path)
        self.assertEqual(device.vendor, "asa")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
