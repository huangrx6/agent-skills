#!/usr/bin/env python3
"""PDF 导出层的验证 —— 验的是**产物**，不是"命令跑完了"。

## 为什么这层要单独测

`chrome --print-to-pdf` 一行就能出 PDF，而且**几乎总是"成功"**。所以"跑通了"什么
都证明不了：页数可能不对（分页被撑破的元素推歪）、页尺寸可能是 Letter（`@page` 没写，
deck 被缩小加留白）、内容可能整页退化成位图。这三种情况下 `--print-to-pdf` 都返回 0。

这里逐个把它们钉住，包括**故意把 `@page` 删掉**，确认验的那一步真的会拦。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/deck-authoring/test_pdf.py
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
# 测试自有夹具：风格与内容样本都放在 tests/ 下，**不随 skill 发布** ——
# 可拷贝的模板必然变成默认答案（每份 deck 长得一样）。
FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
# 夹具当"额外风格根"：工具链不内置任何风格（可拷贝的模板必然变成
# 默认答案）。脚本各持一份模块副本，所以走环境变量而不是改常量。
os.environ.setdefault("DECK_STYLES",
                      os.path.join(FIXTURES_DIR, "styles"))
os.environ.setdefault("DECK_BRANDS",
                      os.path.join(FIXTURES_DIR, "brands"))
SCRIPTS = os.path.join(SKILL, "scripts")
DEMO = os.path.join(FIXTURES_DIR, "demo.spec.json")

PAGE_RULE = "@page{size:1600px 900px;margin:0}"


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestPdfExport(unittest.TestCase):
    """两趟导出（正常 + 删掉 @page）共享给五条用例 —— 一趟真 PDF 约 3 秒。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.pdf = _load("deck_pdf", os.path.join(SCRIPTS, "pdf.py"))
        cls.render = _load("deck_render_pdf", os.path.join(SCRIPTS, "render.py"))
        with open(DEMO, encoding="utf-8") as fh:
            spec = json.load(fh)
        cls.slides = len(spec["deck"]["slides"])
        html = cls.render.render(spec)

        cls._tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._tmp.cleanup)
        td = cls._tmp.name
        cls.good_html = os.path.join(td, "good.html")
        with open(cls.good_html, "w", encoding="utf-8") as fh:
            fh.write(html)
        # 图页引用的那张图要放到位 —— 否则这条用例测的是“图不存在”的产物，
        # 而照片本身就是位图，一缺就把位图那条断言变得毫无意义
        # （实测踩过：测试绿了，真跑一遍却报“内嵌位图 1”）。
        from PIL import Image
        Image.new("RGB", (64, 48), (200, 40, 90)).save(os.path.join(td, "sample-treated.png"))
        # 只数**位图** <img>：品牌 logo 也是 <img> 但常是 SVG，SVG 在 PDF 里仍是矢量
        # （数进去会让这条断言恒假 —— 而它要盯的是"除照片外多出来的栅格化图层"）。
        cls.photos = len(re.findall(r'<img [^>]*src="(?!#|data:image/svg)', html))
        cls.all_imgs = html.count("<img ")
        cls.svg_imgs = html.count("data:image/svg+xml")
        # 变异：拿掉 @page 尺寸规则 —— 打印就会退成 Letter，而 --print-to-pdf 照样返回 0
        cls.bad_html = os.path.join(td, "bad.html")
        with open(cls.bad_html, "w", encoding="utf-8") as fh:
            fh.write(html.replace(PAGE_RULE, ""))

        cls.good = cls.pdf.export(cls.good_html, os.path.join(td, "good.pdf"))
        cls.bad = cls.pdf.export(cls.bad_html, os.path.join(td, "bad.pdf"))

    # ── 正常产物 ─────────────────────────────────────────────────────────

    def test_one_pdf_page_per_slide(self) -> None:
        """页数必须等于产物里的页数 —— 少一页的 PDF 会被拿上台讲。"""
        self.assertEqual(self.good["expected_pages"], self.slides,
                         "数页逻辑读到的页数和 spec 对不上（先怀疑 section.slide 的结构）")
        self.assertEqual(self.good["pages"], self.good["expected_pages"],
                         f"PDF 出了 {self.good['pages']} 页，产物里有 "
                         f"{self.good['expected_pages']} 页 —— 分页被撑破版面的元素推歪了")

    def test_no_rasterization_beyond_the_photos(self) -> None:
        """内嵌位图数 == 产物里的 `<img>` 数（照片本来就是位图，不能断言“零位图”）。

        真正的回归是**除照片之外多出来**的位图：滤镜、`<pattern>`、大图层的合成
        都会让 Chrome 把整页栅格化（实测退化版 6 页 32 张 / 7.5MB，现在是 1 张 / 0.66MB）。
        断言写成“等于照片数”而不是“等于 0”，这条才有牙 —— 否则图一缺它就永远绿。
        """
        self.assertGreater(self.photos, 0, "demo 里本该有图文页 —— 这条用例的前提变了")
        self.assertEqual(self.good["images"], self.photos,
                         f"内嵌位图 {self.good['images']} 张，但产物里只有 "
                         f"{self.photos} 张照片 —— 多出来的是被栅格化的图层"
                         f"（滤镜 / <pattern> / 大图层 是常见原因）")

    def test_fonts_are_embedded(self) -> None:
        """字要嵌进去，否则对方机器缺字就换字体（排版会变）。"""
        self.assertGreater(self.good["fonts"], 0, "PDF 里没有嵌入字体 —— 文字会随对方机器变")

    def test_page_box_is_exactly_1600x900_css_px(self) -> None:
        """页尺寸 = 1600×900 CSS px = 1200×675 pt。不对就是被缩放了。"""
        self.assertTrue(self.good["mediaboxes"], "PDF 里没有 MediaBox")
        for box in self.good["mediaboxes"]:
            w = self.pdf._box_w(box)
            self.assertAlmostEqual(w, 1600 * self.pdf.PX_TO_PT, delta=2,
                                   msg=f"页宽 {w}pt，应是 {1600 * self.pdf.PX_TO_PT}pt（MediaBox {box}）")

    def test_report_passes_on_good_pdf(self) -> None:
        """验的那一步本身对好产物不能报错（否则人会学会忽略它）。"""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = self.pdf.report(self.good, "good.pdf")
        self.assertEqual(code, 0, f"好 PDF 被判失败：{buf.getvalue()}")

    # ── 变异：必须被拦 ───────────────────────────────────────────────────

    def test_missing_page_rule_is_caught(self) -> None:
        """删掉 `@page` 后，页尺寸退成 Letter —— 验的那一步必须报出来并返回 1。"""
        width = self.pdf._box_w(self.bad["mediaboxes"][0]) if self.bad["mediaboxes"] else -1
        self.assertLess(width, 1000, "删掉 @page 之后页尺寸居然还是 1200pt —— 变异的假设不成立")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = self.pdf.report(self.bad, "bad.pdf")
        out = buf.getvalue()
        self.assertEqual(code, 1, f"页尺寸不对却没拦：{out}")
        self.assertIn("页尺寸", out, f"报错没指出是页尺寸的问题：{out}")


if __name__ == "__main__":
    unittest.main()
