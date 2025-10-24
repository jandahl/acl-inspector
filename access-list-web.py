#!/usr/bin/env python3
"""Minimal web UI for access-list inspection and comparison.

This server is intentionally separate from the core CLI to keep concerns
isolated. It lists available config files for supported vendors and allows
running inspect/compare operations via a browser form.
"""

import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

from parsers import asa as asa_parser


def list_files(dirpath: str):
    try:
        return sorted([f for f in os.listdir(dirpath) if os.path.isfile(os.path.join(dirpath, f))])
    except FileNotFoundError:
        return []


class WebHandler(BaseHTTPRequestHandler):
    def do_GET(self):
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
                    body = self._render_diff(old, new, diff)
                self._html(body + self._form())
            except Exception as e:
                self._html(f"<p style='color:red'>Error: {e}</p>" + self._form())
        else:
            self._html("<p>Vendor not implemented.</p>" + self._form())

    # ------------ render helpers ------------
    def _form(self):
        asa_opts = "\n".join(["<option value='{}'>{}</option>".format(x, x) for x in list_files(self.server.config_dirs.get('asa', 'configs/cisco'))])
        ftg_opts = "\n".join(["<option value='{}'>{}</option>".format(x, x) for x in list_files(self.server.config_dirs.get('fortigate', 'configs/fortigate'))])
        return (
            "<!doctype html>\n"
            "<html><head><meta charset='utf-8'><title>ACL Inspector</title></head>\n"
            "<body>\n"
            "  <h2>ACL Inspector</h2>\n"
            "  <form method='POST' action='/run'>\n"
            "    <label>Vendor:</label>\n"
            "    <select name='vendor' id='vendor' onchange='toggleVendor()'>\n"
            "      <option value='asa' selected>ASA</option>\n"
            "      <option value='fortigate'>FortiGate</option>\n"
            "    </select>\n"
            "    <br/>\n"
            "    <div id='asa_cfg'>\n"
            "      <label>ASA Config:</label>\n"
            "      <select name='config'>\n"
            + asa_opts +
            "      </select>\n"
            "    </div>\n"
            "    <div id='ftg_cfg' style='display:none'>\n"
            "      <label>FortiGate Config:</label>\n"
            "      <select name='config'>\n"
            + ftg_opts +
            "      </select>\n"
            "    </div>\n"
            "    <br/>\n"
            "    <label>Mode:</label>\n"
            "    <select name='mode' id='mode' onchange='toggleMode()'>\n"
            "      <option value='inspect' selected>Inspect</option>\n"
            "      <option value='compare'>Compare</option>\n"
            "    </select>\n"
            "    <div id='inspect_fields'>\n"
            "      <label>Inspect target:</label>\n"
            "      <input type='text' name='inspect' placeholder='ip|cidr|object'/>\n"
            "    </div>\n"
            "    <div id='compare_fields' style='display:none'>\n"
            "      <label>Old target:</label>\n"
            "      <input type='text' name='old' placeholder='ip|cidr|object'/>\n"
            "      <label>New target:</label>\n"
            "      <input type='text' name='new' placeholder='ip|cidr|object'/>\n"
            "    </div>\n"
            "    <br/>\n"
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
            "    <br/>\n"
            "    <button type='submit'>Run</button>\n"
            "  </form>\n"
            "  <script>\n"
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
            "  </script>\n"
            "</body></html>\n"
        )

    def _render_report(self, target, report):
        lines_raw = "\n".join(f"  {e['raw']}" for e in report['hits'])
        lines_flat = "\n".join(f"  {self._fmt(e)}" for e in report['hits'])
        alias_section = ""
        if report.get('aliases'):
            alias_lines = []
            for addr, names in sorted(report['aliases'].items(), key=lambda x: str(x[0])):
                alias_lines.append(f"  {addr}: {', '.join(sorted(names))}")
            alias_section = "<h3>Aliases</h3><pre>" + "\n".join(alias_lines) + "</pre>"
        return f"""
<h3>Inspection Report for {target}</h3>
<p>Resolved to: {', '.join(str(n) for n in report['target_nets'])}</p>
<p>Found {len(report['hits'])} matching ACL entries.</p>
<h3>Matched Rules (Raw)</h3>
<pre>{lines_raw}</pre>
<h3>Matched Rules (Flattened)</h3>
<pre>{lines_flat}</pre>
{alias_section}
"""

    def _render_diff(self, old, new, diff):
        added = "\n".join(f" + {e['raw']}\n   -> {self._fmt(e)}" for e in diff['added_to_new'][:200])
        removed = "\n".join(f" - {e['raw']}\n   -> {self._fmt(e)}" for e in diff['removed_from_old'][:200])
        return f"""
<h3>Comparison</h3>
<p>Old target: {old}</p>
<p>New target: {new}</p>
<p>Old hits: {len(diff['old_hits'])} &nbsp; New hits: {len(diff['new_hits'])}</p>
<p>Added to new: {len(diff['added_to_new'])} &nbsp; Removed from old: {len(diff['removed_from_old'])}</p>
<h3>Rules Added to New</h3>
<pre>{added}</pre>
<h3>Rules Removed from Old</h3>
<pre>{removed}</pre>
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


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description='Web UI for access-list inspection/comparison')
    ap.add_argument('--addr', default='127.0.0.1', help='Bind address (default 127.0.0.1)')
    ap.add_argument('--port', type=int, default=8080, help='TCP port (default 8080)')
    ap.add_argument('--configs-cisco', default='configs/cisco', help='Directory with ASA configs')
    ap.add_argument('--configs-fortigate', default='configs/fortigate', help='Directory with FortiGate configs')
    args = ap.parse_args()

    server = HTTPServer((args.addr, args.port), WebHandler)
    server.config_dirs = {
        'asa': args.configs_cisco,
        'fortigate': args.configs_fortigate,
    }
    print(f"Web UI running at http://{args.addr}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")


if __name__ == '__main__':
    main()
