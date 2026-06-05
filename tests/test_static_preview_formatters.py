# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Unit tests for scripts/generate_static_preview.py formatter functions."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# scripts/ is not a package; add it to the path so we can import directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from generate_static_preview import fmt_compare, fmt_config_snippet, fmt_findhost, fmt_inspect, highlight_rule


class TestHighlightRule(unittest.TestCase):
    def _span(self, cls, text):
        return f'<span class="{cls}">{text}</span>'

    def test_permit_action(self):
        result = highlight_rule("permit")
        self.assertIn(self._span("act", "permit"), result)

    def test_deny_action(self):
        result = highlight_rule("deny")
        self.assertIn(self._span("act", "deny"), result)

    def test_ip_address(self):
        result = highlight_rule("10.1.1.1")
        self.assertIn(self._span("addr", "10.1.1.1"), result)

    def test_cidr_prefix(self):
        result = highlight_rule("10.1.1.0/24")
        self.assertIn(self._span("addr", "10.1.1.0/24"), result)

    def test_protocol_token(self):
        result = highlight_rule("tcp")
        self.assertIn(self._span("proto", "tcp"), result)

    def test_any_token(self):
        result = highlight_rule("any")
        self.assertIn(self._span("addr", "any"), result)

    def test_port_keyword(self):
        result = highlight_rule("eq")
        self.assertIn(self._span("kw", "eq"), result)

    def test_port_number(self):
        result = highlight_rule("443")
        self.assertIn(self._span("num", "443"), result)

    def test_keyword_token(self):
        result = highlight_rule("host")
        self.assertIn(self._span("kw", "host"), result)

    def test_full_rule(self):
        rule = "permit tcp 10.1.1.1 255.255.255.255 any eq 443"
        result = highlight_rule(rule)
        self.assertIn(self._span("act", "permit"), result)
        self.assertIn(self._span("proto", "tcp"), result)
        self.assertIn(self._span("addr", "10.1.1.1"), result)
        self.assertIn(self._span("addr", "any"), result)
        self.assertIn(self._span("kw", "eq"), result)
        self.assertIn(self._span("num", "443"), result)

    def test_html_escaping(self):
        result = highlight_rule('<script>alert("xss")</script>')
        self.assertNotIn("<script>", result)
        self.assertIn("&lt;script&gt;", result)


class TestFmtInspect(unittest.TestCase):
    def _make_json(self, **kwargs):
        base = {
            "target_nets": ["10.1.1.1"],
            "hits": [{"raw": "permit tcp any host 10.1.1.1 eq 443", "action": "permit", "binding": {}}],
            "aliases": {},
        }
        base.update(kwargs)
        return json.dumps(base)

    def test_happy_path_contains_target_net(self):
        result = fmt_inspect(self._make_json(), "10.1.1.1")
        self.assertIn("10.1.1.1", result)
        self.assertIn("1 matching rule", result)

    def test_hit_rule_is_rendered(self):
        result = fmt_inspect(self._make_json(), "10.1.1.1")
        # Rules are passed through highlight_rule, so check for highlighted tokens.
        self.assertIn('class="act">permit', result)
        self.assertIn('class="proto">tcp', result)
        self.assertIn('class="num">443', result)

    def test_empty_hits_shows_no_results(self):
        result = fmt_inspect(self._make_json(hits=[]), "10.1.1.1")
        self.assertIn("No matching ACL entries", result)

    def test_invalid_json_returns_error_block(self):
        result = fmt_inspect("not json", "target")
        self.assertIn("Error parsing output", result)
        self.assertIn("result-pre", result)

    def test_non_object_json_returns_error_block(self):
        result = fmt_inspect(json.dumps([1, 2, 3]), "target")
        self.assertIn("Error parsing output", result)

    def test_interface_binding_shows_bind_tag(self):
        payload = {
            "target_nets": ["10.1.1.1"],
            "hits": [{"raw": "permit ip any any", "action": "permit",
                      "binding": {"scope": "interface", "interface": "inside", "direction": "in"}}],
            "aliases": {},
        }
        result = fmt_inspect(json.dumps(payload), "10.1.1.1")
        self.assertIn("bind-tag", result)
        self.assertIn("inside", result)

    def test_global_binding_shows_global_tag(self):
        payload = {
            "target_nets": ["10.1.1.1"],
            "hits": [{"raw": "permit ip any any", "action": "permit",
                      "binding": {"scope": "global"}}],
            "aliases": {},
        }
        result = fmt_inspect(json.dumps(payload), "10.1.1.1")
        self.assertIn("global", result)

    def test_aliases_shown(self):
        payload = {
            "target_nets": ["10.1.1.1"],
            "hits": [],
            "aliases": {"10.1.1.1": ["HOST_A", "HOST_B", "target"]},
        }
        result = fmt_inspect(json.dumps(payload), "target")
        self.assertIn("HOST_A", result)
        self.assertIn("HOST_B", result)
        # The target itself should not appear in the "also known as" list
        self.assertNotIn(">target<", result)

    def test_missing_keys_handled_gracefully(self):
        result = fmt_inspect(json.dumps({}), "x")
        self.assertIn("No matching ACL entries", result)


class TestFmtCompare(unittest.TestCase):
    def _make_json(self, added=None, removed=None):
        return json.dumps({
            "added_to_new": added if added is not None else [{"raw": "permit ip any host 1.1.1.1"}],
            "removed_from_old": removed if removed is not None else [{"raw": "permit ip any host 2.2.2.2"}],
        })

    def test_happy_path_counts(self):
        result = fmt_compare(self._make_json())
        self.assertIn("+1 added", result)
        self.assertIn("-1 removed", result)

    def test_added_rule_rendered(self):
        result = fmt_compare(self._make_json())
        # Rules are highlighted; check for the IP address token in an addr span.
        self.assertIn('class="addr">1.1.1.1', result)

    def test_removed_rule_rendered(self):
        result = fmt_compare(self._make_json())
        self.assertIn('class="addr">2.2.2.2', result)

    def test_empty_added_shows_none(self):
        result = fmt_compare(self._make_json(added=[]))
        self.assertIn("+0 added", result)
        self.assertIn("none", result)

    def test_empty_removed_shows_none(self):
        result = fmt_compare(self._make_json(removed=[]))
        self.assertIn("-0 removed", result)
        self.assertIn("none", result)

    def test_missing_added_key_returns_error(self):
        result = fmt_compare(json.dumps({"removed_from_old": []}))
        self.assertIn("Unexpected compare output format", result)

    def test_missing_removed_key_returns_error(self):
        result = fmt_compare(json.dumps({"added_to_new": []}))
        self.assertIn("Unexpected compare output format", result)

    def test_invalid_json_returns_error_block(self):
        result = fmt_compare("not json")
        self.assertIn("Error parsing output", result)


class TestFmtFindhost(unittest.TestCase):
    def _make_json(self, results=None):
        return json.dumps({"results": results if results is not None else [
            {"file": "fw1.conf", "objects": ["HOST_A"], "literals": ["10.1.1.1"]},
        ]})

    def test_happy_path_shows_filename(self):
        result = fmt_findhost(self._make_json(), "10.1.1.1")
        self.assertIn("fw1.conf", result)

    def test_happy_path_shows_object(self):
        result = fmt_findhost(self._make_json(), "10.1.1.1")
        self.assertIn("HOST_A", result)

    def test_happy_path_shows_literal(self):
        result = fmt_findhost(self._make_json(), "10.1.1.1")
        self.assertIn("10.1.1.1", result)

    def test_empty_results_shows_not_found(self):
        result = fmt_findhost(self._make_json(results=[]), "10.1.1.1")
        self.assertIn("not found", result)

    def test_invalid_json_returns_error_block(self):
        result = fmt_findhost("bad json", "10.1.1.1")
        self.assertIn("Error", result)

    def test_missing_results_key_shows_not_found(self):
        result = fmt_findhost(json.dumps({}), "10.1.1.1")
        self.assertIn("not found", result)

    def test_multiple_files(self):
        payload = json.dumps({"results": [
            {"file": "fw1.conf", "objects": ["OBJ_A"], "literals": []},
            {"file": "fw2.conf", "objects": [], "literals": ["10.1.1.1"]},
        ]})
        result = fmt_findhost(payload, "10.1.1.1")
        self.assertIn("fw1.conf", result)
        self.assertIn("fw2.conf", result)


class TestFmtConfigSnippet(unittest.TestCase):
    def _make_file(self, lines):
        fd, path = tempfile.mkstemp(suffix=".conf", text=True)
        with os.fdopen(fd, "w") as f:
            f.write("\n".join(lines))
        self.addCleanup(os.unlink, path)
        return path

    def test_missing_file_returns_no_results_div(self):
        result = fmt_config_snippet("/nonexistent/path/fw.conf")
        self.assertIn("no-results", result)
        self.assertIn("not found", result)

    def test_output_wrapped_in_pre(self):
        path = self._make_file(["permit ip any any"])
        result = fmt_config_snippet(path)
        self.assertIn("result-pre", result)
        self.assertTrue(result.startswith("<pre"))

    def test_normal_line_is_highlighted(self):
        path = self._make_file(["permit tcp 10.1.1.1 any eq 443"])
        result = fmt_config_snippet(path)
        self.assertIn('class="act">permit', result)
        self.assertIn('class="proto">tcp', result)

    def test_bang_comment_gets_comment_span(self):
        path = self._make_file(["! this is a comment"])
        result = fmt_config_snippet(path)
        self.assertIn('class="comment">', result)
        self.assertIn("this is a comment", result)

    def test_hash_comment_gets_comment_span(self):
        path = self._make_file(["# hash comment"])
        result = fmt_config_snippet(path)
        self.assertIn('class="comment">', result)
        self.assertIn("hash comment", result)

    def test_empty_line_gets_comment_span(self):
        path = self._make_file(["permit ip any any", "", "deny ip any any"])
        result = fmt_config_snippet(path)
        self.assertIn('class="comment"></span>', result)

    def test_truncation_shows_footer(self):
        path = self._make_file(["permit ip any any"] * 5)
        result = fmt_config_snippet(path, max_lines=3)
        self.assertIn("2 more lines", result)
        self.assertIn('class="comment">', result)

    def test_no_footer_when_within_max(self):
        path = self._make_file(["permit ip any any"] * 3)
        result = fmt_config_snippet(path, max_lines=3)
        self.assertNotIn("more lines", result)

    def test_html_escaping_in_comment(self):
        path = self._make_file(["! <script>alert('xss')</script>"])
        result = fmt_config_snippet(path)
        self.assertNotIn("<script>", result)
        self.assertIn("&lt;script&gt;", result)


if __name__ == "__main__":
    unittest.main()
