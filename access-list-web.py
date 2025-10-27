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
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from parsers.cisco import asa as asa_parser
from webui.handlers import actions as actions_handlers
from webui.themes import DEFAULT_THEMES, load_themes
from webui.handlers import api as api_handlers
from webui.handlers import pages as pages_handlers
from webui import settings as webui_settings
from webui.state import AppState
from webui.testing import (
    extract_meta_for_tests,
    build_index_for_tests,
    match_candidates_for_tests,
    highlight_asa_for_tests,
    index_status_for_tests,
)

# Expose small module-level helpers for unit tests
def _vendor_os_tag(vendor: str) -> str:
    vendor = (vendor or '').lower()
    if vendor == 'asa':
        return 'ASA'
    if vendor == 'fortigate':
        return 'FortiOS'
    return vendor.upper() or 'UNKNOWN'



def prewarm_all_configs(server) -> int:
    """Eagerly build index cache entries for all known configs."""
    state = getattr(server, 'app_state', None)
    if state is None:
        overrides = {
            'paths': {
                'configs': getattr(server, 'config_dirs', {}),
                'themes_dir': getattr(server, 'theme_dir', 'themes') or 'themes',
                'cache_dir': getattr(server, 'cache_dir', None),
            },
            'features': {
                'predictive_search': {
                    'limit': getattr(server, 'search_limit', 50),
                }
            },
        }
        settings = webui_settings.load_settings(None, cli_overrides=overrides)
        state = AppState.create(settings)
    total = 0
    for vendor, dirpath in state.settings.paths.configs.items():
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
                entry = state.index_manager.get_index(vendor, _vendor_os_tag(vendor), 'auto', path)
                if hasattr(server, 'index_cache'):
                    server.index_cache[entry.key] = entry.to_payload()
                total += 1
            except Exception:
                continue
    server.app_state = state
    return total


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


class WebHandler(BaseHTTPRequestHandler):
    def _find_host(self, target: str) -> List[dict]:
        overrides = {
            'paths': {
                'configs': getattr(self.server, 'config_dirs', {}),
                'themes_dir': getattr(self.server, 'theme_dir', 'themes') or 'themes',
                'cache_dir': getattr(self.server, 'cache_dir', None),
            },
            'features': {
                'predictive_search': {
                    'limit': getattr(self.server, 'search_limit', 50),
                }
            },
        }
        try:
            settings = webui_settings.load_settings(None, cli_overrides=overrides)
            state = AppState.create(settings)
            themes = getattr(self.server, 'themes', None)
            if themes:
                state.themes = themes
            return actions_handlers._find_host(state, target)
        except Exception:
            return []

    def do_GET(self):
        app_state = getattr(self.server, 'app_state', None)
        if app_state is not None:
            body = pages_handlers._render_home(app_state)
            self._html(body)
            return
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
        fields = parse_qs(data, keep_blank_values=True)
        app_state = getattr(self.server, 'app_state', None)
        if app_state is not None:
            status, payload = actions_handlers.process_run(app_state, fields)
            if status == 200:
                body = payload.get('html', '')
                self._html(self._form() + body, 200)
            else:
                error_html = payload.get('error', 'Failed to run request.')
                self._html(self._form() + f"<p style='color:red'>{error_html}</p>", status)
            return

        # Legacy fallback (expected to be phased out)
        self._html("<p style='color:red'>Server state unavailable.</p>" + self._form(), 500)

    # ------------ render helpers ------------
    def _form(self):
        app_state = getattr(self.server, 'app_state', None)
        if app_state is not None:
            return pages_handlers._render_home(app_state)
        configs = getattr(self.server, 'config_dirs', {})
        overrides = {
            'paths': {
                'configs': configs,
                'themes_dir': getattr(self.server, 'theme_dir', 'themes') or 'themes',
                'cache_dir': getattr(self.server, 'cache_dir', None),
            },
            'features': {
                'predictive_search': {
                    'limit': getattr(self.server, 'search_limit', 50),
                }
            },
        }
        try:
            settings = webui_settings.load_settings(None, cli_overrides=overrides)
            state = AppState.create(settings)
            themes = getattr(self.server, 'themes', None)
            if themes:
                state.themes = themes
            self.server.app_state = state
            html = pages_handlers._render_home(state)
            if 'function storageGet' not in html:
                try:
                    app_js_path = Path(__file__).resolve().parent / 'webui' / 'static' / 'app.js'
                    app_js = app_js_path.read_text(encoding='utf-8')
                    close_idx = html.find('</script>')
                    if close_idx != -1:
                        html = html[:close_idx] + '\n' + app_js + '\n' + html[close_idx:]
                    else:
                        html = '<script>' + app_js + '</script>' + html

                except Exception:
                    pass
            return html
        except Exception:
            return '<p>Server state unavailable.</p>'

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

def main(argv: Optional[Sequence[str]] = None) -> None:
    from webui import run as webui_run

    webui_run(argv)


if __name__ == '__main__':
    main()
