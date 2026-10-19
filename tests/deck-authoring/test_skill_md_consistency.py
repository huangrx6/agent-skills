#!/usr/bin/env python3
"""Validate renderer capabilities against the contract reachable from SKILL.md.

The entry links to the spec reference, which links to layout and chart details.
Keep that progressive disclosure while checking exact supported vocabularies.
Rendering probes separately verify decoration behavior, not a fixed aesthetic.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
# 测试自有夹具：风格与内容样本都放在 tests/ 下，**不随 skill 发布** ——
# 可拷贝的模板必然变成默认答案（每份 deck 长得一样）。
FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
# 夹具当"额外风格根"：工具链不内置任何风格（可拷贝的模板必然变成
# 默认答案）。脚本各持一份模块副本，所以走环境变量而不是改常量。
os.environ.setdefault("DECK_STYLES",
                      os.path.join(FIXTURES_DIR, "styles"))
os.environ.setdefault("DECK_BRANDS",
                      os.path.join(FIXTURES_DIR, "brands"))

# 夹具第一套风格（tests/fixtures/styles 下；风格不再有内置解析根）
FIXTURE_STYLE = os.path.join(FIXTURES_DIR, "styles", "swiss-grid")
SCRIPTS = os.path.join(SKILL, "scripts")
TOKENS = os.path.join(FIXTURES_DIR, "styles", "swiss-grid", "style.json")
STYLES = os.path.join(FIXTURES_DIR, "styles")
SKILL_MD = os.path.join(SKILL, "SKILL.md")

# Spec field table: type and supported fields. Decoration is tested separately.
TABLE_ROW = re.compile(r"^\|\s*`([a-z][a-z-]*)`\s*\|([^|]*)\|\s*$", re.M)

# Layout table: accumulate all documented layouts across rows of each type.
LAYOUT_ROW = re.compile(
    r"^\|\s*(content-image|two-column)\s*\|\s*([^|]*)\|[^|]*\|\s*$", re.M)
BACKTICKED = re.compile(r"`([a-z][a-z0-9-]*)`")

# 每个版式一页的最小 spec —— 只为把那一页渲出来看有没有墨块
PROBE_SLIDES = {
    "title": {"type": "title", "title": "T", "subtitle": "s"},
    "content-text": {"type": "content-text", "title": "C", "bullets": ["a"]},
    "content-image": {"type": "content-image", "title": "I", "bullets": ["a"], "image": "x.png"},
    "two-column": {"type": "two-column", "title": "W",
                   "columns": [{"title": "A", "bullets": ["a"]}, {"title": "B", "bullets": ["b"]}]},
    "timeline": {"type": "timeline", "title": "L", "nodes": [{"label": "Q1", "note": "n"}]},
    "chart": {"type": "chart", "title": "G", "chart": "bar",
              "data": [{"label": "A", "value": 10}], "unit": "%"},
    "end": {"type": "end", "title": "E"},
}


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


render = _load("_deck_test_render_md", os.path.join(SCRIPTS, "render.py"))
# 页现在带着 data-slide / 错位变量（`--dx` 等上移到了 section）—— 匹配要允许属性。
SECTION = re.compile(r'<section class="slide"[^>]*>(.*?)</section>', re.S)



def _style_names() -> list[str]:
    """所有风格 —— **读目录，不写死名单**。

    写死的名单会让新加的风格**整批逃过**运动 / 装饰 / 版式表这些检查，
    而测试仍然是绿的。目录才是唯一事实来源。
    """
    return sorted(d for d in os.listdir(STYLES) if os.path.isdir(os.path.join(STYLES, d)))


class TestSkillMdMatchesRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with open(SKILL_MD, encoding="utf-8") as fh:
            cls.skill_md = fh.read()
        # Progressive disclosure: validate the linked contract, not a duplicate
        # capability table forced into the design workflow's entry document.
        def linked(parent, text, target):
            paths = re.findall(r"\]\(([^)#]+)(?:#[^)]*)?\)", text)
            if target not in paths:
                raise AssertionError(f"{parent} does not link to {target}")
            path = os.path.join(os.path.dirname(parent), target)
            with open(path, encoding="utf-8") as document:
                return path, document.read()

        spec_path, cls.spec_md = linked(SKILL_MD, cls.skill_md, "references/style-architecture.md")
        _, cls.layouts_md = linked(spec_path, cls.spec_md, "layout-system.md")
        _, cls.charts_md = linked(spec_path, cls.spec_md, "charts.md")
        cls.style = render.load_style(FIXTURE_STYLE)
        cls.tokens = cls.style["tokens"]
        # 色板名从风格里取（不写死）：写死过 "vivid"，默认风格一换就变成
        # “用例还是绿的，但测的不是它要测的东西”。
        cls.color_set = next(iter(cls.tokens["colorSets"]))

    def _documented_types(self) -> set[str]:
        table = self.spec_md.split("| type | 该页额外字段 |", 1)[1].split("\n\n", 1)[0]
        found = {m.group(1) for m in TABLE_ROW.finditer(table)}
        self.assertTrue(found, "规格文档里没解析到 type 字段表")
        return found

    def _render_each(self, kinds: list[str], style: dict | None = None) -> dict[str, str]:
        chosen = style if style is not None else render.load_style(FIXTURE_STYLE)
        # 色板名每种风格各自一套，从**这份风格**里取（不能拿别人的 colorSet 去渲）
        deck = {"colorSet": next(iter(chosen["tokens"]["colorSets"])), "seed": 7,
                "title": "探针", "slides": [PROBE_SLIDES[k] for k in kinds]}
        html = render.render({"deck": deck}, chosen)
        sections = SECTION.findall(html)
        self.assertEqual(len(sections), len(kinds),
                         f"渲染出的页数 {len(sections)} ≠ 版式数 {len(kinds)}")
        # 上面刚断言过两串等长 —— strict 只是把这个前提写死
        return {k: ("✓" if "data-zone=" in s else "✗")
                for k, s in zip(kinds, sections, strict=True)}

    def test_decoration_contract_is_honored(self) -> None:
        """装饰只在**风格自己声明的那几种版式**上出现。

        为什么不用“版式 ↔ ✓/✗”那张写死的表：那等于把“放不放装饰”当成版式的属性。
        它其实是**风格**的属性（`decor.types`），所以表一变就得同步改，
        而同步一漏就是文档与产物不一致。改测契约之后，这条对每种风格都成立：

          - 风格声明了装饰 → data-zone 恰好落在 decor.types 列的那些版式上
          - 风格没声明（kind=null）→ 一页都不该有 data-zone
        """
        kinds = list(PROBE_SLIDES)
        for name in _style_names():
            with self.subTest(style=name):
                style = render.load_style(name)
                spec = style["tokens"].get("decor") or {}
                declared = set(spec.get("types") or []) if spec.get("kind") else set()
                actual = self._render_each(kinds, style)
                got = {k for k, mark in actual.items() if mark == "✓"}
                self.assertEqual(
                    got, declared,
                    f"{name} 的装饰落点与它声明的 decor.types 不一致："
                    f"声明 {sorted(declared)}，实际 {sorted(got)}")

    def test_documented_types_cover_all_probes(self) -> None:
        """文档列出的版式必须覆盖探针里的每一种 —— 少写一种就说明文档缺行。"""
        documented = self._documented_types()
        self.assertEqual(
            documented, set(PROBE_SLIDES),
            f"文档版式集与实现集不同：只在文档 {documented - set(PROBE_SLIDES)}；"
            f"只在实现 {set(PROBE_SLIDES) - documented}")

    def test_documented_layouts_match_the_renderer(self) -> None:
        """Linked layout documentation equals the renderer's structure vocabulary.

        为什么必须钉：这份表是给模型看的**规格**，而布局名就是它要写进 spec 的值。
        实测漏过 —— 表里写了 4 个 content-image 结构、3 个 two-column 结构，
        而 `render.IMAGE_LAYOUTS` / `TWO_COL_LAYOUTS` 各有 5 个：
        `visual-wide`、`lean-hard-left/right` 在候选搜索里天在用，却从没进过文档。
        少一个名字不等于“少个选项”：模型不知道它存在。
        """
        rows = {}
        for match in LAYOUT_ROW.finditer(self.layouts_md):
            rows.setdefault(match.group(1), []).extend(BACKTICKED.findall(match.group(2)))
        self.assertTrue(rows, "布局文档里没解析到布局列")
        for page_type, allowed in (("content-image", render.IMAGE_LAYOUTS),
                                   ("two-column", render.TWO_COL_LAYOUTS)):
            with self.subTest(page_type=page_type):
                documented = set(rows.get(page_type, []))
                self.assertEqual(
                    documented, set(allowed),
                    f"{page_type} 的布局列与渲染器漂了："
                    f"只在文档 {sorted(documented - set(allowed))}；"
                    f"只在实现 {sorted(set(allowed) - documented)}")

    def test_documented_chart_types_cover_the_renderer(self) -> None:
        """Linked chart contract must enumerate actual supported chart types.

        这一列是散文（不拆表），所以钉"全都出现过"——它拦的是"加了类型却
        忘了写文档"，而那正是会让模型永远不用它的错。
        """
        table = self.charts_md.split("| chart | 数据 | HTML | 原生 PPTX |", 1)[1].split("\n\n", 1)[0]
        documented = set(re.findall(r"^\| ([a-z][a-z-]*) \|", table, re.M))
        self.assertEqual(documented, set(render.CHART_TYPES))

    def test_unknown_slide_type_is_rejected(self) -> None:
        """版式集是封闭的 —— 未知 type 必须被拒，而不是静默渲成空白页。

        ⚠️ colorSet 要用**当前默认风格里真实存在**的名字：写死一个色板名，
        默认风格一换它就开始因为 colorSet 而报错 —— 用例还是绿的，
        但测的已经不是“版式被拒”了。
        """
        # deck.style 必填 —— 这份合成 spec 也要写上，否则报的会是"缺风格"
        bad = {"deck": {"style": "swiss-grid", "colorSet": self.color_set, "seed": 1,
                        "title": "x",
                        "slides": [{"type": "not-a-real-type", "title": "x"}]}}
        with self.assertRaises(SystemExit) as caught:
            render.render(bad)
        self.assertIn("版式", str(caught.exception),
                      f"报的错与版式无关 —— 用例没测到目标：{caught.exception}")


if __name__ == "__main__":
    unittest.main()
