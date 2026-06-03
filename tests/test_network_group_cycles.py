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
        ports = {str(m['v1']) for m in resolved if m.get('op') == 'eq'}
        self.assertEqual(ports, {'80', '443'})
        self.assertEqual(len(resolved), 2)

    def test_service_group_cycle_port_before_group_object(self):
        """Port accumulated before recursive group-object call must not be duplicated.

        Regression for issue #64: pre-caching the mutable accumulator lets
        cycle re-entry return partial members, so both groups resolve fully
        without the incomplete-eviction mechanism discarding correct results.
        """
        cfg_text = """
object-group service S_A tcp
 port-object eq 80
 group-object S_B
object-group service S_B tcp
 group-object S_A
 port-object eq 443
"""
        cfg = ASAConfig(cfg_text)
        for name, expected_ports in [('S_A', {'80', '443'}), ('S_B', {'80', '443'})]:
            with self.subTest(group=name):
                resolved = cfg.resolve_service_group(name)
                ports = {str(m['v1']) for m in resolved if m.get('op') == 'eq'}
                self.assertEqual(ports, expected_ports)
                self.assertEqual(len(resolved), 2)


    def test_non_cyclic_ancestor_of_cycle_stays_cached(self):
        """Non-cyclic ancestors of cyclic groups must not be evicted (issue #65).

        The pre-cache in resolve_network catches cycle re-entry before the
        visited check fires, so incomplete stays empty and no eviction occurs.
        """
        cfg_text = """
object network HOST_A
 host 10.0.0.1
object network HOST_B
 host 10.0.0.2
object-group network OUTER
 group-object CYCLIC_A
 network-object object HOST_B
object-group network CYCLIC_A
 group-object CYCLIC_B
 network-object object HOST_A
object-group network CYCLIC_B
 group-object CYCLIC_A
"""
        cfg = ASAConfig(cfg_text)
        import ipaddress as _ip
        result = cfg.resolve_network('OUTER')
        self.assertIn(_ip.ip_address('10.0.0.1'), result)
        self.assertIn(_ip.ip_address('10.0.0.2'), result)
        # All three groups must remain cached — no spurious eviction
        for name in ('OUTER', 'CYCLIC_A', 'CYCLIC_B'):
            self.assertIn(name, cfg._network_cache, msg=f'{name} was spuriously evicted')


if __name__ == '__main__':
    unittest.main()
