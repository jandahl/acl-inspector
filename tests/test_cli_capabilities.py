# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Tests for CLI capability listing."""

import io
import unittest
from contextlib import redirect_stdout

import aclinspector


class TestCliCapabilities(unittest.TestCase):
    def test_list_capabilities_flag(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = aclinspector.main(["--list-capabilities"])
        self.assertEqual(rc, 0)
        output = buf.getvalue()
        self.assertIn("ASA", output)
        self.assertIn("FORTIGATE", output)
        self.assertIn("inspect", output)
        self.assertIn("packet", output)


if __name__ == "__main__":
    unittest.main()
