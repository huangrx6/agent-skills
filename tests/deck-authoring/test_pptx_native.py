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

import copy
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
# 测试自有夹具（v4）：风格与内容样本都放在 tests/ 下，**不随 skill 发布** ——
# 可拷贝的模板必然变成默认答案（用户实测：每份 deck 长得一样）。
FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
# 夹具当"额外风格根"：v4 起工具链不内置任何风格（可拷贝的模板必然变成
# 默认答案）。脚本各持一份模块副本，所以走环境变量而不是改常量。
os.environ.setdefault("DECK_STYLES",
                      os.path.join(FIXTURES_DIR, "styles"))

# 夹具第一套风格（tests/fixtures/styles 下；风格不再有内置解析根）
FIXTURE_STYLE = os.path.join(FIXTURES_DIR, "styles", "swiss-grid")
SCRIPTS = os.path.join(SKILL, "scripts")
TOKENS = os.path.join(FIXTURES_DIR, "styles", "swiss-grid", "style.json")
STYLES = os.path.join(FIXTURES_DIR, "styles")
DEMO = os.path.join(FIXTURES_DIR, "demo.spec.json")

# 版面 1600×900px → EMU。1 CSS px = 9525 EMU（= 0.75pt）。
EMU_PER_PX = 9525
SLIDE_H_PX = 900

# 会变成文本框的角色
# 会变成真文本的角色。**新增一个文本角色就要加到这里** —— 漏了会让下面那条
# "数量一个不少"的用例把 pptx 里多出来的段落报成失败（实测被 brandfoot 撞过一次）。
TEXT_ROLES = {"title", "subtitle", "bullet", "caption", "foot", "brandfoot"}

CHART_SLIDE = {
    "type": "chart", "title": "渠道占比", "chart": "donut", "unit": "%",
    "caption": "数据可改",
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



def _style_names() -> list[str]:
    """所有风格 —— **读目录，不写死名单**。

    写死名单的代价是实测过的：加了四套新风格之后，那份写死的名单让它们全部逃过了
    运动 / 装饰 / 版式表三条检查 —— 而测试是绿的。目录才是唯一事实来源。
    """
    return sorted(d for d in os.listdir(STYLES) if os.path.isdir(os.path.join(STYLES, d)))


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

        cls.chart_zip = zipfile.ZipFile(cls.chart_pptx)
        cls.addClassCleanup(cls.chart_zip.close)
        cls.slides = _slide_xmls(cls.pptx)
        cls.chart_slides = _slide_xmls(cls.chart_pptx)
        cls.demo = demo
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

        判据是**大小**而不是"有没有 <p:pic>"：有品牌 logo 的封面本来就会有图片，
        而 logo 是个小图。整页贴图才会占满整页 —— 那才是"退回了贴图版"。
        """
        first = self.slides["ppt/slides/slide1.xml"]
        self.assertIn("<a:t>", first, "封面页里没有文本 —— 内容去哪了")
        for cx, cy in re.findall(r'<a:ext cx="(\d+)" cy="(\d+)"/>', first):
            area = int(cx) * int(cy)
            slide_area = 12192000 * 6858000          # 13.333in × 7.5in
            self.assertLess(area / slide_area, 0.5,
                            f"封面页里有一张占了整页 {area / slide_area:.0%} 的图 —— "
                            f"可编辑版不该有整页贴图（logo 之类的小图不算）")

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

    def test_every_style_decor_kind_is_exportable(self) -> None:
        """每种风格声明的 `decor.kind` 都必须有导出映射。

        守的是**静默少元素**：`add_decor` 按 kind 分派，新加一种装饰而忘了加分支，
        导出的 pptx 会照常生成、页数照样对，只是静默缺一个形状。

        也钉住了“图案填充必须有 prst”那条 —— python-pptx 的属性名写错
        （`pattern_type` 而不是 `pattern`）会被当成普通属性默默吞掉，
        XML 里 `<a:pattFill>` 光秃秃，渲染出来是个空圈（实测踩过）。若哪天有风格
        重新用上 halftone-circle，这条会把它拉回来。
        """
        # 内置风格已删（styles/ 移除），夹具 swiss 不声明装饰 —— 前提改为
        # **构造**声明装饰的风格：这条守的是"declared ⊆ DECOR_SHAPES"的映射
        # 完整性，不依赖哪套具体风格恰好用了装饰。
        declared = set()
        for name in _style_names():
            spec = self.render.load_style(name)["tokens"].get("decor") or {}
            if spec.get("kind"):
                declared.add(spec["kind"])
        base = self.render.load_style(FIXTURE_STYLE)
        for kind in ("accent-block", "halftone-circle"):
            variant = dict(base, tokens=dict(base["tokens"],
                                             decor={"kind": kind}))
            declared.add(variant["tokens"]["decor"]["kind"])
        self.assertTrue(declared, "没有任何风格声明装饰 —— 这条用例的前提没了")
        self.assertTrue(
            declared <= self.native.DECOR_SHAPES,
            f"有风格声明了导出层不认识的装饰：{declared - self.native.DECOR_SHAPES}")

    def test_decor_lands_as_a_native_shape(self) -> None:
        """有装饰的风格，装饰要真的落成一个原生形状（不是被静默吞掉）。"""
        # billboard（自带 accent-block 装饰）已随 styles/ 删除：注入同款 token
        # 驱动同一分支 —— 测的是"声明的装饰真的落成原生形状"，与哪套风格无关。
        style = self.render.load_style(FIXTURE_STYLE)
        style = dict(style, tokens=dict(style["tokens"], decor={
            "kind": "accent-block", "types": ["title"], "zones": ["br"],
            "sizes": [400]}))
        deck = json.loads(json.dumps(json.load(open(DEMO, encoding="utf-8"))))
        deck["deck"]["style"] = "swiss-grid"
        deck["deck"]["colorSet"] = next(iter(style["tokens"]["colorSets"]))
        with tempfile.TemporaryDirectory() as td:
            html = os.path.join(td, "out.html")
            with open(html, "w", encoding="utf-8") as fh:
                fh.write(self.render.render(deck, style))
            pptx = os.path.join(td, "deck.pptx")
            counts = self.native.build(html, pptx)
            expected = len(self.measure.measure(html).get("decor", []))
            xml = _slide_xmls(pptx)["ppt/slides/slide1.xml"]
        self.assertEqual(counts["decor"], expected,
                         f"测到 {expected} 个装饰，pptx 里只落了 {counts['decor']} 个")
        self.assertIn('prst="rect"', xml, "装饰在 pptx 里不是个矩形形状")

    def test_halftone_decor_exports_with_a_real_pattern(self) -> None:
        """网点圆（halftone-circle）导出时 `<a:pattFill>` **必须带 prst**。

        现在没有发布的风格用网点圆（risograph 那套已删），所以这条得**自己造一份**
        token 去驱那个分支 —— 不然它就是个空跑的用例，而空跑的用例比没有更糟：
        它让人以为有人看着。

        为什么盯这一条：python-pptx 的属性名写错（`pattern_type` 而不是 `pattern`）
        会被当成普通属性默默吞掉，XML 里 `<a:pattFill>` 光秃秃没有 prst，
        渲染出来是个空圈 —— 实测踩过，而且文件生成/页数全对，不查就发现不了。
        """
        base = self.render.load_style(FIXTURE_STYLE)
        style = dict(base, tokens=copy.deepcopy(base["tokens"]))
        style["tokens"]["decor"] = {"kind": "halftone-circle", "types": ["title"],
                                    "zones": ["br"], "sizes": [400]}
        deck = json.loads(json.dumps(json.load(open(DEMO, encoding="utf-8"))))
        deck["deck"]["style"] = "swiss-grid"
        deck["deck"]["colorSet"] = next(iter(style["tokens"]["colorSets"]))
        with tempfile.TemporaryDirectory() as td:
            html = os.path.join(td, "out.html")
            with open(html, "w", encoding="utf-8") as fh:
                fh.write(self.render.render(deck, style))
            pptx = os.path.join(td, "deck.pptx")
            self.native.build(html, pptx)
            xml = _slide_xmls(pptx)["ppt/slides/slide1.xml"]
        fills = re.findall(r"<a:pattFill\b[^>]*>", xml)
        self.assertTrue(fills, "网点圆没导出成图案填充的椭圆")
        for fill in fills:
            self.assertRegex(fill, r'prst="\w+"',
                             f"图案填充没有 prst —— 画出来会是个空圈：{fill}")
        self.assertIn('prst="ellipse"', xml, "网点圆在 pptx 里不是个椭圆")

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

    # ── 交付演练才发现的三个真 bug（都只在"打开 PPTX 看"时才露出来）──────────

    def test_every_text_run_declares_an_east_asian_font(self) -> None:
        """中文靠 `<a:ea>`，**不能只写 `<a:latin>`**。

        `run.font.name` 只写 latin，于是宿主软件（PowerPoint / WPS / LibreOffice）会
        自己挑一个东亚字体来画汉字 —— 一份中文 deck 的字几乎全是汉字，等于**整个风格
        被换掉**。实测：`paper-ink`（宋体）导出来被 LibreOffice 画成一个加粗黑体。
        """
        cjk = set(self.native.CJK_FAMILIES)
        checked = 0
        for name, xml in list(self.slides.items()) + list(self.chart_slides.items()):
            for m in re.finditer(r"<a:rPr[^>]*>(.*?)</a:rPr>", xml, re.S):
                blk = m.group(1)
                latin = re.search(r'<a:latin typeface="([^"]*)"', blk)
                ea = re.search(r'<a:ea typeface="([^"]*)"', blk)
                if latin is None:
                    continue                     # 没有 latin 的 run 不是我们的文字
                checked += 1
                self.assertIsNotNone(ea, f"{name} 里有 run 没写 <a:ea>：{latin.group(1)}")
                assert ea is not None
                self.assertIn(ea.group(1), cjk,
                              f"{name} 的 ea 写成了 {ea.group(1)!r} —— 那不是 CJK 族，"
                              f"宿主照样会自己挑（等于没写）")
        self.assertGreater(checked, 10, "一个文本 run 都没扫到 —— 这条用例失效了")

    def test_chart_shows_values_and_hides_gridlines(self) -> None:
        """原生图表要跟着**我们的设计**，不是跟着宿主软件的默认模板。

        不设这两项时：LibreOffice/PowerPoint 会画上网格线与左侧坐标轴数字，
        而柱子上**没有数值** —— 和我们的设计正好相反（我们数值在柱顶、只有一条基线）。
        这是"打开看"才发现的：文件生成成功、页数也对，图却是另一个样子。
        """
        chart_xml = "".join(
            self.chart_zip.read(n).decode()
            for n in self.chart_zip.namelist() if re.search(r"ppt/charts/chart\d+\.xml$", n))
        self.assertTrue(chart_xml, "原生 PPTX 里没有图表 XML")
        self.assertIn("<c:dLbls>", chart_xml, "柱子上没有数值标签")
        self.assertNotIn("majorGridlines", chart_xml, "还画着网格线")

    def test_chart_labels_carry_the_unit(self) -> None:
        """数值要带单位（我们设计里是 31%，不是 31）。

        `sourceLinked="0"` 也要有：不设的话 PowerPoint 会当成"跟随数据源"
        而在打开时重套一遍默认格式，单位就丢了。
        """
        chart_xml = "".join(
            self.chart_zip.read(n).decode()
            for n in self.chart_zip.namelist() if re.search(r"ppt/charts/chart\d+\.xml$", n))
        self.assertIn('formatCode="0&quot;%&quot;"', chart_xml)
        self.assertIn('sourceLinked="0"', chart_xml)

    def test_title_weight_follows_the_style_not_a_hardcoded_bold(self) -> None:
        """字重跟着**实测**走，不按角色写死。

        八套风格里有**两套**（paper-ink / botanical-dark）的标题是 400 字重，
        统一 bold 就等于把这两套的标题设计抹掉 —— 而 XML 里读出来是 `b="1"`，
        文件照生成、页数照样对，只有把 PPTX 打开看才发现。
        """
        # paper-ink（标题 400 字重）已随 styles/ 删除：受控实验改为同一套夹具的
        # 两个变体 —— 原版（UA 默认 h1=700）与注入 h1{font-weight:400} 的变体。
        # 同风格只动一个变量，"导出跟实测字重走、不按角色写死"测得更直接。
        demo = json.loads(json.dumps(self.demo))
        base = self.render.load_style(FIXTURE_STYLE)
        light = dict(base, skin=base["skin"] + "\nh1.title{font-weight:400}\n")
        results = {}
        for tag, st in (("heavy", base), ("light", light)):
            spec = json.loads(json.dumps(demo))
            spec["deck"]["style"] = "swiss-grid"
            spec["deck"]["slides"] = [s for s in spec["deck"]["slides"]
                                      if s["type"] == "title"]
            path = os.path.join(self._tmp.name, f"w-{tag}.html")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.render.render(spec, st))
            out = os.path.join(self._tmp.name, f"w-{tag}.pptx")
            self.native.build(path, out)
            xmls = _slide_xmls(out)
            first = xmls["ppt/slides/slide1.xml"]
            m = re.search(r'<a:rPr[^>]*sz="(\d+)"[^>]*b="(\d)"', first)
            self.assertIsNotNone(m, f"{tag} 的标题 run 没读到字重")
            assert m is not None
            results[tag] = m.group(2)
        self.assertEqual(results["heavy"], "1", "实测 700 的标题导出却是常规")
        self.assertEqual(results["light"], "0", "实测 400 的标题导出却被加粗了")


    def test_skipped_elements_are_counted_not_hidden(self) -> None:
        """量不到几何、或图不在旁边时**跳过并计数**，不猜一个位置静静画上去。"""
        want = (self.counts["text"] + self.counts["decor"] + self.counts["chart"]
                + self.counts["image"] + self.counts["logo"] + self.counts["skipped"])
        self.assertEqual(want, len(self.manifest) + self.counts["decor"],
                         "统计对不上：有元素既没进 pptx 也没被记成跳过")


if __name__ == "__main__":
    unittest.main()
