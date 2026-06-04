#!/usr/bin/env python3
"""
Generate a self-contained static HTML preview for GitHub Pages.

Runs the CLI against in-repo example configs, embeds the results in
docs/index.html using the project's existing CSS variables and classes.
"""

import html
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PREVIEW_DIR = REPO_ROOT / "preview"
CLI = REPO_ROOT / "aclinspector.py"
CSS_SRC = REPO_ROOT / "webui" / "static" / "app.css"

ASA_CONFIG = REPO_ROOT / "configs" / "cisco" / "cisco-asa-example"
ASA_DIR = REPO_ROOT / "configs" / "cisco"
FTG_CONFIG = REPO_ROOT / "configs" / "fortigate" / "fortigate7-4-example"

# Named objects used in the preview sections below.
# If the example configs change, update these constants and re-run to verify.
ASA_HOST1 = "alpha_lobby_host1"
ASA_HOST2 = "alpha_lobby_host2"
ASA_DESTGRP_ALL = "alpha_destgrp_all"
ASA_DEST1_GRP = "alpha_dest1_grp"
ASA_DEST2_GRP = "alpha_dest2_grp"
# Raw IPs always resolve; no pre-flight existence check needed for these.
ASA_IP = "10.1.1.101"
FTG_NET = "lobby-net"
FTG_VDOM = "Alpha"
FTG_IP = "10.0.1.101"


def _check_objects():
    """Verify that named network objects exist in their configs before building.

    The CLI exits 0 even for unknown objects (returns empty target_nets/hits),
    so we parse stdout and require non-empty target_nets to confirm the object
    is defined in the config. Raw IP constants (ASA_IP, FTG_IP) are excluded
    because IPs always resolve to themselves regardless of config content.

    Note: the target_nets key is part of the --inspect JSON contract
    (see tests/test_static_preview_formatters.py); if the schema changes,
    update the check below accordingly.
    """
    checks = [
        ("asa", str(ASA_CONFIG), None, ASA_HOST1),
        ("asa", str(ASA_CONFIG), None, ASA_HOST2),
        ("asa", str(ASA_CONFIG), None, ASA_DESTGRP_ALL),
        ("asa", str(ASA_CONFIG), None, ASA_DEST1_GRP),
        ("asa", str(ASA_CONFIG), None, ASA_DEST2_GRP),
        ("fortigate", str(FTG_CONFIG), FTG_VDOM, FTG_NET),
    ]
    ok = True
    for vendor, config, vdom, obj in checks:
        cmd = [sys.executable, str(CLI), "inspect",
               "--vendor", vendor, "--config", config, "--inspect", obj, "--format", "json"]
        if vdom:
            cmd += ["--vdom", vdom]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT, timeout=30)
        except subprocess.TimeoutExpired:
            print(f"  PREFLIGHT ERROR: timed out checking {obj!r}", file=sys.stderr)
            ok = False
            continue
        if r.returncode != 0:
            print(f"  PREFLIGHT ERROR: {obj!r} exited {r.returncode}", file=sys.stderr)
            ok = False
            continue
        try:
            data = json.loads(r.stdout)
        except json.JSONDecodeError:
            print(f"  PREFLIGHT ERROR: unparseable output for {obj!r}", file=sys.stderr)
            ok = False
            continue
        if not data.get("target_nets"):
            print(f"  PREFLIGHT ERROR: object {obj!r} not found in {config} "
                  f"(resolved to empty target_nets)", file=sys.stderr)
            ok = False
    if not ok:
        print("Update the object name constants at the top of this script to match "
              "the example configs, then re-run.", file=sys.stderr)
        sys.exit(1)


def run_cli(*args):
    cmd = [sys.executable, str(CLI), "inspect"] + list(args) + ["--format", "json"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT, timeout=60)
    except subprocess.TimeoutExpired:
        print(f"  ERROR: {' '.join(str(a) for a in args)} timed out after 60s", file=sys.stderr)
        sys.exit(1)
    if result.returncode != 0:
        print(f"  ERROR: {' '.join(str(a) for a in args)} → exit {result.returncode}", file=sys.stderr)
        print(f"    stderr: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def esc(s):
    return html.escape(s)


# ── highlight helpers ──────────────────────────────────────────────────────────

_HL_ACT   = {"permit", "deny"}
_HL_PROTO = {"tcp", "udp", "icmp", "ip"}
_HL_ANY   = {"any", "any4", "any6"}
_HL_PORT  = {"eq", "range", "gt", "lt", "neq"}
_HL_KW    = {"access-list", "object-group", "object", "network", "host"}
_HL_IP_RE = re.compile(r"\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?")


def highlight_rule(text):
    """Apply syntax highlighting spans to a rule string."""

    def span(cls, s):
        return f'<span class="{cls}">{s}</span>'

    parts = []
    for token in re.split(r"(\s+)", esc(text)):
        if not token.strip():
            parts.append(token)
            continue
        tl = token.lower()
        if tl in _HL_ACT:
            parts.append(span("act", token))
        elif tl in _HL_PROTO:
            parts.append(span("proto", token))
        elif tl in _HL_ANY:
            parts.append(span("addr", token))
        elif _HL_IP_RE.fullmatch(token):
            parts.append(span("addr", token))
        elif tl in _HL_PORT:
            parts.append(span("kw", token))
        elif re.fullmatch(r"\d+", token):
            parts.append(span("num", token))
        elif tl in _HL_KW:
            parts.append(span("kw", token))
        else:
            parts.append(token)
    return "".join(parts)


# ── result formatters ──────────────────────────────────────────────────────────

def fmt_inspect(raw_json, target):
    try:
        d = json.loads(raw_json)
        if not isinstance(d, dict):
            raise ValueError("expected JSON object")
    except Exception as e:
        return f'<pre class="result-pre">Error parsing output ({esc(str(e))}):\n{esc(raw_json)}</pre>'

    nets = d.get("target_nets") or []
    hits = d.get("hits") or []
    aliases = d.get("aliases") or {}

    lines = []
    if nets:
        lines.append(f'<div class="meta-line">Resolves to: '
                     + ", ".join(f'<span class="addr">{esc(n)}</span>' for n in nets)
                     + f"  <span class='hit-count'>({len(hits)} matching rule{'s' if len(hits)!=1 else ''})</span></div>")
    if aliases:
        # aliases = {ip: [obj_name, ...], ...} — collect sibling names from values
        alt = []
        for names in aliases.values():
            alt.extend(n for n in names if n != target)
        if alt:
            shown = alt[:8]
            more = f" <span class='hit-count'>+{len(alt) - 8} more</span>" if len(alt) > 8 else ""
            lines.append(f'<div class="meta-line alias-line">Also known as: '
                         + ", ".join(f"<code>{esc(a)}</code>" for a in shown)
                         + more + "</div>")
    if not hits:
        lines.append('<div class="no-results">No matching ACL entries found.</div>')
    else:
        lines.append('<div class="rule-list">')
        for h in hits:
            raw = h.get("raw", "")
            action = h.get("action", "")
            binding = h.get("binding", {})
            bind_str = ""
            if binding:
                scope = binding.get("scope", "")
                iface = binding.get("interface", "")
                direction = binding.get("direction", "")
                if scope == "interface":
                    bind_str = f'<span class="bind-tag">{esc(iface)}({esc(direction)})</span>'
                elif scope == "global":
                    bind_str = '<span class="bind-tag">global</span>'
                else:
                    bind_str = f'<span class="bind-tag">{esc(scope)}</span>'
            lines.append(f'<div class="rule-entry action-{esc(action)}">'
                         f'{bind_str}<code>{highlight_rule(raw)}</code></div>')
        lines.append("</div>")

    return "\n".join(lines)


def fmt_compare(raw_json):
    try:
        d = json.loads(raw_json)
        if not isinstance(d, dict):
            raise ValueError("expected JSON object")
    except Exception as e:
        return f'<pre class="result-pre">Error parsing output ({esc(str(e))}):\n{esc(raw_json)}</pre>'

    if "added_to_new" not in d or "removed_from_old" not in d:
        return f'<pre class="result-pre">Unexpected compare output format:\n{esc(raw_json[:400])}</pre>'
    added = d.get("added_to_new") or []
    removed = d.get("removed_from_old") or []

    lines = []
    lines.append(f'<div class="meta-line">'
                 f'<span class="added-count">+{len(added)} added</span> &nbsp; '
                 f'<span class="removed-count">-{len(removed)} removed</span></div>')

    def render_group(title, rules, css_class, prefix):
        if not rules:
            return f'<div class="{css_class} empty-group">{title}: <em>none</em></div>'
        out = [f'<div class="{css_class}"><div class="group-title">{title}</div><div class="rule-list">']
        for r in rules:
            raw = r.get("raw", "")
            out.append(f'<div class="rule-entry"><span class="diff-prefix">{prefix}</span>'
                       f'<code>{highlight_rule(raw)}</code></div>')
        out.append("</div></div>")
        return "\n".join(out)

    lines.append(render_group("Added (new only)", added, "diff-added", "+"))
    lines.append(render_group("Removed (old only)", removed, "diff-removed", "−"))
    return "\n".join(lines)


def fmt_findhost(raw_json, host):
    try:
        d = json.loads(raw_json)
        if not isinstance(d, dict):
            raise ValueError("expected JSON object")
    except Exception as e:
        return f'<pre class="result-pre">Error ({esc(str(e))}):\n{esc(raw_json)}</pre>'

    results = d.get("results") or []
    if not results:
        return '<div class="no-results">Host not found in any config.</div>'

    lines = ['<div class="findhost-results">']
    for info in results:
        fname = info.get("file", "")
        objects = info.get("objects") or []
        literals = info.get("literals") or []
        lines.append(f'<div class="fh-config"><div class="fh-filename">&#128196; {esc(fname)}</div>')
        if objects:
            lines.append(f'<div class="fh-group">Named objects: '
                         + ", ".join(f"<code>{esc(o)}</code>" for o in objects)
                         + "</div>")
        if literals:
            lines.append(f'<div class="fh-group">Literal matches: '
                         + ", ".join(f'<span class="addr">{esc(l)}</span>' for l in literals)
                         + "</div>")
        lines.append("</div>")
    lines.append("</div>")
    return "\n".join(lines)


def fmt_config_snippet(config_path, max_lines=80):
    try:
        text = Path(config_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return '<div class="no-results">Config file not found.</div>'

    all_lines = text.splitlines()
    kept = []
    for line in all_lines[:max_lines]:
        stripped = line.strip()
        if stripped.startswith("!") or stripped.startswith("#") or stripped == "":
            kept.append(f'<span class="comment">{esc(line)}</span>')
        else:
            kept.append(highlight_rule(line))
    if len(all_lines) > max_lines:
        kept.append(f'<span class="comment">… ({len(all_lines) - max_lines} more lines)</span>')
    return "<pre class='result-pre'>" + "\n".join(kept) + "</pre>"


# ── page builder ───────────────────────────────────────────────────────────────


def build_tab(tab_id, label, content):
    return f"""
  <button class="tab-btn" data-tab="{tab_id}" role="tab" aria-selected="false" aria-controls="panel-{tab_id}">{label}</button>
""", f"""
  <div id="panel-{tab_id}" class="tab-panel" role="tabpanel">
    {content}
  </div>
"""


def cmd_block(cmd):
    return f'<div class="cmd-line"><span class="prompt">$</span> <code>{esc(cmd)}</code></div>'


def section(title, cmd, result_html):
    return f"""
<div class="preview-section">
  <h3>{esc(title)}</h3>
  {cmd_block(cmd)}
  <div class="result-box preview-result">{result_html}</div>
</div>"""


def build_page(tabs_btns, tabs_panels, css):
    tabs_btns_html = "\n".join(tabs_btns)
    tabs_panels_html = "\n".join(tabs_panels)
    return f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ACL-inspector — Live Preview</title>
  <style>
{css}

/* ── preview-page extras ─────────────────────────────────────── */
body {{ margin: 0; }}
.page-header {{
  background: var(--muted);
  border-bottom: 1px solid var(--border);
  padding: 18px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}}
.page-header h1 {{ margin: 0; font-size: 1.3rem; color: var(--text); }}
.page-header .tagline {{ color: var(--sub); font-size: 0.9rem; margin-top: 4px; }}
.header-links a {{ color: var(--accent); font-size: 0.9rem; margin-left: 16px; }}
.page-body {{ max-width: 960px; margin: 0 auto; padding: 24px 16px 48px; }}
.tab-nav {{
  display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 0;
  border-bottom: 1px solid var(--border); padding-bottom: 0;
}}
.tab-btn {{
  background: transparent; color: var(--sub);
  border: 1px solid transparent; border-bottom: none;
  border-radius: 6px 6px 0 0; padding: 7px 16px;
  cursor: pointer; font-size: 0.92rem; font-family: inherit;
  margin-bottom: -1px; position: relative;
  transition: color 0.15s ease, background 0.15s ease;
}}
.tab-btn:hover {{ color: var(--text); background: var(--muted); }}
.tab-btn.active {{
  background: var(--bg); color: var(--text); font-weight: 600;
  border-color: var(--border); border-bottom-color: var(--bg);
}}
.tab-panel {{ display: none; padding: 20px 0; }}
.tab-panel.active {{ display: block; }}
.preview-section {{ margin-bottom: 28px; }}
.preview-section h3 {{ margin: 0 0 8px; font-size: 1rem; color: var(--sub); font-weight: 600; }}
.cmd-line {{
  font-family: var(--font-mono); font-size: 0.85rem;
  background: var(--muted); border: 1px solid var(--border);
  border-radius: 6px; padding: 8px 12px; margin-bottom: 10px;
  display: flex; gap: 8px; align-items: center; overflow-x: auto;
}}
.prompt {{ color: var(--accent); user-select: none; }}
.preview-result {{
  padding: 14px 16px;
  font-family: var(--font-mono); font-size: 0.85rem;
  line-height: 1.65;
}}
.result-pre {{
  margin: 0; white-space: pre-wrap; word-break: break-word; overflow-wrap: anywhere;
  font-family: var(--font-mono); font-size: 0.85rem;
  line-height: 1.65;
}}
.meta-line {{ margin-bottom: 8px; font-size: 0.88rem; }}
.hit-count {{ color: var(--sub); }}
.alias-line {{ color: var(--sub); }}
.no-results {{ color: var(--sub); font-style: italic; padding: 6px 0; }}
.rule-list {{ display: flex; flex-direction: column; gap: 3px; }}
.rule-entry {{ display: flex; align-items: baseline; gap: 8px; }}
.rule-entry code {{ word-break: break-word; overflow-wrap: anywhere; }}
:root {{ --permit-color: #c3e88d; --deny-color: #f07178; }}
:root[data-theme='light'] {{ --permit-color: #2d7a2d; --deny-color: #c0392b; }}
.action-permit {{ border-left: 3px solid var(--permit-color); padding-left: 8px; }}
.action-deny   {{ border-left: 3px solid var(--deny-color); padding-left: 8px; }}
.bind-tag {{
  font-size: 0.78rem; color: var(--sub);
  background: var(--muted); border: 1px solid var(--border);
  border-radius: 4px; padding: 1px 5px; white-space: nowrap; flex-shrink: 0;
}}
.diff-added {{ margin-bottom: 16px; }}
.diff-removed {{ margin-bottom: 16px; }}
.diff-added .group-title {{ color: var(--permit-color); font-weight: 600; margin-bottom: 4px; }}
.diff-removed .group-title {{ color: var(--deny-color); font-weight: 600; margin-bottom: 4px; }}
.diff-prefix {{ color: var(--sub); user-select: none; width: 1em; flex-shrink: 0; }}
.diff-added .diff-prefix {{ color: var(--permit-color); }}
.diff-removed .diff-prefix {{ color: var(--deny-color); }}
.empty-group {{ color: var(--sub); font-style: italic; margin-bottom: 8px; }}
.added-count {{ color: var(--permit-color); }}
.removed-count {{ color: var(--deny-color); }}
.findhost-results {{ display: flex; flex-direction: column; gap: 12px; }}
.fh-config {{ border: 1px solid var(--border); border-radius: 6px; padding: 10px 14px; }}
.fh-filename {{ font-weight: 600; margin-bottom: 6px; }}
.fh-group {{ font-size: 0.88rem; color: var(--sub); margin-top: 4px; }}
.fh-group code {{ color: var(--accent); }}
.comment {{ color: var(--sub); }}
.page-footer {{
  text-align: center; color: var(--sub); font-size: 0.82rem;
  padding: 20px 0 10px; border-top: 1px solid var(--border);
  margin-top: 40px;
}}
  </style>
</head>
<body>
  <header class="page-header">
    <div>
      <h1>ACL-inspector</h1>
      <div class="tagline">Firewall ACL analysis · Cisco ASA &amp; FortiGate · Live preview with in-repo example data</div>
    </div>
    <div class="header-links">
      <a href="https://github.com/jandahl/acl-inspector" target="_blank" rel="noopener">GitHub →</a>
      <button class="theme-toggle" id="theme-toggle" title="Toggle light/dark" aria-label="Toggle light/dark theme">☀</button>
    </div>
  </header>

  <main class="page-body">
    <nav class="tab-nav" role="tablist">
      {tabs_btns_html}
    </nav>
    {tabs_panels_html}
  </main>

  <footer class="page-footer">
    Generated from <a href="https://github.com/jandahl/acl-inspector/tree/main/configs">in-repo example configs</a>.
    Results are pre-computed; this is a static preview, not a live server.
  </footer>

  <script>
    // Tab switching
    const btns = Array.from(document.querySelectorAll('.tab-btn'));
    const panels = document.querySelectorAll('.tab-panel');
    function activateTab(tabId) {{
      btns.forEach(b => {{ b.classList.remove('active'); b.setAttribute('aria-selected', 'false'); b.tabIndex = -1; }});
      panels.forEach(p => p.classList.remove('active'));
      const btn = document.querySelector('.tab-btn[data-tab="' + tabId + '"]');
      if (btn) {{ btn.classList.add('active'); btn.setAttribute('aria-selected', 'true'); btn.tabIndex = 0; }}
      const panel = document.getElementById('panel-' + tabId);
      if (panel) panel.classList.add('active');
    }}
    // Activate first tab by its data-tab value
    if (btns.length) activateTab(btns[0].dataset.tab);
    btns.forEach(btn => btn.addEventListener('click', () => {{ activateTab(btn.dataset.tab); btn.focus(); }}));
    // Arrow-key navigation (ARIA tablist pattern)
    btns.forEach(btn => btn.addEventListener('keydown', e => {{
      const idx = btns.indexOf(e.currentTarget);
      let next = -1;
      if (e.key === 'ArrowRight') next = (idx + 1) % btns.length;
      if (e.key === 'ArrowLeft')  next = (idx - 1 + btns.length) % btns.length;
      if (e.key === 'Home')       next = 0;
      if (e.key === 'End')        next = btns.length - 1;
      if (next >= 0) {{ e.preventDefault(); activateTab(btns[next].dataset.tab); btns[next].focus(); }}
    }}));

    // Theme toggle
    const root = document.documentElement;
    const toggle = document.getElementById('theme-toggle');
    const saved = localStorage.getItem('acl_preview_theme') || 'dark';
    root.dataset.theme = saved;
    toggle.textContent = saved === 'dark' ? '☀' : '☾';
    toggle.addEventListener('click', () => {{
      const next = root.dataset.theme === 'dark' ? 'light' : 'dark';
      root.dataset.theme = next;
      toggle.textContent = next === 'dark' ? '☀' : '☾';
      localStorage.setItem('acl_preview_theme', next);
    }});
  </script>
</body>
</html>
"""


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    print("Generating static preview...")
    PREVIEW_DIR.mkdir(exist_ok=True)

    for path, label in [
        (CSS_SRC,    "CSS file"),
        (ASA_CONFIG, "ASA example config"),
        (ASA_DIR,    "ASA config directory"),
        (FTG_CONFIG, "FortiGate example config"),
    ]:
        if not path.exists():
            print(f"  ERROR: {label} not found: {path}", file=sys.stderr)
            sys.exit(1)

    print("  Pre-flight: verifying named objects exist in example configs...")
    _check_objects()

    css = CSS_SRC.read_text(encoding="utf-8").replace("</style>", "<\\/style>")

    tabs_btns = []
    tabs_panels = []

    # ── Tab 1: Inspect (ASA) ────────────────────────────────────────────────
    print(f"  Running: ASA inspect {ASA_HOST1}")
    j1 = run_cli("--vendor", "asa", "--config", str(ASA_CONFIG), "--inspect", ASA_HOST1)
    s1a = section(
        "Inspect a named host object",
        f"aclinspector.py inspect --vendor asa --config cisco-asa-example --inspect {ASA_HOST1}",
        fmt_inspect(j1, ASA_HOST1),
    )

    print(f"  Running: ASA inspect {ASA_DESTGRP_ALL}")
    j2 = run_cli("--vendor", "asa", "--config", str(ASA_CONFIG), "--inspect", ASA_DESTGRP_ALL)
    s1b = section(
        "Inspect an object-group (expands to multiple addresses)",
        f"aclinspector.py inspect --vendor asa --config cisco-asa-example --inspect {ASA_DESTGRP_ALL}",
        fmt_inspect(j2, ASA_DESTGRP_ALL),
    )

    print(f"  Running: ASA inspect {ASA_IP}")
    j3 = run_cli("--vendor", "asa", "--config", str(ASA_CONFIG), "--inspect", ASA_IP)
    s1c = section(
        "Inspect a raw IP address",
        f"aclinspector.py inspect --vendor asa --config cisco-asa-example --inspect {ASA_IP}",
        fmt_inspect(j3, ASA_IP),
    )

    btns_html, panel_html = build_tab("asa-inspect", "Inspect (ASA)", s1a + s1b + s1c)
    tabs_btns.append(btns_html)
    tabs_panels.append(panel_html)

    # ── Tab 2: Compare (ASA) ────────────────────────────────────────────────
    print(f"  Running: ASA compare {ASA_DEST1_GRP} vs {ASA_DEST2_GRP}")
    jc = run_cli("--vendor", "asa", "--config", str(ASA_CONFIG),
                 "--old", ASA_DEST1_GRP, "--new", ASA_DEST2_GRP)
    sc = section(
        f"Compare ACL coverage: {ASA_DEST1_GRP} → {ASA_DEST2_GRP}",
        f"aclinspector.py inspect --vendor asa --config cisco-asa-example --old {ASA_DEST1_GRP} --new {ASA_DEST2_GRP}",
        fmt_compare(jc),
    )

    print(f"  Running: ASA compare {ASA_HOST1} vs {ASA_HOST2}")
    jc2 = run_cli("--vendor", "asa", "--config", str(ASA_CONFIG),
                  "--old", ASA_HOST1, "--new", ASA_HOST2)
    sc2 = section(
        "Compare two host objects in the same subnet",
        f"aclinspector.py inspect --vendor asa --config cisco-asa-example --old {ASA_HOST1} --new {ASA_HOST2}",
        fmt_compare(jc2),
    )

    btns_html, panel_html = build_tab("asa-compare", "Compare (ASA)", sc + sc2)
    tabs_btns.append(btns_html)
    tabs_panels.append(panel_html)

    # ── Tab 3: Find host ─────────────────────────────────────────────────────
    print(f"  Running: find-host {ASA_IP} across configs/cisco/")
    jf = run_cli("--vendor", "asa", "--config", str(ASA_DIR), "--find-host", ASA_IP)
    sf = section(
        f"Find host {ASA_IP} across all configs in the directory",
        f"aclinspector.py inspect --vendor asa --config configs/cisco/ --find-host {ASA_IP}",
        fmt_findhost(jf, ASA_IP),
    )

    btns_html, panel_html = build_tab("find-host", "Find host", sf)
    tabs_btns.append(btns_html)
    tabs_panels.append(panel_html)

    # ── Tab 4: FortiGate ─────────────────────────────────────────────────────
    print(f"  Running: FortiGate inspect {FTG_NET}")
    jftg = run_cli("--vendor", "fortigate", "--config", str(FTG_CONFIG),
                   "--vdom", FTG_VDOM, "--inspect", FTG_NET)
    sftg = section(
        f"Inspect FortiGate address object '{FTG_NET}' (VDOM: {FTG_VDOM})",
        f"aclinspector.py inspect --vendor fortigate --config fortigate7-4-example --vdom {FTG_VDOM} --inspect {FTG_NET}",
        fmt_inspect(jftg, FTG_NET),
    )

    print(f"  Running: FortiGate inspect {FTG_IP}")
    jftg2 = run_cli("--vendor", "fortigate", "--config", str(FTG_CONFIG),
                    "--vdom", FTG_VDOM, "--inspect", FTG_IP)
    sftg2 = section(
        "Inspect by IP (resolved through FortiGate address objects)",
        f"aclinspector.py inspect --vendor fortigate --config fortigate7-4-example --vdom {FTG_VDOM} --inspect {FTG_IP}",
        fmt_inspect(jftg2, FTG_IP),
    )

    btns_html, panel_html = build_tab("fortigate", "FortiGate", sftg + sftg2)
    tabs_btns.append(btns_html)
    tabs_panels.append(panel_html)

    # ── Tab 5: Config viewer ─────────────────────────────────────────────────
    snippet_asa = fmt_config_snippet(ASA_CONFIG, max_lines=80)
    snippet_ftg = fmt_config_snippet(FTG_CONFIG, max_lines=80)
    sv = (
        section("Cisco ASA example config (first 80 lines)", "configs/cisco/cisco-asa-example", snippet_asa)
        + section("FortiGate 7.4 example config (first 80 lines)", "configs/fortigate/fortigate7-4-example", snippet_ftg)
    )

    btns_html, panel_html = build_tab("config", "Config viewer", sv)
    tabs_btns.append(btns_html)
    tabs_panels.append(panel_html)

    # ── Write output ──────────────────────────────────────────────────────────
    (PREVIEW_DIR / ".nojekyll").touch()

    page_html = build_page(tabs_btns, tabs_panels, css)
    out_path = PREVIEW_DIR / "index.html"
    out_path.write_text(page_html, encoding="utf-8")
    print(f"  Written: {out_path}  ({out_path.stat().st_size // 1024} KB)")

    print("Done.")


if __name__ == "__main__":
    main()
