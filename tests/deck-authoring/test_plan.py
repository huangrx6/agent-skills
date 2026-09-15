#!/usr/bin/env python3
"""规划层的回归测试：内容理解 / Storyline / Page Planner / 到 Slide DSL 的桥。

这一层是整条链的**上游**，它最容易出的错不是崩，而是**悄悄产出渲染器吃不下
或者自相矛盾的东西**：

- message 的证据指向不存在的 fact（悬空引用的证据不是证据）；
- 把 AI 推断的话当事实讲（source_type 不分）；
- 骨架乱序（先讲方案再讲问题不是自由，是错）；
- 配额漂移（"15 页做成 28 页"）；
- 一页复杂度爆表还硬塞（AI PPT 最典型的爆法）；
- 映射出的 spec 过不了 validate_spec（规划层白写）。

最后一条是**金标准**：`to_spec` 产出的一切必须能被既有渲染链吃下 —— 有专门的
集成用例钉死。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/deck-authoring/test_plan.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
SCRIPTS = os.path.join(SKILL, "scripts")


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


plan = _load("plan")
vs = _load("validate_spec")
render = _load("render")


def _content(**over):
    base = {
        "topic": "统一平台",
        "brief": {"purpose": "proposal", "audience": "technical",
                  "delivery": "live", "desiredAction": "批准平台建设方案"},
        "coreThesis": {"statement": "统一平台可以解决模型服务碎片化并形成规模化能力"},
        "facts": [
            {"id": "fact_01", "type": "problem", "text": "资源分散",
             "source_type": "original", "source_ref": "doc:p1"},
            {"id": "fact_02", "type": "solution", "text": "统一纳管",
             "source_type": "original", "source_ref": "doc:p2"},
            {"id": "fact_03", "type": "result", "text": "成本降六成",
             "source_type": "inferred", "source_ref": "doc:p3"},
        ],
        "metrics": [{"id": "m_01", "label": "降幅", "value": 60, "unit": "%"}],
        "messages": [
            {"id": "msg_01", "statement": "服务分散缺统一管理", "importance": 0.95,
             "evidence_refs": ["fact_01"]},
            {"id": "msg_02", "statement": "统一平台解决三件事", "importance": 0.98,
             "evidence_refs": ["fact_02"]},
        ],
    }
    base.update(over)
    return base


def _story(**over):
    base = {
        "archetype": "problem_solution",
        "target_slide_count": 3,
        "beats": [
            {"order": 1, "role": "context", "message_ref": "msg_01"},
            {"order": 2, "role": "problem", "message_ref": "msg_01"},
            {"order": 3, "role": "solution", "message_ref": "msg_02"},
        ],
        "sections": [
            {"name": "背景与问题", "weight": 0.67, "target_slides": 2},
            {"name": "方案", "weight": 0.33, "target_slides": 1},
        ],
    }
    base.update(over)
    return base


def _pageplan(**over):
    base = {
        "pages": [
            {"page_id": "p01", "section": "背景与问题", "message_ref": "msg_01",
             "page_type": "statement", "density": "sparse",
             "bullets": ["多模型并行", "接口不一"]},
            {"page_id": "p02", "section": "背景与问题", "message_ref": "msg_01",
             "page_type": "comparison", "density": "medium",
             "data": [{"label": "A", "value": 8}, {"label": "B", "value": 5}]},
            {"page_id": "p03", "section": "方案", "message_ref": "msg_02",
             "page_type": "statement", "density": "sparse", "bullets": ["纳管", "调用"]},
        ]
    }
    base.update(over)
    return base


class TestArchetypes(unittest.TestCase):
    """叙事骨架是成文数据 —— 形状不对，选骨架的人就无从选起。"""

    def test_every_archetype_is_well_formed(self) -> None:
        for key, row in plan.ARCHETYPES.items():
            with self.subTest(archetype=key):
                self.assertTrue(row.get("label"))
                self.assertTrue(row.get("roles"))
                self.assertTrue(row.get("fits"))
                self.assertEqual(len(set(row["roles"])), len(row["roles"]),
                                 "骨架角色有重复")

    def test_at_least_one_chinese_context_archetype(self) -> None:
        """中文汇报场景（技术方案/项目汇报）是真实需求，骨架得有。"""
        self.assertIn("tech_proposal", plan.ARCHETYPES)
        self.assertIn("project_report", plan.ARCHETYPES)


class TestContentUnderstanding(unittest.TestCase):
    """① 内容理解：引用完整 + 事实/推断分离。"""

    def test_valid_content_passes(self) -> None:
        problems, notes = plan.check_content(_content())
        self.assertEqual(problems, [])
        self.assertEqual(notes, [])

    def test_dangling_evidence_ref_is_an_error(self) -> None:
        bad = _content()
        bad["messages"][0]["evidence_refs"] = ["fact_99"]
        problems, _ = plan.check_content(bad)
        self.assertTrue(any("悬空引用" in p for p in problems), problems)

    def test_source_type_must_be_declared(self) -> None:
        bad = _content()
        bad["facts"][0]["source_type"] = "看起来像真的"
        problems, _ = plan.check_content(bad)
        self.assertTrue(any("source_type" in p for p in problems), problems)

    def test_fact_type_is_a_closed_set(self) -> None:
        bad = _content()
        bad["facts"][0]["type"] = "vibe"
        problems, _ = plan.check_content(bad)
        self.assertTrue(any("type" in p for p in problems), problems)

    def test_high_importance_on_inferred_only_evidence_is_flagged(self) -> None:
        """**AI PPT 最危险的一类错**：把推断当事实讲。

        message 重要性 ≥0.9，证据却全是 inferred —— 不是阻塞（推断也可以是
        结论，比如预测），但必须开口。
        """
        suspicious = _content()
        suspicious["messages"].append(
            {"id": "msg_03", "statement": "成本将下降六成", "importance": 0.95,
             "evidence_refs": ["fact_03"]})
        problems, notes = plan.check_content(suspicious)
        self.assertEqual(problems, [])
        self.assertTrue(any("推断" in n for n in notes), notes)

    def test_low_importance_on_inferred_is_silent(self) -> None:
        """反面对照：低重要性的推断结论不值得唠叨 —— 提示太多会让人全部忽略。"""
        ok = _content()
        ok["messages"].append(
            {"id": "msg_03", "statement": "长期看还可能再降", "importance": 0.5,
             "evidence_refs": ["fact_03"]})
        _problems, notes = plan.check_content(ok)
        self.assertFalse(any("推断" in n for n in notes), notes)

    def test_empty_content_is_an_error(self) -> None:
        problems, _ = plan.check_content({"facts": []})
        self.assertTrue(problems)


class TestContentV3(unittest.TestCase):
    """content-design v3.0 接进来的检查：Brief / Core Thesis / Claim / 空话 / 重复。"""

    def test_missing_core_thesis_is_an_error(self) -> None:
        """元规则 2：没有统领论断，每页各自为政。"""
        bad = _content()
        del bad["coreThesis"]
        problems, _ = plan.check_content(bad)
        self.assertTrue(any("coreThesis" in p for p in problems), problems)

    def test_brief_without_any_desired_outcome_is_an_error(self) -> None:
        """元规则 1：先明确观众要做什么，再决定内容。"""
        bad = _content()
        bad["brief"] = {"purpose": "proposal"}
        problems, _ = plan.check_content(bad)
        self.assertTrue(any("desiredAction" in p for p in problems), problems)

    def test_missing_brief_is_only_a_note(self) -> None:
        """Brief 可选 —— 但缺席要开口，不是静默。"""
        ok = _content()
        del ok["brief"]
        problems, notes = plan.check_content(ok)
        self.assertEqual(problems, [])
        self.assertTrue(any("desiredAction" in n for n in notes), notes)

    def test_brief_enums_are_closed(self) -> None:
        bad = _content()
        bad["brief"]["audience"] = "所有人"
        problems, _ = plan.check_content(bad)
        self.assertTrue(any("audience" in p for p in problems), problems)

    def test_brief_target_slides_must_be_positive_int(self) -> None:
        bad = _content()
        bad["brief"]["targetSlides"] = 0
        problems, _ = plan.check_content(bad)
        self.assertTrue(any("targetSlides" in p for p in problems), problems)

    def test_claims_derived_from_real_facts(self) -> None:
        ok = _content()
        ok["claims"] = [{"id": "claim_01", "statement": "接口已碎片化",
                         "type": "derived", "derivedFrom": ["fact_01"],
                         "confidence": 0.9}]
        problems, _ = plan.check_content(ok)
        self.assertEqual(problems, [])

    def test_claim_with_dangling_derived_from_is_an_error(self) -> None:
        """判断基于不存在的事实 = 悬空的论证。"""
        bad = _content()
        bad["claims"] = [{"id": "claim_01", "statement": "碎片化",
                          "type": "derived", "derivedFrom": ["fact_99"]}]
        problems, _ = plan.check_content(bad)
        self.assertTrue(any("derivedFrom" in p for p in problems), problems)

    def test_message_claim_must_resolve(self) -> None:
        bad = _content()
        bad["messages"][0]["claimId"] = "claim_404"
        problems, _ = plan.check_content(bad)
        self.assertTrue(any("claimId" in p for p in problems), problems)

    def test_vague_change_word_without_digit_is_flagged(self) -> None:
        """§50/§51："全面提升能力" 该被追问；带数字的不唠叨。"""
        vague = _content()
        vague["messages"].append(
            {"id": "msg_v", "statement": "平台将全面提升管理能力",
             "importance": 0.6, "evidence_refs": ["fact_01"]})
        _p, notes = plan.check_content(vague)
        self.assertTrue(any("没有数字" in n for n in notes), notes)
        numbered = _content()
        numbered["messages"].append(
            {"id": "msg_n", "statement": "按入口从 5 套提升到 1 套",
             "importance": 0.6, "evidence_refs": ["fact_01"]})
        _p, notes2 = plan.check_content(numbered)
        self.assertFalse(any("没有数字" in n for n in notes2), notes2)

    def test_identical_messages_are_flagged(self) -> None:
        """§44：同一句话讲两遍 —— 归一化后相同才算（语义相似度未实现）。"""
        dup = _content()
        dup["messages"].append(
            {"id": "msg_d", "statement": "服务分散，缺统一管理！",
             "importance": 0.7, "evidence_refs": ["fact_01"]})
        _p, notes = plan.check_content(dup)
        self.assertTrue(any("同一句话" in n for n in notes), notes)

    def test_no_messages_is_an_error(self) -> None:
        bad = _content()
        bad["messages"] = []
        problems, _ = plan.check_content(bad)
        self.assertTrue(any("messages" in p for p in problems), problems)


class TestStoryline(unittest.TestCase):
    """② Storyline：骨架符合 + 配额自洽。"""

    def test_valid_storyline_passes(self) -> None:
        self.assertEqual(plan.check_storyline(_story()), [])

    def test_unknown_archetype_is_rejected(self) -> None:
        problems = plan.check_storyline(_story(archetype="自由发挥"))
        self.assertTrue(any("预定义骨架" in p for p in problems), problems)

    def test_beats_out_of_skeleton_order_are_rejected(self) -> None:
        """先讲方案再讲问题不是自由，是错 —— 骨架的意义就是逻辑递进。"""
        bad = _story()
        bad["beats"] = [
            {"order": 1, "role": "solution", "message_ref": "msg_02"},
            {"order": 2, "role": "problem", "message_ref": "msg_01"},
        ]
        problems = plan.check_storyline(bad)
        self.assertTrue(any("顺序" in p for p in problems), problems)

    def test_skipping_roles_is_allowed(self) -> None:
        """骨架允许跳角色（不是每页都讲 impact），只是不许乱序。"""
        skip = _story()
        skip["beats"] = [
            {"order": 1, "role": "context", "message_ref": "msg_01"},
            {"order": 2, "role": "solution", "message_ref": "msg_02"},
        ]
        self.assertEqual(plan.check_storyline(skip), [])

    def test_role_outside_the_archetype_is_rejected(self) -> None:
        bad = _story()
        bad["beats"].append({"order": 4, "role": "vibes", "message_ref": "msg_01"})
        problems = plan.check_storyline(bad)
        self.assertTrue(any("不属于" in p for p in problems), problems)

    def test_weights_must_sum_to_one(self) -> None:
        bad = _story()
        bad["sections"][0]["weight"] = 0.5
        problems = plan.check_storyline(bad)
        self.assertTrue(any("权重" in p for p in problems), problems)

    def test_section_slides_must_match_the_target(self) -> None:
        """「15 页的 PPT 做成 28 页」就是这条漏的。"""
        bad = _story()
        bad["sections"][0]["target_slides"] = 5
        problems = plan.check_storyline(bad)
        self.assertTrue(any("target_slide_count" in p for p in problems), problems)


class TestPagePlanner(unittest.TestCase):
    """③ Page Planner：页型合法 + 拆页判断 + 配额对齐。"""

    def test_valid_pageplan_passes(self) -> None:
        problems, notes = plan.check_pageplan(_pageplan(), _story())
        self.assertEqual(problems, [])
        self.assertEqual(notes, [])

    def test_unknown_page_type_is_rejected(self) -> None:
        bad = _pageplan()
        bad["pages"][0]["page_type"] = "酷炫卡片"
        problems, _ = plan.check_pageplan(bad)
        self.assertTrue(any("页型表" in p for p in problems), problems)

    def test_over_complex_page_without_split_is_an_error(self) -> None:
        """**AI PPT 最典型的爆法**：一页塞下一切。"""
        heavy = {
            "page_id": "p09", "section": "x", "message_ref": "msg_01",
            "page_type": "statement",
            "message": "一" * 200,                                  # ~1.67 的字符分
            "nodes": [{"label": "n"} for _ in range(6)],            # 0.72
        }
        problems, _ = plan.check_pageplan({"pages": [heavy]})
        self.assertTrue(any("split" in p for p in problems), problems)

    def test_split_with_low_complexity_is_only_a_note(self) -> None:
        light = {"page_id": "p01", "page_type": "statement", "split": True,
                 "message": "短", "bullets": ["a"]}
        _problems, notes = plan.check_pageplan({"pages": [light]})
        self.assertTrue(any("拆得太碎" in n for n in notes), notes)

    def test_page_count_must_match_the_storyline_quota(self) -> None:
        """配额到执行层不许丢 —— 这是"节奏可控"的落点。"""
        problems, _ = plan.check_pageplan(_pageplan(), _story(target_slide_count=7))
        self.assertTrue(any("storyline 定的是 7" in p for p in problems), problems)

    def test_complexity_is_bounded_and_ordered(self) -> None:
        self.assertEqual(plan.complexity({}), 0.0)
        light = plan.complexity({"message": "短", "bullets": ["a"]})
        heavy = plan.complexity({"message": "一" * 200,
                                 "nodes": [{"label": "n"} for _ in range(6)]})
        self.assertLess(light, heavy)
        self.assertLessEqual(heavy, 1.0)


class TestPageTypeToLayout(unittest.TestCase):
    """页型表引用的版式必须是渲染器真支持的 —— 否则映射是死路。"""

    def test_every_layout_exists_in_the_renderer(self) -> None:
        supported = {"title", "content-text", "content-image", "two-column",
                     "timeline", "chart", "end"}
        for pt, row in plan.PAGE_TYPES.items():
            with self.subTest(page_type=pt):
                self.assertIn(row["layout"], supported)

    def test_chart_page_types_carry_a_chart_kind(self) -> None:
        for pt, row in plan.PAGE_TYPES.items():
            if row["layout"] == "chart":
                with self.subTest(page_type=pt):
                    self.assertTrue(row.get("chart"))


class TestToSpecBridge(unittest.TestCase):
    """③→④ 桥：**金标准** —— 映射出的 spec 必须能被既有渲染链吃下。"""

    def _spec(self, pageplan=None, content=None):
        return plan.to_spec(pageplan or _pageplan(), content or _content())

    def test_emitted_spec_passes_validate_spec(self) -> None:
        """规划层产出的东西渲染器吃不下 = 全白写。"""
        issues = vs.validate(self._spec())
        self.assertEqual(issues.errors, [], issues.errors)

    def test_page_types_map_to_the_right_layouts(self) -> None:
        spec = self._spec()
        kinds = [s["type"] for s in spec["deck"]["slides"]]
        self.assertEqual(kinds, ["content-text", "chart", "content-text"])

    def test_message_becomes_the_headline(self) -> None:
        spec = self._spec()
        self.assertIn("服务分散", spec["deck"]["slides"][0]["title"])

    def test_metric_ref_resolves_into_chart_data(self) -> None:
        pages = [{"page_id": "p1", "message_ref": "msg_02", "page_type": "metric",
                  "metric_ref": "m_01"}]
        spec = self._spec(pageplan={"pages": pages})
        slide = spec["deck"]["slides"][0]
        self.assertEqual(slide["type"], "chart")
        self.assertEqual(slide["chart"], "donut")
        self.assertEqual(slide["intent"], "progress")
        self.assertEqual(slide["data"][0]["value"], 60)
        self.assertEqual(slide["unit"], "%")

    def test_process_maps_to_timeline_with_nodes(self) -> None:
        pages = [{"page_id": "p1", "message_ref": "msg_02", "page_type": "process",
                  "nodes": [{"label": "纳管", "note": "注册"}]}]
        spec = self._spec(pageplan={"pages": pages})
        slide = spec["deck"]["slides"][0]
        self.assertEqual(slide["type"], "timeline")
        self.assertEqual(slide["nodes"][0]["label"], "纳管")

    def test_chart_page_without_data_is_rejected(self) -> None:
        pages = [{"page_id": "p1", "message_ref": "msg_02", "page_type": "comparison"}]
        with self.assertRaises(SystemExit):
            self._spec(pageplan={"pages": pages})

    def test_page_without_any_message_is_rejected(self) -> None:
        """一页不知道自己在讲什么，就没法排版。"""
        pages = [{"page_id": "p1", "page_type": "statement", "bullets": ["a"]}]
        with self.assertRaises(SystemExit):
            self._spec(pageplan={"pages": pages})

    def test_image_page_requires_an_image(self) -> None:
        pages = [{"page_id": "p1", "message_ref": "msg_02",
                  "page_type": "hero_visual"}]
        with self.assertRaises(SystemExit):
            self._spec(pageplan={"pages": pages})

    def test_emitted_spec_renders(self) -> None:
        """端到端：规划 → spec → 渲染不炸（渲染链的约定是最硬的约束）。"""
        html = render.render(self._spec())
        self.assertIn("<section", html)


if __name__ == "__main__":
    unittest.main()
