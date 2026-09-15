#!/usr/bin/env python3
"""ink.py 的回归测试：墨色推导 + 三套色板对比度门禁。

## 这个不变量为什么值得钉住

文字色不是「选」出来的，是**推导**出来的 —— `overprint(primary, secondary)`。
原型实测主 / 副色单独当文字色只有 2.35 / 2.68，达不到正文门槛；两墨叠印才有 9.55。
一旦有人把文字色改回「手写一个值」或者放宽阈值，这套用例里至少一条会红。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/deck-authoring/test_ink.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
# 测试住在仓库顶层 `tests/<skill>/`（**刻意不在 skill 目录里**：AI 调用 skill 时读的是
# `skills/<skill>/` 那棵树，测试放在里面会被顺手读进去）。
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
SCRIPTS = os.path.join(SKILL, "scripts")
TOKENS = os.path.join(SKILL, "dev-tools", "style-fixture", "swiss-grid", "style.json")


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ink = _load("_deck_test_ink", os.path.join(SCRIPTS, "ink.py"))


class TestInkGate(unittest.TestCase):
    """三套现役色板必须过；两墨都亮的坏色板必须被拒。"""

    def setUp(self) -> None:
        with open(TOKENS, encoding="utf-8") as fh:
            self.tokens = json.load(fh)
        self.limits = self.tokens["contrast"]

    def test_every_current_palette_passes_body_floor(self) -> None:
        """现役三套色板的叠印墨对比度都必须 ≥ minBody。"""
        for name, colors in self.tokens["colorSets"].items():
            with self.subTest(palette=name):
                text_ink = ink.overprint(colors["primary"], colors["secondary"])
                ratio = ink.contrast(text_ink, colors["background"])
                self.assertGreaterEqual(
                    ratio, self.limits["minBody"],
                    f"{name} 的叠印墨 {text_ink} 对比度 {ratio:.2f} < {self.limits['minBody']}")

    def test_two_light_inks_fail_the_floor(self) -> None:
        """朱红 × 土黄（style.json 注释里的真实失败样例）必须不达标。

        这条守住"换色板，不要放宽门槛"：valid 的色板必须含一个深墨。
        """
        ratio = ink.contrast(ink.overprint("#FF6B35", "#FFCC00"), "#FAF3E7")
        self.assertLess(ratio, self.limits["minBody"],
                        f"两墨都亮本应不达标，却算出 {ratio:.2f} —— 门禁退化")

    def test_the_declared_text_color_clears_the_body_threshold(self) -> None:
        """每套色板**声明的文字色**必须过正文门槛。

        这条取代了原来的「主/副色单独当文字色必然不达标」。原断言是**叠印风格专属**的
        —— 孔版那套主/副色是荧光色（2.35/2.68），所以“只能叠印”。而黑底白字、
        白底黑字、深蓝当文字这类风格，主色本来就能承载文字（实测瑞士栅格 blue
        的主色单独当文字是 8.95，达标）。拿旧断言套新风格就是假设过时了。

        真正要守的不变的是：**产出的文字色过门槛** —— 无论它是声明的还是派生的。
        """
        for name, colors in self.tokens["colorSets"].items():
            with self.subTest(palette=name):
                ratio = ink.contrast(ink.text_color(colors), colors["background"])
                self.assertGreaterEqual(
                    ratio, self.limits["minBody"],
                    f"{name} 声明的文字色对比度只有 {ratio:.2f}，低于正文门槛 "
                    f"{self.limits['minBody']} —— 换色板，不要放宽门槛")

    def test_overprint_is_commutative(self) -> None:
        """sRGB 逐通道相乘必然可交换 —— 实现一致性自检。"""
        self.assertEqual(ink.overprint("#FF48B0", "#00A8E8"),
                         ink.overprint("#00A8E8", "#FF48B0"))

    def test_contrast_identity_is_one(self) -> None:
        """WCAG 定义：任何颜色相对自己的对比度 = 1.0。"""
        for color in ("#FF48B0", "#00A8E8", "#F5EFDD", "#000000", "#FFFFFF"):
            with self.subTest(color=color):
                self.assertAlmostEqual(ink.contrast(color, color), 1.0, places=12)


if __name__ == "__main__":
    unittest.main()
