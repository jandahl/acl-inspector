# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Path check regression tests using fixtures."""

import unittest
from pathlib import Path

from parsers.cisco.asa import path as asa_path
from parsers.fortigate import path as forti_path


FIXTURES = Path(__file__).resolve().parents[1] / "configs" / "fixtures"


class TestPathCheckFixtures(unittest.TestCase):
    def test_asa_path_with_nat(self):
        text = (FIXTURES / "asa-path-sample.conf").read_text()
        result = asa_path.path_check(
            text,
            src="192.0.2.10",
            dst="10.0.0.10",
            proto="tcp",
            dports={80},
            include_any=True,
        )
        self.assertTrue(result.get("allowed", False))
        self.assertEqual(result.get("acl", {}).get("decision"), "permit")

    def test_forti_path_with_vip(self):
        text = (FIXTURES / "forti-path-sample.conf").read_text()
        result = forti_path.path_check(
            text,
            src="192.0.2.10",
            dst="203.0.113.10",
            proto="tcp",
            dports={80},
            include_any=True,
            vdom="root",
        )
        self.assertIsInstance(result, dict)
        self.assertIn("acl", result)
        self.assertIn("nat", result)


if __name__ == "__main__":
    unittest.main()
