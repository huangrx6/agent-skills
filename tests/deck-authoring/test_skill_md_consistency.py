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
TOKENS = os.path.join(SKILL, "styles", "risograph", "style.json")
SKILL_MD = os.path.join(SKILL, "SKILL.md")

# 「| `type` | 用途 | 装饰墨块 | 风险点 |」
TABLE_ROW = re.compile(r"^\|\s*`([a-z][a-z-]*)`\s*\|[^|]*\|\s*([✓✗])\s*\|[^|]*\|\s*$", re.M)

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
        with open(TOKENS, encoding="utf-8") as fh:
            cls.tokens = json.load(fh)

    def _documented_decoration(self) -> dict[str, str]:
        found = dict(TABLE_ROW.findall(self.skill_md))
        self.assertTrue(found, "SKILL.md 里没解析到版式表 —— 表头或格式变了")
        return found

    def _render_each(self, kinds: list[str]) -> dict[str, str]:
        deck = {"colorSet": "vivid", "seed": 7, "title": "探针",
                "slides": [PROBE_SLIDES[k] for k in kinds]}
        html = render.render({"deck": deck})
        sections = SECTION.findall(html)
        self.assertEqual(len(sections), len(kinds),
                         f"渲染出的页数 {len(sections)} ≠ 版式数 {len(kinds)}")
        return {k: ("✓" if "data-zone=" in s else "✗") for k, s in zip(kinds, sections)}

    def test_decoration_column_matches_actual_render(self) -> None:
        """「装饰墨块」那一列必须与产物里有没有 data-zone 完全一致。"""
        documented = self._documented_decoration()
        actual = self._render_each(list(documented))
        mismatched = {k: (documented[k], actual[k]) for k in documented
                      if documented[k] != actual[k]}
        self.assertEqual(
            mismatched, {},
            f"SKILL.md 版式表与 render.py 不一致（版式: 文档写的→实测）：{mismatched}")

    def test_documented_types_cover_all_probes(self) -> None:
        """文档列出的版式必须覆盖探针里的每一种 —— 少写一种就说明文档缺行。"""
        documented = set(self._documented_decoration())
        self.assertEqual(
            documented, set(PROBE_SLIDES),
            f"文档版式集与实现集不同：只在文档 {documented - set(PROBE_SLIDES)}；"
            f"只在实现 {set(PROBE_SLIDES) - documented}")

    def test_unknown_slide_type_is_rejected(self) -> None:
        """版式集是封闭的 —— 未知 type 必须被拒，而不是静默渲成空白页。"""
        bad = {"deck": {"colorSet": "vivid", "seed": 1, "title": "x",
                        "slides": [{"type": "not-a-real-type", "title": "x"}]}}
        with self.assertRaises(SystemExit):
            render.render(bad)


if __name__ == "__main__":
    unittest.main()
