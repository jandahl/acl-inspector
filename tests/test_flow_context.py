"""Test vendor-agnostic FlowContext generation."""

import unittest
from parsers.cisco.asa.parser import ASAConfig
from parsers import model as ir


class TestFlowContext(unittest.TestCase):
    """Test FlowContext generation for packet flow analysis."""

    def test_inbound_flow_from_external(self):
        """Inbound flow from external network should identify correct context."""
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
access-list OUTSIDE_IN extended permit tcp any object WebServer eq https
access-group OUTSIDE_IN in interface outside
        """
        cfg = ASAConfig(config)

        # External client (1.1.1.1) to internal web server (192.168.1.50)
        ctx = cfg.build_flow_context(
            src_ip='1.1.1.1',
            dst_ip='192.168.1.50',
            proto='tcp',
            dst_port=443
        )

        # Assertions
        self.assertEqual(ctx.src_ip, '1.1.1.1')
        self.assertEqual(ctx.dst_ip, '192.168.1.50')
        self.assertEqual(ctx.proto, 'tcp')
        self.assertEqual(ctx.dst_port, 443)

        # Direction
        self.assertEqual(ctx.flow_direction, 'inbound')

        # Zones (ASA uses interfaces)
        self.assertIsNone(ctx.ingress_zone)  # Source is external
        self.assertEqual(ctx.egress_zone, 'inside')  # Dest is on inside interface

        # Applicable policies
        self.assertIn('OUTSIDE_IN', ctx.applicable_policies)

        # Vendor context
        self.assertEqual(ctx.vendor_context['ingress_security_level'], 0)
        self.assertEqual(ctx.vendor_context['egress_security_level'], 100)
        self.assertFalse(ctx.vendor_context['implicit_permit'])

    def test_outbound_flow_to_internet(self):
        """Outbound flow to internet should identify correct context."""
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
access-list INSIDE_OUT extended permit tcp any any eq 443
access-group INSIDE_OUT out interface inside
        """
        cfg = ASAConfig(config)

        # Internal client to external server
        ctx = cfg.build_flow_context(
            src_ip='192.168.1.100',
            dst_ip='8.8.8.8',
            proto='tcp',
            dst_port=443
        )

        self.assertEqual(ctx.flow_direction, 'outbound')
        self.assertEqual(ctx.ingress_zone, 'inside')
        self.assertIsNone(ctx.egress_zone)  # Dest is external

    def test_lateral_flow_between_interfaces(self):
        """Lateral flow between two internal interfaces."""
        config = """
interface GigabitEthernet0/0
 nameif dmz
 ip address 10.0.1.1 255.255.255.0
 security-level 50
!
interface GigabitEthernet0/1
 nameif inside
 ip address 192.168.1.1 255.255.255.0
 security-level 100
!
access-list DMZ_IN extended permit tcp any any eq 80
access-list INSIDE_OUT extended permit tcp any any
access-group DMZ_IN in interface dmz
access-group INSIDE_OUT out interface inside
        """
        cfg = ASAConfig(config)

        # From inside to DMZ
        ctx = cfg.build_flow_context(
            src_ip='192.168.1.100',
            dst_ip='10.0.1.50',
            proto='tcp',
            dst_port=80
        )

        self.assertEqual(ctx.flow_direction, 'lateral')
        self.assertEqual(ctx.ingress_zone, 'inside')
        self.assertEqual(ctx.egress_zone, 'dmz')

        # Should have ingress ACL (in on inside) + egress ACL (out on inside) + any global
        # Note: ASA evaluates ACLs based on direction and interface
        self.assertIsInstance(ctx.applicable_policies, list)

    def test_global_acl_included_in_all_flows(self):
        """Global ACLs should apply to all flows."""
        config = """
interface GigabitEthernet0/1
 nameif inside
 ip address 192.168.1.1 255.255.255.0
!
access-list GLOBAL extended deny tcp any any eq 23
access-list INSIDE_OUT extended permit ip any any
access-group GLOBAL global
access-group INSIDE_OUT out interface inside
        """
        cfg = ASAConfig(config)

        ctx = cfg.build_flow_context(
            src_ip='192.168.1.100',
            dst_ip='8.8.8.8'
        )

        # Global ACL should be in applicable policies
        self.assertIn('GLOBAL', ctx.applicable_policies)

    def test_implicit_permit_higher_to_lower_security(self):
        """Flow from higher to lower security level has implicit permit."""
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

        # Inside (sec 100) to outside (sec 0) - implicit permit
        ctx = cfg.build_flow_context(
            src_ip='192.168.1.100',
            dst_ip='203.0.113.200'
        )

        self.assertTrue(ctx.vendor_context['implicit_permit'])
        self.assertEqual(ctx.vendor_context['ingress_security_level'], 100)
        self.assertEqual(ctx.vendor_context['egress_security_level'], 0)

    def test_no_implicit_permit_lower_to_higher_security(self):
        """Flow from lower to higher security level requires ACL."""
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

        # Outside (sec 0) to inside (sec 100) - no implicit permit
        ctx = cfg.build_flow_context(
            src_ip='203.0.113.200',
            dst_ip='192.168.1.100'
        )

        self.assertFalse(ctx.vendor_context['implicit_permit'])

    def test_nat_rules_included_for_matching_interfaces(self):
        """NAT rules matching interface pair should be included."""
        config = """
interface GigabitEthernet0/0
 nameif outside
 ip address 203.0.113.1 255.255.255.0
!
interface GigabitEthernet0/1
 nameif inside
 ip address 192.168.1.1 255.255.255.0
!
object network WebServer
 host 192.168.1.50
 nat (inside,outside) static 203.0.113.50
        """
        cfg = ASAConfig(config)

        ctx = cfg.build_flow_context(
            src_ip='192.168.1.50',
            dst_ip='8.8.8.8'
        )

        # Should include NAT rule
        self.assertTrue(len(ctx.applicable_nats) > 0)
        # NAT rule should reference the interface pair
        self.assertIsInstance(ctx.applicable_nats, list)

    def test_transit_flow_no_local_interfaces(self):
        """Flow with no local interfaces is transit."""
        config = """
interface GigabitEthernet0/1
 nameif inside
 ip address 192.168.1.1 255.255.255.0
        """
        cfg = ASAConfig(config)

        # Both IPs external
        ctx = cfg.build_flow_context(
            src_ip='8.8.8.8',
            dst_ip='1.1.1.1'
        )

        self.assertEqual(ctx.flow_direction, 'transit')
        self.assertIsNone(ctx.ingress_zone)
        self.assertIsNone(ctx.egress_zone)

    def test_loopback_same_interface(self):
        """Flow within the same interface is loopback."""
        config = """
interface GigabitEthernet0/1
 nameif inside
 ip address 192.168.1.1 255.255.255.0
        """
        cfg = ASAConfig(config)

        # Both on same interface
        ctx = cfg.build_flow_context(
            src_ip='192.168.1.100',
            dst_ip='192.168.1.200'
        )

        self.assertEqual(ctx.flow_direction, 'loopback')
        self.assertEqual(ctx.ingress_zone, 'inside')
        self.assertEqual(ctx.egress_zone, 'inside')

    def test_invalid_ip_raises_value_error(self):
        """Malformed IP addresses should raise ValueError."""
        config = """
interface GigabitEthernet0/1
 nameif inside
 ip address 192.168.1.1 255.255.255.0
        """
        cfg = ASAConfig(config)

        with self.assertRaises(ValueError) as cm:
            cfg.build_flow_context(
                src_ip='not.an.ip.address',
                dst_ip='192.168.1.100'
            )

        self.assertIn("Invalid IP address", str(cm.exception))

    def test_flow_context_serializable_to_dict(self):
        """FlowContext should be JSON-serializable via _jsonable."""
        config = """
interface GigabitEthernet0/1
 nameif inside
 ip address 192.168.1.1 255.255.255.0
        """
        cfg = ASAConfig(config)

        ctx = cfg.build_flow_context(
            src_ip='192.168.1.100',
            dst_ip='8.8.8.8',
            proto='tcp',
            dst_port=443
        )

        # Should be able to convert to dict via IR's _jsonable
        from parsers.model import _jsonable
        ctx_dict = _jsonable(ctx)

        # Verify structure
        self.assertEqual(ctx_dict['src_ip'], '192.168.1.100')
        self.assertEqual(ctx_dict['dst_ip'], '8.8.8.8')
        self.assertEqual(ctx_dict['proto'], 'tcp')
        self.assertEqual(ctx_dict['dst_port'], 443)
        self.assertIsInstance(ctx_dict['vendor_context'], dict)
        self.assertIsInstance(ctx_dict['applicable_policies'], list)


if __name__ == '__main__':
    unittest.main()
