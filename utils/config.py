"""Config text helpers."""

from __future__ import annotations

import html
import logging
from pathlib import Path
from typing import Union

logger = logging.getLogger(__name__)


def load_config_text(path: Union[str, Path]) -> str:
    """Read config text with a tolerant decoder.

    We prefer UTF-8 but fall back to ignoring invalid sequences so configs with
    stray bytes do not break predictive search or metadata endpoints.
    """

    target = Path(path)
    try:
        return target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        logger.debug("UTF-8 decode failed for %s: %s; stripping invalid bytes.", target, exc)
        data = target.read_bytes()
        return data.decode("utf-8", errors="ignore")


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


__all__ = ["clean_config_text", "load_config_text"]
