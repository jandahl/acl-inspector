import re
import unittest
from pathlib import Path

JS_PATH = Path("webui/static/app.js")
LAYOUT_PATH = Path("webui/templates/layout.html")


class TestWebUIJSCompatibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js_text = JS_PATH.read_text(encoding="utf-8")

    def test_no_optional_chaining(self):
        self.assertNotIn("?.", self.js_text, "Optional chaining is not allowed in legacy bundle")
        self.assertNotIn("??", self.js_text, "Nullish coalescing is not allowed in legacy bundle")

    def test_no_async_keyword(self):
        self.assertIsNone(
            re.search(r"\basync\b", self.js_text),
            "Async functions should not appear in the legacy bundle",
        )

    def test_fetch_calls_routed_through_legacy_helper(self):
        pattern = re.compile(r"(?<!\.)\bfetch\(")
        self.assertIsNone(
            pattern.search(self.js_text),
            "Direct fetch() calls should be routed through legacyFetch",
        )


class TestLayoutStructure(unittest.TestCase):
    def test_boot_status_placeholder_present(self):
        html = LAYOUT_PATH.read_text(encoding="utf-8")
        self.assertIn('id="boot_status"', html)


if __name__ == "__main__":
    unittest.main()
