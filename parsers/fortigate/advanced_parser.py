# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Parallel FortiGate parser powered by fortios-xutils (Scaffolding)."""

from __future__ import annotations
from typing import Optional, Set, Union


class AdvancedFTGConfig:
    """Advanced FortiGate parser using fortios-xutils (Scaffolding)."""

    def __init__(self, text: str, vdom: Optional[str] = None) -> None:
        try:
            import fortios_xutils as _fortios_xutils  # noqa: F401
        except ImportError:
            raise ImportError(
                "fortios-xutils is required for the external engine. "
                "Install with: pip install .[external]"
            )

        # Scaffolding is not yet implemented end-to-end.
        raise NotImplementedError(
            "Advanced FortiGate engine is not yet implemented. Remove --use-external-engines to continue."
        )

    def resolve_addr_token(self, *args, **kwargs):
        raise NotImplementedError()

    def resolve_service_names(self, *args, **kwargs):
        raise NotImplementedError()

    def to_ir(self, device_name: Optional[str] = None):
        from . import ir_export
        return ir_export.to_ir(self, device_name)
