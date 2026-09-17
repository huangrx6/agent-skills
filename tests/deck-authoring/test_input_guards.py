#!/usr/bin/env python3
"""启 Chrome 的脚本必须先看输入在不在 —— 否则会把 Chrome 的**错误页**当成产物。

实测事故（本文件就是它留下的门）：`shots.py` 对一个**不存在**的 HTML 起了 Chrome，
Chrome 截了自己的错误页（3200×1800、底色 `(32,33,36)`），脚本把它切成
`page-01.png…page-06.png` 并报「✓ 截出 6 页」；紧接着
`pptx_native.py --png-dir pages/` 把六张错误页贴成一份**"成功"**的 PPTX。
整条链每一步都报成功，坏只坏在最后有人打开看。

三条不变量：

1. 输入不存在 → **干净报错**（`SystemExit`，文案里带那个路径），不启浏览器；
2. **一个产物都不写** —— 不能留下半份假产物让人以为跑过了（"先跑一遍看看"正是
   会踩的用法）；
3. 三个启 Chrome 的脚本口径一致（`shots` / `animate` / `pdf`）——
   修一处漏两处，剩下的就是下次事故的入口。

跑法：
    python3 -m unittest discover -s tests
    python3 tests/deck-authoring/test_input_guards.py
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
SCRIPTS = os.path.join(SKILL, "scripts")

# 三个脚本的报错都从这句话起头（读不到就该说读不到，别描述 Chrome 怎么了）
PREFIX = "读不到产物"


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestMissingInputIsRefused(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="deck-guard-")
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self.missing = os.path.join(self.root, "nope.html")   # 故意不建

    def _assert_refused(self, exc: SystemExit) -> None:
        text = str(exc)
        self.assertIn(PREFIX, text)
        self.assertIn(self.missing, text)

    def test_shots_writes_nothing_for_missing_input(self):
        shots = _load("_guard_shots", os.path.join(SCRIPTS, "shots.py"))
        out_dir = os.path.join(self.root, "pages")
        with self.assertRaises(SystemExit) as ctx:
            shots.shoot(self.missing, out_dir, 1600, 900, 6)
        self._assert_refused(ctx.exception)
        # 关键：不留下任何"看起来截过了"的东西（包括 _full.png）
        written = sorted(os.listdir(out_dir)) if os.path.isdir(out_dir) else []
        self.assertEqual(written, [], f"不该写出任何文件，实际有 {written}")

    def test_animate_refuses_missing_input(self):
        animate = _load("_guard_animate", os.path.join(SCRIPTS, "animate.py"))
        out = os.path.join(self.root, "deck.mp4")
        with self.assertRaises(SystemExit) as ctx:
            animate.main(["_", self.missing, "-o", out])
        self._assert_refused(ctx.exception)
        self.assertFalse(os.path.exists(out), "不该产出视频文件")

    def test_pdf_refuses_missing_input(self):
        pdf = _load("_guard_pdf", os.path.join(SCRIPTS, "pdf.py"))
        out = os.path.join(self.root, "deck.pdf")
        with self.assertRaises(SystemExit) as ctx:
            pdf.export(self.missing, out)
        self._assert_refused(ctx.exception)
        self.assertFalse(os.path.exists(out), "不该产出 PDF")

    def test_all_three_use_the_same_wording(self):
        """口径一致：不然修好两个，第三个还是洞。"""
        messages = {}
        for name, call in (
                ("shots", lambda m: _load("_g1", os.path.join(SCRIPTS, "shots.py"))
                 .shoot(m, os.path.join(self.root, "p1"), 1600, 900, 1)),
                ("animate", lambda m: _load("_g2", os.path.join(SCRIPTS, "animate.py"))
                 .main(["_", m, "-o", os.path.join(self.root, "o1.mp4")])),
                ("pdf", lambda m: _load("_g3", os.path.join(SCRIPTS, "pdf.py"))
                 .export(m, os.path.join(self.root, "o1.pdf")))):
            with self.assertRaises(SystemExit) as ctx:
                call(os.path.join(self.root, f"nope-{name}.html"))
            messages[name] = str(ctx.exception)
        for name, text in messages.items():
            self.assertIn(PREFIX, text, f"{name} 的报错口径与其它两个不一致：{text!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
