# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Tests for action handlers."""

import tempfile
import unittest
from pathlib import Path

from parsers.cisco import asa as asa_parser
from parsers.cisco.asa import path as asa_path

from tests.fixtures.cisco_asa_example import ASA_EXAMPLE
from webui import settings as settings_mod
from webui.handlers import actions as action_handlers
from webui.state import AppState

FORTI_FIXTURE = Path(__file__).parent / "fixtures" / "configs" / "fortigate" / "advanced_policy_nat.conf"

ASA_SAMPLE = """!
object network OBJ_WEB
 host 192.0.2.10
object-group network OG_WEB
 network-object object OBJ_WEB
access-list OUTSIDE extended permit tcp object-group OG_WEB object OBJ_WEB eq 443
"""


class ActionHandlersTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        base = Path(self.tmpdir.name)
        self.config_dir = base / "configs" / "cisco"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        (self.config_dir / "sample.cfg").write_text(ASA_SAMPLE, encoding="utf-8")
        self.ftg_dir = base / "configs" / "fortigate"
        self.ftg_dir.mkdir(parents=True, exist_ok=True)
        (self.ftg_dir / "forti.conf").write_text(FORTI_FIXTURE.read_text(), encoding="utf-8")
        settings = settings_mod.load_settings(
            base / "settings.json",
            env={
                "ACLINSPECTOR_CONFIGS_CISCO": str(self.config_dir),
                "ACLINSPECTOR_CONFIGS_FORTIGATE": str(self.ftg_dir),
            },
        )
        self.state = AppState.create(settings)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_process_inspect(self):
        status, payload = action_handlers.process_run(
            self.state,
            {
                "vendor": ["asa"],
                "mode": ["inspect"],
                "config": ["sample.cfg"],
                "inspect": ["OBJ_WEB"],
            },
        )
        self.assertEqual(status, 200)
        self.assertIn("OBJ_WEB", payload["html"])
        self.assertIn(
            "object-groups",
            payload["html"],
            msg="Expected object-group guidance in inspect output",
        )
        self.assertIn("object-group OG_WEB", payload["html"])
        self.assertEqual(payload.get("meta", {}).get("mode"), "inspect")
        self.assertEqual(payload.get("meta", {}).get("query"), "OBJ_WEB")
        history = self.state.history.snapshot()["entries"]
        self.assertTrue(history)
        self.assertEqual(history[0]["query"], "OBJ_WEB")

    def test_missing_config(self):
        status, payload = action_handlers.process_run(
            self.state,
            {
                "vendor": ["asa"],
                "mode": ["inspect"],
                "config": ["missing.cfg"],
                "inspect": ["OBJ_WEB"],
            },
        )
        self.assertEqual(status, 400)
        self.assertIn("error", payload)

    def test_history_replay_suppresses_record(self):
        status, payload = action_handlers.process_run(
            self.state,
            {
                "vendor": ["asa"],
                "mode": ["inspect"],
                "config": ["sample.cfg"],
                "inspect": ["OBJ_WEB"],
                "history_replay": ["1"],
            },
        )
        self.assertEqual(status, 200)
        self.assertIn("OBJ_WEB", payload["html"])
        history = self.state.history.snapshot()["entries"]
        self.assertFalse(history)

    def test_process_inspect_fortigate(self):
        status, payload = action_handlers.process_run(
            self.state,
            {
                "vendor": ["fortigate"],
                "mode": ["inspect"],
                "config_ftg": ["forti.conf"],
                "inspect": ["INTERNAL_NET"],
                "vdom": ["root"],
            },
        )
        self.assertEqual(status, 200)
        self.assertIn("INTERNAL_NET", payload["html"])
        self.assertEqual(payload.get("meta", {}).get("vendor"), "fortigate")
        self.assertIn("Object context", payload["html"])
        self.assertIn("firewall address INTERNAL_NET", payload["html"])
        self.assertIn("Zone context", payload["html"])

    def test_process_compare_fortigate(self):
        status, payload = action_handlers.process_run(
            self.state,
            {
                "vendor": ["fortigate"],
                "mode": ["compare"],
                "config_ftg": ["forti.conf"],
                "old": ["INTERNAL_NET"],
                "new": ["DMZ_WEB"],
                "vdom": ["root"],
            },
        )
        self.assertEqual(status, 200)
        self.assertIn("New-only Policies", payload["html"])
        self.assertIn("Old object context", payload["html"])
        self.assertIn("New object context", payload["html"])
        self.assertIn("Old target zones", payload["html"])
        self.assertIn("New target zones", payload["html"])

    def test_process_find_fortigate(self):
        status, payload = action_handlers.process_run(
            self.state,
            {
                "vendor": ["fortigate"],
                "mode": ["find"],
                "config_ftg": ["forti.conf"],
                "findq": ["INTERNAL_NET"],
                "vdom": ["root"],
            },
        )
        self.assertEqual(status, 200)
        self.assertIn("Likely Owner", payload["html"])

    def test_packet_check_fortigate_render(self):
        status, payload = action_handlers.process_run(
            self.state,
            {
                "vendor": ["fortigate"],
                "mode": ["packet"],
                "config_ftg": ["forti.conf"],
                "pkt_src": ["1.1.1.1"],
                "pkt_dst": ["198.51.100.10"],
                "proto": ["tcp"],
                "dport": ["443"],
                "include_any": ["1"],
                "vdom": ["root"],
            },
        )
        self.assertEqual(status, 200)
        html = payload["html"]
        self.assertIn("NAT Steps", html)
        self.assertIn("VIP", html)

    def test_format_list_includes_more_suffix(self):
        text = action_handlers._format_list(["a", "b", "c", "d"], limit=2)
        self.assertEqual(text, "a, b (+2 more)")

    def test_fmt_preserves_brackets(self):
        rule = {
            "action": "permit",
            "src": ["192.0.2.0/24"],
            "dst": ["203.0.113.10"],
            "svc": {
                "proto": "tcp",
                "dst_ports": [("eq", (443, 443))],
                "dst_service_groups": [],
                "dst_service_objects": [],
            },
            "binding": {"interface": "outside", "direction": "in"},
            "proto": "tcp",
        }
        formatted = action_handlers._fmt(rule)
        self.assertIn("src=[192.0.2.0/24]", formatted)
        self.assertIn("dst=[203.0.113.10]", formatted)

    def test_parser_allows_hostname_objects(self):
        cfg = asa_parser.ASAConfig(
            """
object network OBJ_HOSTNAME
 host warsapd5.sapag.local
"""
        )
        values = cfg.network_objects.get("OBJ_HOSTNAME")
        self.assertIsNotNone(values)
        assert values is not None
        self.assertEqual(len(values), 0)
        literals = cfg.network_object_literals.get("OBJ_HOSTNAME")
        self.assertIn("host warsapd5.sapag.local", literals)

    def test_packet_check_matches_object_host(self):
        result = asa_path.path_check(
            ASA_EXAMPLE,
            src="10.0.0.10",
            dst="192.0.2.10",
            proto="tcp",
            dports={443},
        )
        self.assertTrue(result["allowed"])
        matches = result["acl"].get("matches", [])
        self.assertTrue(matches)
        self.assertTrue(any("SRC_GROUP" in entry.get("raw", "") for entry in matches))

    def test_packet_check_collects_multiple_acl_matches(self):
        result = asa_path.path_check(
            ASA_EXAMPLE,
            src="10.0.0.10",
            dst="192.0.2.10",
            proto="tcp",
            dports={443},
        )
        matches = [entry.get("raw") for entry in result["acl"].get("matches", [])]
        self.assertIn(
            "access-list outside_in extended permit tcp object-group SRC_GROUP object DST_HOST eq 443",
            matches,
        )
        self.assertIn(
            "access-list outside_out extended permit tcp object-group SRC_GROUP object DST_HOST eq 443",
            matches,
        )
        warnings = result["acl"].get("warnings", [])
        self.assertFalse(warnings)

    def test_packet_check_warns_when_pair_missing(self):
        cfg_text = ASA_EXAMPLE.replace(
            "access-list outside_in extended permit tcp object-group SRC_GROUP object DST_HOST eq 443\naccess-group outside_in in interface outside\n\n",
            "",
        )
        result = asa_path.path_check(
            cfg_text,
            src="10.0.0.10",
            dst="192.0.2.10",
            proto="tcp",
            dports={443},
        )
        matches = [entry.get("raw") for entry in result["acl"].get("matches", [])]
        self.assertIn(
            "access-list outside_out extended permit tcp object-group SRC_GROUP object DST_HOST eq 443",
            matches,
        )
        warnings = result["acl"].get("warnings", [])
        self.assertTrue(any("outbound" in msg for msg in warnings))

        result_no_guess = asa_path.path_check(
            cfg_text,
            src="10.0.0.10",
            dst="192.0.2.10",
            proto="tcp",
            dports={443},
            guess_interface_pairs=False,
        )
        matches_no_guess = [entry.get("raw") for entry in result_no_guess["acl"].get("matches", [])]
        self.assertEqual(matches_no_guess.count("access-list outside_out extended permit tcp object-group SRC_GROUP object DST_HOST eq 443"), 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
