#!/usr/bin/env python3
"""内置语义 sigil 的回归：目录完整性、未知名不 fallback、零素材库可用、宽度进尺寸链。"""

from __future__ import annotations

import importlib.util
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills",
                       os.path.basename(HERE), "scripts")


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SIG = _load("sigils", os.path.join(SCRIPTS, "sigils.py"))
E = _load("emit_excalidraw", os.path.join(SCRIPTS, "emit_excalidraw.py"))
L = E.L


def spec_of(nodes, edges, **extra):
    base = {"type": "architecture",
            "nodes": [{"id": n, "label": n, "kind": "service"} for n in nodes],
            "edges": [{"from": a, "to": b} for a, b in edges]}
    base.update(extra)
    return base


class TestBuiltinSigils(unittest.TestCase):

    def test_catalog_and_aliases(self):
        for name in ("user", "database", "queue", "shield", "api"):
            self.assertTrue(SIG.is_builtin(name))
        self.assertTrue(SIG.is_builtin("client"))       # 别名
        self.assertFalse(SIG.is_builtin("不存在的名字"))

    def test_glyph_unknown_raises(self):
        with self.assertRaises(KeyError):
            SIG.glyph("不存在的名字", "#000000")

    def test_all_glyphs_have_geometry(self):
        for name in sorted(SIG.NAMES):
            els = SIG.glyph(name, "#000000")
            self.assertTrue(els)
            for el in els:
                self.assertIn(el["type"], ("line", "ellipse", "rectangle"))

    def test_builtin_icon_needs_no_library(self):
        """全部图标都是内置名时，load_icons 完全不接触素材库路径。"""
        spec = spec_of(["a", "b"], [("a", "b")])
        spec["nodes"][0]["icon"] = "database"
        spec["nodes"][1]["icon"] = "api"
        old = os.environ.pop("EXCALIDRAW_LIBRARY", None)
        try:
            lookup, sizes, _heights = E.load_icons(spec)
            self.assertIsNotNone(lookup)
            self.assertIn("database", lookup)
            self.assertIn("a", sizes, "内置图标也要进尺寸链（盒子加宽）")
        finally:
            if old is not None:
                os.environ["EXCALIDRAW_LIBRARY"] = old

    def test_sigil_widens_the_node_box(self):
        plain = L.boxes_from_spec(spec_of(["a"], []))["a"]
        with_icon = dict(spec_of(["a"], []))
        with_icon["nodes"][0]["icon"] = "database"
        got = L.boxes_from_spec(with_icon, {"a": (24.0, 24.0)})["a"]
        self.assertGreater(got.width, plain.width,
                           "图标（含内置 sigil）是外部尺寸来源，必须加宽盒子")


if __name__ == "__main__":
    unittest.main()
