"""Compatibility wrappers for legacy handler imports."""

from webui.shared.api import register_api
from webui.handlers.pages import register_pages

__all__ = ["register_api", "register_pages"]
