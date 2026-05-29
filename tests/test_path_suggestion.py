# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
import unittest

from parsers.cisco.asa import path_check as asa_path_check
from parsers.fortigate import path_check as ftg_path_check
from parsers.suggest import suggest_corrections, SCHEMA_VERSION


ASA_SAMPLE = """
interface GigabitEthernet0/0
 nameif outside
 security-level 0
 ip address 203.0.113.2 255.255.255.0
!
interface GigabitEthernet0/1
 nameif inside
 security-level 100
 ip address 10.0.0.1 255.255.255.0
!
object network WEB
 host 10.0.0.10
!
access-list outside_access_in extended permit tcp any host 10.0.0.99 eq 443
access-group outside_access_in in interface outside
"""


FTG_SAMPLE = """
config firewall address
    edit "SRC"
        set subnet 10.10.10.10 255.255.255.255
    next
    edit "WEB"
        set subnet 192.168.1.10 255.255.255.255
    next
end
config firewall policy
    edit 1
        set srcintf "port1"
        set dstintf "port2"
        set srcaddr "SRC"
        set dstaddr "WEB"
        set service "HTTPS"
        set action accept
        set schedule "always"
    next
end
"""


FTG_VDOM_SAMPLE = """
config vdom
edit CUSTOMER_A
config firewall address
    edit "SRC"
        set subnet 10.10.10.10 255.255.255.255
    next
    edit "WEB"
        set subnet 192.168.1.10 255.255.255.255
    next
end
config firewall policy
    edit 1
        set srcintf "port1"
        set dstintf "port2"
        set srcaddr "SRC"
        set dstaddr "WEB"
        set service "HTTPS"
        set action accept
        set schedule "always"
    next
end
end
"""


class TestASASuggestion(unittest.TestCase):
    def test_blocked_flow_gets_suggestion(self):
        # No ACL permits this -> implicit deny.
        result = asa_path_check(ASA_SAMPLE, '203.0.113.5', 'WEB',
                                proto='tcp', dports={443})
        self.assertFalse(result['allowed'])
        sug = result['suggestion']
        self.assertEqual(sug['schema_version'], SCHEMA_VERSION)
        self.assertTrue(sug['needed'])
        self.assertEqual(sug['reason'], 'implicit-deny')
        cmds = [c for s in sug['suggestions'] for c in s['commands']]
        self.assertTrue(any('access-list outside_access_in extended permit tcp' in c
                            for c in cmds))
        self.assertTrue(any('host 10.0.0.10 eq 443' in c for c in cmds))

    def test_allowed_flow_needs_no_suggestion(self):
        result = asa_path_check(ASA_SAMPLE, '203.0.113.5', '10.0.0.99',
                                proto='tcp', dports={443})
        self.assertTrue(result['allowed'])
        self.assertFalse(result['suggestion']['needed'])
        self.assertEqual(result['suggestion']['reason'], 'allowed')
        self.assertEqual(result['suggestion']['suggestions'], [])
        self.assertEqual(result['suggestion']['verification'], [])

    def test_explicit_deny_detected(self):
        cfg = ASA_SAMPLE + (
            "access-list outside_access_in extended deny ip any host 10.0.0.10\n"
        )
        result = asa_path_check(cfg, '203.0.113.5', 'WEB',
                                proto='tcp', dports={443})
        self.assertFalse(result['allowed'])
        sug = result['suggestion']
        self.assertEqual(sug['reason'], 'explicit-deny')
        self.assertIsNotNone(sug['blocking_rule'])

    def test_verification_has_packet_tracer(self):
        result = asa_path_check(ASA_SAMPLE, '203.0.113.5', 'WEB',
                                proto='tcp', dports={443})
        verifs = result['suggestion']['verification']
        self.assertTrue(verifs)
        self.assertTrue(any('packet-tracer input' in v['command'] for v in verifs))


class TestFortiGateSuggestion(unittest.TestCase):
    def test_blocked_flow_emits_policy_block(self):
        # Mismatched dst -> no matching policy -> implicit deny.
        result = ftg_path_check(FTG_SAMPLE, 'SRC', '203.0.113.50',
                                proto='tcp', dports={443})
        self.assertFalse(result['allowed'])
        sug = result['suggestion']
        self.assertTrue(sug['needed'])
        cmds = sug['suggestions'][0]['commands']
        self.assertIn('config firewall policy', cmds)
        self.assertTrue(any('set action accept' in c for c in cmds))
        self.assertTrue(any('set service "TCP_443"' in c for c in cmds))

    def test_allowed_flow_no_suggestion(self):
        result = ftg_path_check(FTG_SAMPLE, 'SRC', 'WEB',
                                proto='tcp', dports={443})
        self.assertTrue(result['allowed'])
        self.assertFalse(result['suggestion']['needed'])

    def test_verification_has_iprope_lookup(self):
        result = ftg_path_check(FTG_SAMPLE, 'SRC', '203.0.113.50',
                                proto='tcp', dports={443})
        verifs = result['suggestion']['verification']
        self.assertTrue(verifs)
        self.assertTrue(any('diagnose firewall iprope lookup' in v['command']
                            for v in verifs))

    def test_vdom_is_threaded_into_commands(self):
        result = ftg_path_check(FTG_VDOM_SAMPLE, 'SRC', '203.0.113.50',
                                proto='tcp', dports={443}, vdom='CUSTOMER_A')
        self.assertEqual(result['context'].get('vdom'), 'CUSTOMER_A')
        sug = result['suggestion']
        cmds = sug['suggestions'][0]['commands']
        self.assertIn('config vdom', cmds)
        self.assertIn('edit CUSTOMER_A', cmds)
        verif_cmd = sug['verification'][0]['command']
        self.assertIn('edit CUSTOMER_A', verif_cmd)


class TestSuggestHelper(unittest.TestCase):
    def test_interface_overrides(self):
        result = asa_path_check(ASA_SAMPLE, '203.0.113.5', 'WEB',
                                proto='tcp', dports={443})
        sug = suggest_corrections(result, 'asa',
                                  ingress_interface='dmz',
                                  egress_interface='inside')
        locs = {s['location'].get('nameif') for s in sug['suggestions']}
        self.assertIn('dmz', locs)
        self.assertIn('inside', locs)

    def test_schema_version_present(self):
        result = asa_path_check(ASA_SAMPLE, '203.0.113.5', 'WEB',
                                proto='tcp', dports={443})
        sug = suggest_corrections(result, 'asa')
        self.assertEqual(sug['schema_version'], SCHEMA_VERSION)

    def test_unsupported_vendor(self):
        with self.assertRaises(ValueError):
            suggest_corrections({'allowed': False, 'acl': {'decision': 'no-match'}},
                                'paloalto')


if __name__ == '__main__':
    unittest.main()
