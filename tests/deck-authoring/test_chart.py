#!/usr/bin/env python3
"""图表引擎的回归测试：意图树、muted+accent、八类 SVG、结论先行、字段集。

这一层最容易出的错：

**一、选错图。** "趋势用饼图"不是风格问题，是**读不通** —— 意图到图形的映射
必须是确定性的，AI 改了意图图就该跟着换。

**二、彩虹。** 八根柱子八种颜色是业余的第一特征；规则是 muted + 1 accent，
而且给了 emphasis 才启用（没给时维持旧观感，不悄悄改）。

**三、图表标题还是数据集名。** 规范第 5 条：标题应是结论（message），
数据集名（title）降为小标签。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/deck-authoring/test_chart.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import unittest
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
SCRIPTS = os.path.join(SKILL, "scripts")

COLORS = {"primary": "#0033CC", "secondary": "#0A0A0A",
          "background": "#FFFFFF", "text": "#0A0A0A"}


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


chart = _load("chart")
render = _load("render")
vs = _load("validate_spec")


def _svg(slide: dict) -> str:
    return chart.svg(slide, COLORS)


class TestDeclaredType(unittest.TestCase):
    """v3：图形类型由作者显式声明（推断层已退役）。"""

    def test_declared_type_is_used(self) -> None:
        for t in chart.CHART_TYPES:
            with self.subTest(t=t):
                self.assertEqual(chart.declared_type({"chart": t}), t)

    def test_missing_type_is_a_clean_error(self) -> None:
        """不写 chart → 干净报错（不是猜 bar，也不是 KeyError 栈）。"""
        for slide in ({}, {"data": [{"label": "a", "value": 1}]},
                      {"intent": "trend"}):
            with self.subTest(slide=slide):
                with self.assertRaises(SystemExit) as cm:
                    chart.declared_type(slide)
                self.assertIn("chart", str(cm.exception))

    def test_unknown_type_is_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            chart.declared_type({"chart": "pie3d"})

    def test_intent_is_annotation_only(self) -> None:
        """intent 仍是合法语义标注，但**不影响**图形（类型看 chart）。"""
        self.assertEqual(chart.declared_type({"chart": "donut", "intent": "trend"}),
                         "donut")

    def test_svg_uses_the_declared_type(self) -> None:
        html = _svg({"chart": "donut", "data": [{"label": "a", "value": 3}],
                     "title": "t"})
        self.assertIn('data-chart="donut"', html)


class TestMutedAccent(unittest.TestCase):
    """muted + 1 accent（规范第 4 条）：给了 emphasis 才启用。"""

    DATA = [{"label": "DeepSeek", "value": 86}, {"label": "Qwen", "value": 61},
            {"label": "Llama", "value": 34}, {"label": "GLM", "value": 28}]

    def _fills(self, slide: dict) -> list[str]:
        return re.findall(r'class="bar"[^>]*fill="([^"]+)"', _svg(slide))

    def test_emphasis_yields_exactly_two_colors(self) -> None:
        fills = self._fills({"chart": "bar", "data": self.DATA,
                             "emphasis": {"values": ["DeepSeek"]}})
        self.assertEqual(len(set(fills)), 2, f"彩虹或全同色：{fills}")
        self.assertEqual(fills.count(COLORS["primary"]), 1)      # 只有被强调的那根

    def test_no_emphasis_keeps_the_old_look(self) -> None:
        """没写 emphasis 时不悄悄改观感 —— 全部主色（与重构前的行为一致）。"""
        fills = self._fills({"chart": "bar", "data": self.DATA})
        self.assertEqual(set(fills), {COLORS["primary"]})

    def test_muted_is_a_tint_not_grey(self) -> None:
        """muted 是主色向纸色褪 —— 保留色相，不是无彩灰（那样整页发死）。"""
        m = chart.muted("#0033CC", "#FFFFFF")
        self.assertNotEqual(m, "#FFFFFF")
        self.assertTrue(m.startswith("#"))
        r, g, b = (int(m[i:i + 2], 16) for i in (1, 3, 5))
        self.assertGreater(b, r)                                  # 还是偏蓝的

    def test_series_colors_are_tints_not_rainbow(self) -> None:
        cols = chart.series_colors("#0033CC", "#FFFFFF", 4)
        self.assertEqual(len(set(cols)), 4)
        self.assertEqual(cols[0], "#0033CC")                      # 首系列最深

    def test_horizontal_bar_ranks_largest_first(self) -> None:
        """排名图的规矩：大的在上（读完名字就看到长度）。"""
        src = _svg({"chart": "bar-horizontal", "data": self.DATA})
        ys = [float(y) for y in re.findall(r'class="bar"[^>]*y="([\d.]+)"', src)]
        self.assertEqual(ys, sorted(ys))                          # y 越小越靠上


class TestSvgForEightTypes(unittest.TestCase):
    """八类都要渲出**合法**的 SVG，且几何与数据成比例。"""

    def test_all_eight_render_valid_xml(self) -> None:
        for kind, demo in chart._DEMO.items():
            with self.subTest(kind=kind):
                svg = chart.svg(demo, COLORS)
                ET.fromstring(svg)                                # 不合法会抛
                self.assertIn(f'data-chart="{kind}"', svg)

    def test_bar_heights_are_proportional(self) -> None:
        data = [{"label": "A", "value": 10}, {"label": "B", "value": 20}]
        src = _svg({"chart": "bar", "data": data})
        hs = [float(h) for h in re.findall(r'class="bar"[^>]*height="([\d.]+)"', src)]
        self.assertAlmostEqual(hs[1] / hs[0], 2.0, places=2)

    def test_hbar_widths_are_proportional(self) -> None:
        """横条按值**降序**排（大的在上 —— 排名图的规矩），比值按排序后的顺序算。"""
        data = [{"label": "A", "value": 10}, {"label": "B", "value": 30}]
        src = _svg({"chart": "bar-horizontal", "data": data})
        ws = [float(w) for w in re.findall(r'class="bar"[^>]*width="([\d.]+)"', src)]
        self.assertEqual(ws, sorted(ws, reverse=True))           # B(30) 在 A(10) 前
        self.assertAlmostEqual(ws[0] / ws[1], 3.0, places=2)

    def test_line_labels_only_first_last_peak(self) -> None:
        """一排数字会把线埋掉 —— 只标 首/尾/峰。"""
        data = [{"label": f"{m}月", "value": v} for m, v in
                zip(range(1, 7), (22, 28, 25, 31, 30, 81))]
        src = _svg({"chart": "line", "data": data})
        vals = re.findall(r'class="val"[^>]*>(\d+)<', src)
        self.assertLessEqual(len(vals), 4, f"标了太多数字：{vals}")
        self.assertIn("81", vals)                                 # 峰值必须在

    def test_donut_center_shows_the_point(self) -> None:
        src = _svg({"chart": "donut", "intent": "progress", "unit": "%",
                    "data": [{"label": "已完成", "value": 72}, {"label": "剩余", "value": 28}]})
        self.assertIn("72%", src)

    def test_area_has_a_soft_fill(self) -> None:
        src = _svg({"chart": "area", "data": [
            {"label": "Q1", "value": 30}, {"label": "Q2", "value": 60}]})
        self.assertIn('class="area"', src)
        self.assertIn("opacity", src)

    def test_stacked_totals_on_top(self) -> None:
        src = _svg({"chart": "bar-stacked", "series": [
            {"name": "a", "data": [{"label": "Q1", "value": 30}]},
            {"name": "b", "data": [{"label": "Q1", "value": 12}]}]})
        self.assertIn(">42<", src)                                # 30+12 的总量

    def test_scatter_uses_both_measures(self) -> None:
        src = _svg({"chart": "scatter", "data": [
            {"label": "A", "x": 0, "y": 0}, {"label": "B", "x": 100, "y": 100}]})
        self.assertEqual(src.count('class="dot"'), 2)
        self.assertIn('class="axis"', src)                         # 基线是 axis，散点没有 bar

    def test_combo_falls_back_to_bar_with_one_series(self) -> None:
        src = _svg({"chart": "combo", "data": [{"label": "A", "value": 5}]})
        self.assertIn('class="bar"', src)

    def test_no_legends_axes_numbers_or_gridlines_anywhere(self) -> None:
        """既定风格：不画图例/坐标轴数字/网格线 —— 八类都不许破例。"""
        for kind, demo in chart._DEMO.items():
            with self.subTest(kind=kind):
                svg = _svg({**demo})
                self.assertNotIn("legend", svg)
                self.assertNotIn("grid", svg)
                for m in re.findall(r'class="axis"[^>]*', svg):
                    self.assertNotIn("stroke-dasharray", m)      # 基线是实线


class TestMessageFirst(unittest.TestCase):
    """结论先行（规范第 5 条）：message 当大标题，title 降为小标签。"""

    SPEC = {"deck": {"title": "t", "style": "swiss-grid", "colorSet": "blue", "slides": [
        {"type": "chart", "chart": "bar", "title": "模型调用量统计", "message": "DeepSeek 领先 40%",
         "data": [{"label": "A", "value": 86}, {"label": "B", "value": 61}]},
        {"type": "chart", "chart": "bar", "title": "没有结论的旧式写法",
         "data": [{"label": "A", "value": 1}, {"label": "B", "value": 2}]},
    ]}}

    def test_message_becomes_the_headline(self) -> None:
        html = render.render(self.SPEC)
        self.assertIn("DeepSeek 领先 40%", html)
        self.assertIn('class="chartsrc"', html)

    def test_chartsrc_holds_plain_text_not_escaped_html(self) -> None:
        """**回归**：`th` 是渲染好的 <h1> HTML —— 曾把整串标签转义后印在页上。"""
        html = render.render(self.SPEC)
        m = re.search(r'<div class="chartsrc">(.*?)</div>', html)
        assert m is not None, "chartsrc 没渲出来"
        body = m.group(1)
        self.assertNotIn("&lt;h1", body)
        self.assertIn("模型调用量统计", body)

    def test_without_message_the_old_behavior_holds(self) -> None:
        html = render.render(self.SPEC)
        self.assertIn("没有结论的旧式写法", html)
        self.assertEqual(html.count('class="chartsrc"'), 1)      # 只有第一页有小标签

    def test_missing_message_is_called_out_by_explain(self) -> None:
        """没有 message 时 `--explain` 要点名（标题退回数据集名是违规）。

        v3：`--explain` 只报声明的类型与缺 message 的提醒，不再有类型推导。
        """
        slide = {"type": "chart", "chart": "bar",
                 "data": [{"label": "A", "value": 1}]}
        self.assertEqual(chart.declared_type(slide), "bar")
        self.assertFalse(slide.get("message"))


class TestAnnotations(unittest.TestCase):
    """标注（规范第 12 条）：好图表与普通图表的差距多半在这里。"""

    DATA = [{"label": "1月", "value": 22}, {"label": "2月", "value": 28},
            {"label": "3月", "value": 45}]

    def test_reference_line_is_dashed_and_labeled(self) -> None:
        src = _svg({"chart": "bar", "data": self.DATA,
                    "annotations": [{"type": "reference", "value": 40, "text": "目标"}]})
        self.assertIn("stroke-dasharray", src)
        self.assertIn("目标", src)

    def test_callout_points_at_its_target(self) -> None:
        src = _svg({"chart": "bar", "data": self.DATA,
                    "annotations": [{"type": "callout", "target": "3月", "text": "加速"}]})
        self.assertIn("加速", src)
        self.assertIn('class="ann"', src)

    def test_peak_finds_the_max_by_itself(self) -> None:
        src = _svg({"chart": "bar", "data": self.DATA,
                    "annotations": [{"type": "peak", "text": "峰值"}]})
        self.assertIn("峰值", src)

    def test_unknown_target_is_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            _svg({"chart": "bar", "data": self.DATA,
                  "annotations": [{"type": "callout", "target": "不存在的月", "text": "x"}]})

    def test_unknown_annotation_type_is_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            _svg({"chart": "bar", "data": self.DATA,
                  "annotations": [{"type": "arrow3d", "target": "1月"}]})


class TestSpecFields(unittest.TestCase):
    """字段集：图表 DSL 的新键都合法；x/y 只在散点上豁免。"""

    def _issues(self, slide: dict):
        return vs.validate({"deck": {"colorSet": "blue", "slides": [slide]}}).errors

    def test_chart_dsl_fields_are_accepted(self) -> None:
        errors = self._issues({"type": "chart", "chart": "bar", "intent": "comparison",
                               "message": "结论", "unit": "%", "title": "t",
                               "data": [{"label": "A", "value": 1}],
                               "emphasis": {"values": ["A"]},
                               "annotations": [{"type": "peak", "text": "p"}],
                               "series": [{"name": "s", "data": [{"label": "A", "value": 1}]}]})
        self.assertEqual([e for e in errors if e["code"] != "BAD_COLOR_SET"], [])

    def test_scatter_x_y_is_data_not_layout(self) -> None:
        """**限定豁免**：散点的 x/y 是两个连续量（数据），不是版式坐标。"""
        errors = self._issues({"type": "chart", "chart": "scatter", "title": "t",
                               "data": [{"label": "A", "x": 1, "y": 2}]})
        self.assertEqual([e for e in errors if e["code"] != "BAD_COLOR_SET"], [])

    def test_x_y_is_still_banned_outside_scatter(self) -> None:
        """禁令在其他所有地方原样有效 —— 豁免不许扩散。"""
        # bullets 是字符串数组、不做项级检查 —— 能带 x/y 的是 data/nodes/columns 这些
        # **对象项**，所以用它们当反面（第三个覆盖"豁免不许扩散到别的嵌套表"）
        for slide in ({"type": "chart", "chart": "bar", "title": "t",
                       "data": [{"label": "A", "value": 1, "x": 5}]},
                      {"type": "timeline", "title": "t",
                       "nodes": [{"label": "a", "note": "b", "y": 3}]},
                      {"type": "two-column", "title": "t",
                       "columns": [{"title": "a", "bullets": ["b"], "y": 3}]}):
            with self.subTest(slide=slide.get("chart") or slide["type"]):
                errors = self._issues(slide)
                self.assertTrue(any(e["code"] == "COORD_FIELD" for e in errors), errors)

    def test_motion_tokens_are_within_the_spec_budgets(self) -> None:
        """规范第 9 条：整张图的动画 < 1.5s、storytelling 页 < 3s。"""
        t = chart.MOTION_TOKENS
        self.assertLessEqual(t["chart_enter"] + t["chart_stagger"] * 5, t["page_total_max"])
        self.assertLessEqual(t["page_total_max"], t["story_total_max"])
        self.assertIn(t["easing_enter"], ("ease-out", "expo-out"))


class TestNativeMapping(unittest.TestCase):
    """PPT 层：八类都有原生对应（combo 如实降级为柱，不假装是组合）。"""

    def test_every_type_has_a_native_kind(self) -> None:
        pptx_native = _load("pptx_native")
        for kind in chart.CHART_TYPES:
            with self.subTest(kind=kind):
                self.assertIn(kind, pptx_native._XL_KIND)

    def test_doughnut_and_scatter_are_not_column_charts(self) -> None:
        pptx_native = _load("pptx_native")
        from pptx.enum.chart import XL_CHART_TYPE
        self.assertEqual(pptx_native._XL_KIND["donut"], XL_CHART_TYPE.DOUGHNUT)
        self.assertEqual(pptx_native._XL_KIND["scatter"], XL_CHART_TYPE.XY_SCATTER)


if __name__ == "__main__":
    unittest.main()
