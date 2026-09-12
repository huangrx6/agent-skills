#!/usr/bin/env python3
"""dev-tools/preview.py 里**纯几何**那部分的测试。

为什么单独一个文件：`preview.py` 不是运行时的一部分（它需要 PIL），所以不值得给它
写渲染测试。但它里面有一处几何计算**是真错过一次的**，而且那个错很难发现 ——

> 第一版用 `x + width` 算所有元素的包围盒。对箭头这是错的：Excalidraw 的线性元素
> `x`/`y` 是**首点**而不是包围盒左上角，折线点可以是负的（回边就是）
> → 算出的范围比真实内容大 744px，渲染出来右侧一大片空白。

发现它的方式很典型：先用自己写的渲染器看图，看到一片空白，**先怀疑的是图而不是工具**；
直到拿 Excalidraw 官方的 `getCommonBounds` 对比，才发现真正在骗人的是我的渲染器。
所以这条几何值得钉住 —— 目视工具自己有偏差时，你看到的是偏差，不是图。

这一层不 import PIL（`preview.py` 把 PIL 放在函数里惰性 import），所以这些用例
在没有 PIL 的环境下也能跑。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/test_preview_bounds.py
"""

from __future__ import annotations

import importlib.util
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
PREVIEW = os.path.join(SKILL, "dev-tools", "preview.py")


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


P = _load("preview", PREVIEW)


def rect(x, y, w, h):
    return {"id": "r", "type": "rectangle", "x": x, "y": y, "width": w, "height": h}


class TestElementBounds(unittest.TestCase):
    def test_rectangle_uses_x_and_width(self):
        self.assertEqual((10.0, 20.0, 110.0, 80.0), P.element_bounds(rect(10, 20, 100, 60)))

    def test_linear_element_uses_points_not_x_plus_width(self):
        """**这就是那个真错过的 bug。**

        回边：`x` = 首点（右端），点是负的，`width` 是跨度。用 `x + width` 会把它算到
        744px 之外 —— 真实右缘是点的最大值，不是 `x + width`。
        """
        back = {"id": "e", "type": "arrow", "x": 1248.0, "y": 100.0,
                "width": 744.0, "height": 50.0,
                "points": [[0, 0], [-372, 140], [-744, 60]]}
        left, top, right, bottom = P.element_bounds(back)
        self.assertEqual(504.0, left, "左缘应是点的最小值")
        self.assertEqual(1248.0, right, "右缘应是点的最大值，而不是 x + width")
        self.assertNotEqual(1992.0, right, "x + width 正是那个错的算法")

    def test_linear_element_without_points_falls_back(self):
        """退化：没有 points 就按普通元素算，不抛异常。"""
        weird = {"id": "e", "type": "arrow", "x": 5.0, "y": 6.0, "width": 7.0, "height": 8.0}
        self.assertEqual((5.0, 6.0, 12.0, 14.0), P.element_bounds(weird))

    def test_scene_bounds_ignores_negative_point_offsets(self):
        elements = [rect(0, 0, 100, 50),
                    {"id": "e", "type": "arrow", "x": 100.0, "y": 25.0,
                     "width": 60.0, "height": 40.0,
                     "points": [[0, 0], [-60, 40]]}]
        left, top, right, bottom = P.scene_bounds(elements)
        self.assertEqual((0.0, 0.0, 100.0, 65.0), (left, top, right, bottom))

    def test_bounds_match_excalidraw_convention(self):
        """把这条性质写清楚：线性元素的 x 可以大于右缘（点向左伸）。"""
        back = {"id": "e", "type": "arrow", "x": 500.0, "y": 0.0,
                "width": 300.0, "height": 10.0, "points": [[0, 0], [-300, 10]]}
        left, _, right, _ = P.element_bounds(back)
        self.assertEqual(200.0, left)
        self.assertEqual(500.0, right)
        self.assertGreater(back["x"], right - 1, "x 是首点，不是包围盒左缘")


class TestNoRuntimeDependency(unittest.TestCase):
    def test_module_imports_without_pil(self):
        """加载这个模块本身不该需要 PIL —— 否则 dev-tools 就变成了运行时依赖的一部分。

        PIL 是在 `render()` 里惰性 import 的，所以模块级不该有它。
        """
        self.assertTrue(hasattr(P, "element_bounds"))
        self.assertFalse(hasattr(P, "Image"), "PIL 被挪到模块级了 —— 那就成了运行时依赖")
        self.assertFalse(hasattr(P, "ImageDraw"))

    def test_preview_is_outside_scripts_dir(self):
        """放在 dev-tools/ 而不是 scripts/ —— 这条把“核心链路零依赖”钉住。"""
        self.assertNotIn(os.sep + "scripts" + os.sep, PREVIEW)


if __name__ == "__main__":
    unittest.main(verbosity=2)
