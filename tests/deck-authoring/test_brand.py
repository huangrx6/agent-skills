#!/usr/bin/env python3
"""品牌资产层的验证。

这个文件钉的核心是三件事：

1. **优先级**：品牌赢在"是谁"（色板 / 字体 / logo），风格赢在"怎么表达"
   （版面 / 构图 / 运动）。这条一旦写歪，症状是"换个品牌把风格搞坏了"或反过来。
2. **logo 必须跟着产物走**：内嵌成 data URI，不是相对路径 —— 相对路径的产物
   挪个目录就裂图，而 logo 每页都在，裂了整份 deck 就废了（`image` 字段那条老路
   已经吃过这个亏）。
3. **logo 压文字要阻塞**：它不在"越出该页"的管辖范围里（两个盒子都在页内），
   但盖上标题就是废页。这条有牙 —— 变异测试见最后一个用例。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/deck-authoring/test_brand.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
SCRIPTS = os.path.join(SKILL, "scripts")
DEMO = os.path.join(SKILL, "dev-tools", "demo.spec.json")

# 加载成**真名**（`brand` / `render`）：render.py 内部用 `_load_sibling("brand")`
# 拿的就是 sys.modules["brand"]，只有同名才是同一个对象 —— 否则下面 patch
# BRANDS_DIR 只改了测试这一份，渲染那一份看不见，测试会假绿。
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


brand = _load("brand")
render = _load("render")
check_mod = _load("check")

LOGO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">
<rect width="{w}" height="{h}" fill="#123456"/></svg>
"""


class BrandCase(unittest.TestCase):
    """所有用例共用的夹具。

    测试品牌建在**真** `brands/` 下，名字统一带 `zz_test_` 前缀，用完即删。

    为什么不另建一个临时 brands 目录再改 `BRANDS_DIR`：改不动。`_load_sibling`
    加载的是 `_deck_brand`，而且每调一次就是一个**新对象**（它自己的 docstring
    就写了“实测：两次加载是两个对象”）—— render 里那个、check 里那个、测试自己
    加载的那个，是三个不同的模块对象。patch 一个，另外两个看不见，于是渲染会去真
    目录找品牌、报“找不到”，而测试还以为夹具生效了。走真目录反而没有这层间接。
    """

    TEST_PREFIX = "zz_test_"

    @classmethod
    def setUpClass(cls) -> None:
        with open(DEMO, encoding="utf-8") as fh:
            cls.spec = json.load(fh)

    def setUp(self) -> None:
        # 上一次跑崩了可能留下残留，先清干净（幂等，不影响正常情况）
        for name in brand.available():
            if name.startswith(self.TEST_PREFIX):
                shutil.rmtree(os.path.join(brand.BRANDS_DIR, name), ignore_errors=True)

    def _full(self, short: str) -> str:
        return self.TEST_PREFIX + short

    def make_brand(self, short: str, **fields) -> dict:
        d = os.path.join(brand.BRANDS_DIR, self._full(short))
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d, exist_ok=True)
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        payload = {"version": 1, "label": short, "logo": "logo.svg", **fields}
        with open(os.path.join(d, "brand.json"), "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        for key in ("logo", "logoInverse"):
            if payload.get(key):
                with open(os.path.join(d, payload[key]), "w", encoding="utf-8") as fh:
                    fh.write(LOGO_SVG.format(w=420, h=100))
        return payload

    def spec_with(self, short: str | None, **deck_over) -> dict:
        spec = json.loads(json.dumps(self.spec))          # 深拷贝，用例之间不串
        if short is None:
            spec["deck"].pop("brand", None)
        else:
            spec["deck"]["brand"] = self._full(short)
        spec["deck"].update(deck_over)
        return spec


class TestBrandContract(BrandCase):
    def test_unknown_field_is_rejected(self) -> None:
        """字段集封闭 —— 未知字段直接报，不静默忽略（静默最坏：以为写进去了）。"""
        self.make_brand("x", 主色="#FF0000")
        with self.assertRaises(SystemExit) as ctx:
            brand.load(self._full("x"))
        self.assertIn("主色", str(ctx.exception))

    def test_unknown_logo_on_is_rejected(self) -> None:
        self.make_brand("x", logoOn="封面")
        with self.assertRaises(SystemExit) as ctx:
            brand.load(self._full("x"))
        self.assertIn("cover+end", str(ctx.exception))       # 报错里要列出可用值

    def test_missing_logo_file_is_rejected_with_the_path(self) -> None:
        """文件不在就报**具体路径** —— "logo 没生效"最难查的就是没说是哪个路径。"""
        d = os.path.join(brand.BRANDS_DIR, self._full("x"))
        os.makedirs(d, exist_ok=True)
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        with open(os.path.join(d, "brand.json"), "w", encoding="utf-8") as fh:
            json.dump({"version": 1, "logo": "nope.svg"}, fh)
        with self.assertRaises(SystemExit) as ctx:
            brand.load(self._full("x"))
        self.assertIn("nope.svg", str(ctx.exception))

    def test_unknown_brand_lists_what_exists(self) -> None:
        """认不出品牌名时报错要带候选表 —— 否则用户只能靠猜目录名。"""
        self.make_brand("acme")
        with self.assertRaises(SystemExit) as ctx:
            brand.load(self._full("acmee"))
        msg = str(ctx.exception)
        self.assertIn("acmee", msg)
        self.assertIn(self._full("acme"), msg)                # 候选里要有真的那个

    def test_no_brand_is_a_legal_state(self) -> None:
        """不带品牌是**合法**的，不是错误 —— 静默降级在这里恰恰是对的（没有就是没有）。"""
        self.assertEqual(brand.load(None), {})
        self.assertEqual(brand.load(""), {})
        html = render.render(self.spec_with(None))
        self.assertNotIn('class="brandlogo"', html)
        self.assertNotIn('class="brandfoot"', html)


class TestBrandPrecedence(BrandCase):
    """品牌赢"是谁"，风格赢"怎么表达"。"""

    def test_inverse_logo_on_dark_paper(self) -> None:
        """深底用反白版 —— 这是抽帧看图当场撞到的（keynote-dark 黑底上深色块整个消失）。"""
        self.make_brand("x", logoInverse="logo-inv.svg")
        b = brand.load(self._full("x"))
        self.assertEqual(brand.logo_file(b, "#000000"), "logo-inv.svg")
        self.assertEqual(brand.logo_file(b, "#FFFFFF"), "logo.svg")
        self.assertTrue(brand.is_dark_paper("#0A0A0A"))
        self.assertFalse(brand.is_dark_paper("#FBFAF6"))

    def test_single_logo_still_renders_everywhere(self) -> None:
        """只给一个 logo 也能跑（不因为缺反白版就报错）—— 但由 check.py 提示。"""
        self.make_brand("x")
        b = brand.load(self._full("x"))
        self.assertEqual(brand.logo_file(b, "#000000"), "logo.svg")
        self.assertEqual(brand.logo_file(b, "#FFFFFF"), "logo.svg")

    def test_brand_colors_merge_without_dropping_the_styles_own(self) -> None:
        """品牌色板是**并入**不是替换：同名的品牌赢，风格原有的一个都不少。"""
        self.make_brand("x", colorSets={"brand": {
            "primary": "#0B5FFF", "secondary": "#101418",
            "background": "#FFFFFF", "text": "#101418"}})
        tokens = render.load_style("swiss-grid")["tokens"]
        merged = brand.merge_color_sets(tokens["colorSets"], brand.load(self._full("x")))
        self.assertIn("brand", merged)
        for name in tokens["colorSets"]:
            self.assertIn(name, merged, f"品牌把风格自己的色板 {name} 弄丢了")
        self.assertEqual(merged["brand"]["primary"], "#0B5FFF")

    def test_brand_color_reaches_the_output(self) -> None:
        """优先级要真的落到产物里 —— 只测 merge 函数等于测了个纯函数，没测接线。"""
        self.make_brand("x", colorSets={"b": {
            "primary": "#0B5FFF", "secondary": "#101418",
            "background": "#FFFFFF", "text": "#101418"}})
        html = render.render(self.spec_with("x", colorSet="b"))
        self.assertIn("--accent:#0B5FFF", html)

    def test_fonts_replace_wholly_or_not_at_all(self) -> None:
        """只给一半字体 = 半吊子（标题品牌字体、正文不是），比不换更难看 —— 所以整组才生效。"""
        tokens = render.load_style("swiss-grid")["tokens"]
        self.make_brand("x", fonts={"display": "OnlyDisplay"})
        still = brand.merge_fonts(tokens["fonts"], brand.load(self._full("x")))
        self.assertEqual(still["display"], tokens["fonts"]["display"])

        self.make_brand("y", fonts={"display": "D", "body": "B"})
        both = brand.merge_fonts(tokens["fonts"], brand.load(self._full("y")))
        self.assertEqual(both["display"], "D")
        self.assertEqual(both["body"], "B")

    def test_logo_placement_stays_with_the_style(self) -> None:
        """品牌不决定 logo 放哪 —— 那是构图问题（风格知道画面哪里是空的）。

        所以品牌层的字段集里**没有**位置类字段：想挪 logo 是去改 skin.css。
        """
        for pos in ("logoPos", "logoTop", "logoRight", "logoCorner"):
            with self.subTest(field=pos):
                self.make_brand("x", **{pos: 100})
                with self.assertRaises(SystemExit):
                    brand.load(self._full("x"))


class TestLogoOnPolicy(BrandCase):
    def _count(self, **over) -> int:
        html = render.render(self.spec_with("x", **over))
        return html.count('class="brandlogo"')

    def test_policies(self) -> None:
        self.make_brand("x", logoOn="cover+end")
        self.assertEqual(self._count(), 2, "cover+end 应该只在封面与尾页")
        self.make_brand("x", logoOn="cover")
        self.assertEqual(self._count(), 1)
        self.make_brand("x", logoOn="all")
        self.assertEqual(self._count(), len(self.spec["deck"]["slides"]))
        self.make_brand("x", logoOn="none")
        self.assertEqual(self._count(), 0, "none 应该一个都不出")

    def test_cover_plus_end_targets_the_end_slide_not_just_the_last(self) -> None:
        """`cover+end` 的"尾页"要是 **end 版式那一页**，不是"数组最后一页"。

        两者在 demo 里恰好重合，所以这条测试要造一个尾页不是 end 的 deck —— 否则
        写错成 `slide_no == total` 也会绿（那种假绿最难发现）。
        """
        self.make_brand("x", logoOn="cover+end")
        spec = self.spec_with("x")
        spec["deck"]["slides"] = [
            {"type": "title", "title": "封面"},
            {"type": "content-text", "title": "正文", "bullets": ["a"]},
            {"type": "end", "title": "谢谢"},
            {"type": "content-text", "title": "附录", "bullets": ["b"]},
        ]
        html = render.render(spec)
        self.assertEqual(html.count('class="brandlogo"'), 2)
        # 封面（第 1 页）与 end 页（第 3 页）有；附录（第 4 页）没有
        self.assertIn('data-m="s1.logo"', html)
        self.assertIn('data-m="s3.logo"', html)
        self.assertNotIn('data-m="s4.logo"', html)

    def test_footer_renders_only_when_given(self) -> None:
        self.make_brand("x", footer="© 2026 ACME")
        self.assertIn('class="brandfoot"', render.render(self.spec_with("x")))
        self.make_brand("y")
        # 看**元素**而不是子串：`.brandfoot` 那条 CSS 规则一直都在壳里，
        # 用子串会把"样式规则存在"误判成"元素渲染了"。
        self.assertNotIn('class="brandfoot"', render.render(self.spec_with("y")))


class TestLogoSelfContained(BrandCase):
    def test_logo_is_embedded_not_linked(self) -> None:
        """logo 必须**内嵌**（data URI）—— 相对路径的产物挪个目录就裂图，
        而 logo 每页都在。这条同时保证了"产物是纯 ASCII"（base64 是 ASCII）。"""
        self.make_brand("x")
        html = render.render(self.spec_with("x"))
        self.assertIn('src="data:image/svg+xml;base64,', html)
        self.assertNotIn('src="logo.svg"', html)
        self.assertNotIn('src="brands/', html)
        # 真正要保证的是**内嵌载荷走 ASCII 转义**：正文里的中文本来就该是 UTF-8 原文
        # （早先这里写的是 `html.encode("ascii")`，那条断言是错的 —— 它会因为
        # `<title>` 里的中文而失败，而那时失败的是**断言**，不是产物）。
        payload = re.search(r'id="__deck_manifest">(.*?)</script>', html, re.S)
        self.assertIsNotNone(payload, "产物里没有语义清单")
        assert payload is not None          # 给类型检查看
        payload.group(1).encode("ascii")    # 转义过了，才不会被转存改坏

    def test_manifest_carries_a_skill_relative_ref_not_an_absolute_path(self) -> None:
        """清单里给导出脚本的是**技能相对**路径，不是机主目录 ——
        绝对路径一进产物就洗不掉（这类污染实测踩过）。"""
        self.make_brand("x")
        html = render.render(self.spec_with("x"))
        self.assertIn(f'"text":"brands/{self._full("x")}/logo.svg"', html)
        self.assertNotIn(SKILL, html)
        self.assertIn('"src_base":"skill"', html)


class TestLogoCheckHasTeeth(BrandCase):
    """最后一条，也是最要紧的一条：logo 压文字**要挡住**。

    造法：把产物的 CSS 里 logo 的 top 改低，让它落到标题上。这是**端到端**的
    （渲染 → 真浏览器测量 → 校验），不是喂一个假数据给检查函数 ——
    后者只能证明函数会算，证明不了它接上了测量层。
    """

    def test_logo_over_text_blocks(self) -> None:
        self.make_brand("x")
        spec = self.spec_with("x")
        html = render.render(spec)
        self.assertIn("top:58px", html)
        mutated = html.replace(".brandlogo{position:absolute;right:84px;top:58px;",
                               ".brandlogo{position:absolute;right:84px;top:250px;")
        self.assertNotEqual(mutated, html, "变异没生效 —— 壳里那条 .brandlogo 规则改了？")
        path = os.path.join(brand.BRANDS_DIR, self._full("x"), "mutated.html")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(mutated)
        problems = check_mod.check(spec, path)
        hits = [p for p in problems if "logo 压住了文字" in p]
        self.assertTrue(hits, f"logo 压住标题却没被拦下，实际报的是：{problems}")
        self.assertIn("s1.title", hits[0])            # 要点名被压的是谁

    def test_clean_layout_reports_nothing_about_the_logo(self) -> None:
        """反面对照：没问题时**不许**报 —— 否则上面那条可能是"永远会报"而假绿。"""
        self.make_brand("x")
        spec = self.spec_with("x")
        path = os.path.join(brand.BRANDS_DIR, self._full("x"), "clean.html")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(render.render(spec))
        problems = check_mod.check(spec, path)
        self.assertEqual([p for p in problems if "logo" in p], [])
        self.assertEqual([n for n in check_mod.advisories(
            check_mod.measure_mod.measure(path), spec,
            check_mod.style_tokens(spec)) if "logo" in n], [])


if __name__ == "__main__":
    unittest.main()


class TestExampleBrandIsCalledOut(unittest.TestCase):
    """example（ACME）是演示品牌：用在真实 deck 里 check 必须开口。

    demo.spec 是 SKILL.md 让人抄的模板，抄完不删 brand 就把 ACME logo 带进了
    真实交付 —— 这正是"示例被直接使用"的事故路径，所以提示要指名修法。
    """

    def test_advisory_fires_for_example_brand(self) -> None:
        deck = {"brand": "example"}
        tokens = render.load_style("swiss-grid")["tokens"]
        problems, notes = check_mod._check_brand(
            {"elements": [{"id": "lg", "slide": 1, "role": "logo", "x": 10,
                           "y": 10, "w": 50, "h": 20, "intendedText": "logo.svg"}]},
            deck, tokens)
        self.assertEqual(problems, [])
        self.assertTrue(any("演示品牌" in n for n in notes), notes)

    def test_no_advisory_for_real_or_absent_brand(self) -> None:
        tokens = render.load_style("swiss-grid")["tokens"]
        element = {"id": "lg", "slide": 1, "role": "logo", "x": 10,
                   "y": 10, "w": 50, "h": 20, "intendedText": "logo.svg"}
        _p, notes = check_mod._check_brand({"elements": [element]}, {}, tokens)
        self.assertFalse(any("演示品牌" in n for n in notes))
