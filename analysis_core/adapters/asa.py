# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""ASA index adapter."""

from __future__ import annotations

import ipaddress
import logging
import re
from collections import defaultdict
from typing import Dict, List, Set, Union

from parsers.cisco import asa as asa_parser

logger = logging.getLogger(__name__)

OBJECT_BASE_POPULARITY = 1.0
GROUP_BASE_POPULARITY = 1.0

NetworkLike = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]
AddressLike = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]


def _collect_interface_networks(cfg: asa_parser.ASAConfig) -> List[NetworkLike]:
    nets: List[NetworkLike] = []
    for meta in getattr(cfg, "interfaces", {}).values():
        candidate = meta.get("ipv4")
        if isinstance(candidate, (ipaddress.IPv4Network, ipaddress.IPv6Network)):
            nets.append(candidate)
    return nets


def _value_lives_on_interface(
    value: Union[AddressLike, NetworkLike], interfaces: List[NetworkLike]
) -> bool:
    if not interfaces:
        return False
    if isinstance(value, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
        return any(value in net for net in interfaces if net.version == value.version)
    if isinstance(value, (ipaddress.IPv4Network, ipaddress.IPv6Network)):
        return any(
            value.subnet_of(net) or value == net for net in interfaces if net.version == value.version
        )
    return False


def build_index(text: str) -> Dict[str, object]:
    """Build predictive-search index for ASA configs."""

    cfg = asa_parser.ASAConfig(text)
    interface_networks = _collect_interface_networks(cfg)
    objects = sorted(cfg.network_objects.keys())
    groups = sorted(cfg.network_object_groups.keys())
    literals: Set[str] = set()
    details: Dict[str, Dict[str, object]] = {}
    object_homes: Dict[str, bool] = {}
    for name, members in cfg.network_objects.items():
        if not members:
            continue
        addresses = sorted(str(entry) for entry in members)
        literals.update(addresses)
        details[name] = {"addresses": addresses}
        object_homes[name] = any(
            _value_lives_on_interface(member, interface_networks) for member in members
        )

    object_popularity: Dict[str, float] = defaultdict(float)
    group_popularity: Dict[str, float] = defaultdict(float)

    for name in objects:
        object_popularity[name] += OBJECT_BASE_POPULARITY
    for name in groups:
        group_popularity[name] += GROUP_BASE_POPULARITY

    for members in cfg.network_object_groups.values():
        for member in members:
            if isinstance(member, dict):
                if "object" in member:
                    object_popularity[member["object"]] += 1.2
                elif "group-object" in member:
                    group_popularity[member["group-object"]] += 0.8

    try:
        acl_references = cfg.flatten_acl()
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Failed to flatten ACL entries for popularity weighting: %s", exc, exc_info=True)
        acl_references = []

    re_object = re.compile(r"\bobject\s+([A-Za-z0-9_.-]+)", re.IGNORECASE)
    re_group = re.compile(r"\bobject-group\s+([A-Za-z0-9_.-]+)", re.IGNORECASE)
    for entry in acl_references:
        raw = entry.get("raw", "")
        for match in re_object.finditer(raw):
            object_popularity[match.group(1)] += 2.5
        for match in re_group.finditer(raw):
            group_popularity[match.group(1)] += 1.8

    popularity = {
        "object": dict(object_popularity),
        "group": dict(group_popularity),
    }

    return {
        "objects": objects,
        "groups": groups,
        "literals": sorted(literals),
        "object_details": details,
        "object_homes": object_homes,
        "popularity": popularity,
    }
