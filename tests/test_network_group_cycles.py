# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
import ipaddress
import unittest

from parsers.cisco.asa.parser import ASAConfig


class TestNetworkGroupCycles(unittest.TestCase):
    def test_mutually_referenced_groups_resolve_members(self):
        cfg_text = """
object network HOST_A
 host 10.10.10.1
object network HOST_B
 host 10.10.10.2
object-group network GROUP_A
 network-object object HOST_A
 group-object GROUP_B
object-group network GROUP_B
 network-object object HOST_B
 group-object GROUP_A
"""
        cfg = ASAConfig(cfg_text)
        expected = {
            ipaddress.ip_address('10.10.10.1'),
            ipaddress.ip_address('10.10.10.2'),
        }
        self.assertEqual(cfg.resolve_network('GROUP_A'), expected)
        self.assertEqual(cfg.resolve_network('GROUP_B'), expected)

    def test_transitive_cycle(self):
        """Test A -> B -> C -> A cycle."""
        cfg_text = """
object-group network A
 group-object B
object-group network B
 group-object C
object-group network C
 group-object A
 network-object 1.1.1.1 255.255.255.255
"""
        cfg = ASAConfig(cfg_text)
        expected = {ipaddress.ip_network('1.1.1.1/32')}
        self.assertEqual(cfg.resolve_network('A'), expected)
        self.assertEqual(cfg.resolve_network('B'), expected)
        self.assertEqual(cfg.resolve_network('C'), expected)

    def test_non_cyclic_diamond(self):
        """Test A -> B, A -> C, B -> D, C -> D diamond (not a cycle)."""
        cfg_text = """
object-group network A
 group-object B
 group-object C
object-group network B
 group-object D
object-group network C
 group-object D
object-group network D
 network-object 2.2.2.2 255.255.255.255
"""
        cfg = ASAConfig(cfg_text)
        expected = {ipaddress.ip_network('2.2.2.2/32')}
        self.assertEqual(cfg.resolve_network('A'), expected)
        # Verify that cache is correctly populated and not spuriously cleared
        self.assertIn('D', cfg._network_cache)
        self.assertEqual(cfg._network_cache['D'], expected)

    def test_service_group_cycle(self):
        """Test cycle detection in service object-groups."""
        cfg_text = """
object-group service S_A tcp
 group-object S_B
 port-object eq 80
object-group service S_B tcp
 group-object S_A
 port-object eq 443
"""
        cfg = ASAConfig(cfg_text)
        resolved = cfg.resolve_service_group('S_A')
        # S_A should have 80 and 443 (from B)
        # Note: resolve_service_group returns List[dict]
        ports = set()
        for m in resolved:
            if m.get('op') == 'eq':
                ports.add(m['v1'])
        self.assertEqual(ports, {'80', '443'})


if __name__ == '__main__':
    unittest.main()
