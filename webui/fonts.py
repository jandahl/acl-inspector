# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Helpers for loading local font assets."""

from __future__ import annotations

import json
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Tuple


@dataclass(frozen=True)
class FontFile:
    """Represents a single font variant and its served asset."""

    family: str
    style: str
    weight: str
    display: str
    format: str
    url_path: str
    file_path: Path


FONT_ROOTS: Tuple[Path, ...] = (
    Path("fonts/downloaded"),
    Path("fonts/custom"),
)


def _guess_format(filename: str) -> str:
    ext = filename.lower().rsplit(".", 1)[-1]
    if ext in {"woff2", "woff", "ttf", "otf"}:
        return {
            "ttf": "truetype",
            "otf": "opentype",
        }.get(ext, ext)
    sniff = mimetypes.guess_type(filename)[0] or ""
    if sniff.endswith("woff2"):
        return "woff2"
    if sniff.endswith("woff"):
        return "woff"
    if sniff.endswith("opentype"):
        return "opentype"
    if sniff.endswith("truetype"):
        return "truetype"
    return "truetype"


def _load_manifest(path: Path) -> List[FontFile]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    family = data.get("family")
    if not family:
        return []
    display = data.get("display", "swap")
    variants = data.get("variants", [])
    slug = path.parent.name
    entries: List[FontFile] = []
    for entry in variants:
        filename = entry.get("filename")
        if not filename:
            continue
        style = entry.get("style", "normal")
        weight = str(entry.get("weight", "400"))
        format_hint = entry.get("format") or _guess_format(filename)
        file_path = path.parent / filename
        if not file_path.exists():
            continue
        url_path = f"/static/fonts/{slug}/{filename}"
        entries.append(
            FontFile(
                family=family,
                style=style,
                weight=weight,
                display=display,
                format=format_hint,
                url_path=url_path,
                file_path=file_path,
            )
        )
    return entries


def discover_fonts(base_dir: Path = Path(".")) -> List[FontFile]:
    """Discover available local fonts using manifest files."""

    assets: List[FontFile] = []
    for root in FONT_ROOTS:
        directory = base_dir / root
        if not directory.is_dir():
            continue
        for manifest in directory.glob("*/manifest.json"):
            assets.extend(_load_manifest(manifest))
    return assets


def render_font_css(files: Iterable[FontFile]) -> str:
    """Render @font-face CSS rules for the provided fonts."""

    lines = ["/* Local font overrides generated at runtime */"]
    for font in files:
        lines.append("@font-face {")
        lines.append(f"  font-family: '{font.family}';")
        lines.append(f"  src: url('{font.url_path}') format('{font.format}');")
        lines.append(f"  font-style: {font.style};")
        lines.append(f"  font-weight: {font.weight};")
        lines.append(f"  font-display: {font.display};")
        lines.append("}")
    if len(lines) == 1:
        lines.append("/* (no local fonts detected) */")
    return "\n".join(lines) + "\n"

