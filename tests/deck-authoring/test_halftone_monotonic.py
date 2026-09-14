#!/usr/bin/env python3
"""plate.py 半调渐变测试：墨覆盖率随灰度**单调**（100% → 0%）。

## 为什么这条是不变量（两次真实踩坑）

1. 第一版写成 `if v < 128: 每个像素都打点 else 棋盘格` —— 结果是"暗处实心、
   128 以上密度全都一样"，等于没有连续调（实测：光 / 中调区域平滑无网点）。
2. 第二版把 `dots` 倍放大的 mask 又 LANCZOS 缩回原尺寸 —— 网点被平均成平滑色块
   （实测光 / 中调区域 100px 内只有 1~3 段颜色）。

两次都不是"崩了"，是"看起来还行但密度曲线是平的"。只有把**单调性**写成断言
才抓得住。现在的实现用 Bayer 4×4 矩阵逐子像素比较，16 级密度，曲线是线性的。

判据：数最终产物里**恰好等于主色**的像素比例。
等于主色 = 那一格被半调"打点"了 —— gradient 永远介于 overprint ↔ paper 之间，
不会恰好等于主色，所以这个数就是半调覆盖率本身。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/deck-authoring/test_halftone_monotonic.py
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
import unittest

logging.getLogger("PIL").setLevel(logging.ERROR)

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
SCRIPTS = os.path.join(SKILL, "scripts")

PRIMARY, SECONDARY, PAPER = "#00A8E8", "#FF48B0", "#F5EFDD"
SIZE = (64, 64)
LEVELS = [0, 32, 64, 96, 128, 160, 192, 224, 255]


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


plate = _load("_deck_test_plate", os.path.join(SCRIPTS, "plate.py"))
from PIL import Image  # noqa: E402


class TestHalftoneMonotonic(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.primary_rgb = plate._rgb(PRIMARY)

    def _coverage(self, gray: int) -> float:
        image = Image.new("L", SIZE, gray)
        treated = plate.duotone(image, PRIMARY, SECONDARY, PAPER, dots=4)
        pixels = treated.load()
        width, height = SIZE
        hits = sum(1 for y in range(height) for x in range(width)
                   if pixels[x, y] == self.primary_rgb)
        return hits / (width * height)

    def test_coverage_endpoints_are_full_and_empty(self) -> None:
        """gray=0 必须打满点；gray=255 必须一个点都不打。"""
        self.assertGreaterEqual(self._coverage(0), 0.99,
                                "纯黑没有打满点 —— 半调阈值矩阵失效")
        self.assertLessEqual(self._coverage(255), 0.01,
                             "纯白竟然打了点 —— 半调阈值矩阵失效")

    def test_coverage_decreases_monotonically_with_gray(self) -> None:
        """覆盖率随灰度单调不增 —— 密度连续变化，不是"实心 + 棋盘格"。"""
        coverages = [self._coverage(g) for g in LEVELS]
        for index in range(len(coverages) - 1):
            self.assertLessEqual(
                coverages[index + 1], coverages[index] + 1e-9,
                f"gray={LEVELS[index + 1]} 覆盖率 {coverages[index + 1]:.3f} > "
                f"gray={LEVELS[index]} 的 {coverages[index]:.3f} —— 密度曲线不是单调的\n"
                f"实测曲线：{coverages}")


if __name__ == "__main__":
    unittest.main()
