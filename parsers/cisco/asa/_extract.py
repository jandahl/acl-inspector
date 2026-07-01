# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Per-construct extraction helpers for the ASA parser.

These pure functions hold the line-level field extraction that the (single,
ciscoconfparse2-backed) ``ASAConfig.parse()`` drives. Keeping the verbose
routing-block logic here keeps ``parse()`` a thin tree-walk and preserves the
exact behaviour the hand-rolled parser had.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

__all__ = ["parse_dynamic_routing_block"]


def parse_dynamic_routing_block(header_line: str, child_lines: List[str]) -> Optional[Tuple[str, dict]]:
    """Parse a ``router <protocol> [pid]`` block into a routing-config dict.

    Args:
        header_line: The ``router ospf 1`` (etc.) header line.
        child_lines: The block's child lines (any leading indentation is fine;
            patterns anchor with ``^\\s*``).

    Returns:
        ``(key, routing_config)`` where ``key`` is ``"{protocol}_{pid}"`` (or just
        the protocol when no process id), or ``None`` if the header is not a
        recognised dynamic-routing protocol.
    """
    m_router = re.match(r"^\s*router\s+(?P<protocol>ospf|eigrp|bgp|rip)\s*(?P<pid>\d*)$", header_line, re.IGNORECASE)
    if not m_router:
        return None

    protocol = m_router.group('protocol').lower()
    process_id = m_router.group('pid') or None
    key = f"{protocol}_{process_id}" if process_id else protocol

    routing_config: Dict[str, object] = {
        'protocol': protocol,
        'process_id': process_id,
        'router_id': None,
        'networks': [],
        'neighbors': [],
        'redistribute': [],
        'areas': [],
        'passive_interfaces': [],
        'timers': {},
        'authentication': {},
        'distance': {},
        'config': {},
        'raw_lines': [header_line.strip()],
    }

    for rline in child_lines:
        if not rline.strip():
            continue
        routing_config['raw_lines'].append(rline.strip())

        m_rid = re.match(r"^\s*router-id\s+(?P<rid>\S+)", rline, re.IGNORECASE)
        if m_rid:
            routing_config['router_id'] = m_rid.group('rid')
            continue

        m_net = re.match(r"^\s*network\s+(?P<net>\S+)(?:\s+(?P<mask>\S+))?(?:\s+area\s+(?P<area>\S+))?", rline, re.IGNORECASE)
        if m_net:
            net_entry = {'network': m_net.group('net')}
            if m_net.group('mask'):
                net_entry['mask'] = m_net.group('mask')
            if m_net.group('area'):
                net_entry['area'] = m_net.group('area')
            routing_config['networks'].append(net_entry)
            continue

        m_neigh = re.match(r"^\s*neighbor\s+(?P<ip>\S+)\s+remote-as\s+(?P<as>\d+)", rline, re.IGNORECASE)
        if m_neigh:
            routing_config['neighbors'].append({
                'ip': m_neigh.group('ip'),
                'remote_as': m_neigh.group('as'),
            })
            continue

        m_redis = re.match(r"^\s*redistribute\s+(?P<source>\S+)(?:\s+(?P<options>.*))?", rline, re.IGNORECASE)
        if m_redis:
            redis_entry = {'source': m_redis.group('source')}
            options = m_redis.group('options')
            if options:
                if 'subnets' in options.lower():
                    redis_entry['subnets'] = True
                if 'metric' in options.lower():
                    m_metric = re.search(r"metric\s+(\d+)", options, re.IGNORECASE)
                    if m_metric:
                        redis_entry['metric'] = int(m_metric.group(1))
            routing_config['redistribute'].append(redis_entry)
            continue

        m_passive = re.match(r"^\s*passive-interface\s+(?P<iface>\S+)", rline, re.IGNORECASE)
        if m_passive:
            routing_config['passive_interfaces'].append(m_passive.group('iface'))
            continue

        m_dist = re.match(r"^\s*distance\s+(?P<value>\d+)", rline, re.IGNORECASE)
        if m_dist:
            routing_config['distance']['default'] = int(m_dist.group('value'))
            continue

        m_area_auth = re.match(r"^\s*area\s+(?P<area>\S+)\s+authentication(?:\s+(?P<type>message-digest))?", rline, re.IGNORECASE)
        if m_area_auth:
            area_id = m_area_auth.group('area')
            auth_type = m_area_auth.group('type') or 'simple'
            routing_config.setdefault('areas_config', {})
            routing_config['areas_config'].setdefault(area_id, {})
            routing_config['areas_config'][area_id]['authentication'] = auth_type
            continue

        m_area_stub = re.match(r"^\s*area\s+(?P<area>\S+)\s+(?P<type>stub|nssa)(?:\s+(?P<opts>.*))?", rline, re.IGNORECASE)
        if m_area_stub:
            area_id = m_area_stub.group('area')
            opts = m_area_stub.group('opts') or ''
            routing_config.setdefault('areas_config', {})
            routing_config['areas_config'].setdefault(area_id, {})
            routing_config['areas_config'][area_id]['type'] = m_area_stub.group('type')
            if 'no-summary' in opts.lower():
                routing_config['areas_config'][area_id]['no_summary'] = True
            continue

        m_timers = re.match(r"^\s*timers\s+(?P<type>\S+)\s+(?P<val1>\d+)(?:\s+(?P<val2>\d+))?", rline, re.IGNORECASE)
        if m_timers:
            routing_config['timers'][m_timers.group('type')] = {
                'value1': int(m_timers.group('val1')),
                'value2': int(m_timers.group('val2')) if m_timers.group('val2') else None,
            }
            continue

        m_nbr_pass = re.match(r"^\s*neighbor\s+(?P<ip>\S+)\s+password\s+(?P<pwd>.+)", rline, re.IGNORECASE)
        if m_nbr_pass:
            for nbr in routing_config['neighbors']:
                if nbr.get('ip') == m_nbr_pass.group('ip'):
                    nbr['password'] = True  # Don't store actual password
                    break
            continue

        m_nbr_desc = re.match(r"^\s*neighbor\s+(?P<ip>\S+)\s+description\s+(?P<desc>.+)", rline, re.IGNORECASE)
        if m_nbr_desc:
            for nbr in routing_config['neighbors']:
                if nbr.get('ip') == m_nbr_desc.group('ip'):
                    nbr['description'] = m_nbr_desc.group('desc').strip()
                    break
            continue

        m_nbr_timers = re.match(r"^\s*neighbor\s+(?P<ip>\S+)\s+timers\s+(?P<keepalive>\d+)\s+(?P<holdtime>\d+)", rline, re.IGNORECASE)
        if m_nbr_timers:
            for nbr in routing_config['neighbors']:
                if nbr.get('ip') == m_nbr_timers.group('ip'):
                    nbr['timers'] = {
                        'keepalive': int(m_nbr_timers.group('keepalive')),
                        'holdtime': int(m_nbr_timers.group('holdtime')),
                    }
                    break
            continue

        if re.match(r"^\s*default-information\s+originate", rline, re.IGNORECASE):
            routing_config['config']['default_information_originate'] = True
            continue

        if re.match(r"^\s*log-adjacency-changes", rline, re.IGNORECASE):
            routing_config['config']['log_adjacency_changes'] = True
            continue

        m_autocost = re.match(r"^\s*auto-cost\s+reference-bandwidth\s+(?P<bw>\d+)", rline, re.IGNORECASE)
        if m_autocost:
            routing_config['config']['auto_cost_reference_bandwidth'] = int(m_autocost.group('bw'))
            continue

    return key, routing_config
