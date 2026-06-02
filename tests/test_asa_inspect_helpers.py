# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
import unittest
import ipaddress
import io
from parsers.cisco.asa.parser import ASAConfig
from parsers.cisco.asa.inspect import evaluate_acl

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
    def test_translate_uses_preloaded_text_not_args_config(self):
        """translate mode must pass cfg_text to get_engine, not re-read args.config.

        load_config("-") re-reads stdin; if stdin was already consumed by the
        initial config read, it returns empty and produces an empty config.
        get_engine('asa', cfg_text) uses the already-loaded string instead.
        """
        from unittest.mock import patch
        from parsers.loader import get_engine, load_config

        cfg_text = "access-list TEST extended permit tcp any host 1.1.1.1 eq 443"

        # Demonstrate the bug scenario: load_config("-") with consumed stdin gives empty config
        with patch('sys.stdin', new=io.StringIO("")):
            cfg_empty, _, _ = load_config("-", vendor='asa')
            self.assertNotIn('TEST', cfg_empty.acls)

        # The fix: get_engine with pre-loaded text ignores stdin entirely
        with patch('sys.stdin', new=io.StringIO("")):
            cfg = get_engine('asa', cfg_text)
            self.assertIsInstance(cfg, ASAConfig)
            self.assertIn('TEST', cfg.acls)


class TestFortiGateRuleIdKey(unittest.TestCase):
    def test_rule_id_uses_policy_id_not_policyid(self):
        """compare_old_new rule_id must use 'policy_id' (with underscore) to match
        the key that flatten_policies emits. Wrong key causes all IDs to be None,
        making rules from different policies appear identical when raw text matches.
        """
        from parsers.fortigate.inspect import compare_old_new
        import pathlib
        cfg_text = pathlib.Path('tests/fixtures/configs/fortigate/sample.conf').read_text()

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
        all_new_only_ids = {e.get("policy_id") for e in diff["added_to_new"]}
        all_old_only_ids = {e.get("policy_id") for e in diff["removed_from_old"]}
        # None must not appear: that would mean policy_id lookup failed
        self.assertNotIn(None, all_new_only_ids | all_old_only_ids)


if __name__ == '__main__':
    unittest.main()
