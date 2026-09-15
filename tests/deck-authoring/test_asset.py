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
SCRIPTS = os.path.join(SKILL, "scripts")
DEMO = os.path.join(SKILL, "dev-tools", "demo.spec.json")


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
compile_mod = _load("compile")
fit = _load("fit")

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
        resolved = compile_mod.compile_spec(self._spec("cover-photo"), assets=MANIFEST)
        page = resolved["deck"]["slides"][0]
        self.assertEqual(page["image"], "assets/generated/cover.png")
        # demo 带品牌 → trace 里还有一条 logo 的 asset 记录；按决策内容挑
        entry = next(t for t in resolved["trace"]
                     if t["stage"] == "asset" and "cover-photo" in t["decision"])
        self.assertIn("cover-photo → assets/generated/cover.png", entry["decision"])
        self.assertIn("source=generated", "".join(entry["reason"]))

    def test_plain_path_untouched(self) -> None:
        resolved = compile_mod.compile_spec(self._spec("photo.png"), assets=MANIFEST)
        self.assertEqual(resolved["deck"]["slides"][0]["image"], "photo.png")

    def test_without_assets_behaves_as_before(self) -> None:
        resolved = compile_mod.compile_spec(self._spec("photo.png"))
        self.assertEqual(resolved["deck"]["slides"][0]["image"], "photo.png")

    def test_render_emits_resolved_src(self) -> None:
        html = render.render(self._spec("cover-photo"), assets=MANIFEST)
        self.assertIn('src="assets/generated/cover.png"', html)
        self.assertNotIn('src="cover-photo"', html, "assetId 漏进了产物")


class TestFitProbeKnowsManifest(unittest.TestCase):
    """变体探针也认 manifest：assetId 页能实测（真图路径解析对了）。"""

    def test_probe_resolves_asset_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            assets_dir = os.path.join(tmp, "assets")
            os.makedirs(os.path.join(assets_dir, "generated"), exist_ok=True)
            with open(os.path.join(assets_dir, "manifest.json"), "w",
                      encoding="utf-8") as fh:
                json.dump(MANIFEST, fh)
            # 探针要真图（高宽比是变体选择的真实输入）—— 造一张
            import zlib
            w, h = 400, 300
            raw = b"".join(b"\x00" + bytes((90, 90, 160)) * w for _ in range(h))

            def chunk(tag: bytes, data: bytes) -> bytes:
                head = tag + data
                return (len(data).to_bytes(4, "big") + head
                        + (zlib.crc32(head) & 0xFFFFFFFF).to_bytes(4, "big"))

            with open(os.path.join(assets_dir, "generated", "cover.png"), "wb") as fh:
                fh.write(b"\x89PNG\r\n\x1a\n"
                         + chunk(b"IHDR", w.to_bytes(4, "big")
                                 + h.to_bytes(4, "big") + b"\x08\x02\x00\x00\x00")
                         + chunk(b"IDAT", zlib.compress(raw))
                         + chunk(b"IEND", b""))
            spec = {"deck": {"slides": [
                {"type": "content-image", "title": "t", "bullets": ["a"],
                 "image": "cover-photo"}]}}
            probe, _labels = fit.build_variant_probe(spec, tmp)
            self.assertEqual(probe["deck"]["slides"][0]["image"],
                             os.path.join(tmp, "assets", "generated", "cover.png"))


if __name__ == "__main__":
    unittest.main()
