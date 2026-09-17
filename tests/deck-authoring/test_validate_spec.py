#!/usr/bin/env python3
"""validate_spec.py 的回归测试：字段集必须**真的**封闭。

## 为什么这条要单独测

`check.py` 只主动拦 `color` 一个字段，其余未知键是**静默忽略**的（这一点我实测过：
塞 `fontSize` / `x` / `y` / `bogusTop` 进去，产物毫无变化、也不报错）。
于是"字段集封闭"这件事只由 `validate_spec.py` 兜着 —— 一个只会说 ✓ 的校验器和
没有校验器在结果上一样，所以下面每条都是**造一个越界样例**，断言它被指名报出来。

反向也测：合法的 spec（demo + 七种版式各一页）必须过 —— 校验器不能对什么都说违规。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/deck-authoring/test_validate_spec.py
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
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
TOKENS = os.path.join(FIXTURES_DIR, "styles", "swiss-grid", "style.json")
DEMO = os.path.join(FIXTURES_DIR, "demo.spec.json")


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


vs = _load("_deck_test_validate_spec", os.path.join(SCRIPTS, "validate_spec.py"))

VALID_SLIDES = [
    {"type": "title", "title": "T", "subtitle": "s"},
    {"type": "content-text", "title": "C", "bullets": ["a"]},
    {"type": "content-image", "title": "I", "bullets": ["a"], "image": "x.png"},
    {"type": "two-column", "title": "W",
     "columns": [{"title": "A", "bullets": ["a"]}, {"title": "B", "bullets": ["b"]}]},
    {"type": "timeline", "title": "L", "nodes": [{"label": "Q1", "note": "n"}]},
    {"type": "chart", "title": "G", "chart": "bar",
     "data": [{"label": "A", "value": 10}], "unit": "%"},
    {"type": "end", "title": "E"},
]


def _spec(slides=None) -> dict:
    # 色板名**不写死**：从真实的风格 token 里取。写死过 "vivid"，孔版那套一删
    # 这里就开始报 BAD_COLOR_SET —— 于是“合法 spec 必须全过”这条用例变成在报
    # 一个与本意无关的错。
    with open(TOKENS, encoding="utf-8") as fh:
        color_set = next(iter(json.load(fh)["colorSets"]))
    # deck.style 必填（工具链不内置任何风格）—— 合成 spec 也要写它
    return {"deck": {"style": "swiss-grid", "colorSet": color_set, "seed": 7,
                     "title": "t",
                     "slides": copy.deepcopy(slides or VALID_SLIDES)}}


class TestValidateSpec(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with open(TOKENS, encoding="utf-8") as fh:
            cls.color_sets = set(json.load(fh)["colorSets"])

    def _codes(self, spec: dict) -> set[str]:
        """跑校验，返回所有 error 的 code。"""
        return {i["code"] for i in vs.validate(spec, self.color_sets).errors}

    def _messages(self, spec: dict) -> str:
        return " ".join(i["message"] for i in vs.validate(spec, self.color_sets).items)

    # ── 正向：合法的必须过 ────────────────────────────────────────────────

    def test_demo_spec_passes(self) -> None:
        with open(DEMO, encoding="utf-8") as fh:
            demo = json.load(fh)
        self.assertEqual(vs.validate(demo, self.color_sets).errors, [],
                         "仓库自带的 demo spec 本应通过")

    def test_all_documented_slide_types_pass(self) -> None:
        """七种版式各来一页，必须全过 —— 校验器不能对合法输入也报。"""
        self.assertEqual(self._codes(_spec()), set(),
                         f"合法 spec 被判违规：{self._messages(_spec())}")

    # ── 反向：越界必须被指名报出 ──────────────────────────────────────────

    def test_unknown_deck_field_is_rejected(self) -> None:
        bad = _spec()
        bad["deck"]["bogusTop"] = 123
        self.assertIn("UNKNOWN_FIELD", self._codes(bad))

    def test_unknown_slide_field_is_rejected(self) -> None:
        bad = _spec()
        bad["deck"]["slides"][0]["whatever"] = 1
        self.assertIn("UNKNOWN_FIELD", self._codes(bad))

    def test_coordinate_fields_get_targeted_error(self) -> None:
        """坐标要报成 COORD_FIELD（专门说明），不是笼统的 UNKNOWN_FIELD。"""
        for key in ("x", "y", "dx", "rotation", "width"):
            with self.subTest(field=key):
                bad = _spec()
                bad["deck"]["slides"][0][key] = 1
                self.assertIn("COORD_FIELD", self._codes(bad),
                              f"{key} 应被当作坐标字段报出来")

    def test_size_fields_get_targeted_error(self) -> None:
        for key in ("fontSize", "size", "font"):
            with self.subTest(field=key):
                bad = _spec()
                bad["deck"]["slides"][0][key] = 1
                self.assertIn("SIZE_FIELD", self._codes(bad),
                              f"{key} 应被当作字号字段报出来")

    def test_color_value_fields_get_targeted_error(self) -> None:
        """主/副色 / 叠印墨这些**名字**也不能出现在 spec 里。"""
        for key in ("primary", "secondary", "background", "ink", "inkText"):
            with self.subTest(field=key):
                bad = _spec()
                bad["deck"]["slides"][0][key] = "#FF0000"
                self.assertIn("COLOR_FIELD", self._codes(bad),
                              f"{key} 应被当作色值字段报出来")

    def test_color_must_be_overprint(self) -> None:
        """`color` 是唯一允许的"样式"字段，且只接受 "overprint"。"""
        ok = _spec()
        ok["deck"]["slides"][0]["color"] = "overprint"
        self.assertEqual(self._codes(ok), set(), "color='overprint' 应当合法")

        bad = _spec()
        bad["deck"]["slides"][0]["color"] = "#FF0000"
        self.assertIn("BAD_COLOR", self._codes(bad))

    def test_unknown_slide_type_is_rejected(self) -> None:
        bad = _spec()
        bad["deck"]["slides"][0]["type"] = "not-a-real-type"
        self.assertIn("BAD_TYPE", self._codes(bad))

    def test_unknown_color_set_is_rejected(self) -> None:
        bad = _spec()
        bad["deck"]["colorSet"] = "no-such-palette"
        self.assertIn("BAD_COLOR_SET", self._codes(bad))

    def test_nested_item_unknown_field_is_rejected(self) -> None:
        """嵌套列表也要管：columns / nodes / data 的元素字段同样是封闭的。"""
        cases = [
            ("columns", 3, "extra"),   # index 3 是 two-column 页
            ("nodes", 4, "extra"),     # index 4 是 timeline 页
            ("data", 5, "extra"),      # index 5 是 chart 页
        ]
        for key, index, field in cases:
            with self.subTest(list_key=key):
                bad = _spec()
                bad["deck"]["slides"][index][key][0][field] = 1
                self.assertIn("UNKNOWN_FIELD", self._codes(bad),
                              f"{key}[0].{field} 没有被报出来")

    def test_missing_tokens_skips_colorset_check_not_whole_validation(self) -> None:
        """读不到 token 时只跳过 colorSet 那一条，其余照样验 —— 别整份放行。"""
        bad = _spec()
        bad["deck"]["slides"][0]["fontSize"] = 120
        codes = {i["code"] for i in vs.validate(bad, None).errors}
        self.assertIn("SIZE_FIELD", codes, "color_sets=None 时不该把整份 spec 放过去")
        self.assertNotIn("BAD_COLOR_SET", codes)



class TestRequiredFields(unittest.TestCase):
    """条件必填：版式已经说了要图，就不许把图省掉。

    **实测撞到的**：字段集只查"允许哪些键"，不查"哪些键必需" —— 所以
    `content-image` 不给 `image` 能一路过校验，然后渲染器直接
    `KeyError: 'image'` 崩栈。一个未处理的栈，不是一句人话。

    这条与"图片该要就要，别为了省事少要"是同一件事：版式选了要图的那一种，
    图就不该是可省的。
    """

    def setUp(self) -> None:
        with open(TOKENS, encoding="utf-8") as fh:
            self.color_sets = set(json.load(fh)["colorSets"])

    def _codes(self, spec: dict) -> set[str]:
        return {i["code"] for i in vs.validate(spec, self.color_sets).errors}

    def test_content_image_without_image_is_blocked(self) -> None:
        self.assertIn("MISSING_FIELD",
                      self._codes(_spec([{"type": "content-image", "title": "没图"}])))

    def test_content_image_with_image_passes(self) -> None:
        self.assertEqual(
            self._codes(_spec([{"type": "content-image", "title": "有图",
                                "image": "x.png"}])), set())

    def test_empty_image_name_is_also_blocked(self) -> None:
        """空字符串不算给了图 —— 它照样会渲出一张裂图。"""
        self.assertIn("MISSING_FIELD",
                      self._codes(_spec([{"type": "content-image", "title": "空",
                                          "image": ""}])))

    def test_error_says_what_to_do_instead(self) -> None:
        """报错必须给出路，否则读者只知道"错了"、不知道"那我怎么办"。"""
        issues = vs.validate(_spec([{"type": "content-image", "title": "没图"}]),
                             self.color_sets)
        msg = " ".join(i["message"] for i in issues.items)
        self.assertIn("content-text", msg)

    def test_only_the_layouts_that_need_it_are_required(self) -> None:
        """别的版式不许被顺手要求填图 —— 误伤会把"必填"变成噪音。"""
        self.assertEqual(
            self._codes(_spec([{"type": "content-text", "title": "纯文字",
                                "bullets": ["a", "b"]}])), set())


class TestVisualCarrier(unittest.TestCase):
    """每页的视觉载体（`visual`）：四档合法 + 自相矛盾当场拦。

    这一栏存在的理由是"配图与元素一直没人主动提"—— 不写下来就等于没决定。
    形状与一致性归输入层（这里），产物层只负责点名"没决定的页"。
    """

    @staticmethod
    def _spec(slide: dict) -> dict:
        return {"deck": {"style": "swiss-grid", "colorSet": "blue", "seed": 1,
                         "title": "t", "slides": [slide]}}

    def _codes(self, slide: dict) -> set[str]:
        return {i["code"] for i in vs.validate(self._spec(slide), None).errors}

    def test_three_kinds_are_accepted(self) -> None:
        slides = [
            {"type": "content-text", "title": "t", "bullets": ["a"],
             "visual": {"kind": "none", "note": "三条结论靠文字立住"}},
            {"type": "chart", "title": "t", "chart": "bar",
             "data": [{"label": "甲", "value": 1}],
             "visual": {"kind": "data", "intent": "对比"}},
            {"type": "content-image", "title": "t", "image": "a.png",
             "visual": {"kind": "evidence_image"}},
        ]
        for slide in slides:
            codes = self._codes(slide)
            self.assertNotIn("BAD_VISUAL", codes, slide)
            self.assertNotIn("UNKNOWN_FIELD", codes, slide)

    def test_contradiction_between_carrier_and_layout_is_an_error(self) -> None:
        """声明要用图/图表，版式却装不下 —— 这是客观错误，不是审美。"""
        cases = [
            ({"type": "content-text", "title": "t", "bullets": ["a"],
              "visual": {"kind": "evidence_image"}}, "BAD_VISUAL"),
            ({"type": "content-text", "title": "t", "bullets": ["a"],
              "visual": {"kind": "data"}}, "BAD_VISUAL"),
            ({"type": "content-image", "title": "t", "image": "a.png",
              "visual": {"kind": "none"}}, "BAD_VISUAL"),
            ({"type": "content-text", "title": "t", "bullets": ["a"],
              "visual": {"kind": "illustration"}}, "BAD_VISUAL"),
            ({"type": "content-text", "title": "t", "bullets": ["a"],
              "visual": {"intent": "想要图"}}, "BAD_VISUAL"),
            ({"type": "content-text", "title": "t", "bullets": ["a"],
              "visual": {"kind": "none", "priority": "primary"}}, "UNKNOWN_FIELD"),
            ({"type": "content-text", "title": "t", "bullets": ["a"],
              "visual": "evidence_image"}, "BAD_VISUAL"),
        ]
        for slide, code in cases:
            self.assertIn(code, self._codes(slide), slide)

    def test_page_may_omit_visual_entirely(self) -> None:
        """不写不报错（写不写是作者的自由）—— 但 check 会点名，见 test_check_mutations。"""
        codes = self._codes({"type": "content-text", "title": "t",
                             "bullets": ["a", "b", "c"]})
        self.assertNotIn("BAD_VISUAL", codes)



class TestPageRole(unittest.TestCase):
    """页面角色（`role`）：说这一页"在干什么"，与页型（结构）分开。

    词表是封闭的 —— 拼错的角色名会让它静默失效（配版式、看重复都靠它）。
    类型映射在 layout/roles.py（validate_spec 零依赖，只持名字）；两份的名字
    由下面那条一致性测试钉住。
    """

    @staticmethod
    def _spec(slide: dict) -> dict:
        return {"deck": {"style": "swiss-grid", "colorSet": "blue", "seed": 1,
                         "title": "t", "slides": [slide]}}

    def _codes(self, slide: dict) -> set[str]:
        return {i["code"] for i in vs.validate(self._spec(slide), None).errors}

    def test_every_page_type_accepts_a_role(self) -> None:
        slides = [
            {"type": "title", "title": "t", "role": "cover"},
            {"type": "content-text", "title": "t", "bullets": ["a"],
             "role": "breakdown"},
            {"type": "content-image", "title": "t", "image": "x.png",
             "visual": {"kind": "evidence_image", "ratio": "3:2"}, "role": "context_image"},
            {"type": "two-column", "title": "t",
             "columns": [{"bullets": ["a"]}], "role": "comparison"},
            {"type": "timeline", "title": "t", "nodes": [{"label": "a"}],
             "role": "process"},
            {"type": "chart", "title": "t", "chart": "bar",
             "data": [{"label": "a", "value": 1}], "role": "metric"},
            {"type": "end", "title": "t", "role": "closing"},
        ]
        for slide in slides:
            self.assertNotIn("BAD_ROLE", self._codes(slide), slide["type"])
            self.assertNotIn("BAD_TYPE", self._codes(slide), slide["type"])

    def test_unknown_role_is_an_error_with_the_vocabulary(self) -> None:
        codes = self._codes({"type": "content-text", "title": "t",
                             "bullets": ["a"], "role": "metricks"})
        self.assertIn("BAD_ROLE", codes)

    def test_non_string_role_is_an_error(self) -> None:
        codes = self._codes({"type": "content-text", "title": "t",
                             "bullets": ["a"], "role": 7})
        self.assertIn("BAD_ROLE", codes)

    def test_role_vocabulary_matches_the_mapping_module(self) -> None:
        """两份名字必须一致（一份在零依赖的 schema，一份带类型映射）。"""
        pkg = _load("_deck_test_role_pkg",
                    os.path.join(SCRIPTS, "layout", "__init__.py"))
        self.assertEqual(tuple(vs.ROLES), tuple(pkg.roles.ROLES),
                         "validate_spec.ROLES 与 layout/roles.py 漂移了")


class TestVisualRatio(unittest.TestCase):
    """要图就必须**写清比例**（`visual.ratio`）—— 这是规则，不是建议。

    出图工具的默认比例各家不同（Midjourney 1:1 / SD 看 sampler / DALL·E 只认 prompt），
    而槽位高度按 ratio 算：不写下来等于没定，出回来再改成本高得多。
    """

    @staticmethod
    def _spec(visual: dict, kind: str = "content-image") -> dict:
        slide = {"type": kind, "title": "图页", "visual": visual}
        if kind == "content-image":
            slide["image"] = "a.png"
        else:
            slide["bullets"] = ["一条"]
        return {"deck": {"style": "swiss-grid", "colorSet": "blue", "seed": 1,
                         "title": "t", "slides": [slide]}}

    def _codes(self, visual: dict, kind: str = "content-image") -> set:
        return {i["code"] for i in vs.validate(self._spec(visual, kind), None).errors}

    def test_ratio_is_required_when_an_image_is_declared(self) -> None:
        self.assertIn("MISSING_RATIO", self._codes({"kind": "evidence_image"}))

    def test_common_ratios_are_accepted(self) -> None:
        for ratio in ("3:2", "4:3", "1:1", "16:9", "2:1"):
            codes = self._codes({"kind": "evidence_image", "ratio": ratio})
            self.assertNotIn("MISSING_RATIO", codes, ratio)
            self.assertNotIn("BAD_RATIO", codes, ratio)

    def test_bad_ratio_shapes_are_rejected(self) -> None:
        for ratio in ("1280x853", "3/2", "3:", ":2", "0:1", "9:1", "a:b", ""):
            self.assertIn("BAD_RATIO",
                          self._codes({"kind": "evidence_image", "ratio": ratio}),
                          ratio)

    def test_no_image_kind_needs_no_ratio(self) -> None:
        codes = self._codes({"kind": "none"}, kind="content-text")
        self.assertNotIn("MISSING_RATIO", codes)


if __name__ == "__main__":
    unittest.main()


class TestLayoutField(unittest.TestCase):
    """`layout` 是**自由字符串**（结构布局是渲染器能力，其余交给 skin）。"""

    @classmethod
    def setUpClass(cls) -> None:
        with open(TOKENS, encoding="utf-8") as fh:
            cls.color_sets = set(json.load(fh)["colorSets"])

    def _codes(self, spec: dict) -> set[str]:
        return {i["code"] for i in vs.validate(spec, self.color_sets).errors}

    @staticmethod
    def _slide(kind: str, layout) -> dict:
        base = {"type": kind, "title": "页", "layout": layout}
        if kind == "content-image":
            base.update({"bullets": ["a"], "image": "x.png"})
        else:
            base["columns"] = [{"title": "A", "bullets": ["a"]},
                               {"title": "B", "bullets": ["b"]}]
        return base

    def test_structural_layouts_pass(self) -> None:
        for kind, lay in (("content-image", "visual-left"), ("content-image", "even"),
                          ("content-image", "hero"), ("two-column", "lean-right")):
            with self.subTest(lay=lay):
                codes = self._codes(_spec([self._slide(kind, lay)]))
                self.assertNotIn("BAD_LAYOUT", codes)
                self.assertNotIn("UNKNOWN_FIELD", codes, "layout 不在封闭字段集里")

    def test_custom_layout_name_passes(self) -> None:
        """作者自造布局名合法（渲染套缺省结构 + data-layout，skin 负责排）。"""
        codes = self._codes(_spec([self._slide("content-image", "poster-split")]))
        self.assertNotIn("BAD_LAYOUT", codes, "自造布局名被当成错误拦住了")

    def test_auto_is_rejected(self) -> None:
        """auto 不被接受：布局由 spec 作者声明，没有"实测选布局"这条路。"""
        codes = self._codes(_spec([self._slide("content-image", "auto")]))
        self.assertIn("BAD_LAYOUT", codes)

    def test_non_string_is_rejected(self) -> None:
        codes = self._codes(_spec([self._slide("content-image", 3)]))
        self.assertIn("BAD_LAYOUT", codes)

    def test_variant_field_is_gone_with_a_hint(self) -> None:
        slide = self._slide("content-image", "even")
        slide["variant"] = "even"
        result = vs.validate(_spec([slide]), self.color_sets)
        codes = {i["code"] for i in result.errors}
        self.assertIn("UNKNOWN_FIELD", codes, "旧 variant 字段还在放行")
        hints = " ".join(i["message"] for i in result.errors)
        self.assertIn("layout", hints, "旧字段的错误没指路新字段")


class TestColorSetRequired(unittest.TestCase):
    """colorSet 必填具名（写 auto/mood 一律判失败）。"""

    @classmethod
    def setUpClass(cls) -> None:
        with open(TOKENS, encoding="utf-8") as fh:
            cls.color_sets = set(json.load(fh)["colorSets"])

    def _codes(self, deck_extra: dict) -> set[str]:
        deck = {"title": "t", "colorSet": "blue",
                "slides": [{"type": "title", "title": "封面"}]}
        deck.update(deck_extra)
        return {i["code"] for i in vs.validate({"deck": deck}, self.color_sets).errors}

    def test_missing_color_set_is_blocked(self) -> None:
        deck = {"title": "t", "slides": [{"type": "title", "title": "封面"}]}
        codes = {i["code"] for i in vs.validate({"deck": deck}, self.color_sets).errors}
        self.assertIn("MISSING_COLOR_SET", codes)

    def test_auto_is_blocked(self) -> None:
        self.assertIn("MISSING_COLOR_SET", self._codes({"colorSet": "auto"}))

    def test_mood_field_is_gone(self) -> None:
        self.assertIn("UNKNOWN_FIELD", self._codes({"mood": "bold"}))

    def test_named_but_unknown_set_is_blocked(self) -> None:
        self.assertIn("BAD_COLOR_SET", self._codes({"colorSet": "nope"}))


class TestChartTypeRequired(unittest.TestCase):
    """图表页必须显式声明图形类型（没有推断层）。"""

    @classmethod
    def setUpClass(cls) -> None:
        with open(TOKENS, encoding="utf-8") as fh:
            cls.color_sets = set(json.load(fh)["colorSets"])

    def _codes(self, slide: dict) -> set[str]:
        spec = _spec([slide])
        return {i["code"] for i in vs.validate(spec, self.color_sets).errors}

    def test_all_chart_types_pass(self) -> None:
        for t in vs.CHART_TYPES:
            with self.subTest(t=t):
                codes = self._codes({"type": "chart", "title": "图", "chart": t,
                                     "data": [{"label": "a", "value": 1}]})
                self.assertNotIn("MISSING_CHART_TYPE", codes)
                self.assertNotIn("UNKNOWN_CHART_TYPE", codes)

    def test_chart_types_match_the_renderer(self) -> None:
        """图形类型清单两处必须逐字一致（schema 一处、渲染器一处）。

        两份是有意保留的：`validate_spec.py` 要零依赖（它在渲之前跑，不拉
        渲染器），所以不能 import 渲染器常量。代价就是可能漂 ——
        而漂的后果很安静：给渲染器加了第九类图，校验会先把它拦下，
        报的还是“只认这几类”。所以用一条测试把两份钉在一起。
        """
        render_mod = _load("_deck_test_render_chart_types",
                           os.path.join(SCRIPTS, "render.py"))
        self.assertEqual(tuple(vs.CHART_TYPES), tuple(render_mod.CHART_TYPES),
                         "validate_spec.CHART_TYPES 与 render.py 漂移了")

    def test_missing_type_is_blocked(self) -> None:
        codes = self._codes({"type": "chart", "title": "图",
                             "data": [{"label": "a", "value": 1}]})
        self.assertIn("MISSING_CHART_TYPE", codes)

    def test_unknown_type_is_blocked(self) -> None:
        codes = self._codes({"type": "chart", "title": "图", "chart": "pie3d",
                             "data": [{"label": "a", "value": 1}]})
        self.assertIn("UNKNOWN_CHART_TYPE", codes)

    def test_intent_alone_is_not_enough(self) -> None:
        """intent 是语义标注，不再是类型来源。"""
        codes = self._codes({"type": "chart", "title": "图", "intent": "trend",
                             "data": [{"label": "a", "value": 1}]})
        self.assertIn("MISSING_CHART_TYPE", codes)
