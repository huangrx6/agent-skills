"""触发评测运行器：用例挑选、会话解析、结果折算与 --list。

运行器要真的起 `pi` 会话，测试里不能跑；能自动化盯住的是它周围的判断：
哪些记录算「skill 被加载」、按 skill/编号挑用例挑得对不对、
以及 0.5 这个阈值在两边的判定。
"""

from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TOOL = ROOT / "tools" / "trigger_run.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("trigger_run_under_test", TOOL)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {TOOL}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ParseSessionTests(unittest.TestCase):
    def setUp(self):
        self.tool = _load_tool()

    def test_only_skill_events_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "r1"
            session.mkdir()
            records = [
                {"customType": "loaded-skill", "data": {"name": "deck-authoring"}},
                {"customType": "inline-skill", "data": {"name": "diagram-authoring"}},
                # 工具调用也带 name，混进来会把「读了文件」当成「加载了 skill」
                {"customType": "tool-call", "data": {"name": "read"}},
                {"customType": "loaded-skill", "data": {"name": "deck-authoring"}},
            ]
            (session / "a.jsonl").write_text(
                "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
                encoding="utf-8")
            self.assertEqual(self.tool.parse_session(str(session)),
                             ["deck-authoring", "diagram-authoring"])

    def test_bad_lines_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "r1"
            session.mkdir()
            (session / "a.jsonl").write_text(
                'not json\n{"customType":"loaded-skill","data":{"name":"diagram-authoring"}}\n',
                encoding="utf-8")
            self.assertEqual(self.tool.parse_session(str(session)), ["diagram-authoring"])

    def test_missing_dir_returns_empty(self):
        self.assertEqual(self.tool.parse_session("/definitely/not/here"), [])


class SelectCasesTests(unittest.TestCase):
    def setUp(self):
        self.tool = _load_tool()

    def test_all_cases_by_default(self):
        cases = self.tool.select_cases(str(ROOT), None, None)
        self.assertGreaterEqual(len(cases), 5)
        self.assertTrue(all({"skill", "id", "query", "expect"} <= set(c) for c in cases))

    def test_filter_by_skill(self):
        cases = self.tool.select_cases(str(ROOT), ["deck-authoring"], None)
        self.assertTrue(cases)
        self.assertEqual({c["skill"] for c in cases}, {"deck-authoring"})

    def test_filter_by_ids(self):
        cases = self.tool.select_cases(str(ROOT), ["deck-authoring"], {6, 8})
        self.assertEqual(sorted(c["id"] for c in cases), [6, 8])

    def test_unknown_skill_is_rejected(self):
        with self.assertRaises(SystemExit):
            self.tool.select_cases(str(ROOT), ["no-such-skill"], None)


class SummarizeTests(unittest.TestCase):
    def setUp(self):
        self.tool = _load_tool()

    def case(self, expect: bool) -> dict:
        return {"skill": "deck-authoring", "id": 1, "query": "q", "expect": expect}

    def rows(self, hits: int, runs: int = 3) -> list[dict]:
        out = []
        for index in range(runs):
            loaded = ["deck-authoring"] if index < hits else []
            out.append({"skill": "deck-authoring", "id": 1, "loaded": loaded})
        return out

    def test_positive_passes_above_half(self):
        report = self.tool.summarize([self.case(True)], self.rows(2), 0.5)
        self.assertTrue(report[0]["passed"])
        self.assertEqual(report[0]["hits"], 2)

    def test_negative_passes_below_half(self):
        report = self.tool.summarize([self.case(False)], self.rows(1), 0.5)
        self.assertTrue(report[0]["passed"])

    def test_boundary_half_fails_both_sides(self):
        # 1/2 正好等于阈值：正例不算稳定触发，反例也不算稳定不触发
        report = self.tool.summarize([self.case(True), self.case(False)],
                                     self.rows(1, runs=2), 0.5)
        self.assertFalse(report[0]["passed"])
        self.assertFalse(report[1]["passed"])


class ListModeTests(unittest.TestCase):
    def setUp(self):
        self.tool = _load_tool()

    def test_list_reports_planned_sessions(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = self.tool.main(["--list", "--skill", "deck-authoring", "--reps", "2"])
        self.assertEqual(code, 0)
        self.assertIn("× 2 次", buffer.getvalue())

    def test_bad_ids_is_rejected(self):
        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            self.tool.main(["--ids", "1,x"])


if __name__ == "__main__":
    unittest.main()
