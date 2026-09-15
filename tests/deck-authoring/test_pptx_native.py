#!/usr/bin/env python3
"""可编辑 PPTX 的验证 —— 它和贴图版的差别就是"能不能改字"，所以测的就是这个。

## 为什么这层要单独测

`pptx_native.py` 出来的文件**长得像** pptx、能打开、页数也对，但可能是：

- 每页其实还是一张图（那它就白叫"可编辑"了）
- 某个元素的坐标忘了减页原点 —— 产物是竖向堆叠的多页，第 2 页的元素 y 本来就在
  900 以下，不减原点整片飞出画布（这个 bug 在 check.py 刚踩过一次）
- `<a:pattFill>` 是空的（属性名写成 `pattern_type` 会被**默默吞掉**，实测踩过：
  XML 里 `<a:pattFill/>` 光秃秃没有 `prst`，渲染出来是个空圈）

这三种都能「成功生成文件」，所以必须查产物。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/deck-authoring/test_pptx_native.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import tempfile
import unittest
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
SCRIPTS = os.path.join(SKILL, "scripts")
TOKENS = os.path.join(SKILL, "styles", "risograph", "style.json")
DEMO = os.path.join(SKILL, "dev-tools", "demo.spec.json")

# 版面 1600×900px → EMU。1 CSS px = 9525 EMU（= 0.75pt）。
EMU_PER_PX = 9525
SLIDE_H_PX = 900

# 会变成文本框的角色
TEXT_ROLES = {"title", "subtitle", "bullet", "caption", "foot"}

CHART_SLIDE = {
    "type": "chart", "title": "渠道占比", "unit": "%", "caption": "数据可改",
    "data": [{"label": "自然", "value": 38}, {"label": "投放", "value": 27},
             {"label": "合作", "value": 20}, {"label": "其他", "value": 15}],
}


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _slide_xmls(pptx_path: str) -> dict[str, str]:
    """把 pptx 当 zip 读，取出每页的 XML（不引额外依赖）。"""
    out = {}
    with zipfile.ZipFile(pptx_path) as zf:
        for name in sorted(zf.namelist()):
            if re.fullmatch(r"ppt/slides/slide\d+\.xml", name):
                out[name] = zf.read(name).decode("utf-8")
    return out


def _chart_xmls(pptx_path: str) -> dict[str, str]:
    out = {}
    with zipfile.ZipFile(pptx_path) as zf:
        for name in sorted(zf.namelist()):
            if re.fullmatch(r"ppt/charts/chart\d+\.xml", name):
                out[name] = zf.read(name).decode("utf-8")
    return out


class TestPptxNative(unittest.TestCase):
    """一份 demo（含图）+ 一份追加了图表页的 deck，各出一次 pptx 共享给全部用例。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.native = _load("deck_native", os.path.join(SCRIPTS, "pptx_native.py"))
        cls.measure = _load("deck_measure_native", os.path.join(SCRIPTS, "measure.py"))
        cls.render = _load("deck_render_native", os.path.join(SCRIPTS, "render.py"))
        with open(TOKENS, encoding="utf-8") as fh:
            tokens = json.load(fh)
        with open(DEMO, encoding="utf-8") as fh:
            demo = json.load(fh)

        cls._tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._tmp.cleanup)
        td = cls._tmp.name

        cls.html = os.path.join(td, "out.html")
        with open(cls.html, "w", encoding="utf-8") as fh:
            fh.write(cls.render.render(demo))
        # 图页引用的那张图要放在产物旁边，否则 image 角色会被（正确地）跳过
        from PIL import Image
        Image.new("RGB", (8, 8), (245, 239, 221)).save(os.path.join(td, "sample-treated.png"))

        chart_deck = json.loads(json.dumps(demo))
        chart_deck["deck"]["slides"].append(CHART_SLIDE)
        cls.chart_html = os.path.join(td, "chart.html")
        with open(cls.chart_html, "w", encoding="utf-8") as fh:
            fh.write(cls.render.render(chart_deck))

        cls.pptx = os.path.join(td, "native.pptx")
        cls.counts = cls.native.build(cls.html, cls.pptx)
        cls.chart_pptx = os.path.join(td, "native-chart.pptx")
        cls.chart_counts = cls.native.build(cls.chart_html, cls.chart_pptx)

        cls.slides = _slide_xmls(cls.pptx)
        cls.chart_slides = _slide_xmls(cls.chart_pptx)
        cls.manifest = cls.measure.read_manifest(cls.render.render(demo))
        cls.chart_manifest = cls.measure.read_manifest(
            cls.render.render(chart_deck))

    # ── 能改字：这是这个产物存在的理由 ───────────────────────────────────

    def test_text_is_real_text_not_an_image(self) -> None:
        """每个文本元素都要变成**真文本**，数量一个不少 —— 少一个就是静默丢内容。"""
        want = [e["text"] for e in self.manifest if e.get("role") in TEXT_ROLES and e.get("text")]
        got: list[str] = []
        for xml in self.slides.values():
            got += re.findall(r"<a:t>([^<]*)</a:t>", xml)
        self.assertEqual(len(got), len(want),
                         f"清单里有 {len(want)} 条文本，pptx 里只有 {len(got)} 段")
        for text in want:
            self.assertIn(text, got, f"清单里的文本没进 pptx：{text!r}")

    def test_no_whole_slide_picture(self) -> None:
        """整页贴图是贴图版的活 —— 可编辑版里出现整页图就说明退回去了。

        第 1 页（封面）在 demo 里没有 image 角色，所以它不该有任何 `<p:pic>`。
        """
        first = self.slides["ppt/slides/slide1.xml"]
        self.assertNotIn("<p:pic>", first, "封面页里有图片 —— 可编辑版不该有整页贴图")
        self.assertIn("<a:t>", first, "封面页里没有文本 —— 内容去哪了")

    def test_image_role_becomes_a_picture(self) -> None:
        """图文页的图要真的放进去（图的**位置**是可改的，内容不是）。"""
        self.assertEqual(self.counts["image"], 1, "demo 里那张图没进 pptx")

    # ── 几何：从实测来，且是**页内**坐标 ─────────────────────────────────

    def test_geometry_is_slide_relative(self) -> None:
        """任何形状的 y 偏移都必须小于一页高。

        产物是竖向堆叠的多页，第 2 页的元素 y 本来就在 900 以下 —— 忘了减页原点，
        整片会飞出画布，而文件照样生成成功。这条就是拦它。
        """
        for name, xml in self.slides.items():
            for y in re.findall(r"<a:off x=\"-?\d+\" y=\"(-?\d+)\"", xml):
                self.assertLess(int(y), SLIDE_H_PX * EMU_PER_PX,
                                f"{name} 里有形状 y={int(y)} EMU（{int(y) / EMU_PER_PX:.0f}px）"
                                f" 超出页高 —— 坐标忘了减页原点")
                self.assertGreater(int(y), -SLIDE_H_PX * EMU_PER_PX,
                                   f"{name} 里有形状 y 负得离谱 —— 坐标系可能整个错了")

    def test_slide_size_is_1600x900(self) -> None:
        """版面必须正好 1600×900px（= 1200×675pt）。"""
        from pptx import Presentation
        prs = Presentation(self.pptx)
        self.assertEqual(prs.slide_width, 1600 * EMU_PER_PX)
        self.assertEqual(prs.slide_height, 900 * EMU_PER_PX)

    def test_one_pptx_slide_per_deck_slide(self) -> None:
        self.assertEqual(len(self.slides), len(self.manifest and
                                               {e["slide"] for e in self.manifest}))

    # ── 装饰：拦"属性名写错被默默吞掉"这一类 ─────────────────────────────

    def test_decor_is_a_patterned_ellipse(self) -> None:
        """装饰墨块要是**带 prst 的椭圆图案填充**。

        属性名写成 `pattern_type` 时 python-pptx 不报错、当成普通属性吞掉，
        XML 里就是 `<a:pattFill/>` —— 光秃秃没有 `prst`，渲染出来是个空圈（实测踩过）。
        """
        hit = 0
        for name, xml in self.slides.items():
            fills = re.findall(r"<a:pattFill\b[^>]*>", xml)
            if not fills:
                continue    # 这一页没有装饰墨块 —— 不是每种版式都放（图文页就不放）
            self.assertIn('prst="ellipse"', xml, f"{name} 有图案填充却没有椭圆形状")
            for fill in fills:
                self.assertRegex(fill, r'prst="\w+"',
                                 f"图案填充没有 prst —— 画出来会是个空圈：{fill}")
                hit += 1
        self.assertGreater(hit, 0, "没有任何图案填充 —— 装饰墨块没生成")

    # ── 图表：要能改数据 ─────────────────────────────────────────────────

    def test_chart_is_a_native_editable_chart(self) -> None:
        """图表必须是 PowerPoint 原生图表，且**数据在里面**（能改才有意义）。"""
        charts = _chart_xmls(self.chart_pptx)
        self.assertEqual(len(charts), 1, f"应恰好 1 个原生图表，实际 {len(charts)}")
        xml = next(iter(charts.values()))
        for d in CHART_SLIDE["data"]:
            self.assertIn(str(d["value"]), xml, f"图表里没有值 {d['value']}")
            self.assertIn(d["label"], xml, f"图表里没有类目 {d['label']}")
        self.assertEqual(self.chart_counts["chart"], 1)

    # ── 不静默：该跳过的要计数 ───────────────────────────────────────────

    def test_skipped_elements_are_counted_not_hidden(self) -> None:
        """量不到几何、或图不在旁边时**跳过并计数**，不猜一个位置静静画上去。"""
        want = (self.counts["text"] + self.counts["decor"] + self.counts["chart"]
                + self.counts["image"] + self.counts["skipped"])
        self.assertEqual(want, len(self.manifest) + self.counts["decor"],
                         "统计对不上：有元素既没进 pptx 也没被记成跳过")


if __name__ == "__main__":
    unittest.main()
