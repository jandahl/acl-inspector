# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
import subprocess
import sys
import unittest
from pathlib import Path

from common.project_paths import project_root

from parsers.cisco.asa import path_check as asa_path_check, ASAConfig
from parsers.fortigate import path_check as ftg_path_check
from parsers.fortigate.config import FTGConfig
from parsers.fortigate import ir_export as ftg_ir_export
from parsers.suggest import suggest_corrections, SCHEMA_VERSION, as_str_list


_SCRIPT = project_root() / 'aclinspector.py'


class TestAsStrList(unittest.TestCase):
    def test_none_and_str_and_list(self):
        self.assertEqual(as_str_list(None), [])
        self.assertEqual(as_str_list([]), [])
        self.assertEqual(as_str_list("a"), ["a"])
        self.assertEqual(as_str_list(["a", "b"]), ["a", "b"])

    def test_coerces_elements_and_non_iterable(self):
        self.assertEqual(as_str_list([1, 2]), ["1", "2"])
        self.assertEqual(as_str_list(42), ["42"])


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

    def test_raw_ip_src_synthesises_address_object(self):
        # FTG_SAMPLE has SRC/WEB objects; 198.51.100.9 is a raw IP with no object.
        result = ftg_path_check(FTG_SAMPLE, '198.51.100.9', '203.0.113.50',
                                proto='tcp', dports={8443})
        cmds = result['suggestion']['suggestions'][0]['commands']
        self.assertIn('config firewall address', cmds)
        self.assertIn('    edit "IP_198.51.100.9"', cmds)
        self.assertTrue(any('set subnet 198.51.100.9 255.255.255.255' in c for c in cmds))
        self.assertTrue(any('set srcaddr "IP_198.51.100.9"' in c for c in cmds))
        self.assertTrue(any('Creates address object' in n
                            for n in result['suggestion']['suggestions'][0]['notes']))

    def test_raw_ip_reuses_existing_object_from_phonebook(self):
        # 192.168.1.10 already exists as object WEB -> reuse, no new object.
        result = ftg_path_check(FTG_SAMPLE, 'SRC', '192.168.1.10',
                                proto='tcp', dports={8443})
        cmds = result['suggestion']['suggestions'][0]['commands']
        self.assertTrue(any('set dstaddr "WEB"' in c for c in cmds))
        self.assertNotIn('config firewall address', cmds)

    def test_raw_cidr_synthesises_net_object(self):
        result = ftg_path_check(FTG_SAMPLE, 'SRC', '203.0.113.0/24',
                                proto='tcp', dports={8443})
        cmds = result['suggestion']['suggestions'][0]['commands']
        # The CIDR slash is sanitised out of the object name.
        self.assertIn('    edit "NET_203.0.113.0_24"', cmds)
        self.assertTrue(any('set subnet 203.0.113.0 255.255.255.0' in c for c in cmds))

    def test_synthesised_object_avoids_name_collision(self):
        # Existing object named IP_10.0.0.9 mapped to a *different* subnet must
        # not be clobbered; the generated object gets a suffixed name.
        cfg = """
config firewall address
    edit "IP_10.0.0.9"
        set subnet 172.16.0.1 255.255.255.255
    next
end
config firewall policy
    edit 1
        set srcintf "port1"
        set dstintf "port2"
        set srcaddr "all"
        set dstaddr "all"
        set service "ALL"
        set action deny
    next
end
"""
        result = ftg_path_check(cfg, '10.0.0.9', '203.0.113.7',
                                proto='tcp', dports={443})
        cmds = result['suggestion']['suggestions'][0]['commands']
        self.assertIn('    edit "IP_10.0.0.9_2"', cmds)

    def test_same_raw_ip_src_and_dst_no_duplicate_object(self):
        # When src == dst (same new IP), only one address object is created and
        # both endpoints reference it.
        result = ftg_path_check(FTG_SAMPLE, '198.51.100.9', '198.51.100.9',
                                proto='tcp', dports={8443})
        cmds = result['suggestion']['suggestions'][0]['commands']
        self.assertEqual(cmds.count('config firewall address'), 1)
        self.assertEqual(cmds.count('    edit "IP_198.51.100.9"'), 1)
        self.assertTrue(any('set srcaddr "IP_198.51.100.9"' in c for c in cmds))
        self.assertTrue(any('set dstaddr "IP_198.51.100.9"' in c for c in cmds))

    def test_ftg_verify_does_not_leak_object_name(self):
        # Object-name endpoints with no resolved IP must not leak into iprope.
        synthetic = {
            "allowed": False,
            "acl": {"decision": "implicit-deny", "matches": []},
            "input": {"proto": "tcp", "dports": [443], "src": "SRC", "dst": "WEB"},
            "resolved": {},
            "context": {},
        }
        verif = suggest_corrections(synthetic, "fortigate")['verification'][0]
        self.assertNotIn('SRC', verif['command'])
        self.assertNotIn('WEB', verif['command'])
        self.assertIn('<src_ip>', verif['command'])
        self.assertIn('<dst_ip>', verif['command'])

    def test_raw_ip_address_block_inside_vdom_wrap(self):
        result = ftg_path_check(FTG_VDOM_SAMPLE, '198.51.100.9', '203.0.113.50',
                                proto='tcp', dports={8443}, vdom='CUSTOMER_A')
        cmds = result['suggestion']['suggestions'][0]['commands']
        self.assertEqual(cmds[0], 'config vdom')
        self.assertEqual(cmds[1], 'edit CUSTOMER_A')
        self.assertEqual(cmds[-1], 'end')
        # address + policy blocks both live inside the single vdom wrap.
        self.assertEqual(cmds.count('config vdom'), 1)
        self.assertIn('config firewall address', cmds)
        self.assertIn('config firewall policy', cmds)

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

    def test_first_skips_none_in_list(self):
        from parsers.suggest import _first
        self.assertEqual(_first([None, 'port1']), 'port1')
        self.assertEqual(_first((None, None, 'p2')), 'p2')
        self.assertIsNone(_first([None, None]))

    def test_asa_verify_honors_ingress_override(self):
        result = asa_path_check(ASA_SAMPLE, '203.0.113.5', 'WEB',
                                proto='tcp', dports={443})
        sug = suggest_corrections(result, "asa", ingress_interface="dmz")
        verifs = sug['verification']
        self.assertTrue(verifs)
        # Every packet-tracer command must reference the overridden ingress.
        for v in verifs:
            self.assertIn('packet-tracer input dmz ', v['command'])

    def test_ftg_ipv6_synthesises_address6_object(self):
        from parsers.suggest import _ftg_resolve_addr
        name, block = _ftg_resolve_addr('2001:db8::1', [], set())
        # Name must be free of ':' and '/' (invalid in FortiOS object names).
        self.assertNotIn(':', name)
        self.assertNotIn('/', name)
        self.assertIn('config firewall address6', block)
        self.assertTrue(any('set ip6 2001:db8::1/128' in c for c in block))
        self.assertFalse(any('set subnet' in c for c in block))

        name6, block6 = _ftg_resolve_addr('2001:db8::/64', [], set())
        self.assertNotIn(':', name6)
        self.assertNotIn('/', name6)
        self.assertTrue(any('set ip6 2001:db8::/64' in c for c in block6))

    def test_asa_always_emits_ingress_even_when_only_egress_known(self):
        # ingress can't be inferred, egress is known -> still emit an ingress
        # placeholder rule (ASA policy is primarily inbound).
        synthetic = {
            "allowed": False,
            "acl": {"decision": "no-match", "matches": []},
            "input": {"proto": "tcp", "dports": [443], "src": "10.0.0.1", "dst": "10.0.0.2"},
            "resolved": {"src": "10.0.0.1", "dst": "10.0.0.2"},
            "context": {"src_interface": None, "dst_interface": "inside",
                        "packet_tracer": []},
        }
        sug = suggest_corrections(synthetic, "asa")
        scenarios = [s['scenario'] for s in sug['suggestions']]
        self.assertIn('ingress', scenarios)
        self.assertIn('egress', scenarios)
        ingress = next(s for s in sug['suggestions'] if s['scenario'] == 'ingress')
        self.assertEqual(ingress['location']['nameif'], '<nameif>')

    def test_first_handles_set_deterministically(self):
        from parsers.suggest import _first
        self.assertEqual(_first({'port2', 'port1'}), 'port1')  # sorted
        self.assertEqual(_first(['port9', 'port1']), 'port9')  # list order kept
        self.assertIsNone(_first(set()))
        # Mixed-type / None-containing sets must not raise TypeError.
        self.assertEqual(_first({None, 'port1'}), 'port1')
        self.assertIsNone(_first({None}))

    def test_asa_uses_real_bound_acl_name_no_convention_note(self):
        # ASA_SAMPLE binds 'outside_access_in' on outside; the ingress rule must
        # reference that real ACL and omit the 'convention' caveat.
        result = self._asa_blocked('203.0.113.5', 'WEB', proto='tcp', dports={443})
        ingress = next(s for s in result['suggestion']['suggestions']
                       if s['scenario'] == 'ingress')
        self.assertEqual(ingress['location']['acl'], 'outside_access_in')
        self.assertNotIn('convention', ' '.join(ingress.get('notes') or []))
        # The egress interface (inside) has no bound ACL -> convention caveat.
        egress = next((s for s in result['suggestion']['suggestions']
                       if s['scenario'] == 'egress'), None)
        if egress:
            self.assertIn('convention', ' '.join(egress.get('notes') or []))

    def test_asa_resolves_custom_acl_name(self):
        cfg = """
interface GigabitEthernet0/0
 nameif outside
 security-level 0
 ip address 203.0.113.2 255.255.255.0
!
object network WEB
 host 10.0.0.10
!
access-list OUTSIDE-IN extended permit tcp any host 10.0.0.99 eq 443
access-group OUTSIDE-IN in interface outside
"""
        result = asa_path_check(cfg, '203.0.113.5', 'WEB', proto='tcp', dports={443})
        ingress = next(s for s in result['suggestion']['suggestions']
                       if s['scenario'] == 'ingress')
        self.assertEqual(ingress['location']['acl'], 'OUTSIDE-IN')
        self.assertTrue(any('access-list OUTSIDE-IN extended permit' in c
                            for c in ingress['commands']))

    def test_notes_is_always_a_list(self):
        result = self._asa_blocked('203.0.113.5', 'WEB', proto='tcp', dports={443})
        for s in result['suggestion']['suggestions']:
            self.assertIsInstance(s.get('notes'), list)
        self.assertEqual(result['suggestion']['schema_version'], '1.2')

    def test_asa_explicit_deny_carries_ordering_note(self):
        cfg = ASA_SAMPLE + (
            "access-list outside_access_in extended deny ip any host 10.0.0.10\n"
        )
        result = asa_path_check(cfg, '203.0.113.5', 'WEB', proto='tcp', dports={443})
        self.assertEqual(result['suggestion']['reason'], 'explicit-deny')
        ingress = next(s for s in result['suggestion']['suggestions']
                       if s['scenario'] == 'ingress')
        joined = ' '.join(ingress['notes']).lower()
        self.assertIn('appended', joined)
        self.assertIn('reorder', joined)
        # Generic about ordering — no line-number assumption.
        self.assertNotIn('line <n>', joined)

    def test_implicit_deny_has_no_ordering_note(self):
        result = self._asa_blocked('203.0.113.5', 'WEB', proto='tcp', dports={443})
        for s in result['suggestion']['suggestions']:
            self.assertNotIn('reorder the permit', ' '.join(s.get('notes') or []))

    def test_ftg_explicit_deny_ordering_note(self):
        cfg = """
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
        set service "ALL"
        set action deny
    next
end
"""
        result = ftg_path_check(cfg, 'SRC', 'WEB', proto='tcp', dports={443})
        self.assertEqual(result['suggestion']['reason'], 'explicit-deny')
        notes = ' '.join(result['suggestion']['suggestions'][0]['notes']).lower()
        self.assertIn('edit 0', notes)
        self.assertIn('move', notes)

    def test_asa_egress_postnat_note(self):
        # Synthetic result where NAT translates the destination.
        synthetic = {
            "allowed": False,
            "acl": {"decision": "no-match", "matches": []},
            "input": {"proto": "tcp", "dports": [443],
                      "src": "10.0.0.1", "dst": "10.0.0.2"},
            "resolved": {"src": "10.0.0.1", "dst": "10.0.0.2",
                         "post_nat_dst": "203.0.113.9"},
            "context": {"src_interface": "outside", "dst_interface": "inside"},
        }
        sug = suggest_corrections(synthetic, "asa")
        egress = next(s for s in sug['suggestions'] if s['scenario'] == 'egress')
        self.assertTrue(any('post-NAT destination (203.0.113.9)' in n
                            for n in egress['notes']))

    def test_port_token_is_min_not_first(self):
        from parsers.suggest import _port_token
        self.assertEqual(_port_token('tcp', [8443, 443]), 443)  # unsorted list
        self.assertEqual(_port_token('tcp', []), None)
        self.assertIsNone(_port_token('icmp', [443]))

    def test_vdom_falls_back_to_context(self):
        # No vdom kwarg, but context carries it (replayed-result scenario).
        result = ftg_path_check(FTG_VDOM_SAMPLE, 'SRC', '203.0.113.50',
                                proto='tcp', dports={8443}, vdom='CUSTOMER_A')
        sug = suggest_corrections(result, "fortigate")  # no vdom kwarg
        cmds = sug['suggestions'][0]['commands']
        self.assertIn('edit CUSTOMER_A', cmds)

    def test_verify_asa_override_via_regex(self):
        result = asa_path_check(ASA_SAMPLE, '203.0.113.5', 'WEB',
                                proto='tcp', dports={443})
        sug = suggest_corrections(result, "asa", ingress_interface="dmz")
        for v in sug['verification']:
            self.assertIn('packet-tracer input dmz ', v['command'])

    def test_proto_number_resolves_named_protocols(self):
        from parsers.suggest import _proto_number
        self.assertEqual(_proto_number('gre'), 47)
        self.assertEqual(_proto_number('tcp'), 6)
        self.assertEqual(_proto_number('47'), 47)
        self.assertEqual(_proto_number('definitely-not-a-proto'), 0)

    def test_ftg_service_all_tcp_udp_without_ports(self):
        from parsers.suggest import _ftg_service_name
        self.assertEqual(_ftg_service_name('tcp', []), 'ALL_TCP')
        self.assertEqual(_ftg_service_name('udp', []), 'ALL_UDP')
        self.assertEqual(_ftg_service_name('tcp', [443]), 'TCP_443')

    def test_multiport_note_present(self):
        result = self._asa_blocked('203.0.113.5', 'WEB', proto='tcp',
                                   dports={443, 8443})
        notes = [' '.join(s.get('notes') or [])
                 for s in result['suggestion']['suggestions']]
        self.assertTrue(any('multiple destination ports' in n.lower() for n in notes))

    def test_single_port_has_no_multiport_note(self):
        result = self._asa_blocked('203.0.113.5', 'WEB', proto='tcp', dports={443})
        for s in result['suggestion']['suggestions']:
            joined = ' '.join(s.get('notes') or []).lower()
            self.assertNotIn('multiple destination ports', joined)

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


class TestVerifyFlagGuard(unittest.TestCase):
    def test_verify_without_packet_errors(self):
        proc = subprocess.run(
            [sys.executable, str(_SCRIPT), 'inspect', '--vendor', 'asa',
             '--config', '-', '--inspect', 'OBJ1', '--verify'],
            input='', text=True, capture_output=True,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn('--verify', proc.stderr)


if __name__ == '__main__':
    unittest.main()
