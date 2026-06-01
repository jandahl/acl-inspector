# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Parallel ASA parser powered by ciscoconfparse.

This module provides a scaffolding for advanced Cisco ASA parsing using
the ciscoconfparse library for robust parent/child relationship handling.
"""

from __future__ import annotations
import ipaddress
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple, Union, Any, Iterable

from .utils import to_ip_network
from . import ir_export

class AdvancedASAConfig:
    """Advanced ASA parser using ciscoconfparse."""
    
    def __init__(self, text: str) -> None:
        try:
            from ciscoconfparse import CiscoConfParse
        except ImportError:
            raise ImportError("ciscoconfparse is required for the external engine. Install with: pip install .[external]")

        self.raw_text = text
        self.lines = [line.rstrip() for line in text.splitlines()]
        self.raw_tree = CiscoConfParse(self.lines, factory=True)
        
        # Core data structures matching legacy ASAConfig
        self.network_objects: Dict[str, Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network]]] = {}
        self.network_object_literals: Dict[str, Set[str]] = defaultdict(set)
        self.network_object_groups: Dict[str, List[Union[dict, ipaddress.IPv4Address, ipaddress.IPv4Network]]] = {}
        self.network_object_group_literals: Dict[str, Set[str]] = defaultdict(set)
        self.acls: Dict[str, List[Tuple[str, int]]] = defaultdict(list)
        self.interfaces: Dict[str, dict] = {}
        self.acl_bindings: Dict[str, Dict[str, Optional[str]]] = {}
        self.nat_rules: List[dict] = []
        self.static_routes: List[dict] = []
        self.dynamic_routing: Dict[str, dict] = {}
        self.service_object_groups: Dict[str, List[dict]] = {}
        self.ip_to_objects: Dict[Union[ipaddress.IPv4Address, ipaddress.IPv4Network], Set[str]] = {}
        
        # Caches
        self._network_cache: Dict[str, Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network]]] = {}
        self._service_group_cache: Dict[str, Tuple[dict, ...]] = {}

        # Implementation placeholder
        self._parse_with_external()
        self._build_reverse_indexes()

    def _parse_with_external(self):
        """Placeholder for actual ciscoconfparse implementation.
        
        This will eventually replace the manual state machine in parsers/cisco/asa/parser.py
        by querying self.raw_tree.
        """
        # Example of how it will look:
        # for obj in self.raw_tree.find_objects(r'^object network'):
        #     name = obj.re_match_field(r'^object network\s+(\S+)')
        #     ...
        raise NotImplementedError(
            "Advanced ASA engine is not yet implemented. Remove --use-external-engines."
        )

    def _build_reverse_indexes(self):
        """Build reverse lookup index: IP -> set of object names."""
        ip_to_objects: Dict[Union[ipaddress.IPv4Address, ipaddress.IPv4Network], Set[str]] = defaultdict(set)
        for name, nets in self.network_objects.items():
            for n in nets:
                ip_to_objects[n].add(name)
        self.ip_to_objects = dict(ip_to_objects)

    def to_ir(self, device_name: Optional[str] = None):
        """Map to common IR using ir_export."""
        return ir_export.to_ir(self, device_name)

    # Resolution methods (copied/adapted from legacy ASAConfig to maintain API parity)
    
    def resolve_network(
        self,
        token: Union[str, ipaddress.IPv4Address, ipaddress.IPv4Network],
        visited: Optional[Set[str]] = None,
        incomplete: Optional[Set[str]] = None,
    ) -> Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network]]:
        if visited is None:
            visited = set()
        if incomplete is None:
            incomplete = set()
        is_top_level = len(visited) == 0

        if isinstance(token, (ipaddress.IPv4Address, ipaddress.IPv4Network)):
            return {token}
        if isinstance(token, str):
            cache_key = token
            cached = self._network_cache.get(cache_key)
            if cached is not None:
                return set(cached)
            token_lower = token.lower()
            if token_lower in ('any', 'any4', 'any-ipv4'):
                result = {ipaddress.ip_network('0.0.0.0/0')}
                self._network_cache[cache_key] = set(result)
                return result
            if token_lower in ('any6', 'any-ipv6'):
                try: 
                    result = {ipaddress.ip_network('::/0')}
                except (ValueError, TypeError): 
                    result = set()
                self._network_cache[cache_key] = set(result)
                return result
            if token in self.network_objects:
                nets = set(self.network_objects[token])
                self._network_cache[cache_key] = set(nets)
                return nets
            if token in self.network_object_groups:
                if token in visited:
                    incomplete.update(visited)
                    cached_cycle = self._network_cache.get(cache_key)
                    return set(cached_cycle) if cached_cycle is not None else set()
                visited.add(token)
                resolved: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network]] = set()
                self._network_cache[cache_key] = resolved
                for m in self.network_object_groups[token]:
                    if isinstance(m, dict):
                        if 'group-object' in m:
                            dep = m['group-object']
                            resolved.update(self.resolve_network(dep, visited, incomplete))
                            if dep in incomplete:
                                incomplete.add(token)
                        elif 'object' in m:
                            dep = m['object']
                            resolved.update(self.resolve_network(dep, visited, incomplete))
                            if dep in incomplete:
                                incomplete.add(token)
                    elif isinstance(m, (ipaddress.IPv4Address, ipaddress.IPv4Network)):
                        resolved.add(m)
                visited.discard(token)

                if is_top_level:
                    for key in incomplete:
                        self._network_cache.pop(key, None)

                return set(resolved)
            try: 
                result = {to_ip_network(token)}
            except (ValueError, TypeError): 
                result = set()
            self._network_cache[cache_key] = set(result)
            return result
        return set()

    def _clone_service_members(self, members: Iterable[dict]) -> List[dict]:
        return [dict(m) for m in members]

    def resolve_service_group(
        self,
        name: str,
        visited: Optional[Set[str]] = None,
        incomplete: Optional[Set[str]] = None,
    ) -> List[dict]:
        if visited is None:
            visited = set()
        if incomplete is None:
            incomplete = set()
        is_top_level = len(visited) == 0

        cache_key = name
        cached = self._service_group_cache.get(cache_key)
        if cached is not None:
            return self._clone_service_members(cached)
        if name in visited:
            incomplete.update(visited)
            return []
        visited.add(name)
        out: List[dict] = []
        for m in self.service_object_groups.get(name, []):
            if isinstance(m, dict) and 'group-object' in m:
                dep = m['group-object']
                out.extend(self.resolve_service_group(dep, visited, incomplete))
                if dep in incomplete:
                    incomplete.add(name)
            else:
                out.append(m)
        visited.discard(name)

        cached_members = tuple(self._clone_service_members(out))
        self._service_group_cache[cache_key] = cached_members

        if is_top_level:
            for key in incomplete:
                self._service_group_cache.pop(key, None)

        return self._clone_service_members(cached_members)
