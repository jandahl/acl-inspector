import unittest

from parsers.cisco.asa import ASAConfig


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
access-list OUT extended permit tcp any object WEB_REAL eq 443
access-group OUT in interface outside
"""


class TestNatParse(unittest.TestCase):
    def test_interfaces_acl_bindings_and_nat(self):
        cfg = ASAConfig(ASA_SAMPLE)
        # Interfaces parsed
        self.assertIn('outside', cfg.interfaces)
        self.assertIn('inside', cfg.interfaces)
        self.assertEqual(cfg.interfaces['outside']['security_level'], 0)
        self.assertEqual(cfg.interfaces['inside']['security_level'], 100)
        # ACL binding
        binding = cfg.acl_bindings.get('OUT')
        self.assertIsNotNone(binding)
        self.assertEqual(binding.get('interface'), 'outside')
        self.assertEqual(binding.get('direction'), 'in')
        entry = cfg.flatten_acl()[0]
        self.assertEqual(entry['binding'].get('interface'), 'outside')
        self.assertEqual(entry['binding'].get('direction'), 'in')
        # NAT rules: auto and manual present
        kinds = sorted([r['type'] for r in cfg.nat_rules])
        self.assertEqual(kinds, ['auto', 'manual'])
        auto = [r for r in cfg.nat_rules if r['type'] == 'auto'][0]
        self.assertEqual(auto['src_if'], 'inside')
        self.assertEqual(auto['dst_if'], 'outside')
        self.assertEqual(auto['real_object'], 'WEB_REAL')
        self.assertEqual(auto['kind'], 'static')
        self.assertEqual(auto['mapped'], '203.0.113.10')
        man = [r for r in cfg.nat_rules if r['type'] == 'manual'][0]
        self.assertEqual(man['section'], 1)
        self.assertEqual(man['source']['real'], 'SRC')
        self.assertEqual(man['source']['mapped'], 'SRC_NAT')


if __name__ == '__main__':
    unittest.main()
