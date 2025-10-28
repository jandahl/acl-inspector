"""Tests for API handler helpers."""

import tempfile
import unittest
from pathlib import Path

from webui import settings as settings_mod
from webui.handlers import api as api_handlers
from webui.handlers import pages as page_handlers
from webui.state import AppState


ASA_SAMPLE = """!
object network OBJ_WEB
 host 192.0.2.10
object network OBJ_DB
 host 198.51.100.5
object-group network OG-SERVERS
 network-object object OBJ_WEB
 network-object object OBJ_DB
access-list OUTSIDE extended permit tcp any object OBJ_WEB eq 443
"""


class APIHandlersTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        base = Path(self.tmpdir.name)
        self.config_root = base / "configs" / "cisco"
        self.config_root.mkdir(parents=True, exist_ok=True)
        (self.config_root / "sample.cfg").write_text(ASA_SAMPLE, encoding="utf-8")
        settings = settings_mod.load_settings(
            base / "settings.json",
            env={"ACLINSPECTOR_CONFIGS_CISCO": str(self.config_root)},
        )
        self.state = AppState.create(settings)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_objects_endpoint_success(self):
        status, payload = api_handlers.objects(
            self.state,
            vendor="asa",
            os_tag="ASA",
            version="auto",
            filename="sample.cfg",
            query="obj",
            mode="prefix",
            limit=10,
        )
        self.assertEqual(status, 200)
        values = {item["value"] for item in payload["items"]}
        self.assertIn("OBJ_WEB", values)

    def test_objects_invalid_config(self):
        status, payload = api_handlers.objects(
            self.state,
            vendor="asa",
            os_tag="ASA",
            version="auto",
            filename="missing.cfg",
            query="obj",
            mode="prefix",
            limit=10,
        )
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"], "invalid_config")

    def test_meta_and_config(self):
        status, meta = api_handlers.meta(self.state, vendor="asa", filename="sample.cfg")
        self.assertEqual(status, 200)
        self.assertEqual(meta["vendor"], "asa")

        status, payload = api_handlers.config_text(
            self.state, vendor="asa", filename="sample.cfg"
        )
        self.assertEqual(status, 200)
        self.assertIn("text", payload)

    def test_aliases(self):
        status, payload = api_handlers.aliases(
            self.state, vendor="asa", filename="sample.cfg", target="OBJ_WEB"
        )
        self.assertEqual(status, 200)
        self.assertIn("aliases", payload)

    def test_index_status(self):
        status, payload = api_handlers.index_status(self.state)
        self.assertEqual(status, 200)
        self.assertIn("in_memory", payload)

    def test_render_home_template(self):
        html = page_handlers._render_home(self.state)
        self.assertIn("/static/app.css", html)
        self.assertIn("<select name=\"vendor\"", html)
        self.assertIn("ACL_BETA_MODULES", html)

    def test_packet_probe(self):
        status, payload = api_handlers.packet_probe(
            self.state,
            vendor="asa",
            filename="sample.cfg",
            src="OBJ_WEB",
            dst="OBJ_DB",
            proto="tcp",
            dports=["443"],
            include_any=False,
        )
        self.assertEqual(status, 200)
        self.assertIn("result", payload)
        entries = self.state.history.snapshot()["entries"]
        self.assertTrue(any(entry["tab"] == "packet-probe" for entry in entries))

    def test_packet_probe_invalid_vendor(self):
        status, payload = api_handlers.packet_probe(
            self.state,
            vendor="fortigate",
            filename="sample.cfg",
            src="HOST_A",
            dst="HOST_B",
            proto=None,
            dports=[],
            include_any=False,
        )
        self.assertEqual(status, 400)
        self.assertIn("error", payload)

    def test_flush_caches(self):
        api_handlers.objects(
            self.state,
            vendor="asa",
            os_tag="ASA",
            version="auto",
            filename="sample.cfg",
            query="obj",
            mode="prefix",
            limit=5,
        )
        self.state.history.record("rules", "OBJ_WEB")
        status, payload = api_handlers.flush_caches(self.state, include_disk=False)
        self.assertEqual(status, 200)
        self.assertEqual(payload["history"]["cleared"], 1)
        self.assertEqual(self.state.history.snapshot()["entries"], [])
        self.assertEqual(self.state.search_index.status()["entries"], 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
