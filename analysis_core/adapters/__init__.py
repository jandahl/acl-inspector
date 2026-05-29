# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Parser adapters for vendor-specific indexing."""

from .asa import build_index as build_asa_index
from .fortigate import build_index as build_fortigate_index

__all__ = ["build_asa_index", "build_fortigate_index"]
