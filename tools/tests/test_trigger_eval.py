"""触发评测脚本：模板、算分与退出码。

这个脚本本身不跑模型，所以测试也只能盯「算得对不对」：正例率低于阈值要算失败，
反例被过度唤醒也要算失败，输入坏了要能和「评测没过」区分开。
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TOOL = ROOT / "tools" / "trigger_eval.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("trigger_eval_under_test", TOOL)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {TOOL}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _triggers(positive: int = 8, negative: int = 8) -> dict:
    cases = [{"id": i, "query": f"正例请求 {i}", "should_trigger": True}
             for i in range(1, positive + 1)]
    cases += [{"id": positive + i, "query": f"近邻反例 {i}", "should_trigger": False,
               "note": "→ 别的 skill"} for i in range(1, negative + 1)]
    return {"skill_name": "demo", "triggers": cases}


class TriggerEvalTest(unittest.TestCase):
    def setUp(self):
        self.mod = _load_tool()
        self.root = tempfile.mkdtemp(prefix="trigger-eval-")
        os.makedirs(os.path.join(self.root, "skills", "demo", "evals"))
        self.write_triggers(_triggers())

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write_triggers(self, payload: dict) -> None:
        path = os.path.join(self.root, "skills", "demo", "evals", "triggers.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)

    def write_results(self, name: str, payload) -> str:
        path = os.path.join(self.root, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(payload if isinstance(payload, str)
                         else json.dumps(payload, ensure_ascii=False))
        return path

    def run_tool(self, *args: str) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = self.mod.main(["--root", self.root, *args])
        return code, out.getvalue() + err.getvalue()

    def expected_results(self, covered: bool = True) -> list[dict]:
        rows = []
        for case in _triggers()["triggers"]:
            rows.append({"skill": "demo", "id": case["id"], "runs": 3,
                         "triggered": 3 if case["should_trigger"] else 0})
        return rows

    # ── 模板 ──
    def test_template_lists_every_case(self):
        out_path = os.path.join(self.root, "results.json")
        code, _text = self.run_tool("--template", out_path, "--runs", "5")
        self.assertEqual(0, code)
        with open(out_path, encoding="utf-8") as handle:
            rows = json.load(handle)
        self.assertEqual(16, len(rows))
        self.assertTrue(all(row["runs"] == 5 for row in rows))
        self.assertTrue(all(row["triggered"] == 0 for row in rows))

    # ── 算分 ──
    def test_all_correct_passes(self):
        path = self.write_results("ok.json", self.expected_results())
        code, text = self.run_tool("--score", path)
        self.assertEqual(0, code, text)
        self.assertIn("通过 16", text)

    def test_missed_positive_fails(self):
        rows = self.expected_results()
        rows[0]["triggered"] = 1  # 正例只触发 1/3，低于阈值
        path = self.write_results("miss.json", rows)
        code, text = self.run_tool("--score", path)
        self.assertEqual(1, code)
        self.assertIn("应触发，实际 1/3", text)

    def test_false_positive_fails(self):
        rows = self.expected_results()
        negative = next(row for row in rows if row["id"] > 8)
        negative["triggered"] = 2  # 反例被唤醒 2/3，超过阈值
        path = self.write_results("fp.json", rows)
        code, text = self.run_tool("--score", path)
        self.assertEqual(1, code)
        self.assertIn("不应触发，实际 2/3", text)

    def test_threshold_is_adjustable(self):
        rows = self.expected_results()
        rows[0]["triggered"] = 1
        path = self.write_results("low.json", rows)
        code, _text = self.run_tool("--score", path, "--threshold", "0.3")
        self.assertEqual(0, code, "阈值降到 0.3 后 1/3 应算通过")

    def test_missing_case_is_reported(self):
        rows = self.expected_results()[:-1]
        path = self.write_results("short.json", rows)
        code, text = self.run_tool("--score", path)
        self.assertEqual(1, code)
        self.assertIn("未记录", text)

    # ── 输入问题与评测失败要分开 ──
    def test_unknown_skill_is_input_error(self):
        path = self.write_results("unknown.json", [
            {"skill": "nope", "id": 1, "runs": 1, "triggered": 0}])
        code, _text = self.run_tool("--score", path)
        self.assertEqual(1, code, "未知 skill 的 id 会变成未记录 → 评测未过，不是输入错误")

    def test_triggered_over_runs_is_input_error(self):
        rows = self.expected_results()
        rows[0]["triggered"] = 99
        path = self.write_results("bad.json", rows)
        code, text = self.run_tool("--score", path)
        self.assertEqual(2, code, text)

    def test_zero_runs_is_input_error(self):
        rows = self.expected_results()
        rows[0]["runs"] = 0
        path = self.write_results("zero.json", rows)
        code, _text = self.run_tool("--score", path)
        self.assertEqual(2, code)

    def test_broken_json_is_input_error(self):
        path = self.write_results("broken.json", "{ 不是 json")
        code, _text = self.run_tool("--score", path)
        self.assertEqual(2, code)

    def test_no_mode_prints_help(self):
        code, _text = self.run_tool()
        self.assertEqual(2, code)


if __name__ == "__main__":
    unittest.main()
