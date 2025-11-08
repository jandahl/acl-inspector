"""Compatibility wrapper for page rendering/registration."""

from __future__ import annotations

from webui.router import Router
from webui.shared.state import AppState
from webui.v1_legacy import pages as legacy_pages
from webui.v2_singularity import pages as singularity_pages

__all__ = ["register_pages", "_render_home", "_render_singularity"]


def register_pages(router: Router, state: AppState) -> None:
    """Register both legacy and Singularity page routes."""

    legacy_pages.register_routes(router, state)
    singularity_pages.register_routes(router, state)


def _render_home(state: AppState) -> str:
    """Backwards-compatible helper for legacy handler."""

    return legacy_pages._render_home(state)


def _render_singularity(state: AppState) -> str:
    """Backwards-compatible helper for direct template tests."""

    return singularity_pages._render_singularity(state)
