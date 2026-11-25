"""ui-qa-acceptance/scripts/with_server.py 回归测试。"""

from __future__ import annotations

import socket
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "skills" / "ui-qa-acceptance" / "scripts" / "with_server.py"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class TestWithServer(unittest.TestCase):
    def test_starts_http_server_runs_command_and_cleans_up_port(self):
        port = free_port()
        server_cmd = f"{sys.executable} -m http.server {port} --bind 127.0.0.1"
        client_code = (
            "import urllib.request; "
            f"resp = urllib.request.urlopen('http://127.0.0.1:{port}/'); "
            "assert resp.status == 200; "
            "print('HTTP_OK')"
        )
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--server",
                server_cmd,
                "--port",
                str(port),
                "--path",
                "/",
                "--timeout",
                "10",
                "--",
                sys.executable,
                "-c",
                client_code,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, proc.returncode, msg=proc.stderr + proc.stdout)
        self.assertIn("HTTP_OK", proc.stdout)

        # 退出后端口应已释放
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            self.assertNotEqual(0, sock.connect_ex(("127.0.0.1", port)))

    def test_rejects_mismatched_server_and_port_counts(self):
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--server",
                "echo a",
                "--server",
                "echo b",
                "--port",
                "12345",
                "--",
                "echo",
                "ok",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(2, proc.returncode)

    def test_rejects_missing_command(self):
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--server",
                "echo a",
                "--port",
                "12345",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(2, proc.returncode)


if __name__ == "__main__":
    unittest.main()
