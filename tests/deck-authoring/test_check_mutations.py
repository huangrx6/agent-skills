#!/usr/bin/env python3
"""check.py 六项机械校验的**变异验证** —— 每项都要造违规样例。

## 为什么校验器自己也要被"变异测试"

一个只会说 ✓ 的校验器和没有校验器**在结果上完全一样**，但会让人以为有人守着。
所以六项里每一项都做两件事：

1. 干净产物 → 该项不报
2. **针对该项**做一次变异 → 该项必须报

变异规则：**必须替换产物里真实存在的值**（不是凭空加新值）。凭空加的在真实产物里
根本不会出现，那种"变异"证明了校验器什么都没守住。

| 校验项 | 变异对象 | 被替换的真实值 |
| --- | --- | --- |
| ① 对比度 | token 色板 | 叠印墨（产物里 `--ink-text` 的真实来源） |
| ② 文字溢出 | spec 条目 | 某条 bullet 的文本 |
| ③ 错位区间 | 产物 HTML | 真实的 `--dx:Npx` 字符串 |
| ④ 装饰不压文字 | 产物 HTML | 真实的 `data-zone="tr|br"` |
| ④ 柱高成比例 | 产物 HTML | 真实的柱条 `height="N"` |
| ④ 图表区无错位 | 产物 HTML | 真实的 `<div class="chartwrap">` 容器 |

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/deck-authoring/test_check_mutations.py
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

# 夹具第一套风格（tests/fixtures/styles 下；风格不再有内置解析根）
FIXTURE_STYLE = os.path.join(FIXTURES_DIR, "styles", "swiss-grid")
SCRIPTS = os.path.join(SKILL, "scripts")
TOKENS = os.path.join(FIXTURES_DIR, "styles", "swiss-grid", "style.json")
DEMO = os.path.join(FIXTURES_DIR, "demo.spec.json")

CHART_SLIDE = {
    "type": "chart", "title": "占比", "chart": "bar",
    "data": [{"label": "A", "value": 10}, {"label": "B", "value": 20},
             {"label": "C", "value": 30}, {"label": "D", "value": 40}],
    "unit": "%",
}


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


render = _load("_deck_test_render", os.path.join(SCRIPTS, "render.py"))
check = _load("_deck_test_check", os.path.join(SCRIPTS, "check.py"))
measure = _load("_deck_test_measure", os.path.join(SCRIPTS, "measure.py"))


def _stub_image(directory: str) -> None:
    """在产物旁边放一张 1×1 PNG。

    demo spec 引用了 `sample-treated.png`；不把它放到产物同目录的话，
    “图片没加载”这条**真实有效**的检查会（正确地）报出来 ——
    那测试就测不成“干净产物”了。要的是一个真干净的产品，不是把检查关掉。
    """
    from PIL import Image
    Image.new("RGB", (2, 2), (245, 239, 221)).save(os.path.join(directory, "sample-treated.png"))


class TestCheckMutations(unittest.TestCase):
    """校验项，每项都有一条干净基线 + 一条变异。

    变异有两种：改**产物**（拼 HTML）与改**风格 token**（色板/字号）。后者需要把改过的
    token 包回一个完整风格字典 —— 风格现在是一个目录（token + skin），不是裸 token。
    """

    @classmethod
    def setUpClass(cls) -> None:
        with open(DEMO, encoding="utf-8") as fh:
            cls.demo = json.load(fh)
        cls.style = render.load_style(FIXTURE_STYLE)          # {"name", "tokens", "skin"}
        cls.tokens = cls.style["tokens"]
        cls.chart_spec = copy.deepcopy(cls.demo)
        cls.chart_spec["deck"]["slides"].append(copy.deepcopy(CHART_SLIDE))
        cls.demo_html = render.render(cls.demo, cls.style)
        cls.chart_html = render.render(cls.chart_spec, cls.style)
        # 写一份产物到磁盘：G2 就绪那条用例要拿真实文件路径喂 check
        cls._tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._tmp.cleanup)
        cls.chart_path = os.path.join(cls._tmp.name, "chart.html")
        with open(cls.chart_path, "w", encoding="utf-8") as fh:
            fh.write(cls.chart_html)

    def _problems(self, spec: dict, html_text: str, tokens: dict | None = None) -> list[str]:
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "out.html")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(html_text)
            _stub_image(td)
            return check.check(spec, path, tokens or self.tokens)

    def _assert_reports(self, problems: list[str], needle: str, what: str) -> None:
        self.assertTrue(problems, f"{what}：变异后本应报错却全过")
        self.assertTrue(any(needle in p for p in problems),
                        f"{what}：报的不是目标项（找 {needle!r}），实际：{problems}")

    # ── baseline ──────────────────────────────────────────────────────────

    def test_baseline_demo_and_chart_are_clean(self) -> None:
        """改动之前先证明基线干净 —— 否则后面的"变异被抓到"说明不了什么。"""
        self.assertEqual(self._problems(self.demo, self.demo_html), [],
                         "demo 基线本应干干净净")
        self.assertEqual(self._problems(self.chart_spec, self.chart_html), [],
                         "带 chart 的基线本应干干净净")

    # ── ① 对比度 ──────────────────────────────────────────────────────────

    def test_contrast_mutation_is_caught(self) -> None:
        """变异：把文字色改成跟底色几乎一样（对比度必然不达标）。

        变异的是 `colorSets.*.text` —— 现在文字色是**声明**的（风格自己说了").
        原来是改 primary/secondary 让**推导**出来的叠印色变差（那是叠印风格的路）。
        两种走的是同一个门禁（ink.text_color），所以改哪一边都能验到门禁真的在跑。
        """
        bad = copy.deepcopy(self.tokens)
        name = next(iter(bad["colorSets"]))
        bad["colorSets"][name]["text"] = bad["colorSets"][name]["background"]
        bad_style = dict(self.style, tokens=bad)
        problems = self._problems(self.demo, render.render(self.demo, bad_style), bad)
        self._assert_reports(problems, "对比度", "① 对比度")

    # ── ② 文字溢出 ────────────────────────────────────────────────────────

    def test_overflow_mutation_is_caught(self) -> None:
        """变异：把 content-image 页的第一条条目拉成 500 个字。

        它会被浏览器**真的**排成很多行 → li 盒子下缘冲出该页 → 报"越出版面"。
        这正是估算法当年漏掉的那类（估宽会看到一个比上限大得多的数字，
        但真因是高度而不是宽度）。
        """
        bad = copy.deepcopy(self.demo)
        for slide in bad["deck"]["slides"]:
            if slide.get("type") == "content-image" and slide.get("bullets"):
                slide["bullets"][0] = "长" * 500
                break
        else:
            self.fail("demo 里没有 content-image 页 —— 这条用例的前提变了")
        problems = self._problems(bad, render.render(bad, self.style))
        self._assert_reports(problems, "越出版面", "② 版面越界")

    # ── ③ 错位区间 ────────────────────────────────────────────────────────

    def test_misregistration_mutation_is_caught(self) -> None:
        """变异：把产物里真实的 --dx 值改成 100px（远超 token 区间 [1,3]）。"""
        mutated, count = re.subn(r"--dx:([\d.\-]+)px;--dy:([\d.\-]+)px;--rot:([\d.\-]+)deg",
                                 r"--dx:100px;--dy:\2px;--rot:\3deg", self.demo_html, count=1)
        self.assertEqual(count, 1, "产物里没找到 --dx 字符串 —— render.py 改格式了")
        problems = self._problems(self.demo, mutated)
        self._assert_reports(problems, "错位参数", "③ 错位区间")

    # ── ④ 装饰不压文字 ────────────────────────────────────────────────────

    def test_decoration_zone_mutation_is_caught(self) -> None:
        """变异：把产物里真实的 data-zone 改成一个未知 zone。

        ⚠️ 拿**有装饰的风格**测：默认的瑞士栅格没有装饰（`decor.kind = null`），
        产物里一个 data-zone 都不会有 —— 拿它跑这条只会得到“前提不成立”。
        billboard（自带装饰）已随 styles/ 删除，改为给夹具注入同款 accent-block
        token —— 驱动同一分支，与哪套风格自带装饰无关。
        """
        style = render.load_style(FIXTURE_STYLE)
        style = dict(style, tokens=dict(style["tokens"], decor={
            "kind": "accent-block", "types": ["title"], "zones": ["tr", "br"],
            "sizes": [400]}))
        deck = copy.deepcopy(self.demo)
        # 色板名是**每种风格各自**的 —— 拿 A 风格的 colorSet 去渲 B 风格会被拒。
        deck["deck"]["colorSet"] = next(iter(style["tokens"]["colorSets"]))
        html = render.render(deck, style)
        found = re.search(r'data-zone="(tr|br)"', html)
        if found is None:
            self.fail("注入的装饰产物里没有 data-zone=tr|br —— 装饰版式或标记改了")
        original = found.group(1)
        mutated, count = re.subn(rf'data-zone="{original}"', 'data-zone="center"',
                                 html, count=1)
        self.assertEqual(count, 1)
        problems = self._problems(deck, mutated, style["tokens"])
        self._assert_reports(problems, "未知装饰 zone", "④ 装饰不压文字")

    # ── ④ 柱高成比例 ──────────────────────────────────────────────────────

    def test_real_chart_page_reports_ready(self) -> None:
        """**实测**：真产物跑一遍浏览器，G2 必须真渲染出来（chartReady == ready）。

        为什么这条必须是真浏览器而不是合成 measured：v4 踩过一次 —— 初始化脚本里
        留了 `renderer:'svg'`，而这份 UMD bundle 只带 canvas 渲染器，G2 在运行时抛
        registerPlugin；当时 chartReady 也没接到 `[data-m]` 元素上，**闸门静默失效**，
        只有人肉开浏览器才看得出来。这条用例把两件事一起钉住：字段要接到、
        且真浏览器里必须 ready。
        """
        measured = measure.measure(self.chart_path)
        rows = [e for e in measured.get("elements", [])
                if e.get("chartReady") is not None]
        self.assertTrue(rows, "没有任何元素报 chartReady —— 探测没接到 [data-m] 上")
        bad = [(e.get("id"), e.get("chartReady")) for e in rows
               if e.get("chartReady") != "ready"]
        self.assertEqual(bad, [], f"G2 没渲染成功：{bad}")

    def test_chart_g2_ready_is_required(self) -> None:
        """变异：把 G2 容器标成渲染失败 → check 必须报出来。

        v4 换掉的是**判据**而不是牙口：手写 SVG 时代查"柱高与数据成比例"，
        现在几何由 G2 算，查的是"G2 真渲染出来了"（实测 chartReady 字段，
        静态 HTML 里只有容器与 spec，判断不出来）。
        """
        chart_no = len(self.chart_spec["deck"]["slides"])
        measured = {"elements": [
            {"id": f"s{chart_no}.chart", "slide": chart_no, "role": "chart",
             "x": 84, "y": 500, "w": 1432, "h": 330, "chartReady": "error:render",
             "visible": True}],
            "images": [], "fonts": {}}
        problems = check.check(self.chart_spec, self.chart_path, tokens=self.tokens,
                               measured=measured)
        self._assert_reports(problems, "G2 渲染失败", "④ 图表就绪")

    def test_chart_data_shape_is_required(self) -> None:
        """变异：把某条数据的 value 改成非数字 → check 必须报出来（数据错才是真错）。"""
        spec = copy.deepcopy(self.chart_spec)
        spec["deck"]["slides"][-1]["data"][0]["value"] = "三十二"
        problems = self._problems(spec, self.chart_html)
        self.assertTrue(any("value" in p for p in problems), problems)

    def test_chart_label_must_not_be_empty(self) -> None:
        """变异：标签清空 → 轴上会缺一个标签。"""
        spec = copy.deepcopy(self.chart_spec)
        spec["deck"]["slides"][-1]["data"][0]["label"] = ""
        problems = self._problems(spec, self.chart_html)
        self.assertTrue(any("label" in p for p in problems), problems)

    def test_chart_riso_mutation_is_caught(self) -> None:
        """变异：往真实的 chartwrap 容器里塞一个 riso 元素。"""
        mutated, count = re.subn(
            r'(<div class="chartwrap"[^>]*>)',
            r'\1<div class="riso"><b class="a">X</b></div>', self.chart_html, count=1)
        self.assertEqual(count, 1, "产物里没找到 chartwrap —— render.py 改格式了")
        problems = self._problems(self.chart_spec, mutated)
        self._assert_reports(problems, "错位叠印", "④ 图表区无错位")



class TestVisualDecisionAdvisory(unittest.TestCase):
    """没做视觉决定的内容页要被点名（提示，不阻塞）。

    "一页三条结论"确实不必配图 —— 所以不阻塞；但必须**被决定过**：
    `visual: {"kind": "none"}` 就是显式决定。这条提示是"配图与元素一直没人主动提"
    唯一能被看见的地方。
    """

    def test_silent_pages_are_named_and_decided_pages_are_not(self) -> None:
        deck = {"slides": [
            {"type": "content-text", "title": "没决定", "bullets": ["a", "b", "c"]},
            {"type": "content-text", "title": "决定了", "bullets": ["a", "b", "c"],
             "visual": {"kind": "none"}},
            {"type": "timeline", "title": "时间线",
             "nodes": [{"label": "a", "note": "n"}, {"label": "b", "note": "n"},
                       {"label": "c", "note": "n"}]},
            {"type": "two-column", "title": "双栏",
             "columns": [{"title": "左", "bullets": ["a", "b"]},
                         {"title": "右", "bullets": ["c", "d"]}]},
            {"type": "content-text", "title": "两条不用图", "bullets": ["a", "b"]},
        ]}
        notes = check._visual_decision_notes(deck)
        self.assertEqual(len(notes), 1, notes)
        self.assertIn("第 1 页", notes[0])
        self.assertIn("第 3 页", notes[0])
        self.assertIn("第 4 页", notes[0])
        self.assertNotIn("第 2 页", notes[0])
        self.assertNotIn("第 5 页", notes[0])

    def test_all_decided_is_silent(self) -> None:
        deck = {"slides": [{"type": "content-text", "title": "t",
                            "bullets": ["a", "b", "c"],
                            "visual": {"kind": "none"}}]}
        self.assertEqual(check._visual_decision_notes(deck), [])



class TestPageBox(unittest.TestCase):
    """页盒差 1px 就够：导出 PDF 每页溢出一张，而屏幕上一点看不出来。

    实测：皮肤给 `.slide` 加 1px 上边框 → 页盒 901px → 17 页的 deck 导成 34 页。
    """

    def test_page_box_off_by_one_pixel_is_reported(self) -> None:
        notes = check._check_page_box({"slides": [{"w": 1600, "h": 901}]})
        self.assertEqual(len(notes), 1, notes)
        self.assertIn("901", notes[0])
        self.assertIn("溢到下一张", notes[0])

    def test_exact_page_box_is_silent(self) -> None:
        self.assertEqual(
            check._check_page_box({"slides": [{"w": 1600, "h": 900},
                                               {"w": 1600, "h": 900}]}), [])


class TestGridAnchorScope(unittest.TestCase):
    """锚点门只管**页面级**锚点；卡片 / 时间线节点内部不比整页网格。

    实测误伤：右栏卡片内容 x=832.5（网格列 812）、时间线节点标签 x=113 —— 都是组件
    盒子的内缩。拿它们比整页网格，会让人以为"皮肤全歪了"，然后把整个门忽略掉。
    """

    def test_container_children_are_not_compared_to_the_page_grid(self) -> None:
        measured = {"elements": [
            {"id": "s1.col1.title", "role": "subtitle", "slide": 1, "x": 832.5},
            {"id": "s1.node2.label", "role": "subtitle", "slide": 1, "x": 113.0},
        ]}
        self.assertEqual(check._check_grid_alignment(measured), [])

    def test_top_level_anchor_drift_is_still_reported(self) -> None:
        measured = {"elements": [
            {"id": "s1.subtitle", "role": "subtitle", "slide": 1, "x": 113.0},
        ]}
        notes = check._check_grid_alignment(measured)
        self.assertEqual(len(notes), 1, notes)
        self.assertIn("没吸附到网格列", notes[0])
        self.assertIn("x=113", notes[0])


if __name__ == "__main__":
    unittest.main()


class TestFullPageImageRoleAware(unittest.TestCase):
    """全页图禁令的 role-aware：hero 放行（信息没烤进图里），其余照堵。"""

    @staticmethod
    def _measured(w: float, h: float, slide: int = 1, role: str = "image") -> dict:
        return {"elements": [{"role": role, "slide": slide, "w": w, "h": h}]}

    HERO_DECK = {"slides": [{"type": "content-image", "layout": "hero",
                             "image": "x.png"}]}
    PLAIN_DECK = {"slides": [{"type": "content-image", "layout": "visual-right",
                              "image": "x.png"}]}

    def test_non_hero_giant_image_still_blocks(self) -> None:
        """非 hero 版式图盖满整页：照旧阻塞 —— 守卫没有失牙。"""
        problems = check._check_full_page_image(
            self._measured(1600, 900), self.PLAIN_DECK)
        self.assertTrue(problems, "全页图禁令被静默解除了")

    def test_hero_giant_image_passes(self) -> None:
        """hero 布局：图是主角、标题/条目仍是真 DOM 文本 —— 放行。"""
        self.assertEqual(
            check._check_full_page_image(self._measured(1600, 900), self.HERO_DECK),
            [])

    def test_hero_does_not_excuse_logo(self) -> None:
        """logo 永不放行：品牌标盖满整页没有合法场景。"""
        problems = check._check_full_page_image(
            self._measured(1600, 900, role="logo"), self.HERO_DECK)
        self.assertTrue(problems, "hero 页的 logo 盖满整页居然过了")

    def test_hero_on_other_page_does_not_excuse(self) -> None:
        """hero 声明只豁免自己那页 —— 别页的大图不受牵连。"""
        deck = {"slides": [
            {"type": "content-image", "variant": "hero", "image": "x.png"},
            {"type": "content-image", "variant": "even", "image": "y.png"}]}
        problems = check._check_full_page_image(
            self._measured(1600, 900, slide=2), deck)
        self.assertTrue(problems)


class TestTypeSizeNotes(unittest.TestCase):
    """字号体检（`check._check_type_size`）—— 四条线各自会开口，且**正确的大字不误报**。

    为什么这份测试重要：字号偏大能长期存在，正是因为“装得下就没人报错”。所以这一项
    一半在测“会报”，另一半在测“封面/宣言页的大字不许报” —— 只测前者会把作者逼到
    永远不敢用大字。
    """

    # 那组“海报尺度”字号（= 用户实测产物里的真实值）
    TOKENS = {"type": {
        "cover": 128, "compact": 96, "small": 84, "end": 128, "subtitle": 36,
        "bulletLarge": 46, "bullet": 32, "bulletSmall": 26, "colTitle": 40,
        "nodeLabel": 28, "nodeNote": 22, "chartValue": 20, "chartLabel": 18,
        "caption": 24, "foot": 20}}

    @staticmethod
    def _measured(titles: dict[int, float], bullets: dict[int, list[float]]) -> dict:
        els = [
            {"slide": n, "role": "title", "fontSize": px, "x": 84, "y": 132}
            for n, px in titles.items()]
        els += [
            {"slide": n, "role": "bullet", "fontSize": px, "x": 84, "y": 300 + i * 80}
            for n, pxs in bullets.items() for i, px in enumerate(pxs)]
        return {"elements": els}

    def _notes(self, titles, bullets, kinds):
        deck = {"slides": [{"type": k} for k in kinds]}
        return check._check_type_size(self._measured(titles, bullets), deck,
                                      self.TOKENS)

    def test_content_title_at_cover_scale_is_reported(self) -> None:
        notes = self._notes({1: 128, 2: 96}, {}, ["title", "content-text"])
        text = " ".join(notes)
        self.assertIn("封面尺度", text)
        self.assertIn("第2页", text)
        self.assertNotIn("第1页", text, "封面用 128 是对的，不该被点名")
        self.assertIn("type.compact", text, "提示必须点名是哪一档，否则作者要自己反查")

    def test_cover_and_end_are_exempt(self) -> None:
        # 封面（第1页）与封底（末页）用 128 是对的。注意 slide 编号必须真的
        # 落在 spec 里 —— 编号超出 spec 的标题元素按“未知版式”处理（宁报不漏）。
        self.assertEqual(self._notes({1: 128, 2: 128}, {}, ["title", "end"]), [])

    def test_dense_page_with_poster_body_is_reported(self) -> None:
        notes = self._notes({2: 84}, {2: [46] * 5}, ["title", "content-text"])
        self.assertIn("宣言档", " ".join(notes))

    def test_statement_page_with_big_body_is_fine(self) -> None:
        """1~2 条的宣言页用大字号是对的 —— 不许报“条目多”。"""
        notes = self._notes({2: 84}, {2: [46, 46]}, ["title", "content-text"])
        self.assertNotIn("宣言档", " ".join(notes))

    def test_median_is_weighted_by_bullets(self) -> None:
        """少数宣言页不该把整体结论顶成“偏大”（按条目加权）。"""
        notes = self._notes(
            {2: 84, 3: 84},
            {2: [46, 46], 3: [24] * 8},
            ["title", "content-text", "content-text"])
        self.assertNotIn("整体偏大", " ".join(notes))

    def test_mostly_big_body_is_reported(self) -> None:
        notes = self._notes({2: 84}, {2: [46] * 6}, ["title", "content-text"])
        self.assertIn("整体偏大", " ".join(notes))

    def test_missing_slides_does_not_throw(self) -> None:
        """spec 形状不对时不许抛 —— check 是交付前最后一道，它崩了比漏报更糟。"""
        self.assertEqual(
            check._check_type_size({"elements": [{"slide": 1, "role": "title",
                                                  "fontSize": 200}]},
                                   {}, self.TOKENS), [])
