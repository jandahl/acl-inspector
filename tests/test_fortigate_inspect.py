# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
import subprocess
import sys
import json
import unittest
from common.project_paths import ensure_pythonpath_env, project_root


class TestFortiGateFindHost(unittest.TestCase):
    """Tests for --find-host with --vendor fortigate (issue #66)."""

    FTG_FIXTURE = str(project_root() / 'tests/fixtures/configs/fortigate/sample.conf')

    def _run_find_host(self, query, extra_args=None):
        cli = project_root() / "aclinspector.py"
        cmd = [
            sys.executable, str(cli),
            "inspect", "--vendor", "fortigate",
            "--config", self.FTG_FIXTURE,
            "--vdom", "root",
            "--find-host", query,
            "--format", "json",
        ]
        if extra_args:
            cmd.extend(extra_args)
        return subprocess.run(
            cmd, capture_output=True, text=True,
            cwd=project_root(), env=ensure_pythonpath_env(),
        )

    def test_find_host_by_object_name(self):
        """--find-host WEB_SERVER resolves the named address object."""
        result = self._run_find_host("WEB_SERVER")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data['query'], 'WEB_SERVER')
        self.assertEqual(len(data['results']), 1)
        r = data['results'][0]
        self.assertIn('WEB_SERVER', r['objects'])
        self.assertIn('10.1.1.10/32', r['literals'])

    def test_find_host_by_ip(self):
        """--find-host 10.1.1.10 resolves via ip_to_objects reverse lookup."""
        result = self._run_find_host("10.1.1.10")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data['query'], '10.1.1.10')
        self.assertEqual(len(data['results']), 1)
        r = data['results'][0]
        self.assertIn('WEB_SERVER', r['objects'])

    def test_find_host_addrgrp(self):
        """--find-host BACKEND_SERVERS resolves the group and its members."""
        result = self._run_find_host("BACKEND_SERVERS")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        data = json.loads(result.stdout)
        r = data['results'][0]
        self.assertIn('BACKEND_SERVERS', r['objects'])
        self.assertTrue(
            '10.1.1.10/32' in r['literals'] or '10.1.1.20/32' in r['literals'],
            msg=f"Expected member IPs in literals, got: {r['literals']}"
        )

    def test_find_host_vip(self):
        """--find-host VIP_WEB resolves the virtual IP object and its external IP."""
        result = self._run_find_host("VIP_WEB")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data['query'], 'VIP_WEB')
        self.assertEqual(len(data['results']), 1)
        r = data['results'][0]
        self.assertIn('VIP_WEB', r['objects'])
        self.assertIn('203.0.113.1', r['literals'])

    def test_find_host_cidr(self):
        """--find-host 192.168.10.0/24 resolves via ip_to_objects CIDR lookup."""
        result = self._run_find_host("192.168.10.0/24")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data['query'], '192.168.10.0/24')
        self.assertEqual(len(data['results']), 1)
        r = data['results'][0]
        self.assertIn('APP_NET', r['objects'])

    def test_find_host_no_match_returns_empty(self):
        """--find-host for an unknown object produces no results."""
        result = self._run_find_host("NONEXISTENT_OBJECT_XYZZY")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data['results'], [])


if __name__ == '__main__':
    unittest.main()
