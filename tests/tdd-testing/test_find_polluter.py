"""tdd-testing/scripts/find_polluter.py 回归测试。"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "skills" / "tdd-testing" / "scripts" / "find_polluter.py"


class TestFindPolluter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_case(self, name: str, body: str) -> str:
        path = self.root / name
        path.write_text(body, encoding="utf-8")
        return str(path)

    def test_identifies_first_polluter_and_stops_early(self):
        clean = self._write_case("case_a.py", "print('clean')\n")
        bad = self._write_case(
            "case_b.py",
            "from pathlib import Path\nPath('dirty.flag').write_text('oops')\n",
        )
        later = self._write_case(
            "case_c.py",
            "from pathlib import Path\nPath('should_not_run.flag').write_text('nope')\n",
        )

        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--artifact",
                "dirty.flag",
                "--cmd",
                f"{sys.executable} {{file}}",
                "--cwd",
                str(self.root),
                "--json",
                clean,
                bad,
                later,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(1, proc.returncode)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["found"])
        self.assertEqual(bad, payload["polluter"])
        self.assertEqual(2, len(payload["checked"]))
        self.assertFalse((self.root / "should_not_run.flag").exists())

    def test_returns_zero_when_no_file_pollutes(self):
        c1 = self._write_case("ok1.py", "pass\n")
        c2 = self._write_case("ok2.py", "pass\n")
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--artifact",
                "dirty.flag",
                "--cmd",
                f"{sys.executable} {{file}}",
                "--cwd",
                str(self.root),
                "--json",
                c1,
                c2,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, proc.returncode)
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["found"])
        self.assertIsNone(payload["polluter"])

    def test_refuses_when_artifact_already_exists_or_placeholder_missing(self):
        c1 = self._write_case("ok.py", "pass\n")
        (self.root / "preexisting.flag").write_text("already there", encoding="utf-8")

        pre = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--artifact",
                "preexisting.flag",
                "--cmd",
                f"{sys.executable} {{file}}",
                "--cwd",
                str(self.root),
                c1,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(2, pre.returncode)

        bad_tpl = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--artifact",
                "dirty.flag",
                "--cmd",
                f"{sys.executable} -V",
                "--cwd",
                str(self.root),
                c1,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(2, bad_tpl.returncode)


if __name__ == "__main__":
    unittest.main()
