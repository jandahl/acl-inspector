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

    raw = html.unescape(text or "")
    lines = []
    marker = "<--- more --->"
    for line in raw.splitlines():
        working = line
        lower_working = working.lower()
        if marker in lower_working:
            while marker in lower_working:
                idx = lower_working.index(marker)
                end = idx + len(marker)
                prefix = working[:idx]
                suffix = working[end:]
                prefix = prefix.rstrip()
                suffix = suffix.lstrip()
                if prefix and suffix:
                    working = prefix + " " + suffix
                elif suffix:
                    working = suffix
                else:
                    working = prefix
                lower_working = working.lower()
        stripped = working.strip()
        if not stripped:
            continue
        lines.append(working)

    cleaned = "\n".join(lines)
    if raw.endswith(("\n", "\r")) and not cleaned.endswith("\n"):
        cleaned += "\n"
    return cleaned


__all__ = ["clean_config_text"]
