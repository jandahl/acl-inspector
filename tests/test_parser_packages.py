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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
