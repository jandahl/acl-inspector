# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Compatibility shim for legacy imports.

Presentation layers should depend on :mod:`analysis_core.index` instead.
"""

from analysis_core.index import IndexEntry, IndexManager  # re-export
from analysis_core.adapters.asa import build_index as build_asa_index
from analysis_core.adapters.fortigate import build_index as build_fortigate_index

__all__ = [
    "IndexEntry",
    "IndexManager",
    "build_asa_index",
    "build_fortigate_index",
]
