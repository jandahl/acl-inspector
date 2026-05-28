# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
import unittest

from common.vendor_caps import get_caps

try:
    from tui.app import SingularityApp
    HAS_TEXTUAL = True
except ModuleNotFoundError:
    HAS_TEXTUAL = False


class TestTUIVendorHint(unittest.TestCase):
    @unittest.skipUnless(HAS_TEXTUAL, "textual not installed")
    def test_describe_vendor_caps_known(self):
        caps = get_caps("asa")
        summary = SingularityApp._describe_vendor_caps(caps, "asa")
        self.assertIn("ASA", summary)
        self.assertIn("Inspect", summary)
        self.assertIn("Compare", summary)

    @unittest.skipUnless(HAS_TEXTUAL, "textual not installed")
    def test_describe_vendor_caps_unknown(self):
        summary = SingularityApp._describe_vendor_caps(None, "mystery")
        self.assertIn("MYSTERY", summary)
        self.assertIn("unknown", summary.lower())


if __name__ == "__main__":
    unittest.main()
