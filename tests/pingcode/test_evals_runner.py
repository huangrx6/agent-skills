#!/usr/bin/env python3
"""evals 执行器的结构、dry-run 与可配置 agent/judge 测试。"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNNER_PATH = HERE.parents[1] / "skills" / "pingcode" / "dev-tools" / "run_evals.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("_pingcode_run_evals", RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("加载不了 run_evals.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runner = _load_runner()


class EvalsRunnerCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.evals = {
            "evals": [{
                "id": 1,
                "prompt": "列出缺陷",
                "expected_output": "调用 workitem list --type bug",
                "files": [],
            }]
        }

    def write_evals(self, payload=None) -> str:
        path = os.path.join(self._tmp.name, "evals.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload or self.evals, fh, ensure_ascii=False)
        return path

    def test_check_通过(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = runner.main(["--evals", self.write_evals(), "--check"])
        self.assertEqual(0, code)
        self.assertIn("结构有效", out.getvalue())

    def test_重复_id_报错(self):
        payload = {"evals": [self.evals["evals"][0], dict(self.evals["evals"][0])]}
        code = runner.main(["--evals", self.write_evals(payload), "--check"])
        self.assertEqual(2, code)

    def test_dry_run_不执行_agent(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = runner.main([
                "--evals", self.write_evals(), "--dry-run",
                "--agent-cmd", f"{sys.executable} -c 'print(1)'",
            ])
        self.assertEqual(0, code)
        self.assertIn("列出缺陷", out.getvalue())
        self.assertIn("print(1)", out.getvalue())

    def test_agent_和_judge_可执行并落盘(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = runner.main([
                "--evals", self.write_evals(),
                "--agent-cmd", f"{sys.executable} -c 'print(\"agent ok\")'",
                "--judge-cmd", f"{sys.executable} -c 'import sys; sys.exit(0)' {{actual}}",
                "--output-dir", os.path.join(self._tmp.name, "runs"),
            ])
        self.assertEqual(0, code)
        results = os.path.join(self._tmp.name, "runs", "results.json")
        self.assertTrue(os.path.exists(results))
        with open(results, encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual("ok", data["status"])
        self.assertEqual("pass", data["results"][0]["status"])
        transcript = data["results"][0]["transcript"]
        with open(transcript, encoding="utf-8") as fh:
            self.assertIn("agent ok", fh.read())


if __name__ == "__main__":
    unittest.main(verbosity=2)
