import unittest

from parsers.cisco.asa import ASAConfig


ASA_NAT_SAMPLE = """
object network OBJ_INSIDE
 host 10.0.0.10
 nat (inside,outside) static OBJ_PUBLIC
object network OBJ_PUBLIC
 host 198.51.100.10
object network OBJ_APP
 host 10.0.2.20
object network OBJ_POOL
 subnet 10.0.3.0 255.255.255.0
object network OBJ_POOL_PUB
 host 198.51.100.200
object network OBJ_DMZ_SRV
 host 10.0.1.50
object network OBJ_DMZ_SRV_PUB
 host 203.0.113.50
object network OBJ_WEB
 host 198.51.100.50
!
nat (inside,outside) 20 source static OBJ_POOL OBJ_POOL_PUB
nat (inside,outside) before-auto source static OBJ_DMZ_SRV OBJ_DMZ_SRV_PUB destination static OBJ_WEB OBJ_WEB service tcp source eq 80 tcp destination eq 8080
nat (inside,outside) after-auto source dynamic OBJ_APP interface
"""


class TestASANATParsing(unittest.TestCase):
    def test_normalized_nat_rules(self):
        cfg = ASAConfig(ASA_NAT_SAMPLE)
        rules = cfg.normalized_nat_rules()
        self.assertEqual(len(rules), 4)
        sections = [r['section'] for r in rules]
        self.assertEqual(sections, [1, 1, 2, 3])

        # Section 1 rule with sequence number
        seq_rule = rules[0]
        self.assertEqual(seq_rule['sequence'], 20)
        self.assertIn('10.0.3.0/24', seq_rule['src_real_values'])
        self.assertIn('198.51.100.200', seq_rule['src_mapped_values'])

        # Policy NAT with service translation
        policy_rule = rules[1]
        self.assertTrue(policy_rule['policy'])
        service = policy_rule['service']
        self.assertIsNotNone(service)
        self.assertEqual(service['real']['value'], '80')
        self.assertEqual(service['mapped']['value'], '8080')
        self.assertIn('198.51.100.50', policy_rule['dst_real_values'])

        # Object (auto) NAT captured in section 2
        auto_rule = rules[2]
        self.assertEqual(auto_rule['type'], 'auto')
        self.assertIn('10.0.0.10', auto_rule['real_values'])
        self.assertIn('198.51.100.10', auto_rule['mapped_values'])

        # After-auto rule should PAT to interface
        after_auto = rules[3]
        self.assertEqual(after_auto['section'], 3)
        self.assertEqual(after_auto['src_mapped_values'], ['interface'])


if __name__ == '__main__':
    unittest.main()
