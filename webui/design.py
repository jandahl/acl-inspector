"""Helpers for design documentation and diagrams."""

from __future__ import annotations

import html
import os
import subprocess
from pathlib import Path
from typing import Dict, Tuple


_DOT_CACHE: Dict[Path, Tuple[Tuple[float, int], str]] = {}


class DiagramRenderError(RuntimeError):
    """Raised when a diagram cannot be rendered."""


def read_text_file(path: Path) -> str:
    """Return file contents, raising a friendly error if the file is missing."""

    if not path.exists():
        raise FileNotFoundError(f"Design document not found: {path}")
    return path.read_text(encoding="utf-8")


def dot_to_svg(path: Path) -> str:
    """
    Render a Graphviz DOT file to SVG.

    Uses a simple in-memory cache keyed on (mtime, size) to avoid invoking
    the dot binary repeatedly while editing.
    """

    if not path.exists():
        raise FileNotFoundError(f"Diagram not found: {path}")

    stat = path.stat()
    cache_key = (stat.st_mtime, stat.st_size)
    cached = _DOT_CACHE.get(path)
    if cached and cached[0] == cache_key:
        return cached[1]

    try:
        result = subprocess.run(
            ["dot", "-Tsvg", str(path)],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise DiagramRenderError(
            "Graphviz 'dot' binary not available. Install graphviz to render diagrams."
        ) from exc

    if result.returncode != 0:
        stderr = result.stderr.strip() or "Unknown error"
        raise DiagramRenderError(f"Graphviz rendering failed: {stderr}")

    svg = result.stdout
    _DOT_CACHE[path] = (cache_key, svg)
    return svg


def markdown_to_html(text: str) -> str:
    """
    Very small Markdown-to-HTML helper.

    We keep this intentionally minimal: headings become <h1>/<h2>, everything
    else is escaped and wrapped in <pre>. This avoids pulling in external
    renderers while still making the docs readable in-browser.
    """

    lines = text.splitlines()
    html_lines = []
    for line in lines:
        if line.startswith("# "):
            html_lines.append(f"<h1>{html.escape(line[2:].strip())}</h1>")
        elif line.startswith("## "):
            html_lines.append(f"<h2>{html.escape(line[3:].strip())}</h2>")
        elif line.startswith("### "):
            html_lines.append(f"<h3>{html.escape(line[4:].strip())}</h3>")
        else:
            html_lines.append(html.escape(line))
    body = "\n".join(html_lines)
    return f"<pre class='design-pre'>{body}</pre>"
