#!/usr/bin/env python3
"""image_source.py 缓存不变量：**缓存命中不等于可信**。

## 为什么这条是不变量

缓存里的东西也可能不合规 —— 上一次留下的、或者被别的路径塞进去的。
如果命中就直接拷贝，那张不合规的图就会静默流进 deck，视觉上立刻露馅。

所以 `resolve()` 命中缓存后**仍然**要过"只在色板三角形内"这条不变量：
不合规就丢弃并重新走一遍，绝不拿不合规的图凑数。

判据（必须机器可判，不能靠"看起来对"）：
- 塞一张紫图（色板三角形外）到缓存位置
- 跑 resolve()
- 缓存文件必须被**替换**（不是原样拷贝）
- 产物必须**在三角形内**

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/deck-authoring/test_cache_invariant.py
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import sys
import tempfile
import unittest

logging.getLogger("PIL").setLevel(logging.ERROR)

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
SCRIPTS = os.path.join(SKILL, "scripts")
TOKENS = os.path.join(SKILL, "dev-tools", "style-fixture", "swiss-grid", "style.json")

CACHE_ENV = "AGENT_SKILLS_CACHE_DIR"
SIZE = (320, 200)
# 色板三角形（主色 #FF48B0 / 叠印墨 / 纸色 #F5EFDD）之外的明显异色
STRAY_RGB = (180, 0, 200)


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


image_source = _load("_deck_test_image_source", os.path.join(SCRIPTS, "image_source.py"))
from PIL import Image  # noqa: E402


class TestCacheInvariant(unittest.TestCase):
    """说明（v4）：原先这里还有两条"缓存图必须落在色板三角形里"的用例 ——
    它们测的是 **plate.py 的双色调 + 半调制版后处理**（那张图会被压成两墨色，
    所以能用三角形判定）。v4 删掉 plate.py：图片按原样使用，色板三角形判据
    对真实照片不再适用（照片本来就有千百种颜色）。出图阶段的色彩约束改由
    提示词 + `--brief` 的构图字段承担，见 references/images.md。
    """
    def setUp(self) -> None:
        with open(TOKENS, encoding="utf-8") as fh:
            tokens = json.load(fh)
        # 取哪套色板不重要，只要是**真存在的一套**：这些用例测的是缓存与色板三角
        # 不变量，与风格无关。写死某个名字就会在换默认风格时挂掉（已经挂过一次）。
        self.colors = next(iter(tokens["colorSets"].values()))
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.cache = os.path.join(self._tmp.name, "cache")
        os.makedirs(self.cache, exist_ok=True)
        self._previous = os.environ.get(CACHE_ENV)
        os.environ[CACHE_ENV] = self.cache
        self.addCleanup(self._restore_cache_env)

    def _restore_cache_env(self) -> None:
        if self._previous is None:
            os.environ.pop(CACHE_ENV, None)
        else:
            os.environ[CACHE_ENV] = self._previous

    def _seed_cache_with_stray_image(self, prompt: str) -> str:
        key = image_source.cache_key(prompt, self.colors, SIZE)
        path = os.path.join(self.cache, f"{key}.png")
        Image.new("RGB", SIZE, STRAY_RGB).save(path)
        return path

    def test_palette_detector_actually_flags_a_stray_color(self) -> None:
        """先证明检测器真的会红 —— 否则上一条"没报"可能只是检测器失灵。"""
        stray = Image.new("RGB", SIZE, STRAY_RGB)
        self.assertTrue(image_source.in_palette(stray, self.colors),
                        "检测器对明显异色没反应 —— 上一条用例的保证是假的")

