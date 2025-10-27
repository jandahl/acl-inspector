"""Tests for the modular settings loader."""

import json
import tempfile
import unittest
from pathlib import Path

from webui import settings as settings_mod


class SettingsLoaderTest(unittest.TestCase):
    def test_defaults_when_file_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            missing = Path(tmpdir) / "settings.json"
            loaded = settings_mod.load_settings(missing, env={})
            base = Path(tmpdir)

            self.assertEqual(loaded.server.host, "127.0.0.1")
            self.assertEqual(loaded.server.port, 8083)
            self.assertTrue(loaded.features.predictive_search.enabled)
            self.assertEqual(
                loaded.paths.configs["asa"],
                str((base / "configs/cisco").resolve()),
            )
            self.assertEqual(
                loaded.paths.configs["fortigate"],
                str((base / "configs/fortigate").resolve()),
            )
            self.assertIn("packet-check", loaded.beta.enabled_modules)

    def test_json_overrides_merge_with_defaults(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = Path(tmpdir) / "settings.json"
            data = {
                "server": {"host": "0.0.0.0", "port": 9090, "prewarm_all": True},
                "paths": {
                    "configs": {"asa": "asa-dir"},
                    "themes_dir": "themes-custom",
                    "cache_dir": "cache-dir",
                },
                "features": {"predictive_search": {"limit": 25}},
                "beta": {"enabled_modules": ["packet_probe"]},
            }
            with cfg_path.open("w", encoding="utf-8") as handle:
                json.dump(data, handle)

            loaded = settings_mod.load_settings(cfg_path, env={})
            base = Path(tmpdir)

            self.assertEqual(loaded.server.host, "0.0.0.0")
            self.assertEqual(loaded.server.port, 9090)
            self.assertTrue(loaded.server.prewarm_all)
            self.assertEqual(
                loaded.paths.configs["asa"],
                str((base / "asa-dir").resolve()),
            )
            self.assertEqual(loaded.features.predictive_search.limit, 25)
            self.assertIn("packet-probe", loaded.beta.enabled_modules)
            self.assertEqual(
                loaded.paths.cache_dir,
                str((base / "cache-dir").resolve()),
            )

    def test_environment_overrides(self):
        env = {
            "ACLINSPECTOR_CONFIGS_CISCO": "/data/asa",
            "ACLINSPECTOR_FEATURES__PREDICTIVE_SEARCH__LIMIT": "75",
            "ACLINSPECTOR_DISK_CACHE_ENABLED": "true",
            "ACLINSPECTOR_BETA_MODULES": "packet_probe,foo",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_file = Path(tmpdir) / "settings.json"
            loaded = settings_mod.load_settings(settings_file, env=env)

        self.assertEqual(loaded.paths.configs["asa"], "/data/asa")
        self.assertEqual(loaded.features.predictive_search.limit, 75)
        self.assertTrue(loaded.features.disk_cache.enabled)
        self.assertEqual(tuple(sorted(loaded.beta.enabled_modules)), ("foo", "packet-probe"))

    def test_cli_overrides_merge_last(self):
        overrides = {
            "paths": {"cache_dir": "/tmp/cache"},
            "features": {"predictive_search": {"mode": "fuzzy"}},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_file = Path(tmpdir) / "settings.json"
            env = {"ACLINSPECTOR_SEARCH_MODE": "prefix"}
            loaded = settings_mod.load_settings(settings_file, env=env, cli_overrides=overrides)

        self.assertEqual(loaded.features.predictive_search.mode, "fuzzy")
        self.assertEqual(loaded.paths.cache_dir, "/tmp/cache")

    def test_beta_module_normalisation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = Path(tmpdir) / "settings.json"
            data = {"beta": {"enabled_modules": ["Packet_Probe", "PACKET-PROBE", "packet-check"]}}
            with cfg_path.open("w", encoding="utf-8") as handle:
                json.dump(data, handle)

            loaded = settings_mod.load_settings(cfg_path, env={})

        self.assertEqual(tuple(sorted(loaded.beta.enabled_modules)), ("packet-check", "packet-probe"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
