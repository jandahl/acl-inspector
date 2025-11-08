"""Compatibility wrapper for ASA adapter."""

from analysis_core.adapters.asa import build_index

from typing import Dict, Set

from parsers.cisco import asa as asa_parser


def build_index(text: str) -> Dict[str, object]:
    """Build predictive-search index for ASA configs."""

    cfg = asa_parser.ASAConfig(text)
    objects = sorted(cfg.network_objects.keys())
    groups = sorted(cfg.network_object_groups.keys())
    literals: Set[str] = set()
    object_meta: Dict[str, Dict[str, object]] = {}
    for name in objects:
        members = cfg.network_objects.get(name, set())
        literal_values = sorted(str(entry) for entry in members)
        literals.update(literal_values)
        object_meta[name] = {
            "literals": literal_values,
            "primary": literal_values[0] if literal_values else "",
        }
    group_meta: Dict[str, Dict[str, object]] = {}
    for name in groups:
        members = cfg.network_object_groups.get(name, [])
        rendered = []
        for member in members:
            if isinstance(member, dict):
                if "group-object" in member:
                    rendered.append(f"group {member['group-object']}")
                elif "object" in member:
                    rendered.append(f"object {member['object']}")
            else:
                text = str(member)
                rendered.append(text)
                literals.add(text)
        group_meta[name] = {
            "members": rendered,
            "primary": "",
        }
    literal_meta = {value: {"primary": value} for value in literals}
    return {
        "objects": objects,
        "groups": groups,
        "literals": sorted(literals),
        "meta": {
            "object": object_meta,
            "group": group_meta,
            "literal": literal_meta,
        },
    }
