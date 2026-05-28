# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""FortiGate index adapter."""

from __future__ import annotations

from typing import Dict


def build_index(_text: str) -> Dict[str, object]:
    """Return a minimal index skeleton for FortiGate (not yet implemented)."""

    return {
        "objects": [],
        "groups": [],
        "literals": [],
        "object_details": {},
        "popularity": {"object": {}, "group": {}},
    }
