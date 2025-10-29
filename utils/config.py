"""Config text helpers."""

from __future__ import annotations

import html


def clean_config_text(text: str) -> str:
    """Strip loader artefacts and normalize entities.

    - Drops lines that match the pager marker ``<--- More --->``.
    - Normalizes HTML entities (``&lt;`` -> ``<``) so downstream parsing/render
      works with literal characters.
    - Preserves a trailing newline when present so line counts remain stable.
    """

    if not text:
        return ""

    lines = []
    for line in text.splitlines():
        if line.strip() == "<--- More --->":
            continue
        lines.append(line)

    cleaned = "\n".join(lines)
    if text.endswith(("\n", "\r")) and not cleaned.endswith("\n"):
        cleaned += "\n"
    return html.unescape(cleaned)


__all__ = ["clean_config_text"]
