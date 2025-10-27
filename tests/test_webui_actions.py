"""Tests for action handlers."""

import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
