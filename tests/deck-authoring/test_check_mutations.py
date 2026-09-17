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
# 测试自有夹具：风格与内容样本都放在 tests/ 下，**不随 skill 发布** ——
# 可拷贝的模板必然变成默认答案（每份 deck 长得一样）。
FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
# 夹具当"额外风格根"：工具链不内置任何风格（可拷贝的模板必然变成
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
        """真产物跑一遍浏览器，G2 必须真渲染出来（chartReady == ready）。

        为什么必须真浏览器而不是合成 measured：渲染失败会在两处同时出现 ——
        初始化脚本指定的 `renderer` 与这份 UMD bundle 实际带的渲染器不一致
        （bundle 只带 canvas 渲染器，写 `svg` 就运行时抛 registerPlugin），
        而且 chartReady 若没接到 `[data-m]` 元素上，**闸门会静默失效**：
        静态 HTML 里只有容器与 spec，判断不出渲染没渲染。
        这条用例把两件事一起钉住：字段要接到、且真浏览器里必须 ready。
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

        判据是"G2 真渲染出来了"（实测 chartReady 字段），不是"画出来的几何
        服从数据"：几何由 G2 算，而静态 HTML 里只有容器与 spec，后者量不到。
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



class TestRoleNotes(unittest.TestCase):
    """角色门（`check._role_notes`）：不合与重复两件事。

    “每页都长一样”最容易被算出来的那一种：同角色 + 同页型 + 同 layout ——
    观感上就是同一个版式换了两批字。
    """

    def test_mismatch_and_duplicate_are_reported(self) -> None:
        deck = {"slides": [
            {"type": "timeline", "role": "trend"},
            {"type": "two-column", "role": "trend"},
            {"type": "two-column", "role": "risks"},
            {"type": "two-column", "role": "risks"},
        ]}
        notes = check._role_notes(deck)
        self.assertTrue(any("role=trend" in n and "two-column" in n for n in notes),
                        notes)
        self.assertTrue(any("同角色" in n and "第 3 页" in n and "第 4 页" in n
                            for n in notes), notes)

    def test_matching_roles_are_silent(self) -> None:
        deck = {"slides": [
            {"type": "timeline", "role": "trend"},
            {"type": "two-column", "layout": "lean-left", "role": "risks"},
            {"type": "two-column", "layout": "even", "role": "risks"},
        ]}
        self.assertEqual(check._role_notes(deck), [])


class TestCollisionFix(unittest.TestCase):
    """碰撞的修法建议：hero 页必须说"换版式/拆页"，而不是"拉开间距"。

    为什么值得单独钉：hero 的图高是算出来的且已触下限 —— 让人去"拉开间距"等于
    让他把图压成一条，换个难看但过门的结果。修法说错比不说更坏。
    """

    def test_hero_gets_the_layout_switch_advice(self) -> None:
        fix = check._collision_fix("hero")
        self.assertIn("hero", fix)
        self.assertIn("visual-right", fix)
        self.assertIn("拆开", fix)
        self.assertNotIn("拉开间距", fix)

    def test_other_layouts_keep_the_generic_advice(self) -> None:
        for layout in (None, "even", "visual-wide"):
            self.assertIn("拉开间距", check._collision_fix(layout))


class TestContractDrift(unittest.TestCase):
    """契约过期门（`check._check_contract_drift`）：拷进契约的几何 vs 现在量到的几何。

    为什么它值得一道阻塞门：导 PPTX 走的是契约里那份几何，而契约会过期（改字、
    换风格、换台机器字体不同）。那时 HTML 与 PPTX **不一样**，而两边各自都
    "成功"了。实测噪声底是 **0px**（同一份 HTML 量两次、以及契约 vs 现测同一份
    HTML 都是 0）—— 所以卡 1px 是安全的。
    """

    @staticmethod
    def _geo(elements, slides=2):
        return {"geometry": {"slides": [{}] * slides, "elements": elements}}

    @classmethod
    def setUpClass(cls) -> None:
        cls.ELS = [{"id": "s1.title", "x": 84, "y": 100, "w": 700, "h": 90},
                   {"id": "s2.img", "x": 800, "y": 200, "w": 400, "h": 300}]

    def _measured(self, elements, slides=2):
        return {"slides": [{}] * slides, "elements": elements}

    def test_same_source_is_silent(self) -> None:
        self.assertEqual(
            check._check_contract_drift(self._measured(self.ELS),
                                        self._geo(self.ELS)), [])

    def test_sub_pixel_rounding_is_tolerated(self) -> None:
        moved = [dict(self.ELS[0], x=84.5), self.ELS[1]]
        self.assertEqual(
            check._check_contract_drift(self._measured(moved),
                                        self._geo(self.ELS)), [])

    def test_moved_element_names_the_delta_and_the_fix(self) -> None:
        moved = [dict(self.ELS[0], y=142), self.ELS[1]]
        problems = check._check_contract_drift(self._measured(moved),
                                              self._geo(self.ELS))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("s1.title", problems[0])
        self.assertIn("42px", problems[0])
        self.assertIn("--resolved", problems[0], "要给出修法")

    def test_element_missing_on_either_side(self) -> None:
        only_measured = check._check_contract_drift(
            self._measured(self.ELS), self._geo(self.ELS[:1]))
        self.assertTrue(any("不在契约里" in p for p in only_measured), only_measured)
        only_contract = check._check_contract_drift(
            self._measured(self.ELS[:1]), self._geo(self.ELS))
        self.assertTrue(any("找不到" in p for p in only_contract), only_contract)

    def test_page_count_mismatch(self) -> None:
        problems = check._check_contract_drift(self._measured(self.ELS, slides=1),
                                               self._geo(self.ELS, slides=2))
        self.assertTrue(any("页数都对不上" in p for p in problems), problems)

    def test_contract_without_geometry_is_rejected(self) -> None:
        problems = check._check_contract_drift(self._measured(self.ELS), {"trace": []})
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("完整契约", problems[0])


class TestLocalPaths(unittest.TestCase):
    """产物不许带本机绝对路径：图片**阻塞**（拷到别处就裂图），字体是提示。

    分清两类是关键：`fonts.py` 有意用绝对路径（字体在 deck 项目之外），把它当�错
    会让每份带字体的 deck 都报错；而图片的绝对路径**没有任何合法场景** —— 产物
    就是要被拷来拷去的。
    """

    def test_absolute_image_path_blocks_with_the_fix(self) -> None:
        problems, notes = check._check_local_paths('<img src="/Users/me/proj/x.png">')
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("/Users/me/proj/x.png", problems[0])
        self.assertIn("相对路径", problems[0], "要给出修法，不是只说不行")
        self.assertEqual(notes, [])

    def test_file_url_blocks(self) -> None:
        problems, _ = check._check_local_paths('<img src="file:///tmp/a.png">')
        self.assertTrue(any("file://" in p for p in problems), problems)

    def test_file_url_is_not_counted_twice(self) -> None:
        """`file:///tmp/a.png` 只能算一处 —— 当成 file:// 又当成 /tmp/ 会虚报。"""
        problems, _ = check._check_local_paths('<img src="file:///tmp/a.png">')
        self.assertEqual(len(problems), 1, problems)

    def test_font_url_is_a_note_and_names_embed(self) -> None:
        page = "<style>@font-face{src:url('/Users/me/Library/Fonts/x.ttf')}</style>"
        problems, notes = check._check_local_paths(page)
        self.assertEqual(problems, [], "字体走绝对路径是设计，不能阻塞")
        self.assertEqual(len(notes), 1, notes)
        self.assertIn("--embed", notes[0], "提示要说清怎么变成自包含单文件")

    def test_clean_products_stay_silent(self) -> None:
        for page in ('<img src="assets/x.png">',
                     '<img src="data:image/png;base64,AAAA">',
                     "<p>没有任何路径</p>"):
            self.assertEqual(check._check_local_paths(page), ([], []), page)


class TestReuseNotes(unittest.TestCase):
    """同一张素材用在多页 —— 提示级（合理复用是决定，但得说出来）。"""

    def test_same_asset_on_two_pages_is_flagged_once(self) -> None:
        deck = {"slides": [{"image": "assets/a.png"}, {"image": "assets/a.png"},
                           {"image": "assets/b.png"}]}
        notes = check._reuse_notes(deck)
        self.assertEqual(len(notes), 1, notes)
        self.assertIn("第1页、第2页", notes[0])
        self.assertIn("a.png", notes[0])

    def test_different_slot_ratios_are_called_out(self) -> None:
        deck = {"slides": [
            {"image": "a.png", "visual": {"kind": "evidence_image", "ratio": "3:2"}},
            {"image": "a.png", "visual": {"kind": "evidence_image", "ratio": "1:1"}}]}
        notes = check._reuse_notes(deck)
        self.assertIn("比例不一样", notes[0])
        self.assertIn("3:2", notes[0])
        self.assertIn("1:1", notes[0])

    def test_single_use_and_empty_deck_are_silent(self) -> None:
        self.assertEqual(check._reuse_notes({"slides": [{"image": "a.png"},
                                                       {"image": "b.png"}]}), [])
        self.assertEqual(check._reuse_notes({}), [])
        self.assertEqual(check._reuse_notes({"slides": [None, "不是字典"]}), [])


class TestStyleRules(unittest.TestCase):
    """风格语法门（`check._check_style_rules`）：风格声明的语法 vs 实测。

    钉两件事：**没声明就不检查**（门不能替风格发明语法），以及声明与实测不一致时
    提示里必须有**页号 + 元素 + 实测值**（不然不知道该改哪个选择器）。
    """

    @staticmethod
    def _el(eid: str, slide: int = 3, **kw) -> dict:
        base = {"id": eid, "slide": slide, "visible": True,
                "borderRadius": "0px", "boxShadow": "none",
                "backgroundImage": "none", "fontWeight": 400, "textW": 80.0}
        base.update(kw)
        return base

    def test_without_declaration_nothing_is_checked(self) -> None:
        rounded = {"elements": [self._el("s3.card", borderRadius="12px")]}
        self.assertEqual(check._check_style_rules(rounded, {}), [])
        self.assertEqual(check._check_style_rules(rounded, {"rules": {}}), [])
        self.assertEqual(check._check_style_rules(rounded, None), [])

    def test_square_declaration_catches_radius_and_percent(self) -> None:
        measured = {"elements": [self._el("s3.card", borderRadius="12px"),
                                 self._el("s3.badge", borderRadius="50%"),
                                 self._el("s3.plain")]}
        notes = check._check_style_rules(measured, {"rules": {"corners": "square"}})
        self.assertEqual(len(notes), 1, notes)
        self.assertIn("s3.card", notes[0])
        self.assertIn("12px", notes[0])
        self.assertIn("50%", notes[0], "百分比圆角换不成像素，但确实是圆角")

    def test_shadow_none_and_soft_are_different_checks(self) -> None:
        measured = {"elements": [
            self._el("s3.quote", boxShadow="rgba(0,0,0,.2) 0px 4px 0px 0px")]}
        none_notes = check._check_style_rules(measured, {"rules": {"shadow": "none"}})
        soft_notes = check._check_style_rules(measured, {"rules": {"shadow": "soft"}})
        self.assertEqual(len(none_notes), 1, none_notes)
        self.assertIn("换回描边/底色", none_notes[0])
        self.assertEqual(len(soft_notes), 1, soft_notes)
        self.assertIn("硬边", soft_notes[0], "blur 0 = 硬边：soft 声明下也要报")
        blurred = {"elements": [self._el("s3.quote",
                                       boxShadow="rgba(0,0,0,.2) 0px 4px 8px 0px")]}
        self.assertEqual(check._check_style_rules(blurred, {"rules": {"shadow": "soft"}}), [])

    def test_weight_steps_counts_only_text_elements(self) -> None:
        measured = {"elements": [
            self._el("s3.t", fontWeight=400),
            self._el("s3.u", fontWeight=700),
            self._el("s3.deco", fontWeight=900, textW=0.0)]}
        self.assertEqual(
            check._check_style_rules(measured, {"rules": {"weightSteps": 2}}), [])
        notes = check._check_style_rules(measured, {"rules": {"weightSteps": 1}})
        self.assertEqual(len(notes), 1, notes)
        self.assertIn("2 档字重", notes[0])

    def test_gradients_declaration(self) -> None:
        measured = {"elements": [self._el(
            "s3.band", backgroundImage="linear-gradient(90deg, #111, #333)")]}
        notes = check._check_style_rules(measured, {"rules": {"gradients": "none"}})
        self.assertEqual(len(notes), 1, notes)
        self.assertIn("s3.band", notes[0])

    def test_bad_declaration_is_reported_before_judging(self) -> None:
        measured = {"elements": [self._el("s3.card", borderRadius="12px")]}
        notes = check._check_style_rules(
            measured, {"rules": {"corners": "圆角", "sizeFloor": 16}})
        self.assertEqual(len(notes), 2, notes)
        joined = " ".join(notes)
        self.assertIn("corners", joined)
        self.assertIn("sizeFloor", joined, "不认识的键要说出来（封闭键集）")
        self.assertNotIn("12px", joined, "声明写错了就不拿它去判别人")

    def test_broken_measured_values_are_skipped(self) -> None:
        measured = {"elements": [self._el("s3.a", borderRadius=None),
                                 self._el("s3.b", borderline=1),
                                 {"id": "s3.c"},
                                 "不是字典"]}
        rules = {"rules": {"corners": "square", "shadow": "none",
                           "gradients": "none", "weightSteps": 2}}
        self.assertEqual(check._check_style_rules(measured, rules), [])

    def test_invisible_elements_do_not_count(self) -> None:
        measured = {"elements": [self._el("s3.gone", borderRadius="12px",
                                         visible=False)]}
        self.assertEqual(
            check._check_style_rules(measured, {"rules": {"corners": "square"}}), [])


class TestContentBudget(unittest.TestCase):
    """写前预算的事后核对（`check._content_budget_notes`）。

    它的价值全在**措辞**上：必须把"先改文案 / 换结构"说出来，且**不提缩字号**
    （修复梯里缩字号排第 13 位，而人被装不下追着时最容易先压字号）。
    """

    TOKENS = {"type": {"compact": 96.0, "bullet": 32.0, "colTitle": 40.0,
                       "nodeLabel": 28.0, "nodeNote": 22.0,
                       "cover": 128.0, "end": 128.0}}

    def test_too_many_items_reports_the_limit(self) -> None:
        deck = {"slides": [{"type": "content-image", "layout": "visual-wide",
                            "title": "标题",
                            "bullets": ["短"] * 9}]}
        notes = check._content_budget_notes(deck, self.TOKENS)
        self.assertEqual(len(notes), 1, notes)
        self.assertIn("9 条", notes[0])
        self.assertIn("8 条", notes[0])
        self.assertNotIn("缩字号", notes[0].replace("缩字号是修复顺序第 13 位", ""))

    def test_overlong_item_names_the_worst_one(self) -> None:
        long = "这是一条明显超出这一栏宽度的条目内容"
        deck = {"slides": [{"type": "content-image", "layout": "visual-wide",
                            "title": "标题", "bullets": [long, "短"]}]}
        notes = check._content_budget_notes(deck, self.TOKENS)
        self.assertEqual(len(notes), 1, notes)
        self.assertIn("改短文案", notes[0])
        self.assertIn(long[:10], notes[0])

    def test_within_budget_is_silent(self) -> None:
        deck = {"slides": [{"type": "content-text", "title": "短标题",
                            "bullets": ["一", "二", "三"]}]}
        self.assertEqual(check._content_budget_notes(deck, self.TOKENS), [])

    def test_missing_tokens_is_silent(self) -> None:
        deck = {"slides": [{"type": "content-text", "title": "x" * 200}]}
        self.assertEqual(check._content_budget_notes(deck, None), [])


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
