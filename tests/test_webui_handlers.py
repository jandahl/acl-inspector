# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Tests for API handler helpers."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from webui import settings as settings_mod
from webui import vendor_caps
from webui.handlers import api as api_handlers
from webui.handlers import pages as page_handlers
from webui.indexer import asa as asa_index
from webui.state import AppState


FORTI_FIXTURE = Path(__file__).parent / "fixtures" / "configs" / "fortigate" / "advanced_policy_nat.conf"

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
        self.ftg_root = base / "configs" / "fortigate"
        self.ftg_root.mkdir(parents=True, exist_ok=True)
        forti_text = FORTI_FIXTURE.read_text(encoding="utf-8")
        (self.ftg_root / "forti.conf").write_text(forti_text, encoding="utf-8")
        settings = settings_mod.load_settings(
            base / "settings.json",
            env={
                "ACLINSPECTOR_CONFIGS_CISCO": str(self.config_root),
                "ACLINSPECTOR_CONFIGS_FORTIGATE": str(self.ftg_root),
            },
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

    def test_global_search_short_circuits_large_repos(self):
        class FakeIndexManager:
            def __init__(self):
                self.calls = []

            def get_index(self, vendor, os_tag, version, path):
                self.calls.append(path)
                return SimpleNamespace(
                    index={"objects": [f"obj-{len(self.calls)}"], "object_details": {}, "popularity": {}}
                )

            def suggest(self, index, query, mode, limit):
                return [
                    {
                        "value": f"obj-{len(self.calls)}",
                        "label": f"obj-{len(self.calls)}",
                        "type": "object",
                        "score": 0,
                    }
                ]

        fake_state = SimpleNamespace(
            settings=SimpleNamespace(
                paths=SimpleNamespace(configs={"asa": "/tmp/fake"}),
                features=SimpleNamespace(predictive_search=SimpleNamespace(limit=25)),
            ),
            index_manager=FakeIndexManager(),
        )
        large_listing = {f"cfg{i}": f"/tmp/cfg{i}" for i in range(200)}
        with mock.patch("webui.handlers.api.config_listing", return_value=large_listing):
            status, payload = api_handlers.objects(
                fake_state,
                vendor="all",
                os_tag="",
                version="auto",
                filename="",
                query="foo",
                mode="fuzzy",
                limit=5,
            )
        self.assertEqual(status, 200)
        self.assertGreater(len(payload["items"]), 0)
        self.assertLessEqual(
            len(fake_state.index_manager.calls),
            5 * 4,
            msg="Global search scanned too many configs despite limit.",
        )

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

    def test_packet_probe_fortigate(self):
        status, payload = api_handlers.packet_probe(
            self.state,
            vendor="fortigate",
            filename="forti.conf",
            src="1.1.1.1",
            dst="198.51.100.10",
            proto="tcp",
            dports=["443"],
            include_any=True,
            vdom="root",
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload.get("vendor"), "fortigate")
        self.assertEqual(payload.get("vdom"), "root")
        nat = payload.get("result", {}).get("nat", {})
        self.assertEqual(nat.get("type"), "vip")

    def test_packet_probe_invalid_vendor(self):
        status, payload = api_handlers.packet_probe(
            self.state,
            vendor="ios",
            filename="sample.cfg",
            src="HOST_A",
            dst="HOST_B",
            proto=None,
            dports=[],
            include_any=False,
        )
        self.assertEqual(status, 400)
        self.assertIn("error", payload)

    def test_packet_probe_rejects_when_capability_disabled(self):
        original_caps = vendor_caps.all_caps()
        try:
            vendor_caps._CAPS["asa"] = vendor_caps.VendorCaps(
                name="asa",
                label="ASA",
                config_field="config",
                requires_vdom=False,
                supports_inspect=True,
                supports_compare=True,
                supports_find=True,
                supports_packet=False,
            )
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
            self.assertEqual(status, 400)
            self.assertEqual(payload.get("error"), "packet_not_supported")
        finally:
            vendor_caps._CAPS.update(original_caps)

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
