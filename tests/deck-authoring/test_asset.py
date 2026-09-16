#!/usr/bin/env python3
"""资产管线（§12/§14）第一片的回归测试：manifest 契约 + assetId 解析。

规则口径：assetId 是**语义引用**，路径只在 resolved 里出现（manifest 即选择）；
缺文件由 check 的「图片加载」门实测拦 —— 联网找图禁止，静默造占位同样禁止。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/deck-authoring/test_asset.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
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


render = _load("render")
deck_mod = _load("deck")

MANIFEST = {"schemaVersion": 1, "assets": {
    "cover-photo": {"file": "generated/cover.png", "source": "generated"}}}


class TestLoadAssets(unittest.TestCase):
    """manifest 契约：schema 封闭，违规 = ERROR（不静默猜意图）。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = self._tmp.name
        os.makedirs(os.path.join(self.dir, "assets"), exist_ok=True)

    def _write(self, data) -> str:
        path = os.path.join(self.dir, "assets", "manifest.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
        return path

    def test_no_manifest_is_none(self) -> None:
        """没有 manifest → None：image 走旧的相对路径语义（全兼容）。"""
        self.assertIsNone(render.load_assets_at(self.dir))

    def test_valid_manifest_loads(self) -> None:
        self._write(MANIFEST)
        self.assertEqual(render.load_assets_at(self.dir), MANIFEST)

    def test_unknown_top_key_rejected(self) -> None:
        self._write({**MANIFEST, "extra": 1})
        with self.assertRaises(SystemExit):
            render.load_assets_at(self.dir)

    def test_wrong_schema_version_rejected(self) -> None:
        self._write({**MANIFEST, "schemaVersion": 2})
        with self.assertRaises(SystemExit):
            render.load_assets_at(self.dir)

    def test_unknown_entry_key_rejected(self) -> None:
        self._write({"schemaVersion": 1, "assets": {"x": {"file": "a.png", "width": 9}}})
        with self.assertRaises(SystemExit):
            render.load_assets_at(self.dir)

    def test_entry_without_file_rejected(self) -> None:
        self._write({"schemaVersion": 1, "assets": {"x": {"source": "generated"}}})
        with self.assertRaises(SystemExit):
            render.load_assets_at(self.dir)


class TestResolveAsset(unittest.TestCase):
    def test_id_in_manifest_maps_to_path(self) -> None:
        self.assertEqual(render.resolve_asset(MANIFEST, "cover-photo"),
                         "assets/generated/cover.png")

    def test_unknown_id_is_none(self) -> None:
        self.assertIsNone(render.resolve_asset(MANIFEST, "direct.png"))
        self.assertIsNone(render.resolve_asset(None, "cover-photo"))


class TestCompileResolvesAssetIds(unittest.TestCase):
    """compile 是唯一的 assetId → 路径决策点（页对象携带最终路径 + trace）。"""

    def _spec(self, image: str) -> dict:
        with open(DEMO, encoding="utf-8") as fh:
            spec = json.load(fh)
        spec["deck"]["slides"] = [
            {"type": "content-image", "title": "图页", "bullets": ["a"], "image": image}]
        return spec

    def test_asset_id_resolved_and_traced(self) -> None:
        resolved = deck_mod.compile_spec(self._spec("cover-photo"), assets=MANIFEST)
        page = resolved["deck"]["slides"][0]
        self.assertEqual(page["image"], "assets/generated/cover.png")
        # demo 带品牌 → trace 里还有一条 logo 的 asset 记录；按决策内容挑
        entry = next(t for t in resolved["trace"]
                     if t["stage"] == "asset" and "cover-photo" in t["decision"])
        self.assertIn("cover-photo → assets/generated/cover.png", entry["decision"])
        self.assertIn("source=generated", "".join(entry["reason"]))

    def test_plain_path_untouched(self) -> None:
        resolved = deck_mod.compile_spec(self._spec("photo.png"), assets=MANIFEST)
        self.assertEqual(resolved["deck"]["slides"][0]["image"], "photo.png")

    def test_without_assets_behaves_as_before(self) -> None:
        resolved = deck_mod.compile_spec(self._spec("photo.png"))
        self.assertEqual(resolved["deck"]["slides"][0]["image"], "photo.png")

    def test_render_emits_resolved_src(self) -> None:
        html = render.render(self._spec("cover-photo"), assets=MANIFEST)
        self.assertIn('src="assets/generated/cover.png"', html)
        self.assertNotIn('src="cover-photo"', html, "assetId 漏进了产物")


