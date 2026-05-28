# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
import unittest

from utils.config import clean_config_text


class TestCleanConfigText(unittest.TestCase):
    def test_removes_pager_lines_and_unescapes(self):
        sample = (
            "object network OBJ1\n"
            " host 10.0.0.1\n"
            "&lt;--- More ---&gt;              \n"
            " network-object 10.0.0.0 255.255.255.0\n"
            "<--- More --->\n"
            "! comment\n"
        )
        cleaned = clean_config_text(sample)
        self.assertNotIn("<--- More --->", cleaned)
        self.assertNotIn("&lt;--- More ---&gt;", cleaned)
        self.assertIn("object network OBJ1", cleaned)
        self.assertIn(" network-object 10.0.0.0 255.255.255.0", cleaned)
        self.assertTrue(cleaned.endswith("! comment\n"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
