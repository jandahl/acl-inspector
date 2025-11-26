"""FortiGate multi-VDOM + zone fixture tests."""

import unittest
from pathlib import Path

from parsers.fortigate.config import FTGConfig, load_fortigate_vdoms


FIXTURE = Path(__file__).resolve().parents[1] / "configs" / "fixtures" / "forti-multivdom-zones.conf"


class TestFortigateZones(unittest.TestCase):
    def setUp(self):
        self.text = FIXTURE.read_text()

    def test_list_vdoms(self):
        names = FTGConfig.list_vdom_names([l.rstrip() for l in self.text.splitlines()])
        self.assertEqual(names, ["root", "branch"])

    def test_load_each_vdom(self):
        cfgs = load_fortigate_vdoms(self.text)
        self.assertEqual({cfg.vdom for cfg in cfgs}, {"root", "branch"})
        # Ensure zones mapped into binding
        root_cfg = next(c for c in cfgs if c.vdom == "root")
        self.assertIn("inside-zone", root_cfg.zones)
        branch_cfg = next(c for c in cfgs if c.vdom == "branch")
        self.assertIn("branch-zone", branch_cfg.zones)

    def test_policy_flatten_includes_zones(self):
        cfg = FTGConfig(self.text, vdom="root")
        entries = cfg.flatten_policies()
        self.assertTrue(entries)
        binding = entries[0].get("binding", {})
        # Zone mapping may stay in srcintf when zones are used directly
        self.assertIn("srcintf", binding)
        self.assertIn("dstintf", binding)


if __name__ == "__main__":
    unittest.main()
