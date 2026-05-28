# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Singularity TUI - Terminal User Interface for ACL-inspector.

A search-first, progressive disclosure terminal interface mirroring the
Singularity web UI concept but adapted for terminal environments.
"""

import importlib

__version__ = "0.1.0"
__all__ = ["SingularityApp"]

# Lazy import to avoid textual dependency in tests
def __getattr__(name):
    if name == "SingularityApp":
        from .app import SingularityApp
        return SingularityApp
    elif name == "app":
        return importlib.import_module(".app", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
