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
            report = asa_parser.inspect_host(
                cfg_text, target, service_filter=svc_filter, include_any=include_any
            )
            try:
                cfg = asa_parser.ASAConfig(cfg_text)
                nets = cfg.resolve_network(target)
                inclusive = {}
                for net in nets:
                    names = cfg.ip_to_objects.get(net, set()) if hasattr(cfg, "ip_to_objects") else set()
                    if names:
                        inclusive[net] = names
                report["aliases"] = inclusive
            except Exception:
                pass
            html_output = _render_report(target, report, cfg_file)
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
            html_output = _render_diff(old, new, diff, cfg_file, old_aliases, new_aliases)
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
            pkt = _packet_check_asa(cfg_text, src, dst, proto or None, dports_clean, include_any)
            html_output = _render_packet(cfg_file, pkt)
            tab = "packet"
            history_query = f"{src}->{dst}"
            meta["query"] = history_query

        else:
            html_output = "<p style='color:red'>Unsupported mode.</p>"

    except Exception as exc:
        return 500, {"error": str(exc)}

    if history_query and not suppress_history:
        state.history.record(tab, history_query)

    return 200, {"tab": tab, "html": html_output, "meta": meta}


def _escape_text(value: str) -> str:
    return html.escape(html.unescape(value or ""))


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
    binding_str = rule.get("binding") or ""
    bind_suffix = f" bind={binding_str}" if binding_str else ""
    proto = rule.get("proto")
    proto_part = f" {proto}" if proto else ""
    return f"{rule['action']}{proto_part}{svc_str} src=[{src_str}] dst=[{dst_str}]{bind_suffix}"


def _render_report(target: str, report: dict, cfg_file: str) -> str:
    lines_raw = "\n".join(f"  {entry['raw']}" for entry in report["hits"])
    lines_flat = "\n".join(f"  {_fmt(entry)}" for entry in report["hits"])
    alias_html = ""
    aliases = report.get("aliases") or {}
    if aliases:
        alias_lines = []
        for addr, names in sorted(aliases.items(), key=lambda item: str(item[0])):
            alias_lines.append(f"  {addr}: {', '.join(sorted(names))}")
        alias_html = (
            "<div class='diff diff-aliases-inspect'><h3>Duplicate Objects (Aliases)</h3><pre>"
            + "\n".join(alias_lines)
            + "</pre></div>"
        )
    else:
        alias_html = (
            "<div class='rr'><a href='https://youtu.be/dQw4w9WgXcQ' target='_blank' rel='noopener'>No duplicates found</a></div>"
        )
    return f"""
<div class='results results-rules' data-tab='rules'>
  <div class='section'><h2>{_escape_text(cfg_file)}</h2><h3>Inspection Report for {_escape_text(target)}</h3>
  <p>Resolved to: {', '.join(_escape_text(str(net)) for net in report.get('target_nets', []))}</p>
  <p>Found {len(report.get('hits', []))} matching ACL entries.</p></div>
  {alias_html}
  <div class='diff diff-raw'><h3>Matched Rules (Raw)</h3>
  <pre data-lang='asa'>{_escape_text(lines_raw)}</pre></div>
  <div class='diff diff-flattened'><h3>Matched Rules (Flattened)</h3>
  <pre data-lang='asa'>{_escape_text(lines_flat)}</pre></div>
</div>
"""


def _render_diff(
    old: str,
    new: str,
    diff: dict,
    cfg_file: str,
    old_aliases: Optional[Mapping[ipaddress._BaseAddress, Iterable[str]]] = None,
    new_aliases: Optional[Mapping[ipaddress._BaseAddress, Iterable[str]]] = None,
) -> str:
    added = "\n".join(f" + {entry['raw']}\n   -> {_fmt(entry)}" for entry in diff.get("added_to_new", [])[:200])
    removed = "\n".join(f" - {entry['raw']}\n   -> {_fmt(entry)}" for entry in diff.get("removed_from_old", [])[:200])
    alias_html_parts: List[str] = []

    if old_aliases:
        lines = [
            f"  {addr}: {', '.join(sorted(names))}"
            for addr, names in sorted(old_aliases.items(), key=lambda item: str(item[0]))
        ]
        alias_html_parts.append(
            "<div class='diff diff-aliases-old'><h3>Old Target Duplicates</h3><pre>" + "\n".join(lines) + "</pre></div>"
        )
    if new_aliases:
        lines = [
            f"  {addr}: {', '.join(sorted(names))}"
            for addr, names in sorted(new_aliases.items(), key=lambda item: str(item[0]))
        ]
        alias_html_parts.append(
            "<div class='diff diff-aliases-new'><h3>New Target Duplicates</h3><pre>" + "\n".join(lines) + "</pre></div>"
        )
    alias_section = "".join(alias_html_parts) or (
        "<div class='rr'><a href='https://youtu.be/dQw4w9WgXcQ' target='_blank' rel='noopener'>No duplicates</a></div>"
    )

    return f"""
<div class='results results-rules' data-tab='rules'>
  <div class='section'><h2>{_escape_text(cfg_file)}</h2><h3>Comparison</h3>
  <p>Old target: {_escape_text(old)}</p>
  <p>New target: {_escape_text(new)}</p>
  <p>Old hits: {len(diff.get('old_hits', []))} &nbsp; New hits: {len(diff.get('new_hits', []))}</p>
  </div>
  {alias_section}
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
    blocks: List[str] = []
    for result in filtered[:50]:
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
            lines.append(_escape_text(f"Score: {result['score']}"))
            if result.get("text_hit") and not result.get("has_detail"):
                lines.append(_escape_text("Config text contains query"))
        else:
            if result.get("text_hit") and not result.get("has_detail"):
                lines.append(_escape_text("Config text contains query"))
        blocks.append("\n".join(lines))

    return (
        "<div class='results results-find' data-tab='find'><div class='section'><h3>Find Host Results</h3>"
        "<pre>"
        + "\n\n".join(blocks)
        + "</pre></div></div>"
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
        lines.append(f"  {item.get('raw')}\n   -> {summary}")
    content = "\n".join(lines) if lines else "  (no ACL matches)"
    nat_trans = nat.get("translations", {})
    src_nat = nat_trans.get("src", {})
    dst_nat = nat_trans.get("dst", {})
    nat_lines = []
    if nat.get("applied"):
        rule = nat.get("rule") or {}
        nat_lines.append(f"Rule: {rule.get('raw', 'unknown')}")
        nat_lines.append(f"Source: {src_nat.get('before')} -> {src_nat.get('after')}")
        if src_nat.get("note"):
            nat_lines.append(f"  note: {src_nat.get('note')}")
        if dst_nat.get("after") and dst_nat.get("after") != dst_nat.get("before"):
            nat_lines.append(f"Destination: {dst_nat.get('before')} -> {dst_nat.get('after')}")
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
    return (
        "<div class='results results-packet' data-tab='packet'>\n"
        f"  <div class='section'><h2>{_escape_text(cfg_file)}</h2><h3>Packet Check</h3>\n"
        f"  <p>Status: {status} (NAT direction: {_escape_text(str(nat.get('direction') or 'n/a'))})</p>\n"
        f"  <p>Input: src={_escape_text(inp.get('src', ''))} dst={_escape_text(inp.get('dst', ''))} "
        f"proto={_escape_text(inp.get('proto') or 'any')} dports={_escape_text(str(inp.get('dports') or 'any'))}</p>\n"
        f"  <p>Resolved: src={_escape_text(str(resolved.get('src')))} -> {_escape_text(str(resolved.get('post_nat_src')))} | "
        f"dst={_escape_text(str(resolved.get('dst')))} -> {_escape_text(str(resolved.get('post_nat_dst')))}</p></div>\n"
        "  <div class='diff diff-added'><h3>NAT Evaluation</h3>\n"
        f"  <pre>{_escape_text(nat_block)}</pre></div>\n"
        f"{candidate_block}"
        "  <div class='diff diff-raw'><h3>ACL Matches</h3>\n"
        f"  <pre data-lang='asa'>{_escape_text(content)}</pre></div>\n"
        "</div>\n"
    )


def _packet_check_asa(
    cfg_text: str, src: str, dst: str, proto: Optional[str], dports: Set[int], include_any: bool
) -> dict:
    try:
        return asa_parser.path_check(cfg_text, src, dst, proto=proto, dports=dports, include_any=include_any)
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
                "direct": direct_object,
                "has_detail": has_detail,
            }
        )

    if not results:
        return []

    results.sort(key=lambda res: (-res["score"], -len(res["interfaces"]), -len(res["objects"]), res["file"]))
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
