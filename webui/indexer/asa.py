"""ASA index adapter."""

from __future__ import annotations

from typing import Dict, Set

from parsers.cisco import asa as asa_parser


def build_index(text: str) -> Dict[str, object]:
    """Build predictive-search index for ASA configs."""

    cfg = asa_parser.ASAConfig(text)
    objects = sorted(cfg.network_objects.keys())
    groups = sorted(cfg.network_object_groups.keys())
    literals: Set[str] = set()
    for members in cfg.network_objects.values():
        for entry in members:
            literals.add(str(entry))
    return {
        "objects": objects,
        "groups": groups,
        "literals": sorted(literals),
    }
