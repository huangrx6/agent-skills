#!/usr/bin/env python3
"""SKILL.md 的版式表必须与 render.py 的实际行为一致。

## 为什么这条要写成测试

我第一版 SKILL.md 的版式表把 `chart` 的「装饰墨块」写成 ✗，而 render.py 里
`chart` 是**在**加墨块的那一组的：

    if kind in ("title", "content-text", "end", "chart"):
        out.append(halftone(tokens, seed, i))

七行里错一行，肉眼扫过去发现不了 —— 而模型读 SKILL.md 得到的是错的版式语义
（会以为图表页不该有页角墨块）。表格是**给模型看的规格**，它写错就是规格错。

所以这里把「装饰墨块」那一列**钉在实测行为上**：逐版式渲染一页，看产物里
到底有没有 `data-zone=`。文档与代码任何一边漂了，这条就红。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/deck-authoring/test_skill_md_consistency.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
SCRIPTS = os.path.join(SKILL, "scripts")
TOKENS = os.path.join(SKILL, "styles", "swiss-grid", "style.json")
SKILL_MD = os.path.join(SKILL, "SKILL.md")

# 「| `type` | 用途 | 风险点 |」——只取版式名与用途两列；装饰那一列删了，
# 因为“放不放装饰”现在是**风格**决定的（token 的 decor.types），不是版式决定的，
# 拿一张写死的表去对只会对出一个错的前提。守契约的用例改成了
# test_decoration_contract_is_honored（有装饰的风格只在它声明的那几种版式上放）。
TABLE_ROW = re.compile(r"^\|\s*`([a-z][a-z-]*)`\s*\|([^|]*)\|[^|]*\|\s*$", re.M)

# 每个版式一页的最小 spec —— 只为把那一页渲出来看有没有墨块
PROBE_SLIDES = {
    "title": {"type": "title", "title": "T", "subtitle": "s"},
    "content-text": {"type": "content-text", "title": "C", "bullets": ["a"]},
    "content-image": {"type": "content-image", "title": "I", "bullets": ["a"], "image": "x.png"},
    "two-column": {"type": "two-column", "title": "W",
                   "columns": [{"title": "A", "bullets": ["a"]}, {"title": "B", "bullets": ["b"]}]},
    "timeline": {"type": "timeline", "title": "L", "nodes": [{"label": "Q1", "note": "n"}]},
    "chart": {"type": "chart", "title": "G", "data": [{"label": "A", "value": 10}], "unit": "%"},
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


class TestSkillMdMatchesRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with open(SKILL_MD, encoding="utf-8") as fh:
            cls.skill_md = fh.read()
        cls.style = render.load_style()
        cls.tokens = cls.style["tokens"]
        # 色板名从风格里取（不写死）：写死过 "vivid"，默认风格一换就变成
        # “用例还是绿的，但测的不是它要测的东西”。
        cls.color_set = next(iter(cls.tokens["colorSets"]))

    def _documented_types(self) -> set[str]:
        found = {m.group(1) for m in TABLE_ROW.finditer(self.skill_md)}
        self.assertTrue(found, "SKILL.md 里没解析到版式表 —— 表头或格式变了")
        return found

    def _render_each(self, kinds: list[str], style: dict | None = None) -> dict[str, str]:
        chosen = style if style is not None else render.load_style()
        # 色板名每种风格各自一套，从**这份风格**里取（不能拿别人的 colorSet 去渲）
        deck = {"colorSet": next(iter(chosen["tokens"]["colorSets"])), "seed": 7,
                "title": "探针", "slides": [PROBE_SLIDES[k] for k in kinds]}
        html = render.render({"deck": deck}, chosen)
        sections = SECTION.findall(html)
        self.assertEqual(len(sections), len(kinds),
                         f"渲染出的页数 {len(sections)} ≠ 版式数 {len(kinds)}")
        return {k: ("✓" if "data-zone=" in s else "✗") for k, s in zip(kinds, sections)}

    def test_decoration_contract_is_honored(self) -> None:
        """装饰只在**风格自己声明的那几种版式**上出现。

        为什么不用“版式 ↔ ✓/✗”那张写死的表：那等于把“放不放装饰”当成版式的属性。
        它其实是**风格**的属性（`decor.types`），所以表一变就得同步改，
        而同步一漏就是文档与产物不一致。改测契约之后，这条对每种风格都成立：

          - 风格声明了装饰 → data-zone 恰好落在 decor.types 列的那些版式上
          - 风格没声明（kind=null）→ 一页都不该有 data-zone
        """
        kinds = list(PROBE_SLIDES)
        for name in ("billboard", "swiss-grid", "keynote-dark", "notebook"):
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

    def test_unknown_slide_type_is_rejected(self) -> None:
        """版式集是封闭的 —— 未知 type 必须被拒，而不是静默渲成空白页。

        ⚠️ colorSet 要用**当前默认风格里真实存在**的名字：以前写死 "vivid"，
        默认风格一换它就开始因为 colorSet 而报错 —— 用例还是绿的，
        但测的已经不是“版式被拒”了。
        """
        bad = {"deck": {"colorSet": self.color_set, "seed": 1, "title": "x",
                        "slides": [{"type": "not-a-real-type", "title": "x"}]}}
        with self.assertRaises(SystemExit) as caught:
            render.render(bad)
        self.assertIn("版式", str(caught.exception),
                      f"报的错与版式无关 —— 用例没测到目标：{caught.exception}")


if __name__ == "__main__":
    unittest.main()
