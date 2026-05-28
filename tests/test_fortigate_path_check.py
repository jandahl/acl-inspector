# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Tests for FortiGate path_check (packet simulation)."""

import unittest
from pathlib import Path

from parsers.fortigate.path import path_check


FIXTURES = Path(__file__).parent / "fixtures" / "configs" / "fortigate"


class TestFortiGatePathCheck(unittest.TestCase):
    """Verify NAT + policy evaluation for FortiGate."""

    @classmethod
    def setUpClass(cls):
        cls.cfg_text = (FIXTURES / "advanced_policy_nat.conf").read_text()

    def test_vip_dnat_flow(self):
        """VIP inbound flow should translate destination and permit."""
        result = path_check(
            self.cfg_text,
            src="1.1.1.1",
            dst="198.51.100.10",
            proto="tcp",
            dports={443},
        )
        self.assertTrue(result["allowed"])
        self.assertEqual(result["nat"]["type"], "vip")
        self.assertEqual(result["nat"]["translations"]["dst"]["after"], "10.1.2.10")
        self.assertEqual(result["acl"]["decision"], "permit")

    def test_policy_snat_flow(self):
        """Outbound policy with SNAT pool should translate source."""
        result = path_check(
            self.cfg_text,
            src="10.1.1.20",
            dst="8.8.8.8",
            proto="tcp",
            dports={80},
        )
        self.assertTrue(result["allowed"])
        self.assertEqual(result["nat"]["type"], "policy-snat")
        self.assertEqual(result["nat"]["translations"]["src"]["after"], "198.51.100.50")
        self.assertEqual(result["acl"]["decision"], "permit")


if __name__ == "__main__":
    unittest.main()
