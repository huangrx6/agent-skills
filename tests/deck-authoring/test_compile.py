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
        """无 mood → 风格语法决策（swiss color_creativity=0.55 < 0.66 → safe）。"""
        spec = _demo()
        spec["deck"]["colorSet"] = "auto"
        resolved = compile_mod.compile_spec(spec)
        entry = next(t for t in resolved["trace"]
                     if t["stage"] == "theme" and t["decision"].startswith("auto:"))
        self.assertEqual(entry["decision"], "auto:safe")
        joined = "".join(entry["reason"])
        self.assertIn("color_creativity", joined, "理由里没说风格语法依据")
        self.assertIn("不参与方向决策", joined, "没写明 seed 不做审美决策")
        self.assertIn("纸色文字不动", joined, "理由里没说对比度保证")

    def test_mood_overrides_style_grammar(self) -> None:
        """mood 是第一优先级：bold 压过风格的克制声明 → auto:creative。"""
        spec = _demo()
        spec["deck"]["colorSet"] = "auto"
        spec["deck"]["mood"] = "bold"
        resolved = compile_mod.compile_spec(spec)
        entry = next(t for t in resolved["trace"]
                     if t["stage"] == "theme" and t["decision"].startswith("auto:"))
        self.assertEqual(entry["decision"], "auto:creative")
        self.assertIn("mood=bold", "".join(entry["reason"]))

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

    def test_chart_type_decision_is_traced(self) -> None:
        """图表页的 intent→type 决策进 trace（§19 v2，与渲染同源的纯函数）。"""
        spec = _demo()
        spec["deck"]["slides"] = [
            {"type": "chart", "title": "季度达成", "intent": "progress",
             "data": [{"label": "Q4", "value": 72}]}]
        resolved = compile_mod.compile_spec(spec)
        entry = next(t for t in resolved["trace"] if t["stage"] == "chart")
        self.assertEqual(entry["decision"], "chart:bar-horizontal")
        self.assertIn("温度计", "".join(entry["reason"]))

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
        no_bullets["deck"]["slides"][2]["variant"] = "hero"
        full = render.render(no_bullets)
        self.assertIn("height:648px", full)
        self.assertIn("background:var(--text)", full)   # --text 底 / --paper 字


class TestAutoVariant(unittest.TestCase):
    """variant:"auto"：吃实测数据选变体；没数据回退默认 —— 都不猜。"""

    REC = {"page": 3, "variant": "even", "score": 0.42, "density": 0.6,
           "parts": {"fit": 1.0, "whitespace": 1.0, "semantic": 1.0},
           "penalties": [],
           "alternatives": [{"variant": "visual-right", "score": 0.31, "density": 0.5},
                            {"variant": "visual-left", "score": 0.31, "density": 0.5}]}

    def _spec(self, variant: str | None) -> dict:
        spec = _demo()
        page = spec["deck"]["slides"][2]              # 第 3 页 content-image
        page.pop("variant", None)
        if variant:
            page["variant"] = variant
        return spec

    def test_auto_with_data_uses_measured_best(self) -> None:
        resolved = compile_mod.compile_spec(self._spec("auto"),
                                            fit_variants=[self.REC])
        self.assertEqual(resolved["deck"]["slides"][2]["variant"], "even")
        entry = next(t for t in resolved["trace"] if t["stage"] == "layout")
        self.assertIn("实测最佳", entry["decision"])
        self.assertIn("0.42", "".join(entry["reason"]), "理由里没带分数对比")

    def test_auto_without_data_falls_back_to_default(self) -> None:
        resolved = compile_mod.compile_spec(self._spec("auto"))
        self.assertEqual(resolved["deck"]["slides"][2]["variant"], "visual-right")
        entry = next(t for t in resolved["trace"] if t["stage"] == "layout")
        self.assertIn("默认", entry["decision"])
        self.assertIn("回退默认而不是猜", "".join(entry["reason"]))

    def test_explicit_beats_data(self) -> None:
        """显式 variant 永远赢 —— 实测数据不越权改内容决策。"""
        resolved = compile_mod.compile_spec(self._spec("visual-left"),
                                            fit_variants=[self.REC])
        self.assertEqual(resolved["deck"]["slides"][2]["variant"], "visual-left")

    def test_dict_form_accepted(self) -> None:
        """{页码: rec} 形态也认（页码 str/int 都行）。"""
        resolved = compile_mod.compile_spec(self._spec("auto"),
                                            fit_variants={"3": self.REC})
        self.assertEqual(resolved["deck"]["slides"][2]["variant"], "even")

    def test_resolved_never_carries_auto(self) -> None:
        """auto 是意图不是几何：resolved 里不许出现（渲染器值集没有它）。"""
        for fv in (None, [self.REC]):
            resolved = compile_mod.compile_spec(self._spec("auto"), fit_variants=fv)
            for page in resolved["deck"]["slides"]:
                self.assertNotEqual(page.get("variant"), "auto")


class TestTwoColVariantRendering(unittest.TestCase):
    """two-column 三变体几何分叉；显式 even == 隐式不写（字节级契约）；
    默认双栏字节不变（上一条黄金测试钉着）。"""

    def _page_html(self, variant: str | None) -> str:
        spec = _demo()
        page = spec["deck"]["slides"][3]              # 第 4 页 two-column
        page.pop("variant", None)
        if variant:
            page["variant"] = variant
        out = render.render(spec)
        return out.split('data-idx="04"')[1].split('data-idx="05"')[0]

    def test_variants_differ_in_geometry(self) -> None:
        even = self._page_html("even")
        lean_l = self._page_html("lean-left")
        lean_r = self._page_html("lean-right")
        self.assertIn('class="cols v-lean-left"', lean_l)
        self.assertIn('class="cols v-lean-right"', lean_r)
        self.assertIn('class="cols">', even, "默认不该带变体类（保持旧字节）")
        self.assertNotEqual(lean_l, lean_r, "两个 lean 变体渲成了同一份 DOM")
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

    def test_explicit_variant_is_traced_without_compile_changes(self) -> None:
        """compile.py 未改：layout trace 对任何带 variant 的页自动留痕。"""
        spec = _demo()
        spec["deck"]["slides"][3]["variant"] = "lean-left"
        resolved = compile_mod.compile_spec(spec)
        entry = next(t for t in resolved["trace"] if t["stage"] == "layout")
        self.assertIn("two-column:lean-left", entry["decision"])
        self.assertEqual(resolved["deck"]["slides"][3].get("variant"), "lean-left")

    def test_unknown_variant_exits_cleanly(self) -> None:
        """渲染器也可能被直调（不经 validate_spec）：未知变体要人话报错，不甩栈。"""
        spec = _demo()
        spec["deck"]["slides"][3]["variant"] = "left-lean"
        with self.assertRaises(SystemExit) as ctx:
            render.render(spec)
        msg = str(ctx.exception)
        self.assertIn("two-column", msg)
        self.assertIn("lean-left", msg, "报错必须给出路：可用值要列出来")
