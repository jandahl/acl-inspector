"""Tests for action handlers."""

import tempfile
import unittest
from pathlib import Path

from parsers.cisco import asa as asa_parser
from webui import settings as settings_mod
from webui.handlers import actions as action_handlers
from webui.state import AppState

ASA_SAMPLE = """!
object network OBJ_WEB
 host 192.0.2.10
access-list OUTSIDE extended permit tcp any object OBJ_WEB eq 443
"""


class ActionHandlersTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        base = Path(self.tmpdir.name)
        self.config_dir = base / "configs" / "cisco"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        (self.config_dir / "sample.cfg").write_text(ASA_SAMPLE, encoding="utf-8")
        settings = settings_mod.load_settings(
            base / "settings.json",
            env={"ACLINSPECTOR_CONFIGS_CISCO": str(self.config_dir)},
        )
        self.state = AppState.create(settings)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_process_inspect(self):
        status, payload = action_handlers.process_run(
            self.state,
            {
                "vendor": ["asa"],
                "mode": ["inspect"],
                "config": ["sample.cfg"],
                "inspect": ["OBJ_WEB"],
            },
        )
        self.assertEqual(status, 200)
        self.assertIn("OBJ_WEB", payload["html"])
        self.assertEqual(payload.get("meta", {}).get("mode"), "inspect")
        self.assertEqual(payload.get("meta", {}).get("query"), "OBJ_WEB")
        history = self.state.history.snapshot()["entries"]
        self.assertTrue(history)
        self.assertEqual(history[0]["query"], "OBJ_WEB")

    def test_missing_config(self):
        status, payload = action_handlers.process_run(
            self.state,
            {
                "vendor": ["asa"],
                "mode": ["inspect"],
                "config": ["missing.cfg"],
                "inspect": ["OBJ_WEB"],
            },
        )
        self.assertEqual(status, 400)
        self.assertIn("error", payload)

    def test_history_replay_suppresses_record(self):
        status, payload = action_handlers.process_run(
            self.state,
            {
                "vendor": ["asa"],
                "mode": ["inspect"],
                "config": ["sample.cfg"],
                "inspect": ["OBJ_WEB"],
                "history_replay": ["1"],
            },
        )
        self.assertEqual(status, 200)
        self.assertIn("OBJ_WEB", payload["html"])
        history = self.state.history.snapshot()["entries"]
        self.assertFalse(history)

    def test_format_list_includes_more_suffix(self):
        text = action_handlers._format_list(["a", "b", "c", "d"], limit=2)
        self.assertEqual(text, "a, b (+2 more)")

    def test_fmt_preserves_brackets(self):
        rule = {
            "action": "permit",
            "src": ["192.0.2.0/24"],
            "dst": ["203.0.113.10"],
            "svc": {
                "proto": "tcp",
                "dst_ports": [("eq", (443, 443))],
                "dst_service_groups": [],
                "dst_service_objects": [],
            },
            "binding": {"interface": "outside", "direction": "in"},
            "proto": "tcp",
        }
        formatted = action_handlers._fmt(rule)
        self.assertIn("src=[192.0.2.0/24]", formatted)
        self.assertIn("dst=[203.0.113.10]", formatted)

    def test_parser_allows_hostname_objects(self):
        cfg = asa_parser.ASAConfig(
            """
object network OBJ_HOSTNAME
 host warsapd5.sapag.local
"""
        )
        values = cfg.network_objects.get("OBJ_HOSTNAME")
        self.assertIsNotNone(values)
        assert values is not None
        self.assertIn("warsapd5.sapag.local", {str(v) for v in values})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
