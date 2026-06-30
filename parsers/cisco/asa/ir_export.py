# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""IR export functionality for ASA parser.

Converts parsed ASA configuration to vendor-agnostic Intermediate Representation
(IR) format defined in parsers.model. This allows cross-vendor comparison and
analysis.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Dict, List, Union

if TYPE_CHECKING:
    from .parser import ASAConfig

from parsers import ir_normalize

# IR model for cross-vendor mapping
try:
    from parsers import model as ir
except Exception:
    ir = None  # type: ignore

__all__ = ["to_ir"]


def to_ir(cfg: ASAConfig, device_name: str = None) -> "ir.Device":
    """Map parsed ASA config to common IR.Device representation.

    Converts the ASA-specific parsed configuration into a vendor-agnostic
    intermediate representation that preserves both raw and normalized views
    of ACLs, includes interface context, network objects/groups, service
    groups, and NAT rules.

    Args:
        cfg: Parsed ASAConfig instance containing configuration data
        device_name: Optional device name to include in IR

    Returns:
        ir.Device object representing the configuration in IR format

    Raises:
        RuntimeError: If IR module is not available

    Design notes:
        - Routes are not currently parsed
        - ACL entries are flattened for easier analysis
        - Service groups preserve ASA structure
        - NAT rules include precedence calculation
    """
    if ir is None:
        raise RuntimeError("IR module not available")

    # Version detection from banner lines (best-effort)
    version = 'unknown'
    for ln in cfg.lines:
        m = re.search(r"ASA\s+Version\s+([^\s]+)", ln, flags=re.IGNORECASE)
        if m:
            version = m.group(1)
            break
        m2 = re.search(
            r"Adaptive Security Appliance Software\s+Version\s+([^\s]+)",
            ln,
            flags=re.IGNORECASE
        )
        if m2:
            version = m2.group(1)
            break

    # Convert interfaces
    interfaces: List[ir.Interface] = []
    for name, meta in cfg.interfaces.items():
        ipv4 = meta.get('ipv4')
        interfaces.append(ir.Interface(
            name=name,
            physical=meta.get('phys'),
            ipv4=str(ipv4) if ipv4 else None,
            security_level=meta.get('security_level'),
        ))

    # Convert network objects
    objects: List[ir.Object] = []
    for name, nets in cfg.network_objects.items():
        literals = []
        for n in nets:
            try:
                literals.append(str(n))
            except Exception:
                pass
        objects.append(ir.Object(name=name, literals=sorted(literals)))

    # Convert network groups
    groups: List[ir.Group] = []
    for name, members in cfg.network_object_groups.items():
        mlist: List[ir.GroupMember] = []
        for m in members:
            if isinstance(m, dict):
                if 'group-object' in m:
                    mlist.append(ir.GroupMember(kind='group', ref=m['group-object']))
                elif 'object' in m:
                    mlist.append(ir.GroupMember(kind='object', ref=m['object']))
            else:
                mlist.append(ir.GroupMember(kind='literal', literal=str(m)))
        groups.append(ir.Group(name=name, members=mlist))

    # Convert service groups
    svc_groups: List[ir.ServiceGroup] = []
    if hasattr(cfg, 'service_object_groups'):
        for name, members in getattr(cfg, 'service_object_groups').items():
            out: List[dict] = []
            for m in members:
                if isinstance(m, dict) and 'group-object' in m:
                    out.append({'group': m['group-object']})
                elif isinstance(m, dict) and 'object' in m:
                    out.append({'object': m['object']})
                elif isinstance(m, dict) and 'proto' in m:
                    spec = {'proto': m.get('proto')}
                    if m.get('op'):
                        spec.update({
                            'op': m.get('op'),
                            'v1': m.get('v1'),
                            'v2': m.get('v2')
                        })
                    out.append(spec)
            svc_groups.append(ir.ServiceGroup(name=name, members=out))

    # Convert ACLs and flatten entries
    flattened = cfg.flatten_acl()
    acl_map: Dict[str, List[ir.ACLEntry]] = {}
    for e in flattened:
        src = ir_normalize.addrs_to_strs(e.get('src'))
        dst = ir_normalize.addrs_to_strs(e.get('dst'))
        svc_norm = ir_normalize.svc_to_ir(e.get('svc'))

        acl_name = e.get('acl')
        binding = cfg.acl_bindings.get(acl_name) if acl_name else None
        bound_to = cfg._binding_target_value(binding)

        # Extract direction from binding for IR export
        direction = None
        if binding:
            scope = (binding.get('scope') or '').lower()
            if scope == 'global':
                direction = 'global'
            elif scope == 'control-plane':
                direction = binding.get('direction') or 'any'
            else:
                direction = binding.get('direction') or 'any'

        # For ASA an interface-bound ACL applies to traffic entering ('in') or
        # leaving ('out') the bound interface; record that so rule generation
        # knows the ingress/egress interface (nameif) involved.
        src_interfaces: List[str] = []
        dst_interfaces: List[str] = []
        if bound_to:
            if direction == 'in':
                src_interfaces = [bound_to]
            elif direction == 'out':
                dst_interfaces = [bound_to]

        entry = ir.ACLEntry(
            action=e.get('action'),
            proto=e.get('proto'),
            src=src,
            dst=dst,
            svc=svc_norm,
            raw=e.get('raw'),
            acl=acl_name,
            bound_to=bound_to,
            binding=binding,
            direction=direction,
            src_interfaces=src_interfaces,
            dst_interfaces=dst_interfaces,
        )
        acl_map.setdefault(acl_name or 'UNNAMED', []).append(entry)

    # Build ACL objects with binding metadata
    ir_acls: List[ir.ACL] = []
    for name, entries in acl_map.items():
        binding = cfg.acl_bindings.get(name)
        bound_to = cfg._binding_target_value(binding)
        ir_acls.append(ir.ACL(
            name=name,
            bound_to=bound_to,
            entries=entries,
            binding=binding
        ))

    # Convert NAT rules with precedence
    ir_nats: List[ir.NAT] = []
    for idx, r in enumerate(cfg.nat_rules):
        kind = r.get('type') or 'manual'
        detail: Dict[str, Union[str, int, dict, None]] = {}
        section = r.get('section')
        sequence = r.get('sequence')
        precedence = cfg._nat_precedence_key(
            section if section is not None else (2 if kind == 'auto' else 1),
            sequence,
            idx
        )

        if r.get('type') == 'auto':
            detail = {
                'real_object': r.get('real_object'),
                'kind': r.get('kind'),
                'mapped': r.get('mapped'),
                'service': r.get('service'),
                'sequence': sequence,
                'precedence': precedence,
            }
        else:
            detail = {
                'source': r.get('source'),
                'destination': r.get('destination'),
                'service': r.get('service'),
                'sequence': sequence,
                'precedence': precedence,
            }

        ir_nats.append(ir.NAT(
            kind=kind,
            src_if=r.get('src_if'),
            dst_if=r.get('dst_if'),
            section=section,
            detail=detail,
            raw=r.get('raw')
        ))

    # Convert static routes
    static_routes: List[ir.StaticRoute] = []
    for r in cfg.static_routes:
        static_routes.append(ir.StaticRoute(
            destination=r.get('destination'),
            next_hop=r.get('next_hop'),
            interface=r.get('interface'),
            distance=r.get('distance'),
            metric=None,  # ASA doesn't use metric for static routes
            track=r.get('track'),
            tunneled=r.get('tunneled'),
        ))

    # Convert dynamic routing processes
    dynamic_routing: List[ir.DynamicRoutingProcess] = []
    for key, rconfig in cfg.dynamic_routing.items():
        dynamic_routing.append(ir.DynamicRoutingProcess(
            protocol=rconfig.get('protocol'),
            process_id=rconfig.get('process_id'),
            router_id=rconfig.get('router_id'),
            networks=rconfig.get('networks', []),
            neighbors=rconfig.get('neighbors', []),
            redistribute=rconfig.get('redistribute', []),
            passive_interfaces=rconfig.get('passive_interfaces', []),
            areas=rconfig.get('areas', []),
            areas_config=rconfig.get('areas_config', {}),
            timers=rconfig.get('timers', {}),
            authentication=rconfig.get('authentication', {}),
            distance=rconfig.get('distance', {}),
            config=rconfig.get('config', {}),
        ))

    # Build final Device representation
    dev = ir.Device(
        vendor='asa',
        os='ASA',
        version=version,
        name=device_name or None,
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
