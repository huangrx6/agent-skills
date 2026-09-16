#!/usr/bin/env python3
"""image_source.py 的缓存不变量：**命中即可信，且不重跑 provider**。

## 为什么这条是不变量

`cache_key` 里含 **prompt + 色板 + 尺寸** —— 同一把 key 就是同一张图。所以命中缓存
就该直接复用：缓存里的东西是我们自己上一步写进去的，而重新走一遍意味着**再花一次
生图的钱买同一张图**（用户在 `--provider-cmd` 上配的是真 API）。

判据（必须机器可判，不能靠"看起来对"）：

- 先把一张图塞进缓存位置，再 `resolve()`，同时给一个**会留下痕迹的 provider 命令**
- provider 命令**必须没被执行**（痕迹文件不存在）
- 产物必须与缓存里那张**逐字节相同**

## 这里删掉过一条判据

原先还有"缓存图必须落在色板三角形内"这道门（不合规就丢弃重做）。它量的是
`plate.py` 时代的双色调制版产物 —— v4 删掉制版、图片按原样使用之后，真照片
**本来就有千百种颜色**，这道门只会把好图判死（实测：provider 出的图永远"不合规"，
于是每次都重调 API，缓存形同不存在）。色彩约束改由 `--brief` 的提示词承担，
见 `references/images.md`。

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
TOKENS = os.path.join(FIXTURES_DIR, "styles", "swiss-grid", "style.json")

CACHE_ENV = "AGENT_SKILLS_CACHE_DIR"
SIZE = (320, 200)
CACHED_RGB = (255, 72, 176)


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
    def setUp(self) -> None:
        with open(TOKENS, encoding="utf-8") as fh:
            tokens = json.load(fh)
        # 取哪套色板不重要，只要是**真存在的一套**：这些用例测的是缓存与 key，
        # 与风格无关。写死某个名字就会在换默认风格时挂掉（已经挂过一次）。
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

    def _seed_cache(self, prompt: str) -> str:
        key = image_source.cache_key(prompt, self.colors, SIZE)
        path = os.path.join(self.cache, f"{key}.png")
        Image.new("RGB", SIZE, CACHED_RGB).save(path)
        return path

    def test_cache_hit_reuses_the_image_without_calling_the_provider(self) -> None:
        """命中缓存 = 同一把 key = 同一张图，不该再花一次生图的钱。"""
        marker = os.path.join(self._tmp.name, "provider-was-called")
        cached = self._seed_cache("同一个 prompt")
        out = os.path.join(self._tmp.name, "out.png")
        source = image_source.resolve("同一个 prompt", self.colors, SIZE, out,
                                      provider_cmd=f"touch {marker}")
        self.assertEqual(source, "cache")
        self.assertFalse(os.path.exists(marker),
                         "命中缓存还去调了 provider —— 那是付第二次钱买同一张图")
        with open(cached, "rb") as fh:
            seeded = fh.read()
        with open(out, "rb") as fh:
            self.assertEqual(fh.read(), seeded, "命中缓存应当直接复用那张图")

    def test_cache_key_separates_prompt_palette_and_size(self) -> None:
        """三个输入里改任何一个，都必须换一把 key —— 否则会拿到别人的图。"""
        other_palette = dict(self.colors)
        other_palette["primary"] = "#00FF00"
        keys = {
            image_source.cache_key("A", self.colors, SIZE),
            image_source.cache_key("B", self.colors, SIZE),
            image_source.cache_key("A", other_palette, SIZE),
            image_source.cache_key("A", self.colors, (640, 400)),
        }
        self.assertEqual(len(keys), 4, f"key 没把输入分开：{keys}")

    def test_cache_key_is_stable_for_the_same_inputs(self) -> None:
        """同输入同 key（跨进程也要一致：key 由内容算，不掺进程盐）。"""
        first = image_source.cache_key("A", self.colors, SIZE)
        second = image_source.cache_key("A", dict(self.colors), SIZE)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
