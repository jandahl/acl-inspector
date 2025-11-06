import json
import subprocess
import sys
import unittest
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = BASE_DIR / 'access-list-inspector.py'
CONFIG_PATH = BASE_DIR / 'tests' / 'fixtures' / 'configs' / 'asa' / 'tmp_asa.conf'


class TestCLIStdin(unittest.TestCase):
    def test_inspect_supports_stdin(self):
        config_text = CONFIG_PATH.read_text(encoding='utf-8')
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), '--vendor', 'asa', '--config', '-', '--inspect', 'OBJ1', '--format', 'json'],
            input=config_text,
            text=True,
            capture_output=True,
            check=True,
        )
        data = json.loads(proc.stdout)
        self.assertIn('10.0.0.1', data['target_nets'])
        self.assertGreater(len(data['hits']), 0)


if __name__ == '__main__':
    unittest.main()
