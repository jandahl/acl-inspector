# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
import subprocess
import sys
import unittest
import ipaddress
from parsers.cisco.asa.parser import ASAConfig
from parsers.cisco.asa.inspect import evaluate_acl
from common.project_paths import ensure_pythonpath_env, project_root

class TestASAInspectHelpers(unittest.TestCase):
    def test_evaluate_acl_no_filter(self):
        """Verify that evaluate_acl returns all matching entries when service_filter is None."""
        cfg_text = "access-list TEST extended permit tcp any host 1.1.1.1 eq 443"
        cfg = ASAConfig(cfg_text)
        entries = cfg.flatten_acl()
        target_nets = {ipaddress.ip_address("1.1.1.1")}

        # Test with service_filter=None (default)
        hits = evaluate_acl(entries, target_nets, cfg, service_filter=None, ignore_any=False)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]['raw'], "access-list TEST extended permit tcp any host 1.1.1.1 eq 443")

    def test_evaluate_acl_with_filter_match(self):
        """Verify that evaluate_acl filters correctly when service_filter is provided."""
        cfg_text = "access-list TEST extended permit tcp any host 1.1.1.1 eq 443"
        cfg = ASAConfig(cfg_text)
        entries = cfg.flatten_acl()
        target_nets = {ipaddress.ip_address("1.1.1.1")}

        svc_filter = {'proto': 'tcp', 'dports': {443}}
        hits = evaluate_acl(entries, target_nets, cfg, service_filter=svc_filter, ignore_any=False)
        self.assertEqual(len(hits), 1)

    def test_evaluate_acl_with_filter_mismatch(self):
        """Verify that evaluate_acl filters out mismatches when service_filter is provided."""
        cfg_text = "access-list TEST extended permit tcp any host 1.1.1.1 eq 443"
        cfg = ASAConfig(cfg_text)
        entries = cfg.flatten_acl()
        target_nets = {ipaddress.ip_address("1.1.1.1")}

        svc_filter = {'proto': 'tcp', 'dports': {80}}
        hits = evaluate_acl(entries, target_nets, cfg, service_filter=svc_filter, ignore_any=False)
        self.assertEqual(len(hits), 0)

    def test_compare_old_new_rule_identity(self):
        """Verify that compare_old_new uses a precise rule identity (ACL, raw, src, dst)."""
        from parsers.cisco.asa.inspect import compare_old_new
        cfg_text = """
access-list SHARED extended permit ip host 1.1.1.1 host 3.3.3.3
access-list SHARED extended permit ip host 2.2.2.2 host 3.3.3.3
"""
        # old=1.1.1.1, new=2.2.2.2: the two rules have same ACL/raw text but different src,
        # so they have different rule_ids and show up as added/removed correctly.
        diff = compare_old_new(cfg_text, old_target="1.1.1.1", new_target="2.2.2.2")
        self.assertEqual(len(diff['added_to_new']), 1)
        self.assertEqual(len(diff['removed_from_old']), 1)
        self.assertEqual(diff['added_to_new'][0]['src'], {ipaddress.ip_address("2.2.2.2")})
        self.assertEqual(diff['removed_from_old'][0]['src'], {ipaddress.ip_address("1.1.1.1")})

class TestTranslateStdinFix(unittest.TestCase):
    def test_translate_stdin_produces_output_from_piped_config(self):
        """CLI translate mode uses the config piped via stdin, not a second stdin read.

        The fix changed the translate block to call get_engine(vendor, cfg_text)
        instead of load_config(args.config). If the old bug were reintroduced,
        load_config('-') would re-read the already-consumed stdin and return an
        empty config, producing empty or minimal output. This test pipes a real
        config and verifies the output reflects the piped content.
        """
        cli = project_root() / "aclinspector.py"
        cfg_text = "object network WEBSERVER\n host 10.0.0.1\n"
        result = subprocess.run(
            [sys.executable, str(cli),
             "inspect", "--vendor", "asa", "--config", "-",
             "--translate", "--target-vendor", "fortigate"],
            input=cfg_text,
            capture_output=True,
            text=True,
            cwd=project_root(),
            env=ensure_pythonpath_env(),
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        # Output must contain the translated object — only possible if the
        # config was parsed from the piped text, not from an empty second read.
        self.assertIn("WEBSERVER", result.stdout)


class TestFortiGateRuleIdKey(unittest.TestCase):
    def test_rule_id_uses_policy_id_not_policyid(self):
        """compare_old_new rule_id must use 'policy_id' (with underscore) to match
        the key that flatten_policies emits. Wrong key causes all IDs to be None,
        making rules from different policies appear identical when raw text matches.
        """
        from parsers.fortigate.inspect import compare_old_new
        cfg_text = (project_root() / 'tests/fixtures/configs/fortigate/sample.conf').read_text()

        # Policies 1 and 2 both permit traffic but from different source addresses.
        # With the correct policy_id key, they produce distinct rule_ids.
        diff = compare_old_new(cfg_text, old_target='APP_NET', new_target='WEB_SERVER', vdom='root')
        # Sanity: each target matches exactly one policy
        self.assertTrue(len(diff['old_hits']) > 0)
        self.assertTrue(len(diff['new_hits']) > 0)
        # If policy_id were always None, rules from different policies with matching
        # raw text would collapse to the same rule_id. Verify policy_id is populated.
        for entry in diff['old_hits'] + diff['new_hits']:
            self.assertIn('policy_id', entry)
            self.assertIsNotNone(entry['policy_id'])
        # Verify the diff correctly identifies rules unique to each target.
        # WEB_SERVER-only rules appear in added_to_new; APP_NET-only in removed_from_old.
        # Guard against vacuous pass: assertNotIn(None, empty_set) always passes.
        # The fixture has policy 2 (WEB_SERVER-only), so added_to_new is non-empty.
        self.assertTrue(len(diff['added_to_new']) + len(diff['removed_from_old']) > 0,
            "fixture must produce at least one rule unique to one of the two targets")
        all_new_only_ids = {e.get("policy_id") for e in diff["added_to_new"]}
        all_old_only_ids = {e.get("policy_id") for e in diff["removed_from_old"]}
        # None must not appear: that would mean policy_id lookup failed
        self.assertNotIn(None, all_new_only_ids | all_old_only_ids)


if __name__ == '__main__':
    unittest.main()
