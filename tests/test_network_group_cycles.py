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


if __name__ == '__main__':
    unittest.main()
