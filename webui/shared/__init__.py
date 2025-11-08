"""Shared utilities for web UI variants."""

from . import settings
from .state import AppState
from .themes import DEFAULT_THEMES, build_singularity_palette
from .fonts import FontFile, discover_fonts, render_font_css
__all__ = [
    "settings",
    "AppState",
    "DEFAULT_THEMES",
    "build_singularity_palette",
    "FontFile",
    "discover_fonts",
    "render_font_css",
]
