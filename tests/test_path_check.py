import unittest

from parsers.cisco.asa import path_check


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
object network WEB_REAL
 host 10.0.0.10
 nat (inside,outside) static 203.0.113.10
!
object network SRC
 host 10.0.1.10
object network SRC_NAT
 host 198.51.100.50
!
nat (inside,outside) source static SRC SRC_NAT
!
access-list OUT extended permit tcp object SRC_NAT object WEB_REAL eq 443
access-list OUT extended permit tcp any object SRC eq 443
access-group OUT in interface outside
"""


class TestPathCheck(unittest.TestCase):
    def test_path_permit_with_nat(self):
        result = path_check(ASA_SAMPLE, 'SRC', 'WEB_REAL', proto='tcp', dports={443})
        self.assertTrue(result['allowed'])
        nat = result['nat']
        self.assertTrue(nat['applied'])
        self.assertEqual(nat.get('direction'), 'outbound')
        self.assertIn('nat (inside,outside) source static', nat['rule']['raw'])
        self.assertEqual(nat['translations']['src']['after'], '198.51.100.50')
        acl = result['acl']
        self.assertEqual(acl['decision'], 'permit')
        self.assertTrue(any('SRC_NAT' in m['raw'] for m in acl.get('matches', [])))
        ctx = result.get('context') or {}
        self.assertEqual(ctx.get('nat_direction'), 'outbound')
        self.assertIn({'interface': 'outside', 'direction': 'in'}, ctx.get('acl_candidates', []))

    def test_path_inbound_static(self):
        result = path_check(ASA_SAMPLE, '198.51.100.200', 'SRC_NAT', proto='tcp', dports={443})
        self.assertTrue(result['allowed'])
        nat = result['nat']
        self.assertTrue(nat['applied'])
        self.assertEqual(nat.get('direction'), 'inbound')
        self.assertEqual(nat['translations']['dst']['after'], '10.0.1.10')
        acl = result['acl']
        self.assertEqual(acl['decision'], 'permit')
        self.assertTrue(any('object SRC eq 443' in m['raw'] for m in acl.get('matches', [])))
        ctx = result.get('context') or {}
        self.assertEqual(ctx.get('nat_direction'), 'inbound')
        self.assertIn({'interface': 'outside', 'direction': 'in'}, ctx.get('acl_candidates', []))


if __name__ == '__main__':
    unittest.main()
