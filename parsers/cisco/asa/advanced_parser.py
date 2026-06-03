# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""ASA parser powered by ciscoconfparse2 (parent-child aware).

AdvancedASAConfig subclasses ASAConfig and overrides parse() to use
ciscoconfparse2's parent-child traversal instead of manual index tracking.
All resolution, evaluation, and ACL-flattening logic is inherited unchanged.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from parsers.cisco.asa.parser import (
    ASAConfig,
    re_object,
    re_object_network_host,
    re_object_network_subnet,
    re_object_group,
    re_group_network_object,
    re_group_network_host,
    re_group_network_subnet,
    re_group_network_groupobj,
    re_acl,
    to_ip_network,
)


class AdvancedASAConfig(ASAConfig):
    """ASA parser using ciscoconfparse2 for parent-child aware parsing.

    Drop-in replacement for ASAConfig. Uses ciscoconfparse2 to traverse the
    config hierarchy (objects, groups, interfaces) instead of manual index
    tracking. All resolution, evaluation, and flattening logic is inherited.

    Requires ``pip install ciscoconfparse2``.
    """

    def __init__(self, text: str) -> None:
        try:
            import ciscoconfparse2  # noqa: F401
        except ImportError:
            raise ImportError(
                "ciscoconfparse2 is required for the advanced engine. "
                "Install with: pip install ciscoconfparse2"
            )
        super().__init__(text)

    def parse(self) -> None:
        from ciscoconfparse2 import CiscoConfParse

        ccp = CiscoConfParse(self.lines, syntax='asa')

        # ── Network objects ──────────────────────────────────────────────────
        for obj in ccp.find_objects(r'^object\s+network\s+'):
            m = re_object.match(obj.text)
            if not m:
                continue
            name = m.group('name')
            nets = set()
            for child in obj.children:
                ct = child.text.strip()
                # Auto NAT inside object network block
                nat_m = re.match(
                    r'nat\s*\((?P<src_if>[^,]+),(?P<dst_if>[^\)]+)\)\s+(?P<rest>.+)',
                    ct, re.IGNORECASE,
                )
                if nat_m:
                    mm = re.match(
                        r'(?P<kind>static|dynamic)\s+(?P<target>\S+)',
                        nat_m.group('rest'), re.IGNORECASE,
                    )
                    self.nat_rules.append({
                        'type': 'auto', 'section': 2,
                        'src_if': nat_m.group('src_if').strip(),
                        'dst_if': nat_m.group('dst_if').strip(),
                        'real_object': name,
                        'kind': mm.group('kind').lower() if mm else None,
                        'mapped': mm.group('target') if mm else None,
                        'service': None, 'sequence': None,
                        'order_keyword': None, 'raw': ct,
                    })
                    continue
                lm = re_object_network_host.match(child.text)
                if lm:
                    try:
                        nets.add(to_ip_network(lm.group('ip')))
                    except Exception:
                        self.network_object_literals[name].add(ct)
                    continue
                lm2 = re_object_network_subnet.match(child.text)
                if lm2:
                    try:
                        nets.add(to_ip_network(lm2.group('ip'), lm2.group('mask')))
                    except Exception:
                        self.network_object_literals[name].add(ct)
                    continue
                # range / fqdn — store as literal (same as legacy)
                if ct and not ct.lower().startswith(('description', 'nat')):
                    self.network_object_literals[name].add(ct)
            self.network_objects[name] = nets

        # ── Object groups ────────────────────────────────────────────────────
        for grp in ccp.find_objects(r'^object-group\s+'):
            mg = re_object_group.match(grp.text)
            if not mg:
                continue
            typ = mg.group('type').lower()
            name = mg.group('name')
            service_group_proto = (mg.group('proto') or '').lower() if typ == 'service' else None
            members = []

            for child in grp.children:
                ln = child.text
                if typ == 'network':
                    m_host = re_group_network_host.match(ln)
                    m_obj = re_group_network_object.match(ln)
                    m_subnet = re_group_network_subnet.match(ln)
                    m_grpobj = re_group_network_groupobj.match(ln)
                    if m_host:
                        try:
                            members.append(to_ip_network(m_host.group('ip')))
                        except Exception:
                            self.network_object_group_literals[name].add(ln.strip())
                    elif m_subnet:
                        try:
                            members.append(to_ip_network(m_subnet.group('ip'), m_subnet.group('mask')))
                        except Exception:
                            self.network_object_group_literals[name].add(ln.strip())
                    elif m_obj:
                        members.append({'object': m_obj.group('name')})
                    elif m_grpobj:
                        members.append({'group-object': m_grpobj.group('name')})

                elif typ == 'service':
                    m_grpobj = re_group_network_groupobj.match(ln)
                    if m_grpobj:
                        members.append({'group-object': m_grpobj.group('name')})
                        continue
                    mport = re.match(
                        r'^\s*port-object\s+(eq|lt|gt|neq|range)\s+(\S+)(?:\s+(\S+))?',
                        ln, re.IGNORECASE,
                    )
                    if mport:
                        members.append({
                            'proto': service_group_proto or 'tcp',
                            'op': mport.group(1).lower(),
                            'v1': mport.group(2),
                            'v2': mport.group(3),
                        })
                        continue
                    msvc = re.match(
                        r'^\s*service-object\s+(tcp|udp|icmp|ip)(?:\s+(eq|lt|gt|neq|range)\s+(\S+)(?:\s+(\S+))?)?',
                        ln, re.IGNORECASE,
                    )
                    if msvc:
                        spec: dict = {'proto': msvc.group(1).lower()}
                        op = (msvc.group(2) or '').lower()
                        if op in {'eq', 'lt', 'gt', 'neq', 'range'}:
                            spec.update({'op': op, 'v1': msvc.group(3), 'v2': msvc.group(4)})
                        members.append(spec)
                        continue
                    mobj = re.match(r'^\s*service-object\s+object\s+(\S+)', ln, re.IGNORECASE)
                    if mobj:
                        members.append({'object': mobj.group(1)})

            if typ == 'network':
                self.network_object_groups[name] = members
            elif typ == 'service':
                if not hasattr(self, 'service_object_groups'):
                    self.service_object_groups = {}
                self.service_object_groups[name] = members

        # ── Interfaces ───────────────────────────────────────────────────────
        for iface in ccp.find_objects(r'^interface\s+'):
            phys = iface.text.split(None, 1)[1].strip()
            nameif = None
            ipv4 = None
            sec = None
            for child in iface.children:
                ct = child.text.strip()
                low = ct.lower()
                if low.startswith('nameif '):
                    nameif = ct.split(None, 1)[1].strip()
                elif low.startswith('ip address '):
                    parts = ct.split()
                    if len(parts) >= 3:
                        try:
                            mask = parts[3] if len(parts) >= 4 else None
                            ipv4 = to_ip_network(parts[2], mask)
                        except Exception:
                            pass
                elif low.startswith('security-level '):
                    try:
                        sec = int(ct.split()[-1])
                    except Exception:
                        pass
            key = nameif or phys
            self.interfaces[key] = {
                'phys': phys, 'nameif': nameif, 'ipv4': ipv4, 'security_level': sec,
            }

        # ── ACL lines (flat — no parent-child benefit) ────────────────────────
        for line_obj in ccp.find_objects(re_acl):
            m = re_acl.match(line_obj.text)
            if m:
                # linenum is 0-based; legacy stores 1-based
                self.acls[m.group('name')].append((line_obj.text, line_obj.linenum + 1))

        # ── Access groups ─────────────────────────────────────────────────────
        for ag in ccp.find_objects(r'^access-group\s+'):
            m = re.match(r'^access-group\s+(\S+)\s+(.+)$', ag.text, re.IGNORECASE)
            if m:
                self.acl_bindings[m.group(1)] = self._parse_access_group_binding(
                    m.group(2), ag.text
                )

        # ── Manual NAT (top-level nat lines) ──────────────────────────────────
        for nat_obj in ccp.find_objects(r'^nat\s*\('):
            line = nat_obj.text
            mnat = re.match(
                r'^nat\s*\((?P<src_if>[^,]+),(?P<dst_if>[^\)]+)\)\s*(?P<rest>.+)$',
                line, re.IGNORECASE,
            )
            if not mnat:
                continue
            src_if = mnat.group('src_if').strip()
            dst_if = mnat.group('dst_if').strip()
            rest = mnat.group('rest').strip()
            section = 1
            sequence = None
            order_kw = None
            m_seq = re.match(r'^(?P<num>\d+)\s+(?P<tail>.+)$', rest)
            if m_seq:
                sequence = int(m_seq.group('num'))
                rest = m_seq.group('tail').strip()
            lower_rest = rest.lower()
            if lower_rest.startswith('after-auto'):
                order_kw = 'after-auto'
                rest = rest.split(None, 1)[1].strip() if ' ' in rest else ''
                section = 3
            elif lower_rest.startswith('before-auto'):
                order_kw = 'before-auto'
                rest = rest.split(None, 1)[1].strip() if ' ' in rest else ''
            msrc = re.match(
                r'^source\s+(static|dynamic)\s+(\S+)\s+(\S+)(?P<tail>.*)$',
                rest, re.IGNORECASE,
            )
            if not msrc:
                continue
            s_kind = msrc.group(1).lower()
            s_real = msrc.group(2)
            s_map = msrc.group(3)
            tail = (msrc.group('tail') or '').strip()
            dest_data = None
            service_data = None
            if tail.lower().startswith('destination '):
                mdest = re.match(
                    r'^destination\s+(static|dynamic)\s+(\S+)\s+(\S+)(?P<tail>.*)$',
                    tail, re.IGNORECASE,
                )
                if mdest:
                    dest_data = {
                        'kind': mdest.group(1).lower(),
                        'real': mdest.group(2),
                        'mapped': mdest.group(3),
                    }
                    tail = (mdest.group('tail') or '').strip()
            if tail:
                service_data, _ = self._parse_nat_service_clause(tail)
            self.nat_rules.append({
                'type': 'manual', 'section': section, 'sequence': sequence,
                'order_keyword': order_kw,
                'src_if': src_if, 'dst_if': dst_if,
                'source': {'kind': s_kind, 'real': s_real, 'mapped': s_map},
                'destination': dest_data,
                'service': service_data,
                'raw': line.strip(),
            })

        # ── Static routes ─────────────────────────────────────────────────────
        for rt in ccp.find_objects(r'^route\s+'):
            parts = rt.text.split()
            if len(parts) < 5:
                continue
            try:
                net = to_ip_network(parts[2], parts[3])
                rest_tokens = parts[5:]
                distance = None
                track = None
                tunneled = False
                if rest_tokens and rest_tokens[0].isdigit():
                    distance = int(rest_tokens[0])
                    rest_tokens = rest_tokens[1:]
                if 'tunneled' in [t.lower() for t in rest_tokens]:
                    tunneled = True
                for idx, token in enumerate(rest_tokens):
                    if token.lower() == 'track' and idx + 1 < len(rest_tokens):
                        try:
                            track = int(rest_tokens[idx + 1])
                        except ValueError:
                            pass
                self.static_routes.append({
                    'destination': str(net),
                    'next_hop': parts[4] if parts[4].lower() != 'dhcp' else None,
                    'interface': parts[1],
                    'distance': distance,
                    'track': track,
                    'tunneled': tunneled,
                    'raw': rt.text.strip(),
                })
            except Exception:
                pass
