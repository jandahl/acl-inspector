#!/usr/bin/env python3
"""
Generate a self-contained static HTML preview for GitHub Pages.

Runs the CLI against in-repo example configs, embeds the results in
docs/index.html using the project's existing CSS variables and classes.
"""

import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "preview"
CLI = REPO_ROOT / "aclinspector.py"
CSS_SRC = REPO_ROOT / "webui" / "static" / "app.css"

ASA_CONFIG = REPO_ROOT / "configs" / "cisco" / "cisco-asa-example"
ASA_DIR = REPO_ROOT / "configs" / "cisco"
FTG_CONFIG = REPO_ROOT / "configs" / "fortigate" / "fortigate7-4-example"


def run_cli(*args):
    cmd = [sys.executable, str(CLI), "inspect"] + list(args) + ["--format", "json"]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    if result.returncode != 0:
        print(f"  ERROR: {' '.join(str(a) for a in args)} → exit {result.returncode}", file=sys.stderr)
        print(f"    stderr: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def esc(s):
    return html.escape(s)


# ── highlight helpers ──────────────────────────────────────────────────────────


def highlight_rule(text):
    """Apply syntax highlighting spans to a rule string."""
    # We build the output character by character avoiding overlapping spans.
    # Strategy: run non-overlapping replacements in priority order.
    # Use a simple token-level approach on the escaped string.

    def span(cls, s):
        return f'<span class="{cls}">{s}</span>'

    parts = []
    for token in re.split(r"(\s+)", esc(text)):
        if not token.strip():
            parts.append(token)
            continue
        # action keywords first
        if re.fullmatch(r"permit", token):
            parts.append(span("act", token))
        elif re.fullmatch(r"deny", token):
            parts.append(span("act", token))
        elif re.fullmatch(r"tcp|udp|icmp|ip", token):
            parts.append(span("proto", token))
        elif re.fullmatch(r"any|any4|any6", token):
            parts.append(span("addr", token))
        elif re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?", token):
            parts.append(span("addr", token))
        elif re.fullmatch(r"eq|range|gt|lt|neq", token):
            parts.append(span("kw", token))
        elif re.fullmatch(r"\d+", token):
            parts.append(span("num", token))
        elif re.fullmatch(r"access-list|object-group|object|network|host", token):
            parts.append(span("kw", token))
        else:
            parts.append(token)
    return "".join(parts)


# ── result formatters ──────────────────────────────────────────────────────────

def fmt_inspect(raw_json, target):
    try:
        d = json.loads(raw_json)
    except Exception:
        return f'<pre class="result-pre">Error parsing output:\n{esc(raw_json)}</pre>'

    nets = d.get("target_nets") or []
    hits = d.get("hits") or []
    aliases = d.get("aliases") or {}

    lines = []
    if nets:
        lines.append(f'<div class="meta-line">Resolves to: '
                     + ", ".join(f'<span class="addr">{esc(n)}</span>' for n in nets)
                     + f"  <span class='hit-count'>({len(hits)} matching rule{'s' if len(hits)!=1 else ''})</span></div>")
    if aliases:
        alt = [k for k in aliases if k != target]
        if alt:
            lines.append(f'<div class="meta-line alias-line">Also known as: '
                         + ", ".join(f"<code>{esc(a)}</code>" for a in alt[:8])
                         + "</div>")
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
                else:
                    bind_str = f'<span class="bind-tag">global</span>'
            lines.append(f'<div class="rule-entry action-{esc(action)}">'
                         f'{bind_str}<code>{highlight_rule(raw)}</code></div>')
        lines.append("</div>")

    return "\n".join(lines)


def fmt_compare(raw_json):
    try:
        d = json.loads(raw_json)
    except Exception:
        return f'<pre class="result-pre">Error parsing output:\n{esc(raw_json)}</pre>'

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
    except Exception:
        return f'<pre class="result-pre">Error:\n{esc(raw_json)}</pre>'

    results = d.get("results", [])
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


def fmt_config_snippet(config_path, max_lines=60):
    try:
        text = Path(config_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return '<div class="no-results">Config file not found.</div>'

    kept = []
    for line in text.splitlines()[:max_lines]:
        stripped = line.strip()
        if stripped.startswith("!") or stripped.startswith("#") or stripped == "":
            kept.append(f'<span class="comment">{esc(line)}</span>')
        else:
            kept.append(highlight_rule(line))
    if len(text.splitlines()) > max_lines:
        kept.append(f'<span class="comment">… ({len(text.splitlines()) - max_lines} more lines)</span>')
    return "<pre class='result-pre'>" + "\n".join(kept) + "</pre>"


# ── page builder ───────────────────────────────────────────────────────────────

def cli_label(*args):
    """Format a CLI invocation as a human-readable label."""
    parts = ["aclinspector.py", "inspect"] + list(args[:-2])  # drop --format json
    return " ".join(str(p) for p in parts)


def build_tab(tab_id, label, content):
    return f"""
  <button class="tab-btn" data-tab="{tab_id}" role="tab" aria-controls="panel-{tab_id}">{label}</button>
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
  margin: 0; white-space: pre-wrap; word-break: break-all;
  font-family: var(--font-mono); font-size: 0.85rem;
  line-height: 1.65;
}}
.meta-line {{ margin-bottom: 8px; font-size: 0.88rem; }}
.hit-count {{ color: var(--sub); }}
.alias-line {{ color: var(--sub); }}
.no-results {{ color: var(--sub); font-style: italic; padding: 6px 0; }}
.rule-list {{ display: flex; flex-direction: column; gap: 3px; }}
.rule-entry {{ display: flex; align-items: baseline; gap: 8px; }}
.rule-entry code {{ word-break: break-all; }}
.action-permit {{ border-left: 3px solid #c3e88d; padding-left: 8px; }}
.action-deny   {{ border-left: 3px solid #f07178; padding-left: 8px; }}
.bind-tag {{
  font-size: 0.78rem; color: var(--sub);
  background: var(--muted); border: 1px solid var(--border);
  border-radius: 4px; padding: 1px 5px; white-space: nowrap; flex-shrink: 0;
}}
.diff-added {{ margin-bottom: 16px; }}
.diff-removed {{ margin-bottom: 16px; }}
.diff-added .group-title {{ color: #c3e88d; font-weight: 600; margin-bottom: 4px; }}
.diff-removed .group-title {{ color: #f07178; font-weight: 600; margin-bottom: 4px; }}
.diff-prefix {{ color: var(--sub); user-select: none; width: 1em; flex-shrink: 0; }}
.diff-added .diff-prefix {{ color: #c3e88d; }}
.diff-removed .diff-prefix {{ color: #f07178; }}
.empty-group {{ color: var(--sub); font-style: italic; margin-bottom: 8px; }}
.added-count {{ color: #c3e88d; }}
.removed-count {{ color: #f07178; }}
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
      <button class="theme-toggle" id="theme-toggle" title="Toggle light/dark">☀</button>
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
    const btns = document.querySelectorAll('.tab-btn');
    const panels = document.querySelectorAll('.tab-panel');
    btns[0].classList.add('active');
    panels[0].classList.add('active');
    btns.forEach(btn => {{
      btn.addEventListener('click', () => {{
        btns.forEach(b => b.classList.remove('active'));
        panels.forEach(p => p.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById('panel-' + btn.dataset.tab).classList.add('active');
      }});
    }});

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
    print("Generating static preview…")
    DOCS_DIR.mkdir(exist_ok=True)

    css = CSS_SRC.read_text()

    tabs_btns = []
    tabs_panels = []

    # ── Tab 1: Inspect (ASA) ────────────────────────────────────────────────
    print("  Running: ASA inspect alpha_lobby_host1")
    j1 = run_cli("--vendor", "asa", "--config", str(ASA_CONFIG), "--inspect", "alpha_lobby_host1")
    s1a = section(
        "Inspect a named host object",
        f"aclinspector.py inspect --vendor asa --config cisco-asa-example --inspect alpha_lobby_host1",
        fmt_inspect(j1, "alpha_lobby_host1"),
    )

    print("  Running: ASA inspect alpha_destgrp_all")
    j2 = run_cli("--vendor", "asa", "--config", str(ASA_CONFIG), "--inspect", "alpha_destgrp_all")
    s1b = section(
        "Inspect an object-group (expands to multiple addresses)",
        f"aclinspector.py inspect --vendor asa --config cisco-asa-example --inspect alpha_destgrp_all",
        fmt_inspect(j2, "alpha_destgrp_all"),
    )

    print("  Running: ASA inspect 10.1.1.101")
    j3 = run_cli("--vendor", "asa", "--config", str(ASA_CONFIG), "--inspect", "10.1.1.101")
    s1c = section(
        "Inspect a raw IP address",
        f"aclinspector.py inspect --vendor asa --config cisco-asa-example --inspect 10.1.1.101",
        fmt_inspect(j3, "10.1.1.101"),
    )

    btns_html, panel_html = build_tab("asa-inspect", "Inspect (ASA)", s1a + s1b + s1c)
    tabs_btns.append(btns_html)
    tabs_panels.append(panel_html)

    # ── Tab 2: Compare (ASA) ────────────────────────────────────────────────
    print("  Running: ASA compare alpha_dest1_grp vs alpha_dest2_grp")
    jc = run_cli("--vendor", "asa", "--config", str(ASA_CONFIG),
                 "--old", "alpha_dest1_grp", "--new", "alpha_dest2_grp")
    sc = section(
        "Compare ACL coverage: alpha_dest1_grp → alpha_dest2_grp",
        "aclinspector.py inspect --vendor asa --config cisco-asa-example --old alpha_dest1_grp --new alpha_dest2_grp",
        fmt_compare(jc),
    )

    print("  Running: ASA compare alpha_lobby_host1 vs alpha_lobby_host2")
    jc2 = run_cli("--vendor", "asa", "--config", str(ASA_CONFIG),
                  "--old", "alpha_lobby_host1", "--new", "alpha_lobby_host2")
    sc2 = section(
        "Compare two host objects in the same subnet",
        "aclinspector.py inspect --vendor asa --config cisco-asa-example --old alpha_lobby_host1 --new alpha_lobby_host2",
        fmt_compare(jc2),
    )

    btns_html, panel_html = build_tab("asa-compare", "Compare (ASA)", sc + sc2)
    tabs_btns.append(btns_html)
    tabs_panels.append(panel_html)

    # ── Tab 3: Find host ─────────────────────────────────────────────────────
    print("  Running: find-host 10.1.1.101 across configs/cisco/")
    jf = run_cli("--vendor", "asa", "--config", str(ASA_DIR), "--find-host", "10.1.1.101")
    sf = section(
        "Find host 10.1.1.101 across all configs in the directory",
        "aclinspector.py inspect --vendor asa --config configs/cisco/ --find-host 10.1.1.101",
        fmt_findhost(jf, "10.1.1.101"),
    )

    btns_html, panel_html = build_tab("find-host", "Find host", sf)
    tabs_btns.append(btns_html)
    tabs_panels.append(panel_html)

    # ── Tab 4: FortiGate ─────────────────────────────────────────────────────
    print("  Running: FortiGate inspect lobby-net")
    jftg = run_cli("--vendor", "fortigate", "--config", str(FTG_CONFIG), "--inspect", "lobby-net")
    sftg = section(
        "Inspect FortiGate address object 'lobby-net'",
        "aclinspector.py inspect --vendor fortigate --config fortigate7-4-example --inspect lobby-net",
        fmt_inspect(jftg, "lobby-net"),
    )

    print("  Running: FortiGate inspect 10.0.1.101")
    jftg2 = run_cli("--vendor", "fortigate", "--config", str(FTG_CONFIG), "--inspect", "10.0.1.101")
    sftg2 = section(
        "Inspect by IP (resolved through FortiGate address objects)",
        "aclinspector.py inspect --vendor fortigate --config fortigate7-4-example --inspect 10.0.1.101",
        fmt_inspect(jftg2, "10.0.1.101"),
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
    (DOCS_DIR / ".nojekyll").touch()

    html = build_page(tabs_btns, tabs_panels, css)
    out_path = DOCS_DIR / "index.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"  Written: {out_path}  ({out_path.stat().st_size // 1024} KB)")

    # Also copy the CSS for users who link to it separately
    shutil.copy(CSS_SRC, DOCS_DIR / "app.css")
    print(f"  Copied:  {DOCS_DIR}/app.css")

    print("Done.")


if __name__ == "__main__":
    main()
