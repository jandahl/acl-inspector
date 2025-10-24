import unittest
import os

from parsers.cisco import asa as cisco_asa
from parsers.fortigate import fortigate as ftg


def _load(path):
    with open(path, 'r') as f:
        return f.read()


class TestExamplesCrossVendor(unittest.TestCase):
    def setUp(self):
        self.asa_cfg = _load('configs/cisco/ciscoasa-example')
        self.ftg_cfg = _load('configs/fortigate/fortigate7-2-example')

    def test_host_a_rules_equivalence(self):
        # Host A should have DB:1433 and WEB:443 permits in both vendors
        asa_report = cisco_asa.inspect_host(self.asa_cfg, 'HOST_A', service_filter=None)
        ftg_report = ftg.inspect_host(self.ftg_cfg, 'HOST_A', service_filter=None, vdom='root')
        # Basic sanity: at least two hits in both
        self.assertGreaterEqual(len(asa_report['hits']), 2)
        self.assertGreaterEqual(len(ftg_report['hits']), 2)
        # Check that we can filter by tcp:1433 and tcp:443 and get at least one in each
        f_1433 = {'proto': 'tcp', 'dports': {1433}}
        f_443 = {'proto': 'tcp', 'dports': {443}}
        asa_1433 = cisco_asa.inspect_host(self.asa_cfg, 'HOST_A', service_filter=f_1433)['hits']
        asa_443 = cisco_asa.inspect_host(self.asa_cfg, 'HOST_A', service_filter=f_443)['hits']
        ftg_1433 = ftg.inspect_host(self.ftg_cfg, 'HOST_A', service_filter=f_1433, vdom='root')['hits']
        ftg_443 = ftg.inspect_host(self.ftg_cfg, 'HOST_A', service_filter=f_443, vdom='root')['hits']
        self.assertGreaterEqual(len(asa_1433), 1)
        self.assertGreaterEqual(len(asa_443), 1)
        self.assertGreaterEqual(len(ftg_1433), 1)
        self.assertGreaterEqual(len(ftg_443), 1)

    def test_host_b_db_only(self):
        # Host B should only have DB:1433 permit, not WEB:443
        f_1433 = {'proto': 'tcp', 'dports': {1433}}
        f_443 = {'proto': 'tcp', 'dports': {443}}
        asa_1433 = cisco_asa.inspect_host(self.asa_cfg, 'HOST_B', service_filter=f_1433)['hits']
        asa_443 = [e for e in cisco_asa.inspect_host(self.asa_cfg, 'HOST_B', service_filter=f_443)['hits'] if e['action'] == 'permit']
        ftg_1433 = ftg.inspect_host(self.ftg_cfg, 'HOST_B', service_filter=f_1433, vdom='root')['hits']
        ftg_443 = [e for e in ftg.inspect_host(self.ftg_cfg, 'HOST_B', service_filter=f_443, vdom='root')['hits'] if e['action'] == 'permit']
        self.assertGreaterEqual(len(asa_1433), 1)
        self.assertEqual(len(asa_443), 0)
        self.assertGreaterEqual(len(ftg_1433), 1)
        self.assertEqual(len(ftg_443), 0)


if __name__ == '__main__':
    unittest.main()
