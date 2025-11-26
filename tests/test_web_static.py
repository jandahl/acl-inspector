import io
import importlib.util
import os
import types
import unittest

from common.project_paths import cli_path

_MOD_PATH = str(cli_path("access-list-web.py"))
spec = importlib.util.spec_from_file_location("access_list_web_static", _MOD_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)  # type: ignore
WebHandler = module.WebHandler


class _Shim:
    """Minimal shim to bind WebHandler helpers without socket plumbing."""

    def __init__(self):
        self._headers = []
        self._status = None
        self._ended = False
        self.wfile = io.BytesIO()
        self.server = types.SimpleNamespace(app_state=None)

        def send_response(_self, code, *_args, **_kwargs):
            self._status = code

        def send_header(_self, key, value):
            self._headers.append((key.lower(), value))

        def end_headers(_self):
            self._ended = True

        # Bind helpers from the real handler.
        self.send_response = types.MethodType(send_response, self)
        self.send_header = types.MethodType(send_header, self)
        self.end_headers = types.MethodType(end_headers, self)
        self._load_static_asset = WebHandler._load_static_asset.__get__(self, WebHandler)
        self._send_bytes = WebHandler._send_bytes.__get__(self, WebHandler)
        self._serve_static = WebHandler._serve_static.__get__(self, WebHandler)


class TestLegacyStaticServing(unittest.TestCase):
    def test_serves_bundled_js(self):
        shim = _Shim()
        served = shim._serve_static("/static/app.js")
        self.assertTrue(served)
        self.assertEqual(shim._status, 200)
        body = shim.wfile.getvalue()
        self.assertGreater(len(body), 1000)
        self.assertIn(("content-type", "text/javascript"), shim._headers)

    def test_serves_font_manifest_css(self):
        shim = _Shim()
        shim.server.app_state = types.SimpleNamespace(font_css="/*css*/\n", font_files=[])
        served = shim._serve_static("/static/fonts/local.css")
        self.assertTrue(served)
        self.assertEqual(shim._status, 200)
        self.assertEqual(shim.wfile.getvalue(), b"/*css*/\n")
        self.assertIn(("cache-control", "max-age=60, must-revalidate"), shim._headers)


if __name__ == "__main__":
    unittest.main()
