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
import ipaddress
import plistlib
from typing import Dict, List, Optional, Sequence, Set, Tuple, Union
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from parsers.cisco import asa as asa_parser
from webui.handlers import api as api_handlers

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
        server = type("Srv", (), {"app_state": None})()
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

def index_status_for_tests(cache_dir: Optional[str], index_cache: dict) -> dict:
    """Return index status information for tests and API.

    Structure:
    - in_memory: entries count and up to 20 keys
    - disk: enabled flag, path, files count, optional manifest content
    """
    # In-memory
    mem_keys = sorted(list(index_cache.keys()))[:20]
    mem = {'entries': len(index_cache), 'keys': mem_keys}
    # Disk
    disk = {'enabled': bool(cache_dir), 'path': cache_dir or '', 'files': 0, 'manifest': None}
    if cache_dir:
        try:
            files = [f for f in os.listdir(cache_dir) if os.path.isfile(os.path.join(cache_dir, f)) and f.endswith('.json')]
            disk['files'] = len(files)
        except Exception:
            disk['files'] = 0
        # Optional manifest
        try:
            mf_path = os.path.join(cache_dir, 'manifest.json')
            if os.path.isfile(mf_path):
                with open(mf_path, 'r') as mf:
                    disk['manifest'] = json.load(mf)
        except Exception:
            disk['manifest'] = None
    return {'in_memory': mem, 'disk': disk}


def _vendor_os_tag(vendor: str) -> str:
    vendor = (vendor or '').lower()
    if vendor == 'asa':
        return 'ASA'
    if vendor == 'fortigate':
        return 'FortiOS'
    return vendor.upper() or 'UNKNOWN'


def _channel_to_int(value: Optional[float]) -> int:
    if value is None:
        return 0
    if value > 1.0:
        if value > 255.0:
            value = value / 257.0
        return int(max(0, min(255, round(value))))
    return int(max(0, min(255, round(value * 255.0))))


def _plist_color_to_hex(data: Optional[dict]) -> str:
    if not isinstance(data, dict):
        return "#000000"
    r = _channel_to_int(data.get("Red Component"))
    g = _channel_to_int(data.get("Green Component"))
    b = _channel_to_int(data.get("Blue Component"))
    return "#{:02x}{:02x}{:02x}".format(r, g, b)


def _hex_to_rgb(color: str) -> Tuple[int, int, int]:
    color = color.lstrip("#")
    if len(color) == 3:
        color = "".join(ch * 2 for ch in color)
    if len(color) != 6:
        return (0, 0, 0)
    return tuple(int(color[i : i + 2], 16) for i in range(0, 6, 2))


def _blend_hex(hex_a: str, hex_b: str, ratio: float) -> str:
    ratio = max(0.0, min(1.0, ratio))
    ra, ga, ba = _hex_to_rgb(hex_a)
    rb, gb, bb = _hex_to_rgb(hex_b)
    r = int(round(ra * (1 - ratio) + rb * ratio))
    g = int(round(ga * (1 - ratio) + gb * ratio))
    b = int(round(ba * (1 - ratio) + bb * ratio))
    return "#{:02x}{:02x}{:02x}".format(r, g, b)


DEFAULT_THEMES = [
    {
        "name": "Builtin Dark",
        "kind": "dark",
        "vars": {
            "bg": "#0e1116",
            "muted": "#1a1f29",
            "text": "#e6edf3",
            "sub": "#9da7b3",
            "accent": "#7aa2f7",
            "border": "#2b3240",
            "hl-kw": "#c792ea",
            "hl-proto": "#82aaff",
            "hl-act": "#c3e88d",
            "hl-addr": "#f78c6c",
            "hl-num": "#ffcb6b",
        },
    },
    {
        "name": "Builtin Light",
        "kind": "light",
        "vars": {
            "bg": "#ffffff",
            "muted": "#f6f8fa",
            "text": "#24292f",
            "sub": "#57606a",
            "accent": "#0969da",
            "border": "#d0d7de",
            "hl-kw": "#005cc5",
            "hl-proto": "#0d6efd",
            "hl-act": "#27a744",
            "hl-addr": "#d73a49",
            "hl-num": "#e36209",
        },
    },
]


def load_iterm_theme(path: str) -> Optional[dict]:
    try:
        with open(path, "rb") as fh:
            data = plistlib.load(fh)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    bg = _plist_color_to_hex(data.get("Background Color"))
    fg = _plist_color_to_hex(data.get("Foreground Color"))
    accent = _plist_color_to_hex(
        data.get("Ansi 4 Color")
        or data.get("Cursor Color")
        or data.get("Ansi 6 Color")
    )
    muted = _blend_hex(bg, fg, 0.15)
    sub = _blend_hex(fg, bg, 0.35)
    border = _blend_hex(bg, fg, 0.25)
    luminance = sum(component * weight for component, weight in zip(_hex_to_rgb(bg), (0.2126, 0.7152, 0.0722))) / 255.0
    kind = "light" if luminance > 0.5 else "dark"
    hl_kw = accent or fg
    hl_proto = _blend_hex(accent or fg, fg, 0.5)
    hl_act = _blend_hex("#6cc644", fg, 0.4)
    hl_addr = _blend_hex("#f66a0a", fg, 0.4)
    hl_num = _blend_hex("#ffcb6b", fg, 0.4)
    return {
        "name": os.path.splitext(os.path.basename(path))[0],
        "kind": kind,
        "vars": {
            "bg": bg,
            "muted": muted,
            "text": fg,
            "sub": sub,
            "accent": accent,
            "border": border,
            "hl-kw": hl_kw,
            "hl-proto": hl_proto,
            "hl-act": hl_act,
            "hl-addr": hl_addr,
            "hl-num": hl_num,
        },
    }


def load_themes(theme_dir: str) -> List[dict]:
    themes: List[dict] = []
    if theme_dir and os.path.isdir(theme_dir):
        try:
            for entry in sorted(os.listdir(theme_dir)):
                if not entry.lower().endswith(".itermcolors"):
                    continue
                theme = load_iterm_theme(os.path.join(theme_dir, entry))
                if theme:
                    themes.append(theme)
        except Exception:
            pass
    for default in DEFAULT_THEMES:
        if not any(t["name"] == default["name"] and t["kind"] == default["kind"] for t in themes):
            themes.insert(0, default)
    for default in DEFAULT_THEMES:
        if not any(t["kind"] == default["kind"] for t in themes):
            themes.append(default)
    return themes


def prewarm_all_configs(server) -> int:
    """Eagerly build index cache entries for all known configs."""
    handler = WebHandler.__new__(WebHandler)
    handler.server = server
    total = 0
    for vendor, dirpath in getattr(server, 'config_dirs', {}).items():
        if not dirpath:
            continue
        try:
            entries = list_files(dirpath)
        except Exception:
            continue
        for name in entries:
            path = os.path.join(dirpath, name)
            if not os.path.isfile(path):
                continue
            try:
                handler._get_index(vendor, _vendor_os_tag(vendor), 'auto', path)
                total += 1
            except Exception:
                continue
    return total


def _load_asa_configs(server) -> List[dict]:
    dirpath = getattr(server, 'config_dirs', {}).get('asa')
    if not dirpath:
        return []
    items: List[dict] = []
    for name in list_files(dirpath):
        path = os.path.join(dirpath, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, 'r') as f:
                text = f.read()
        except Exception:
            continue
        try:
            cfg = asa_parser.ASAConfig(text)
        except Exception:
            continue
        items.append({'vendor': 'asa', 'file': name, 'path': path, 'text': text, 'cfg': cfg})
    return items


def list_files(dirpath: str):
    try:
        return sorted(
            [
                f
                for f in os.listdir(dirpath)
                if not f.startswith(".")
                and os.path.isfile(os.path.join(dirpath, f))
            ]
        )
    except FileNotFoundError:
        return []


def format_binding(binding: Optional[dict]) -> str:
    if not binding:
        return ''
    scope = (binding.get('scope') or '').lower()
    direction = binding.get('direction')
    interface = binding.get('interface')
    if scope == 'global':
        return 'global'
    if scope == 'control-plane':
        if interface and direction:
            return f"{interface}({direction},control-plane)"
        return 'control-plane'
    if interface:
        return f"{interface}({direction})" if direction else interface
    return scope or ''

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
        if parsed.path == '/api/index/status':
            return self._api_index_status(parsed.query)
        if parsed.path == '/api/config':
            return self._api_config(parsed.query)
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
        include_any = bool(fields.get('include_any', []))
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

        inspect_target = fields.get('inspect', [''])[0]
        compare_old = fields.get('old', [''])[0]
        compare_new = fields.get('new', [''])[0]
        find_target = fields.get('findq', [''])[0]
        pkt_src_field = fields.get('pkt_src', [''])[0]
        pkt_dst_field = fields.get('pkt_dst', [''])[0]

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
                    target = inspect_target
                    report = asa_parser.inspect_host(cfg_text, target, service_filter=svc_filter, include_any=include_any)
                    # Enrich aliases to include the target object as well
                    try:
                        cfg = asa_parser.ASAConfig(cfg_text)
                        nets = cfg.resolve_network(target)
                        inclusive = {}
                        for n in nets:
                            names = cfg.ip_to_objects.get(n, set()) if hasattr(cfg, 'ip_to_objects') else set()
                            if names:
                                inclusive[n] = names
                        report['aliases'] = inclusive
                    except Exception:
                        pass
                    body = self._render_report(target, report, cfg_file)
                elif mode == 'compare':
                    old = compare_old
                    new = compare_new
                    diff = asa_parser.compare_old_new(cfg_text, old, new, service_filter=svc_filter, include_any=include_any)
                    # Build alias boxes for old/new (inclusive of target names)
                    cfg = asa_parser.ASAConfig(cfg_text)
                    def _incl(name):
                        out = {}
                        nets = cfg.resolve_network(name)
                        for n in nets:
                            names = cfg.ip_to_objects.get(n, set()) if hasattr(cfg, 'ip_to_objects') else set()
                            if names:
                                out[n] = names
                        return out
                    old_aliases = _incl(old) if old else {}
                    new_aliases = _incl(new) if new else {}
                    body = self._render_diff(old, new, diff, cfg_file, old_aliases=old_aliases, new_aliases=new_aliases)
                elif mode == 'find':
                    target = find_target
                    results = self._find_host(target)
                    body = self._render_find(target, results)
                elif mode == 'packet':
                    src = pkt_src_field
                    dst = pkt_dst_field
                    dps = set()
                    for dp in dports_clean:
                        dps.add(dp)
                    pkt = self._packet_check_asa(cfg_text, src, dst, proto or None, dps)
                    body = self._render_packet(cfg_file, pkt)
                else:
                    body = "<p style='color:red'>Unsupported mode.</p>"
                app_state = getattr(self.server, 'app_state', None)
                if app_state is not None:
                    query = ''
                    tab = 'rules'
                    if mode == 'inspect':
                        query = target
                    elif mode == 'compare':
                        query = f"{compare_old}->{compare_new}"
                    elif mode == 'find':
                        tab = 'find'
                        query = find_target
                    elif mode == 'packet':
                        tab = 'packet'
                        query = f"{pkt_src_field}->{pkt_dst_field}"
                    if query:
                        app_state.history.record(tab, query)
                self._html(self._form() + body)
            except Exception as e:
                self._html(f"<p style='color:red'>Error: {e}</p>" + self._form())
        else:
            self._html("<p>Vendor not implemented.</p>" + self._form())

    # ------------ render helpers ------------
    def _form(self):
        asa_opts = "\n".join(["<option value='{}'>{}</option>".format(x, x) for x in list_files(self.server.config_dirs.get('asa', 'configs/cisco'))])
        ftg_opts = "\n".join(["<option value='{}'>{}</option>".format(x, x) for x in list_files(self.server.config_dirs.get('fortigate', 'configs/fortigate'))])
        css = self._css()
        themes = getattr(self.server, 'themes', DEFAULT_THEMES)
        themes_json = json.dumps(themes).replace('</', '<\\/')
        return (
            "<!doctype html>\n"
            "<html><head><meta charset='utf-8'><title>ACL Inspector</title><style>" + css + "</style></head>\n"
            "<body class='theme-dark'>\n"
            "  <div class='app'>\n"
            "  <div class='toolbar'><h2>ACL Inspector</h2><div class='toolbar-controls'><label class='theme-switch'><input type='checkbox' id='themeToggle'/> Light mode</label> <label class='hl-switch'><input type='checkbox' id='hlToggle'/> Highlight output</label> <button type='button' id='histToggle'>History</button></div></div>\n"
            "  <div class='tab-shell'>\n"
            "    <div class='mode-tabs'>\n"
            "      <button type='button' class='tab active' data-tab='rules'>Inspect / Compare</button>\n"
            "      <button type='button' class='tab' data-tab='find'>Find host</button>\n"
            "      <button type='button' class='tab' data-tab='packet'>Packet check</button>\n"
            "      <button type='button' class='tab' data-tab='config'>Config</button>\n"
            "      <button type='button' class='tab' data-tab='prefs'>Preferences</button>\n"
            "      <button type='button' class='tab' data-tab='about'>About</button>\n"
            "    </div>\n"
            "    <form class='form' method='POST' action='/run'>\n"
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
            "    <input type='hidden' name='mode' id='mode' value='inspect'/>\n"
            "    <div class='search-options global-search'><label><input type='checkbox' id='fuzzy' checked/> Fuzzy search</label></div>\n"
            "    <div class='tab-panels'>\n"
            "      <section id='tab-rules' class='tab-panel active'>\n"
            "        <fieldset class='section section-mode-rules'><legend>Rule Mode</legend>\n"
            "          <div class='radio-group'>\n"
            "            <label><input type='radio' name='rule_mode' value='inspect' checked/> Inspect</label>\n"
            "            <label><input type='radio' name='rule_mode' value='compare'/> Compare</label>\n"
            "          </div>\n"
            "        </fieldset>\n"
            "        <fieldset class='section section-targets'><legend>Targets</legend>\n"
            "          <div id='inspect_fields'>\n"
            "            <label>Inspect target:</label>\n"
            "            <input type='text' name='inspect' id='inspect' list='targets' autocomplete='off' placeholder='name|ip|cidr'/>\n"
            "          </div>\n"
            "          <div id='compare_fields' style='display:none'>\n"
            "            <label>Old target:</label>\n"
            "            <input type='text' name='old' id='old' list='targets' autocomplete='off' placeholder='name|ip|cidr'/>\n"
            "            <label>New target:</label>\n"
            "            <input type='text' name='new' id='new' list='targets' autocomplete='off' placeholder='name|ip|cidr'/>\n"
            "          </div>\n"
            "          <datalist id='targets'></datalist>\n"
            "        </fieldset>\n"
            "      </section>\n"
            "      <section id='tab-find' class='tab-panel'>\n"
            "        <fieldset class='section section-find'><legend>Find Host</legend>\n"
            "          <label>Find host (object or IP):</label>\n"
            "          <input type='text' name='findq' id='findq' list='targets' autocomplete='off' placeholder='name|ip|cidr'/>\n"
            "        </fieldset>\n"
            "      </section>\n"
            "      <section id='tab-packet' class='tab-panel'>\n"
            "        <fieldset class='section section-packet'><legend>Packet Check</legend>\n"
            "          <label>Source:</label>\n"
            "          <input type='text' name='pkt_src' id='pkt_src' list='targets' autocomplete='off' placeholder='name|ip|cidr'/>\n"
            "          <label>Destination:</label>\n"
            "          <input type='text' name='pkt_dst' id='pkt_dst' list='targets' autocomplete='off' placeholder='name|ip|cidr'/>\n"
            "        </fieldset>\n"
            "      </section>\n"
            "      <section id='tab-config' class='tab-panel'>\n"
            "        <fieldset class='section section-config-view'><legend>Config Viewer</legend>\n"
            "          <div class='config-select'><label>Config:</label><select id='config_select_tab'>\n"
            + asa_opts +
            "          </select></div>\n"
            "          <label>Search:</label>\n"
            "          <input type='text' id='config_filter' placeholder='filter text' autocomplete='off'/>\n"
            "          <div class='config-meta'>Showing <span id='config_name_display'>n/a</span></div>\n"
            "          <pre id='config_viewer' data-lang='asa'></pre>\n"
            "        </fieldset>\n"
            "      </section>\n"
            "      <section id='tab-prefs' class='tab-panel'>\n"
            "        <fieldset class='section section-preferences'><legend>Preferences</legend>\n"
            "          <div class='theme-control'>\n"
            "            <label for='theme_dark'>Dark theme:</label>\n"
            "            <select id='theme_dark'></select>\n"
            "            <div id='preview_dark' class='theme-preview'></div>\n"
            "          </div>\n"
            "          <div class='theme-control'>\n"
            "            <label for='theme_light'>Light theme:</label>\n"
            "            <select id='theme_light'></select>\n"
            "            <div id='preview_light' class='theme-preview'></div>\n"
            "          </div>\n"
            "          <p class='pref-note'>Theme choices are remembered in a cookie so your dark/light toggle keeps the look you pick.</p>\n"
            "        </fieldset>\n"
            "      </section>\n"
            "      <section id='tab-about' class='tab-panel'>\n"
            "        <fieldset class='section section-about'><legend>About</legend>\n"
            "          <p>Access-List Inspector parses Cisco ASA configurations to inspect ACL impact, compare objects, and surface duplicates.</p>\n"
            "          <p>Source and documentation: <a href='https://github.com/mbadolato/iTerm2-Color-Schemes' target='_blank' rel='noopener'>iTerm2-Color-Schemes</a> for theming data.</p>\n"
            "          <p>Current workspace dir: <code>" + os.getcwd() + "</code></p>\n"
            "        </fieldset>\n"
            "      </section>\n"
            "    </div>\n"
            "    <fieldset class='section section-service' id='service_filters'><legend>Service Filter</legend>\n"
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
            "    <label id='include_any_label'><input type='checkbox' name='include_any' id='include_any'/> Include rules with 'any' <span class='tip' title='By default, rules with any src/dst are skipped to reduce noise. Check to include them.'>?</span></label>\n"
            "    </fieldset>\n"
            "    <div class='actions' id='run_actions'><button type='submit'>Run</button></div>\n"
            "  </form>\n"
            "  </div>\n"
            "  <aside id='history' class='history' style='display:none'></aside>\n"
            "  </div>\n"
            "  <script>\n"
            "    const THEMES=" + themes_json + ";\n"
            "    const PREF_COOKIE='acl_theme_pref';\n"
            "    const THEME_KEY='acl_theme';\n"
            "    const HL_KEY='acl_highlight';\n"
            "    const HIST_VIS_KEY='acl_history_visible';\n"
            "    let activeTab='rules';\n"
            "    let stateGuard=false;\n"
            "    let themePref={};\n"
            "    function storageGet(key, fallback){\n"
            "      try{if(typeof window!=='undefined' && 'localStorage' in window){const v=window.localStorage.getItem(key); return (v===null||v===undefined)?fallback:v;}}catch(e){}\n"
            "      return fallback;\n"
            "    }\n"
            "    function storageSet(key, value){\n"
            "      try{if(typeof window!=='undefined' && 'localStorage' in window){window.localStorage.setItem(key, value);}}catch(e){}\n"
            "    }\n"
            "    function cookieGet(name){\n"
            "      if(typeof document==='undefined'){return null;}\n"
            "      const match = document.cookie.match(new RegExp('(?:^|; )'+name+'=([^;]*)'));\n"
            "      return match ? decodeURIComponent(match[1]) : null;\n"
            "    }\n"
            "    function cookieSet(name, value){\n"
            "      if(typeof document==='undefined'){return;}\n"
            "      const ttl=60*60*24*365;\n"
            "      document.cookie = `${name}=${encodeURIComponent(value)};path=/;max-age=${ttl}`;\n"
            "    }\n"
            "    function loadThemePrefs(){\n"
            "      try{return JSON.parse(cookieGet(PREF_COOKIE)||'{}')||{};}catch(e){return {};}\n"
            "    }\n"
            "    function saveThemePrefs(){\n"
            "      try{cookieSet(PREF_COOKIE, JSON.stringify(themePref));}catch(e){}\n"
            "    }\n"
            "    function themeByName(name, kind){\n"
            "      return THEMES.find(t=>t.name===name && (!kind || t.kind===kind));\n"
            "    }\n"
            "    function ensureThemePref(){\n"
            "      ['dark','light'].forEach(kind=>{\n"
            "        const available = THEMES.filter(t=>t.kind===kind);\n"
            "        if(!available.length){\n"
            "          return;\n"
            "        }\n"
            "        const current = themePref[kind];\n"
            "        if(!current || !themeByName(current, kind)){\n"
            "          themePref[kind] = available[0].name;\n"
            "        }\n"
            "      });\n"
            "    }\n"
            "    function themeForKind(kind){\n"
            "      ensureThemePref();\n"
            "      return themeByName(themePref[kind], kind) || THEMES.find(t=>t.kind===kind) || THEMES[0];\n"
            "    }\n"
            "    function applyThemeVars(theme){\n"
            "      if(!theme || !theme.vars){return;}\n"
            "      const root=document.documentElement;\n"
            "      for(const [key,val] of Object.entries(theme.vars)){\n"
            "        root.style.setProperty(`--${key}`, val);\n"
            "      }\n"
            "    }\n"
            "    function updateThemePreview(kind){\n"
            "      const tgt=document.getElementById(kind==='light'?'preview_light':'preview_dark');\n"
            "      if(!tgt){return;}\n"
            "      const theme=themeForKind(kind);\n"
            "      if(!theme){return;}\n"
            "      tgt.style.background = theme.vars.bg;\n"
            "      tgt.style.color = theme.vars.text;\n"
            "      tgt.style.borderColor = theme.vars.border;\n"
            "      tgt.textContent = theme.name;\n"
            "    }\n"
            "    function populateThemeSelect(kind){\n"
            "      const select=document.getElementById(kind==='light'?'theme_light':'theme_dark');\n"
            "      if(!select){return;}\n"
            "      const themes = THEMES.filter(t=>t.kind===kind);\n"
            "      select.innerHTML='';\n"
            "      themes.forEach(t=>{\n"
            "        const opt=document.createElement('option');\n"
            "        opt.value=t.name;\n"
            "        opt.textContent=t.name;\n"
            "        select.appendChild(opt);\n"
            "      });\n"
            "      ensureThemePref();\n"
            "      if(themePref[kind] && themeByName(themePref[kind], kind)){\n"
            "        select.value=themePref[kind];\n"
            "      }\n"
            "      select.onchange = (ev)=>{\n"
            "        themePref[kind] = ev.target.value;\n"
            "        ensureThemePref();\n"
            "        saveThemePrefs();\n"
            "        applyTheme();\n"
            "        updateThemePreview(kind);\n"
            "      };\n"
            "      updateThemePreview(kind);\n"
            "    }\n"
            "    function populateThemeSelectors(){\n"
            "      populateThemeSelect('dark');\n"
            "      populateThemeSelect('light');\n"
            "    }\n"
            "    function applyTheme(){\n"
            "      const mode=storageGet(THEME_KEY,'dark')||'dark';\n"
            "      const theme=themeForKind(mode==='light'?'light':'dark');\n"
            "      applyThemeVars(theme);\n"
            "      document.documentElement.setAttribute('data-theme', mode);\n"
            "      document.body.classList.toggle('theme-light', mode==='light');\n"
            "      document.body.classList.toggle('theme-dark', mode!=='light');\n"
            "      const t=document.getElementById('themeToggle'); if(t){t.checked = (mode==='light');}\n"
            "      updateThemePreview('dark');\n"
            "      updateThemePreview('light');\n"
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
            "    function rawText(pre){\n"
            "      if(!pre.dataset.raw){\n"
            "        pre.dataset.raw = pre.textContent || '';\n"
            "      }\n"
            "      return pre.dataset.raw;\n"
            "    }\n"
            "    function highlightAll(on){\n"
            "      const pres=document.querySelectorAll('pre[data-lang=\\'asa\\']');\n"
            "      for(const pre of pres){\n"
            "        const raw=rawText(pre);\n"
            "        if(!on){ pre.textContent = raw; continue;}\n"
            "        const lines=raw.split(/\\n/).map(hlASA);\n"
            "        pre.innerHTML = lines.join('\\n');\n"
            "      }\n"
            "    }\n"
            "    let configCache={};\n"
            "    let currentConfigTab='';\n"
            "    function setConfigViewer(text,name){\n"
            "      const pre=document.getElementById('config_viewer'); if(!pre){return;}\n"
            "      pre.dataset.raw = text||'';\n"
            "      const display=document.getElementById('config_name_display'); if(display){display.textContent=name||'n/a';}\n"
            "      applyConfigFilter();\n"
            "    }\n"
            "    function applyConfigFilter(){\n"
            "      const pre=document.getElementById('config_viewer'); if(!pre){return;}\n"
            "      const raw=pre.dataset.raw||'';\n"
            "      const query=(document.getElementById('config_filter')?.value||'').trim().toLowerCase();\n"
            "      if(!query){pre.textContent = raw;} else {pre.textContent = raw.split(/\\n/).filter(line=>line.toLowerCase().includes(query)).join('\\n');}\n"
            "      highlightAll((storageGet(HL_KEY,'on')||'on')==='on');\n"
            "    }\n"
            "    async function loadConfigText(name){\n"
            "      const select=document.getElementById('config_select_tab');\n"
            "      if(!name && select){name=select.value;}\n"
            "      if(!name){return;}\n"
            "      currentConfigTab=name;\n"
            "      if(configCache[name]){setConfigViewer(configCache[name], name); return;}\n"
            "      try{const resp=await fetch(`/api/config?vendor=asa&config=${encodeURIComponent(name)}`); if(!resp.ok){return;} const data=await resp.json(); configCache[name]=data.text||''; setConfigViewer(configCache[name], data.config||name);}catch(e){}\n"
            "    }\n"
            "    function toggleVendor(){\n"
            "      var v = document.getElementById('vendor').value;\n"
            "      document.getElementById('asa_cfg').style.display = (v==='asa') ? 'block':'none';\n"
            "      document.getElementById('ftg_cfg').style.display = (v==='fortigate') ? 'block':'none';\n"
            "      configCache={};\n"
            "      const cfgSelectTab=document.getElementById('config_select_tab'); const cfgMain=document.getElementById('config');\n"
            "      if(cfgSelectTab && cfgMain){cfgSelectTab.value=cfgMain.value; if(activeTab==='config'){loadConfigText(cfgSelectTab.value);}}\n"
            "    }\n"
            "    function setMode(mode){\n"
            "      const hidden=document.getElementById('mode');\n"
            "      if(hidden){hidden.value = mode;}\n"
            "      if(mode==='inspect' || mode==='compare'){\n"
            "        const radio=document.querySelector(`input[name='rule_mode'][value='${mode}']`);\n"
            "        if(radio && !radio.checked){radio.checked=true;}\n"
            "      }\n"
            "      updateRuleModeUI(mode);\n"
            "    }\n"
            "    function updateRuleModeUI(mode){\n"
            "      const inspect=document.getElementById('inspect_fields');\n"
            "      const compare=document.getElementById('compare_fields');\n"
            "      if(inspect){inspect.style.display = (mode==='inspect') ? 'block':'none';}\n"
            "      if(compare){compare.style.display = (mode==='compare') ? 'block':'none';}\n"
            "    }\n"
            "    function activateTab(tab, suppressSave){\n"
            "      activeTab = tab;\n"
            "      const panels=document.querySelectorAll('.tab-panel');\n"
            "      panels.forEach(p=>p.classList.toggle('active', p.id===`tab-${tab}`));\n"
            "      const buttons=document.querySelectorAll('.mode-tabs .tab');\n"
            "      buttons.forEach(btn=>btn.classList.toggle('active', btn.dataset.tab===tab));\n"
            "      const service=document.getElementById('service_filters');\n"
            "      const includeAnyLabel=document.getElementById('include_any_label');\n"
            "      const cfgSection=document.querySelector('.section-config');\n"
            "      if(cfgSection){cfgSection.style.display = (tab==='rules'||tab==='packet') ? 'block':'none';}\n"
            "      const searchRow=document.querySelector('.global-search');\n"
            "      if(searchRow){searchRow.style.display = (tab==='rules') ? 'block' : 'none';}\n"
            "      document.querySelectorAll('.results[data-tab]').forEach(panel=>{panel.style.display = (panel.dataset.tab===tab)?'block':'none';});\n"
            "      const runActions=document.getElementById('run_actions'); if(runActions){runActions.style.display = (['rules','find','packet'].includes(tab))?'block':'none';}\n"
            "      if(tab==='rules'){\n"
            "        const selected=document.querySelector(\"input[name='rule_mode']:checked\");\n"
            "        const chosen=selected?selected.value:'inspect';\n"
            "        setMode(chosen);\n"
            "        if(service){service.style.display='block';}\n"
            "        if(includeAnyLabel){includeAnyLabel.style.display='inline-flex';}\n"
            "      }else if(tab==='find'){\n"
            "        setMode('find');\n"
            "        if(service){service.style.display='none';}\n"
            "        if(includeAnyLabel){includeAnyLabel.style.display='none';}\n"
            "      }else if(tab==='packet'){\n"
            "        setMode('packet');\n"
            "        if(service){service.style.display='block';}\n"
            "        if(includeAnyLabel){includeAnyLabel.style.display='none';}\n"
            "      }else{\n"
            "        if(service){service.style.display='none';}\n"
            "        if(includeAnyLabel){includeAnyLabel.style.display='none';}\n"
            "      }\n"
            "      if(tab==='config'){loadConfigText(currentConfigTab);}\n"
            "      if(!suppressSave){saveState();}\n"
            "      setTimeout(()=>highlightAll((storageGet(HL_KEY,'on')||'on')==='on'),0);\n"
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
"      if(activeTab!=='rules'){fillDatalist([]);return;}\n"
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
"      for(const id of ['inspect','old','new','pkt_src','pkt_dst','findq']){const el=document.getElementById(id); if(el){el.addEventListener('input',fetchSuggest);}}\n"
            "    }\n"
            "    function saveState(){\n"
            "      if(stateGuard){return;}\n"
            "      const ruleSelected=document.querySelector(\"input[name='rule_mode']:checked\");\n"
            "      const st={vendor:document.getElementById('vendor').value,mode:document.getElementById('mode')?document.getElementById('mode').value:'inspect',rule_mode:ruleSelected?ruleSelected.value:'inspect',tab:activeTab,config:document.getElementById('config')?document.getElementById('config').value:'',config_ftg:document.getElementById('config_ftg')?document.getElementById('config_ftg').value:'',inspect:document.getElementById('inspect')?document.getElementById('inspect').value:'',old:document.getElementById('old')?document.getElementById('old').value:'',new:document.getElementById('new')?document.getElementById('new').value:'',findq:document.getElementById('findq')?document.getElementById('findq').value:'',pkt_src:document.getElementById('pkt_src')?document.getElementById('pkt_src').value:'',pkt_dst:document.getElementById('pkt_dst')?document.getElementById('pkt_dst').value:'',proto:document.querySelector(\"select[name='proto']\")?document.querySelector(\"select[name='proto']\").value:'',dport:document.querySelector(\"input[name='dport']\")?document.querySelector(\"input[name='dport']\").value:'',include_any:document.getElementById('include_any')?document.getElementById('include_any').checked:false,fuzzy:document.getElementById('fuzzy')?document.getElementById('fuzzy').checked:true};\n"
            "      storageSet('acl_state', JSON.stringify(st));\n"
            "      const cfgSelectTab=document.getElementById('config_select_tab'); if(cfgSelectTab && document.getElementById('config')){cfgSelectTab.value=document.getElementById('config').value;}\n"
            "    }\n"
            "    function applyState(st, suppressSave){\n"
            "      if(!st||typeof st!=='object') return;\n"
            "      stateGuard = true;\n"
            "      try{\n"
            "        if(st.vendor && document.getElementById('vendor')){document.getElementById('vendor').value=st.vendor;}\n"
            "        toggleVendor();\n"
            "        if(st.config&&document.getElementById('config')){document.getElementById('config').value=st.config;}\n"
            "        const cfgSelectTab=document.getElementById('config_select_tab'); if(st.config && cfgSelectTab){cfgSelectTab.value=st.config;}\n"
            "        if(st.config_ftg&&document.getElementById('config_ftg')){document.getElementById('config_ftg').value=st.config_ftg;}\n"
            "        if(st.inspect&&document.getElementById('inspect')){document.getElementById('inspect').value=st.inspect;}\n"
            "        if(st.old&&document.getElementById('old')){document.getElementById('old').value=st.old;}\n"
            "        if(st.new&&document.getElementById('new')){document.getElementById('new').value=st.new;}\n"
            "        if(st.findq&&document.getElementById('findq')){document.getElementById('findq').value=st.findq;}\n"
            "        if(st.pkt_src&&document.getElementById('pkt_src')){document.getElementById('pkt_src').value=st.pkt_src;}\n"
            "        if(st.pkt_dst&&document.getElementById('pkt_dst')){document.getElementById('pkt_dst').value=st.pkt_dst;}\n"
            "        if(st.proto&&document.querySelector(\"select[name='proto']\")){document.querySelector(\"select[name='proto']\").value=st.proto;}\n"
            "        if(typeof st.include_any==='boolean' && document.getElementById('include_any')){document.getElementById('include_any').checked=st.include_any;}\n"
            "        if(typeof st.fuzzy==='boolean' && document.getElementById('fuzzy')){document.getElementById('fuzzy').checked=st.fuzzy;}\n"
            "        if(st.dport&&document.querySelector(\"input[name='dport']\")){document.querySelector(\"input[name='dport']\").value=st.dport;}\n"
            "        const ruleMode = st.rule_mode || ((st.mode==='inspect'||st.mode==='compare') ? st.mode : 'inspect');\n"
            "        if(ruleMode){const radio=document.querySelector(`input[name='rule_mode'][value='${ruleMode}']`); if(radio){radio.checked=true;}}\n"
            "        let desiredTab = st.tab;\n"
            "        if(!desiredTab){\n"
            "          if(st.mode==='find') desiredTab='find';\n"
            "          else if(st.mode==='packet') desiredTab='packet';\n"
            "          else desiredTab='rules';\n"
            "        }\n"
            "        if(!['rules','find','packet','prefs'].includes(desiredTab)) desiredTab='rules';\n"
            "        activateTab(desiredTab, true);\n"
            "        setTimeout(()=>highlightAll((storageGet(HL_KEY,'on')||'on')==='on'),0);\n"
            "      }catch(e){}\n"
            "      finally{\n"
            "        stateGuard = false;\n"
            "      }\n"
            "      if(!suppressSave){saveState();}\n"
            "    }\n"
            "    function loadState(){\n"
            "      try{const st=JSON.parse(storageGet('acl_state','{}')||'{}'); applyState(st, true);}catch(e){}\n"
            "    }\n"
            "    function attachStateHandlers(){\n"
            "      for(const sel of ['vendor','config','config_ftg','inspect','old','new','findq','pkt_src','pkt_dst','include_any','fuzzy']){const el=document.getElementById(sel); if(el){el.addEventListener('change',saveState); el.addEventListener('input',saveState);}}\n"
            "      const ps=document.querySelector(\"select[name='proto']\"); if(ps){ps.addEventListener('change',saveState);}\n"
            "      const dp=document.querySelector(\"input[name='dport']\"); if(dp){dp.addEventListener('input',saveState);}\n"
            "      document.querySelectorAll(\"input[name='rule_mode']\").forEach(radio=>{\n"
            "        radio.addEventListener('change', (e)=>{setMode(e.target.value); saveState();});\n"
            "      });\n"
            "      const cfgSelectTab=document.getElementById('config_select_tab'); if(cfgSelectTab){cfgSelectTab.addEventListener('change', ()=>{loadConfigText(cfgSelectTab.value);});}\n"
            "      const cfgFilter=document.getElementById('config_filter'); if(cfgFilter){cfgFilter.addEventListener('input', ()=>applyConfigFilter()); cfgFilter.addEventListener('keydown',(ev)=>{if(ev.key==='Enter'){ev.preventDefault();}});}\n"
            "    }\n"
            "    function setHistoryVisibility(show, skipSave){\n"
            "      const el=document.getElementById('history');\n"
            "      if(!el){return;}\n"
            "      el.dataset.wantVisible = show ? '1':'0';\n"
            "      const hasEntries = el.dataset.hasEntries === '1';\n"
            "      el.style.display = (show && hasEntries) ? 'block':'none';\n"
            "      if(!skipSave){storageSet(HIST_VIS_KEY, show?'on':'off');}\n"
            "    }\n"
            "    function addToHistory(){try{saveState(); const h=JSON.parse(storageGet('acl_history','[]')||'[]'); const st=JSON.parse(storageGet('acl_state','{}')||'{}'); h.unshift({t:Date.now(),st}); storageSet('acl_history', JSON.stringify(h.slice(0,50))); renderHistory();}catch(e){}}\n"
            "    function renderHistory(){try{const h=JSON.parse(storageGet('acl_history','[]')||'[]'); const el=document.getElementById('history'); if(!el) return; el.innerHTML='<h3>History</h3>' + h.map(x=>{const s=x.st||{}; const payload=encodeURIComponent(JSON.stringify(s)); return `<button type=\"button\" class=\"hist-entry\" data-state=\"${payload}\"><div class=\"hist-time\">${new Date(x.t).toLocaleString()}</div><div class=\"hist-desc\">${s.mode||''} ${s.inspect||s.old||''}${s.new?(' -> '+s.new):''}</div></button>`}).join(''); el.dataset.hasEntries = h.length ? '1':'0'; const want=(storageGet(HIST_VIS_KEY,'off')==='on'); setHistoryVisibility(want, true);}catch(e){} }\n"
            "    document.addEventListener('DOMContentLoaded', ()=>{const f=document.querySelector('form.form'); if(f){f.addEventListener('submit', addToHistory);}});\n"
            "    async function refreshMeta(){\n"
            "      const {vendor,config}=currentConfig();\n"
            "      const el=document.getElementById('meta'); el.textContent='';\n"
            "      if(!config){return;}\n"
            "      try{const r=await fetch(`/api/meta?vendor=${vendor}&config=${encodeURIComponent(config)}`); if(r.ok){const j=await r.json(); el.textContent = `OS: ${j.os||vendor.toUpperCase()}  Version: ${j.version||'unknown'}`;}}catch(e){}\n"
            "    }\n"
            "    document.querySelectorAll('.mode-tabs .tab').forEach(btn=>{btn.addEventListener('click', ()=>activateTab(btn.dataset.tab));});\n"
            "    themePref = loadThemePrefs(); ensureThemePref(); saveThemePrefs(); populateThemeSelectors();\n"
            "    const themeToggle=document.getElementById('themeToggle'); if(themeToggle){themeToggle.addEventListener('change', (e)=>{const mode=e.target.checked?'light':'dark'; storageSet(THEME_KEY, mode); applyTheme();});}\n"
            "    const hlToggle=document.getElementById('hlToggle'); if(hlToggle){hlToggle.addEventListener('change', (e)=>{const on=e.target.checked?'on':'off'; storageSet(HL_KEY, on); highlightAll(on==='on');});}\n"
            "    const hist = document.getElementById('history');\n"
            "    const histToggle=document.getElementById('histToggle'); if(histToggle){histToggle.addEventListener('click', ()=>{const want = storageGet(HIST_VIS_KEY,'off')==='on'; setHistoryVisibility(!want, false);});}\n"
            "    if(hist){hist.addEventListener('click', (ev)=>{const btn=ev.target.closest('.hist-entry'); if(!btn) return; ev.preventDefault(); try{const st=JSON.parse(decodeURIComponent(btn.dataset.state||'{}')); applyState(st, false);}catch(e){}});}\n"
            "    applyTheme(); activateTab(activeTab, true); loadState(); toggleVendor(); attachTypeahead(); attachStateHandlers(); refreshMeta(); const hlOn=(storageGet(HL_KEY,'on')||'on')==='on'; highlightAll(hlOn); if(hlToggle){hlToggle.checked = hlOn;} renderHistory(); saveState(); loadConfigText(currentConfigTab || document.getElementById('config_select_tab')?.value || '');\n"
            "  </script>\n"
            "</body></html>\n"
        )

    def _render_report(self, target, report, cfg_file):
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
<div class='results results-rules' data-tab='rules'>
  <div class='section'><h2>{cfg_file}</h2><h3>Inspection Report for {target}</h3>
  <p>Resolved to: {', '.join(str(n) for n in report['target_nets'])}</p>
  <p>Found {len(report['hits'])} matching ACL entries.</p></div>
  {alias_html}
  <div class='diff diff-raw'><h3>Matched Rules (Raw)</h3>
  <pre data-lang='asa'>{lines_raw}</pre></div>
  <div class='diff diff-flattened'><h3>Matched Rules (Flattened)</h3>
  <pre data-lang='asa'>{lines_flat}</pre></div>
</div>
"""

    def _render_diff(self, old, new, diff, cfg_file, old_aliases=None, new_aliases=None):
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
<div class='results results-rules' data-tab='rules'>
  <div class='section'><h2>{cfg_file}</h2><h3>Comparison</h3>
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

    def _render_find(self, target: str, results: list) -> str:
        if not target:
            return "<div class='results results-find' data-tab='find'><div class='section'><h3>Find Host</h3><p>No target provided.</p></div></div>"
        if not results:
            return f"<div class='results results-find' data-tab='find'><div class='section'><h3>Find Host</h3><p>No matches for {target}.</p></div></div>"
        blocks: List[str] = []
        for idx, entry in enumerate(results[:200]):
            header = f"{entry['vendor'].upper()} {entry['file']}"
            if entry.get('best'):
                header += "  ← best match"
            lines = [header]
            if entry.get('objects'):
                lines.append("  Objects: " + ', '.join(entry['objects']))
            if entry.get('literals'):
                lines.append("  Resolved IPs: " + ', '.join(entry['literals']))
            if entry.get('interfaces'):
                lines.append("  Interfaces: " + ', '.join(entry['interfaces']))
            if entry.get('text_hit'):
                lines.append("  (config text contains query)")
            blocks.append("\n".join(lines))
        return "<div class='results results-find' data-tab='find'><div class='section'><h3>Find Host Results</h3><pre data-lang='asa'>" + "\n\n".join(blocks) + "</pre></div></div>"

    def _find_host(self, target: str) -> List[dict]:
        query = (target or '').strip()
        if not query:
            return []
        data = _load_asa_configs(self.server)
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
                cfg = entry['cfg']
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
                    resolved = entry['cfg'].resolve_network(query)
                except Exception:
                    resolved = set()
                before = len(nets)
                nets.update(resolved)
                if len(nets) > before:
                    changed = True

        # Final sweep to ensure names derived from newly added nets are included
        for entry in data:
            cfg = entry['cfg']
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
            cfg = entry['cfg']
            text_lower = entry['text'].lower()
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
                ipv4_val = meta.get('ipv4')
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

            if not (matched_objects or matched_literals or text_hit):
                continue

            results.append({
                'vendor': entry['vendor'],
                'file': entry['file'],
                'objects': sorted(matched_objects),
                'literals': sorted(matched_literals),
                'interfaces': sorted(interface_hits),
                'text_hit': text_hit,
                'score': score,
                'direct': direct_object,
            })

        if not results:
            return []

        results.sort(key=lambda r: (-r['score'], -len(r['interfaces']), -len(r['objects']), r['file']))
        for r in results:
            r['best'] = False
        if results and results[0]['score'] > 0:
            results[0]['best'] = True
        return results

    def _render_packet(self, cfg_file: str, pkt: dict) -> str:
        if pkt.get('error'):
            return (
                "<div class='results results-packet' data-tab='packet'>\n"
                f"  <div class='section'><h2>{cfg_file}</h2><h3>Packet Check</h3>\n"
                f"  <p style='color:red'>Error: {pkt.get('error')}</p></div>\n"
                "</div>\n"
            )
        status = 'ALLOWED' if pkt.get('allowed') else 'BLOCKED'
        inp = pkt.get('input', {})
        resolved = pkt.get('resolved', {})
        nat = pkt.get('nat', {})
        acl = pkt.get('acl', {})
        context = pkt.get('context', {})
        matches = acl.get('matches', [])
        lines = []
        for item in matches[:200]:
            summary = item.get('summary') or ''
            lines.append(f"  {item.get('raw')}\n   -> {summary}")
        content = "\n".join(lines) if lines else "  (no ACL matches)"
        nat_trans = nat.get('translations', {})
        src_nat = nat_trans.get('src', {})
        dst_nat = nat_trans.get('dst', {})
        nat_lines = []
        if nat.get('applied'):
            rule = nat.get('rule') or {}
            nat_lines.append(f"Rule: {rule.get('raw', 'unknown')}")
            nat_lines.append(f"Source: {src_nat.get('before')} -> {src_nat.get('after')}")
            if src_nat.get('note'):
                nat_lines.append(f"  note: {src_nat.get('note')}")
            if dst_nat.get('after') and dst_nat.get('after') != dst_nat.get('before'):
                nat_lines.append(f"Destination: {dst_nat.get('before')} -> {dst_nat.get('after')}")
                if dst_nat.get('note'):
                    nat_lines.append(f"  note: {dst_nat.get('note')}")
        else:
            nat_lines.append("No NAT rule matched.")
        nat_block = "\n".join(nat_lines)
        cand_lines = []
        for cand in context.get('acl_candidates', []):
            iface = cand.get('interface') or 'global'
            direction = cand.get('direction') or '*'
            cand_lines.append(f"  {iface} ({direction})")
        candidate_block = ""
        if cand_lines:
            cand_text = "\n".join(cand_lines)
            candidate_block = (
                "  <div class='diff diff-aliases'><h3>ACL Candidate Bindings</h3>\n"
                f"  <pre>{cand_text}</pre></div>\n"
            )
        return (
            "<div class='results results-packet' data-tab='packet'>\n"
            f"  <div class='section'><h2>{cfg_file}</h2><h3>Packet Check</h3>\n"
            f"  <p>Status: {status} (NAT direction: {nat.get('direction') or 'n/a'})</p>\n"
            f"  <p>Input: src={inp.get('src','')} dst={inp.get('dst','')} proto={inp.get('proto') or 'any'} dports={inp.get('dports') or 'any'}</p>\n"
            f"  <p>Resolved: src={resolved.get('src')} -> {resolved.get('post_nat_src')} | dst={resolved.get('dst')} -> {resolved.get('post_nat_dst')}</p></div>\n"
            "  <div class='diff diff-added'><h3>NAT Evaluation</h3>\n"
            f"  <pre>{nat_block}</pre></div>\n"
            f"{candidate_block}"
            "  <div class='diff diff-raw'><h3>ACL Matches</h3>\n"
            f"  <pre data-lang='asa'>{content}</pre></div>\n"
            "</div>\n"
        )

    def _packet_check_asa(self, cfg_text: str, src: str, dst: str, proto: Optional[str], dports: Set[int]) -> dict:
        try:
            return asa_parser.path_check(cfg_text, src, dst, proto=proto, dports=dports)
        except Exception as exc:
            return {'error': str(exc), 'allowed': False}

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
        binding_str = format_binding(rule.get('binding'))
        bind_suffix = f" bind={binding_str}" if binding_str else ''
        return f"{rule['action']}{(' ' + rule['proto']) if rule.get('proto') else ''}{svc_str} src=[{src_str}] dst=[{dst_str}]{bind_suffix}"

    def _html(self, body: str, status: int = 200):
        content = body.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    # -------------------- API helpers --------------------
    def _json(self, payload: dict, status: int = 200):
        data = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
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
        app_state = getattr(self.server, 'app_state', None)
        if app_state is not None:
            status, payload = api_handlers.objects(
                app_state,
                vendor=vendor,
                os_tag=os_tag,
                version=version,
                filename=cfg_file,
                query=q,
                mode=mode,
                limit=limit,
            )
            return self._json(payload, status)
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
        app_state = getattr(self.server, 'app_state', None)
        if app_state is not None:
            status, payload = api_handlers.meta(app_state, vendor=vendor, filename=cfg_file)
            return self._json(payload, status)
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
        app_state = getattr(self.server, 'app_state', None)
        if app_state is not None:
            status, payload = api_handlers.aliases(
                app_state, vendor=vendor, filename=cfg_file, target=target
            )
            return self._json(payload, status)
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

    def _api_config(self, query: str):
        qs = parse_qs(query or '')
        vendor = (qs.get('vendor', ['asa'])[0] or 'asa').lower()
        cfg_file = qs.get('config', [''])[0]
        app_state = getattr(self.server, 'app_state', None)
        if app_state is not None:
            status, payload = api_handlers.config_text(
                app_state, vendor=vendor, filename=cfg_file
            )
            return self._json(payload, status)
        cfg_dir = self.server.config_dirs.get(vendor)
        path = os.path.join(cfg_dir, cfg_file) if cfg_dir and cfg_file else ''
        if not path or not os.path.isfile(path):
            return self._json({'error': 'invalid_config'}, 400)
        try:
            with open(path, 'r') as f:
                text = f.read()
        except Exception as e:
            return self._json({'error': f'read_failed: {e}'}, 500)
        return self._json({'vendor': vendor, 'config': cfg_file, 'text': text})

    def _api_index_status(self, query: str):
        # No query params required; returns summary of in-memory + disk cache state
        app_state = getattr(self.server, 'app_state', None)
        if app_state is not None:
            status, payload = api_handlers.index_status(app_state)
            return self._json(payload, status)
        payload = index_status_for_tests(getattr(self.server, 'cache_dir', None), getattr(self.server, 'index_cache', {}))
        return self._json(payload)

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
        app_state = getattr(self.server, 'app_state', None)
        if app_state is not None:
            entry = app_state.index_manager.get_index(vendor, os_tag, version, path)
            return entry.index
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
        app_state = getattr(self.server, 'app_state', None)
        if app_state is not None:
            return app_state.index_manager.suggest(index, q, 'prefix', limit)
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
        app_state = getattr(self.server, 'app_state', None)
        if app_state is not None:
            return app_state.index_manager.suggest(index, q, 'substring', limit)
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
        app_state = getattr(self.server, 'app_state', None)
        if app_state is not None:
            return app_state.index_manager.suggest(index, q, 'fuzzy', limit)
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
            ":root[data-theme='light']{--bg:#ffffff;--muted:#f6f8fa;--text:#24292f;--sub:#57606a;--accent:#0969da;--border:#d0d7de;}\n"
            "body{background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,'Helvetica Neue',sans-serif;margin:0;transition:background 0.2s ease,color 0.2s ease;}\n"
            ".app{max-width:1200px;margin:0 auto;padding:16px;}\n"
            ".toolbar{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;}\n"
            "h2{margin:0;}\n"
            ".tab-shell{margin-top:12px;max-width:960px;margin-left:auto;margin-right:auto;}\n"
            ".mode-tabs{display:flex;gap:4px;margin:0 0 -1px;padding:0 8px;}\n"
            ".mode-tabs .tab{background:var(--muted);color:var(--text);border:1px solid var(--border);border-bottom:none;border-radius:6px 6px 0 0;padding:6px 14px;cursor:pointer;font-size:0.95em;box-shadow:inset 1px 1px 0 rgba(255,255,255,0.15);}\n"
            ".mode-tabs .tab.active{background:var(--bg);color:var(--text);border-bottom:1px solid var(--bg);position:relative;top:1px;}\n"
            ".form{background:var(--muted);padding:12px;border:1px solid var(--border);border-radius:0 8px 8px 8px;margin-bottom:16px;position:sticky;top:48px;z-index:10;max-width:960px;margin-left:auto;margin-right:auto;}\n"
            ".section{margin-bottom:10px;} fieldset.section{border:1px solid var(--border);border-radius:8px;} legend{color:var(--sub);}\n"
            "label{margin-right:6px;} select,input[type=text]{margin-right:8px;margin-bottom:6px;padding:4px 6px;border:1px solid var(--border);border-radius:6px;background:transparent;color:var(--text);}\n"
            ".actions{margin-top:8px;} button{background:var(--accent);color:#fff;border:none;border-radius:6px;padding:6px 10px;cursor:pointer;} button:hover{opacity:0.9;}\n"
            ".results{max-width:960px;margin:12px auto;}\n"
            ".results .diff{background:var(--muted);border:1px solid var(--border);border-radius:8px;margin:10px 0;padding:8px;}\n"
            ".results a{color:var(--accent);} .results a:visited{color:var(--sub);}\n"
            "pre{white-space:pre-wrap;background:#00000022;padding:8px;border-radius:6px;overflow:auto;}\n"
            ".meta{margin-left:10px;color:var(--sub);} .theme-switch{font-size:0.9em;color:var(--sub);} .hl-switch{font-size:0.9em;color:var(--sub);} .rr{display:none;}\n"
            ".toolbar-controls{display:flex;gap:12px;align-items:center;}\n"
            ".kw{color:var(--hl-kw);} .proto{color:var(--hl-proto);} .act{color:var(--hl-act);} .addr{color:var(--hl-addr);} .num{color:var(--hl-num);}\n"
            ".tip{display:inline-block;width:16px;height:16px;line-height:16px;text-align:center;border-radius:50%;border:1px solid var(--sub);color:var(--sub);font-size:12px;cursor:help;}\n"
            ".history{position:fixed;right:8px;top:64px;width:260px;max-height:70vh;overflow:auto;background:var(--muted);border:1px solid var(--border);border-radius:8px;padding:8px;z-index:30;}\n"
            ".hist-entry{display:block;width:100%;text-align:left;background:transparent;color:var(--text);border:1px solid transparent;border-radius:6px;padding:6px;margin-bottom:4px;cursor:pointer;}\n"
            ".hist-entry:hover{border-color:var(--accent);background:rgba(122,162,247,0.12);}\n"
            ".hist-time{font-size:0.85em;color:var(--sub);}\n"
            ".hist-desc{font-size:0.95em;}\n"
            ".tab-panels{margin-top:12px;}\n"
            ".tab-panel{display:none;}\n"
            ".tab-panel.active{display:block;}\n"
            ".global-search{margin:6px 0 0;padding:0 8px;}\n"
            ".global-search label{display:inline-flex;align-items:center;gap:6px;}\n"
            "#include_any_label{display:inline-flex;align-items:center;gap:4px;}\n"
            ".radio-group{display:flex;gap:16px;align-items:center;} .radio-group label{margin-right:0;}\n"
            ".theme-control{display:flex;align-items:center;gap:12px;margin-bottom:8px;} .theme-control select{min-width:180px;}\n"
            ".theme-preview{width:80px;height:32px;border-radius:6px;border:1px solid var(--border);display:flex;align-items:center;justify-content:center;font-size:0.8em;}\n"
            ".pref-note{font-size:0.85em;color:var(--sub);margin-top:8px;}\n"
        )


def main(argv: Optional[Sequence[str]] = None) -> None:
    import argparse
    ap = argparse.ArgumentParser(description='Web UI for access-list inspection/comparison')
    ap.add_argument('--addr', default='127.0.0.1', help='Bind address (default 127.0.0.1)')
    ap.add_argument('--port', type=int, default=8083, help='TCP port (default 8083)')
    # Allow env overrides for config directories; falling back to defaults
    env_configs_cisco = os.environ.get('ACLINSPECTOR_CONFIGS_CISCO', 'configs/cisco')
    env_configs_fortigate = os.environ.get('ACLINSPECTOR_CONFIGS_FORTIGATE', 'configs/fortigate')
    ap.add_argument('--configs-cisco', default=env_configs_cisco, help='Directory with ASA configs (env ACLINSPECTOR_CONFIGS_CISCO)')
    ap.add_argument('--configs-fortigate', default=env_configs_fortigate, help='Directory with FortiGate configs (env ACLINSPECTOR_CONFIGS_FORTIGATE)')
    # Robust env parsing for optional overrides
    env_cache_dir = os.environ.get('ACLINSPECTOR_CACHE_DIR', '')
    env_theme_dir = os.environ.get('ACLINSPECTOR_THEME_DIR', 'themes')
    try:
        env_search_limit = int(os.environ.get('ACLINSPECTOR_SEARCH_LIMIT', '').strip() or '50')
    except Exception:
        env_search_limit = 50
    env_prewarm = os.environ.get('ACLINSPECTOR_PREWARM_ALL', '').strip().lower() in {'1', 'true', 'yes', 'on'}
    ap.add_argument('--cache-dir', default=env_cache_dir, help='Disk cache directory (optional; enable by setting a path)')
    ap.add_argument('--search-limit', type=int, default=env_search_limit, help='Default suggestion limit (can be overridden via query)')
    ap.add_argument('--theme-dir', default=env_theme_dir, help='Directory with iTerm2 theme files (env ACLINSPECTOR_THEME_DIR)')
    ap.add_argument('--prewarm-all-configs', action='store_true', default=env_prewarm, help='Pre-build index cache for all configs on startup (env ACLINSPECTOR_PREWARM_ALL)')
    args = ap.parse_args(argv)

    server = HTTPServer((args.addr, args.port), WebHandler)
    server.config_dirs = {
        'asa': args.configs_cisco,
        'fortigate': args.configs_fortigate,
    }
    server.index_cache: Dict[str, dict] = {}
    server.cache_dir = args.cache_dir or None
    server.search_limit = args.search_limit
    server.theme_dir = args.theme_dir
    server.themes = load_themes(args.theme_dir)
    if args.prewarm_all_configs:
        count = prewarm_all_configs(server)
        print(f"Prewarmed indices for {count} config(s).")
    print(f"Web UI running at http://{args.addr}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")


if __name__ == '__main__':
    main()
