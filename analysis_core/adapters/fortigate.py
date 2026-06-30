# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""FortiGate index adapter.

Mirrors :mod:`analysis_core.adapters.asa`: builds the predictive-search index
from a parsed :class:`~parsers.fortigate.config.FTGConfig`. Address objects and
VIPs are treated as searchable "objects"; address-groups and VIP-groups as
"groups". Popularity is seeded with a base weight and boosted by group
membership and policy references.
"""

from __future__ import annotations

import ipaddress
import logging
from collections import defaultdict
from typing import Dict, List, Set

from parsers.fortigate.config import FTGConfig

logger = logging.getLogger(__name__)

OBJECT_BASE_POPULARITY = 1.0
GROUP_BASE_POPULARITY = 1.0


def _resolved_addresses(cfg: FTGConfig, name: str) -> List[str]:
    """Best-effort resolution of an address/VIP name to sorted address strings."""
    try:
        resolved = cfg.resolve_addr_token(name)
    except Exception:  # pragma: no cover - defensive
        return []
    out = []
    for entry in resolved:
        if isinstance(entry, (ipaddress.IPv4Address, ipaddress.IPv4Network,
                              ipaddress.IPv6Address, ipaddress.IPv6Network)):
            out.append(str(entry))
    return sorted(out)


def build_index(text: str) -> Dict[str, object]:
    """Build predictive-search index for FortiGate configs."""

    cfg = FTGConfig(text)

    # Address objects + VIPs are searchable single entities; addrgrps + vipgrps
    # are groups.
    object_names = sorted(set(cfg.addresses) | set(cfg.vips))
    group_names = sorted(set(cfg.addrgrps) | set(cfg.vipgrps))

    literals: Set[str] = set()
    details: Dict[str, Dict[str, object]] = {}
    for name in object_names:
        addresses = _resolved_addresses(cfg, name)
        if addresses:
            literals.update(addresses)
            details[name] = {"addresses": addresses}

    object_popularity: Dict[str, float] = defaultdict(float)
    group_popularity: Dict[str, float] = defaultdict(float)

    for name in object_names:
        object_popularity[name] += OBJECT_BASE_POPULARITY
    for name in group_names:
        group_popularity[name] += GROUP_BASE_POPULARITY

    object_set = set(object_names)
    group_set = set(group_names)

    def _bump(token: str, obj_weight: float, grp_weight: float) -> None:
        if token in group_set:
            group_popularity[token] += grp_weight
        elif token in object_set:
            object_popularity[token] += obj_weight

    # Address-group membership weight.
    for members in cfg.addrgrps.values():
        for member in members:
            if isinstance(member, dict) and "object" in member:
                _bump(member["object"], 1.2, 0.8)
    for members in cfg.vipgrps.values():
        for member in members:
            if isinstance(member, str):
                _bump(member, 1.2, 0.8)

    # Policy reference weight (srcaddr/dstaddr tokens).
    try:
        policies = cfg.policies
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Failed to read policies for popularity weighting: %s", exc, exc_info=True)
        policies = []
    for policy in policies:
        for key in ("srcaddr", "dstaddr"):
            for token in policy.get(key, []) or []:
                _bump(token, 2.5, 1.8)

    popularity = {
        "object": dict(object_popularity),
        "group": dict(group_popularity),
    }

    return {
        "objects": object_names,
        "groups": group_names,
        "literals": sorted(literals),
        "object_details": details,
        "popularity": popularity,
    }
