import unittest
import importlib.util
import os

from common.project_paths import cli_path

_MOD_PATH = str(cli_path('access-list-web.py'))
spec = importlib.util.spec_from_file_location('access_list_web', _MOD_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)  # type: ignore


class TestWebStorageFallback(unittest.TestCase):
    def test_storage_helpers_present(self):
        handler = mod.WebHandler.__new__(mod.WebHandler)

        class DummyServer:
            config_dirs = {'asa': 'configs/cisco', 'fortigate': 'configs/fortigate'}

        handler.server = DummyServer()
        html = handler._form()
        self.assertIn('function storageGet', html)
        self.assertIn('storageSet(', html)
        script = html.split('<script>')[1]
        self.assertEqual(script.count('localStorage.'), 2)
        self.assertIn("document.querySelector(\"select[name='proto']\")", script)
        self.assertIn("document.querySelector(\"input[name='dport']\")", script)


if __name__ == '__main__':
    unittest.main()
