# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Test interface/ACL binding and direction mapping."""

import unittest
from parsers.cisco.asa.parser import ASAConfig


class TestInterfaceACLBinding(unittest.TestCase):
    """Test that ACL entries correctly capture binding and direction information."""

    def test_interface_bound_acl_populates_fields(self):
        """ACL bound to interface should populate bound_to and direction."""
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
        entries = cfg.flatten_acl()

        # Should have one entry
        self.assertEqual(len(entries), 1)

        entry = entries[0]
        # Check that bound_to and direction are populated
        self.assertEqual(entry['bound_to'], 'outside')
        self.assertEqual(entry['direction'], 'in')
        self.assertEqual(entry['acl'], 'OUTSIDE_IN')

        # Binding dict should also exist
        self.assertIsNotNone(entry['binding'])
        self.assertEqual(entry['binding']['interface'], 'outside')
        self.assertEqual(entry['binding']['direction'], 'in')
        self.assertEqual(entry['binding']['scope'], 'interface')

    def test_global_acl_binding(self):
        """Global ACL should have bound_to='global' and direction='global'."""
        config = """
object network Server
 host 10.1.1.50
!
access-list GLOBAL_ACL extended permit tcp any object Server eq 443
access-group GLOBAL_ACL global
        """
        cfg = ASAConfig(config)
        entries = cfg.flatten_acl()

        self.assertEqual(len(entries), 1)
        entry = entries[0]

        self.assertEqual(entry['bound_to'], 'global')
        self.assertEqual(entry['direction'], 'global')
        self.assertEqual(entry['binding']['scope'], 'global')

    def test_control_plane_acl_binding(self):
        """Control-plane ACL should have bound_to='control-plane'."""
        config = """
access-list CP_IN extended permit tcp any any eq 22
access-group CP_IN control-plane in interface management
        """
        cfg = ASAConfig(config)
        entries = cfg.flatten_acl()

        self.assertEqual(len(entries), 1)
        entry = entries[0]

        self.assertEqual(entry['bound_to'], 'control-plane')
        self.assertEqual(entry['direction'], 'in')
        self.assertEqual(entry['binding']['scope'], 'control-plane')
        self.assertEqual(entry['binding']['interface'], 'management')

    def test_unbound_acl_has_none_values(self):
        """ACL without access-group binding should have None for bound_to/direction."""
        config = """
object network Host
 host 10.1.1.100
!
access-list UNBOUND extended permit tcp any object Host eq 80
        """
        cfg = ASAConfig(config)
        entries = cfg.flatten_acl()

        self.assertEqual(len(entries), 1)
        entry = entries[0]

        # Unbound ACL should have None
        self.assertIsNone(entry['bound_to'])
        self.assertIsNone(entry['direction'])
        self.assertIsNone(entry['binding'])

    def test_multiple_acls_different_bindings(self):
        """Multiple ACLs with different bindings should preserve correct associations."""
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
!
access-list OUTSIDE_IN extended permit tcp any object WebServer eq https
access-list INSIDE_OUT extended permit tcp object WebServer any eq 443
access-list GLOBAL extended permit icmp any any

access-group OUTSIDE_IN in interface outside
access-group INSIDE_OUT out interface inside
access-group GLOBAL global
        """
        cfg = ASAConfig(config)
        entries = cfg.flatten_acl()

        # Should have 3 entries
        self.assertEqual(len(entries), 3)

        # Find each entry by ACL name
        outside_in = next(e for e in entries if e['acl'] == 'OUTSIDE_IN')
        inside_out = next(e for e in entries if e['acl'] == 'INSIDE_OUT')
        global_acl = next(e for e in entries if e['acl'] == 'GLOBAL')

        # Check OUTSIDE_IN
        self.assertEqual(outside_in['bound_to'], 'outside')
        self.assertEqual(outside_in['direction'], 'in')

        # Check INSIDE_OUT
        self.assertEqual(inside_out['bound_to'], 'inside')
        self.assertEqual(inside_out['direction'], 'out')

        # Check GLOBAL
        self.assertEqual(global_acl['bound_to'], 'global')
        self.assertEqual(global_acl['direction'], 'global')

    def test_interface_without_direction_defaults_to_any(self):
        """Access-group without direction should default to 'any'."""
        config = """
interface GigabitEthernet0/0
 nameif dmz
!
access-list DMZ_ACL extended permit tcp any any eq 80
access-group DMZ_ACL interface dmz
        """
        cfg = ASAConfig(config)
        entries = cfg.flatten_acl()

        self.assertEqual(len(entries), 1)
        entry = entries[0]

        self.assertEqual(entry['bound_to'], 'dmz')
        self.assertEqual(entry['direction'], 'any')

    def test_graceful_handling_of_malformed_binding(self):
        """Malformed bindings should not crash parser."""
        config = """
access-list TEST extended permit ip any any
access-group TEST invalid_syntax_here
        """
        # Should not raise exception
        try:
            cfg = ASAConfig(config)
            entries = cfg.flatten_acl()
            # Entry should exist but binding might be partial
            self.assertEqual(len(entries), 1)
        except Exception as e:
            self.fail(f"Parser should handle malformed binding gracefully: {e}")


if __name__ == '__main__':
    unittest.main()
