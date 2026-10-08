"""逐页截图回归：输入门、时间轴选页、2倍像素和非默认页间距。"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/deck-authoring/scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load(name: str):
    spec = importlib.util.spec_from_file_location("shots_regression_" + name,
                                                 SCRIPTS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


shots = load("shots")


class TestShotsInput(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "two-pages.html"
        self.output = self.root / "pages"
        self.source.write_text('<script>window.__deck_timeline=' + json.dumps([
            {"start": 0, "enter": 1, "hold": 3},
            {"start": 4, "enter": 1, "hold": 3},
        ]) + ';</script>', encoding="utf-8")

    def test_requesting_more_pages_than_exist_stops_before_browser(self):
        with patch.object(shots, "_capture_module") as capture:
            with self.assertRaisesRegex(SystemExit, "请求 3 页，但产物只有 2 页"):
                shots.shoot(str(self.source), str(self.output), 1600, 900, 3)
            capture.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_non_16_9_and_nonpositive_inputs_stop_before_browser(self):
        for width, height, count in ((1600, 1000, 2), (800, 600, 2),
                                     (0, 900, 2), (1600, -900, 2), (1600, 900, 0)):
            with self.subTest(width=width, height=height, count=count):
                with patch.object(shots, "_capture_module") as capture:
                    with self.assertRaisesRegex(SystemExit, "16:9"):
                        shots.shoot(str(self.source), str(self.output), width, height, count)
                    capture.assert_not_called()
        self.assertFalse(self.output.exists())


class TestShotsBrowser(unittest.TestCase):
    def test_two_pages_keep_order_at_2x_with_nonstandard_page_gap(self):
        """使用真实renderer/时间轴；173px页间距会让旧固定36px裁切路径错页。"""
        render = load("render")
        style_dir = FIXTURES / "styles/minimal-baseline"
        style = json.loads((style_dir / "style.json").read_text(encoding="utf-8"))
        spec = {"deck": {
            "style": str(style_dir), "colorSet": next(iter(style["colorSets"])),
            "seed": 1, "title": "Screenshot regression", "slides": [
                {"type": "title", "title": "11111111", "visual": {"kind": "none"}},
                {"type": "title", "title": "WWWWWWWW", "visual": {"kind": "none"}},
            ],
        }}
        html = render.render(spec)
        # 单纯改变滚动态的页间距；frame态仍由真正的演示壳将所选页显示在原点。
        custom_css = '''<style>
          .slide{margin-bottom:173px}
          .slide[data-slide="1"]{background:rgb(240,220,200)}
          .slide[data-slide="2"]{background:rgb(200,220,240)}
          .title{font-family:Arial,sans-serif!important;font-size:96px!important;color:#000!important}
        </style>'''
        html = html.replace("</head>", custom_css + "</head>")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "deck.html"
            source.write_text(html, encoding="utf-8")
            pages = shots.shoot(str(source), str(root / "pages"), 1600, 900, 2)
            self.assertEqual([Path(page).name for page in pages], ["page-01.png", "page-02.png"])
            text_masks = []
            for page, color in zip(pages, ((240, 220, 200), (200, 220, 240)), strict=True):
                with Image.open(page) as image:
                    self.assertEqual(image.size, (3200, 1800))
                    rgb = image.convert("RGB")
                    # 页中央与四周都应属于该页，没有页间距或相邻页被裁进来。
                    for point in ((1600, 1400), (3000, 100), (200, 1600)):
                        self.assertEqual(rgb.getpixel(point), color, (page, point))
                    title = rgb.crop((160, 200, 2900, 500))
                    ink = title.convert("L").point(lambda value: 255 if value < 80 else 0)
                    self.assertIsNotNone(ink.getbbox(), "标题文字必须完整入场后再截图")
                    text_masks.append(ink)
            self.assertIsNotNone(ImageChops.difference(*text_masks).getbbox(),
                                 "两页文字不同，不能两次都捕获同一页")
            # Arial的W比1宽；进一步验证文字顺序，避免只检查背景颜色。
            first_box, second_box = (mask.getbbox() for mask in text_masks)
            self.assertLess(first_box[2] - first_box[0], second_box[2] - second_box[0])


if __name__ == "__main__":
    unittest.main()
