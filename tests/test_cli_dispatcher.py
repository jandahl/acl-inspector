import os
import signal
import subprocess
import sys
import unittest
import socket
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "aclinspector.py"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestCliDispatcher(unittest.TestCase):
    def _run(self, *args, timeout=10):
        env = os.environ.copy()
        env["PYTHONPATH"] = ""
        proc = subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        if proc.returncode != 0:
            self.fail(
                f"{' '.join(args)} exited {proc.returncode}\nSTDOUT:\n{proc.stdout.decode()}\nSTDERR:\n{proc.stderr.decode()}"
            )

    def test_inspect_help_runs(self):
        self._run("inspect", "--help")

    def test_web_help_runs(self):
        self._run("web", "--help")

    def test_web_ctrl_c_is_graceful(self):
        port = free_port()
        env = os.environ.copy()
        env["PYTHONPATH"] = ""
        env["PYTHONUNBUFFERED"] = "1"
        env.setdefault("ACLINSPECTOR_CONFIGS_CISCO", str(ROOT / "configs" / "cisco"))
        env.setdefault("ACLINSPECTOR_CONFIGS_FORTIGATE", str(ROOT / "configs" / "fortigate"))
        cmd = [
            sys.executable,
            str(CLI),
            "web",
            "--addr",
            "127.0.0.1",
            "--port",
            str(port),
        ]
        proc = subprocess.Popen(
            cmd,
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout_lines = []
        stderr_output = ""
        try:
            deadline = time.time() + 15
            while time.time() < deadline:
                line = proc.stdout.readline()
                if not line:
                    if proc.poll() is not None:
                        break
                    continue
                stdout_lines.append(line)
                if "Web UI running" in line:
                    break
            else:
                self.fail("web server did not report startup in time")
            proc.send_signal(signal.SIGINT)
            proc.wait(timeout=10)
        finally:
            try:
                stdout_lines.extend(proc.stdout.readlines())
            except Exception:
                pass
            try:
                stderr_output = proc.stderr.read()
            except Exception:
                stderr_output = ""
            try:
                proc.stdout.close()
            except Exception:
                pass
            try:
                proc.stderr.close()
            except Exception:
                pass
            if proc.poll() is None:
                proc.kill()
        self.assertEqual(
            proc.returncode,
            0,
            f"Expected graceful shutdown, got {proc.returncode}\nSTDERR:\n{stderr_output}",
        )
        self.assertNotIn("Traceback", stderr_output or "")

    def test_translate_help_runs(self):
        self._run("translate", "--help")

    def test_optimize_help_runs(self):
        self._run("optimize", "--help")

    def test_tui_help_runs_or_skips(self):
        try:
            import textual  # noqa: F401
        except Exception:
            self.skipTest("textual not installed")
        self._run("tui", "--help")


if __name__ == "__main__":
    unittest.main()
