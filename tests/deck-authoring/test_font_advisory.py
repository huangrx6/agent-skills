#!/usr/bin/env python3
"""字体回退**提示**的验证 —— 提示的价值在于可操作，不在于报了。

## 为什么这条提示要单独测

它对交付**不阻塞**（启发式，可能误报），所以它唯一的用处就是让人看一眼然后做个决定。
一旦它开始说废话，人就会学会忽略它 —— 那时候它和不存在是一样的，而且更糟：
它还会掩盖真话。实测踩过一次：

    字体回退（启发式提示）：声明的 'PingFang SC' 在本机不可用

而**页面上根本没写过 `PingFang SC`** —— 那是 Chrome 给 CJK 的 UA 默认值，报的是
`<figure class="imgwrap">`（一个不渲染任何字形的元素）。后来探针只统计**真有文字**
的元素，这条噪音就没了。

所以这里钉两件事：**别报废话**、**报就要说清谁顶上了**。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/deck-authoring/test_font_advisory.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
# 测试自有夹具（v4）：风格与内容样本都放在 tests/ 下，**不随 skill 发布** ——
# 可拷贝的模板必然变成默认答案（用户实测：每份 deck 长得一样）。
FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
# 夹具当"额外风格根"：v4 起工具链不内置任何风格（可拷贝的模板必然变成
# 默认答案）。脚本各持一份模块副本，所以走环境变量而不是改常量。
os.environ.setdefault("DECK_STYLES",
                      os.path.join(FIXTURES_DIR, "styles"))
SCRIPTS = os.path.join(SKILL, "scripts")
TOKENS = os.path.join(FIXTURES_DIR, "styles", "swiss-grid", "style.json")
DEMO = os.path.join(FIXTURES_DIR, "demo.spec.json")


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestFontAdvisory(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.check = _load("deck_check_font", os.path.join(SCRIPTS, "check.py"))
        cls.render = _load("deck_render_font", os.path.join(SCRIPTS, "render.py"))
        with open(TOKENS, encoding="utf-8") as fh:
            cls.tokens = json.load(fh)
        with open(DEMO, encoding="utf-8") as fh:
            cls.spec = json.load(fh)

        cls._tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._tmp.cleanup)
        cls.html = os.path.join(cls._tmp.name, "out.html")
        html = cls.render.render(cls.spec)
        with open(cls.html, "w", encoding="utf-8") as fh:
            fh.write(html)
        cls.measured = cls.check.measure_mod.measure(cls.html)
        cls.notes = cls.check.advisories(cls.measured)

    def test_only_real_stacks_are_reported(self) -> None:
        """报的族必须是页面上**真写过**的（不再报 UA 默认字体）。"""
        declared = set()
        for stack in self.measured.get("stacks", []):
            declared |= set(stack)
        for note in self.notes:
            quoted = set(re.findall(r"'([^']+)'", note))
            for fam in quoted:
                self.assertIn(fam, declared,
                              f"提示里提到 {fam!r}，但它不在页面声明的任何字体栈里 —— "
                              f"这是在报 UA 默认字体（实测踩过的假话）")

    def test_no_text_means_no_font_opinion(self) -> None:
        """没有文字的元素不该对字体有意见。

        `<figure class="imgwrap">`（图文页的图容器）一个字形都不渲染，
        它的 font-family 是 Chrome 给 CJK 的 UA 默认值 —— 拿它报字体回退是纯噪音。
        """
        self.assertNotIn("PingFang SC", " ".join(self.notes),
                         "又报 UA 默认字体了 —— 探针大概又开始统计无文字的元素了")

    def test_advisory_names_the_winner(self) -> None:
        """报回退时必须说清**谁顶上了** —— 只说"某族不可用"不够可操作。"""
        for note in self.notes:
            self.assertIn("实际用的是", note,
                          f"这条提示没说清谁顶上了（不够可操作）：{note}")
            winner = re.search(r"实际用的是 '([^']+)'", note)
            assert winner is not None
            self.assertTrue(self.measured["fonts"].get(winner.group(1), {}).get("available"),
                            f"说顶上的是 {winner.group(1)!r}，但它本身也不可用：{note}")

    def test_no_advisory_when_first_choice_works(self) -> None:
        """首选家族**能用**的栈不该产生提示（否则提示就泛滥了）。"""
        for stack in self.measured.get("stacks", []):
            first = stack[0]
            if self.measured["fonts"].get(first, {}).get("available"):
                offenders = [n for n in self.notes if f"'{first}'" in n]
                self.assertEqual(offenders, [],
                                 f"{first!r} 首选可用，却报了它回退：{offenders}")

    def test_generic_families_are_never_called_missing(self) -> None:
        """`serif` / `monospace` 是**回退目标**不是字体，不能被报成"不可用"。"""
        for note in self.notes:
            for generic in ("'serif'", "'monospace'", "'sans-serif'"):
                self.assertNotIn(generic, note,
                                 f"把通用族当缺失字体报了：{note}")

    def test_advisory_does_not_block(self) -> None:
        """字体回退是**提示**，不能进 problems（进了就会把人逼到忽略整个校验）。"""
        problems = self.check.check(self.spec, self.html, self.tokens,
                                    measured=self.measured)
        for note in self.notes:
            self.assertNotIn(note, problems, "字体提示漏进了阻塞的 problems")


if __name__ == "__main__":
    unittest.main()
