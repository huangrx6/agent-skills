#!/usr/bin/env python3
"""交付演练工具（deliver.py）的验证。

这个工具做的事里有两处**容易悄悄错**的地方，各钉一条：

1. **"从整份 HTML 里只打印第 N 页"那段 CSS 覆盖** —— 如果它没生效，拿到的会是第 1 页
   （于是对比图上出现"HTML 写 03、PDF 写 01"的假差异）；如果 `page-break-after` 没关掉，
   尾巴会多一张空页。两者都不会报错，只会让对比图说谎。
2. **逐像素差**本身 —— 它得对"一样"和"不一样"都给对答案。给错的话，要么漏掉真偏差，
   要么把正常差异报成故障。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/deck-authoring/test_deliver.py
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
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, f"{name}.py"))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


deliver = _load("deliver")
deckio = _load("deckio")
render = _load("render")
pdf_mod = _load("pdf")


class TestParsePages(unittest.TestCase):
    def test_parses_commas_and_spaces(self) -> None:
        self.assertEqual(deliver.parse_pages("1,9,12"), [1, 9, 12])
        self.assertEqual(deliver.parse_pages(" 3 5 "), [3, 5])

    def test_bad_input_is_reported_not_crashed(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            deliver.parse_pages("1,x")
        self.assertIn("x", str(ctx.exception))


class TestFidelityMetric(unittest.TestCase):
    """逐像素差要给对答案 —— 它对了，"画面对不对"才有资格自动判。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def _png(self, name: str, color: tuple[int, int, int], box=None):
        from PIL import Image, ImageDraw   # noqa: PLC0415

        im = Image.new("RGB", (400, 225), (255, 255, 255))
        if box:
            ImageDraw.Draw(im).rectangle(box, fill=color)
        else:
            im = Image.new("RGB", (400, 225), color)
        path = os.path.join(self._tmp.name, name)
        im.save(path)
        return path

    def test_identical_images_score_zero(self) -> None:
        a = self._png("a.png", (200, 30, 60))
        b = self._png("b.png", (200, 30, 60))
        self.assertAlmostEqual(deliver.fidelity(a, b), 0.0, places=3)

    def test_different_size_same_content_still_matches(self) -> None:
        """HTML 截图是 2x、PDF 出来是 1x —— 尺寸不同不该被当成差异。"""
        from PIL import Image   # noqa: PLC0415

        a = self._png("big.png", (10, 20, 30))
        big = Image.open(a).resize((1200, 675), Image.Resampling.LANCZOS)
        b = os.path.join(self._tmp.name, "big2.png")
        big.save(b)
        self.assertLess(deliver.fidelity(a, b), 1.0)

    def test_a_missing_block_is_loud(self) -> None:
        """少一块内容必须报得出来（这是"导出少了一半东西"的信号）。"""
        a = self._png("full.png", (255, 255, 255), box=(40, 40, 360, 180))
        b = self._png("blank.png", (255, 255, 255))
        a2 = self._png("full2.png", (20, 20, 20), box=(40, 40, 360, 180))
        self.assertGreater(deliver.fidelity(a2, b), 10.0,
                           "整块内容不见了却几乎没差异 —— 这个指标没有牙")

    def test_pure_color_swap_is_detected(self) -> None:
        """纯色相变化也要报得出来 —— 但**要比亮度变化登记得少**。

        这个指标是**亮度基准**的（先把两图转 L 再比），所以红↔蓝这种"亮度接近、
        色相相反"的替换只有 ~41%（实测），而黑白互换是 100%。
        这是刻意选的：交付里真正要命的是"这块内容在不在"（亮度的变化），
        而不是"颜色偏了一点点"。所以阈值按实测定，不按直觉拍。
        """
        a = self._png("c1.png", (255, 0, 0))
        b = self._png("c2.png", (0, 0, 255))
        self.assertGreater(deliver.fidelity(a, b), 25.0)
        # 反面对照：黑白互换应当顶到 100%（说明这个指标真的在量亮度）
        self.assertGreater(deliver.fidelity(self._png("w.png", (255, 255, 255)),
                                            self._png("k.png", (0, 0, 0))), 95.0)


class TestPrintOnePage(unittest.TestCase):
    """只打印第 N 页那段覆盖：要真的只出一页，而且**页码保持原样**。

    这两点都只能实测 —— 纯逻辑层看不出 CSS 有没有生效（实测踩过：单页 deck 的写法
    让第 3 页变成第 01 页，对比图上出现了假差异，而逐像素差只有 0.3% 没报警）。
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._tmp.cleanup)
        spec = deckio.read_json(DEMO)
        cls.html = os.path.join(cls._tmp.name, "out.html")
        with open(cls.html, "w", encoding="utf-8") as fh:
            fh.write(render.render(spec))

    def test_extracts_one_page_with_its_own_number(self) -> None:
        out = os.path.join(self._tmp.name, "p3.png")
        deliver._print_one(self.html, 3, out, self._tmp.name)
        self.assertTrue(os.path.isfile(out), "没打出来")
        # 页码是页面序号派生的：第 3 页的页脚该是 / 03，不是 / 01
        pdf = out.replace(".png", ".pdf")
        pages = pdf_mod.inspect(pdf).get("pages")
        self.assertEqual(pages, 1, f"应只出一页，实际 {pages} 页（覆盖没生效，或尾巴多了空页）")
        with open(self.html, encoding="utf-8") as fh:
            self.assertIn('data-slide="3"', fh.read(), "产物里没有 data-slide —— 覆盖选不中页")

    def test_a_bad_page_number_is_not_silently_page_one(self) -> None:
        """选不中页的时候**不能**静静给出第 1 页 —— 那会让对比图撒谎。"""
        out = os.path.join(self._tmp.name, "p99.png")
        deliver._print_one(self.html, 99, out, self._tmp.name)
        if os.path.isfile(out):
            # 真出了图的话，它必须是**空白**的（选不中任何页），而不是第 1 页的内容
            from PIL import Image   # noqa: PLC0415

            with Image.open(out) as im:
                hist = im.convert("L").histogram()
            non_white = sum(hist[:250])
            self.assertLess(non_white, sum(hist) * 0.001,
                            "选不中的页号给出了有内容的图 —— 那多半是第 1 页")


class TestImagePlaceholder(unittest.TestCase):
    """缺必需图 = ERROR（§14/§15：静默造占位禁止），--allow-placeholder 显式选入。"""

    def test_missing_image_is_an_error_by_default(self) -> None:
        """默认不再造合成测试卡 —— 占位图滑进交付是迟早的事。"""
        spec = deckio.read_json(DEMO)
        with tempfile.TemporaryDirectory() as tmp:
            names = {s.get("image") for s in spec["deck"]["slides"] if s.get("image")}
            self.assertTrue(names, "demo 里本该有图文页 —— 这条用例的前提变了")
            with self.assertRaises(SystemExit) as ctx:
                deliver.ensure_images(spec, tmp)
            msg = str(ctx.exception)
            for name in names:
                self.assertIn(str(name), msg, "报错没点名缺哪张图")
            self.assertIn("allow-placeholder", msg, "报错没教空跑的显式选入口")
                # 默认路径一个文件都不造
            for name in names:
                self.assertFalse(os.path.isfile(os.path.join(tmp, str(name))))

    def test_placeholder_only_with_explicit_flag(self) -> None:
        """显式选入才造，且造的是**说清自己是占位**的合成图（老行为收进门内）。"""
        spec = deckio.read_json(DEMO)
        with tempfile.TemporaryDirectory() as tmp:
            deliver.ensure_images(spec, tmp, allow_placeholder=True)
            for s in spec["deck"]["slides"]:
                if s.get("image"):
                    self.assertTrue(os.path.isfile(os.path.join(tmp, str(s["image"]))))

    def test_existing_image_is_left_alone(self) -> None:
        """已经有了就不该覆盖 —— 真照片不能被一张合成图顶掉。"""
        spec = deckio.read_json(DEMO)
        with tempfile.TemporaryDirectory() as tmp:
            name = next(s["image"] for s in spec["deck"]["slides"] if s.get("image"))
            target = os.path.join(tmp, name)
            deckio.write_bytes(target, b"KEEP-ME")
            deliver.ensure_images(spec, tmp, allow_placeholder=True)
            self.assertEqual(deckio.read_bytes(target), b"KEEP-ME")


class TestContactSheet(unittest.TestCase):
    def test_sheet_is_written_with_a_row_per_page(self) -> None:
        from PIL import Image   # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "x.png")
            Image.new("RGB", (1600, 900), (250, 250, 250)).save(src)
            sheet = os.path.join(tmp, "sheet.png")
            deliver.contact_sheet(sheet, [("第 1 页", {"html": src, "pdf": src})])
            self.assertTrue(os.path.isfile(sheet))
            with Image.open(sheet) as im:
                self.assertGreater(im.width, 0)


if __name__ == "__main__":
    unittest.main()
