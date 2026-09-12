#!/usr/bin/env python3
"""theme_preview.py 的回归测试。

这个脚本存在的理由是"让用户在出图前挑主题"，所以它自己的产物**必须是对的** ——
一个看起来正常但打不开的对照图，比没有更糟（用户会以为自己不喜欢那些主题）。

下面的 id 用例来自一个真实缺陷：三个面板走同一个 `emit()`，节点 id 完全相同，
Excalidraw 里会互相覆盖 —— 脚本照常打印"已写出"，打开却只看到一个面板。
"""

from __future__ import annotations

import importlib.util
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")


def _load(name: str, filename: str):
    path = os.path.join(SCRIPTS, filename)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


TP = _load("theme_preview_under_test", "theme_preview.py")


class TestThemePreview(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.scene = TP.build()

    def test_it_draws_every_theme(self):
        palette = TP._load("palette")
        for theme in palette.available_themes():
            with self.subTest(theme=theme):
                self.assertTrue(any(e["id"].startswith(f"panel-bg-{theme}")
                                    for e in self.scene["elements"]),
                                f"{theme} 的面板没画出来")

    def test_element_ids_are_unique_across_panels(self):
        """三个面板共用同一份节点 id，不隔离就会互相覆盖。"""
        ids = [e["id"] for e in self.scene["elements"]]
        self.assertEqual(len(ids), len(set(ids)), "有重复的元素 id")

    def test_no_dangling_references(self):
        """id 加了前缀之后，**内部引用也必须跟着改**，少改一处就是悬空引用。"""
        known = {e["id"] for e in self.scene["elements"]}
        for element in self.scene["elements"]:
            with self.subTest(element=element["id"]):
                if element.get("containerId"):
                    self.assertIn(element["containerId"], known)
                for item in (element.get("boundElements") or []):
                    self.assertIn(item["id"], known)
                for key in ("startBinding", "endBinding"):
                    binding = element.get(key)
                    if binding and binding.get("elementId"):
                        self.assertIn(binding["elementId"], known)

    def test_it_uses_the_palette_theme_names(self):
        """主题名以 `THEMES` 为准 —— 别的地方再抄一份就会漂移（这个坑踩过）。"""
        palette = TP._load("palette")
        self.assertEqual(sorted(palette.available_themes()),
                         sorted(palette.THEMES))


if __name__ == "__main__":
    unittest.main()
