"""IR import functionality for ASA.

Converts vendor-agnostic Intermediate Representation (IR) format to Cisco ASA
configuration syntax. This enables migration from other platforms to ASA and
round-trip validation of IR conversions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Set

if TYPE_CHECKING:
    from parsers import model as ir

__all__ = ["from_ir"]


def from_ir(device: "ir.Device", hostname: str = None) -> str:
    """Convert IR.Device representation to ASA configuration syntax.

    Args:
        device: IR.Device object containing vendor-agnostic configuration
        hostname: Optional hostname for the device

    Returns:
        ASA configuration as a string

    Design notes:
        - Output targets ASA 9.x syntax
        - Generates network objects, object-groups, service groups, ACLs
        - NAT translation included for manual and auto NAT
        - Interface configuration is minimal (name, IP, security-level)
        - Does not generate full system config (AAA, routing protocols, etc.)
    """
    lines: List[str] = []

    # Optional: Add header comment
    lines.append(f"! Generated from IR (vendor={device.vendor}, version={device.version})")
    if hostname or device.name:
        lines.append(f"hostname {hostname or device.name}")
    lines.append("!")

    # Convert interfaces (if present)
    if device.interfaces:
        for intf in device.interfaces:
            if intf.physical:
                lines.append(f"interface {intf.physical}")
            else:
                lines.append(f"interface {intf.name}")

            lines.append(f" nameif {intf.name}")

            if intf.security_level is not None:
                lines.append(f" security-level {intf.security_level}")

            if intf.ipv4:
                # Parse IP/netmask
                if '/' in intf.ipv4:
                    ip, prefix = intf.ipv4.split('/', 1)
                    netmask = _prefix_to_netmask(int(prefix))
                    lines.append(f" ip address {ip} {netmask}")
                else:
                    # Assume /32 if no prefix
                    lines.append(f" ip address {intf.ipv4} 255.255.255.255")

            lines.append("!")
        lines.append("")

    # Convert network objects
    if device.objects:
        for obj in device.objects:
            lines.append(f"object network {obj.name}")
            for literal in obj.literals:
                if '/' in literal:
                    ip, prefix = literal.split('/', 1)
                    prefix_int = int(prefix)
                    if prefix_int == 32:
                        # /32 is a host
                        lines.append(f" host {ip}")
                    else:
                        # Network with netmask
                        netmask = _prefix_to_netmask(prefix_int)
                        lines.append(f" subnet {ip} {netmask}")
                else:
                    # Host without prefix
                    lines.append(f" host {literal}")
            lines.append("!")
        lines.append("")

    # Convert network groups
    if device.groups:
        for grp in device.groups:
            lines.append(f"object-group network {grp.name}")
            for member in grp.members:
                if member.kind == 'object' and member.ref:
                    lines.append(f" network-object object {member.ref}")
                elif member.kind == 'group' and member.ref:
                    lines.append(f" group-object {member.ref}")
                elif member.kind == 'literal' and member.literal:
                    if '/' in member.literal:
                        lines.append(f" network-object {member.literal}")
                    else:
                        lines.append(f" network-object host {member.literal}")
            lines.append("!")
        lines.append("")

    # Convert service groups
    if device.service_groups:
        for svc_grp in device.service_groups:
            # Check if this is a pure group reference or has protocol definitions
            has_proto = any('proto' in m for m in svc_grp.members)
            has_refs = any('object' in m or 'group' in m for m in svc_grp.members)

            if has_proto:
                # Service object-group with protocol/port definitions
                # Determine protocol type (tcp-udp if mixed, otherwise specific)
                protos: Set[str] = set()
                for m in svc_grp.members:
                    if 'proto' in m:
                        protos.add(m['proto'])

                if len(protos) > 1 or 'ip' in protos:
                    svc_type = 'tcp-udp'
                elif 'tcp' in protos:
                    svc_type = 'tcp'
                elif 'udp' in protos:
                    svc_type = 'udp'
                else:
                    svc_type = 'tcp-udp'

                lines.append(f"object-group service {svc_grp.name} {svc_type}")

                for member in svc_grp.members:
                    if 'proto' in member:
                        proto = member.get('proto')
                        op = member.get('op')
                        v1 = member.get('v1')
                        v2 = member.get('v2')

                        if proto in ('tcp', 'udp'):
                            if op == 'eq' or (v1 == v2):
                                lines.append(f" port-object eq {v1}")
                            elif op == 'range':
                                lines.append(f" port-object range {v1} {v2}")
                    elif 'object' in member:
                        lines.append(f" service-object object {member['object']}")
                    elif 'group' in member:
                        lines.append(f" group-object {member['group']}")

                lines.append("!")
            elif has_refs:
                # Pure group reference (needs protocol type, default to tcp-udp)
                lines.append(f"object-group service {svc_grp.name}")
                for member in svc_grp.members:
                    if 'object' in member:
                        lines.append(f" service-object object {member['object']}")
                    elif 'group' in member:
                        lines.append(f" group-object {member['group']}")
                lines.append("!")

        lines.append("")

    # Convert ACLs
    if device.acls:
        for acl in device.acls:
            acl_name = acl.name or "UNNAMED"

            for entry in acl.entries:
                parts = ["access-list", acl_name, "extended", entry.action]

                # Protocol
                proto = entry.proto or 'ip'
                parts.append(proto)

                # Source addresses
                if entry.src:
                    # If multiple sources, we need to create multiple ACL entries
                    # For simplicity, use first source or 'any'
                    # TODO: Handle multiple sources by emitting multiple ACEs
                    src = entry.src[0] if entry.src else 'any'
                    if src == '0.0.0.0/0':
                        parts.append("any")
                    elif '/' in src:
                        parts.append(src)
                    else:
                        parts.append(f"host {src}")
                else:
                    parts.append("any")

                # Destination addresses
                if entry.dst:
                    dst = entry.dst[0] if entry.dst else 'any'
                    if dst == '0.0.0.0/0':
                        parts.append("any")
                    elif '/' in dst:
                        parts.append(dst)
                    else:
                        parts.append(f"host {dst}")
                else:
                    parts.append("any")

                # Service/ports
                svc = entry.svc or {}
                if svc.get('dst_ports'):
                    for port_spec in svc['dst_ports']:
                        op = port_spec.get('op')
                        start = port_spec.get('start')
                        end = port_spec.get('end')

                        if op == 'eq' or (start == end):
                            parts.append(f"eq {start}")
                        elif op == 'range':
                            parts.append(f"range {start} {end}")

                lines.append(" ".join(parts))

            # Add ACL binding if present
            if acl.bound_to:
                binding = acl.binding or {}
                direction = binding.get('direction', 'in')
                lines.append(f"access-group {acl_name} {direction} interface {acl.bound_to}")

            lines.append("!")

        lines.append("")

    # Convert NAT rules
    if device.nats:
        lines.append("! NAT rules")
        for nat in device.nats:
            if nat.kind == 'auto':
                # Object NAT (auto NAT)
                detail = nat.detail or {}
                real_obj = detail.get('real_object')
                nat_kind = detail.get('kind')
                mapped = detail.get('mapped')

                if real_obj:
                    # This would be inside the object definition
                    # For simplicity, emit inline (not inside object block)
                    lines.append(f"! Auto NAT for {real_obj}")
                    if nat_kind == 'dynamic' and mapped == 'interface':
                        src_if = nat.src_if or 'any'
                        dst_if = nat.dst_if or 'any'
                        lines.append(f"nat ({src_if},{dst_if}) source dynamic {real_obj} interface")
                    lines.append("!")

            elif nat.kind == 'manual':
                # Manual NAT
                detail = nat.detail or {}
                src_if = nat.src_if or 'any'
                dst_if = nat.dst_if or 'any'
                section = nat.section

                source = detail.get('source', {})
                destination = detail.get('destination', {})

                # Build NAT statement
                nat_parts = [f"nat"]

                # Section
                if section is not None:
                    nat_parts.append(f"({src_if},{dst_if})")
                    nat_parts.append(f"source")

                    # Source translation
                    if source:
                        real = source.get('real')
                        mapped = source.get('mapped')
                        if real and mapped:
                            nat_parts.append(f"static {real} {mapped}")

                    # Destination translation
                    if destination:
                        nat_parts.append("destination")
                        real = destination.get('real')
                        mapped = destination.get('mapped')
                        if real and mapped:
                            nat_parts.append(f"static {real} {mapped}")

                if len(nat_parts) > 1:
                    lines.append(" ".join(nat_parts))
                    lines.append("!")

        lines.append("")

    # Convert static routes
    if device.static_routes:
        lines.append("! Static routes")
        for route in device.static_routes:
            # route <interface> <destination> <netmask> <gateway> [distance] [tunneled] [track N]
            parts = ["route"]

            # Interface
            if route.interface:
                parts.append(route.interface)
            else:
                parts.append("outside")  # Default interface if not specified

            # Destination and netmask
            if '/' in route.destination:
                ip, prefix = route.destination.split('/', 1)
                netmask = _prefix_to_netmask(int(prefix))
                parts.append(ip)
                parts.append(netmask)
            else:
                parts.append(route.destination)
                parts.append("255.255.255.255")

            # Gateway
            if route.next_hop:
                parts.append(route.next_hop)
            else:
                # Connected route (no gateway)
                parts.append("0.0.0.0")

            # Distance
            if route.distance is not None:
                parts.append(str(route.distance))

            # Tunneled flag
            if route.tunneled:
                parts.append("tunneled")

            # Track
            if route.track is not None:
                parts.append("track")
                parts.append(str(route.track))

            lines.append(" ".join(parts))
        lines.append("!")
        lines.append("")

    # Convert dynamic routing
    if device.dynamic_routing:
        lines.append("! Dynamic routing")
        for routing_process in device.dynamic_routing:
            # router <protocol> <process-id>
            if routing_process.process_id:
                lines.append(f"router {routing_process.protocol} {routing_process.process_id}")
            else:
                lines.append(f"router {routing_process.protocol}")

            # Router ID
            if routing_process.router_id:
                lines.append(f" router-id {routing_process.router_id}")

            # Distance
            if routing_process.distance and routing_process.distance.get('default'):
                lines.append(f" distance {routing_process.distance['default']}")

            # Passive interfaces
            for iface in routing_process.passive_interfaces:
                lines.append(f" passive-interface {iface}")

            # OSPF area configuration
            if routing_process.areas_config:
                for area_id, area_cfg in routing_process.areas_config.items():
                    # Area type (stub/nssa)
                    if area_cfg.get('type'):
                        area_line = f" area {area_id} {area_cfg['type']}"
                        if area_cfg.get('no_summary'):
                            area_line += " no-summary"
                        lines.append(area_line)
                    # Area authentication
                    if area_cfg.get('authentication'):
                        auth_type = area_cfg['authentication']
                        if auth_type == 'message-digest':
                            lines.append(f" area {area_id} authentication message-digest")
                        else:
                            lines.append(f" area {area_id} authentication")

            # Networks
            for net in routing_process.networks:
                # Handle both 'network' (ASA) and 'prefix' (FortiGate) keys
                network = net.get('network') or net.get('prefix')
                if network:
                    net_str = f" network {network}"
                    if 'mask' in net:
                        net_str += f" {net['mask']}"
                    if 'area' in net:
                        net_str += f" area {net['area']}"
                    lines.append(net_str)

            # Neighbors (BGP)
            for neighbor in routing_process.neighbors:
                lines.append(f" neighbor {neighbor['ip']} remote-as {neighbor['remote_as']}")
                if neighbor.get('description'):
                    lines.append(f" neighbor {neighbor['ip']} description {neighbor['description']}")
                if neighbor.get('password'):
                    lines.append(f" neighbor {neighbor['ip']} password <removed>")
                if neighbor.get('timers'):
                    timers = neighbor['timers']
                    lines.append(f" neighbor {neighbor['ip']} timers {timers['keepalive']} {timers['holdtime']}")

            # Redistribute
            for redis in routing_process.redistribute:
                redis_line = f" redistribute {redis['source']}"
                if redis.get('subnets'):
                    redis_line += " subnets"
                if redis.get('metric'):
                    redis_line += f" metric {redis['metric']}"
                lines.append(redis_line)

            # Timers (protocol-level)
            for timer_type, timer_vals in routing_process.timers.items():
                timer_line = f" timers {timer_type} {timer_vals['value1']}"
                if timer_vals.get('value2'):
                    timer_line += f" {timer_vals['value2']}"
                lines.append(timer_line)

            # Additional config
            config = routing_process.config or {}
            if config.get('auto_cost_reference_bandwidth'):
                lines.append(f" auto-cost reference-bandwidth {config['auto_cost_reference_bandwidth']}")
            if config.get('default_information_originate'):
                lines.append(" default-information originate")
            if config.get('log_adjacency_changes'):
                lines.append(" log-adjacency-changes")

            lines.append("!")
        lines.append("")

    return '\n'.join(lines)


def _prefix_to_netmask(prefix: int) -> str:
    """Convert CIDR prefix length to dotted-decimal netmask."""
    mask = (0xffffffff >> (32 - prefix)) << (32 - prefix)
    return f"{(mask >> 24) & 0xff}.{(mask >> 16) & 0xff}.{(mask >> 8) & 0xff}.{mask & 0xff}"
