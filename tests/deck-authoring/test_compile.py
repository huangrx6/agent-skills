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
        self.assertIn("显式声明", "".join(entry["reason"]))

    def test_auto_color_set_is_gone(self) -> None:
        """v3：auto 配色退役 —— 直调 compile 也要人话报错，不静默回退。"""
        spec = _demo()
        spec["deck"]["colorSet"] = "auto"
        with self.assertRaises(SystemExit) as cm:
            compile_mod.compile_spec(spec)
        self.assertIn("colorSet", str(cm.exception))

    def test_missing_color_set_is_gone(self) -> None:
        spec = _demo()
        spec["deck"].pop("colorSet", None)
        with self.assertRaises(SystemExit):
            compile_mod.compile_spec(spec)

    def test_style_bullet_default_applies_without_trace(self) -> None:
        """风格 bulletDefault 决定缺省条目档；缺省值不值得一行 trace。"""
        spec = _demo()
        spec["deck"]["slides"] = [{"type": "content-text", "title": "页",
                                   "bullets": ["a", "b", "c"]}]
        resolved = compile_mod.compile_spec(spec)
        self.assertEqual(resolved["deck"]["slides"][0]["bTier"], "bullet")
        self.assertFalse(any(t["stage"] == "typography" for t in resolved["trace"]))

    def test_two_column_defaults_to_narrow_tier(self) -> None:
        """两栏栏宽固定为窄栏 —— 结构事实（不是按条数缩字）。"""
        spec = _demo()
        spec["deck"]["slides"] = [
            {"type": "two-column", "title": "对照",
             "columns": [{"title": "A", "bullets": ["a"]},
                         {"title": "B", "bullets": ["b"]}]}]
        resolved = compile_mod.compile_spec(spec)
        self.assertEqual(resolved["deck"]["slides"][0]["bTier"], "bulletSmall")

    def test_explicit_layout_is_traced_and_carried(self) -> None:
        """显式 layout：决策进 trace，页对象带布局（{**slide} 自动合并）。"""
        spec = _demo()
        spec["deck"]["slides"][2]["layout"] = "visual-left"   # 第 3 页 content-image
        resolved = compile_mod.compile_spec(spec)
        entry = next(t for t in resolved["trace"] if t["stage"] == "layout")
        self.assertIn("content-image:visual-left", entry["decision"])
        self.assertEqual(resolved["deck"]["slides"][2].get("layout"), "visual-left")

    def test_custom_layout_says_it_is_free_form(self) -> None:
        """自造布局名：trace 说清"缺省结构 + data-layout，排法交给 skin"。"""
        spec = _demo()
        spec["deck"]["slides"][2]["layout"] = "poster-split"
        resolved = compile_mod.compile_spec(spec)
        entry = next(t for t in resolved["trace"] if t["stage"] == "layout")
        self.assertIn("poster-split", entry["decision"])
        self.assertIn("skin", "".join(entry["reason"]))

    def test_default_layout_is_silent(self) -> None:
        """不写 layout：不记 layout trace（默认不值得一行日志，留痕只给偏离）。"""
        resolved = compile_mod.compile_spec(_demo())
        self.assertFalse(any(t["stage"] == "layout" for t in resolved["trace"]))

    def test_declared_tier_is_traced(self) -> None:
        """作者声明档位进 trace；不声明则无声（v3：无自动升降档）。"""
        spec = _demo()
        spec["deck"]["slides"] = [{"type": "content-text", "title": "页",
                                   "bullets": ["a", "b"],
                                   "bulletTier": "bulletSmall"}]
        resolved = compile_mod.compile_spec(spec)
        entry = next(t for t in resolved["trace"] if t["stage"] == "typography")
        self.assertIn("bulletSmall", entry["decision"])
        self.assertEqual(resolved["deck"]["slides"][0]["bTier"], "bulletSmall")

    def test_unknown_tier_name_is_a_clean_error(self) -> None:
        spec = _demo()
        spec["deck"]["slides"][2]["bulletTier"] = "bulletTiny"
        with self.assertRaises(SystemExit) as cm:
            compile_mod.compile_spec(spec)
        self.assertIn("bulletTiny", str(cm.exception))

    def test_brand_merge_is_traced(self) -> None:
        resolved = compile_mod.compile_spec(_demo())       # demo 引 example 品牌
        self.assertTrue(any(t["decision"].startswith("brand:") for t in resolved["trace"]))


class TestTierAdvisoryAtTheGate(unittest.TestCase):
    """check 门禁的档位提示：内容多 + 没声明档位时提醒（v3 无自动降档）。"""

    def test_dense_text_page_gets_called_out(self) -> None:
        deck = {"slides": [
            {"type": "content-text", "title": "密", "bullets": [f"b{i}" for i in range(7)]}]}
        notes = check_mod._tier_notes(deck)
        self.assertTrue(any("未声明 bulletTier" in n for n in notes), notes)

    def test_declaring_a_small_tier_is_silent(self) -> None:
        """已经声明了小档 → 提示闭嘴（作者已经做过决定）。"""
        deck = {"slides": [
            {"type": "content-text", "title": "密", "bulletTier": "bulletSmall",
             "bullets": [f"b{i}" for i in range(7)]}]}
        self.assertEqual(check_mod._tier_notes(deck), [])

    def test_slim_page_is_silent(self) -> None:
        deck = {"slides": [
            {"type": "content-text", "title": "疏", "bullets": ["a", "b"]}]}
        self.assertEqual(check_mod._tier_notes(deck), [])

    def test_same_layout_run_gets_rotation_note(self) -> None:
        """连排同型同布局 → 轮换提示（"每页同构图"是反 slop 第一条）。"""
        deck = {"slides": [
            {"type": "content-image", "title": "a", "image": "x.png"},
            {"type": "content-image", "title": "b", "image": "y.png"},
            {"type": "content-image", "title": "c", "image": "z.png"}]}
        notes = check_mod._layout_rotation_notes(deck)
        self.assertEqual(len(notes), 1)
        self.assertIn("布局", notes[0])
        self.assertIn("第 1~3 页", notes[0])

    def test_rotated_layouts_stay_silent(self) -> None:
        """布局有轮换（缺省/left/hero）→ 不提示；单页也不提示。"""
        rotated = {"slides": [
            {"type": "content-image", "title": "a", "image": "x.png"},
            {"type": "content-image", "title": "b", "image": "y.png",
             "layout": "visual-left"},
            {"type": "content-image", "title": "c", "image": "z.png",
             "layout": "hero"}]}
        self.assertEqual(check_mod._layout_rotation_notes(rotated), [])
        single = {"slides": [{"type": "content-image", "title": "a", "image": "x.png"}]}
        self.assertEqual(check_mod._layout_rotation_notes(single), [])

    def test_layout_free_for_other_types(self) -> None:
        """没有结构布局的版式连排不提示（content-text 无可换结构）。"""
        deck = {"slides": [
            {"type": "content-text", "title": "a", "bullets": ["1"]},
            {"type": "content-text", "title": "b", "bullets": ["2"]}]}
        self.assertEqual(check_mod._layout_rotation_notes(deck), [])

    def test_layout_vocabulary_gate(self) -> None:
        """风格声明 layouts 词表 → spec 里的布局名必须落在表内（拼错当场拦）。"""
        tokens = {"layouts": ["poster-split", "visual-left"]}
        deck = {"slides": [
            {"type": "content-image", "title": "a", "image": "x.png",
             "layout": "poster-splti"},
            {"type": "content-image", "title": "b", "image": "y.png",
             "layout": "poster-split"},
            {"type": "content-image", "title": "c", "image": "z.png",
             "layout": "hero"}]}          # 结构布局永远放行（渲染器能力）
        problems = check_mod._layout_vocab_problems(deck, tokens, deck["slides"])
        self.assertEqual(len(problems), 1)
        self.assertIn("poster-splti", problems[0])


class TestCliRoundTrip(unittest.TestCase):
    """compile CLI 的 -o：退出 0、产物可读、与 compile_spec 全等。

    钉死的回归：写完文件后 print 里取 resolved['slides']（不存在，在
    deck 下）—— 文件成功、退出非零，调用方以为失败。benchmark.py 落盘
    时顺带炸出来的（deckio 也因此补了 write_json）。
    """

    def test_out_file_matches_compile_spec(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "resolved.deck.json")
            code = compile_mod.main(["compile", DEMO, "-o", out])
            self.assertEqual(code, 0, "CLI 写完文件后崩了（打印键错/写法错）")
            with open(out, encoding="utf-8") as fh:
                written = json.load(fh)
            self.assertEqual(written, compile_mod.compile_spec(_demo()))


if __name__ == "__main__":
    unittest.main()


class TestLayoutRendering(unittest.TestCase):
    """结构布局真实几何不同；缺省 == 显式缺省（字节级契约）；
    自造布局名走缺省结构 + data-layout 钩子（skin 的接入点）。"""

    def _page_html(self, layout: str | None) -> str:
        spec = _demo()
        page = spec["deck"]["slides"][2]              # 第 3 页 content-image
        page.pop("layout", None)
        if layout:
            page["layout"] = layout
        out = render.render(spec)
        # 页码是补零的（data-idx="03"）—— 第 3 页的片段切到第 4 页之前
        return out.split('data-idx="03"')[1].split('data-idx="04"')[0]

    def test_layouts_differ_in_geometry_and_order(self) -> None:
        right = self._page_html("visual-right")
        left = self._page_html("visual-left")
        even = self._page_html("even")
        self.assertNotEqual(right, left)
        self.assertNotEqual(right, even)
        self.assertIn('class="two v-left"', left)
        self.assertIn('class="two v-even"', even)
        self.assertIn('class="two">', right, "缺省不该带布局类（保持旧字节）")
        # visual-left：figure（图）在 main（文）之前 —— DOM 顺序即阅读顺序
        self.assertLess(left.index("<figure"), left.index('class="main"'))
        self.assertGreater(right.index("<figure"), right.index('class="main"'))

    def test_explicit_default_equals_implicit(self) -> None:
        self.assertEqual(self._page_html(None), self._page_html("visual-right"))

    def test_custom_layout_gets_default_structure_plus_hook(self) -> None:
        """作者自造布局名：结构照缺省，只多一个 data-layout（skin 靠它重排）。"""
        custom = self._page_html("poster-split")
        plain = self._page_html(None)
        self.assertIn('data-layout="poster-split"', custom)
        self.assertNotIn("data-layout", plain)
        self.assertEqual(custom.replace(' data-layout="poster-split"', ""), plain,
                         "自造布局名不许改变结构 —— 结构是渲染器能力")

    def test_hero_renders_single_title_in_bar(self) -> None:
        """hero：标题只住 herobar，顶部不许再立 titleblock（双标题 = 溢出元凶）。"""
        seg = self._page_html("hero")
        self.assertIn('class="herofig"', seg)
        self.assertIn('class="herobar"', seg)
        self.assertEqual(seg.count('class="titleblock'), 0,
                         "hero 页还有独立标题块 —— 标题会被渲染两次")
        self.assertIn("height:520px", seg)   # demo 第 3 页带 2 条条目 → 520
        # 无条目形态才是 648（占整页 64%，role-aware 放行的那档）；
        # 实心标题条的反转色对 CSS 在壳的 <style> 里，断言要看整份产物
        no_bullets = _demo()
        no_bullets["deck"]["slides"][2].pop("bullets", None)
        no_bullets["deck"]["slides"][2]["layout"] = "hero"
        full = render.render(no_bullets)
        self.assertIn("height:648px", full)
        self.assertIn("background:var(--text)", full)   # --text 底 / --paper 字


class TestTwoColLayoutRendering(unittest.TestCase):
    """two-column 三种结构布局几何分叉；显式 even == 隐式不写（字节级契约）；
    缺省双栏字节不变（上一条黄金测试钉着）。"""

    def _page_html(self, layout: str | None) -> str:
        spec = _demo()
        page = spec["deck"]["slides"][3]              # 第 4 页 two-column
        page.pop("layout", None)
        if layout:
            page["layout"] = layout
        out = render.render(spec)
        return out.split('data-idx="04"')[1].split('data-idx="05"')[0]

    def test_layouts_differ_in_geometry(self) -> None:
        even = self._page_html("even")
        lean_l = self._page_html("lean-left")
        lean_r = self._page_html("lean-right")
        self.assertIn('class="cols v-lean-left"', lean_l)
        self.assertIn('class="cols v-lean-right"', lean_r)
        self.assertIn('class="cols">', even, "缺省不该带布局类（保持旧字节）")
        self.assertNotEqual(lean_l, lean_r, "两个 lean 布局渲成了同一份 DOM")
        self.assertNotEqual(even, lean_l)
        self.assertNotEqual(even, lean_r)

    def test_lean_widths_come_from_the_grid(self) -> None:
        """宽度是栅格算的：span(7)=825.33（另一侧由 flex:1 补齐 582.67=span(5)，
        825.33+582.67+24=1432 不变）；规则在骨架 CSS 里，每个产物只有一份。"""
        out = render.render(_demo())
        self.assertIn(".cols.v-lean-left .col:first-child{flex:none;width:825.33px}", out)
        self.assertIn(".cols.v-lean-right .col:last-child{flex:none;width:825.33px}", out)

    def test_explicit_even_equals_implicit(self) -> None:
        self.assertEqual(self._page_html(None), self._page_html("even"))

    def test_explicit_layout_is_traced(self) -> None:
        spec = _demo()
        spec["deck"]["slides"][3]["layout"] = "lean-left"
        resolved = compile_mod.compile_spec(spec)
        entry = next(t for t in resolved["trace"] if t["stage"] == "layout")
        self.assertIn("two-column:lean-left", entry["decision"])
        self.assertEqual(resolved["deck"]["slides"][3].get("layout"), "lean-left")

    def test_custom_layout_on_two_col_gets_the_hook(self) -> None:
        """自造布局名：缺省列宽结构 + data-layout，skin 负责改排。"""
        custom = self._page_html("poster-two")
        self.assertIn('data-layout="poster-two"', custom)
        self.assertEqual(custom.replace(' data-layout="poster-two"', ""),
                         self._page_html(None), "自造布局名不许改变结构")
