# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""FortiGate parser powered by ciscoconfparse2 (AdvancedFTGConfig).

Drop-in replacement for FTGConfig. Parses the same config blocks using
ciscoconfparse2 as the structural parser instead of the hand-rolled
line-iterator in FTGConfig._parse(). All resolution logic (resolve_addr_token,
flatten_policies, etc.) is inherited unchanged.

Note: ciscoconfparse2 is invoked with syntax='ios' because it uses indentation
depth to build the object hierarchy. FortiOS configs use consistent 4-space
indentation per nesting level, so the IOS parser correctly reconstructs the
config/edit/set/next/end block structure. Configs with inconsistent or tab
indentation would not parse correctly.
"""

from __future__ import annotations

from typing import Optional

from parsers.fortigate.config import FTGConfig, to_ip_network


class AdvancedFTGConfig(FTGConfig):
    """FortiGate parser using ciscoconfparse2 for structural parsing.

    Requires: pip install .[external]
    """

    def __init__(self, text: str, vdom: Optional[str] = None) -> None:
        try:
            import ciscoconfparse2  # noqa: F401 — guard import; raises early if missing
        except ImportError:
            raise ImportError(
                "ciscoconfparse2 is required for the external engine. "
                "Install with: pip install .[external]"
            )
        # super().__init__ initialises all attributes then calls self._parse(),
        # which dispatches to our override below.
        super().__init__(text, vdom)

    # ------------------------------------------------------------------
    # Override: structural parser using ciscoconfparse2
    # ------------------------------------------------------------------
    def _parse(self) -> None:
        from ciscoconfparse2 import CiscoConfParse

        ccp = CiscoConfParse(
            self.lines,
            syntax='ios',
            comment_delimiters=['#'],
            ignore_blank_lines=True,
        )

        for obj in ccp.objs:
            txt = obj.text.strip()
            # addrgrp before address — avoids the 'address' prefix matching 'addrgrp'
            if txt.startswith('config firewall addrgrp'):
                self._ccp_parse_addrgrp(obj)
            elif txt.startswith('config firewall address'):
                self._ccp_parse_addresses(obj)
            elif txt.startswith('config firewall vipgrp'):
                self._ccp_parse_vipgrp(obj)
            elif txt.startswith('config firewall vip'):
                self._ccp_parse_vip(obj)
            elif txt.startswith('config firewall service custom'):
                self._ccp_parse_service_custom(obj)
            elif txt.startswith('config firewall service group'):
                self._ccp_parse_service_group(obj)
            elif txt.startswith('config firewall policy'):
                self._ccp_parse_policy(obj)
            elif txt.startswith('config firewall ippool'):
                self._ccp_parse_ippool(obj)
            elif txt.startswith('config firewall central-snat-map'):
                self._ccp_parse_central_snat(obj)
            elif txt.startswith('config system interface'):
                self._ccp_parse_system_interface(obj)
            elif txt.startswith('config system zone'):
                self._ccp_parse_system_zone(obj)
            elif txt.startswith('config router static'):
                self._ccp_parse_static_routes(obj)

        # OSPF/BGP blocks: delegate to the inherited line-based parsers since
        # the data structures are complex and benefit from existing coverage.
        i = 0
        L = len(self.lines)
        while i < L:
            s = self.lines[i].strip()
            if s.startswith('config router ospf'):
                i = self._parse_router_ospf(i + 1)
                continue
            elif s.startswith('config router bgp'):
                i = self._parse_router_bgp(i + 1)
                continue
            i += 1

    # ------------------------------------------------------------------
    # Block parsers (one method per config section)
    # ------------------------------------------------------------------

    def _ccp_parse_addresses(self, obj) -> None:
        for child in obj.children:
            txt = child.text.strip()
            if not txt.startswith('edit '):
                continue
            name = txt.split('edit', 1)[1].strip().strip('"')
            subnet_ip = subnet_mask = None
            for gc in child.children:
                tokens = self._tokenize(gc.text.strip())
                if tokens and tokens[0].lower() == 'set' and len(tokens) >= 4 and tokens[1].lower() == 'subnet':
                    subnet_ip, subnet_mask = tokens[2], tokens[3]
            nets = set()
            if subnet_ip and subnet_mask:
                nets.add(to_ip_network(subnet_ip, subnet_mask))
            self.addresses[name] = nets

    def _ccp_parse_addrgrp(self, obj) -> None:
        for child in obj.children:
            txt = child.text.strip()
            if not txt.startswith('edit '):
                continue
            name = txt.split('edit', 1)[1].strip().strip('"')
            members = []
            for gc in child.children:
                tokens = self._tokenize(gc.text.strip())
                if tokens and tokens[0].lower() == 'set' and len(tokens) >= 3 and tokens[1].lower() == 'member':
                    for m in tokens[2:]:
                        members.append({'object': self._strip_quotes(m)})
            self.addrgrps[name] = members

    def _ccp_parse_vip(self, obj) -> None:
        for child in obj.children:
            txt = child.text.strip()
            if not txt.startswith('edit '):
                continue
            name = txt.split('edit', 1)[1].strip().strip('"')
            cur_data = {}
            for gc in child.children:
                tokens = self._tokenize(gc.text.strip())
                if not tokens or tokens[0].lower() != 'set' or len(tokens) < 3:
                    continue
                key = tokens[1].lower()
                values = [self._strip_quotes(t) for t in tokens[2:]]
                if key in {'extip', 'mappedip'}:
                    cur_data[key] = values
                elif key in {'extintf', 'type'}:
                    cur_data[key] = values[0]
                elif key in {'extport', 'mappedport'} and values:
                    cur_data[key] = values[0]
                elif key == 'portforward' and values:
                    cur_data[key] = values[0].lower() == 'enable'
                else:
                    cur_data[key] = values if len(values) > 1 else values[0]
            self.vips[name] = cur_data

    def _ccp_parse_vipgrp(self, obj) -> None:
        for child in obj.children:
            txt = child.text.strip()
            if not txt.startswith('edit '):
                continue
            name = txt.split('edit', 1)[1].strip().strip('"')
            members = []
            for gc in child.children:
                tokens = self._tokenize(gc.text.strip())
                if tokens and tokens[0].lower() == 'set' and len(tokens) >= 3 and tokens[1].lower() == 'member':
                    members.extend(self._strip_quotes(t) for t in tokens[2:])
            self.vipgrps[name] = members

    def _ccp_parse_service_custom(self, obj) -> None:
        for child in obj.children:
            txt = child.text.strip()
            if not txt.startswith('edit '):
                continue
            name = txt.split('edit', 1)[1].strip().strip('"')
            spec = {}
            for gc in child.children:
                tokens = self._tokenize(gc.text.strip())
                if not tokens or tokens[0].lower() != 'set' or len(tokens) < 3:
                    continue
                key = tokens[1].lower()
                if key == 'tcp-portrange':
                    spec.setdefault('tcp', []).extend(self._split_ranges(' '.join(tokens[2:])))
                elif key == 'udp-portrange':
                    spec.setdefault('udp', []).extend(self._split_ranges(' '.join(tokens[2:])))
            self.services[name] = spec

    def _ccp_parse_service_group(self, obj) -> None:
        for child in obj.children:
            txt = child.text.strip()
            if not txt.startswith('edit '):
                continue
            name = txt.split('edit', 1)[1].strip().strip('"')
            members = set()
            for gc in child.children:
                tokens = self._tokenize(gc.text.strip())
                if tokens and tokens[0].lower() == 'set' and len(tokens) >= 3 and tokens[1].lower() == 'member':
                    members.update(self._strip_quotes(m) for m in tokens[2:])
            self.service_groups[name] = members

    def _ccp_parse_policy(self, obj) -> None:
        for child in obj.children:
            txt = child.text.strip()
            if not txt.startswith('edit '):
                continue
            policy_id = txt.split('edit', 1)[1].strip().strip('"')
            cur_data = {
                'id': policy_id,
                'srcaddr': [],
                'dstaddr': [],
                'service': [],
                'srcintf': [],
                'dstintf': [],
            }
            for gc in child.children:
                tokens = self._tokenize(gc.text.strip())
                if not tokens or tokens[0].lower() != 'set' or len(tokens) < 3:
                    continue
                key = tokens[1].lower()
                values = [self._strip_quotes(t) for t in tokens[2:]]
                if key == 'action' and values:
                    act = values[0].lower()
                    cur_data['action'] = 'permit' if act == 'accept' else 'deny'
                elif key == 'srcaddr':
                    cur_data['srcaddr'] = values
                elif key == 'dstaddr':
                    cur_data['dstaddr'] = values
                elif key == 'service':
                    cur_data['service'] = values
                elif key == 'srcintf':
                    cur_data['srcintf'] = values
                elif key == 'dstintf':
                    cur_data['dstintf'] = values
                elif key == 'schedule' and values:
                    cur_data['schedule'] = values[0]
                elif key == 'name' and values:
                    cur_data['name'] = values[0]
                elif key == 'uuid' and values:
                    cur_data['uuid'] = values[0]
                elif key == 'logtraffic' and values:
                    cur_data['logtraffic'] = values[0]
                elif key == 'nat' and values:
                    cur_data['nat'] = values[0].lower() == 'enable'
                elif key == 'ippool' and values:
                    cur_data['ippool'] = values[0].lower() == 'enable'
                elif key == 'poolname':
                    cur_data['poolname'] = values
                elif key == 'status' and values:
                    cur_data['status'] = values[0]
                elif key == 'comments' and values:
                    cur_data['comments'] = ' '.join(values)
            self.policies.append(cur_data)

    def _ccp_parse_system_interface(self, obj) -> None:
        for child in obj.children:
            txt = child.text.strip()
            if not txt.startswith('edit '):
                continue
            name = txt.split('edit', 1)[1].strip().strip('"')
            cur_data = {}
            for gc in child.children:
                tokens = self._tokenize(gc.text.strip())
                if not tokens or tokens[0].lower() != 'set' or len(tokens) < 3:
                    continue
                key = tokens[1].lower()
                values = [self._strip_quotes(t) for t in tokens[2:]]
                if key == 'ip':
                    cur_data['ip'] = ' '.join(values)
                elif key == 'allowaccess':
                    cur_data['allowaccess'] = values
                elif key == 'alias':
                    cur_data['alias'] = ' '.join(values)
                elif key == 'description':
                    cur_data['description'] = ' '.join(values)
                else:
                    cur_data[key] = values if len(values) > 1 else values[0]
            self.interfaces[name] = cur_data

    def _ccp_parse_system_zone(self, obj) -> None:
        for child in obj.children:
            txt = child.text.strip()
            if not txt.startswith('edit '):
                continue
            name = txt.split('edit', 1)[1].strip().strip('"')
            cur_data = {}
            for gc in child.children:
                tokens = self._tokenize(gc.text.strip())
                if not tokens or tokens[0].lower() != 'set' or len(tokens) < 3:
                    continue
                key = tokens[1].lower()
                values = [self._strip_quotes(t) for t in tokens[2:]]
                cur_data[key] = values  # always a list, matching FTGConfig._parse_system_zone
            self.zones[name] = cur_data

    def _ccp_parse_ippool(self, obj) -> None:
        for child in obj.children:
            txt = child.text.strip()
            if not txt.startswith('edit '):
                continue
            name = txt.split('edit', 1)[1].strip().strip('"')
            cur_data = {}
            for gc in child.children:
                tokens = self._tokenize(gc.text.strip())
                if not tokens or tokens[0].lower() != 'set' or len(tokens) < 3:
                    continue
                key = tokens[1].lower()
                values = [self._strip_quotes(t) for t in tokens[2:]]
                if key in {'startip', 'endip', 'type'}:
                    cur_data[key] = values[0]
                else:
                    cur_data[key] = values if len(values) > 1 else values[0]
            self.ippools[name] = cur_data

    def _ccp_parse_central_snat(self, obj) -> None:
        for child in obj.children:
            txt = child.text.strip()
            if not txt.startswith('edit '):
                continue
            tokens_head = self._tokenize(txt)
            seq = self._strip_quotes(tokens_head[1]) if len(tokens_head) >= 2 else None
            cur_data = {'seq': seq} if seq else {}
            for gc in child.children:
                tokens = self._tokenize(gc.text.strip())
                if not tokens or tokens[0].lower() != 'set' or len(tokens) < 3:
                    continue
                key = tokens[1].lower()
                values = [self._strip_quotes(t) for t in tokens[2:]]
                cur_data[key] = values if len(values) > 1 else values[0]
            if cur_data:
                self.central_snat_map.append(cur_data)

    def _ccp_parse_static_routes(self, obj) -> None:
        for child in obj.children:
            txt = child.text.strip()
            if not txt.startswith('edit '):
                continue
            seq = txt.split('edit', 1)[1].strip().strip('"')
            cur_data = {'seq': seq, 'destination': None, 'gateway': None, 'device': None, 'distance': None}
            for gc in child.children:
                tokens = self._tokenize(gc.text.strip())
                if not tokens or tokens[0].lower() != 'set' or len(tokens) < 3:
                    continue
                key = tokens[1].lower()
                values = [self._strip_quotes(t) for t in tokens[2:]]
                if key == 'dst':
                    cur_data['destination'] = ' '.join(values)
                elif key == 'gateway':
                    cur_data['gateway'] = ' '.join(values)
                elif key == 'device':
                    cur_data['device'] = values[0]
                elif key == 'distance':
                    try:
                        cur_data['distance'] = int(values[0])
                    except (ValueError, IndexError):
                        pass
            if cur_data.get('destination'):
                self.static_routes.append(cur_data)
