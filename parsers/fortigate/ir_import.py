# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""IR import functionality for FortiGate.

Converts vendor-agnostic Intermediate Representation (IR) format to FortiGate
configuration syntax. This enables migration from other platforms to FortiGate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from parsers import model as ir

__all__ = ["from_ir"]


def from_ir(device: "ir.Device", vdom: str = "root") -> str:
    """Convert IR.Device representation to FortiGate configuration syntax."""

    lines: List[str] = [
        f"# Generated from IR (vendor={device.vendor}, version={device.version})",
        f"# Target VDOM: {vdom}",
        "",
    ]

    literal_members = _discover_literal_members(device.groups)

    lines.extend(_emit_firewall_addresses(device.objects, literal_members))
    lines.extend(_emit_addr_groups(device.groups, literal_members))
    lines.extend(_emit_service_blocks(device.service_groups))

    vip_defs = _collect_vip_nat(device.nats)
    if vip_defs:
        lines.extend(_emit_vip_block(vip_defs))

    policy_nat_map = _index_policy_snat(device.nats)
    lines.extend(_emit_policies(device.acls, policy_nat_map))
    lines.extend(_emit_central_snat_map(device.nats))
    lines.extend(_emit_static_routes(device.static_routes))
    lines.extend(_emit_dynamic_routes(device.dynamic_routing))

    leftover_nat = [
        nat.detail for nat in device.nats
        if (nat.detail or {}).get('type') not in {'vip', 'policy-snat', 'central-snat'}
    ]
    if leftover_nat:
        lines.append("# The following NAT records require manual conversion:")
        for detail in leftover_nat:
            lines.append(f"#   - {detail}")

    return "\n".join(lines).rstrip() + "\n"


# --------------------------- Address helpers --------------------------- #

def _emit_firewall_addresses(objects: List["ir.Object"], literal_members: Dict[str, str]) -> List[str]:
    lines: List[str] = []
    if not objects and not literal_members:
        return lines

    lines.append("config firewall address")
    for obj in objects:
        lines.append(f'    edit "{obj.name}"')
        if obj.literals:
            literal = obj.literals[0]
            if '/' in literal:
                ip, prefix = literal.split('/', 1)
                netmask = _prefix_to_netmask(int(prefix))
                lines.append(f"        set subnet {ip} {netmask}")
            else:
                lines.append(f"        set subnet {literal} 255.255.255.255")
        lines.append("    next")

    for name, literal in sorted(literal_members.items()):
        lines.append(f'    edit "{name}"')
        if '/' in literal:
            ip, prefix = literal.split('/', 1)
            netmask = _prefix_to_netmask(int(prefix))
            lines.append(f"        set subnet {ip} {netmask}")
        else:
            lines.append(f"        set subnet {literal} 255.255.255.255")
        lines.append("    next")

    lines.append("end")
    lines.append("")
    return lines


def _emit_addr_groups(groups: List["ir.Group"], literal_members: Dict[str, str]) -> List[str]:
    lines: List[str] = []
    if not groups:
        return lines

    lines.append("config firewall addrgrp")
    for grp in groups:
        lines.append(f'    edit "{grp.name}"')
        members: List[str] = []
        for member in grp.members:
            if member.kind == 'object' and member.ref:
                members.append(f'"{member.ref}"')
            elif member.kind == 'group' and member.ref:
                members.append(f'"{member.ref}"')
            elif member.kind == 'literal' and member.literal:
                literal_name = _literal_object_name(member.literal)
                literal_members.setdefault(literal_name, member.literal)
                members.append(f'"{literal_name}"')
        if members:
            lines.append(f"        set member {' '.join(members)}")
        lines.append("    next")
    lines.append("end")
    lines.append("")
    return lines


def _discover_literal_members(groups: List["ir.Group"]) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for grp in groups:
        for member in grp.members:
            if member.kind == 'literal' and member.literal:
                name = _literal_object_name(member.literal)
                mapping.setdefault(name, member.literal)
    return mapping


def _literal_object_name(literal: str) -> str:
    return f"auto_{literal.replace('/', '_').replace('.', '_')}"


# --------------------------- Service helpers --------------------------- #

def _emit_service_blocks(service_groups: List["ir.ServiceGroup"]) -> List[str]:
    service_objects: List[Tuple[str, str, str, object, object]] = []
    service_group_refs: Dict[str, List[str]] = {}

    for svc_grp in service_groups:
        has_proto = False
        group_members: List[str] = []
        for member in svc_grp.members:
            if 'proto' in member:
                has_proto = True
                service_objects.append(
                    (svc_grp.name, member.get('proto'), member.get('op'), member.get('v1'), member.get('v2'))
                )
            elif 'object' in member:
                group_members.append(member['object'])
            elif 'group' in member:
                group_members.append(member['group'])
        if group_members and not has_proto:
            service_group_refs[svc_grp.name] = group_members

    lines: List[str] = []
    if service_objects:
        lines.append("config firewall service custom")
        grouped: Dict[str, Dict[str, List[str]]] = {}
        for name, proto, op, v1, v2 in service_objects:
            grouped.setdefault(name, {'tcp': [], 'udp': []})
            if proto in ('tcp', 'udp'):
                if op == 'range':
                    grouped[name][proto].append(f"{v1}-{v2}")
                else:
                    grouped[name][proto].append(f"{v1}")
        for name, spec in grouped.items():
            lines.append(f'    edit "{name}"')
            if spec['tcp']:
                lines.append(f"        set tcp-portrange {' '.join(spec['tcp'])}")
            if spec['udp']:
                lines.append(f"        set udp-portrange {' '.join(spec['udp'])}")
            lines.append("    next")
        lines.append("end")
        lines.append("")

    if service_group_refs:
        lines.append("config firewall service group")
        for name, members in service_group_refs.items():
            lines.append(f'    edit "{name}"')
            member_str = ' '.join(f'"{m}"' for m in members)
            lines.append(f"        set member {member_str}")
            lines.append("    next")
        lines.append("end")
        lines.append("")
    return lines


# --------------------------- VIP helpers ------------------------------- #

def _emit_vip_block(vip_defs: List[Dict[str, object]]) -> List[str]:
    lines: List[str] = ["config firewall vip"]
    for detail in vip_defs:
        name = detail.get('name')
        if not name:
            continue
        lines.append(f'    edit "{name}"')
        extip = detail.get('extip') or []
        if extip:
            lines.append(f"        set extip {' '.join(extip)}")
        mapped = detail.get('mappedip') or []
        if mapped:
            lines.append(f"        set mappedip {' '.join(mapped)}")
        extintf = detail.get('extintf')
        if extintf:
            lines.append(f'        set extintf "{extintf}"')
        if detail.get('portforward'):
            lines.append("        set portforward enable")
            if detail.get('extport'):
                lines.append(f"        set extport {detail.get('extport')}")
            if detail.get('mappedport'):
                lines.append(f"        set mappedport {detail.get('mappedport')}")
        policies = detail.get('policies') or []
        if policies:
            joined = ", ".join(policies)
            lines.append(f"        # referenced by policies {joined}")
        lines.append("    next")
    lines.append("end")
    lines.append("")
    return lines


def _collect_vip_nat(nats: List["ir.NAT"]) -> List[Dict[str, object]]:
    vip_details: List[Dict[str, object]] = []
    for nat in nats:
        detail = nat.detail or {}
        if detail.get('type') == 'vip':
            vip_details.append(detail)
    return vip_details


# --------------------------- Policy helpers --------------------------- #

def _emit_policies(acls: List["ir.ACL"], policy_nat_map: Dict[str, Dict[str, object]]) -> List[str]:
    if not acls:
        return []

    lines: List[str] = ["config firewall policy"]
    policy_seq = 1

    for acl in acls:
        for entry in acl.entries:
            policy_id, policy_seq = _resolve_policy_id(entry.binding, policy_seq)
            lines.append(f"    edit {policy_id}")

            action = 'accept' if entry.action == 'permit' else 'deny'
            lines.append(f"        set action {action}")

            binding = entry.binding or {}
            srcintf = _ensure_list(binding.get('srcintf'))
            dstintf = _ensure_list(binding.get('dstintf'))
            if srcintf:
                lines.append(f"        set srcintf {' '.join(_quote_list(srcintf))}")
            if dstintf:
                lines.append(f"        set dstintf {' '.join(_quote_list(dstintf))}")

            src = entry.src or ['all']
            src_quoted = [f'"{s}"' if s.lower() != 'all' else 'all' for s in src]
            lines.append(f"        set srcaddr {' '.join(src_quoted)}")

            dst = entry.dst or ['all']
            dst_quoted = [f'"{d}"' if d.lower() != 'all' else 'all' for d in dst]
            lines.append(f"        set dstaddr {' '.join(dst_quoted)}")

            svc = entry.svc or {}
            service_names: List[str] = []
            if svc.get('dst_service_groups'):
                service_names.extend(f'"{sg}"' for sg in svc['dst_service_groups'])
            if svc.get('dst_service_objects'):
                service_names.extend(f'"{so}"' for so in svc['dst_service_objects'])
            if not service_names:
                service_names = ['ALL']
            lines.append(f"        set service {' '.join(service_names)}")

            schedule = binding.get('schedule')
            if schedule:
                lines.append(f'        set schedule "{schedule}"')

            name = binding.get('name')
            if name:
                lines.append(f'        set name "{name}"')

            nat_detail = policy_nat_map.get(policy_id)
            if nat_detail:
                lines.append("        set nat enable")
                if nat_detail.get('ippool'):
                    lines.append("        set ippool enable")
                    pools = nat_detail.get('poolname') or []
                    pool_list = pools if isinstance(pools, list) else [pools]
                    if pool_list:
                        lines.append(f"        set poolname {' '.join(_quote_list(pool_list))}")
            elif binding.get('vip_refs'):
                lines.append("        set nat disable")

            lines.append("    next")

    lines.append("end")
    lines.append("")
    return lines


def _emit_central_snat_map(nats: List["ir.NAT"]) -> List[str]:
    entries = []
    for nat in nats:
        detail = nat.detail or {}
        if detail.get('type') == 'central-snat':
            entries.append(detail)
    if not entries:
        return []

    lines: List[str] = ["config firewall central-snat-map"]
    for idx, entry in enumerate(entries, start=1):
        seq = entry.get('seq') or idx
        lines.append(f"    edit {seq}")
        for key in ('srcintf', 'dstintf', 'orig-addr', 'dst-addr', 'nat-ippool'):
            value = entry.get(key)
            values = _ensure_list(value)
            if not values:
                continue
            quoted = ' '.join(_quote_list(values))
            lines.append(f"        set {key} {quoted}")
        lines.append("    next")
    lines.append("end")
    lines.append("")
    return lines


def _emit_static_routes(routes: List["ir.StaticRoute"]) -> List[str]:
    if not routes:
        return []
    lines: List[str] = ["config router static"]
    for idx, route in enumerate(routes, start=1):
        seq = route.destination or idx
        lines.append(f"    edit {seq}")
        if route.destination:
            lines.append(f"        set dst {route.destination}")
        if route.next_hop:
            lines.append(f"        set gateway {route.next_hop}")
        if route.interface:
            lines.append(f'        set device "{route.interface}"')
        if route.distance is not None:
            lines.append(f"        set distance {route.distance}")
        lines.append("    next")
    lines.append("end")
    lines.append("")
    return lines


def _emit_dynamic_routes(processes: List["ir.DynamicRoutingProcess"]) -> List[str]:
    lines: List[str] = []
    for proc in processes:
        if proc.protocol != 'ospf':
            continue
        lines.append("config router ospf")
        if proc.router_id:
            lines.append(f"    set router-id {proc.router_id}")
        if proc.networks:
            lines.append("    config network")
            for idx, net in enumerate(proc.networks, start=1):
                lines.append(f"        edit {idx}")
                prefix = net.get('prefix') or net.get('network')
                if prefix:
                    lines.append(f"            set prefix {prefix}")
                area = net.get('area')
                if area:
                    lines.append(f"            set area {area}")
                lines.append("        next")
            lines.append("    end")
        lines.append("end")
        lines.append("")
    return lines


def _index_policy_snat(nats: List["ir.NAT"]) -> Dict[str, Dict[str, object]]:
    mapping: Dict[str, Dict[str, object]] = {}
    for nat in nats:
        detail = nat.detail or {}
        if detail.get('type') != 'policy-snat':
            continue
        policy_id = detail.get('policy_id')
        if policy_id is None:
            continue
        mapping[str(policy_id)] = detail
    return mapping


def _resolve_policy_id(binding: Optional[Dict[str, object]], seq: int) -> Tuple[str, int]:
    binding = binding or {}
    policy_id = binding.get('policy_id')
    if policy_id is not None:
        pid = str(policy_id)
        try:
            num = int(pid)
            seq = max(seq, num + 1)
        except ValueError:
            pass
        return pid, seq
    pid = str(seq)
    return pid, seq + 1


# --------------------------- Utilities -------------------------------- #

def _prefix_to_netmask(prefix: int) -> str:
    mask = (0xffffffff >> (32 - prefix)) << (32 - prefix)
    return ".".join(str((mask >> offset) & 0xff) for offset in (24, 16, 8, 0))


def _ensure_list(value: Optional[object]) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def _quote_list(values: List[str]) -> List[str]:
    return [f'"{v}"' if v.lower() != 'all' else 'all' for v in values]
