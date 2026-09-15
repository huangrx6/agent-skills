#!/usr/bin/env python3
"""check.py 六项机械校验的**变异验证** —— 每项都要造违规样例。

## 为什么校验器自己也要被"变异测试"

一个只会说 ✓ 的校验器和没有校验器**在结果上完全一样**，但会让人以为有人守着。
所以六项里每一项都做两件事：

1. 干净产物 → 该项不报
2. **针对该项**做一次变异 → 该项必须报

变异规则：**必须替换产物里真实存在的值**（不是凭空加新值）。凭空加的在真实产物里
根本不会出现，那种"变异"证明了校验器什么都没守住。

| 校验项 | 变异对象 | 被替换的真实值 |
| --- | --- | --- |
| ① 对比度 | token 色板 | 叠印墨（产物里 `--ink-text` 的真实来源） |
| ② 文字溢出 | spec 条目 | 某条 bullet 的文本 |
| ③ 错位区间 | 产物 HTML | 真实的 `--dx:Npx` 字符串 |
| ④ 装饰不压文字 | 产物 HTML | 真实的 `data-zone="tr|br"` |
| ④ 柱高成比例 | 产物 HTML | 真实的柱条 `height="N"` |
| ④ 图表区无错位 | 产物 HTML | 真实的 `<div class="chartwrap">` 容器 |

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/deck-authoring/test_check_mutations.py
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
SCRIPTS = os.path.join(SKILL, "scripts")
TOKENS = os.path.join(SKILL, "styles", "risograph", "style.json")
DEMO = os.path.join(SKILL, "dev-tools", "demo.spec.json")

CHART_SLIDE = {
    "type": "chart", "title": "占比",
    "data": [{"label": "A", "value": 10}, {"label": "B", "value": 20},
             {"label": "C", "value": 30}, {"label": "D", "value": 40}],
    "unit": "%",
}


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


render = _load("_deck_test_render", os.path.join(SCRIPTS, "render.py"))
check = _load("_deck_test_check", os.path.join(SCRIPTS, "check.py"))


class TestCheckMutations(unittest.TestCase):
    """六项校验，每项都有一条干净基线 + 一条变异。"""

    @classmethod
    def setUpClass(cls) -> None:
        with open(TOKENS, encoding="utf-8") as fh:
            cls.tokens = json.load(fh)
        with open(DEMO, encoding="utf-8") as fh:
            cls.demo = json.load(fh)
        cls.chart_spec = copy.deepcopy(cls.demo)
        cls.chart_spec["deck"]["slides"].append(copy.deepcopy(CHART_SLIDE))
        cls.demo_html = render.render(cls.demo, cls.tokens)
        cls.chart_html = render.render(cls.chart_spec, cls.tokens)

    def _problems(self, spec: dict, html_text: str, tokens: dict | None = None) -> list[str]:
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False,
                                         encoding="utf-8") as fh:
            path = fh.name
            fh.write(html_text)
        try:
            return check.check(spec, path, tokens or self.tokens)
        finally:
            os.unlink(path)

    def _assert_reports(self, problems: list[str], needle: str, what: str) -> None:
        self.assertTrue(problems, f"{what}：变异后本应报错却全过")
        self.assertTrue(any(needle in p for p in problems),
                        f"{what}：报的不是目标项（找 {needle!r}），实际：{problems}")

    # ── baseline ──────────────────────────────────────────────────────────

    def test_baseline_demo_and_chart_are_clean(self) -> None:
        """改动之前先证明基线干净 —— 否则后面的"变异被抓到"说明不了什么。"""
        self.assertEqual(self._problems(self.demo, self.demo_html), [],
                         "demo 基线本应干干净净")
        self.assertEqual(self._problems(self.chart_spec, self.chart_html), [],
                         "带 chart 的基线本应干干净净")

    # ── ① 对比度 ──────────────────────────────────────────────────────────

    def test_contrast_mutation_is_caught(self) -> None:
        """变异：把 vivid 换成两墨都亮的坏色板（朱红 × 土黄）。"""
        bad = copy.deepcopy(self.tokens)
        bad["colorSets"]["vivid"] = {
            "primary": "#FF6B35", "secondary": "#FFCC00", "background": "#FAF3E7"}
        problems = self._problems(self.demo, render.render(self.demo, bad), bad)
        self._assert_reports(problems, "对比度", "① 对比度")

    # ── ② 文字溢出 ────────────────────────────────────────────────────────

    def test_overflow_mutation_is_caught(self) -> None:
        """变异：把 content-image 页的第一条条目拉成 500 个字。"""
        bad = copy.deepcopy(self.demo)
        for slide in bad["deck"]["slides"]:
            if slide.get("type") == "content-image" and slide.get("bullets"):
                slide["bullets"][0] = "长" * 500
                break
        else:
            self.fail("demo 里没有 content-image 页 —— 这条用例的前提变了")
        problems = self._problems(bad, render.render(bad, self.tokens))
        self._assert_reports(problems, "文字溢出", "② 文字溢出")

    # ── ③ 错位区间 ────────────────────────────────────────────────────────

    def test_misregistration_mutation_is_caught(self) -> None:
        """变异：把产物里真实的 --dx 值改成 100px（远超 token 区间 [1,3]）。"""
        mutated, count = re.subn(r"--dx:([\d.\-]+)px;--dy:([\d.\-]+)px;--rot:([\d.\-]+)deg",
                                 r"--dx:100px;--dy:\2px;--rot:\3deg", self.demo_html, count=1)
        self.assertEqual(count, 1, "产物里没找到 --dx 字符串 —— render.py 改格式了")
        problems = self._problems(self.demo, mutated)
        self._assert_reports(problems, "错位参数", "③ 错位区间")

    # ── ④ 装饰不压文字 ────────────────────────────────────────────────────

    def test_decoration_zone_mutation_is_caught(self) -> None:
        """变异：把产物里真实的 data-zone 改成一个未知 zone。"""
        found = re.search(r'data-zone="(tr|br)"', self.demo_html)
        if found is None:
            self.fail("产物里没有 data-zone=tr|br —— render.py 改格式了")
        original = found.group(1)
        mutated, count = re.subn(rf'data-zone="{original}"', 'data-zone="center"',
                                 self.demo_html, count=1)
        self.assertEqual(count, 1)
        problems = self._problems(self.demo, mutated)
        self._assert_reports(problems, "未知装饰 zone", "④ 装饰不压文字")

    # ── ④ 柱高成比例 ──────────────────────────────────────────────────────

    def test_chart_proportion_mutation_is_caught(self) -> None:
        """变异：把第二种柱子的真实 height 改成 999。"""
        bars = list(re.finditer(r'(class="bar"[^>]*height=")([\d.]+)("[^>]*/?>)',
                                self.chart_html))
        self.assertGreaterEqual(len(bars), 2, "产物里柱条不足两根 —— render.py 改格式了")
        match = bars[1]
        mutated = (self.chart_html[:match.start()] + match.group(1) + "999"
                   + match.group(3) + self.chart_html[match.end():])
        problems = self._problems(self.chart_spec, mutated)
        self._assert_reports(problems, "不成比例", "④ 柱高成比例")

    # ── ④ 图表区无错位 ────────────────────────────────────────────────────

    def test_chart_riso_mutation_is_caught(self) -> None:
        """变异：往真实的 chartwrap 容器里塞一个 riso 元素。"""
        mutated, count = re.subn(
            r'(<div class="chartwrap"[^>]*>)',
            r'\1<div class="riso"><b class="a">X</b></div>', self.chart_html, count=1)
        self.assertEqual(count, 1, "产物里没找到 chartwrap —— render.py 改格式了")
        problems = self._problems(self.chart_spec, mutated)
        self._assert_reports(problems, "错位叠印", "④ 图表区无错位")


if __name__ == "__main__":
    unittest.main()
