# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Handlers for form-based actions (inspect/compare/find/packet)."""

from __future__ import annotations

import html
import ipaddress
import os
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set, Tuple, Union

from parsers.cisco import asa as asa_parser
from parsers.fortigate import inspect as fortigate_parser
from parsers.fortigate import path_check as fortigate_path
from parsers.fortigate.config import FTGConfig
from ..vendor_caps import get_caps

from ..state import AppState
from utils.config import clean_config_text


def process_run(state: AppState, fields: Mapping[str, List[str]]) -> Tuple[int, Dict[str, Any]]:
    """Process a run request and return HTML payload."""

    def get(name: str, default: str = "") -> str:
        return (fields.get(name, [default])[0] or default).strip()

    def is_checked(name: str, default: bool = False) -> bool:
        values = fields.get(name)
        if not values:
            return default
        for value in values:
            text = (value or "").strip().lower()
            if text in {"0", "false", "no", "off"}:
                return False
        return True

    vendor = get("vendor", "asa").lower()
    mode = get("mode", "inspect")
    caps = get_caps(vendor)
    if not caps:
        return 400, {"error": f"Vendor {vendor!r} not supported"}
    config_field = caps.config_field
    cfg_file = get(config_field)
    vdom = get("vdom") or ""
    proto = get("proto")
    include_any = bool(fields.get("include_any", []))
    find_verbose = bool(fields.get("find_verbose", []))
    replay_flag = get("history_replay", "0").lower()
    suppress_history = replay_flag in {"1", "true", "yes", "on"}
    dports_clean: Set[int] = set()
    for dp in fields.get("dport", []):
        dp = dp.strip()
        if not dp:
            continue
        try:
            dports_clean.add(int(dp))
        except Exception:
            continue
    svc_filter = None
    if proto or dports_clean:
        svc_filter = {"proto": proto or None, "dports": dports_clean}

    configs = state.settings.paths.configs.get(vendor)
    if not configs:
        return 400, {"error": f"Vendor {vendor!r} not supported"}
    path = os.path.join(configs, cfg_file) if cfg_file else ""
    if not path or not os.path.isfile(path):
        return 400, {"error": "Invalid or missing config file"}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            cfg_text = clean_config_text(handle.read())
    except Exception as exc:  # pragma: no cover - filesystem failures
        return 500, {"error": f"Failed to read: {exc}"}

    tab = "rules"
    html_output = ""
    history_query = ""
    meta: Dict[str, Any] = {
        "mode": mode,
        "vendor": vendor,
        "config": cfg_file,
        "query": "",
        "vdom": vdom,
    }

    try:
        if mode == "inspect":
            if not caps.supports_inspect:
                return 400, {"error": f"Inspect not supported for vendor {vendor!r}"}
            target = get("inspect")
            if vendor == "asa":
                cfg = asa_parser.ASAConfig(cfg_text)
                report = asa_parser.inspect_host(
                    cfg_text, target, service_filter=svc_filter, include_any=include_any
                )
                try:
                    nets = cfg.resolve_network(target)
                    inclusive = {}
                    for net in nets:
                        names = cfg.ip_to_objects.get(net, set()) if hasattr(cfg, "ip_to_objects") else set()
                        if names:
                            inclusive[net] = names
                    report["aliases"] = inclusive
                except Exception:
                    pass
                html_output = _render_report(target, report, cfg_file, cfg)
            elif vendor == "fortigate":
                report = fortigate_parser.inspect_host(
                    cfg_text, target, service_filter=svc_filter, vdom=vdom or None
                )
                cfg = FTGConfig(cfg_text, vdom=vdom or None)
                html_output = _render_fortigate_report(target, report, cfg_file, cfg, vdom=vdom)
            else:
                return 400, {"error": f"Inspect not supported for vendor {vendor!r}"}
            history_query = target
            meta["query"] = target

        elif mode == "compare":
            if not caps.supports_compare:
                return 400, {"error": f"Compare not supported for vendor {vendor!r}"}
            old = get("old")
            new = get("new")
            if vendor == "asa":
                diff = asa_parser.compare_old_new(
                    cfg_text, old, new, service_filter=svc_filter, include_any=include_any
                )
                cfg = asa_parser.ASAConfig(cfg_text)

                def _incl(name: str) -> Dict[ipaddress._BaseAddress, Set[str]]:
                    out: Dict[ipaddress._BaseAddress, Set[str]] = {}
                    nets_inner = cfg.resolve_network(name)
                    for net in nets_inner:
                        names = cfg.ip_to_objects.get(net, set()) if hasattr(cfg, "ip_to_objects") else set()
                        if names:
                            out[net] = names
                    return out

                old_aliases = _incl(old) if old else {}
                new_aliases = _incl(new) if new else {}
                html_output = _render_diff(old, new, diff, cfg_file, cfg, old_aliases, new_aliases)
            elif vendor == "fortigate":
                diff = fortigate_parser.compare_old_new(
                    cfg_text, old, new, service_filter=svc_filter, vdom=vdom or None
                )
                cfg = FTGConfig(cfg_text, vdom=vdom or None)
                html_output = _render_fortigate_diff(old, new, diff, cfg_file, cfg, vdom=vdom)
            else:
                return 400, {"error": f"Compare not supported for vendor {vendor!r}"}
            history_query = f"{old}->{new}"
            meta["query"] = history_query

        elif mode == "find":
            if not caps.supports_find:
                return 400, {"error": f"Find not supported for vendor {vendor!r}"}
            target = get("findq")
            results = _find_host(state, target, vendor, vdom or None)
            html_output = _render_find(target, results, find_verbose)
            tab = "find"
            history_query = target
            meta["query"] = target
            meta["verbose"] = bool(find_verbose)

        elif mode == "packet":
            if not caps.supports_packet:
                return 400, {"error": f"Packet check not supported for vendor {vendor!r}"}
            src = get("pkt_src")
            dst = get("pkt_dst")
            guess_pairs = is_checked("pkt_guess", True)
            if vendor == "asa":
                pkt = _packet_check_asa(
                    cfg_text, src, dst, proto or None, dports_clean, include_any, guess_pairs
                )
            elif vendor == "fortigate":
                pkt = _packet_check_fortigate(
                    cfg_text, src, dst, proto or None, dports_clean, include_any, vdom or None
                )
                guess_pairs = False
            else:
                return 400, {"error": f"Packet check not supported for vendor {vendor!r}"}
            html_output = _render_packet(cfg_file, pkt, vendor=vendor)
            tab = "packet"
            history_query = f"{src}->{dst}"
            meta["query"] = history_query
            meta["guess_pairs"] = guess_pairs

        else:
            html_output = "<p style='color:red'>Unsupported mode.</p>"

    except Exception as exc:
        return 500, {"error": str(exc)}

    if history_query and not suppress_history:
        state.history.record(tab, history_query)

    return 200, {"tab": tab, "html": html_output, "meta": meta}


def _escape_text(value: str) -> str:
    return html.escape(html.unescape(value or ""))


def _escape_attr(value: str) -> str:
    return html.escape(html.unescape(value or ""), quote=True)


def _format_list(values: Iterable[str], limit: Optional[int] = None) -> str:
    seq = [str(v) for v in values if v]
    if not seq:
        return "-"
    if limit is not None and len(seq) > limit:
        head = ", ".join(seq[:limit])
        return f"{head} (+{len(seq) - limit} more)"
    return ", ".join(seq)


def _fmt(rule: dict) -> str:
    src_str = ", ".join(sorted(str(s) for s in rule["src"]))
    dst_str = ", ".join(sorted(str(s) for s in rule["dst"]))
    svc = rule.get("svc") or {}
    parts: List[str] = []
    if svc.get("proto"):
        parts.append(svc["proto"])
    if svc.get("service_group_at_proto"):
        sg = svc["service_group_at_proto"]
        parts.append(f"{sg['kind']}:{sg['name']}")
    port_parts: List[str] = []
    for op, (p1, p2) in svc.get("dst_ports", []):
        if op == "range":
            port_parts.append(f"{p1}-{p2}")
        else:
            port_parts.append(f"{op} {p1}")
    for group in svc.get("dst_service_groups", []) or []:
        port_parts.append(f"group:{group}")
    for obj in svc.get("dst_service_objects", []) or []:
        port_parts.append(f"object:{obj}")
    svc_str = ""
    if parts or port_parts:
        head = " ".join(parts) if parts else ""
        tail = (" ports=" + ",".join(port_parts)) if port_parts else ""
        svc_str = f" {head}{tail}".rstrip()
    bind_suffix = ""
    bind_desc = _format_binding(rule.get("binding"))
    if bind_desc:
        bind_suffix = f" bind={bind_desc}"
    proto = rule.get("proto")
    proto_part = f" {proto}" if proto else ""
    return f"{rule['action']}{proto_part}{svc_str} src=[{src_str}] dst=[{dst_str}]{bind_suffix}"


def _format_flat_rule(entry: dict) -> str:
    src_str = ", ".join(sorted(str(s) for s in entry.get("src", [])))
    dst_str = ", ".join(sorted(str(s) for s in entry.get("dst", [])))
    svc = entry.get("svc") or {}
    proto = svc.get("proto") or entry.get("proto")
    svc_parts: List[str] = []
    if proto:
        svc_parts.append(proto)
    if svc.get("service_group_at_proto"):
        sg = svc["service_group_at_proto"]
        svc_parts.append(f"{sg['kind']}:{sg['name']}")
    port_chunks: List[str] = []
    for op, (p1, p2) in svc.get("dst_ports", []):
        if op == "range":
            port_chunks.append(f"{p1}-{p2}")
        else:
            port_chunks.append(f"{op} {p1}")
    for name in sorted(svc.get("dst_service_groups") or []):
        port_chunks.append(f"group:{name}")
    for name in sorted(svc.get("dst_service_objects") or []):
        port_chunks.append(f"object:{name}")
    svc_str = ""
    if svc_parts or port_chunks:
        head = " ".join(svc_parts) if svc_parts else ""
        tail = (" ports=" + ",".join(port_chunks)) if port_chunks else ""
        svc_str = f" {head}{tail}".rstrip()
    binding = entry.get("binding") or {}
    src_if = ", ".join(binding.get("srcintf") or [])
    dst_if = ", ".join(binding.get("dstintf") or [])
    bind_desc = ""
    if src_if or dst_if:
        bind_desc = f" bind={src_if or 'any'}->{dst_if or 'any'}"
    return f"{entry.get('action', 'deny')}{svc_str} src=[{src_str}] dst=[{dst_str}]{bind_desc}"


def _format_binding(binding: Optional[Mapping[str, Any]]) -> str:
    if not binding or not isinstance(binding, Mapping):
        return ""
    interface = binding.get("interface")
    direction = binding.get("direction")
    scope = binding.get("scope")
    if interface:
        desc = str(interface)
        if direction:
            desc += f" ({direction})"
        return desc
    if scope:
        return str(scope)
    direction = direction or binding.get("scope")
    if direction:
        return str(direction)
    return ""


def _object_detail_block(
    cfg: asa_parser.ASAConfig,
    *,
    primary_names: Iterable[str],
    aliases: Mapping[Union[str, ipaddress.IPv4Address, ipaddress.IPv4Network], Iterable[str]],
    membership: Mapping[str, Set[str]],
    title: str,
) -> str:
    names: Set[str] = set()
    literal_tokens: Set[str] = set()
    primary_tokens: Set[str] = set()
    alias_lookup: Dict[str, List[Union[str, ipaddress.IPv4Address, ipaddress.IPv4Network]]] = defaultdict(list)
    object_lookup = {name.lower(): name for name in cfg.network_objects.keys()}
    group_lookup = {name.lower(): name for name in cfg.network_object_groups.keys()}
    for name in primary_names:
        if isinstance(name, str) and name:
            canon = object_lookup.get(name.lower(), name)
            names.add(canon)
            lower_name = name.lower()
            primary_tokens.add(lower_name)
            if _looks_like_address(name):
                literal_tokens.add(lower_name)
    for addr, group_names in aliases.items():
        literal_tokens.add(str(addr).lower())
        for value in group_names:
            if value:
                value_str = str(value)
                canon = object_lookup.get(value_str.lower(), value_str)
                names.add(canon)
                alias_lookup[canon.lower()].append(addr)
                primary_tokens.add(canon.lower())
    names_lower = {name.lower() for name in names}
    primary_tokens.update(names_lower)
    primary_tokens.update(literal_tokens)
    object_sections: List[List[str]] = []
    seen_names: Set[str] = set()
    object_cards: List[str] = []

    def format_object(name: str) -> List[str]:
        lines = [f"object network {name}"]
        for net in sorted(cfg.network_objects.get(name, []), key=lambda v: str(v)):
            if isinstance(net, ipaddress.IPv4Address):
                lines.append(f" host {net}")
            elif isinstance(net, ipaddress.IPv4Network):
                mask = net.netmask.exploded
                lines.append(f" network-object {net.network_address} {mask}")
        for literal in sorted(getattr(cfg, "network_object_literals", {}).get(name, set())):
            lines.append(f" {literal}")
        return lines

    def format_addr_line(addr: Union[str, ipaddress.IPv4Address, ipaddress.IPv4Network]) -> str:
        if isinstance(addr, ipaddress.IPv4Address):
            return f" host {addr}"
        if isinstance(addr, ipaddress.IPv4Network):
            mask = addr.netmask.exploded
            return f" network-object {addr.network_address} {mask}"
        return f" {addr}"

    def build_card(
        lines: List[str],
        *,
        variant: str,
        alias_key: Optional[str] = None,
        highlight_tokens: Optional[Set[str]] = None,
        extra_override: Optional[List[str]] = None,
    ) -> Optional[str]:
        cleaned = [line.rstrip() for line in lines if line is not None and line.rstrip()]
        if not cleaned:
            return None
        first_line = cleaned[0]
        second_line = ""
        highlight_tokens = highlight_tokens or set()
        highlight_line: Optional[str] = None
        extra_lines: List[str] = []
        if len(cleaned) > 1:
            candidates = cleaned[1:]
            for line in candidates:
                lower_line = line.lower()
                if any(token in lower_line for token in highlight_tokens):
                    highlight_line = line
                    break
            if not highlight_line:
                highlight_line = candidates[0]
            second_line = highlight_line
            if extra_override is not None:
                extra_lines = list(extra_override)
                if highlight_line in extra_lines:
                    extra_lines = [line for line in extra_lines if line != highlight_line]
            else:
                extra_lines = [line for line in candidates if line != highlight_line]
        elif alias_key:
            for addr in alias_lookup.get(alias_key, []):
                fallback = format_addr_line(addr)
                if fallback:
                    second_line = fallback
                    break
        if not second_line:
            return None
        row_attrs: List[str] = []
        aria_label = second_line.strip()
        extra_hint = ""
        if extra_lines:
            count_label = "members" if variant == "group" else "entries"
            extra_hint = f"(+{len(extra_lines)} more {count_label})"
            row_attrs.append(f"data-extra-label=\"{_escape_attr(extra_hint)}\"")
            aria_label = f"{aria_label} {extra_hint}".strip()
        if aria_label:
            row_attrs.append(f"aria-label=\"{_escape_attr(aria_label)}\"")
        row_attr_str = (" " + " ".join(row_attrs)) if row_attrs else ""
        highlight_class = " is-highlight" if variant == "object" or (highlight_line and any(token in highlight_line.lower() for token in highlight_tokens)) else ""
        extra_html = ""
        if extra_lines:
            count_label = "members" if variant == "group" else "entries"
            label_collapsed = f"Show {len(extra_lines)} more {count_label}"
            label_expanded = f"Hide {len(extra_lines)} {count_label}"
            extra_content = "".join(
                f"<div class='config-card-extra-line'><span class='config-card-text'>{_escape_text(line)}</span></div>"
                for line in extra_lines
            )
            collapsed_attr = _escape_attr(label_collapsed)
            expanded_attr = _escape_attr(label_expanded)
            extra_html = (
                "<details class='config-card-collapsible'>"
                f"<summary class='config-card-collapsible-summary' aria-label='{collapsed_attr}' "
                f"data-label-collapsed='{collapsed_attr}' data-label-expanded='{expanded_attr}'></summary>"
                f"<div class='config-card-extra'>{extra_content}</div>"
                "</details>"
            )
        return (
            f"<div class='config-card config-card--{variant}'>"
            f"<div class='config-card-row is-name'><span class='config-card-text'>{_escape_text(first_line)}</span></div>"
            f"<div class='config-card-row is-value{highlight_class}'{row_attr_str}><span class='config-card-text'>{_escape_text(second_line)}</span></div>"
            f"{extra_html}</div>"
        )

    for name in sorted(names, key=lambda v: v.lower()):
        lower = name.lower()
        if lower in seen_names:
            continue
        seen_names.add(lower)
        canonical = object_lookup.get(lower, name)
        if lower in object_lookup:
            formatted_object = format_object(canonical)
            object_sections.append(formatted_object)
            card = build_card(
                formatted_object,
                variant="object",
                alias_key=lower,
                highlight_tokens=primary_tokens,
            )
            if card:
                object_cards.append(card)

    group_names: Set[str] = set()
    for name in names:
        group_names.update(membership.get(name.lower(), set()))

    def format_group(group: str) -> Tuple[List[str], List[str]]:
        canonical_group = group_lookup.get(group.lower(), group)
        members = cfg.network_object_groups.get(canonical_group, [])
        primary_lines = [f"object-group network {canonical_group}"]
        extra_lines: List[str] = []

        def add_line(text: str, important: bool) -> None:
            target = primary_lines if important else extra_lines
            target.append(text)

        for member in members:
            if isinstance(member, dict):
                if "object" in member:
                    member_name = member["object"]
                    line = f" network-object object {member_name}"
                    important = member_name.lower() in names_lower or member_name.lower() in primary_tokens
                    add_line(line, important)
                elif "group-object" in member:
                    child = member["group-object"]
                    line = f" group-object {child}"
                    important = (
                        child.lower() in group_names
                        or child.lower() in names_lower
                        or child.lower() in primary_tokens
                    )
                    add_line(line, important)
            else:
                member_literal = str(member).lower()
                if isinstance(member, ipaddress.IPv4Address):
                    line = f" host {member}"
                elif isinstance(member, ipaddress.IPv4Network):
                    line = f" network-object {member.network_address} {member.netmask.exploded}"
                else:
                    line = f" {member}"
                add_line(line, member_literal in literal_tokens)
        for literal in sorted(getattr(cfg, "network_object_group_literals", {}).get(group, set())):
            literal_lower = literal.lower()
            add_line(f" {literal}", literal_lower in literal_tokens)
        if len(primary_lines) == 1 and extra_lines:
            primary_lines.append(extra_lines.pop(0))
        return primary_lines, extra_lines

    group_sections: List[List[str]] = []
    seen_groups: Set[str] = set()
    group_cards: List[str] = []
    for group in sorted(group_names):
        lower = group.lower()
        if lower in seen_groups:
            continue
        seen_groups.add(lower)
        formatted_primary, formatted_extra = format_group(group_lookup.get(lower, group))
        if formatted_primary:
            group_sections.append(formatted_primary + (formatted_extra if formatted_extra else []))
            card = build_card(
                formatted_primary,
                variant="group",
                highlight_tokens=primary_tokens,
                extra_override=formatted_extra,
            )
            if card:
                group_cards.append(card)

    alias_lines: List[str] = []
    if aliases:
        for addr, nameset in sorted(aliases.items(), key=lambda item: str(item[0])):
            alias_lines.append(f"{addr}: {', '.join(sorted(str(name) for name in nameset))}")

    sections: List[str] = []
    object_lines: List[str] = []
    if object_sections:
        sections.append("!!! OBJECTS")
        for idx, block in enumerate(object_sections):
            for line in block:
                object_lines.append(line.rstrip())
            if idx < len(object_sections) - 1:
                object_lines.append("!")
            object_lines.append("")
        sections.extend([line for line in object_lines if line is not None])
    if group_sections:
        sections.append("!!! GROUPS")
        for idx, block in enumerate(group_sections):
            for line in block:
                sections.append(line.rstrip())
            if idx < len(group_sections) - 1:
                sections.append("!")
            sections.append("")
    if alias_lines:
        sections.append("!!! RESOLVED ADDRESSES")
        sections.extend(alias_lines)
    text = "\n".join(line for line in sections if line is not None).strip()
    cards_sections: List[str] = []
    obj_count = len(object_cards)
    group_count = len(group_cards)
    if object_cards:
        cards_sections.append(
            "<div class='config-card-stack'>"
            "<div class='config-card-stack-title'>Objects</div>"
            f"<div class='config-card-grid'>{''.join(object_cards)}</div>"
            "</div>"
        )
    if group_cards:
        cards_sections.append(
            "<div class='config-card-stack'>"
            "<div class='config-card-stack-title'>Groups</div>"
            f"<div class='config-card-grid'>{''.join(group_cards)}</div>"
            "</div>"
        )
    cards_body = "".join(cards_sections)
    views: List[str] = []
    buttons: List[Tuple[str, str, bool]] = []
    if cards_body:
        label = "Summary"
        counts: List[str] = []
        if obj_count:
            counts.append(f"{obj_count} object{'s' if obj_count != 1 else ''}")
        if group_count:
            counts.append(f"{group_count} group{'s' if group_count != 1 else ''}")
        if counts:
            label = f"{label} ({', '.join(counts)})"
        views.append(
            "<div class='config-summary-view is-active' data-view='cards'>"
            f"<div class='config-card-area'>{cards_body}</div>"
            "</div>"
        )
        buttons.append(("cards", label, True))
    if text:
        detail_text = _escape_text(text)
        active_flag = "" if views else " is-active"
        views.append(
            f"<div class='config-summary-view{active_flag}' data-view='config'>"
            f"<pre data-lang='asa'>{detail_text}</pre>"
            "</div>"
        )
        buttons.append(("config", "Config view", not cards_body))
    if not views:
        return ""
    buttons.append(("hide", "Hide", False))
    toggle_html = ""
    buttons_html = "".join(
        f"<button type='button' class='config-summary-btn{' is-active' if is_active else ''}' "
        f"data-target='{target}'>{_escape_text(label)}</button>"
        for target, label, is_active in buttons
    )
    toggle_html = (
        "<div class='config-summary-toggle' role='group' aria-label='Result view'>"
        f"{buttons_html}</div>"
    )
    return (
        f"<div class='diff diff-objects'><h3>{_escape_text(title)}</h3>"
        f"{toggle_html}"
        "<div class='config-summary'>"
        f"{''.join(views)}"
        "</div></div>"
    )


def _looks_like_address(value: str) -> bool:
    value = value.strip()
    if not value:
        return False
    try:
        ipaddress.ip_address(value)
        return True
    except Exception:
        try:
            ipaddress.ip_network(value, strict=False)
            return True
        except Exception:
            return False


def _fortigate_group_membership(cfg: FTGConfig) -> Dict[str, Set[str]]:
    membership: Dict[str, Set[str]] = defaultdict(set)
    group_lookup = {name.lower(): name for name in cfg.addrgrps.keys()}

    def canonical(name: str) -> Optional[str]:
        if not name:
            return None
        lower = name.lower()
        if lower in group_lookup:
            return group_lookup[lower]
        return name if name in cfg.addrgrps else None

    def visit(group_name: str, chain: Set[str]) -> None:
        actual = canonical(group_name)
        if not actual:
            return
        lower = actual.lower()
        if lower in chain:
            return
        next_chain = set(chain)
        next_chain.add(lower)
        members = cfg.addrgrps.get(actual, [])
        for member in members:
            if isinstance(member, dict) and "object" in member:
                target = member["object"]
                membership[target.lower()].add(actual)
                if target.lower() in group_lookup:
                    membership[target.lower()].add(actual)
                    visit(target, next_chain)
            else:
                membership[str(member).lower()].add(actual)

    for group in cfg.addrgrps.keys():
        visit(group, set())
    return membership


def _fortigate_vip_group_membership(cfg: FTGConfig) -> Dict[str, Set[str]]:
    membership: Dict[str, Set[str]] = defaultdict(set)
    for group, members in cfg.vipgrps.items():
        for member in members:
            if member:
                membership[member.lower()].add(group)
    return membership


def _format_ftg_literal(value: Union[str, ipaddress._BaseAddress, ipaddress._BaseNetwork]) -> str:
    if isinstance(value, (ipaddress.IPv4Address, ipaddress.IPv4Network)):
        return str(value)
    return str(value)


def _fortigate_add_literal(
    name: str,
    literal: str,
    literal_map: Dict[str, Set[str]],
    label_map: Dict[str, str],
) -> None:
    if not name or not literal:
        return
    key = name.lower()
    literal_map.setdefault(key, set()).add(literal)
    label_map.setdefault(key, name)


def _fortigate_literal_maps_from_report(
    target: str,
    target_nets: Iterable[Union[ipaddress._BaseAddress, ipaddress._BaseNetwork, str]],
    aliases: Optional[Mapping[Union[ipaddress._BaseAddress, ipaddress._BaseNetwork], Iterable[str]]],
) -> Tuple[Dict[str, Set[str]], Dict[str, str]]:
    literal_map: Dict[str, Set[str]] = defaultdict(set)
    label_map: Dict[str, str] = {}
    if target:
        label_map[target.lower()] = target
    for net in target_nets:
        literal = _format_ftg_literal(net)
        if target:
            _fortigate_add_literal(target, literal, literal_map, label_map)
    if aliases:
        for net, names in aliases.items():
            literal = _format_ftg_literal(net)
            for name in names:
                _fortigate_add_literal(name, literal, literal_map, label_map)
    return literal_map, label_map


def _fortigate_literal_maps_for_target(cfg: FTGConfig, target: str) -> Tuple[Dict[str, Set[str]], Dict[str, str]]:
    literal_map: Dict[str, Set[str]] = defaultdict(set)
    label_map: Dict[str, str] = {}
    if target:
        label_map[target.lower()] = target
    try:
        resolved = cfg.resolve_addr_token(target)
    except Exception:
        resolved = set()
    for item in resolved:
        literal = _format_ftg_literal(item)
        if target:
            _fortigate_add_literal(target, literal, literal_map, label_map)
        if isinstance(item, (ipaddress.IPv4Address, ipaddress.IPv4Network)):
            for alias in cfg.ip_to_objects.get(item, set()):
                _fortigate_add_literal(alias, literal, literal_map, label_map)
    return literal_map, label_map


def _fortigate_describe_vip(cfg: FTGConfig, name: str) -> str:
    vip = cfg.vips.get(name)
    if vip:
        ext = vip.get("extip")
        mapped = vip.get("mappedip")
        ext_text = ", ".join(ext) if isinstance(ext, list) else str(ext or "")
        mapped_text = ", ".join(mapped) if isinstance(mapped, list) else str(mapped or "")
        if ext_text and mapped_text:
            suffix = f"{ext_text} -> {mapped_text}"
        else:
            suffix = ext_text or mapped_text or ""
        iface = vip.get("extintf")
        if iface:
            suffix = f"{suffix} ({iface})" if suffix else iface
        return suffix
    members = cfg.vipgrps.get(name)
    if members:
        if len(members) <= 4:
            return f"group members: {', '.join(members)}"
        head = ", ".join(members[:4])
        return f"group members: {head} (+{len(members) - 4} more)"
    return ""


def _fortigate_render_card(rows: List[Tuple[str, str]]) -> str:
    if not rows:
        return ""
    body = "".join(
        f"<div class='config-card-row {row_class}'><span class='config-card-text'>{_escape_text(text)}</span></div>"
        for row_class, text in rows
        if text
    )
    return f"<div class='config-card'>{body}</div>"


def _fortigate_object_detail_block(
    cfg: FTGConfig,
    *,
    primary_names: Iterable[str],
    literal_map: Dict[str, Set[str]],
    label_map: Dict[str, str],
    membership: Dict[str, Set[str]],
    vip_membership: Dict[str, Set[str]],
    title: str,
) -> str:
    addr_lookup = {name.lower(): name for name in cfg.addresses.keys()}
    group_lookup = {name.lower(): name for name in cfg.addrgrps.keys()}
    vip_lookup = {name.lower(): name for name in cfg.vips.keys()}
    vipgrp_lookup = {name.lower(): name for name in cfg.vipgrps.keys()}

    def canonical(name: str) -> Tuple[str, str]:
        lower = name.lower()
        if lower in addr_lookup:
            return lower, addr_lookup[lower]
        if lower in group_lookup:
            return lower, group_lookup[lower]
        if lower in vip_lookup:
            return lower, vip_lookup[lower]
        if lower in vipgrp_lookup:
            return lower, vipgrp_lookup[lower]
        return lower, label_map.get(lower, name)

    ordered_keys: List[str] = []
    seen: Set[str] = set()
    for name in primary_names:
        if not name:
            continue
        key, label = canonical(name)
        if key not in label_map:
            label_map[key] = label
        if key not in seen:
            ordered_keys.append(key)
            seen.add(key)
    for key in list(label_map.keys()):
        if key not in seen:
            ordered_keys.append(key)
            seen.add(key)
    for key in list(ordered_keys):
        for group in membership.get(key, set()):
            group_key = group.lower()
            if group_key not in label_map:
                label_map[group_key] = group
            if group_key not in seen:
                ordered_keys.append(group_key)
                seen.add(group_key)
        for vip_group in vip_membership.get(key, set()):
            vg_key = vip_group.lower()
            if vg_key not in label_map:
                label_map[vg_key] = vip_group
            if vg_key not in seen:
                ordered_keys.append(vg_key)
                seen.add(vg_key)

    cards: List[str] = []
    for key in ordered_keys:
        label = label_map.get(key)
        if not label:
            continue
        literal_values = sorted(literal_map.get(key, set()))
        rows: List[Tuple[str, str]] = []
        if key in addr_lookup:
            rows.append(("is-name", f"firewall address {addr_lookup[key]}"))
            literals = literal_values or [str(net) for net in sorted(cfg.addresses.get(addr_lookup[key], []), key=str)]
            value = ", ".join(literals) if literals else "(no subnet)"
            rows.append(("is-value", value))
            groups = sorted(membership.get(key, set()))
            if groups:
                rows.append(("is-meta", f"Groups: {', '.join(groups)}"))
        elif key in group_lookup:
            rows.append(("is-name", f"firewall addrgrp {group_lookup[key]}"))
            members = []
            for member in cfg.addrgrps.get(group_lookup[key], []):
                if isinstance(member, dict) and "object" in member:
                    members.append(member["object"])
                else:
                    members.append(str(member))
            if members:
                head = ", ".join(members[:4])
                suffix = f" (+{len(members) - 4} more)" if len(members) > 4 else ""
                rows.append(("is-value", f"Members: {head}{suffix}"))
            if literal_values:
                rows.append(("is-meta", f"Resolves: {', '.join(literal_values)}"))
        elif key in vip_lookup:
            rows.append(("is-name", f"firewall vip {vip_lookup[key]}"))
            rows.append(("is-value", _fortigate_describe_vip(cfg, vip_lookup[key]) or "(no mapping)"))
            policies = sorted(cfg.policy_vip_refs.get(vip_lookup[key], set()))
            if policies:
                rows.append(("is-meta", f"Policies: {', '.join(policies)}"))
            groups = sorted(vip_membership.get(key, set()))
            if groups:
                rows.append(("is-meta", f"VIP groups: {', '.join(groups)}"))
        elif key in vipgrp_lookup:
            rows.append(("is-name", f"firewall vipgrp {vipgrp_lookup[key]}"))
            members = cfg.vipgrps.get(vipgrp_lookup[key], [])
            if members:
                head = ", ".join(members[:4])
                suffix = f" (+{len(members) - 4} more)" if len(members) > 4 else ""
                rows.append(("is-value", f"Members: {head}{suffix}"))
        else:
            rows.append(("is-name", label))
            rows.append(("is-value", ", ".join(literal_values) if literal_values else label))
        card = _fortigate_render_card(rows)
        if card:
            cards.append(card)
    if not cards:
        return ""
    body = "".join(cards)
    return f"<div class='diff diff-objects'><h3>{_escape_text(title)}</h3><div class='config-cards'>{body}</div></div>"


def _fortigate_zone_summary(title: str, hits: Iterable[dict]) -> str:
    entries: List[str] = []
    seen: Set[Tuple[str, str, str]] = set()

    def _value(binding: Mapping[str, Any], zone_key: str, iface_key: str) -> str:
        zone = binding.get(zone_key)
        if zone:
            vals = zone if isinstance(zone, list) else [zone]
            return ", ".join(vals)
        iface = binding.get(iface_key)
        if iface:
            vals = iface if isinstance(iface, list) else [iface]
            return ", ".join(vals)
        return "any"

    for entry in hits:
        binding = entry.get("binding") or {}
        src = _value(binding, "srczone", "srcintf")
        dst = _value(binding, "dstzone", "dstintf")
        policy_label = entry.get("policy_id") or binding.get("name") or binding.get("uuid") or ""
        key = (policy_label, src, dst)
        if key in seen:
            continue
        seen.add(key)
        label = f"Policy {policy_label}" if policy_label else "Policy"
        entries.append(f"{label}: {src} -> {dst}")
    if not entries:
        return ""
    text = "\n".join(entries)
    return f"<div class='diff diff-objects'><h3>{_escape_text(title)}</h3><pre data-lang='fortigate'>{_escape_text(text)}</pre></div>"


def _fortigate_vip_reference_block(cfg: FTGConfig, hits: Iterable[dict], title: str) -> str:
    lines: List[str] = []
    seen: Set[Tuple[str, str]] = set()
    for entry in hits:
        binding = entry.get("binding") or {}
        vip_refs = binding.get("vip_refs") or []
        if not vip_refs:
            continue
        policy_label = entry.get("policy_id") or binding.get("name") or binding.get("uuid") or ""
        for vip_name in vip_refs:
            key = (policy_label, vip_name)
            if key in seen:
                continue
            seen.add(key)
            desc = _fortigate_describe_vip(cfg, vip_name)
            label = f"Policy {policy_label}" if policy_label else "Policy"
            line = f"{label} -> {vip_name}"
            if desc:
                line += f": {desc}"
            lines.append(line)
    if not lines:
        return ""
    text = "\n".join(lines)
    return f"<div class='diff diff-objects'><h3>{_escape_text(title)}</h3><pre data-lang='fortigate'>{_escape_text(text)}</pre></div>"


def _render_report(target: str, report: dict, cfg_file: str, cfg: asa_parser.ASAConfig) -> str:
    raw_entries = report.get("hits", [])
    raw_text = "\n".join(entry["raw"] for entry in raw_entries)
    raw_numbers = ",".join(str(entry.get("line") or "") for entry in raw_entries)
    match_numbers = ",".join(str(entry.get("line")) for entry in raw_entries if entry.get("line"))
    lines_flat = "\n".join(_fmt(entry) for entry in raw_entries)
    aliases = report.get("aliases") or {}
    membership = _build_group_membership(cfg)
    group_lookup = {name.lower(): name for name in cfg.network_object_groups.keys()}
    target_groups = {
        group_lookup[key.lower()]
        for key in membership.get(target.lower(), set())
        if key.lower() in group_lookup
    }
    allow_group_rules: Dict[str, Set[str]] = defaultdict(set)
    if target_groups:
        for entry in raw_entries:
            if entry.get("action") != "permit":
                continue
            raw_line = entry.get("raw") or ""
            raw_lower = raw_line.lower()
            for group_name in target_groups:
                if group_name.lower() in raw_lower:
                    allow_group_rules[group_name].add(raw_line)
    allow_block = ""
    if allow_group_rules:
        lines: List[str] = ["! Object groups permitting target"]
        for group_name in sorted(allow_group_rules):
            lines.append(f"object-group {group_name}")
            for rule in sorted(allow_group_rules[group_name]):
                lines.append(f"  {rule}")
            lines.append("")
        text = "\n".join(line.rstrip() for line in lines if line is not None).strip()
        allow_block = (
            f"<div class='diff diff-objects'><h3>ACL permit rules via matching object-groups</h3>"
            f"<pre data-lang='asa'>{_escape_text(text)}</pre></div>"
        )
    object_block = _object_detail_block(
        cfg,
        primary_names=[target],
        aliases=aliases,
        membership=membership,
        title="Object names and group memberships",
    )
    return f"""
<div class='results results-rules' data-tab='rules'>
  <div class='section'><h2>{_escape_text(cfg_file)}</h2><h3>Inspection Report for {_escape_text(target)}</h3>
  <p>Resolved to: {', '.join(_escape_text(str(net)) for net in report.get('target_nets', []))}</p>
  <p>Found {len(report.get('hits', []))} matching ACL entries.</p></div>
  {object_block or ""}
  {allow_block or ""}
  <div class='diff diff-ruleset'>
    <h3>Matched Rules</h3>
    <div class='config-summary-toggle acl-view-toggle' role='group' aria-label='Matched rules view'>
      <button type='button' class='config-summary-btn acl-view-btn' data-target='raw'>Raw access-lists</button>
      <button type='button' class='config-summary-btn acl-view-btn' data-target='flat'>Flattened access-lists</button>
      <button type='button' class='config-summary-btn acl-view-btn is-active' data-target='both'>Both</button>
      <button type='button' class='config-summary-btn acl-view-btn' data-target='hide'>Hide</button>
    </div>
    <div class='acl-view-container' data-mode='both'>
      <div class='acl-view acl-view--raw is-active' data-view='raw'>
        <h4>Raw access-lists</h4>
        <pre data-lang='asa' data-line-numbers='{_escape_text(raw_numbers)}' data-match-lines='{_escape_text(match_numbers)}'>{_escape_text(raw_text)}</pre>
      </div>
      <div class='acl-view acl-view--flat is-active' data-view='flat'>
        <h4>Flattened access-lists</h4>
        <pre data-lang='asa'>{_escape_text(lines_flat)}</pre>
      </div>
    </div>
  </div>
</div>
"""

def _render_fortigate_report(target: str, report: dict, cfg_file: str, cfg: FTGConfig, vdom: Optional[str] = None) -> str:
    hits = report.get("hits", [])
    raw_block = "\n".join(entry.get("raw", "") for entry in hits)
    flat_block = "\n".join(_format_flat_rule(entry) for entry in hits)
    aliases = report.get("aliases") or {}
    target_nets = report.get("target_nets", [])
    cfg.flatten_policies()
    literal_map, label_map = _fortigate_literal_maps_from_report(target, target_nets, aliases)
    membership = _fortigate_group_membership(cfg)
    vip_membership = _fortigate_vip_group_membership(cfg)
    object_block = _fortigate_object_detail_block(
        cfg,
        primary_names=[target],
        literal_map=literal_map,
        label_map=label_map,
        membership=membership,
        vip_membership=vip_membership,
        title="Object context",
    )
    zone_block = _fortigate_zone_summary("Zone context", hits)
    vip_block = _fortigate_vip_reference_block(cfg, hits, "VIP references")
    vdom_suffix = f" (VDOM={_escape_text(vdom)})" if vdom else ""
    return f"""
<div class='results results-rules' data-tab='rules'>
  <div class='section'><h2>{_escape_text(cfg_file)}</h2><h3>Inspection Report for {_escape_text(target)}{vdom_suffix}</h3>
  <p>Resolved to: {', '.join(_escape_text(str(net)) for net in report.get('target_nets', []))}</p>
  <p>Found {len(hits)} matching policies.</p></div>
  {object_block or ""}
  {vip_block or ""}
  {zone_block or ""}
  <div class='diff diff-ruleset'>
    <h3>Matched Policies</h3>
    <div class='acl-view-container' data-mode='both'>
      <div class='acl-view acl-view--raw is-active' data-view='raw'>
        <h4>Raw policies</h4>
        <pre data-lang='fortigate'>{_escape_text(raw_block or '  (none)')}</pre>
      </div>
      <div class='acl-view acl-view--flat is-active' data-view='flat'>
        <h4>Flattened policies</h4>
        <pre data-lang='fortigate'>{_escape_text(flat_block or '  (none)')}</pre>
      </div>
    </div>
  </div>
</div>
"""


def _render_diff(
    old: str,
    new: str,
    diff: dict,
    cfg_file: str,
    cfg: asa_parser.ASAConfig,
    old_aliases: Optional[Mapping[Union[str, ipaddress.IPv4Address, ipaddress.IPv4Network], Iterable[str]]] = None,
    new_aliases: Optional[Mapping[Union[str, ipaddress.IPv4Address, ipaddress.IPv4Network], Iterable[str]]] = None,
) -> str:
    added = "\n".join(f" + {entry['raw']}\n   -> {_fmt(entry)}" for entry in diff.get("added_to_new", [])[:200])
    removed = "\n".join(f" - {entry['raw']}\n   -> {_fmt(entry)}" for entry in diff.get("removed_from_old", [])[:200])
    membership = _build_group_membership(cfg)
    old_block = _object_detail_block(
        cfg,
        primary_names=[old],
        aliases=old_aliases or {},
        membership=membership,
        title="Old object names and group memberships",
    )
    new_block = _object_detail_block(
        cfg,
        primary_names=[new],
        aliases=new_aliases or {},
        membership=membership,
        title="New object names and group memberships",
    )

    return f"""
<div class='results results-rules' data-tab='rules'>
  <div class='section'><h2>{_escape_text(cfg_file)}</h2><h3>Comparison</h3>
  <p>Old target: {_escape_text(old)}</p>
  <p>New target: {_escape_text(new)}</p>
  <p>Old hits: {len(diff.get('old_hits', []))} &nbsp; New hits: {len(diff.get('new_hits', []))}</p>
  </div>
  {old_block or ""}
  {new_block or ""}
  <div class='diff diff-added'><h3>New-only Rules</h3>
  <pre data-lang='asa'>{_escape_text(added or '  (none)')}</pre></div>
  <div class='diff diff-removed'><h3>Old-only Rules</h3>
  <pre data-lang='asa'>{_escape_text(removed or '  (none)')}</pre></div>
</div>
"""


def _render_fortigate_diff(
    old: str,
    new: str,
    diff: dict,
    cfg_file: str,
    cfg: FTGConfig,
    vdom: Optional[str] = None,
) -> str:
    added = "\n".join(_format_flat_rule(entry) for entry in diff.get("added_to_new", [])[:200])
    removed = "\n".join(_format_flat_rule(entry) for entry in diff.get("removed_from_old", [])[:200])
    cfg.flatten_policies()
    membership = _fortigate_group_membership(cfg)
    vip_membership = _fortigate_vip_group_membership(cfg)
    old_literal_map, old_labels = _fortigate_literal_maps_for_target(cfg, old)
    new_literal_map, new_labels = _fortigate_literal_maps_for_target(cfg, new)
    old_block = _fortigate_object_detail_block(
        cfg,
        primary_names=[old],
        literal_map=old_literal_map,
        label_map=old_labels,
        membership=membership,
        vip_membership=vip_membership,
        title="Old object context",
    )
    new_block = _fortigate_object_detail_block(
        cfg,
        primary_names=[new],
        literal_map=new_literal_map,
        label_map=new_labels,
        membership=membership,
        vip_membership=vip_membership,
        title="New object context",
    )
    old_zone = _fortigate_zone_summary("Old target zones", diff.get("old_hits", []))
    new_zone = _fortigate_zone_summary("New target zones", diff.get("new_hits", []))
    old_vip = _fortigate_vip_reference_block(cfg, diff.get("old_hits", []), "Old target VIP references")
    new_vip = _fortigate_vip_reference_block(cfg, diff.get("new_hits", []), "New target VIP references")
    vdom_suffix = f" (VDOM={_escape_text(vdom)})" if vdom else ""
    return f"""
<div class='results results-rules' data-tab='rules'>
  <div class='section'><h2>{_escape_text(cfg_file)}</h2><h3>Comparison{vdom_suffix}</h3>
  <p>Old target: {_escape_text(old)}</p>
  <p>New target: {_escape_text(new)}</p>
  <p>Old hits: {len(diff.get('old_hits', []))} &nbsp; New hits: {len(diff.get('new_hits', []))}</p>
  </div>
  {old_block or ""}
  {new_block or ""}
  {old_vip or ""}
  {new_vip or ""}
  {old_zone or ""}
  {new_zone or ""}
  <div class='diff diff-added'><h3>New-only Policies</h3>
  <pre data-lang='fortigate'>{_escape_text(added or '  (none)')}</pre></div>
  <div class='diff diff-removed'><h3>Old-only Policies</h3>
  <pre data-lang='fortigate'>{_escape_text(removed or '  (none)')}</pre></div>
</div>
"""


def _render_find(target: str, results: List[dict], verbose: bool) -> str:
    filtered = [res for res in results if verbose or res.get("has_detail")]
    if not filtered:
        return """
<div class='results results-find' data-tab='find'>
  <div class='section'><h3>No results</h3></div>
</div>
"""

    limit = None if verbose else 6
    primary = filtered[0]
    primary_file = _escape_text(primary["file"])
    primary_vendor = _escape_text(primary["vendor"])
    primary_vdom = _escape_text(primary.get("vdom") or "")
    target_safe = _escape_text(target)

    def _render_lines(result: dict) -> str:
        file_label = _escape_text(result["file"])
        vendor_label = _escape_text(result["vendor"].upper())
        header = f"File: {file_label} ({vendor_label})"
        if result.get("best"):
            header += " <span class='badge owner'>Likely owner</span>"
        lines: List[str] = [header]
        if result.get("direct"):
            lines.append(_escape_text("Direct object match"))
        if result.get("objects"):
            lines.append(_escape_text("Objects: " + _format_list(result["objects"], limit)))
        if result.get("groups"):
            lines.append(_escape_text("Groups: " + _format_list(result["groups"], limit)))
        if result.get("interfaces"):
            lines.append(_escape_text("Interfaces: " + _format_list(result["interfaces"], limit)))
        if verbose:
            if result.get("literals"):
                lines.append(_escape_text("Literals: " + _format_list(result["literals"], None)))
            if result.get("score_details"):
                lines.append(_escape_text("Score detail: " + ", ".join(result["score_details"])))
            lines.append(_escape_text(f"Score: {result['score']}"))
            if result.get("text_hit") and not result.get("has_detail"):
                lines.append(_escape_text("Config text contains query"))
        elif result.get("text_hit") and not result.get("has_detail"):
            lines.append(_escape_text("Config text contains query"))
        return "\n".join(lines)

    primary_block = _render_lines(primary)

    jump_button = (
        "<div class='find-actions'>"
        f"<button type='button' class='btn-secondary js-find-to-packet' data-config='{primary_file}' "
        f"data-vendor='{primary_vendor}' data-vdom='{primary_vdom}' data-target='{target_safe}'>Send to Packet Check</button>"
        "</div>"
    )

    other_blocks: List[str] = []
    for result in filtered[1:50]:
        other_blocks.append(_render_lines(result))

    return (
        "<div class='results results-find' data-tab='find'>"
        "<div class='section find-primary'><h3>Likely Owner</h3>"
        f"{jump_button}"
        f"<pre>{primary_block}</pre></div>"
        + (
            "<div class='section find-secondary'><h3>Other Matches</h3><pre>"
            + "\n\n".join(other_blocks)
            + "</pre></div>"
            if other_blocks
            else ""
        )
        + "</div>"
    )


def _as_str_list(value) -> list:
    """Coerce a suggestion field to a list of strings.

    ``commands``/``notes`` are normally lists, but a malformed suggestion node
    may carry a bare string (which would iterate character-by-character) or
    ``None``. Normalise both to a clean list.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


def _render_packet_suggestion(suggestion: dict, vendor: str = "asa") -> str:
    """Render the path-check correction `suggestion` node as an HTML block.

    Consumes the payload as-is (see parsers/suggest.py); only shown when the
    flow is blocked (``needed`` is true). Commands live in selectable ``<pre>``
    blocks; live-verification commands sit behind a collapsed ``<details>``
    toggle (mirrors the CLI ``--verify`` flag).
    """
    if not suggestion or not suggestion.get("needed"):
        return ""
    reason = (suggestion.get("reason") or "deny").replace("-", " ").title()
    parts = [
        "  <div class='section suggestion'>"
        f"<h3>Correction Suggestion ({_escape_text(reason)})</h3>\n"
    ]
    blocking = suggestion.get("blocking_rule") or {}
    if blocking.get("raw"):
        parts.append(
            f"  <p class='blocking-rule'>Blocked by: "
            f"<code>{_escape_text(blocking.get('raw'))}</code></p>\n"
        )
    # `location` (nameif/srcintf/etc.) is intentionally not rendered here — the
    # generated command already embeds it; keeping the block concise.
    for sug in suggestion.get("suggestions", []):
        scenario = (sug.get("scenario") or "").upper()
        rationale = sug.get("rationale") or ""
        cmds = "\n".join(_as_str_list(sug.get("commands")))
        parts.append(
            "  <div class='diff diff-added'>"
            f"<h4>[{_escape_text(scenario)}] {_escape_text(rationale)}</h4>\n"
            f"  <pre data-lang='{_escape_attr(vendor)}'>{_escape_text(cmds)}</pre>\n"
        )
        notes = _as_str_list(sug.get("notes"))
        if notes:
            items = "".join(f"<li>{_escape_text(n)}</li>" for n in notes)
            parts.append(f"  <ul class='notes'>{items}</ul>\n")
        parts.append("  </div>\n")
    verifications = suggestion.get("verification") or []
    if verifications:
        ver_parts = [
            "  <details class='verify'><summary>Live verification commands</summary>\n"
        ]
        for ver in verifications:
            desc = ver.get("description") or ""
            cmd = ver.get("command") or ""
            if desc:
                ver_parts.append(f"  <p>{_escape_text(desc)}</p>\n")
            ver_parts.append(
                f"  <pre data-lang='{_escape_attr(vendor)}'>{_escape_text(cmd)}</pre>\n"
            )
        ver_parts.append("  </details>\n")
        parts.append("".join(ver_parts))
    parts.append("  </div>\n")
    return "".join(parts)


def _render_packet(cfg_file: str, pkt: dict, vendor: str = "asa") -> str:
    if pkt.get("error"):
        return (
            "<div class='results results-packet' data-tab='packet'>"
            f"<div class='section'><h2>{_escape_text(cfg_file)}</h2><h3>Packet Check</h3>"
            f"<p style='color:red'>Error: {_escape_text(pkt.get('error'))}</p></div></div>"
        )
    status = "ALLOWED" if pkt.get("allowed") else "BLOCKED"
    inp = pkt.get("input", {})
    resolved = pkt.get("resolved", {})
    nat = pkt.get("nat", {})
    acl = pkt.get("acl", {})
    context = pkt.get("context", {})
    matches = acl.get("matches", [])
    lines = []
    for item in matches[:200]:
        summary = item.get("summary") or ""
        inferred_suffix = " (inferred)" if item.get("inferred") else ""
        lines.append(f"  {item.get('raw')}{inferred_suffix}\n   → {summary}")
    content = "\n".join(lines) if lines else "  (no ACL matches)"
    nat_trans = nat.get("translations", {})
    src_nat = nat_trans.get("src", {})
    dst_nat = nat_trans.get("dst", {})
    nat_lines = []
    if nat.get("applied"):
        rule = nat.get("rule") or {}
        rule_desc = (
            rule.get("raw")
            or rule.get("name")
            or rule.get("policy_name")
            or rule.get("type")
            or "unknown"
        )
        nat_lines.append(f"Rule: {rule_desc}")
        nat_lines.append(f"Source: {src_nat.get('before')} → {src_nat.get('after')}")
        if src_nat.get("note"):
            nat_lines.append(f"  note: {src_nat.get('note')}")
        if dst_nat.get("after") and dst_nat.get("after") != dst_nat.get("before"):
            nat_lines.append(f"Destination: {dst_nat.get('before')} → {dst_nat.get('after')}")
            if dst_nat.get("note"):
                nat_lines.append(f"  note: {dst_nat.get('note')}")
    else:
        nat_lines.append("No NAT rule matched.")
    nat_block = "\n".join(nat_lines)
    step_block = ""
    steps = nat.get("steps") or []
    if steps:
        rendered_steps: List[str] = []
        for idx, step in enumerate(steps, start=1):
            desc = step.get("type", "nat")
            direction = step.get("direction") or "n/a"
            detail = step.get("rule") or {}
            summary = detail.get("raw") or detail.get("name") or detail.get("policy_name") or detail.get("type") or ""
            rendered_steps.append(f"Step {idx}: {desc} (direction={direction}) {summary}")
        step_block = (
            "  <div class='diff diff-steps'><h3>NAT Steps</h3>\n"
            f"  <pre>{_escape_text(chr(10).join(rendered_steps))}</pre></div>\n"
        )
    cand_lines = []
    for cand in context.get("acl_candidates", []):
        iface = cand.get("interface") or "global"
        direction = cand.get("direction") or "*"
        cand_lines.append(f"  {iface} ({direction})")
    candidate_block = ""
    if cand_lines:
        cand_text = "\n".join(cand_lines)
        candidate_block = (
            "  <div class='diff diff-aliases'><h3>ACL Candidate Bindings</h3>\n"
            f"  <pre>{_escape_text(cand_text)}</pre></div>\n"
        )
    warnings = (pkt.get("acl") or {}).get("warnings") or []
    warning_block = ""
    if warnings:
        items = "".join(f"<li>{_escape_text(w)}</li>" for w in warnings)
        warning_block = (
            "  <div class='section warnings'><h3>Warnings</h3>\n"
            f"  <ul>{items}</ul></div>\n"
        )
    return (
        "<div class='results results-packet' data-tab='packet'>\n"
        f"  <div class='section'><h2>{_escape_text(cfg_file)}</h2><h3>Packet Check</h3>\n"
        f"  <p>Status: {status} (NAT direction: {_escape_text(str(nat.get('direction') or 'n/a'))})</p>\n"
        f"  <p>Input: src={_escape_text(inp.get('src', ''))} dst={_escape_text(inp.get('dst', ''))} "
        f"proto={_escape_text(inp.get('proto') or 'any')} dports={_escape_text(str(inp.get('dports') or 'any'))}</p>\n"
        f"  <p>Resolved: src={_escape_text(str(resolved.get('src')))} → {_escape_text(str(resolved.get('post_nat_src')))} | "
        f"dst={_escape_text(str(resolved.get('dst')))} → {_escape_text(str(resolved.get('post_nat_dst')))}</p></div>\n"
        "  <div class='diff diff-added'><h3>NAT Evaluation</h3>\n"
        f"  <pre>{_escape_text(nat_block)}</pre></div>\n"
        f"{candidate_block}"
        f"{step_block}"
        f"{warning_block}"
        "  <div class='diff diff-raw'><h3>ACL Matches</h3>\n"
        f"  <pre data-lang='{_escape_text(vendor)}'>{_escape_text(content)}</pre></div>\n"
        f"{_render_packet_suggestion(pkt.get('suggestion') or {}, vendor)}"
        "</div>\n"
    )


def _packet_check_asa(
    cfg_text: str,
    src: str,
    dst: str,
    proto: Optional[str],
    dports: Set[int],
    include_any: bool,
    guess_pairs: bool,
) -> dict:
    try:
        return asa_parser.path_check(
            cfg_text,
            src,
            dst,
            proto=proto,
            dports=dports,
            include_any=include_any,
            guess_interface_pairs=guess_pairs,
        )
    except Exception as exc:
        return {"error": str(exc), "allowed": False}


def _packet_check_fortigate(
    cfg_text: str,
    src: str,
    dst: str,
    proto: Optional[str],
    dports: Set[int],
    include_any: bool,
    vdom: Optional[str],
) -> dict:
    try:
        return fortigate_path(
            cfg_text,
            src,
            dst,
            proto=proto,
            dports=dports,
            include_any=include_any,
            vdom=vdom,
        )
    except Exception as exc:
        return {"error": str(exc), "allowed": False}


def _find_host(state: AppState, target: str, vendor: str = "asa", vdom: Optional[str] = None) -> List[dict]:
    if vendor == "fortigate":
        return _find_host_fortigate(state, target, vdom)
    return _find_host_asa(state, target)


def _find_host_asa(state: AppState, target: str) -> List[dict]:
    query = (target or "").strip()
    if not query:
        return []
    data = _load_asa_configs(state)
    if not data:
        return []
    query_lower = query.lower()
    names_lower: Set[str] = {query_lower}
    nets: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network]] = set()
    try:
        nets.add(ipaddress.ip_address(query))
    except Exception:
        pass
    try:
        nets.add(ipaddress.ip_network(query, strict=False))
    except Exception:
        pass

    changed = True
    while changed:
        changed = False
        for entry in data:
            cfg = entry["cfg"]
            for name, netset in cfg.network_objects.items():
                if name.lower() in names_lower:
                    before = len(nets)
                    nets.update(netset)
                    if len(nets) > before:
                        changed = True
            for net in list(nets):
                for obj in cfg.ip_to_objects.get(net, set()):
                    if obj.lower() not in names_lower:
                        names_lower.add(obj.lower())
                        changed = True
        for entry in data:
            try:
                resolved = entry["cfg"].resolve_network(query)
            except Exception:
                resolved = set()
            before = len(nets)
            nets.update(resolved)
            if len(nets) > before:
                changed = True

    for entry in data:
        cfg = entry["cfg"]
        for net in list(nets):
            for obj in cfg.ip_to_objects.get(net, set()):
                names_lower.add(obj.lower())

    try:
        query_ip = ipaddress.ip_address(query)
    except Exception:
        query_ip = None
    try:
        query_network = ipaddress.ip_network(query, strict=False)
    except Exception:
        query_network = None

    results: List[dict] = []
    for entry in data:
        cfg = entry["cfg"]
        group_membership = entry.get("group_membership", {})
        text_lower = entry["text"].lower()
        matched_objects: Set[str] = set()
        matched_literals: Set[str] = set()
        interface_hits: Set[str] = set()
        score = 0
        direct_object = False

        for name, netset in cfg.network_objects.items():
            if name.lower() in names_lower:
                matched_objects.add(name)
                matched_literals.update(str(val) for val in netset)
                matched_literals.update(getattr(cfg, "network_object_literals", {}).get(name, set()))
                if name.lower() == query_lower:
                    direct_object = True
                    score = max(score, 4)
                else:
                    score = max(score, 2)

        for net in nets:
            for obj in cfg.ip_to_objects.get(net, set()):
                matched_objects.add(obj)
            matched_literals.add(str(net))
            if query_ip is not None:
                if isinstance(net, ipaddress.IPv4Address) and net == query_ip:
                    score = max(score, 3)
                if isinstance(net, ipaddress.IPv4Network) and query_ip in net:
                    score = max(score, 3)
            if query_network is not None and isinstance(net, ipaddress.IPv4Network) and net == query_network:
                score = max(score, 3)

        try:
            resolved = cfg.resolve_network(query)
        except Exception:
            resolved = set()
        matched_literals.update(str(val) for val in resolved)
        for val in resolved:
            if query_ip is not None and isinstance(val, ipaddress.IPv4Address) and val == query_ip:
                score = max(score, 3)

        candidate_ips: Set[ipaddress.IPv4Address] = set()
        for name in matched_objects:
            for val in cfg.network_objects.get(name, set()):
                if isinstance(val, ipaddress.IPv4Address):
                    candidate_ips.add(val)
                elif isinstance(val, ipaddress.IPv4Network):
                    candidate_ips.add(val.network_address)
        for net in nets:
            if isinstance(net, ipaddress.IPv4Address):
                candidate_ips.add(net)
            elif isinstance(net, ipaddress.IPv4Network):
                candidate_ips.add(net.network_address)

        for iface, meta in cfg.interfaces.items():
            ipv4_val = meta.get("ipv4")
            if isinstance(ipv4_val, ipaddress.IPv4Interface):
                network = ipv4_val.network
                display = f"{iface} {ipv4_val}"
            elif isinstance(ipv4_val, ipaddress.IPv4Network):
                network = ipv4_val
                display = f"{iface} {ipv4_val}"
            else:
                continue
            if any(ip in network for ip in candidate_ips):
                interface_hits.add(display)
                score = max(score, 3)
            for net in nets:
                if isinstance(net, ipaddress.IPv4Network) and network == net:
                    interface_hits.add(display)
                    score = max(score, 3)

        text_hit = query_lower in text_lower
        if text_hit:
            score = max(score, 1)

        matched_groups: Set[str] = set()
        for name in matched_objects:
            matched_groups.update(group_membership.get(name.lower(), set()))
        for literal in matched_literals:
            matched_groups.update(group_membership.get(literal.lower(), set()))

        if not (matched_objects or matched_literals or matched_groups or text_hit):
            continue

        has_detail = bool(matched_objects or matched_groups or interface_hits)
        score_details: List[str] = []
        score = 0
        if direct_object:
            score += 100
            score_details.append("Direct object reference")
        if matched_groups:
            score += 40
            score_details.append("Group membership")
        if interface_hits:
            score += 60
            score_details.append("Interface network match")
        if matched_objects:
            score += 20
        if matched_literals:
            score += 10
        if text_hit and not has_detail:
            score += 5
            score_details.append("Text reference")
        results.append(
            {
                "vendor": entry["vendor"],
                "file": entry["file"],
                "vdom": "",
                "objects": sorted(matched_objects),
                "literals": sorted(matched_literals),
                "interfaces": sorted(interface_hits),
                "groups": sorted(matched_groups),
                "text_hit": text_hit,
                "score": score,
                "score_details": score_details,
                "direct": direct_object,
                "has_detail": has_detail,
            }
        )

    if not results:
        return []

    results.sort(
        key=lambda res: (
            -res["score"],
            -len(res["interfaces"]),
            -len(res["objects"]),
            res["file"],
        )
    )
    if results:
        top_score = results[0]["score"]
        if top_score > 0:
            for res in results:
                if res["score"] == top_score:
                    res["best"] = True
                else:
                    break
    return results


def _find_host_fortigate(state: AppState, target: str, vdom: Optional[str]) -> List[dict]:
    query = (target or "").strip()
    if not query:
        return []
    data = _load_fortigate_configs(state, vdom)
    if not data:
        return []
    query_lower = query.lower()
    literal_targets: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network]] = set()
    try:
        literal_targets.add(ipaddress.ip_address(query))
    except Exception:
        pass
    try:
        literal_targets.add(ipaddress.ip_network(query, strict=False))
    except Exception:
        pass

    results: List[dict] = []
    for entry in data:
        cfg = entry["cfg"]
        text_lower = entry["text"].lower()
        direct = False
        matched_objects: Set[str] = set()
        matched_groups: Set[str] = set()
        matched_literals: Set[str] = set()
        score_details: List[str] = []

        if query_lower in (name.lower() for name in cfg.addresses.keys()):
            direct = True

        try:
            resolved = cfg.resolve_addr_token(query)
        except Exception:
            resolved = set()
        resolved_ips: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network]] = set()
        for val in resolved:
            if isinstance(val, (ipaddress.IPv4Address, ipaddress.IPv4Network)):
                resolved_ips.add(val)
            else:
                try:
                    resolved_ips.add(ipaddress.ip_address(str(val)))
                except Exception:
                    try:
                        resolved_ips.add(ipaddress.ip_network(str(val), strict=False))
                    except Exception:
                        continue
        matched_literals.update(str(val) for val in resolved_ips)

        for name, nets in cfg.addresses.items():
            if resolved_ips and any(net in resolved_ips for net in nets):
                matched_objects.add(name)
            elif literal_targets and any(net in literal_targets for net in nets):
                matched_objects.add(name)

        for net, names in getattr(cfg, "ip_to_objects", {}).items():
            if net in resolved_ips or net in literal_targets:
                matched_objects.update(names)

        for group, members in cfg.addrgrps.items():
            for member in members:
                ref = member.get("object") if isinstance(member, dict) else None
                if ref and (ref.lower() == query_lower or ref in matched_objects):
                    matched_groups.add(group)

        text_hit = query_lower in text_lower
        has_detail = bool(matched_objects or matched_groups)
        score = 0
        if direct:
            score += 100
            score_details.append("Direct object reference")
        if matched_objects:
            score += 30
            score_details.append("Address match")
        if matched_groups:
            score += 20
            score_details.append("Group membership")
        if matched_literals:
            score += 10
        if text_hit and not has_detail:
            score += 5
            score_details.append("Text reference")

        if not (matched_objects or matched_groups or matched_literals or text_hit):
            continue

        results.append(
            {
                "vendor": "fortigate",
                "file": entry["file"],
                "vdom": entry.get("vdom", ""),
                "objects": sorted(matched_objects),
                "literals": sorted(matched_literals),
                "interfaces": [],
                "groups": sorted(matched_groups),
                "text_hit": text_hit,
                "score": score,
                "score_details": score_details,
                "direct": direct,
                "has_detail": has_detail,
            }
        )

    if not results:
        return []
    results.sort(key=lambda res: (-res["score"], -len(res["objects"]), res["file"]))
    top_score = results[0]["score"]
    for res in results:
        if res["score"] == top_score and top_score > 0:
            res["best"] = True
        else:
            break
    return results


def _build_group_membership(cfg) -> Dict[str, Set[str]]:
    membership: Dict[str, Set[str]] = defaultdict(set)

    def add_member(key: Union[str, ipaddress.IPv4Address, ipaddress.IPv4Network], groups: Set[str]) -> None:
        membership[str(key).lower()].update(groups)

    def visit(group: str, ancestors: Set[str]) -> None:
        group = str(group)
        if group.lower() in ancestors:
            return
        current = set(ancestors)
        current.add(group)
        membership[group.lower()].update(current)
        members = cfg.network_object_groups.get(group, [])
        for member in members:
            if isinstance(member, dict):
                if "object" in member:
                    add_member(member["object"], current)
                elif "group-object" in member:
                    child = str(member["group-object"])
                    add_member(child, current)
                    visit(child, current)
            elif isinstance(member, (ipaddress.IPv4Address, ipaddress.IPv4Network)):
                add_member(member, current)

    for group_name in cfg.network_object_groups.keys():
        visit(group_name, set())

    return membership


def _load_asa_configs(state: AppState) -> List[dict]:
    dirpath = state.settings.paths.configs.get("asa")
    if not dirpath:
        return []
    items: List[dict] = []
    try:
        entries = [
            name
            for name in sorted(os.listdir(dirpath))
            if not name.startswith(".") and os.path.isfile(os.path.join(dirpath, name))
        ]
    except FileNotFoundError:
        return []
    for name in entries:
        path = os.path.join(dirpath, name)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                text = clean_config_text(handle.read())
        except Exception:
            continue
        try:
            cfg = asa_parser.ASAConfig(text)
        except Exception:
            continue
        items.append(
            {
                "vendor": "asa",
                "file": name,
                "path": path,
                "text": text,
                "cfg": cfg,
                "group_membership": _build_group_membership(cfg),
            }
        )
    return items


def _load_fortigate_configs(state: AppState, vdom: Optional[str]) -> List[dict]:
    dirpath = state.settings.paths.configs.get("fortigate")
    if not dirpath:
        return []
    items: List[dict] = []
    try:
        entries = [
            name
            for name in sorted(os.listdir(dirpath))
            if not name.startswith(".") and os.path.isfile(os.path.join(dirpath, name))
        ]
    except FileNotFoundError:
        return []
    for name in entries:
        path = os.path.join(dirpath, name)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                text = clean_config_text(handle.read())
        except Exception:
            continue
        try:
            cfg = FTGConfig(text, vdom=vdom or None)
        except Exception:
            continue
        items.append(
            {
                "vendor": "fortigate",
                "file": name,
                "path": path,
                "text": text,
                "cfg": cfg,
                "vdom": vdom or cfg.vdom or "",
            }
        )
    return items
