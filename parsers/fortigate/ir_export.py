"""IR export functionality for FortiGate parser.

Converts parsed FortiGate configuration to vendor-agnostic Intermediate
Representation (IR) format defined in parsers.model. This allows cross-vendor
comparison and analysis.
"""

from __future__ import annotations

import ipaddress
import re
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Union

if TYPE_CHECKING:
    from .config import FTGConfig

# IR model for cross-vendor mapping
try:
    from parsers import model as ir
except Exception:
    ir = None  # type: ignore

__all__ = ["to_ir"]


def to_ir(cfg: FTGConfig, device_name: str = None) -> "ir.Device":
    """Map parsed FortiGate config to common IR.Device representation.

    Converts the FortiGate-specific parsed configuration into a vendor-agnostic
    intermediate representation that preserves both raw and normalized views
    of policies, network objects/groups, and service groups.

    Args:
        cfg: Parsed FTGConfig instance containing configuration data
        device_name: Optional device name to include in IR

    Returns:
        ir.Device object representing the configuration in IR format

    Raises:
        RuntimeError: If IR module is not available

    Design notes:
        - FortiGate uses zones/VDOMs, not interfaces (zones mapped to Interface.name)
        - Policies are zone-based, not interface-based
        - Routes and NAT rules not yet implemented in FortiGate parser
        - Service groups preserve FortiGate structure
    """
    if ir is None:
        raise RuntimeError("IR module not available")

    # Version detection from config (best-effort)
    version = 'unknown'
    for ln in cfg._raw_lines:
        # Look for '#config-version=...' lines common in FortiOS configs
        m = re.search(r"#config-version=([^:]+):", ln, flags=re.IGNORECASE)
        if m:
            version = m.group(1).strip()
            break
        # Also check for version in system global
        m2 = re.search(r"set\s+version\s+([^\s]+)", ln, flags=re.IGNORECASE)
        if m2:
            version = m2.group(1).strip()
            break

    interfaces: List[ir.Interface] = []
    for name, meta in cfg.interfaces.items():
        ipv4 = _normalize_interface_ip(meta.get('ip'))
        alias = meta.get('alias') if isinstance(meta.get('alias'), str) else None
        interfaces.append(ir.Interface(
            name=name,
            physical=alias or name,
            ipv4=ipv4,
            security_level=None,
        ))

    # Convert network objects (firewall address)
    objects: List[ir.Object] = []
    for name, nets in cfg.addresses.items():
        literals = []
        for n in nets:
            try:
                literals.append(str(n))
            except Exception:
                pass
        objects.append(ir.Object(name=name, literals=sorted(literals)))

    # Convert network groups (firewall addrgrp)
    groups: List[ir.Group] = []
    for name, members in cfg.addrgrps.items():
        mlist: List[ir.GroupMember] = []
        for m in members:
            if isinstance(m, dict):
                if 'object' in m:
                    mlist.append(ir.GroupMember(kind='object', ref=m['object']))
                elif 'group' in m:
                    mlist.append(ir.GroupMember(kind='group', ref=m['group']))
            else:
                # Direct IP/network
                mlist.append(ir.GroupMember(kind='literal', literal=str(m)))
        groups.append(ir.Group(name=name, members=mlist))

    # Convert service groups (firewall service custom + group)
    svc_groups: List[ir.ServiceGroup] = []

    # First, convert service custom objects to service groups
    for name, spec in cfg.services.items():
        members: List[dict] = []
        for proto in ('tcp', 'udp'):
            if proto in spec:
                for port_range in spec[proto]:
                    if port_range[0] == port_range[1]:
                        # Single port
                        members.append({
                            'proto': proto,
                            'op': 'eq',
                            'v1': port_range[0],
                            'v2': port_range[0]
                        })
                    else:
                        # Range
                        members.append({
                            'proto': proto,
                            'op': 'range',
                            'v1': port_range[0],
                            'v2': port_range[1]
                        })
        if members:
            svc_groups.append(ir.ServiceGroup(name=name, members=members))

    # Then, convert service groups (which reference service objects)
    for name, member_names in cfg.service_groups.items():
        members: List[dict] = []
        for member_name in member_names:
            members.append({'object': member_name})
        svc_groups.append(ir.ServiceGroup(name=name, members=members))

    # Convert policies to ACLs
    # FortiGate policies are a single list; we'll create one ACL named 'policy'
    flattened = cfg.flatten_policies()
    ir_acls: List[ir.ACL] = []

    if flattened:
        entries: List[ir.ACLEntry] = []
        for e in flattened:
            src = sorted([str(s) for s in e.get('src', [])])
            dst = sorted([str(d) for d in e.get('dst', [])])
            svc = e.get('svc') or {}

            # Normalize service dict for IR compatibility
            svc_norm = {
                'proto': svc.get('proto'),
                'service_group_at_proto': None,  # FortiGate doesn't use this concept
                'dst_ports': [
                    {'op': op, 'start': rng[0], 'end': rng[1]}
                    for (op, rng) in svc.get('dst_ports', [])
                ],
                'dst_service_groups': sorted(list(svc.get('dst_service_groups') or [])),
                'dst_service_objects': [],  # FortiGate resolver returns groups, not individual objects
            }

            entry = ir.ACLEntry(
                action=e.get('action', 'permit'),
                proto=e.get('proto', 'ip'),
                src=src,
                dst=dst,
                svc=svc_norm,
                raw=e.get('raw', ''),
                acl='policy',
                bound_to=None,
                binding=e.get('binding'),
                direction='global',
            )
            entries.append(entry)

        ir_acls.append(ir.ACL(
            name='policy',
            bound_to=None,
            entries=entries,
            binding=None
        ))

    ir_nats: List[ir.NAT] = []

    for name, vip in cfg.vips.items():
        extips = _ensure_list(vip.get('extip'))
        mapped = _ensure_list(vip.get('mappedip'))
        policies = sorted(list(cfg.policy_vip_refs.get(name, set())))
        detail = {
            'type': 'vip',
            'name': name,
            'extip': extips,
            'mappedip': mapped,
            'extintf': vip.get('extintf'),
            'portforward': vip.get('portforward'),
            'extport': vip.get('extport'),
            'mappedport': vip.get('mappedport'),
            'policies': policies,
        }
        ir_nats.append(ir.NAT(
            kind='manual',
            src_if=None,
            dst_if=vip.get('extintf'),
            detail=detail,
            raw=f"vip {name}",
        ))

    for policy in cfg.policies:
        if policy.get('nat'):
            detail = {
                'type': 'policy-snat',
                'policy_id': policy.get('id'),
                'policy_name': policy.get('name'),
                'ippool': policy.get('ippool'),
                'poolname': policy.get('poolname'),
            }
            ir_nats.append(ir.NAT(
                kind='manual',
                src_if=_first_or_none(policy.get('srcintf')),
                dst_if=_first_or_none(policy.get('dstintf')),
                detail=detail,
                raw=f"policy {policy.get('id')}",
            ))

    for entry in cfg.central_snat_map:
        detail = {
            'type': 'central-snat',
            'seq': entry.get('seq'),
            'srcintf': entry.get('srcintf'),
            'dstintf': entry.get('dstintf'),
            'orig-addr': entry.get('orig-addr'),
            'dst-addr': entry.get('dst-addr'),
            'nat-ippool': entry.get('nat-ippool'),
        }
        ir_nats.append(ir.NAT(
            kind='manual',
            src_if=_first_or_none(entry.get('srcintf')),
            dst_if=_first_or_none(entry.get('dstintf')),
            detail=detail,
            raw=f"central-snat {entry.get('seq')}",
        ))

    # Convert static routes
    static_routes: List[ir.StaticRoute] = []
    for r in cfg.static_routes:
        static_routes.append(ir.StaticRoute(
            destination=r.get('destination'),
            next_hop=r.get('gateway'),
            interface=r.get('device'),
            distance=r.get('distance'),
            metric=None,
            track=None,
            tunneled=None,
        ))

    # Convert dynamic routing
    dynamic_routing: List[ir.DynamicRoutingProcess] = []
    for key, rconfig in cfg.dynamic_routing.items():
        dynamic_routing.append(ir.DynamicRoutingProcess(
            protocol=rconfig.get('protocol'),
            process_id=rconfig.get('process_id'),
            router_id=rconfig.get('router_id'),
            networks=rconfig.get('networks', []),
            neighbors=rconfig.get('neighbors', []),
            redistribute=rconfig.get('redistribute', []),
            areas=rconfig.get('areas', []),
            config=rconfig.get('config', {}),
        ))

    # Build final Device representation
    dev = ir.Device(
        vendor='fortigate',
        os='FortiOS',
        version=version,
        name=device_name or cfg.vdom,
        interfaces=interfaces,
        objects=objects,
        groups=groups,
        service_groups=svc_groups,
        acls=ir_acls,
        nats=ir_nats,
        static_routes=static_routes,
        dynamic_routing=dynamic_routing,
        routes=[],  # Backward compat, deprecated
    )
    return dev


def _normalize_interface_ip(value: Optional[Union[str, List[str]]]) -> Optional[str]:
    if not value:
        return None
    if isinstance(value, list):
        value = ' '.join(str(v) for v in value)
    text = str(value).strip()
    if not text:
        return None
    if '/' in text:
        return text
    parts = text.split()
    if len(parts) == 2:
        ip, mask = parts
        try:
            net = ipaddress.ip_network(f"{ip}/{mask}", strict=False)
            return f"{ip}/{net.prefixlen}"
        except Exception:
            return f"{ip}/{mask}"
    return text


def _ensure_list(value: Optional[Union[str, List[str]]]) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _first_or_none(value: Optional[Union[str, List[str]]]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, list):
        return value[0] if value else None
    return value
