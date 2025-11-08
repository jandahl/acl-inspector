"""Test packet evaluation and path checking."""

import unittest
from parsers.cisco.asa.parser import ASAConfig


class TestPacketEvaluation(unittest.TestCase):
    """Test packet evaluation using evaluate_packet() method."""

    def test_permit_by_explicit_acl(self):
        """Packet explicitly permitted by ACL should return permit verdict."""
        config = """
interface GigabitEthernet0/0
 nameif outside
 ip address 203.0.113.1 255.255.255.0
 security-level 0
!
interface GigabitEthernet0/1
 nameif inside
 ip address 192.168.1.1 255.255.255.0
 security-level 100
!
object network WebServer
 host 192.168.1.50
!
access-list OUTSIDE_IN extended permit tcp any object WebServer eq 443
access-group OUTSIDE_IN in interface outside
        """
        cfg = ASAConfig(config)

        # External client to internal web server on port 443
        result = cfg.evaluate_packet(
            src_ip='1.1.1.1',
            dst_ip='192.168.1.50',
            proto='tcp',
            dst_port=443
        )

        self.assertEqual(result['verdict'], 'permit')
        self.assertEqual(result['matched_acl'], 'OUTSIDE_IN')
        self.assertIsNotNone(result['matched_entry'])
        self.assertIn('OUTSIDE_IN', result['explanation'])

    def test_deny_by_explicit_acl(self):
        """Packet explicitly denied by ACL should return deny verdict."""
        config = """
interface GigabitEthernet0/0
 nameif outside
 ip address 203.0.113.1 255.255.255.0
 security-level 0
!
interface GigabitEthernet0/1
 nameif inside
 ip address 192.168.1.1 255.255.255.0
 security-level 100
!
object network WebServer
 host 192.168.1.50
!
access-list OUTSIDE_IN extended deny tcp any object WebServer eq 23
access-list OUTSIDE_IN extended permit ip any any
access-group OUTSIDE_IN in interface outside
        """
        cfg = ASAConfig(config)

        # External client trying telnet to internal server - should be denied
        result = cfg.evaluate_packet(
            src_ip='1.1.1.1',
            dst_ip='192.168.1.50',
            proto='tcp',
            dst_port=23
        )

        self.assertEqual(result['verdict'], 'deny')
        self.assertEqual(result['matched_acl'], 'OUTSIDE_IN')
        self.assertIn('23', result['matched_entry']['raw'])

    def test_implicit_permit_higher_to_lower_security(self):
        """Traffic from higher to lower security should be implicitly permitted."""
        config = """
interface GigabitEthernet0/0
 nameif outside
 ip address 203.0.113.1 255.255.255.0
 security-level 0
!
interface GigabitEthernet0/1
 nameif inside
 ip address 192.168.1.1 255.255.255.0
 security-level 100
        """
        cfg = ASAConfig(config)

        # Inside (sec 100) to outside (sec 0) - should be implicitly permitted
        result = cfg.evaluate_packet(
            src_ip='192.168.1.100',
            dst_ip='203.0.113.200',
            proto='tcp',
            dst_port=443
        )

        self.assertEqual(result['verdict'], 'implicit-permit')
        self.assertIsNone(result['matched_acl'])

    def test_implicit_deny_lower_to_higher_security(self):
        """Traffic from lower to higher security without ACL should be denied."""
        config = """
interface GigabitEthernet0/0
 nameif outside
 ip address 203.0.113.1 255.255.255.0
 security-level 0
!
interface GigabitEthernet0/1
 nameif inside
 ip address 192.168.1.1 255.255.255.0
 security-level 100
        """
        cfg = ASAConfig(config)

        # Outside (sec 0) to inside (sec 100) without ACL - should be denied
        result = cfg.evaluate_packet(
            src_ip='203.0.113.200',
            dst_ip='192.168.1.100',
            proto='tcp',
            dst_port=443
        )

        self.assertEqual(result['verdict'], 'implicit-deny')
        self.assertIsNone(result['matched_acl'])

    def test_port_range_matching(self):
        """Packet with port in range should match range ACL."""
        config = """
interface GigabitEthernet0/0
 nameif outside
 ip address 203.0.113.1 255.255.255.0
 security-level 0
!
interface GigabitEthernet0/1
 nameif inside
 ip address 192.168.1.1 255.255.255.0
 security-level 100
!
access-list OUTSIDE_IN extended permit tcp any any range 8000 8999
access-group OUTSIDE_IN in interface outside
        """
        cfg = ASAConfig(config)

        # Port 8080 is in range 8000-8999
        result = cfg.evaluate_packet(
            src_ip='1.1.1.1',
            dst_ip='192.168.1.50',
            proto='tcp',
            dst_port=8080
        )

        self.assertEqual(result['verdict'], 'permit')

        # Port 9000 is outside range
        result2 = cfg.evaluate_packet(
            src_ip='1.1.1.1',
            dst_ip='192.168.1.50',
            proto='tcp',
            dst_port=9000
        )

        self.assertEqual(result2['verdict'], 'implicit-deny')

    def test_global_acl_blocks_traffic(self):
        """Global ACL should apply to all traffic."""
        config = """
interface GigabitEthernet0/1
 nameif inside
 ip address 192.168.1.1 255.255.255.0
 security-level 100
!
access-list GLOBAL extended deny tcp any any eq 23
access-group GLOBAL global
        """
        cfg = ASAConfig(config)

        # Telnet should be blocked by global ACL
        result = cfg.evaluate_packet(
            src_ip='192.168.1.100',
            dst_ip='8.8.8.8',
            proto='tcp',
            dst_port=23
        )

        self.assertEqual(result['verdict'], 'deny')
        self.assertEqual(result['matched_acl'], 'GLOBAL')

    def test_protocol_matching(self):
        """Packet protocol must match ACL protocol."""
        config = """
interface GigabitEthernet0/0
 nameif outside
 ip address 203.0.113.1 255.255.255.0
 security-level 0
!
interface GigabitEthernet0/1
 nameif inside
 ip address 192.168.1.1 255.255.255.0
 security-level 100
!
access-list OUTSIDE_IN extended permit tcp any any
access-group OUTSIDE_IN in interface outside
        """
        cfg = ASAConfig(config)

        # TCP should be permitted
        result_tcp = cfg.evaluate_packet(
            src_ip='1.1.1.1',
            dst_ip='192.168.1.50',
            proto='tcp',
            dst_port=80
        )
        self.assertEqual(result_tcp['verdict'], 'permit')

        # UDP should not match TCP ACL
        result_udp = cfg.evaluate_packet(
            src_ip='1.1.1.1',
            dst_ip='192.168.1.50',
            proto='udp',
            dst_port=53
        )
        self.assertEqual(result_udp['verdict'], 'implicit-deny')

    def test_steps_provided(self):
        """Result should include detailed evaluation steps."""
        config = """
interface GigabitEthernet0/0
 nameif outside
 ip address 203.0.113.1 255.255.255.0
 security-level 0
!
interface GigabitEthernet0/1
 nameif inside
 ip address 192.168.1.1 255.255.255.0
 security-level 100
!
access-list OUTSIDE_IN extended permit tcp any any eq 443
access-group OUTSIDE_IN in interface outside
        """
        cfg = ASAConfig(config)

        result = cfg.evaluate_packet(
            src_ip='1.1.1.1',
            dst_ip='192.168.1.50',
            proto='tcp',
            dst_port=443
        )

        self.assertIn('steps', result)
        self.assertIsInstance(result['steps'], list)
        self.assertGreater(len(result['steps']), 0)

        # Should have flow classification step
        step_types = [s.get('step') for s in result['steps']]
        self.assertIn('flow_classification', step_types)

    def test_invalid_ip_returns_error(self):
        """Invalid IP address should return error verdict."""
        config = """
interface GigabitEthernet0/1
 nameif inside
 ip address 192.168.1.1 255.255.255.0
        """
        cfg = ASAConfig(config)

        result = cfg.evaluate_packet(
            src_ip='not.an.ip.address',
            dst_ip='192.168.1.100'
        )

        self.assertEqual(result['verdict'], 'error')
        self.assertIn('error', result)


if __name__ == '__main__':
    unittest.main()
