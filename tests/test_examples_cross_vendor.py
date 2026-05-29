# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
import unittest

from parsers.cisco import asa as cisco_asa
from parsers.fortigate import fortigate as ftg


def _load(path):
    with open(path, 'r') as f:
        return f.read()


class TestExamplesCrossVendor(unittest.TestCase):
    def setUp(self):
        self.asa_cfg = _load('configs/cisco/cisco-asa-example')
        self.ftg_cfg = _load('configs/fortigate/fortigate7-4-example')
        self.vdom = 'Alpha'

    def test_lobby_net_http_and_https(self):
        asa_report = cisco_asa.inspect_host(self.asa_cfg, 'alpha_lobby_net', service_filter=None)
        ftg_report = ftg.inspect_host(self.ftg_cfg, 'lobby-net', service_filter=None, vdom=self.vdom)
        self.assertGreaterEqual(len(asa_report['hits']), 5)
        self.assertGreaterEqual(len(ftg_report['hits']), 5)

        f_http = {'proto': 'tcp', 'dports': {80}}
        f_https = {'proto': 'tcp', 'dports': {443}}
        asa_http = cisco_asa.inspect_host(self.asa_cfg, 'alpha_lobby_net', service_filter=f_http)['hits']
        asa_https = cisco_asa.inspect_host(self.asa_cfg, 'alpha_lobby_net', service_filter=f_https)['hits']
        ftg_http = ftg.inspect_host(self.ftg_cfg, 'lobby-net', service_filter=f_http, vdom=self.vdom)['hits']
        ftg_https = ftg.inspect_host(self.ftg_cfg, 'lobby-net', service_filter=f_https, vdom=self.vdom)['hits']
        self.assertGreaterEqual(len(asa_http), 1)
        self.assertGreaterEqual(len(asa_https), 1)
        self.assertGreaterEqual(len(ftg_http), 1)
        self.assertGreaterEqual(len(ftg_https), 1)

    def test_lobby_net_dns_and_ntp(self):
        f_dns = {'proto': 'udp', 'dports': {53}}
        f_ntp = {'proto': 'udp', 'dports': {123}}
        asa_dns = cisco_asa.inspect_host(self.asa_cfg, 'alpha_lobby_net', service_filter=f_dns)['hits']
        asa_ntp = cisco_asa.inspect_host(self.asa_cfg, 'alpha_lobby_net', service_filter=f_ntp)['hits']
        ftg_dns = ftg.inspect_host(self.ftg_cfg, 'lobby-net', service_filter=f_dns, vdom=self.vdom)['hits']
        ftg_ntp = ftg.inspect_host(self.ftg_cfg, 'lobby-net', service_filter=f_ntp, vdom=self.vdom)['hits']
        self.assertGreaterEqual(len(asa_dns), 1)
        self.assertGreaterEqual(len(asa_ntp), 1)
        self.assertGreaterEqual(len(ftg_dns), 1)
        self.assertGreaterEqual(len(ftg_ntp), 1)


if __name__ == '__main__':
    unittest.main()
