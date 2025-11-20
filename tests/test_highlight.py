import unittest
import importlib.util
import os

_MOD_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cli', 'cli/access-list-web.py')
spec = importlib.util.spec_from_file_location('access_list_web', _MOD_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)  # type: ignore


class TestHighlight(unittest.TestCase):
    def test_basic_highlight(self):
        line = "access-list OUT extended permit tcp object OBJ any eq 443"
        out = mod.highlight_asa_for_tests(line)
        self.assertIn("<span class='kw'>access-list</span>", out)
        self.assertIn("<span class='act'>permit</span>", out)
        self.assertIn("<span class='proto'>tcp</span>", out)
        self.assertIn("<span class='kw'>object</span>", out)
        self.assertIn("<span class='kw'>any</span>", out)
        self.assertIn("<span class='num'>443</span>", out)


if __name__ == '__main__':
    unittest.main()

