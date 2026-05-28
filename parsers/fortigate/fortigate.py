# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Backward-compatible facade for the FortiGate parser API."""

from __future__ import annotations

from .config import FTGConfig  # noqa: F401
from .inspect import evaluate, compare_old_new, inspect_host  # noqa: F401

__all__ = [
    "FTGConfig",
    "evaluate",
    "compare_old_new",
    "inspect_host",
]
