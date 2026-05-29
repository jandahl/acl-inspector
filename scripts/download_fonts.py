#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Download open fonts declared in fonts/fonts.json."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "fonts" / "fonts.json"
DOWNLOAD_ROOT = ROOT / "fonts" / "downloaded"


def guess_format(filename: str) -> str:
    ext = filename.lower().rsplit(".", 1)[-1]
    if ext == "woff2":
        return "woff2"
    if ext == "woff":
        return "woff"
    if ext == "otf":
        return "opentype"
    return "truetype"


def fetch(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as response:  # nosec B310
        data = response.read()
    destination.write_bytes(data)


def build_runtime_manifest(font: Dict[str, object], downloaded: List[Dict[str, str]]) -> Dict[str, object]:
    return {
        "family": font["family"],
        "display": font.get("display", "swap"),
        "variants": downloaded,
    }


def download_fonts(force: bool = False) -> int:
    if not MANIFEST_PATH.exists():
        print(f"Manifest {MANIFEST_PATH} not found", file=sys.stderr)
        return 1
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    fonts = manifest.get("fonts", [])
    if not fonts:
        print("No fonts declared in manifest", file=sys.stderr)
        return 1
    updated = 0
    for font in fonts:
        slug = font.get("slug")
        family = font.get("family")
        if not slug or not family:
            continue
        target_dir = DOWNLOAD_ROOT / slug
        target_dir.mkdir(parents=True, exist_ok=True)
        variants = []
        for variant in font.get("variants", []):
            filename = variant.get("filename")
            url = variant.get("url")
            if not filename or not url:
                continue
            destination = target_dir / filename
            if destination.exists() and not force:
                print(f"✓ {family} {filename} (cached)")
            else:
                try:
                    print(f"↓ {family} {filename}")
                    fetch(url, destination)
                    updated += 1
                except urllib.error.URLError as exc:
                    print(f"! Failed to download {url}: {exc}", file=sys.stderr)
                    if destination.exists():
                        destination.unlink(missing_ok=True)
                    continue
            variants.append(
                {
                    "style": variant.get("style", "normal"),
                    "weight": str(variant.get("weight", "400")),
                    "filename": filename,
                    "format": variant.get("format") or guess_format(filename),
                }
            )
        if variants:
            manifest_path = target_dir / "manifest.json"
            manifest_path.write_text(
                json.dumps(build_runtime_manifest(font, variants), indent=2) + "\n",
                encoding="utf-8",
            )
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description="Download libre fonts for the ACL Inspector web UI.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download fonts even if they already exist.",
    )
    args = parser.parse_args()
    try:
        updated = download_fonts(force=args.force)
    except KeyboardInterrupt:
        print("Aborted", file=sys.stderr)
        return 1
    if updated == 0:
        print("Fonts are up to date.")
    else:
        print(f"Downloaded {updated} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
