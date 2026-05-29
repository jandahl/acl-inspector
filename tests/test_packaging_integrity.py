# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Verification that the core package has no hidden dependency on scripts/."""

import sys
import unittest
from pathlib import Path


class PackagingIntegrityTest(unittest.TestCase):
    def test_loader_without_scripts_on_path(self):
        """Verify that parsers.loader works even if scripts/ is not in sys.path.
        
        This test runs in a subprocess to ensure absolute isolation and avoid
        polluting the global sys.path or sys.modules of the test runner.
        """
        import subprocess
        
        repo_root = Path(__file__).parent.parent.resolve()
        
        # This script runs in a clean subprocess. It manually sets sys.path
        # to include the repo root but explicitly EXCLUDES the scripts directory.
        code = f"""
import sys
import os
import tempfile
from pathlib import Path

# Add repo root but NOT scripts
repo_root = Path({repr(str(repo_root))})
sys.path.insert(0, str(repo_root))

# Ensure 'scripts' is NOT accidentally inherited in sys.path
scripts_path = repo_root / "scripts"
resolved_scripts = scripts_path.resolve()

sys.path = [p for p in sys.path if not p or not Path(p).exists() or Path(p).resolve() != resolved_scripts]

try:
    from parsers.loader import load_config
    
    config_text = "ASA Version 9.8(2)\\ninterface GigabitEthernet0/0\\n nameif outside"
    with tempfile.NamedTemporaryFile(suffix=".conf", mode="w", delete=False) as tmp:
        tmp.write(config_text)
        config_path = tmp.name

    try:
        cfg, vendor, score = load_config(config_path)
        if vendor != 'asa' or score < 80:
            print(f"Unexpected detection results: {{vendor}} ({{score}}%)")
            sys.exit(3)
            
        # Verify that scripts/ was not added back to sys.path by the loader
        for p in sys.path:
            try:
                if p and Path(p).resolve() == resolved_scripts:
                    print("Error: scripts/ was added to sys.path by parsers.loader")
                    sys.exit(2)
            except Exception:
                pass
    finally:
        try:
            os.unlink(config_path)
        except Exception:
            pass
except Exception as e:
    print(f"Import or execution error: {{e}}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

sys.exit(0)
"""
        res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Subprocess failed with exit code {res.returncode}. \nstdout: {res.stdout}\nstderr: {res.stderr}")


if __name__ == "__main__":
    unittest.main()
