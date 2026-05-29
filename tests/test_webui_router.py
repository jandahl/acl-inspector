# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Router integration tests."""

import tempfile
import unittest
from pathlib import Path

from webui import settings as settings_mod
from webui.handlers import register_api
from webui.router import Request, Router
from webui.state import AppState


class RouterTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        base = Path(self.tmpdir.name)
        configs = base / "configs" / "cisco"
        configs.mkdir(parents=True, exist_ok=True)
        (configs / "sample.cfg").write_text("object network OBJ\n host 192.0.2.1\n", encoding="utf-8")
        self.settings = settings_mod.load_settings(
            base / "settings.json",
            env={"ACLINSPECTOR_CONFIGS_CISCO": str(configs)},
        )
        self.state = AppState.create(self.settings)
        self.router = Router()
        register_api(self.router, self.state)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_objects_route(self):
        request = Request(
            method="GET",
            path="/api/objects",
            query={"vendor": ["asa"], "config": ["sample.cfg"], "q": ["obj"], "mode": ["prefix"]},
            headers={},
            body=b"",
            state=self.state,
        )
        response = self.router.dispatch(request)
        self.assertEqual(response.status, 200)
        self.assertIn(b"OBJ", response.body)

    def test_unknown_route(self):
        request = Request(
            method="GET",
            path="/unknown",
            query={},
            headers={},
            body=b"",
            state=self.state,
        )
        with self.assertRaises(Exception):
            self.router.dispatch(request)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
