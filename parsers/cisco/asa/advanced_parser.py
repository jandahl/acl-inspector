# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Parallel ASA parser powered by ciscoconfparse (Scaffolding)."""

from __future__ import annotations


class AdvancedASAConfig:
    """Advanced ASA parser using ciscoconfparse (Scaffolding)."""

    def __init__(self, text: str) -> None:
        try:
            import ciscoconfparse  # noqa: F401
        except ImportError:
            raise ImportError(
                "ciscoconfparse is required for the external engine. "
                "Install with: pip install .[external]"
            )

        # Scaffolding is not yet implemented end-to-end.
        raise NotImplementedError(
            "Advanced ASA engine is not yet implemented."
        )
