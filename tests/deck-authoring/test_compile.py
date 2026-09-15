#!/usr/bin/env python3
"""compile（决策层）的回归测试：spec → resolved → 只画不想。

这层最容易出的错不是崩，是**悄悄变了**：

- 决策搬进 compile 后渲染结果漂移（重构必须逐字节不动物理输出）；
- resolved 不自足（渲染器还得回头读 spec / 加载风格 —— "只画不想"就是空话）；
- trace 说谎（升档写成降档、显式写成派生 —— 决策解释比没有更糟）；
- 决策有随机性（同 spec 同 seed 两次编译不一样）。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/deck-authoring/test_compile.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
SCRIPTS = os.path.join(SKILL, "scripts")
DEMO = os.path.join(SKILL, "dev-tools", "demo.spec.json")


def _load(name: str):
    key = f"_deck_test_{name}"
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, os.path.join(SCRIPTS, f"{name}.py"))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


compile_mod = _load("compile")
render = _load("render")
check_mod = _load("check")


def _demo() -> dict:
    with open(DEMO, encoding="utf-8") as fh:
        return json.load(fh)


class TestCompileSpec(unittest.TestCase):
    """compile_spec：决策层纯函数 + resolved 自足。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = _demo()
        cls.resolved = compile_mod.compile_spec(cls.spec)

    def test_resolved_shape_is_complete(self) -> None:
        """resolved 自足：schema/kind/style/brand/色/ logo/时间轴/决策全在，
        渲染器不需要回头读 spec。"""
        for key in ("schemaVersion", "kind", "style", "brand", "colorSet", "colors",
                    "logoFile", "title", "seed", "deck", "timeline", "trace"):
            self.assertIn(key, self.resolved, f"resolved 缺 {key} —— 渲染器得回头找")
        self.assertIn("slides", self.resolved["deck"], "resolved.deck 里没有 slides")
        self.assertEqual(self.resolved["kind"], "resolved.deck")
        # 内容与决策合并在同一页对象里
        slide = self.resolved["deck"]["slides"][0]
        for key in ("type", "tTier", "tSize", "bTier", "bSize", "dx", "dy", "rot"):
            self.assertIn(key, slide, f"页对象缺决策键 {key}")

    def test_compilation_is_deterministic(self) -> None:
        """同 spec 同 seed：两次编译全等 —— 决策层不许有随机性。"""
        again = compile_mod.compile_spec(json.loads(json.dumps(self.spec)))
        self.assertEqual(self.resolved, again, "两次编译不一样 —— 混进了随机或时钟")

    def test_is_resolved_detection(self) -> None:
        self.assertTrue(compile_mod.is_resolved(self.resolved))
        self.assertFalse(compile_mod.is_resolved(self.spec))
        self.assertFalse(compile_mod.is_resolved({}))

    def test_render_paths_are_byte_identical(self) -> None:
        """**重构不变量**：spec 直渲 == compile→render_resolved == render(resolved)。

        三条路径逐字节相同 = 决策搬迁没有改物理输出（416 条测试的根）。
        """
        direct = render.render(json.loads(json.dumps(self.spec)))
        via_resolved = render.render_resolved(
            compile_mod.compile_spec(json.loads(json.dumps(self.spec))))
        self.assertEqual(direct, via_resolved, "决策搬进 compile 后渲染漂移了")
        self.assertEqual(direct, render.render(self.resolved),
                         "render(resolved) 与 render(spec) 不一致")

    def test_resolved_carries_content_not_just_decisions(self) -> None:
        """内容在 resolved 里（标题/条目），不是只有档位数字。"""
        slides = self.resolved["deck"]["slides"]
        self.assertIn("title", slides[0])
        text_slide = next(s for s in slides if s.get("type") == "content-text")
        self.assertIn("bullets", text_slide)


class TestDecisionTrace(unittest.TestCase):
    """trace（§26 Decision Trace）：系统能解释"为什么这样设计"，且不撒谎。"""

    def test_explicit_color_set_has_explicit_reason(self) -> None:
        resolved = compile_mod.compile_spec(_demo())       # demo 显式 blue
        entry = next(t for t in resolved["trace"]
                     if t["stage"] == "theme" and t["decision"] == "blue")
        self.assertIn("显式指定", "".join(entry["reason"]))

    def test_auto_color_set_trace_explains_derivation(self) -> None:
        spec = _demo()
        spec["deck"]["colorSet"] = "auto"
        resolved = compile_mod.compile_spec(spec)
        entry = next(t for t in resolved["trace"]
                     if t["stage"] == "theme" and t["decision"].startswith("auto:"))
        self.assertTrue(entry["decision"].startswith("auto:"),
                        f"auto 的 trace 决策应是派生名，得到 {entry['decision']}")
        joined = "".join(entry["reason"])
        self.assertIn("seed", joined, "理由里没说按 seed 派生")
        self.assertIn("纸色文字不动", joined, "理由里没说对比度保证")

    def test_down_tier_reason_cites_repair_order(self) -> None:
        """降档（bulletSmall）的理由必须引用修复顺序第 13 位 —— 缩字号不许静默。"""
        spec = _demo()
        spec["deck"]["slides"] = [
            {"type": "content-text", "title": "长页",
             "bullets": [f"条目{i}" for i in range(7)]}]
        resolved = compile_mod.compile_spec(spec)
        entry = next(t for t in resolved["trace"]
                     if t.get("slide") == 1 and t["stage"] == "typography")
        self.assertIn("bulletSmall", entry["decision"])
        self.assertIn("第 13 位", "".join(entry["reason"]),
                      "降档理由没引修复顺序 —— 静默缩字又回来了")

    def test_up_tier_reason_is_positive_not_a_repair_signal(self) -> None:
        """升档（bulletLarge）是好事（内容少字就该大），理由不许写成修复警告。"""
        spec = _demo()
        spec["deck"]["slides"] = [
            {"type": "content-text", "title": "短页", "bullets": ["仅两条", "很疏"]}]
        resolved = compile_mod.compile_spec(spec)
        entry = next(t for t in resolved["trace"]
                     if t.get("slide") == 1 and t["stage"] == "typography")
        self.assertIn("bulletLarge", entry["decision"])
        joined = "".join(entry["reason"])
        self.assertIn("内容少字就该大", joined)
        self.assertNotIn("第 13 位", joined, "升档被写成了降档警告 —— trace 在撒谎")

    def test_explicit_variant_is_traced_and_carried(self) -> None:
        """显式 variant：layout 决策进 trace，页对象带变体（{**slide} 自动合并）。"""
        spec = _demo()
        spec["deck"]["slides"][2]["variant"] = "visual-left"   # 第 3 页 content-image
        resolved = compile_mod.compile_spec(spec)
        entry = next(t for t in resolved["trace"] if t["stage"] == "layout")
        self.assertIn("content-image:visual-left", entry["decision"])
        self.assertEqual(resolved["deck"]["slides"][2].get("variant"), "visual-left")

    def test_default_variant_is_silent(self) -> None:
        """不写 variant：不记 layout trace（默认不值得一行日志，留痕只给偏离）。"""
        resolved = compile_mod.compile_spec(_demo())
        self.assertFalse(any(t["stage"] == "layout" for t in resolved["trace"]))

    def test_brand_merge_is_traced(self) -> None:
        resolved = compile_mod.compile_spec(_demo())       # demo 引 example 品牌
        self.assertTrue(any(t["decision"].startswith("brand:") for t in resolved["trace"]))


class TestTierAdvisoryAtTheGate(unittest.TestCase):
    """check 门禁的降档提示：compile 记 trace 之外的第二声。"""

    def test_dense_text_page_gets_called_out(self) -> None:
        deck = {"slides": [
            {"type": "content-text", "title": "密", "bullets": [f"b{i}" for i in range(7)]}]}
        notes = check_mod._tier_notes(deck)
        self.assertTrue(any("最小字号档" in n for n in notes), notes)

    def test_slim_page_is_silent(self) -> None:
        deck = {"slides": [
            {"type": "content-text", "title": "疏", "bullets": ["a", "b"]}]}
        self.assertEqual(check_mod._tier_notes(deck), [])


if __name__ == "__main__":
    unittest.main()


class TestVariantRendering(unittest.TestCase):
    """三个变体真实几何不同；显式默认 == 隐式默认（字节级契约）。"""

    def _page_html(self, variant: str | None) -> str:
        spec = _demo()
        page = spec["deck"]["slides"][2]              # 第 3 页 content-image
        page.pop("variant", None)
        if variant:
            page["variant"] = variant
        out = render.render(spec)
        # 页码是补零的（data-idx="03"）—— 第 3 页的片段切到第 4 页之前
        return out.split('data-idx="03"')[1].split('data-idx="04"')[0]

    def test_variants_differ_in_geometry_and_order(self) -> None:
        right = self._page_html("visual-right")
        left = self._page_html("visual-left")
        even = self._page_html("even")
        self.assertNotEqual(right, left)
        self.assertNotEqual(right, even)
        self.assertIn('class="two v-left"', left)
        self.assertIn('class="two v-even"', even)
        self.assertIn('class="two">', right, "默认不该带变体类（保持旧字节）")
        # visual-left：figure（图）在 main（文）之前 —— DOM 顺序即阅读顺序
        self.assertLess(left.index("<figure"), left.index('class="main"'))
        self.assertGreater(right.index("<figure"), right.index('class="main"'))

    def test_explicit_default_equals_implicit(self) -> None:
        self.assertEqual(self._page_html(None), self._page_html("visual-right"))
