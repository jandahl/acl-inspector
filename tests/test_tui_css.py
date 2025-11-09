"""Test TUI CSS stylesheet parsing."""

import unittest
import subprocess
import sys


class TUICSSTest(unittest.TestCase):
    """Test that TUI CSS parses without errors."""

    def test_css_stylesheet_parses(self):
        """Verify TUI app CSS has no parsing errors."""
        # Run TUI with --help to trigger CSS parsing without entering interactive mode
        result = subprocess.run(
            [sys.executable, "acl-inspector-tui.py", "--help"],
            capture_output=True,
            text=True,
            timeout=5
        )

        # Check for CSS parsing errors in stderr
        self.assertNotIn("CSS parsing failed", result.stderr,
                        "CSS stylesheet has parsing errors")
        self.assertNotIn("Invalid CSS property", result.stderr,
                        "CSS contains invalid properties")
        self.assertNotIn("expected easing function", result.stderr,
                        "CSS has invalid transition/easing syntax")


if __name__ == '__main__':
    unittest.main()
