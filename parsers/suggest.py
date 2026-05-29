# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Correction suggestions for blocked traffic paths.

Given the result of a vendor ``path_check`` (see ``parsers.cisco.asa.path`` and
``parsers.fortigate.path``), this module synthesises:

* the concrete CLI commands an operator would run to *allow* a flow that is
  currently being denied (explicit ``deny`` or the implicit end-of-policy deny),
  and
* optional **live-verification** commands (ASA ``packet-tracer input ...`` /
  FortiGate ``diagnose firewall iprope lookup ...``) the operator can paste on
  the box to confirm the change.

Design notes (kept deliberately decoupled so an HTTP API or MCP tool can reuse it
trivially):

* The single public entry point :func:`suggest_corrections` is a **pure
  function** driven entirely off the JSON-serialisable ``path_check`` result dict.
  It never touches parser internals.
* The output dict is **stable and versioned** (``schema_version``) so downstream
  API/MCP consumers have a contract to code against.
* Vendor dispatch goes through the :data:`_GENERATORS` registry, so adding a new
  vendor (or wiring a new caller) is a one-line change.

Two operational scenarios are covered, mirroring how operators reason about
firewall placement:

* **Ingress** – the rule needed on the interface where traffic *enters* the
  firewall (e.g. an uplink or lobby segment).
* **Egress** – the rule needed on the interface where traffic *exits* toward the
  destination's local subnet.

For ASA each scenario produces an ``access-list`` line bound to the relevant
``nameif``. For FortiGate, where policies are inherently directional
(``srcintf`` -> ``dstintf``), a single ``config firewall policy`` block expresses
the ingress/egress pairing (VDOM-wrapped when a VDOM is in play).
"""

from __future__ import annotations

import ipaddress
from typing import Any, Dict, List, Optional, Tuple

__all__ = ["suggest_corrections", "SCHEMA_VERSION"]

# Stable contract version for API/MCP consumers. Bump on breaking shape changes.
SCHEMA_VERSION = "1.1"  # 1.1: + per-suggestion optional `note` field

# IANA protocol numbers used by FortiGate's iprope lookup.
_PROTO_NUMBERS = {"icmp": 1, "tcp": 6, "udp": 17}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _classify(result: dict) -> str:
    """Return one of 'allowed' | 'explicit-deny' | 'implicit-deny'."""
    if result.get("allowed"):
        return "allowed"
    decision = ((result.get("acl") or {}).get("decision") or "").lower()
    if decision == "deny":
        return "explicit-deny"
    # ASA 'no-match' and FortiGate 'implicit-deny' both mean: fell through.
    return "implicit-deny"


def _blocking_rule(result: dict) -> Optional[dict]:
    """Return the first explicit deny match, if any."""
    for match in (result.get("acl") or {}).get("matches") or []:
        if (match.get("action") or "").lower() == "deny":
            return match
    return None


def _port_token(proto: Optional[str], dports: List[int]) -> Optional[int]:
    """Single representative destination port for L4 protocols, else None.

    A multi-port flow (``--dport 80 --dport 443``) intentionally collapses to the
    first port: the suggestion is a starting point an operator extends, not an
    exhaustive rule set.
    """
    if (proto or "").lower() not in {"tcp", "udp"}:
        return None
    return dports[0] if dports else None


def _proto_number(proto: Optional[str]) -> int:
    """IANA protocol number for FortiGate iprope lookup.

    Falls back to a numeric ``proto`` token if one is supplied, else 0.
    """
    p = (proto or "").lower()
    if p in _PROTO_NUMBERS:
        return _PROTO_NUMBERS[p]
    if p.isdigit():
        return int(p)
    return 0


def _first(value: Any) -> Optional[str]:
    if isinstance(value, (list, tuple)):
        return str(value[0]) if value else None
    if isinstance(value, set):
        # Sets are unordered; sort for deterministic command generation.
        # Filter None and key on str so a mixed-type set can't raise TypeError.
        items = sorted((x for x in value if x is not None), key=str)
        return str(items[0]) if items else None
    if not value:
        return None
    return str(value)


# ---------------------------------------------------------------------------
# ASA generation
# ---------------------------------------------------------------------------

def _asa_addr_token(addr: Optional[str]) -> str:
    """Format an address as ASA ACL tokens ('host x' / 'net mask' / 'any').

    Wildcard tokens (``any``/``any4``/``any6``) collapse to ``any``. Anything
    that is neither a valid IP nor a CIDR (e.g. an object name that could not be
    resolved) is returned verbatim so we never emit invalid lines like
    ``host any`` or ``host WebServer01``.
    """
    if not addr:
        # Defensive: a missing endpoint (malformed result dict) must not leak a
        # bare ``None`` into the generated line.
        return "any"
    if addr.lower() in {"any", "any4", "any6"}:
        return "any"
    try:
        ipaddress.ip_address(addr)
        return f"host {addr}"
    except ValueError:
        pass
    try:
        net = ipaddress.ip_network(addr, strict=False)
        host_prefix = 128 if net.version == 6 else 32
        if net.prefixlen == host_prefix:
            return f"host {net.network_address}"
        if net.prefixlen == 0:
            return "any"
        # IPv6 ACLs use prefix-length notation; IPv4 uses dotted netmask.
        return str(net) if net.version == 6 else f"{net.network_address} {net.netmask}"
    except ValueError:
        return addr


def _asa_acl_line(nameif: str, suffix: str, proto: str, src: str, dst: str,
                  port: Optional[int]) -> str:
    acl_name = f"{nameif}_access_{suffix}"
    line = (
        f"access-list {acl_name} extended permit {proto} "
        f"{_asa_addr_token(src)} {_asa_addr_token(dst)}"
    )
    if port is not None:
        line += f" eq {port}"
    return line


def _multiport_note(proto: str, dports: List[int], port: Optional[int]) -> Optional[str]:
    """Caveat when a multi-port flow collapses to a single representative port."""
    if port is not None and len(dports) > 1:
        others = ", ".join(str(p) for p in dports if p != port)
        return (
            f"Flow has multiple destination ports ({', '.join(map(str, dports))}); "
            f"only {port} is shown — duplicate the line for: {others}."
        )
    return None


# The ACL names below are the ASA auto-generated convention; a device may bind a
# differently named ACL to the interface, so suggestions carry this caveat.
_ASA_ACL_NAME_NOTE = (
    "ACL name follows the '<nameif>_access_<dir>' convention; verify the ACL "
    "actually bound to the interface ('show run access-group') before pasting."
)


def _suggest_asa(result: dict, *, ingress_interface: Optional[str],
                 egress_interface: Optional[str],
                 vdom: Optional[str]) -> List[dict]:
    ctx = result.get("context") or {}
    resolved = result.get("resolved") or {}
    inp = result.get("input") or {}

    proto = (inp.get("proto") or "ip").lower()
    dports = inp.get("dports") or []
    port = _port_token(proto, dports)

    # ASA ACLs match on real (pre-NAT) addresses on modern releases (>= 8.3).
    src = resolved.get("src") or inp.get("src")
    dst = resolved.get("dst") or inp.get("dst")

    ingress = ingress_interface or ctx.get("src_interface")
    egress = egress_interface or ctx.get("dst_interface")

    notes = [n for n in (_ASA_ACL_NAME_NOTE, _multiport_note(proto, dports, port)) if n]
    note = " ".join(notes) if notes else None

    suggestions: List[dict] = []
    if ingress:
        suggestions.append({
            "scenario": "ingress",
            "vendor": "asa",
            "location": {"nameif": ingress, "direction": "in",
                         "acl": f"{ingress}_access_in"},
            "commands": [_asa_acl_line(ingress, "in", proto, src, dst, port)],
            "rationale": f"Permit the flow as it enters the firewall on '{ingress}'.",
            "note": note,
        })
    if egress and egress != ingress:
        suggestions.append({
            "scenario": "egress",
            "vendor": "asa",
            "location": {"nameif": egress, "direction": "out",
                         "acl": f"{egress}_access_out"},
            "commands": [_asa_acl_line(egress, "out", proto, src, dst, port)],
            "rationale": (
                f"Permit the flow as it exits toward the destination subnet on "
                f"'{egress}'."
            ),
            "note": note,
        })
    if not suggestions:
        suggestions.append({
            "scenario": "ingress",
            "vendor": "asa",
            "location": {"nameif": "<nameif>", "direction": "in",
                         "acl": "<nameif>_access_in"},
            "commands": [_asa_acl_line("<nameif>", "in", proto, src, dst, port)],
            "rationale": (
                "Ingress interface could not be inferred; substitute the correct "
                "nameif."
            ),
            "note": note,
        })
    return suggestions


def _verify_asa(result: dict, *, ingress_interface: Optional[str] = None,
                egress_interface: Optional[str] = None,
                vdom: Optional[str] = None) -> List[dict]:
    """Reuse the packet-tracer commands the ASA path builder already produced."""
    verifications: List[dict] = []
    ctx = result.get("context") or {}
    tracers = ctx.get("packet_tracer") or result.get("packet_tracer") or []
    seen: set = set()
    for tr in tracers:
        cmd = tr.get("command")
        if not cmd or cmd in seen:
            continue
        seen.add(cmd)
        iface = tr.get("interface")
        verifications.append({
            "vendor": "asa",
            "kind": "packet-tracer",
            "command": cmd,
            "description": (
                f"Simulate the flow entering '{iface}' to confirm the new rule "
                f"permits it." if iface else "Simulate the flow to confirm the fix."
            ),
        })
    return verifications


# ---------------------------------------------------------------------------
# FortiGate generation
# ---------------------------------------------------------------------------

def _ftg_service_name(proto: Optional[str], dports: List[int]) -> str:
    p = (proto or "").lower()
    if p in {"tcp", "udp"} and dports:
        return f"{p.upper()}_{dports[0]}"
    if p == "icmp":
        return "ALL_ICMP"
    if p in {"tcp", "udp"}:
        return p.upper()
    return "ALL"


def _ftg_policy_block(srcintf: str, dstintf: str, src_obj: str, dst_obj: str,
                      service: str) -> List[str]:
    return [
        "config firewall policy",
        "    edit 0",
        f'        set srcintf "{srcintf}"',
        f'        set dstintf "{dstintf}"',
        f'        set srcaddr "{src_obj}"',
        f'        set dstaddr "{dst_obj}"',
        f'        set service "{service}"',
        "        set action accept",
        '        set schedule "always"',
        "    next",
        "end",
    ]


def _ftg_vdom_wrap(commands: List[str], vdom: Optional[str]) -> List[str]:
    """Wrap a command block in 'config vdom / edit <vdom> ... end' when set.

    The trailing 'end' closes 'config vdom'; the inner blocks close themselves.
    """
    if vdom:
        return ["config vdom", f"edit {vdom}", *commands, "end"]
    return commands


def _ftg_subnet_tokens(net: "ipaddress.IPv4Network") -> str:
    """FortiGate 'set subnet' value: '<addr> <mask>' for IPv4."""
    return f"{net.network_address} {net.netmask}"


def _ftg_resolve_addr(token: str, inventory: List[dict],
                      taken: set) -> Tuple[str, List[str]]:
    """Resolve a srcaddr/dstaddr token to a named FortiGate address object.

    FortiGate policy ``set srcaddr``/``dstaddr`` only accept named ``firewall
    address`` objects, never raw IPs/CIDRs. Strategy (per operator guidance):

    1. If the token is not a raw IP/CIDR, assume it is already an object name
       (or a ``<placeholder>``) and use it verbatim.
    2. Otherwise reverse-look it up in the device's address inventory (the
       "phone book") — if an existing object covers exactly that IP/CIDR, use
       its name and emit no new object.
    3. Failing that, synthesise an ``IP_<addr>`` / ``NET_<net>/<prefix>`` object,
       choosing a name that does not collide with an existing one, and emit the
       ``config firewall address`` block to create it.

    Returns ``(object_name, address_block_commands)``.
    """
    net = None
    try:
        ip = ipaddress.ip_address(token)
        net = ipaddress.ip_network(f"{ip}/32" if ip.version == 4 else f"{ip}/128",
                                   strict=False)
    except ValueError:
        try:
            net = ipaddress.ip_network(token, strict=False)
        except ValueError:
            net = None
    if net is None:
        # Already an object name (or placeholder) — use as-is.
        return token, []

    canonical = str(net)
    # 2. Reverse lookup against the inventory.
    for obj in inventory:
        if canonical in (obj.get("subnets") or []):
            return obj["name"], []

    # 3. Synthesise a collision-free object name.
    is_host = net.prefixlen in (32, 128)
    base = f"IP_{net.network_address}" if is_host else f"NET_{canonical}"
    name = base
    suffix = 1
    while name in taken:
        suffix += 1
        name = f"{base}_{suffix}"
    taken.add(name)
    block = [
        "config firewall address",
        f'    edit "{name}"',
        f"        set subnet {_ftg_subnet_tokens(net)}",
        "    next",
        "end",
    ]
    return name, block


def _ftg_interfaces(result: dict, ingress_interface: Optional[str],
                    egress_interface: Optional[str]) -> Tuple[str, str]:
    blocking = _blocking_rule(result)
    binding = (blocking or {}).get("binding") or {}
    srcintf = ingress_interface or _first(binding.get("srcintf")) or "<in>"
    dstintf = egress_interface or _first(binding.get("dstintf")) or "<out>"
    return srcintf, dstintf


def _suggest_fortigate(result: dict, *, ingress_interface: Optional[str],
                       egress_interface: Optional[str],
                       vdom: Optional[str]) -> List[dict]:
    inp = result.get("input") or {}
    proto = (inp.get("proto") or "").lower()
    dports = inp.get("dports") or []
    service = _ftg_service_name(proto, dports)
    port = _port_token(proto, dports)

    # Address objects: prefer the original tokens (often object names already);
    # for raw IP/CIDR inputs reuse an existing object or synthesise one, since
    # FortiGate srcaddr/dstaddr only accept named objects.
    src_token = inp.get("src") or "<src_obj>"
    dst_token = inp.get("dst") or "<dst_obj>"
    inventory = (result.get("context") or {}).get("address_objects") or []
    taken = {obj.get("name") for obj in inventory if obj.get("name")}

    src_name, src_block = _ftg_resolve_addr(src_token, inventory, taken)
    dst_name, dst_block = _ftg_resolve_addr(dst_token, inventory, taken)

    srcintf, dstintf = _ftg_interfaces(result, ingress_interface, egress_interface)
    commands = _ftg_vdom_wrap(
        [*src_block, *dst_block,
         *_ftg_policy_block(srcintf, dstintf, src_name, dst_name, service)],
        vdom,
    )

    rationale = (
        f"Add a policy permitting {srcintf} -> {dstintf} for the flow. FortiGate "
        "policies are directional, so this single rule covers both ingress and "
        "egress for the path."
    )
    if vdom:
        rationale += f" (VDOM '{vdom}')"

    notes = []
    created = [n for n, blk in ((src_name, src_block), (dst_name, dst_block)) if blk]
    if created:
        notes.append(
            "Creates address object(s) " + ", ".join(created) +
            "; adjust the name(s) to match your naming standard if required."
        )
    mp = _multiport_note(proto, dports, port)
    if mp:
        notes.append(mp)

    return [{
        "scenario": "policy",
        "vendor": "fortigate",
        "location": {"srcintf": srcintf, "dstintf": dstintf, "vdom": vdom},
        "commands": commands,
        "rationale": rationale,
        "note": " ".join(notes) if notes else None,
    }]


def _verify_fortigate(result: dict, *, ingress_interface: Optional[str] = None,
                      egress_interface: Optional[str] = None,
                      vdom: Optional[str] = None) -> List[dict]:
    inp = result.get("input") or {}
    resolved = result.get("resolved") or {}
    proto = (inp.get("proto") or "").lower()
    dports = inp.get("dports") or []

    src = resolved.get("src") or inp.get("src") or "<src_ip>"
    dst = resolved.get("dst") or inp.get("dst") or "<dst_ip>"
    proto_num = _proto_number(proto)
    sport = 0  # ephemeral; iprope only needs the destination socket
    dport = dports[0] if dports else 0

    # Keep the verification interface consistent with the suggested policy when
    # the caller supplied overrides.
    srcintf, _dstintf = _ftg_interfaces(result, ingress_interface, egress_interface)
    lookup = (
        f"diagnose firewall iprope lookup {src} {sport} {dst} {dport} "
        f"{proto_num} {srcintf}"
    )
    command = lookup
    if vdom:
        # iprope is run inside the VDOM context on multi-VDOM devices.
        command = f"config vdom\nedit {vdom}\n{lookup}\nend"
    return [{
        "vendor": "fortigate",
        "kind": "iprope-lookup",
        "command": command,
        "description": (
            "Look up the kernel policy match for this socket to confirm the new "
            "policy is selected."
        ),
    }]


# ---------------------------------------------------------------------------
# Vendor registry + public entry point
# ---------------------------------------------------------------------------

# (suggestion_builder, verification_builder) per vendor. Adding a vendor is a
# single registry entry — keeps API/MCP wiring trivial.
_GENERATORS = {
    "asa": (_suggest_asa, _verify_asa),
    "fortigate": (_suggest_fortigate, _verify_fortigate),
}


def suggest_corrections(
    result: dict,
    vendor: str,
    *,
    ingress_interface: Optional[str] = None,
    egress_interface: Optional[str] = None,
    vdom: Optional[str] = None,
) -> dict:
    """Generate CLI correction + verification suggestions for a blocked flow.

    Args:
        result: The dict returned by a vendor ``path_check``.
        vendor: ``'asa'`` or ``'fortigate'``.
        ingress_interface: Optional override for the entry interface name.
        egress_interface: Optional override for the exit interface name.
        vdom: Optional FortiGate VDOM name (threaded into generated commands).

    Returns:
        A JSON-serialisable dict (see module docstring / ``SCHEMA_VERSION``)::

            {
              "schema_version": "1.1",
              "needed": bool,            # False when the flow is already allowed
              "reason": str,             # allowed | explicit-deny | implicit-deny
              "blocking_rule": dict|None,
              "suggestions": [ {scenario, vendor, location, commands, rationale} ],
              "verification": [ {vendor, kind, command, description} ],
            }
    """
    reason = _classify(result)
    if reason == "allowed":
        return {
            "schema_version": SCHEMA_VERSION,
            "needed": False,
            "reason": reason,
            "blocking_rule": None,
            "suggestions": [],
            "verification": [],
        }

    v = (vendor or "").lower()
    try:
        suggest_fn, verify_fn = _GENERATORS[v]
    except KeyError:
        raise ValueError(f"unsupported vendor for suggestions: {vendor!r}")

    suggestions = suggest_fn(
        result,
        ingress_interface=ingress_interface,
        egress_interface=egress_interface,
        vdom=vdom,
    )
    verification = verify_fn(
        result,
        ingress_interface=ingress_interface,
        egress_interface=egress_interface,
        vdom=vdom,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "needed": True,
        "reason": reason,
        "blocking_rule": _blocking_rule(result),
        "suggestions": suggestions,
        "verification": verification,
    }
