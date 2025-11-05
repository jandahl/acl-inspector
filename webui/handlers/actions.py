"""Handlers for form-based actions (inspect/compare/find/packet)."""

from __future__ import annotations

import html
import ipaddress
import os
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set, Tuple, Union

from parsers.cisco import asa as asa_parser

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
    cfg_file = get("config")
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
    }

    try:
        if vendor != "asa":
            return 400, {"error": f"Vendor {vendor!r} not implemented"}

        if mode == "inspect":
            target = get("inspect")
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
            history_query = target
            meta["query"] = target

        elif mode == "compare":
            old = get("old")
            new = get("new")
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
            history_query = f"{old}->{new}"
            meta["query"] = history_query

        elif mode == "find":
            target = get("findq")
            results = _find_host(state, target)
            html_output = _render_find(target, results, find_verbose)
            tab = "find"
            history_query = target
            meta["query"] = target
            meta["verbose"] = bool(find_verbose)

        elif mode == "packet":
            src = get("pkt_src")
            dst = get("pkt_dst")
            guess_pairs = is_checked("pkt_guess", True)
            pkt = _packet_check_asa(
                cfg_text, src, dst, proto or None, dports_clean, include_any, guess_pairs
            )
            html_output = _render_packet(cfg_file, pkt)
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
        f"data-vendor='{primary_vendor}' data-target='{target_safe}'>Send to Packet Check</button>"
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


def _render_packet(cfg_file: str, pkt: dict) -> str:
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
        nat_lines.append(f"Rule: {rule.get('raw', 'unknown')}")
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
        f"{warning_block}"
        "  <div class='diff diff-raw'><h3>ACL Matches</h3>\n"
        f"  <pre data-lang='asa'>{_escape_text(content)}</pre></div>\n"
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


def _find_host(state: AppState, target: str) -> List[dict]:
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
