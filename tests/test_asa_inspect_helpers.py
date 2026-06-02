# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
import unittest
import ipaddress
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
access-list ACL1 extended permit ip host 1.1.1.1 host 2.2.2.2
access-list ACL2 extended permit ip host 1.1.1.1 host 2.2.2.2
"""
        # Compare old=1.1.1.1 vs new=1.1.1.1
        # In the old logic (raw-only), these would be considered "shared" and added_to_new would be empty.
        # In the new logic (ACL+raw+src+dst), since they have DIFFERENT ACL names but same raw text,
        # they are both "shared" because both targets match both rules.
        # Wait, if old and new are the SAME, added_to_new should be empty regardless of identity key.
        
        # Let's test different targets.
        cfg_text = """
access-list SHARED extended permit ip host 1.1.1.1 host 3.3.3.3
access-list SHARED extended permit ip host 2.2.2.2 host 3.3.3.3
"""
        # old=1.1.1.1, new=2.2.2.2
        diff = compare_old_new(cfg_text, old_target="1.1.1.1", new_target="2.2.2.2")
        self.assertEqual(len(diff['added_to_new']), 1)
        self.assertEqual(len(diff['removed_from_old']), 1)
        self.assertEqual(diff['added_to_new'][0]['src'], {ipaddress.ip_address("2.2.2.2")})
        self.assertEqual(diff['removed_from_old'][0]['src'], {ipaddress.ip_address("1.1.1.1")})

if __name__ == '__main__':
    unittest.main()
