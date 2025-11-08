"""IR import functionality for FortiGate.

Converts vendor-agnostic Intermediate Representation (IR) format to FortiGate
configuration syntax. This enables migration from other platforms to FortiGate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from parsers import model as ir

__all__ = ["from_ir"]


def from_ir(device: "ir.Device", vdom: str = "root") -> str:
    """Convert IR.Device representation to FortiGate configuration syntax.

    Args:
        device: IR.Device object containing vendor-agnostic configuration
        vdom: VDOM name to generate config for (default: "root")

    Returns:
        FortiGate configuration as a string

    Design notes:
        - Output is suitable for FortiOS 7.4+
        - Generates config firewall address, addrgrp, service custom/group, policy
        - NAT translation not yet implemented
        - Interface/zone mapping is simplified
    """
    lines: List[str] = []

    # Optional: Add header comment
    lines.append(f"# Generated from IR (vendor={device.vendor}, version={device.version})")
    lines.append(f"# Target VDOM: {vdom}")
    lines.append("")

    # Convert network objects to firewall addresses
    if device.objects:
        lines.append("config firewall address")
        for obj in device.objects:
            lines.append(f'    edit "{obj.name}"')
            # FortiGate addresses are single subnet; if multiple literals, create one per literal
            if obj.literals:
                # Use first literal as primary (or combine if possible)
                # For simplicity, we'll just use the first one
                # TODO: Handle multiple literals by creating obj_name_1, obj_name_2, etc.
                literal = obj.literals[0]
                if '/' in literal:
                    # CIDR notation
                    ip, prefix = literal.split('/', 1)
                    # Convert prefix to netmask
                    netmask = _prefix_to_netmask(int(prefix))
                    lines.append(f"        set subnet {ip} {netmask}")
                else:
                    # Single host
                    lines.append(f"        set subnet {literal} 255.255.255.255")
            lines.append("    next")
        lines.append("end")
        lines.append("")

    # Convert network groups to firewall addrgrp
    if device.groups:
        lines.append("config firewall addrgrp")
        for grp in device.groups:
            lines.append(f'    edit "{grp.name}"')
            member_names: List[str] = []
            for member in grp.members:
                if member.kind == 'object' and member.ref:
                    member_names.append(f'"{member.ref}"')
                elif member.kind == 'group' and member.ref:
                    member_names.append(f'"{member.ref}"')
                elif member.kind == 'literal' and member.literal:
                    # FortiGate groups can only reference named objects
                    # Create an auto-generated address object for literals
                    literal_obj_name = f"auto_{member.literal.replace('/', '_').replace('.', '_')}"
                    member_names.append(f'"{literal_obj_name}"')
                    # TODO: Track these and emit them in the address section
            if member_names:
                lines.append(f"        set member {' '.join(member_names)}")
            lines.append("    next")
        lines.append("end")
        lines.append("")

    # Convert service groups to firewall service custom and group
    # First pass: collect service objects (non-group members)
    service_objects: List[tuple] = []  # (name, proto, op, v1, v2)
    service_group_refs: dict = {}  # {group_name: [member_names]}

    for svc_grp in device.service_groups:
        has_proto_members = False
        group_members: List[str] = []

        for member in svc_grp.members:
            if 'proto' in member:
                # This is a protocol definition, create a service custom
                has_proto_members = True
                proto = member.get('proto')
                op = member.get('op')
                v1 = member.get('v1')
                v2 = member.get('v2')
                service_objects.append((svc_grp.name, proto, op, v1, v2))
            elif 'object' in member:
                group_members.append(member['object'])
            elif 'group' in member:
                group_members.append(member['group'])

        if group_members and not has_proto_members:
            # This is a pure group reference
            service_group_refs[svc_grp.name] = group_members

    # Emit service custom objects
    if service_objects:
        lines.append("config firewall service custom")
        # Group by service name
        svc_dict: dict = {}
        for name, proto, op, v1, v2 in service_objects:
            if name not in svc_dict:
                svc_dict[name] = {'tcp': [], 'udp': []}
            if proto in ('tcp', 'udp'):
                if op == 'eq' or (v1 == v2):
                    svc_dict[name][proto].append(f"{v1}")
                elif op == 'range':
                    svc_dict[name][proto].append(f"{v1}-{v2}")

        for name, spec in svc_dict.items():
            lines.append(f'    edit "{name}"')
            if spec['tcp']:
                lines.append(f"        set tcp-portrange {' '.join(spec['tcp'])}")
            if spec['udp']:
                lines.append(f"        set udp-portrange {' '.join(spec['udp'])}")
            lines.append("    next")
        lines.append("end")
        lines.append("")

    # Emit service groups
    if service_group_refs:
        lines.append("config firewall service group")
        for name, members in service_group_refs.items():
            lines.append(f'    edit "{name}"')
            quoted_members = [f'"{m}"' for m in members]
            lines.append(f"        set member {' '.join(quoted_members)}")
            lines.append("    next")
        lines.append("end")
        lines.append("")

    # Convert ACLs to firewall policies
    if device.acls:
        lines.append("config firewall policy")
        policy_id = 1
        for acl in device.acls:
            for entry in acl.entries:
                lines.append(f"    edit {policy_id}")
                policy_id += 1

                # Action
                action = 'accept' if entry.action == 'permit' else 'deny'
                lines.append(f"        set action {action}")

                # Source addresses
                src_addrs = entry.src if entry.src else ['all']
                # Quote address names
                src_quoted = [f'"{s}"' if not s.lower() == 'all' else 'all' for s in src_addrs]
                lines.append(f"        set srcaddr {' '.join(src_quoted)}")

                # Destination addresses
                dst_addrs = entry.dst if entry.dst else ['all']
                dst_quoted = [f'"{d}"' if not d.lower() == 'all' else 'all' for d in dst_addrs]
                lines.append(f"        set dstaddr {' '.join(dst_quoted)}")

                # Service
                svc = entry.svc or {}
                service_names: List[str] = []

                # Check for service groups
                if svc.get('dst_service_groups'):
                    service_names.extend([f'"{sg}"' for sg in svc['dst_service_groups']])

                # Check for service objects
                if svc.get('dst_service_objects'):
                    service_names.extend([f'"{so}"' for so in svc['dst_service_objects']])

                # If no service specified, use ALL
                if not service_names:
                    service_names = ['ALL']

                lines.append(f"        set service {' '.join(service_names)}")

                # TODO: Add srcintf/dstintf based on binding/direction if available
                # For now, we'll omit them (FortiGate requires these, but we don't have zone info)

                lines.append("    next")
        lines.append("end")
        lines.append("")

    # NAT rules not yet implemented
    if device.nats:
        lines.append("# NAT translation not yet implemented")
        lines.append("")

    # Convert static routes
    if device.static_routes:
        lines.append("config router static")
        seq_id = 1
        for route in device.static_routes:
            lines.append(f"    edit {seq_id}")
            seq_id += 1

            # Destination
            if route.destination:
                lines.append(f"        set dst {route.destination}")

            # Gateway
            if route.next_hop:
                lines.append(f"        set gateway {route.next_hop}")

            # Device (interface)
            if route.interface:
                lines.append(f'        set device "{route.interface}"')

            # Distance
            if route.distance is not None:
                lines.append(f"        set distance {route.distance}")

            lines.append("    next")
        lines.append("end")
        lines.append("")

    # Convert dynamic routing
    for routing_process in device.dynamic_routing:
        protocol = routing_process.protocol

        if protocol == 'ospf':
            lines.append("config router ospf")

            # Router ID
            if routing_process.router_id:
                lines.append(f"    set router-id {routing_process.router_id}")

            # Networks
            if routing_process.networks:
                lines.append("    config network")
                net_id = 1
                for net in routing_process.networks:
                    lines.append(f"        edit {net_id}")
                    net_id += 1
                    if 'prefix' in net:
                        lines.append(f"            set prefix {net['prefix']}")
                    elif 'network' in net:
                        lines.append(f"            set prefix {net['network']}")
                    if 'area' in net:
                        lines.append(f"            set area {net['area']}")
                    lines.append("        next")
                lines.append("    end")

            # Redistribute
            if routing_process.redistribute:
                lines.append("    config redistribute \"connected\"")
                lines.append("        set status enable")
                lines.append("    end")

            lines.append("end")
            lines.append("")

        elif protocol == 'bgp':
            lines.append("config router bgp")

            # AS number
            if routing_process.process_id:
                lines.append(f"    set as {routing_process.process_id}")

            # Router ID
            if routing_process.router_id:
                lines.append(f"    set router-id {routing_process.router_id}")

            # Neighbors
            if routing_process.neighbors:
                lines.append("    config neighbor")
                for neighbor in routing_process.neighbors:
                    lines.append(f"        edit \"{neighbor['ip']}\"")
                    if 'remote_as' in neighbor:
                        lines.append(f"            set remote-as {neighbor['remote_as']}")
                    lines.append("        next")
                lines.append("    end")

            lines.append("end")
            lines.append("")

    return '\n'.join(lines)


def _prefix_to_netmask(prefix: int) -> str:
    """Convert CIDR prefix length to dotted-decimal netmask."""
    mask = (0xffffffff >> (32 - prefix)) << (32 - prefix)
    return f"{(mask >> 24) & 0xff}.{(mask >> 16) & 0xff}.{(mask >> 8) & 0xff}.{mask & 0xff}"
