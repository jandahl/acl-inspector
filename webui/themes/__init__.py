"""Backward-compatible import surface for themes."""

from webui.shared.themes import (
    DEFAULT_THEMES,
    build_singularity_palette,
    load_iterm_theme,
    load_themes,
)

__all__ = ["DEFAULT_THEMES", "load_iterm_theme", "load_themes", "build_singularity_palette"]
