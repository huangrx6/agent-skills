#!/usr/bin/env python3
"""配色的回归测试：OKLCH 换算、色相结构分类、novelty 判据、三方向、角色推导。

这一层最容易出的错有两类，用例大多针对它们：

**一、算错了但看不出来。** OKLCH 是我手搓的（sRGB → 线性 → LMS → 立方根 →
OKLab → 极坐标），算错了不会抛异常，只会让"结构分类"和"变体"悄悄偏 —— 所以第一条
用例就是**往返精度**：`to_hex(oklch(hex))` 必须还原回原色。

**二、判据范围错了。** 俗套那条（规范第 18/23 条）是**按主题条件**的：AI 主题 + 蓝紫青
才是"自动绑定俗套"。如果没有主题也报，那这条提示会在每个非科技 deck 上刷屏，
然后被整体忽略 —— 所以正反两面都要测。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/deck-authoring/test_palette.py
"""

from __future__ import annotations

import importlib.util
import zlib
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
SCRIPTS = os.path.join(SKILL, "scripts")
STYLES = os.path.join(SKILL, "styles")


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


palette = _load("palette")
ink = _load("ink")


def _rgb(hexstr: str) -> tuple[int, int, int]:
    h = hexstr.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


class TestOklch(unittest.TestCase):
    """手搓的换算必须可验证 —— 算错不会抛，只会悄悄偏。"""

    # 覆盖各个色相区、明暗两端、以及近乎中性的色（后者最容易在立方根那步出错）
    SAMPLES = ("#000000", "#FFFFFF", "#0A0A0A", "#F4F4F4", "#0033CC", "#D93F0B",
               "#0B6B3A", "#FF6900", "#58A6FF", "#D4A574", "#8A8578", "#FBFAF6",
               "#2F6FB0", "#C8443C", "#1ED760", "#8B949E")

    def test_round_trip_is_exact_per_channel(self) -> None:
        """**往返**：HEX → OKLCH → HEX 必须还原。

        允许每个通道 ±1（8 位色深本来就有取整），但**不能更大** —— 更大的误差说明
        公式或矩阵系数错了，而那种错不会以异常的形式出现。
        """
        for hexstr in self.SAMPLES:
            with self.subTest(color=hexstr):
                back = palette.to_hex(palette.oklch(hexstr))
                self.assertEqual(len(back), 7)
                for got, want in zip(_rgb(back), _rgb(hexstr)):
                    self.assertLessEqual(abs(got - want), 1,
                                         f"{hexstr} → {back}（通道差 {got - want}）")

    def test_lightness_is_perceptually_ordered(self) -> None:
        """明度排序必须与肉眼一致 —— 这正是用 OKLCH 而不是 HSL 的理由。

        HSL 里蓝和黄的 L 都是 50%，感知上却差很多。这里钉住"白 > 黄 > 蓝 > 黑"。
        """
        L = {c: palette.oklch(c)[0] for c in ("#FFFFFF", "#FFE01B", "#0033CC", "#000000")}
        self.assertGreater(L["#FFFFFF"], L["#FFE01B"])
        self.assertGreater(L["#FFE01B"], L["#0033CC"])
        self.assertGreater(L["#0033CC"], L["#000000"])

    def test_achromatic_colors_have_near_zero_chroma(self) -> None:
        for hexstr in ("#000000", "#FFFFFF", "#0A0A0A", "#4A4A4A"):
            with self.subTest(color=hexstr):
                self.assertLess(palette.oklch(hexstr)[1], 0.01)

    def test_hue_is_in_range(self) -> None:
        for hexstr in self.SAMPLES:
            with self.subTest(color=hexstr):
                h = palette.oklch(hexstr)[2]
                self.assertGreaterEqual(h, 0.0)
                self.assertLess(h, 360.0)


class TestHueStructure(unittest.TestCase):
    """色相结构分类（规范第 5 条）。"""

    def test_accent_plus_neutral_is_neutral_accent(self) -> None:
        self.assertEqual(palette.hue_structure(
            {"primary": "#0033CC", "secondary": "#0A0A0A", "background": "#FFFFFF"}),
            "neutral-accent")

    def test_close_hues_are_analogous(self) -> None:
        self.assertEqual(palette.hue_structure(
            {"primary": "#2997FF", "secondary": "#5AC8FA", "background": "#000000"}),
            "analogous")

    def test_opposite_hues_are_complementary(self) -> None:
        self.assertEqual(palette.hue_structure(
            {"primary": "#2F6FB0", "secondary": "#E0A400", "background": "#FFFFFF"}),
            "complementary")

    def test_near_neutral_secondary_counts_as_neutral(self) -> None:
        """**回归（按实测标定的那条）**：`#8A8578` 的彩度是 0.020，目视是暖灰。

        原先阈值取 0.02，它正好卡在边界上被算成"有色" —— 于是 `pastel-geometry`
        被判成互补色，而那套风格实际是**中性 + 单强调色**（实测发现）。
        阈值抬到 0.03 之后它归中性。
        """
        chroma = palette.oklch("#8A8578")[1]
        self.assertLess(chroma, palette.NEUTRAL_CHROMA)
        self.assertEqual(palette.hue_structure(
            {"primary": "#6C5CA8", "secondary": "#8A8578", "background": "#F7F5FB"}),
            "neutral-accent")

    def test_a_truly_colored_secondary_still_counts(self) -> None:
        """反面对照：抬阈值不能把"真的有色"也吞掉。

        `#C9B896` 彩度 0.050（botanical 的副色，确实带黄）—— 它必须仍算有色。
        """
        self.assertGreater(palette.oklch("#C9B896")[1], palette.NEUTRAL_CHROMA)
        self.assertEqual(palette.hue_structure(
            {"primary": "#D4A574", "secondary": "#C9B896", "background": "#0F0F0F"}),
            "analogous")


class TestNovelty(unittest.TestCase):
    """俗套判据（规范第 18 / 23 条）—— **按主题条件**。"""

    TECH = {"primary": "#0033CC", "secondary": "#0A0A0A", "background": "#FFFFFF"}

    def _penalties(self, colors: dict, topic: str) -> set[str]:
        _score, reasons = palette.novelty(colors, topic)
        return {r["id"] for r in reasons if r["kind"] == "penalty"}

    def test_tech_topic_with_blue_is_flagged(self) -> None:
        self.assertIn("tech_blue_purple_cyan", self._penalties(self.TECH, "AI 大模型架构"))

    def test_the_same_palette_without_a_tech_topic_is_not_flagged(self) -> None:
        """**关键的反面**：没有科技主题时，蓝主色不该被扣这一条。

        否则这条提示会在每个非科技 deck 上刷屏，然后被整体忽略 —— 那比不做还糟。
        """
        self.assertNotIn("tech_blue_purple_cyan",
                         self._penalties(self.TECH, "年度财务复盘"))

    def test_corporate_blue_white_is_flagged_regardless_of_topic(self) -> None:
        """蓝主色 + 白底是企业模板的默认解 —— 这条与主题无关。"""
        self.assertIn("corporate_blue_white", self._penalties(self.TECH, ""))

    def test_a_non_cliche_palette_scores_higher_than_the_cliche(self) -> None:
        """反面对照：非常规组合（暖色 + 深底）必须**比俗套那套分高**。

        比"绝对值大于某个数"更有意义 —— 单看分数会随权重调整而失效，而"排序对不对"
        是这条判据真正要保证的东西。
        """
        plant, _ = palette.novelty(
            {"primary": "#D4A574", "secondary": "#9FB39A", "background": "#0F0F0F"}, "植物")
        cliche, _ = palette.novelty(self.TECH, "AI 大模型架构")
        self.assertGreater(plant, cliche, f"植物 {plant:.2f} 没比俗套 {cliche:.2f} 高")

    def test_reasons_name_the_rule(self) -> None:
        """扣分必须**说得出是哪一条** —— 否则 novelty 只是个没说服力的数字。"""
        _score, reasons = palette.novelty(self.TECH, "AI 大模型")
        self.assertTrue(reasons)
        for r in reasons:
            self.assertIn(r["id"], [p[0] for p in palette.PENALTIES]
                          + [b[0] for b in palette.BONUSES])
            self.assertTrue(r["why"], "没有说明为什么")
            self.assertNotEqual(r["delta"], 0.0, "记了一条权重为 0 的")

    def test_score_is_bounded(self) -> None:
        for colors in (self.TECH,
                       {"primary": "#FFE01B", "secondary": "#FF3B30", "background": "#0A0A0A"},
                       {"primary": "#D4A574", "secondary": "#0F0F0F", "background": "#0F0F0F"}):
            with self.subTest(colors=colors):
                score, _ = palette.novelty(colors, "AI 科技")
                self.assertGreaterEqual(score, 0.0)
                self.assertLessEqual(score, 1.0)

    def test_thresholds_match_the_spec(self) -> None:
        self.assertEqual(palette.NOVELTY_MIN, {"plain": 0.45, "design": 0.65, "cover": 0.75})


class TestDirections(unittest.TestCase):
    """三方向（规范第 17 / 19 条）：确定性 + 变化落在允许范围内。"""

    BASE = {"primary": "#0033CC", "secondary": "#0A0A0A", "background": "#FFFFFF"}

    def test_three_directions(self) -> None:
        self.assertEqual(sorted(palette.directions(self.BASE)),
                         ["creative", "experimental", "safe"])

    def test_safe_is_identical(self) -> None:
        self.assertEqual(palette.variant(self.BASE, "safe")["primary"], self.BASE["primary"])

    def test_deterministic(self) -> None:
        """同一份输入必须得到同一份输出 —— 随机会让两次渲染不一致，没法回归。"""
        for _ in range(3):
            self.assertEqual(palette.directions(self.BASE),
                             palette.directions(self.BASE))

    def test_variation_stays_within_the_spec_range(self) -> None:
        """规范第 19 条：Hue ±10~30°、Chroma ±5~20%、Lightness ±3%~12%。"""
        base_l, base_c, base_h = palette.oklch(self.BASE["primary"])
        for name in ("creative", "experimental"):
            L, C, H = palette.oklch(palette.variant(self.BASE, name)["primary"])
            with self.subTest(direction=name):
                self.assertLessEqual(palette._hue_delta(base_h, H), 30.0)
                self.assertLessEqual(abs(C / base_c - 1.0), 0.20)
                self.assertLessEqual(abs(L - base_l), 0.12)

    def test_neutral_colors_are_left_alone(self) -> None:
        """中性色不参与色相变化 —— 挪了只会变脏。"""
        out = palette.variant(self.BASE, "experimental")
        self.assertEqual(out["secondary"], self.BASE["secondary"])
        self.assertEqual(out["background"], self.BASE["background"])

    def test_unknown_direction_is_reported(self) -> None:
        with self.assertRaises(SystemExit):
            palette.variant(self.BASE, "nope")


class TestRoles(unittest.TestCase):
    """13 个角色的推导（规范第 20 条）。"""

    BASE = {"primary": "#0033CC", "secondary": "#0A0A0A", "background": "#FFFFFF"}

    def test_all_roles_present(self) -> None:
        out = palette.roles(self.BASE)
        for key in ("background", "surface", "surface_alt", "primary", "secondary",
                    "accent", "highlight", "text_primary", "text_secondary",
                    "text_muted", "border", "chart_colors", "gradient"):
            with self.subTest(role=key):
                self.assertIn(key, out)

    def test_surface_differs_from_background_on_both_papers(self) -> None:
        """浅底与深底的偏移方向必须相反 —— 否则深底上 surface 会比底还亮得离谱。"""
        light = palette.roles(self.BASE)
        dark = palette.roles({"primary": "#2997FF", "secondary": "#5AC8FA",
                              "background": "#000000"})
        self.assertNotEqual(light["surface"], light["background"])
        self.assertNotEqual(dark["surface"], dark["background"])
        self.assertLess(palette.oklch(light["surface"])[0],
                        palette.oklch(light["background"])[0])
        self.assertGreater(palette.oklch(dark["surface"])[0],
                           palette.oklch(dark["background"])[0])

    def test_text_tiers_are_ordered(self) -> None:
        out = palette.roles(self.BASE)
        L = [palette.oklch(out[k])[0] for k in
             ("text_primary", "text_secondary", "text_muted")]
        self.assertEqual(L, sorted(L, reverse=True), f"文字层级乱了：{L}")

    def test_text_primary_is_readable(self) -> None:
        """推出来的文字色必须过门槛 —— 这是 role 推导存在的意义。"""
        for base in (self.BASE,
                     {"primary": "#2997FF", "secondary": "#5AC8FA", "background": "#000000"}):
            out = palette.roles(base)
            with self.subTest(bg=base["background"]):
                self.assertGreaterEqual(
                    ink.contrast(out["text_primary"], out["background"]), 4.5)

    def test_chart_colors_are_distinct_and_bounded(self) -> None:
        out = palette.roles(self.BASE)
        self.assertGreaterEqual(len(out["chart_colors"]), 4)
        self.assertEqual(len(out["chart_colors"]), len(set(out["chart_colors"])))

    def test_gradient_stops_are_non_uniform(self) -> None:
        """规范第 13 条：可用非线性 stop —— 不要固定 0 / 50 / 100。"""
        stops = palette.roles(self.BASE)["gradient"]["stops"]
        offsets = [s[0] for s in stops]
        self.assertNotEqual(offsets, [0.0, 0.5, 1.0])
        self.assertEqual(offsets[0], 0.0)
        self.assertEqual(offsets[-1], 1.0)
        self.assertEqual(offsets, sorted(offsets))


class TestAudit(unittest.TestCase):
    """审查：客观的阻塞、语境的提示。"""

    def _styles(self):
        for name in sorted(os.listdir(STYLES)):
            path = os.path.join(STYLES, name, "style.json")
            if os.path.isfile(path) and not name.startswith("zz_"):
                with open(path, encoding="utf-8") as fh:
                    yield name, json.load(fh)

    def test_no_blocking_problem_in_the_shipped_styles(self) -> None:
        for name, tokens in self._styles():
            problems, _notes = palette.audit(tokens, "AI 大模型架构")
            with self.subTest(style=name):
                self.assertEqual(problems, [], f"{name}：{problems}")

    def test_unreadable_text_is_blocking(self) -> None:
        """反面对照：故意造一个文字对比不达标的风格，必须被阻塞。"""
        bad = {"label": "T", "colorSets": {"x": {"primary": "#777777",
                                                 "secondary": "#888888",
                                                 "background": "#7A7A7A",
                                                 "text": "#7B7B7B"}},
               "contrast": {"minBody": 4.5}}
        problems, _notes = palette.audit(bad)
        self.assertTrue(problems, "文字不可读却没被拦")

    def test_cliche_is_advisory_not_blocking(self) -> None:
        """**关键**：俗套必须是提示而不是阻塞 —— 仓库自己的风格就有 5 套命中它。

        把它做成阻塞的话，仓库自己的风格先挂，而规范第 23 条的原文是"不得**自动**
        绑定"（是主题条件的问题），不是"这个色不许用"。
        """
        cliche = {"label": "T", "colorSets": {"blue": {"primary": "#0033CC",
                                                       "secondary": "#0A0A0A",
                                                       "background": "#FFFFFF",
                                                       "text": "#0A0A0A"}},
                  "contrast": {"minBody": 4.5}}
        problems, notes = palette.audit(cliche, "AI 大模型架构")
        self.assertEqual(problems, [], "俗套不该阻塞")
        self.assertTrue(any("tech_blue_purple_cyan" in n for n in notes), notes)

    def test_declared_structure_matching_reality_passes(self) -> None:
        """声明的色相结构必须落在实测集合里（现在是，因为两者由同一次测量产生）。"""
        for name, tokens in self._styles():
            if "colorStructure" not in tokens:
                continue
            with self.subTest(style=name):
                _problems, notes = palette.audit(tokens)
                self.assertFalse(any("声明 hue_structure" in n for n in notes), notes)

    def test_wrong_declaration_is_caught(self) -> None:
        """反面对照：声明与实测不符必须报出来。"""
        wrong = {"label": "T", "colorStructure": {"hue_structure": "triadic"},
                 "colorSets": {"x": {"primary": "#0033CC", "secondary": "#0A0A0A",
                                     "background": "#FFFFFF", "text": "#0A0A0A"}},
                 "contrast": {"minBody": 4.5}}
        _problems, notes = palette.audit(wrong)
        self.assertTrue(any("声明 hue_structure" in n for n in notes), notes)

    def test_novelty_floor_reports_when_missed(self) -> None:
        cliche = {"label": "T", "colorSets": {"blue": {"primary": "#0033CC",
                                                       "secondary": "#0A0A0A",
                                                       "background": "#FFFFFF",
                                                       "text": "#0A0A0A"}},
                  "contrast": {"minBody": 4.5}}
        _problems, notes = palette.audit(cliche, "AI 大模型", novelty_floor=0.65)
        self.assertTrue(any("novelty" in n for n in notes), notes)


if __name__ == "__main__":
    unittest.main()


class TestAutoSet(unittest.TestCase):
    """colorSet 省略 / auto：风格手调基准 + seed 确定性派生。

    规则口径（总编排 §17 / 品牌协议 §5）：Style 出**语法与基准**，主题按 deck
    实际情况（seed）派生——同 seed 同结果（可回归），不同 deck 落不同变体。
    这条最容易出的错：派生动了纸色/文字 → 对比度结构悄悄坏掉。所以第二条
    钉死：只有 primary/secondary 允许动。
    """

    def setUp(self) -> None:
        # style.json 是扁平的（load_style 才包成 {tokens, skin}）；auto_set 只
        # 需要 colorSets，拿原文件即可。
        with open(os.path.join(STYLES, "swiss-grid", "style.json"),
                  encoding="utf-8") as fh:
            self.tokens = json.load(fh)
        self.base_name = list(self.tokens["colorSets"])[0]
        self.base = self.tokens["colorSets"][self.base_name]

    def _fresh(self) -> dict:
        return json.loads(json.dumps(self.tokens))

    def test_same_seed_same_result_and_injected_by_name(self) -> None:
        a = palette.auto_set(self._fresh(), 1)
        b = palette.auto_set(self._fresh(), 1)
        self.assertEqual(a, b, "同 seed 派生两次不一样 —— 混进了随机性")
        tokens = self._fresh()
        name, colors = palette.auto_set(tokens, 1)
        self.assertIn(name, tokens["colorSets"], "派生结果没注入 —— 消费方没名可取")
        self.assertEqual(tokens["colorSets"][name], colors)

    def test_only_primary_secondary_move(self) -> None:
        tokens = self._fresh()
        seed = next(s for s in range(1, 30)
                    if ["safe", "creative", "experimental"][
                        zlib.crc32(f"auto:{s}".encode()) % 3] == "creative")
        _, colors = palette.auto_set(tokens, seed)
        self.assertEqual(colors["background"], self.base["background"],
                         "纸色被动了 —— 对比度结构会悄悄坏")
        self.assertEqual(colors["text"], self.base["text"])
        self.assertNotEqual(colors["primary"], self.base["primary"],
                            "creative 方向没真的变 —— 派生是空转")

    def test_safe_direction_is_identity(self) -> None:
        tokens = self._fresh()
        seed = next(s for s in range(1, 30)
                    if ["safe", "creative", "experimental"][
                        zlib.crc32(f"auto:{s}".encode()) % 3] == "safe")
        name, colors = palette.auto_set(tokens, seed)
        self.assertEqual(colors, self.base, "safe 桶应等于基准本身")

    def test_omitted_colorset_renders_reproducibly(self) -> None:
        """端到端：省略 colorSet 也能渲、同 seed 逐字节可复现、validate 放行。"""
        render = _load("render")
        validate = _load("validate_spec")
        with open(os.path.join(SKILL, "dev-tools", "demo.spec.json"),
                  encoding="utf-8") as fh:
            spec = json.load(fh)
        spec["deck"].pop("colorSet", None)
        self.assertEqual(validate.validate(spec).errors, [])
        html1 = render.render(json.loads(json.dumps(spec)))
        html2 = render.render(json.loads(json.dumps(spec)))
        self.assertIn("<section", html1)
        self.assertEqual(html1, html2, "同 seed 渲两次不一样 —— auto 不确定")
        spec["deck"]["colorSet"] = "auto"
        self.assertEqual(validate.validate(spec).errors, [],
                         "显式 auto 应放行")
