#!/usr/bin/env python3
"""palette.py 的回归测试：用户指定的莫兰迪配色，可用性用**量出来的数**守住。

## 为什么这层值得有测试

配色看起来是"审美"，但里面有几条**可测量**的硬约束。不测的代价这次已经付过：
我在 `palette.py` 注释里写了"对比度 ≥ 7:1"，而**那句话是写的时候还没量过的**，
实测只有 6.15~7.79。所以现在这层不写"深色文字可读"这种话，直接算、直接卡。

## 判据的来历（每一条都说清为什么是这个数）

| 判据 | 阈值 | 实测 | 依据 |
| --- | --- | --- | --- |
| 文字 vs 底色 | ≥ 4.5 | 6.15 ~ 7.79 | WCAG AA 正文 |
| 文字 vs 画布 | ≥ 4.5 | 9.00 | 同上 |
| 描边 vs 底色 | ≥ 1.8 | 2.19 ~ 2.48 | 框边界要看得见 |
| 描边 vs 画布 | ≥ 2.0 | 2.57 ~ 3.63 | 否则轮廓在页面上"消失" |
| 底色 vs 画布 ΔE | ≥ 5 | 8.0 ~ 17.0 | 浅色块也要分得出来 |
| 底色两两 ΔE | ≥ 5 | 6.7 | 色板的意义就是"一眼按颜色分角色" |
| 饱和度 | ≤ 0.30 | 0.14 | 莫兰迪 = 去饱和 |
| 亮度 | ≥ 0.50 | 0.65 | 用户要"浅色一点" |

**关于描边为什么不卡 WCAG 的 3:1**：那一条是给 **UI 控件边界**定的（按钮、输入框 ——
用户得先找到它才能操作）。图里的框是**内容**，它的可读性由文字对比度承担（已卡 4.5）。
而且实测过：把描边压到 3:1，六条会全部变成近似的深灰（`#8A857E` / `#71797D` / `#77737B`…），
**色相识别没了** —— 那正好违背用户要的风格。所以描边卡的是"看得见"，不是"够黑"。

阈值都留在实测值**之下**留余量：它们是防"换成荧光色 / 换成深色底"这类退化的闸门，
不是把当前数值抄一遍（那种测试只会把数字写死，改不动）。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/test_palette.py
"""

from __future__ import annotations

import importlib.util
import itertools
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
PALETTE = os.path.join(SCRIPTS, "palette.py")

TEXT_MIN = 4.5
STROKE_VS_FILL_MIN = 1.8
STROKE_VS_CANVAS_MIN = 2.0
FILL_VS_CANVAS_DE_MIN = 5.0
PAIR_DE_MIN = 5.0          # 感知可辨阈值 ΔE≈2.3，这里留两倍余量
MAX_SATURATION = 0.30
MIN_LUMINANCE = 0.50


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


P = _load("palette", PALETTE)


# ── 颜色数学 ────────────────────────────────────────────────
# 颜色数学的**唯一实现**在 scripts/palette.py 里（图标撞色检查、报告的可读性提示
# 都要用它）—— 这里不再存第二份，只把这几把尺子钉住。
_channels = P.hex_to_rgb
_luminance = P.relative_luminance
contrast = P.contrast
saturation = P.saturation
_lab = P.to_lab
delta_e = P.delta_e


class TestColourMath(unittest.TestCase):
    """先证明这把尺子准，再拿它去量配色。"""

    def test_white_on_black_is_21(self):
        self.assertAlmostEqual(21.0, contrast("#FFFFFF", "#000000"), places=1)

    def test_same_colour_contrast_is_one(self):
        self.assertAlmostEqual(1.0, contrast("#4A4744", "#4A4744"), places=6)

    def test_identical_colour_has_zero_delta_e(self):
        self.assertAlmostEqual(0.0, delta_e("#7C93A6", "#7C93A6"), places=6)

    def test_black_white_delta_e_is_large(self):
        self.assertGreater(delta_e("#000000", "#FFFFFF"), 90)

    def test_delta_e_separates_same_lightness_different_hue(self):
        """这条正是"不能用对比度当色差"的理由。"""
        a, b = "#EBDACB", "#D1DBD4"          # 亮度几乎一样，色相不同
        self.assertLess(contrast(a, b), 1.05)
        self.assertGreater(delta_e(a, b), PAIR_DE_MIN)

    def test_bad_hex_is_rejected(self):
        for bad in ("4A4744", "#4A47", "#GGGGGG"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    _channels(bad)


class TestTextReadability(unittest.TestCase):
    def test_text_on_every_node_fill(self):
        text = P.CANVAS["text"]
        for kind, entry in P.KINDS.items():
            with self.subTest(kind=kind):
                ratio = contrast(text, entry["background"])
                self.assertGreaterEqual(ratio, TEXT_MIN,
                                        f"{kind} 底色上的文字只有 {ratio:.2f}")

    def test_text_on_canvas(self):
        self.assertGreaterEqual(contrast(P.CANVAS["text"], P.CANVAS["background"]),
                                TEXT_MIN)


class TestStrokesAreVisible(unittest.TestCase):
    def test_stroke_against_its_own_fill(self):
        for kind, entry in P.KINDS.items():
            with self.subTest(kind=kind):
                ratio = contrast(entry["stroke"], entry["background"])
                self.assertGreaterEqual(ratio, STROKE_VS_FILL_MIN,
                                        f"{kind} 的描边在自己底色上只有 {ratio:.2f}")

    def test_stroke_against_canvas(self):
        for kind, entry in P.KINDS.items():
            with self.subTest(kind=kind):
                ratio = contrast(entry["stroke"], P.CANVAS["background"])
                self.assertGreaterEqual(ratio, STROKE_VS_CANVAS_MIN)

    def test_edge_colours_against_canvas(self):
        for kind, entry in P.EDGE_KINDS.items():
            with self.subTest(kind=kind):
                ratio = contrast(entry["stroke"], P.CANVAS["background"])
                self.assertGreaterEqual(ratio, STROKE_VS_CANVAS_MIN,
                                        f"{kind} 的连线在画布上只有 {ratio:.2f}")


class TestMorandiCharacter(unittest.TestCase):
    """用户指定的是**莫兰迪**：去饱和、灰调、浅色。把风格变成可检查的。"""

    def test_fills_are_desaturated(self):
        for kind, entry in P.KINDS.items():
            with self.subTest(kind=kind):
                sat = saturation(entry["background"])
                self.assertLessEqual(sat, MAX_SATURATION,
                                     f"{kind} 底色饱和度 {sat:.2f} —— 这已经不是莫兰迪了")

    def test_fills_are_light(self):
        for kind, entry in P.KINDS.items():
            with self.subTest(kind=kind):
                self.assertGreaterEqual(_luminance(entry["background"]), MIN_LUMINANCE,
                                        f"{kind} 的底色偏暗，用户要的是浅色")

    def test_fills_stand_out_from_canvas(self):
        for kind, entry in P.KINDS.items():
            with self.subTest(kind=kind):
                d = delta_e(entry["background"], P.CANVAS["background"])
                self.assertGreaterEqual(d, FILL_VS_CANVAS_DE_MIN,
                                        f"{kind} 底色与画布 ΔE 只有 {d:.1f}，看不出成块")

    def test_fills_are_distinguishable_from_each_other(self):
        for (ka, ea), (kb, eb) in itertools.combinations(P.KINDS.items(), 2):
            with self.subTest(pair=(ka, kb)):
                d = delta_e(ea["background"], eb["background"])
                self.assertGreaterEqual(d, PAIR_DE_MIN,
                                        f"{ka} 与 {kb} 的底色 ΔE 只有 {d:.1f}")

    def test_no_duplicate_colours(self):
        values = [v for e in P.KINDS.values() for v in e.values() if v.startswith("#")]
        self.assertEqual(len(values), len(set(values)), "有重复的颜色值")


class TestEmphasis(unittest.TestCase):
    """强调层级 —— 三档必须**真的分得出来**，而且默认档不许改变原观感。"""

    LEVELS = ("primary", "normal", "muted")

    def test_default_level_changes_nothing(self):
        """默认档的填充必须就是色板原色。

        这条是这次改动的**零回归保证**：加 emphasis 之前所有节点都用色板原色，
        默认档若不是原色，等于偷偷把之前看过的图全改了一遍。
        """
        for kind in P.KINDS:
            with self.subTest(kind=kind):
                self.assertEqual(P.background_for(kind),
                                 P.emphasis_fill(kind, P.DEFAULT_EMPHASIS))
                self.assertEqual("normal", P.DEFAULT_EMPHASIS)

    def test_three_levels_are_actually_different(self):
        """三档同色的话，emphasis 就只是多了个没人看得出效果的字段。"""
        for kind in P.KINDS:
            with self.subTest(kind=kind):
                fills = [P.emphasis_fill(kind, lvl) for lvl in self.LEVELS]
                self.assertEqual(3, len(set(fills)), f"{kind} 的填充三档没分开：{fills}")
                widths = [P.emphasis_stroke_width(lvl) for lvl in self.LEVELS]
                self.assertEqual(3, len(set(widths)), f"描边宽三档没分开：{widths}")

    def test_primary_is_heavier_and_muted_is_quieter(self):
        for kind in P.KINDS:
            with self.subTest(kind=kind):
                widths = [P.emphasis_stroke_width(lvl) for lvl in self.LEVELS]
                self.assertGreater(widths[0], widths[1], "primary 要比 normal 重")
                self.assertGreater(widths[1], widths[2], "normal 要比 muted 重")
                # 在浅色底板上“更有颜色 = 更重要” —— 不能用“更深 = 更重要”那套。
                canvas = P.CANVAS["background"]
                d_primary = abs(_luminance(P.emphasis_fill(kind, "primary")) - _luminance(canvas))
                d_normal = abs(_luminance(P.emphasis_fill(kind, "normal")) - _luminance(canvas))
                d_muted = abs(_luminance(P.emphasis_fill(kind, "muted")) - _luminance(canvas))
                self.assertGreater(d_primary, d_normal, "primary 应该比 normal 更实")
                self.assertLess(d_muted, d_normal, "muted 应该更靠近画布（更安静）")

    def test_text_stays_readable_at_every_level(self):
        """primary 会把填充往描边色拉，文字对比度会降 —— 但不能降到 AA 以下。"""
        for kind in P.KINDS:
            for lvl in self.LEVELS:
                with self.subTest(kind=kind, emphasis=lvl):
                    got = contrast(P.CANVAS["text"],
                                   P.emphasis_fill(kind, lvl))
                    self.assertGreaterEqual(got, 4.5, f"对比度只有 {got:.2f}")

    def test_unknown_emphasis_raises_never_falls_back(self):
        """同 kind / shape 一条规矩：不 fallback。"""
        for bad in ("emphasized", "", "PRIMARY", None):
            with self.subTest(emphasis=bad):
                with self.assertRaises(KeyError) as ctx:
                    P.emphasis_fill("service", bad)
                self.assertIn("emphasis", str(ctx.exception))
                with self.assertRaises(KeyError):
                    P.emphasis_stroke_width(bad)

    def test_derived_colours_stay_derived(self):
        """派生色的唯一来源是色板 —— 换个 kind 就该换个结果，不能是写死的常量。"""
        fills = {kind: P.emphasis_fill(kind, "primary") for kind in P.KINDS}
        self.assertEqual(len(P.KINDS), len(set(fills.values())),
                         "primary 的填充各 kind 应当互不相同（说明是从色板算的）")


class TestEveryTheme(unittest.TestCase):
    """**每个**主题都要过同一套不变量。

    为什么单独一个类：主题可切换之后，只在默认主题下跑的那套测试等于
    只测了三分之一 —— 另两个主题变成"没测过的那一半"，而用户看到的正是它们。

    这里只放**不变量**（可读性、边界可见、彼此可区分）。
    莫兰迪的"去饱和 / 偏浅"那种是**风格**约束，只对那一个主题成立，
    放在上面的 TestMorandiCharacter 里。
    """

    def test_every_theme_keeps_text_readable(self):
        for theme in P.available_themes():
            with P.theme_context(theme):
                for kind in P.KINDS:
                    with self.subTest(theme=theme, kind=kind):
                        got = contrast(P.CANVAS["text"], P.background_for(kind))
                        self.assertGreaterEqual(
                            got, 4.5,
                            f"{theme}/{kind} 文字在其填充上只有 {got:.2f}")

    def test_every_theme_keeps_strokes_visible(self):
        for theme in P.available_themes():
            with P.theme_context(theme):
                for kind in P.KINDS:
                    with self.subTest(theme=theme, kind=kind):
                        own = contrast(P.stroke_for(kind), P.background_for(kind))
                        self.assertGreaterEqual(own, 1.5, f"{theme}/{kind} 描边贴住了自己的填充")
                        canvas = contrast(P.stroke_for(kind), P.CANVAS["background"])
                        self.assertGreaterEqual(canvas, 1.5, f"{theme}/{kind} 描边在画布上看不见")

    def test_every_theme_has_distinguishable_fills(self):
        """六种填充必须两两分得开 —— 深色主题尤其容易在这里翻车。

        实测：深色主题第一版六色都挤在 #1E~#36 的窄明度带里，两两 ΔE 最小只有 2.5
        （浅色主题是 6.7），看着就是六块差不多的深灰。所以这条对每个主题都要跑。
        """
        for theme in P.available_themes():
            with P.theme_context(theme):
                fills = {k: P.background_for(k) for k in P.KINDS}
                names = list(fills)
                worst = min((delta_e(fills[a], fills[b]), a, b)
                            for i, a in enumerate(names) for b in names[i + 1:])
                self.assertGreaterEqual(worst[0], 5.0,
                                        f"{theme}: {worst[1]}/{worst[2]} 的填充几乎一样"
                                        f"（ΔE {worst[0]:.1f}）")

    def test_every_theme_sets_a_full_canvas(self):
        for theme in P.available_themes():
            with P.theme_context(theme):
                for key in ("background", "grid", "text"):
                    self.assertIn(key, P.CANVAS, f"{theme} 的画布缺 {key}")
                self.assertEqual(2, P.CANVAS["font_family"])

    def test_themes_are_actually_different_from_each_other(self):
        """几个主题长得一样的话，"可选主题"就是假的。"""
        seen = {}
        for theme in P.available_themes():
            with P.theme_context(theme):
                seen[theme] = tuple(sorted(P.background_for(k) for k in P.KINDS))
        self.assertEqual(len(P.available_themes()), len(set(seen.values())),
                         "有两个主题的六色完全相同")

    def test_theme_context_restores_the_previous_one(self):
        """用例之间不能互相污染 —— 上个用例切了主题没切回来，后面的全跑在错的主题上。"""
        before = P.active_theme()
        with P.theme_context("dark-tech"):
            self.assertEqual("dark-tech", P.active_theme())
        self.assertEqual(before, P.active_theme())

    def test_unknown_theme_raises_and_lists_options(self):
        with self.assertRaises(KeyError) as ctx:
            P.use_theme("蒸汽波")
        message = str(ctx.exception)
        for name in P.available_themes():
            self.assertIn(name, message, "报错要列出可用主题")
        P.use_theme(None)          # 还原，别影响后面的用例


class TestPaletteShape(unittest.TestCase):
    def test_kind_count_is_capped(self):
        self.assertLessEqual(len(P.KINDS), P.MAX_KINDS)

    def test_unknown_kind_raises_never_falls_back(self):
        """**绝不 fallback** —— 静默给个默认色会让"颜色必须在板内"这条校验自己绕过自己。"""
        with self.assertRaises(KeyError):
            P.stroke_for("queue")
        with self.assertRaises(KeyError):
            P.background_for("queue")
        with self.assertRaises(KeyError):
            P.edge_style_for("telepathy")

    def test_every_kind_has_a_chinese_role(self):
        for kind, entry in P.KINDS.items():
            with self.subTest(kind=kind):
                self.assertTrue(entry.get("zh"), f"{kind} 缺中文语义说明")


if __name__ == "__main__":
    unittest.main(verbosity=2)
