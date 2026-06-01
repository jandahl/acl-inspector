# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Parallel ASA parser powered by ciscoconfparse (Scaffolding)."""

from __future__ import annotations
from typing import Optional, Set, Union


class AdvancedASAConfig:
    """Advanced ASA parser using ciscoconfparse (Scaffolding)."""

    def __init__(self, text: str) -> None:
        try:
            from ciscoconfparse import CiscoConfParse  # noqa: F401
        except ImportError:
            raise ImportError(
                "ciscoconfparse is required for the external engine. "
                "Install with: pip install .[external]"
            )

        # Scaffolding is not yet implemented end-to-end.
        raise NotImplementedError(
            "Advanced ASA engine is not yet implemented. Remove --use-external-engines to continue."
        )

    def resolve_network(self, *args, **kwargs):
        raise NotImplementedError()

    def resolve_service_group(self, *args, **kwargs):
        raise NotImplementedError()

    def to_ir(self, device_name: Optional[str] = None):
        """Map to common IR using ir_export."""
        from . import ir_export
        return ir_export.to_ir(self, device_name)
