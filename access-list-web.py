#!/usr/bin/env python3
"""Minimal web UI for access-list inspection and comparison.

This server is intentionally separate from the core CLI to keep concerns
isolated. It lists available config files for supported vendors and allows
running inspect/compare operations via a browser form.

Enhancements:
- JSON API endpoints for predictive search and metadata
- In-process + optional disk cache of parsed indices
- Dark mode (default) with toggle, and CSS-classed structure
"""

import os
import json
import time
import hashlib
from typing import Dict, List, Optional, Tuple
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from parsers.cisco import asa as asa_parser

# Expose small module-level helpers for unit tests
def extract_meta_for_tests(vendor: str, text: str) -> dict:
    vendor = vendor.lower()
    if vendor == 'asa':
        import re
        for pat in [r"ASA\s+Version\s+([^\s]+)", r"Adaptive Security Appliance Software\s+Version\s+([^\s]+)"]:
            m = re.search(pat, text, flags=re.IGNORECASE)
            if m:
                return {'vendor': 'asa', 'os': 'ASA', 'version': m.group(1)}
        return {'vendor': 'asa', 'os': 'ASA', 'version': 'unknown'}
    if vendor == 'fortigate':
        return {'vendor': 'fortigate', 'os': 'FortiOS', 'version': 'unknown'}
    return {'vendor': vendor, 'os': vendor.upper(), 'version': 'unknown'}


def build_index_for_tests(vendor: str, text: str) -> dict:
    vendor = vendor.lower()
    if vendor == 'asa':
        cfg = asa_parser.ASAConfig(text)
        objects = sorted(cfg.network_objects.keys())
        groups = sorted(cfg.network_object_groups.keys())
        literals = set()
        for nset in cfg.network_objects.values():
            for n in nset:
                literals.add(str(n))
        return {'objects': objects, 'groups': groups, 'literals': sorted(literals)}
    return {'objects': [], 'groups': [], 'literals': []}


def match_candidates_for_tests(index: dict, query: str, limit: int = 50, mode: str = 'fuzzy') -> list:
    # Minimal adapter to exercise search modes in tests
    q = query.strip().lower()
    class _Dummy:
        pass
    dummy = _Dummy()
    # bind fuzzy scorer so _match_fuzzy can call self._fuzzy_score
    dummy._fuzzy_score = lambda text, pattern: WebHandler._fuzzy_score(dummy, text, pattern)
    if mode == 'prefix':
        return WebHandler._match_prefix(dummy, index, q, limit)
    if mode == 'substring':
        return WebHandler._match_substring(dummy, index, q, limit)
    return WebHandler._match_fuzzy(dummy, index, q, limit)


def highlight_asa_for_tests(line: str) -> str:
    import html, re
    s = html.escape(line)
    s = re.sub(r"\b(permit|deny)\b", r"<span class='act'>\1</span>", s, flags=re.IGNORECASE)
    s = re.sub(r"\b(tcp|udp|icmp|ip)\b", r"<span class='proto'>\1</span>", s, flags=re.IGNORECASE)
    s = re.sub(r"\b(access-list|extended|object-group|object|host|subnet|eq|lt|gt|neq|range|any|any4|any6)\b", r"<span class='kw'>\1</span>", s, flags=re.IGNORECASE)
    s = re.sub(r"\b(\d{1,3}(?:\.\d{1,3}){3})(?:/(\d{1,2}))?\b", lambda m: f"<span class='addr'>{m.group(1)}{('/'+m.group(2)) if m.group(2) else ''}</span>", s)
    s = re.sub(r"\b(\d{2,5})\b", r"<span class='num'>\1</span>", s)
    return s


def list_files(dirpath: str):
    try:
        return sorted([f for f in os.listdir(dirpath) if os.path.isfile(os.path.join(dirpath, f))])
    except FileNotFoundError:
        return []


class WebHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # API routing
        parsed = urlparse(self.path)
        if parsed.path == '/api/objects':
            return self._api_objects(parsed.query)
        if parsed.path == '/api/meta':
            return self._api_meta(parsed.query)
        if parsed.path == '/api/aliases':
            return self._api_aliases(parsed.query)
        # UI
        self._html(self._form())

    def do_POST(self):
        if self.path != '/run':
            self.send_error(404)
            return
        length = int(self.headers.get('Content-Length', 0))
        data = self.rfile.read(length).decode('utf-8')
        fields = parse_qs(data)
        vendor = (fields.get('vendor', ['asa'])[0] or 'asa').lower()
        mode = fields.get('mode', ['inspect'])[0]
        cfg_file = fields.get('config', [''])[0]
        proto = fields.get('proto', [''])[0]
        dports = fields.get('dport', [])
        dports_clean = set()
        for dp in dports:
            dp = dp.strip()
            if not dp:
                continue
            try:
                dports_clean.add(int(dp))
            except Exception:
                pass
        svc_filter = None
        if proto or dports_clean:
            svc_filter = {'proto': (proto or None), 'dports': dports_clean}

        cfg_dir = self.server.config_dirs.get(vendor)
        path = os.path.join(cfg_dir, cfg_file) if cfg_dir and cfg_file else ''
        if not path or not os.path.isfile(path):
            self._html("<p style='color:red'>Invalid or missing config file.</p>" + self._form())
            return
        try:
            with open(path, 'r') as f:
                cfg_text = f.read()
        except Exception as e:
            self._html(f"<p style='color:red'>Failed to read: {e}</p>" + self._form())
            return

        if vendor == 'asa':
            try:
                if mode == 'inspect':
                    target = fields.get('inspect', [''])[0]
                    report = asa_parser.inspect_host(cfg_text, target, service_filter=svc_filter)
                    body = self._render_report(target, report)
                else:
                    old = fields.get('old', [''])[0]
                    new = fields.get('new', [''])[0]
                    diff = asa_parser.compare_old_new(cfg_text, old, new, service_filter=svc_filter)
                    # Build alias boxes for old/new
                    cfg = asa_parser.ASAConfig(cfg_text)
                    old_aliases = cfg.find_alias_objects(old, cfg.resolve_network(old)) if old else {}
                    new_aliases = cfg.find_alias_objects(new, cfg.resolve_network(new)) if new else {}
                    body = self._render_diff(old, new, diff, old_aliases=old_aliases, new_aliases=new_aliases)
                self._html(body + self._form())
            except Exception as e:
                self._html(f"<p style='color:red'>Error: {e}</p>" + self._form())
        else:
            self._html("<p>Vendor not implemented.</p>" + self._form())

    # ------------ render helpers ------------
    def _form(self):
        asa_opts = "\n".join(["<option value='{}'>{}</option>".format(x, x) for x in list_files(self.server.config_dirs.get('asa', 'configs/cisco'))])
        ftg_opts = "\n".join(["<option value='{}'>{}</option>".format(x, x) for x in list_files(self.server.config_dirs.get('fortigate', 'configs/fortigate'))])
        css = self._css()
        return (
            "<!doctype html>\n"
            "<html><head><meta charset='utf-8'><title>ACL Inspector</title><style>" + css + "</style></head>\n"
            "<body class='theme-dark'>\n"
            "  <div class='app'>\n"
            "  <div class='toolbar'><h2>ACL Inspector</h2><div class='toolbar-controls'><label class='theme-switch'><input type='checkbox' id='themeToggle'/> Light mode</label> <label class='hl-switch'><input type='checkbox' id='hlToggle'/> Highlight output</label></div></div>\n"
            "  <form class='form' method='POST' action='/run'>\n"
            "    <fieldset class='section section-config'><legend>Config</legend>\n"
            "    <label>Vendor:</label>\n"
            "    <select name='vendor' id='vendor' onchange='toggleVendor(); refreshMeta();'>\n"
            "      <option value='asa' selected>ASA</option>\n"
            "      <option value='fortigate'>FortiGate</option>\n"
            "    </select>\n"
            "    <span id='meta' class='meta'></span><br/>\n"
            "    <div id='asa_cfg'>\n"
            "      <label>ASA Config:</label>\n"
            "      <select name='config' id='config' onchange='refreshMeta();'>\n"
            + asa_opts +
            "      </select>\n"
            "    </div>\n"
            "    <div id='ftg_cfg' style='display:none'>\n"
            "      <label>FortiGate Config:</label>\n"
            "      <select name='config' id='config_ftg' onchange='refreshMeta();'>\n"
            + ftg_opts +
            "      </select>\n"
            "    </div>\n"
            "    </fieldset>\n"
            "    <fieldset class='section section-mode'><legend>Mode</legend>\n"
            "    <label>Mode:</label>\n"
            "    <select name='mode' id='mode' onchange='toggleMode()'>\n"
            "      <option value='inspect' selected>Inspect</option>\n"
            "      <option value='compare'>Compare</option>\n"
            "    </select>\n"
            "    </fieldset>\n"
            "    <fieldset class='section section-targets'><legend>Targets</legend>\n"
            "    <div id='inspect_fields'>\n"
            "      <label>Inspect target:</label>\n"
            "      <input type='text' name='inspect' id='inspect' list='targets' autocomplete='off' placeholder='name|ip|cidr'/>\n"
            "    </div>\n"
            "    <div id='compare_fields' style='display:none'>\n"
            "      <label>Old target:</label>\n"
            "      <input type='text' name='old' id='old' list='targets' autocomplete='off' placeholder='name|ip|cidr'/>\n"
            "      <label>New target:</label>\n"
            "      <input type='text' name='new' id='new' list='targets' autocomplete='off' placeholder='name|ip|cidr'/>\n"
            "    </div>\n"
            "    <datalist id='targets'></datalist>\n"
            "    <div class='search-options'><label><input type='checkbox' id='fuzzy' checked/> Fuzzy search</label></div>\n"
            "    </fieldset>\n"
            "    <fieldset class='section section-service'><legend>Service Filter</legend>\n"
            "    <label>Protocol:</label>\n"
            "    <select name='proto'>\n"
            "      <option value=''>Any</option>\n"
            "      <option value='tcp'>TCP</option>\n"
            "      <option value='udp'>UDP</option>\n"
            "      <option value='icmp'>ICMP</option>\n"
            "      <option value='ip'>IP</option>\n"
            "    </select>\n"
            "    <label>Destination ports (comma separated):</label>\n"
            "    <input type='text' name='dport' placeholder='443,1433'/>\n"
            "    </fieldset>\n"
            "    <div class='actions'><button type='submit'>Run</button></div>\n"
            "  </form>\n"
            "  </div>\n"
            "  <script>\n"
            "    const THEME_KEY='acl_theme';\n"
            "    const HL_KEY='acl_highlight';\n"
            "    function applyTheme(){\n"
            "      const mode=localStorage.getItem(THEME_KEY)||'dark';\n"
            "      document.body.className = (mode==='dark') ? 'theme-dark' : 'theme-light';\n"
            "      document.getElementById('themeToggle').checked = (mode!=='dark');\n"
            "    }\n"
            "    function escapeHtml(s){return s.replace(/[&<>]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}\n"
            "    function hlASA(line){\n"
            "      let s=escapeHtml(line);\n"
            "      s=s.replace(/\\b(permit|deny)\\b/gi,'<span class=\\'act\\'>$1</span>');\n"
            "      s=s.replace(/\\b(tcp|udp|icmp|ip)\\b/gi,'<span class=\\'proto\\'>$1</span>');\n"
            "      s=s.replace(/\\b(access-list|extended|object-group|object|host|subnet|eq|lt|gt|neq|range|any|any4|any6)\\b/gi,'<span class=\\'kw\\'>$1</span>');\n"
            "      s=s.replace(/\\b(\\d{1,3}(?:\\.\\d{1,3}){3})(?:\\/(\\d{1,2}))?\\b/g,(m,ip,cidr)=>`<span class='addr'>${ip}${cidr?`/${cidr}`:''}</span>`);\n"
            "      s=s.replace(/\\b(\\d{2,5})\\b/g,'<span class=\\'num\\'>$1</span>');\n"
            "      return s;\n"
            "    }\n"
            "    function highlightAll(on){\n"
            "      const pres=document.querySelectorAll('pre[data-lang=\\'asa\\']');\n"
            "      for(const pre of pres){\n"
            "        const raw=pre.textContent;\n"
            "        if(!on){ pre.innerHTML = escapeHtml(raw); continue;}\n"
            "        const lines=raw.split(/\\n/).map(hlASA);\n"
            "        pre.innerHTML = lines.join('\\n');\n"
            "      }\n"
            "    }\n"
            "    function toggleVendor(){\n"
            "      var v = document.getElementById('vendor').value;\n"
            "      document.getElementById('asa_cfg').style.display = (v==='asa') ? 'block':'none';\n"
            "      document.getElementById('ftg_cfg').style.display = (v==='fortigate') ? 'block':'none';\n"
            "    }\n"
            "    function toggleMode(){\n"
            "      var m = document.getElementById('mode').value;\n"
            "      document.getElementById('inspect_fields').style.display = (m==='inspect') ? 'block':'none';\n"
            "      document.getElementById('compare_fields').style.display = (m==='compare') ? 'block':'none';\n"
            "    }\n"
            "    function debounce(fn,ms){let t;return (...a)=>{clearTimeout(t);t=setTimeout(()=>fn.apply(this,a),ms)};}\n"
            "    function currentConfig(){\n"
            "      const v=document.getElementById('vendor').value;\n"
            "      const c=(v==='asa')?document.getElementById('config').value:document.getElementById('config_ftg').value;\n"
            "      return {vendor:v,config:c};\n"
            "    }\n"
            "    function fillDatalist(items){\n"
            "      const dl=document.getElementById('targets');\n"
            "      dl.innerHTML='';\n"
            "      for (const it of items){\n"
            "        const opt=document.createElement('option');\n"
            "        opt.value=it.value; opt.label=it.label||it.value;\n"
            "        dl.appendChild(opt);\n"
            "      }\n"
            "    }\n"
            "    const fetchSuggest = debounce(async function(ev){\n"
            "      const q=ev.target.value; if(!q||q.length<1){fillDatalist([]);return;}\n"
            "      const {vendor,config}=currentConfig();\n"
            "      const mode=document.getElementById('fuzzy').checked ? 'fuzzy' : 'prefix';\n"
            "      try{\n"
            "        const resp=await fetch(`/api/objects?vendor=${vendor}&os=${vendor.toUpperCase()}&version=auto&config=${encodeURIComponent(config)}&q=${encodeURIComponent(q)}&mode=${mode}&limit=50`);\n"
            "        if(!resp.ok){return;}\n"
            "        const data=await resp.json();\n"
            "        fillDatalist(data.items||[]);\n"
            "      }catch(e){}\n"
            "    },150);\n"
            "    function attachTypeahead(){\n"
            "      for(const id of ['inspect','old','new']){const el=document.getElementById(id); if(el){el.addEventListener('input',fetchSuggest);}}\n"
            "    }\n"
            "    async function refreshMeta(){\n"
            "      const {vendor,config}=currentConfig();\n"
            "      const el=document.getElementById('meta'); el.textContent='';\n"
            "      if(!config){return;}\n"
            "      try{const r=await fetch(`/api/meta?vendor=${vendor}&config=${encodeURIComponent(config)}`); if(r.ok){const j=await r.json(); el.textContent = `OS: ${j.os||vendor.toUpperCase()}  Version: ${j.version||'unknown'}`;}}catch(e){}\n"
            "    }\n"
            "    document.getElementById('themeToggle').addEventListener('change', (e)=>{localStorage.setItem(THEME_KEY, e.target.checked?'light':'dark'); applyTheme();});\n"
            "    document.getElementById('hlToggle').addEventListener('change', (e)=>{localStorage.setItem('acl_highlight', e.target.checked?'on':'off'); highlightAll(e.target.checked);});\n"
            "    applyTheme(); toggleVendor(); toggleMode(); attachTypeahead(); refreshMeta(); highlightAll((localStorage.getItem(HL_KEY)||'on')==='on'); document.getElementById('hlToggle').checked = (localStorage.getItem(HL_KEY)||'on')==='on';\n"
            "  </script>\n"
            "</body></html>\n"
        )

    def _render_report(self, target, report):
        lines_raw = "\n".join(f"  {e['raw']}" for e in report['hits'])
        lines_flat = "\n".join(f"  {self._fmt(e)}" for e in report['hits'])
        alias_html = ""
        aliases = report.get('aliases') or {}
        if aliases:
            alias_lines = []
            for addr, names in sorted(aliases.items(), key=lambda x: str(x[0])):
                alias_lines.append(f"  {addr}: {', '.join(sorted(names))}")
            alias_html = "<div class='diff diff-aliases-inspect'><h3>Duplicate Objects (Aliases)</h3><pre>" + "\n".join(alias_lines) + "</pre></div>"
        else:
            # Subtle rickroll link per request when empty
            alias_html = "<div class='rr'><a href='https://youtu.be/dQw4w9WgXcQ' target='_blank' rel='noopener'>No duplicates found</a></div>"
        return f"""
<div class='results'>
  <div class='section'><h3>Inspection Report for {target}</h3>
  <p>Resolved to: {', '.join(str(n) for n in report['target_nets'])}</p>
  <p>Found {len(report['hits'])} matching ACL entries.</p></div>
  {alias_html}
  <div class='diff diff-raw'><h3>Matched Rules (Raw)</h3>
  <pre data-lang='asa'>{lines_raw}</pre></div>
  <div class='diff diff-flattened'><h3>Matched Rules (Flattened)</h3>
  <pre data-lang='asa'>{lines_flat}</pre></div>
</div>
"""

    def _render_diff(self, old, new, diff, old_aliases=None, new_aliases=None):
        added = "\n".join(f" + {e['raw']}\n   -> {self._fmt(e)}" for e in diff['added_to_new'][:200])
        removed = "\n".join(f" - {e['raw']}\n   -> {self._fmt(e)}" for e in diff['removed_from_old'][:200])
        # Aliases boxes (hide if empty; include subtle rickroll links when both empty)
        alias_html_parts = []
        if old_aliases:
            lines = []
            for addr, names in sorted(old_aliases.items(), key=lambda x: str(x[0])):
                lines.append(f"  {addr}: {', '.join(sorted(names))}")
            alias_html_parts.append("<div class='diff diff-aliases-old'><h3>Old Target Duplicates</h3><pre>" + "\n".join(lines) + "</pre></div>")
        if new_aliases:
            lines = []
            for addr, names in sorted(new_aliases.items(), key=lambda x: str(x[0])):
                lines.append(f"  {addr}: {', '.join(sorted(names))}")
            alias_html_parts.append("<div class='diff diff-aliases-new'><h3>New Target Duplicates</h3><pre>" + "\n".join(lines) + "</pre></div>")
        alias_section = "".join(alias_html_parts)
        if not alias_section:
            alias_section = "<div class='rr'><a href='https://youtu.be/dQw4w9WgXcQ' target='_blank' rel='noopener'>No duplicates</a></div>"
        return f"""
<div class='results'>
  <div class='section'><h3>Comparison</h3>
  <p>Old target: {old}</p>
  <p>New target: {new}</p>
  <p>Old hits: {len(diff['old_hits'])} &nbsp; New hits: {len(diff['new_hits'])}</p>
  <p>Added to new: {len(diff['added_to_new'])} &nbsp; Removed from old: {len(diff['removed_from_old'])}</p></div>
  {alias_section}
  <div class='diff diff-added'><h3>Rules Added to New</h3>
  <pre data-lang='asa'>{added}</pre></div>
  <div class='diff diff-removed'><h3>Rules Removed from Old</h3>
  <pre data-lang='asa'>{removed}</pre></div>
</div>
"""

    def _fmt(self, rule: dict) -> str:
        src_str = ', '.join(sorted([str(s) for s in rule['src']]))
        dst_str = ', '.join(sorted([str(s) for s in rule['dst']]))
        svc = rule.get('svc') or {}
        parts = []
        if svc.get('proto'):
            parts.append(svc['proto'])
        if svc.get('service_group_at_proto'):
            sg = svc['service_group_at_proto']
            parts.append(f"{sg['kind']}:{sg['name']}")
        port_parts = []
        for op, (p1, p2) in svc.get('dst_ports', []):
            if op == 'range':
                port_parts.append(f"{p1}-{p2}")
            else:
                port_parts.append(f"{op} {p1}")
        if svc.get('dst_service_groups'):
            for g in sorted(svc['dst_service_groups']):
                port_parts.append(f"group:{g}")
        if svc.get('dst_service_objects'):
            for o in sorted(svc['dst_service_objects']):
                port_parts.append(f"object:{o}")
        svc_str = ''
        if parts or port_parts:
            head = ' '.join(parts) if parts else ''
            tail = (' ports=' + ','.join(port_parts)) if port_parts else ''
            svc_str = f" {head}{tail}".rstrip()
        return f"{rule['action']}{(' ' + rule['proto']) if rule.get('proto') else ''}{svc_str} src=[{src_str}] dst=[{dst_str}]"

    def _html(self, body: str, status: int = 200):
        content = body.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    # -------------------- API helpers --------------------
    def _json(self, payload: dict, status: int = 200):
        data = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _api_objects(self, query: str):
        qs = parse_qs(query or '')
        vendor = (qs.get('vendor', ['asa'])[0] or 'asa').lower()
        os_tag = qs.get('os', [vendor.upper()])[0]
        version = qs.get('version', ['auto'])[0]
        cfg_file = qs.get('config', [''])[0]
        q = (qs.get('q', [''])[0] or '').strip().lower()
        mode = (qs.get('mode', ['fuzzy'])[0] or 'fuzzy').lower()
        try:
            limit = int(qs.get('limit', [str(self.server.search_limit)])[0])
        except Exception:
            limit = self.server.search_limit
        cfg_dir = self.server.config_dirs.get(vendor)
        path = os.path.join(cfg_dir, cfg_file) if cfg_dir and cfg_file else ''
        if not path or not os.path.isfile(path):
            return self._json({'items': [], 'error': 'invalid_config'}, 400)
        # Build or load index
        index = self._get_index(vendor, os_tag, version, path)
        if q:
            if mode == 'prefix':
                items = self._match_prefix(index, q, limit)
            elif mode == 'substring':
                items = self._match_substring(index, q, limit)
            else:
                items = self._match_fuzzy(index, q, limit)
        else:
            items = []
        return self._json({'items': items})

    def _api_meta(self, query: str):
        qs = parse_qs(query or '')
        vendor = (qs.get('vendor', ['asa'])[0] or 'asa').lower()
        cfg_file = qs.get('config', [''])[0]
        cfg_dir = self.server.config_dirs.get(vendor)
        path = os.path.join(cfg_dir, cfg_file) if cfg_dir and cfg_file else ''
        if not path or not os.path.isfile(path):
            return self._json({'error': 'invalid_config'}, 400)
        try:
            with open(path, 'r') as f:
                text = f.read()
        except Exception as e:
            return self._json({'error': f'read_failed: {e}'}, 500)
        meta = self._extract_meta(vendor, text)
        return self._json(meta)

    def _api_aliases(self, query: str):
        qs = parse_qs(query or '')
        vendor = (qs.get('vendor', ['asa'])[0] or 'asa').lower()
        cfg_file = qs.get('config', [''])[0]
        target = qs.get('target', [''])[0]
        cfg_dir = self.server.config_dirs.get(vendor)
        path = os.path.join(cfg_dir, cfg_file) if cfg_dir and cfg_file else ''
        if not path or not os.path.isfile(path) or not target:
            return self._json({'aliases': {}}, 200)
        try:
            with open(path, 'r') as f:
                text = f.read()
        except Exception as e:
            return self._json({'error': f'read_failed: {e}'}, 500)
        if vendor == 'asa':
            cfg = asa_parser.ASAConfig(text)
            nets = cfg.resolve_network(target)
            aliases = cfg.find_alias_objects(target, nets)
            # Stringify keys for JSON
            out = {str(k): sorted(list(v)) for (k, v) in aliases.items()}
            return self._json({'aliases': out})
        return self._json({'aliases': {}})

    # -------------------- Cache and index --------------------
    def _extract_meta(self, vendor: str, text: str) -> dict:
        vendor = vendor.lower()
        if vendor == 'asa':
            # Try a couple of common patterns
            import re
            for pat in [r"ASA\s+Version\s+([^\s]+)", r"Adaptive Security Appliance Software\s+Version\s+([^\s]+)"]:
                m = re.search(pat, text, flags=re.IGNORECASE)
                if m:
                    return {'vendor': 'asa', 'os': 'ASA', 'version': m.group(1)}
            return {'vendor': 'asa', 'os': 'ASA', 'version': 'unknown'}
        if vendor == 'fortigate':
            # Best-effort placeholder
            return {'vendor': 'fortigate', 'os': 'FortiOS', 'version': 'unknown'}
        return {'vendor': vendor, 'os': vendor.upper(), 'version': 'unknown'}

    def _hash_path(self, path: str) -> str:
        return hashlib.sha1(os.path.realpath(path).encode('utf-8')).hexdigest()

    def _cache_load(self, key: str) -> Optional[dict]:
        cache_dir = getattr(self.server, 'cache_dir', None)
        if not cache_dir:
            return None
        fpath = os.path.join(cache_dir, key + '.json')
        try:
            with open(fpath, 'r') as f:
                return json.load(f)
        except Exception:
            return None

    def _cache_save(self, key: str, data: dict) -> None:
        cache_dir = getattr(self.server, 'cache_dir', None)
        if not cache_dir:
            return
        try:
            os.makedirs(cache_dir, exist_ok=True)
            fpath = os.path.join(cache_dir, key + '.json')
            with open(fpath, 'w') as f:
                json.dump(data, f)
        except Exception:
            pass

    def _get_index(self, vendor: str, os_tag: str, version: str, path: str) -> dict:
        st = os.stat(path)
        cache_key = f"{vendor}-{os_tag}-{self._hash_path(path)}"
        # First check in-memory
        mem = self.server.index_cache.get(cache_key)
        if mem and mem.get('src_mtime') == st.st_mtime and mem.get('src_size') == st.st_size:
            return mem['index']
        # Try disk cache
        disk = self._cache_load(cache_key)
        if disk and disk.get('src_mtime') == st.st_mtime and disk.get('src_size') == st.st_size:
            self.server.index_cache[cache_key] = disk
            return disk['index']
        # Build fresh
        with open(path, 'r') as f:
            text = f.read()
        index = self._build_index(vendor, text)
        payload = {
            'vendor': vendor,
            'os': os_tag,
            'version': version,
            'built_at': time.time(),
            'src_mtime': st.st_mtime,
            'src_size': st.st_size,
            'index': index,
        }
        self.server.index_cache[cache_key] = payload
        self._cache_save(cache_key, payload)
        return index

    def _build_index(self, vendor: str, text: str) -> dict:
        vendor = vendor.lower()
        if vendor == 'asa':
            cfg = asa_parser.ASAConfig(text)
            # Gather
            objects = sorted(cfg.network_objects.keys())
            groups = sorted(cfg.network_object_groups.keys())
            literals = set()
            for nset in cfg.network_objects.values():
                for n in nset:
                    literals.add(str(n))
            # Note: We don’t include service groups yet
            return {
                'objects': objects,
                'groups': groups,
                'literals': sorted(literals),
            }
        # Fallback empty for other vendors for now
        return {'objects': [], 'groups': [], 'literals': []}

    def _match_prefix(self, index: dict, q: str, limit: int) -> List[dict]:
        out: List[dict] = []
        ql = q.lower()
        def add_many(values: List[str], typ: str):
            nonlocal out
            for v in values:
                if v.lower().startswith(ql):
                    label = v
                    if typ == 'object':
                        label = f"{v}"
                    elif typ == 'group':
                        label = f"{v} (group)"
                    out.append({'value': v, 'label': label, 'type': typ})
                    if len(out) >= limit:
                        return True
            return False
        if add_many(index.get('objects', []), 'object'):
            return out
        if add_many(index.get('groups', []), 'group'):
            return out
        add_many(index.get('literals', []), 'literal')
        return out[:limit]

    def _match_substring(self, index: dict, q: str, limit: int) -> List[dict]:
        out: List[dict] = []
        ql = q.lower()
        def add_many(values: List[str], typ: str):
            nonlocal out
            for v in values:
                if ql in v.lower():
                    label = v if typ != 'group' else f"{v} (group)"
                    out.append({'value': v, 'label': label, 'type': typ})
                    if len(out) >= limit:
                        return True
            return False
        if add_many(index.get('objects', []), 'object'):
            return out
        if add_many(index.get('groups', []), 'group'):
            return out
        add_many(index.get('literals', []), 'literal')
        return out[:limit]

    def _fuzzy_score(self, text: str, pattern: str) -> Optional[Tuple[int, int, int]]:
        # Returns a tuple score (gaps, start, length) where lower is better; None if no subsequence match
        t = text.lower(); p = pattern.lower()
        ti = 0; pi = 0; start = -1; gaps = 0; last_match = -1
        while ti < len(t) and pi < len(p):
            if t[ti] == p[pi]:
                if start == -1:
                    start = ti
                if last_match != -1 and ti - last_match > 1:
                    gaps += (ti - last_match - 1)
                last_match = ti
                pi += 1
            ti += 1
        if pi != len(p):
            return None
        length = (last_match - start + 1) if start != -1 else len(t)
        return (gaps, start if start != -1 else 0, length)

    def _match_fuzzy(self, index: dict, q: str, limit: int) -> List[dict]:
        candidates: List[Tuple[Tuple[int,int,int], dict]] = []
        def consider(values: List[str], typ: str):
            for v in values:
                sc = self._fuzzy_score(v, q)
                if sc is not None:
                    label = v if typ != 'group' else f"{v} (group)"
                    candidates.append((sc, {'value': v, 'label': label, 'type': typ}))
        consider(index.get('objects', []), 'object')
        consider(index.get('groups', []), 'group')
        consider(index.get('literals', []), 'literal')
        candidates.sort(key=lambda x: (x[0][0], x[0][1], x[0][2], x[1]['type'] != 'object', x[1]['type'] != 'group', x[1]['value']))
        return [c[1] for c in candidates[:limit]]

    def _css(self) -> str:
        return (
            ":root{--bg:#0e1116;--muted:#1a1f29;--text:#e6edf3;--sub:#9da7b3;--accent:#7aa2f7;--border:#2b3240;}\n"
            ".theme-light{--bg:#ffffff;--muted:#f6f8fa;--text:#24292f;--sub:#57606a;--accent:#0969da;--border:#d0d7de;}\n"
            "body{background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,'Helvetica Neue',sans-serif;margin:0;}\n"
            ".app{max-width:1200px;margin:0 auto;padding:16px;}\n"
            ".toolbar{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;}\n"
            "h2{margin:0;}\n"
            ".form{background:var(--muted);padding:12px;border:1px solid var(--border);border-radius:8px;margin-bottom:16px;}\n"
            ".section{margin-bottom:10px;} fieldset.section{border:1px solid var(--border);border-radius:8px;} legend{color:var(--sub);}\n"
            "label{margin-right:6px;} select,input[type=text]{margin-right:8px;margin-bottom:6px;padding:4px 6px;border:1px solid var(--border);border-radius:6px;background:transparent;color:var(--text);}\n"
            ".actions{margin-top:8px;} button{background:var(--accent);color:#fff;border:none;border-radius:6px;padding:6px 10px;cursor:pointer;} button:hover{opacity:0.9;}\n"
            ".results .diff{background:var(--muted);border:1px solid var(--border);border-radius:8px;margin:10px 0;padding:8px;}\n"
            "pre{white-space:pre-wrap;background:#00000022;padding:8px;border-radius:6px;overflow:auto;}\n"
            ".meta{margin-left:10px;color:var(--sub);} .theme-switch{font-size:0.9em;color:var(--sub);} .hl-switch{font-size:0.9em;color:var(--sub);} .rr{display:none;}\n"
            ".toolbar-controls{display:flex;gap:12px;align-items:center;}\n"
            ".kw{color:#c792ea;} .proto{color:#82aaff;} .act{color:#c3e88d;} .addr{color:#f78c6c;} .num{color:#ffcb6b;}\n"
        )


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description='Web UI for access-list inspection/comparison')
    ap.add_argument('--addr', default='127.0.0.1', help='Bind address (default 127.0.0.1)')
    ap.add_argument('--port', type=int, default=8080, help='TCP port (default 8080)')
    ap.add_argument('--configs-cisco', default='configs/cisco', help='Directory with ASA configs')
    ap.add_argument('--configs-fortigate', default='configs/fortigate', help='Directory with FortiGate configs')
    # Robust env parsing for optional overrides
    env_cache_dir = os.environ.get('ACLINSPECTOR_CACHE_DIR', '')
    try:
        env_search_limit = int(os.environ.get('ACLINSPECTOR_SEARCH_LIMIT', '').strip() or '50')
    except Exception:
        env_search_limit = 50
    ap.add_argument('--cache-dir', default=env_cache_dir, help='Disk cache directory (optional; enable by setting a path)')
    ap.add_argument('--search-limit', type=int, default=env_search_limit, help='Default suggestion limit (can be overridden via query)')
    args = ap.parse_args()

    server = HTTPServer((args.addr, args.port), WebHandler)
    server.config_dirs = {
        'asa': args.configs_cisco,
        'fortigate': args.configs_fortigate,
    }
    server.index_cache: Dict[str, dict] = {}
    server.cache_dir = args.cache_dir or None
    server.search_limit = args.search_limit
    print(f"Web UI running at http://{args.addr}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")


if __name__ == '__main__':
    main()
