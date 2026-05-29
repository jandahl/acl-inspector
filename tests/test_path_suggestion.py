# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
import unittest

from parsers.cisco.asa import path_check as asa_path_check, ASAConfig
from parsers.fortigate import path_check as ftg_path_check
from parsers.fortigate.config import FTGConfig
from parsers.fortigate import ir_export as ftg_ir_export
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


class TestSuggestionEdgeCases(unittest.TestCase):
    """Address formatting, port-less protocols, and service-name synthesis."""

    def _asa_blocked(self, src, dst, **kw):
        return asa_path_check(ASA_SAMPLE, src, dst, **kw)

    def test_asa_icmp_has_no_port_qualifier(self):
        result = self._asa_blocked('203.0.113.5', 'WEB', proto='icmp')
        cmds = [c for s in result['suggestion']['suggestions'] for c in s['commands']]
        self.assertTrue(cmds)
        self.assertTrue(all(' eq ' not in c for c in cmds))
        self.assertTrue(all('permit icmp' in c for c in cmds))

    def test_asa_network_destination_uses_mask(self):
        # When a caller hands us a network (rather than a single host),
        # the ACL line should render 'net mask', not 'host'. path_check
        # itself collapses to a host, so exercise the formatter via a
        # synthetic result dict (the documented public contract).
        synthetic = {
            "allowed": False,
            "acl": {"decision": "no-match", "matches": []},
            "input": {"proto": "tcp", "dports": [443], "src": "any", "dst": "10.0.0.0/24"},
            "resolved": {"src": "203.0.113.5", "dst": "10.0.0.0/24"},
            "context": {"src_interface": "outside", "dst_interface": "inside",
                        "packet_tracer": []},
        }
        sug = suggest_corrections(synthetic, "asa")
        cmds = [c for s in sug['suggestions'] for c in s['commands']]
        self.assertTrue(any('10.0.0.0 255.255.255.0' in c for c in cmds))
        self.assertFalse(any('host 10.0.0.0' in c for c in cmds))

    def test_ftg_service_synthesis_variants(self):
        # icmp -> ALL_ICMP, no proto -> ALL.
        icmp = ftg_path_check(FTG_SAMPLE, 'SRC', '203.0.113.50', proto='icmp')
        icmp_cmds = icmp['suggestion']['suggestions'][0]['commands']
        self.assertTrue(any('set service "ALL_ICMP"' in c for c in icmp_cmds))

        bare = ftg_path_check(FTG_SAMPLE, 'SRC', '203.0.113.50')
        bare_cmds = bare['suggestion']['suggestions'][0]['commands']
        self.assertTrue(any('set service "ALL"' in c for c in bare_cmds))

    def test_ftg_verification_proto_number_for_icmp(self):
        result = ftg_path_check(FTG_SAMPLE, 'SRC', '203.0.113.50', proto='icmp')
        verif = result['suggestion']['verification'][0]['command']
        # iprope proto-number for icmp is 1.
        self.assertRegex(verif, r'iprope lookup .* 1 ')

    def test_asa_verification_is_deduplicated(self):
        result = self._asa_blocked('203.0.113.5', 'WEB', proto='tcp', dports={443})
        cmds = [v['command'] for v in result['suggestion']['verification']]
        self.assertEqual(len(cmds), len(set(cmds)))

    def test_asa_wildcard_and_unresolved_tokens(self):
        # 'any' must collapse to 'any'; an unresolved object name must NOT get a
        # 'host' prefix (would be invalid ASA syntax).
        synthetic = {
            "allowed": False,
            "acl": {"decision": "no-match", "matches": []},
            "input": {"proto": "tcp", "dports": [443], "src": "any", "dst": "WEB"},
            "resolved": {"src": "any", "dst": "WEB"},  # dst unresolved -> name
            "context": {"src_interface": "outside", "dst_interface": "inside",
                        "packet_tracer": []},
        }
        cmds = [c for s in suggest_corrections(synthetic, "asa")['suggestions']
                for c in s['commands']]
        self.assertTrue(cmds)
        self.assertTrue(all('host any' not in c for c in cmds))
        self.assertTrue(all('host WEB' not in c for c in cmds))
        self.assertTrue(any('permit tcp any WEB eq 443' in c for c in cmds))

    def test_asa_egress_equals_ingress_emits_single_rule(self):
        # When ingress and egress resolve to the same nameif, only one rule.
        sug = suggest_corrections(
            {"allowed": False, "acl": {"decision": "no-match", "matches": []},
             "input": {"proto": "tcp", "dports": [443], "src": "a", "dst": "b"},
             "resolved": {"src": "10.0.0.1", "dst": "10.0.0.2"},
             "context": {"packet_tracer": []}},
            "asa", ingress_interface="dmz", egress_interface="dmz")
        self.assertEqual(len(sug['suggestions']), 1)
        self.assertEqual(sug['suggestions'][0]['scenario'], 'ingress')

    def test_multi_port_collapses_to_first(self):
        # Pass an explicit list so the test does not rely on set ordering;
        # path_check sorts dports, so the lowest (443) is the representative.
        result = asa_path_check(ASA_SAMPLE, '203.0.113.5', 'WEB', proto='tcp',
                                dports={443, 8443})
        cmds = [c for s in result['suggestion']['suggestions'] for c in s['commands']]
        self.assertTrue(all('eq 443' in c for c in cmds))
        self.assertFalse(any('eq 8443' in c for c in cmds))

    def test_asa_addr_token_none_does_not_leak(self):
        # A malformed result with no resolvable endpoints must not emit a bare
        # 'None' token in the generated ACL line.
        synthetic = {
            "allowed": False,
            "acl": {"decision": "no-match", "matches": []},
            "input": {"proto": "tcp", "dports": [443], "src": None, "dst": None},
            "resolved": {"src": None, "dst": None},
            "context": {"src_interface": "outside", "packet_tracer": []},
        }
        cmds = [c for s in suggest_corrections(synthetic, "asa")['suggestions']
                for c in s['commands']]
        self.assertTrue(cmds)
        self.assertTrue(all('None' not in c for c in cmds))

    def test_ftg_verification_honors_interface_overrides(self):
        # The verification command must match the suggested policy interface
        # when overrides are supplied (no <in>/<out> vs port mismatch).
        result = ftg_path_check(FTG_SAMPLE, 'SRC', '203.0.113.50',
                                proto='tcp', dports={443})
        sug = suggest_corrections(result, "fortigate",
                                  ingress_interface="wan1",
                                  egress_interface="lan")
        self.assertIn('wan1', sug['suggestions'][0]['location']['srcintf'])
        verif_cmd = sug['verification'][0]['command']
        self.assertIn('wan1', verif_cmd)
        self.assertNotIn('<in>', verif_cmd)

    def test_asa_ipv6_network_uses_prefix_notation(self):
        from parsers.suggest import _asa_addr_token
        self.assertEqual(_asa_addr_token('2001:db8::/64'), '2001:db8::/64')
        self.assertEqual(_asa_addr_token('2001:db8::1/128'), 'host 2001:db8::1')
        self.assertEqual(_asa_addr_token('::/0'), 'any')
        # IPv4 still uses dotted netmask.
        self.assertEqual(_asa_addr_token('10.0.0.0/24'), '10.0.0.0 255.255.255.0')

    def test_first_handles_set_deterministically(self):
        from parsers.suggest import _first
        self.assertEqual(_first({'port2', 'port1'}), 'port1')  # sorted
        self.assertEqual(_first(['port9', 'port1']), 'port9')  # list order kept
        self.assertIsNone(_first(set()))
        # Mixed-type / None-containing sets must not raise TypeError.
        self.assertEqual(_first({None, 'port1'}), 'port1')
        self.assertIsNone(_first({None}))

    def test_asa_suggestion_carries_acl_name_note(self):
        result = self._asa_blocked('203.0.113.5', 'WEB', proto='tcp', dports={443})
        for s in result['suggestion']['suggestions']:
            self.assertIn('convention', (s.get('note') or ''))

    def test_multiport_note_present(self):
        result = self._asa_blocked('203.0.113.5', 'WEB', proto='tcp',
                                   dports={443, 8443})
        notes = [s.get('note') or '' for s in result['suggestion']['suggestions']]
        self.assertTrue(any('multiple destination ports' in n.lower() for n in notes))

    def test_single_port_has_no_multiport_note(self):
        result = self._asa_blocked('203.0.113.5', 'WEB', proto='tcp', dports={443})
        for s in result['suggestion']['suggestions']:
            self.assertNotIn('multiple destination ports', (s.get('note') or '').lower())

    def test_ftg_verification_no_none_leak_on_missing_endpoints(self):
        synthetic = {
            "allowed": False,
            "acl": {"decision": "implicit-deny", "matches": []},
            "input": {"proto": "tcp", "dports": [443], "src": None, "dst": None},
            "resolved": {},
            "context": {},
        }
        verif = suggest_corrections(synthetic, "fortigate")['verification'][0]
        self.assertNotIn('None', verif['command'])
        self.assertIn('<src_ip>', verif['command'])
        self.assertIn('<dst_ip>', verif['command'])

    def test_ftg_numeric_protocol_in_verification(self):
        # A numeric protocol token (e.g. GRE=47) is passed through, not zeroed.
        synthetic = {
            "allowed": False,
            "acl": {"decision": "implicit-deny", "matches": []},
            "input": {"proto": "47", "dports": [], "src": "SRC", "dst": "DST"},
            "resolved": {"src": "10.0.0.1", "dst": "10.0.0.2"},
            "context": {},
        }
        verif = suggest_corrections(synthetic, "fortigate")['verification'][0]
        self.assertRegex(verif['command'], r'iprope lookup .* 47 ')


class TestIRMetadata(unittest.TestCase):
    """The IR fields added to support rule generation must be populated."""

    def test_asa_acl_entry_carries_ingress_interface(self):
        dev = ASAConfig(ASA_SAMPLE).to_ir()
        entry = dev.acls[0].entries[0]
        # 'access-group outside_access_in in interface outside' -> ingress on outside.
        self.assertEqual(entry.src_interfaces, ['outside'])
        self.assertEqual(entry.dst_interfaces, [])
        self.assertEqual(entry.direction, 'in')

    def test_fortigate_policy_entry_carries_src_dst_interfaces(self):
        dev = ftg_ir_export.to_ir(FTGConfig(FTG_SAMPLE))
        entry = dev.acls[0].entries[0]
        self.assertEqual(entry.src_interfaces, ['port1'])
        self.assertEqual(entry.dst_interfaces, ['port2'])

    def test_fortigate_device_and_interface_vdom_zone(self):
        cfg_text = (
            "config vdom\n"
            "edit CUSTOMER_A\n"
            "config system interface\n"
            '    edit "port1"\n'
            "        set ip 10.0.0.1 255.255.255.0\n"
            "    next\n"
            "end\n"
            "config system zone\n"
            '    edit "trust"\n'
            '        set interface "port1"\n'
            "    next\n"
            "end\n"
            "end\n"
        )
        dev = ftg_ir_export.to_ir(FTGConfig(cfg_text, vdom='CUSTOMER_A'))
        self.assertEqual(dev.vdom, 'CUSTOMER_A')
        iface = next(i for i in dev.interfaces if i.name == 'port1')
        self.assertEqual(iface.zone, 'trust')
        self.assertEqual(iface.vdom, 'CUSTOMER_A')


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
