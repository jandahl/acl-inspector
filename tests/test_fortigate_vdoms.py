# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
import unittest
from pathlib import Path

from parsers.fortigate.config import FTGConfig, load_fortigate_vdoms

SAMPLE = (Path(__file__).resolve().parents[1] / "configs" / "fortigate" / "fortigate7-4-example").read_text()


class TestFortiGateVdoms(unittest.TestCase):
    def test_lists_all_vdoms(self):
        lines = [line.rstrip() for line in SAMPLE.splitlines()]
        names = FTGConfig.list_vdom_names(lines)
        self.assertEqual(names, ["Alpha", "Bravo", "Charlie"])

    def test_load_all_vdoms(self):
        cfgs = load_fortigate_vdoms(SAMPLE)
        self.assertEqual({cfg.vdom for cfg in cfgs}, {"Alpha", "Bravo", "Charlie"})
        # Ensure each vdom has some policies parsed
        self.assertTrue(all(len(cfg.policies) > 0 for cfg in cfgs))

    def test_load_specific_vdom(self):
        cfgs = load_fortigate_vdoms(SAMPLE, target_vdom="Bravo")
        self.assertEqual(len(cfgs), 1)
        self.assertEqual(cfgs[0].vdom, "Bravo")
        self.assertGreater(len(cfgs[0].addresses), 0)


if __name__ == "__main__":
    unittest.main()
