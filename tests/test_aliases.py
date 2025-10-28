import unittest
import ipaddress

from parsers.cisco.asa import inspect_host


class TestAliases(unittest.TestCase):
    def test_duplicate_host_objects(self):
        cfg_text = """
object network HOST_A
 host 10.1.1.1
object network HOST_B
 host 10.1.1.1
access-list TEST extended permit ip object HOST_A any
"""
        report = inspect_host(cfg_text, 'HOST_A')
        aliases = report.get('aliases')
        self.assertIn(ipaddress.ip_address('10.1.1.1'), aliases)
        self.assertEqual(aliases[ipaddress.ip_address('10.1.1.1')], {'HOST_B'})

    def test_no_aliases_for_unique_host(self):
        cfg_text = """
object network HOST_A
 host 10.1.1.1
object network HOST_B
 host 10.1.1.2
access-list TEST extended permit ip object HOST_A any
"""
        report = inspect_host(cfg_text, 'HOST_A')
        aliases = report.get('aliases')
        self.assertTrue(aliases == {} or ipaddress.ip_address('10.1.1.1') not in aliases)


if __name__ == '__main__':
    unittest.main()
