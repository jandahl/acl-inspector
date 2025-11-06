"""Tests for API handler helpers."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from webui import settings as settings_mod
from webui.handlers import api as api_handlers
from webui.handlers import pages as page_handlers
from webui.indexer import asa as asa_index
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
        obj_entry = next((item for item in payload["items"] if item["value"] == "OBJ_WEB"), None)
        self.assertIsNotNone(obj_entry)
        self.assertEqual(obj_entry["context"], "sample.cfg")
        self.assertIn("192.0.2.10", obj_entry.get("addresses", []))
        self.assertEqual(obj_entry.get("home"), "home")
        self.assertIn("popularity", obj_entry)

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

    def test_objects_handles_non_utf8_config(self):
        bad_name = "non_utf8.cfg"
        (self.config_root / bad_name).write_bytes(ASA_SAMPLE.encode("utf-8") + b"\xff")
        status, payload = api_handlers.objects(
            self.state,
            vendor="asa",
            os_tag="ASA",
            version="auto",
            filename=bad_name,
            query="OBJ",
            mode="prefix",
            limit=10,
        )
        self.assertEqual(status, 200)
        obj_entry = next((item for item in payload["items"] if item["value"] == "OBJ_WEB"), None)
        self.assertIsNotNone(obj_entry)
        self.assertIn("192.0.2.10", obj_entry.get("addresses", []))
        self.assertEqual(obj_entry.get("home"), "home")

    def test_objects_global_search_aggregates_across_configs(self):
        status, payload = api_handlers.objects(
            self.state,
            vendor="all",
            os_tag="",
            version="auto",
            filename="",
            query="OBJ",
            mode="prefix",
            limit=5,
        )
        self.assertEqual(status, 200)
        obj_entry = next((item for item in payload["items"] if item["value"] == "OBJ_WEB"), None)
        self.assertIsNotNone(obj_entry)
        self.assertEqual(obj_entry["vendor"], "asa")
        self.assertEqual(obj_entry["context"], "sample.cfg")
        self.assertIn("192.0.2.10", obj_entry.get("addresses", []))
        self.assertEqual(obj_entry.get("home"), "home")
        self.assertIn("popularity", obj_entry)

    def test_objects_global_search_includes_context_matches(self):
        status, payload = api_handlers.objects(
            self.state,
            vendor="all",
            os_tag="",
            version="auto",
            filename="",
            query="sample",
            mode="substring",
            limit=5,
        )
        self.assertEqual(status, 200)
        context_entry = next((item for item in payload["items"] if item["type"] == "context"), None)
        self.assertIsNotNone(context_entry)
        self.assertEqual(context_entry["context"], "sample.cfg")
        self.assertEqual(context_entry["vendor"], "asa")
        self.assertEqual(context_entry.get("home"), "context")

    def test_index_popularity_handles_acl_errors(self):
        with mock.patch("analysis_core.adapters.asa.asa_parser.ASAConfig.flatten_acl", side_effect=RuntimeError("flatten boom")):
            index = asa_index.build_index(ASA_SAMPLE)
        self.assertIn("objects", index)
        self.assertIn("popularity", index)
        self.assertIn("object", index["popularity"])

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

    def _extract_singularity_payload(self, html: str) -> dict:
        marker = "window.SINGULARITY_DATA = "
        self.assertIn(marker, html, msg="Singularity payload missing from template")
        segment = html.split(marker, 1)[1]
        terminator = segment.find(";")
        self.assertGreater(terminator, 0, msg="Unable to locate payload terminator")
        raw = segment[:terminator].strip()
        return json.loads(raw)

    def test_render_singularity_payload_includes_themes(self):
        html = page_handlers._render_singularity(self.state)
        payload = self._extract_singularity_payload(html)
        self.assertEqual(payload["defaultVendor"], "asa")
        self.assertEqual(payload["defaultConfig"], "sample.cfg")
        self.assertIn("themes", payload)
        self.assertIn("dark", payload["themes"])
        self.assertIn("light", payload["themes"])
        for palette in payload["themes"].values():
            self.assertIn("bg-base", palette)
            self.assertIn("accent", palette)
            self.assertIn("highlight", palette)
        self.assertIn(payload["defaultTheme"], ("dark", "light"))

    def test_singularity_default_vendor_with_only_fortigate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            cisco_root = base / "configs" / "cisco"
            cisco_root.mkdir(parents=True, exist_ok=True)
            ftg_root = base / "configs" / "fortigate"
            ftg_root.mkdir(parents=True, exist_ok=True)
            (ftg_root / "ftg.conf").write_text("config firewall address\n", encoding="utf-8")
            settings = settings_mod.load_settings(
                base / "settings.json",
                env={
                    "ACLINSPECTOR_CONFIGS_CISCO": str(cisco_root),
                    "ACLINSPECTOR_CONFIGS_FORTIGATE": str(ftg_root),
                },
            )
            alt_state = AppState.create(settings)
            html = page_handlers._render_singularity(alt_state)
            payload = self._extract_singularity_payload(html)
            self.assertEqual(payload["defaultVendor"], "fortigate")
            self.assertEqual(payload["defaultConfig"], "ftg.conf")

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
