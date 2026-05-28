# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
import json
import tempfile
from pathlib import Path
import unittest

from webui.fonts import discover_fonts, render_font_css


class FontDiscoveryTest(unittest.TestCase):
    def test_empty_directories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / "fonts" / "downloaded").mkdir(parents=True)
            (base / "fonts" / "custom").mkdir(parents=True)
            assets = discover_fonts(base)
            self.assertEqual(assets, [])
            css = render_font_css(assets)
            self.assertIn("no local fonts", css)

    def test_manifest_discovery(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            manifest_dir = base / "fonts" / "downloaded" / "sample"
            manifest_dir.mkdir(parents=True)
            font_path = manifest_dir / "SampleFont.ttf"
            font_path.write_bytes(b"fake font data")
            manifest = {
                "family": "Sample Font",
                "display": "swap",
                "variants": [
                    {
                        "style": "normal",
                        "weight": "400",
                        "filename": "SampleFont.ttf",
                        "format": "truetype",
                    }
                ],
            }
            (manifest_dir / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            assets = discover_fonts(base)
            self.assertEqual(len(assets), 1)
            self.assertEqual(assets[0].family, "Sample Font")
            css = render_font_css(assets)
            self.assertIn("@font-face", css)
            self.assertIn("SampleFont.ttf", css)


if __name__ == "__main__":
    unittest.main()
