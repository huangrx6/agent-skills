"""形状层：`kind` → 形状的默认映射、`shape` 的显式覆盖、以及**形状几何**。

这个模块的存在理由不是好看：形状决定盒子要多大，而盒子决定布局。
所以这里的断言分两类 ——
  · 枚举类：封闭、未知值判失败不 fallback（和 `kind` 同一条规矩）
  · 几何类：`box_for` 与 `text_area` 互为逆运算、盒子一定装得下文字
"""
import importlib.util
import math
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
# 测试住在仓库顶层 `tests/<skill>/`（**刻意不在 skill 目录里**：AI 调用 skill 时读的是
# `skills/<skill>/` 那棵树，测试放在里面会被顺手读进去）。
# 所以从 `tests/<skill>/` 往上两级到仓库根，再进 `skills/<skill>/`。
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
SCRIPTS = os.path.join(SKILL, "scripts")


def _load(name):
    """按文件路径加载脚本（`scripts/` 不是包）。

    注意顺序：**先注册进 `sys.modules` 再 exec** —— 否则 `@dataclass` 会去
    `sys.modules[cls.__module__]` 找不到而炸。这个坑踩过一次。
    """
    path = os.path.join(SCRIPTS, name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


sh = _load("shapes")
palette = _load("palette")


def inside_capsule(px, py, width, height):
    """点是否在胶囊内部 —— 直接用定义算，不调用被测函数。

    胶囊 = 宽 `width - height` 的矩形 + 两端半径 `height/2` 的半圆。
    所以给定纵向偏移 y，横向能到的最远处是 center_x ± (w/2 - r + √(r² - y²))。
    """
    r = height / 2.0
    if abs(py) > r:
        return False
    return abs(px) <= width / 2.0 - r + math.sqrt(max(0.0, r * r - py * py))


class TestShapeEnum(unittest.TestCase):
    def test_shape_names_are_a_closed_enum(self):
        self.assertEqual(
            {"rect", "round", "capsule", "ellipse", "diamond", "cylinder", "note"},
            set(sh.SHAPES))

    def test_every_shape_declares_name_type_and_roundness(self):
        for name, entry in sh.SHAPES.items():
            with self.subTest(shape=name):
                for field in ("zh", "excalidraw", "roundness", "text_fit"):
                    self.assertIn(field, entry)

    def test_excalidraw_types_are_only_the_three_it_knows(self):
        types = {entry["excalidraw"] for entry in sh.SHAPES.values()}
        self.assertLessEqual(types, {"rectangle", "ellipse", "diamond"})

    def test_unknown_shape_fails_without_fallback(self):
        """未知值判失败，**不回退到 round** —— 回退上一眼看不出来。"""
        with self.assertRaises(KeyError) as ctx:
            sh.resolve({"id": "a", "kind": "service", "label": "x", "shape": "star"})
        message = str(ctx.exception)
        self.assertIn("star", message)
        for allowed in sh.SHAPES:
            self.assertIn(allowed, message, "报错要列出允许值")

    def test_every_kind_has_a_resolvable_default_shape(self):
        """色板的每个 `kind` 都必须能落到一个形状上 —— 否则那条 kind 一用就炸。"""
        for kind in palette.KINDS:
            with self.subTest(kind=kind):
                self.assertEqual(sh.DEFAULT_SHAPE_FOR_KIND.get(kind) is not None, True,
                                 f"{kind} 没有默认形状；新加 kind 时要同时加默认形状")
                self.assertIn(sh.DEFAULT_SHAPE_FOR_KIND[kind], sh.SHAPES)

    def test_no_default_shape_points_at_an_unknown_kind(self):
        self.assertLessEqual(set(sh.DEFAULT_SHAPE_FOR_KIND), set(palette.KINDS))

    def test_explicit_shape_beats_the_kind_default(self):
        node = {"id": "a", "kind": "data", "label": "判断？", "shape": "diamond"}
        self.assertEqual("diamond", sh.resolve(node))
        del node["shape"]
        self.assertEqual("cylinder", sh.resolve(node), "不写 shape 时才用 kind 默认")


class TestShapeGeometry(unittest.TestCase):
    """`box_for` 与 `text_area` 必须互为逆运算，且盒子一定装得下文字。"""

    SAMPLES = ((20.0, 20.0), (48.0, 20.0), (100.0, 40.0), (272.0, 44.0), (400.0, 80.0))

    def test_box_for_and_text_area_are_inverses(self):
        for name in sh.SHAPES:
            for tw, th in self.SAMPLES:
                with self.subTest(shape=name, text=(tw, th)):
                    w, h = sh.box_for(name, tw, th)
                    back_w, back_h = sh.text_area(name, w, h)
                    self.assertAlmostEqual(tw, back_w, places=6)
                    self.assertAlmostEqual(th, back_h, places=6)

    def test_box_never_shrinks_text(self):
        """盒子只会比文字大 —— 估窄会让容器装不下，Excalidraw 自己换行撑高，整个布局偏移。"""
        for name in sh.SHAPES:
            for tw, th in self.SAMPLES:
                with self.subTest(shape=name, text=(tw, th)):
                    w, h = sh.box_for(name, tw, th)
                    self.assertGreaterEqual(w + 1e-9, tw)
                    self.assertGreaterEqual(h + 1e-9, th)

    def test_rect_and_note_do_not_inflate(self):
        for name in ("rect", "note"):
            with self.subTest(shape=name):
                self.assertEqual((100.0, 40.0), sh.box_for(name, 100.0, 40.0))

    def test_diamond_needs_twice_the_width_and_height(self):
        """菱形里能放下文字的只有它的**内接矩形** —— 一半宽、一半高。

        所以 120×20 的文字必须塞进 240×40 的菱形。不是审美选择，是几何。
        """
        w, h = sh.box_for("diamond", 120.0, 20.0)
        self.assertAlmostEqual(240.0, w, places=6)
        self.assertAlmostEqual(40.0, h, places=6)

    def test_ellipse_is_root_two(self):
        w, h = sh.box_for("ellipse", 120.0, 20.0)
        self.assertAlmostEqual(120.0 * math.sqrt(2.0), w, places=6)
        self.assertAlmostEqual(20.0 * math.sqrt(2.0), h, places=6)

    def test_capsule_text_corners_are_inside_the_shape(self):
        """用胶囊的**定义**验证，不用被测函数验证自己。

        文字的四角是 (±tw/2, ±th/2)。胶囊里纵向偏移越靠边，横向能用的地方越窄 ——
        两端弧线真正侵占的就是那个差值。四角必须都在里面。
        """
        for tw, th in self.SAMPLES:
            with self.subTest(text=(tw, th)):
                w, h = sh.box_for("capsule", tw, th)
                for sx in (-1, 1):
                    for sy in (-1, 1):
                        self.assertTrue(
                            inside_capsule(sx * tw / 2.0, sy * th / 2.0, w, h),
                            f"{tw}×{th} 的角 ({sx * tw / 2},{sy * th / 2}) "
                            f"落在 {w:.1f}×{h:.1f} 的胶囊外面")

    def test_capsule_inflation_is_small_this_is_a_regression_pin(self):
        """钉住一次实测出来的判断错误。

        第一版写的是“宽度 += 高度”，按“两端半圆各占一个半径”拍的 —— 46px。
        按几何算真正侵入的只有 r − √(r² − (h/2)²)，约 2~3px。
        多出来的 44px 不是审美问题：盒子变大就会挤掉布局余地
        （实测加完形状后网状图开始出现“连线穿过节点”）。
        """
        tw, th = 120.0, 20.0
        w, h = sh.box_for("capsule", tw, th)
        self.assertLess(w - tw, h * 0.5,
                        f"胶囊左右一共多占了 {w - tw:.1f}px —— "
                        f"又回到“按半径拍”的估法了？")
        self.assertLess(h - th, th, "胶囊上下不该多占一个文字高度")

    def test_capsule_intrusion_matches_its_own_definition(self):
        """`capsule_intrusion` 的返回值必须等于“角点刚好贴住弧线”时的偏移量。"""
        for th in (12.0, 20.0, 40.0):
            with self.subTest(text_height=th):
                r = th  # 盒子高度 = 文字高 + 呼吸量，这里直接取一个半径试
                got = sh.capsule_intrusion(r, th)
                want = r - math.sqrt(max(0.0, r * r - (th / 2.0) ** 2))
                self.assertAlmostEqual(want, got, places=9)

    def test_cylinder_cap_is_bounded_and_leaves_room_for_text(self):
        for tw, th in self.SAMPLES:
            with self.subTest(text=(tw, th)):
                w, h = sh.box_for("cylinder", tw, th)
                cap = sh.cylinder_cap(w)
                self.assertLessEqual(cap, sh.CYLINDER_CAP_MAX + 1e-9)
                self.assertAlmostEqual(th, h - cap, places=6,
                                       msg="圆柱体部分的高度必须正好装下文字")

    def test_cylinder_cap_grows_with_width_then_stops(self):
        self.assertLess(sh.cylinder_cap(80.0), sh.cylinder_cap(160.0))
        self.assertEqual(sh.cylinder_cap(400.0), sh.cylinder_cap(2000.0),
                         "太宽的盒子不该把盖子也拉得巨厚")


if __name__ == "__main__":
    unittest.main()
