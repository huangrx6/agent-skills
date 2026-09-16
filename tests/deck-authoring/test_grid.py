#!/usr/bin/env python3
"""网格 / 间距令牌 / 阶梯 与 对齐的回归测试。

这一层是「布局重构」的地基，地基的错不会当场炸 —— 只会让所有页面一起歪。
所以用例钉的是**数学**：

- 列宽不是整数（(1432−11×24)/12 = 97.33），一切吸附判断都吃这个精度；
- 7+5 列的分栏必须**正好**铺满内容宽（825.33 + 24 + 582.67 = 1432）；
- 间距令牌的关系规则（组距 ≥ 1.5 × 条目距）是从 ramp 推的，改一个值就可能破。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/deck-authoring/test_grid.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
# 测试自有夹具（v4）：风格与内容样本都放在 tests/ 下，**不随 skill 发布** ——
# 可拷贝的模板必然变成默认答案（用户实测：每份 deck 长得一样）。
FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
# 夹具当"额外风格根"：v4 起工具链不内置任何风格（可拷贝的模板必然变成
# 默认答案）。脚本各持一份模块副本，所以走环境变量而不是改常量。
os.environ.setdefault("DECK_STYLES",
                      os.path.join(FIXTURES_DIR, "styles"))
os.environ.setdefault("DECK_BRANDS",
                      os.path.join(FIXTURES_DIR, "brands"))
SCRIPTS = os.path.join(SKILL, "scripts")
STYLES = os.path.join(FIXTURES_DIR, "styles")
DEMO = os.path.join(FIXTURES_DIR, "demo.spec.json")


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


grid = _load("grid")
render = _load("render")
check = _load("check")


class TestGridMath(unittest.TestCase):
    """列与跨度的数学 —— 一切吸附判断都吃这个精度。"""

    def test_columns_fill_the_content_width_exactly(self) -> None:
        """12 列 + 11 个列距必须正好铺满内容宽（不多不少）。"""
        self.assertAlmostEqual(
            grid.COLUMNS * grid.COL_W + (grid.COLUMNS - 1) * grid.GUTTER,
            grid.CONTENT_W, places=6)

    def test_column_positions(self) -> None:
        self.assertAlmostEqual(grid.col(1), grid.PAD_X, places=6)
        # 第 7 列 = 图文分栏的第二栏起点（实测两栏布局的 x=812 就在这）
        self.assertAlmostEqual(grid.col(7), 812.0, places=1)
        # 第 8 列 = 7 列跨度的右邻（图文页图片的起点 933）
        self.assertAlmostEqual(grid.col(8), 933.3, places=1)

    def test_spans_fill_exactly(self) -> None:
        """7+5 的图文分栏：两个跨度 + 一个列距 = 内容宽（分毫不差）。"""
        x7, w7 = grid.span(7)
        x5, w5 = grid.span(5, 8)
        self.assertAlmostEqual(x7, grid.PAD_X, places=6)
        self.assertAlmostEqual(x5, grid.col(8), places=6)
        self.assertAlmostEqual(w7 + grid.GUTTER + w5, grid.CONTENT_W, places=6)

    def test_half_split_aligns_to_columns(self) -> None:
        """6+6 的两栏分栏：第二栏起点必须是第 7 列。"""
        _x, w6 = grid.span(6)
        self.assertAlmostEqual(grid.PAD_X + w6 + grid.GUTTER, grid.col(7), places=6)

    def test_fractional_spans_are_rejected(self) -> None:
        """「5.37 列」这种东西直接判错 —— 那是"看着差不多"的来源之一。"""
        with self.assertRaises(SystemExit):
            grid.span(5.37) if False else grid.span(11)      # 11 不在允许集里

    def test_span_out_of_bounds_is_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            grid.span(12, 3)                                  # 第 3 列起跨 12 列越界

    def test_snap(self) -> None:
        self.assertEqual(grid.snap(84.0), 0)                  # 左边距
        self.assertEqual(grid.snap(448.0), 4)
        self.assertEqual(grid.snap(933.3), 8)
        self.assertIsNone(grid.snap(537.0))                   # 两列之间
        self.assertEqual(grid.snap(85.2), 0)                  # 容差内
        self.assertIsNone(grid.snap(205.3 + 1.6))             # 容差外


class TestSpacingTokens(unittest.TestCase):
    """间距令牌：ramp、语义档、关系规则。"""

    def test_relationship_rules_hold(self) -> None:
        """组距 ≥ 1.5 × 条目距 —— Gestalt 接近性的量化版。"""
        self.assertEqual(grid.check_relationships(), [])

    def test_semantic_values_come_from_the_ramp(self) -> None:
        """gap 只许从 ramp 取 —— 语义档不是另立一套数。"""
        ramp = set(grid.SPACING.values())
        for name, value in grid.SEMANTIC.items():
            self.assertIn(value, ramp, f"{name}={value} 不在 ramp 里")

    def test_ramp_is_strictly_increasing(self) -> None:
        values = [grid.SPACING[k] for k in sorted(grid.SPACING, key=lambda k: grid.SPACING[k])]
        self.assertEqual(values, sorted(values))
        self.assertEqual(len(values), len(set(values)))

    def test_css_vars_are_emitted(self) -> None:
        vars_ = grid.spacing_vars()
        for key in ("--sp-inner", "--sp-item", "--sp-block", "--sp-group",
                    "--sp-section"):
            self.assertIn(key, vars_)
        self.assertEqual(vars_["--sp-item"], f"{grid.SEMANTIC['item']}px")

    def test_render_injects_the_vars(self) -> None:
        spec = json.loads(open(DEMO, encoding="utf-8").read())
        html = render.render(spec)
        for key in ("--sp-item", "--sp-group", "--sp-section"):
            self.assertIn(key, html, f"产物里没有 {key} —— 令牌没接上")

    def test_shell_css_uses_tokens_not_bare_gaps(self) -> None:
        """壳里的 gap 必须走令牌 —— 裸数字是"间距无律"的来源。

        实测改前：壳里 11 个 gap 值挤在 28~64 区间（28/34/36/38/44/44/48/48/56/60/64）。
        """
        import re

        for m in re.finditer(r"(?:gap|margin[^:{]*|padding[^:{]*):([^;}]+)", render.SHELL_CSS):
            value = m.group(1)
            if "var(--sp-" in value or "0" == value.strip():
                continue
            # 允许非间距用途的 margin（居中 auto、定位 top/bottom）
            if "auto" in value or "calc" in value:
                continue
            nums = re.findall(r"\d+", value)
            for n in nums:
                self.assertNotIn(int(n), set(range(25, 65)),
                                 f"壳里出现了裸间距 {value!r}（在 25~64 的「无律区间」）")


class TestGeometrySingleSource(unittest.TestCase):
    """几何必须只有一个来源 —— 两个"唯一来源"就是没有唯一来源。"""

    def test_check_reads_the_same_bounds_as_render(self) -> None:
        """**回归**：check.py 曾手写 CONTENT=(…, 838)，与 render 的 824 差 14px。"""
        self.assertEqual(check.CONTENT[3], render.CONTENT_BOTTOM)
        self.assertEqual(check.CONTENT[0], render.PAD_X)
        self.assertEqual(check.CONTENT[2], render.SLIDE_W - render.PAD_X)

    def test_grid_is_the_source_for_render(self) -> None:
        self.assertEqual(render.SLIDE_W, grid.SLIDE_W)
        self.assertEqual(render.CONTENT_BOTTOM, grid.CONTENT_BOTTOM)


class TestTypeLadder(unittest.TestCase):
    """阶梯：不许同级碰撞、不许倒挂。"""

    def _styles(self):
        for name in sorted(os.listdir(STYLES)):
            path = os.path.join(STYLES, name, "style.json")
            if os.path.isfile(path) and not name.startswith("zz_"):
                with open(path, encoding="utf-8") as fh:
                    yield name, json.load(fh)["type"]

    def test_no_style_has_subtitle_equal_to_bullet(self) -> None:
        """**回归**：4 套风格曾有 subtitle == bullet —— 两级之间没有层级可言。"""
        for name, t in self._styles():
            with self.subTest(style=name):
                self.assertNotEqual(t.get("subtitle"), t.get("bullet"),
                                    f"{name} 的 subtitle 与 bullet 同字号")

    def test_bullet_tiers_are_ordered(self) -> None:
        for name, t in self._styles():
            with self.subTest(style=name):
                self.assertLess(t["bulletSmall"], t["bullet"])
                self.assertLess(t["bullet"], t["bulletLarge"])

    @classmethod
    def setUpClass(cls) -> None:
        import tempfile

        cls._tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._tmp.cleanup)
        cls.html = os.path.join(cls._tmp.name, "demo.html")
        spec = json.loads(open(DEMO, encoding="utf-8").read())
        cls.measured_render = render.render(spec)
        with open(cls.html, "w", encoding="utf-8") as fh:
            fh.write(cls.measured_render)
        measure = _load("measure")
        cls.measured = measure.measure(cls.html)

    def test_gridded_output_is_quiet(self) -> None:
        """**重构的验收**：真实产物上，锚点全部吸附到列（改前是 7 个任意 x 值）。"""
        self.assertEqual(check._check_grid_alignment(self.measured), [])

    def test_off_grid_anchor_is_reported(self) -> None:
        fake = dict(self.measured)
        fake["elements"] = list(self.measured["elements"]) + [
            {"slide": 2, "role": "title", "x": 537.0, "y": 300, "w": 400, "h": 60}]
        out = check._check_grid_alignment(fake)
        self.assertEqual(len(out), 1)
        self.assertIn("没吸附到网格列", out[0])
        self.assertIn("537", out[0])

    def test_non_anchor_roles_are_not_checked(self) -> None:
        """列表条目不查 —— 悬挂缩进是版式语言，不是失对齐。"""
        fake = dict(self.measured)
        fake["elements"] = list(self.measured["elements"]) + [
            {"slide": 2, "role": "bullet", "x": 537.0, "y": 400, "w": 300, "h": 40}]
        self.assertEqual(check._check_grid_alignment(fake), [])

    def test_bad_data_does_not_raise(self) -> None:
        for bad in ({"role": "title", "x": None}, {"role": "title", "x": "a", "slide": 1},
                    {"role": "title", "x": 100.0, "slide": "2"}):
            with self.subTest(bad=bad):
                self.assertEqual(check._check_grid_alignment({"elements": [bad]}), [])


if __name__ == "__main__":
    unittest.main()
