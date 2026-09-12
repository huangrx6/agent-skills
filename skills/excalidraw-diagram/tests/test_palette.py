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
def _channels(colour: str) -> tuple[int, int, int]:
    if not colour.startswith("#") or len(colour) != 7:
        raise ValueError(f"不是 #RRGGBB 形式：{colour!r}")
    return (int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16))


def _luminance(colour: str) -> float:
    linear = []
    for value in _channels(colour):
        c = value / 255
        linear.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def saturation(colour: str) -> float:
    r, g, b = (v / 255 for v in _channels(colour))
    high, low = max(r, g, b), min(r, g, b)
    return 0.0 if high <= 0 else (high - low) / high


def _lab(colour: str) -> tuple[float, float, float]:
    v = []
    for value in _channels(colour):
        c = value / 255
        v.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    x = (v[0] * 0.4124 + v[1] * 0.3576 + v[2] * 0.1805) / 0.95047
    y = v[0] * 0.2126 + v[1] * 0.7152 + v[2] * 0.0722
    z = (v[0] * 0.0193 + v[1] * 0.1192 + v[2] * 0.9505) / 1.08883
    f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116   # noqa: E731
    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def delta_e(a: str, b: str) -> float:
    """CIE76 色差。**不能拿对比度当色差用** —— 对比度只量亮度差，
    而这套莫兰迪相邻色的特点正是"亮度相近、色相不同"（实测踩过：用对比度判，
    async 与 external 只差 1.005，看着像同色，实际一眼能分）。"""
    return sum((x - y) ** 2 for x, y in zip(_lab(a), _lab(b))) ** 0.5


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
