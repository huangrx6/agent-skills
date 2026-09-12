#!/usr/bin/env python3
"""check_layout.py 的回归测试：五项校验 + 自动调参 + 报告措辞。

## 用例的着力点

按仓库已定的停止判据 —— **元工具只需要边界值测试**，不必再去验证"测试本身对不对"。
所以这里的重点是两类：

1. **阈值边界**：`< 12px` / `< 24px` / `> 边数÷2`。
   「恰好等于阈值」不该报，「差一点点」必须报。差一个 `<` 写成 `<=` 这种错，
   只有边界用例能抓。
2. **措辞与分派**（这一层的规则不是"算得对"，而是"说得对"）：
   - 报告里**不许出现参数名** —— 出现就等于把参数选择权交回模型（前作的病根）。
   - 脚本 bug（测量与落笔不符）**不许**给内容建议 —— 否则模型会去干"缩短标签"这件没用的事。

## 一条曾经真实存在的 bug

`#5 交叉数` 在文档里是**软**项（不阻塞输出），但**可自动修**。
第一版的 `checks_hit()` 只返回阻塞项，于是软项永远调不动 —— 调参循环对它等于不存在。
`test_soft_crossing_is_still_tuned` 是这条的守卫：它同时断言"不阻塞"和"确实被调了"，
因为在别的实现里这两个性质很容易被拆散。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/test_check_layout.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
CHECK = os.path.join(SCRIPTS, "check_layout.py")


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


C = _load("check_layout", CHECK)
L = C.L


# ── 造规格与桩 ──────────────────────────────────────────────
def spec_of(ids, edges, direction: str = "LR", kind: str = "service") -> dict:
    return {"type": "architecture", "direction": direction,
            "nodes": [{"id": n, "kind": kind, "label": n} for n in ids],
            "edges": [{"from": a, "to": b} for a, b in edges]}


def run(spec, params=None):
    boxes = L.boxes_from_spec(spec)
    result, outcome, attempts = C.layout_with_retry(spec, boxes, params)
    return result, outcome, attempts


class StubResult:
    """只带 `real_nodes()` / `edges` 的桩，用来单独测某一项检查的边界。"""

    def __init__(self, nodes: dict, edges=None, crossings: int = 0,
                 crossing_origins=None) -> None:
        self._nodes = nodes
        self.edges = edges or []
        self.crossings = crossings
        self.crossing_origins = crossing_origins or []

    def real_nodes(self) -> dict:
        return self._nodes


def placed(node_id: str, x: float, y: float, w: float = 100.0, h: float = 50.0):
    return L.Placed(id=node_id, x=x, y=y, width=w, height=h, rank=0)


class TestGapBoundary(unittest.TestCase):
    """#1：阈值是「间隙 < 12」不是「重叠」。前作容忍 4px 重叠 —— 那检查的是另一个东西。"""

    def test_exactly_at_threshold_passes(self):
        r = StubResult({"a": placed("a", 0, 0), "b": placed("b", 112, 0)})
        self.assertEqual([], C.check_gaps(r), "恰好 12px 不该报")

    def test_just_under_threshold_fails(self):
        r = StubResult({"a": placed("a", 0, 0), "b": placed("b", 111.9, 0)})
        issues = C.check_gaps(r)
        self.assertEqual(1, len(issues))
        self.assertTrue(issues[0].blocking)

    def test_overlapping_boxes_are_reported(self):
        r = StubResult({"a": placed("a", 0, 0), "b": placed("b", 50, 0)})
        self.assertEqual(1, len(C.check_gaps(r)))

    def test_diagonal_gap_is_euclidean_not_per_axis(self):
        """斜对角：两轴各差 10px。

        两条轴都差 10 时，欧氏距离 ≈ 14.1（过 12px），而"各轴取大"只有 10（会被判失败）。
        所以这条用例固定住了我们用的是**两个框之间的真实距离**，不是分量。
        """
        r = StubResult({"a": placed("a", 0, 0), "b": placed("b", 110, 60)})
        self.assertEqual([], C.check_gaps(r), "欧氏距离 14.1px，不该报")

    def test_overlap_in_one_axis_makes_the_gap_zero(self):
        """纵向相交时，横向虽然差 10px 但它们其实是叠着的 —— 间隙算 0。"""
        r = StubResult({"a": placed("a", 0, 0), "b": placed("b", 110, 45)})
        self.assertEqual(1, len(C.check_gaps(r)))

    def test_opposite_side_ordering_also_detected(self):
        """b 在 a 左边时同样要报 —— 只判一个方向会漏掉一半。"""
        r = StubResult({"a": placed("a", 200, 0), "b": placed("b", 195, 0)})
        self.assertEqual(1, len(C.check_gaps(r)))


class TestEdgeLengthBoundary(unittest.TestCase):
    """#2：连线短到看不见箭头的最小长度。"""

    def edge(self, a, b, points):
        return {"from": a, "to": b, "points": points, "reversed": False}

    def test_exactly_at_threshold_passes(self):
        r = StubResult({}, [self.edge("a", "b", [[0, 0], [24, 0]])])
        self.assertEqual([], C.check_edge_lengths(r))

    def test_just_under_threshold_fails(self):
        r = StubResult({}, [self.edge("a", "b", [[0, 0], [23.9, 0]])])
        self.assertEqual(1, len(C.check_edge_lengths(r)))

    def test_minimum_over_the_whole_polyline(self):
        """折线取最短的一段 —— 长边中间有一小段短了也算。"""
        r = StubResult({}, [self.edge("a", "b", [[0, 0], [200, 0], [210, 0]])])
        self.assertEqual(1, len(C.check_edge_lengths(r)))

    def test_single_point_edge_is_skipped(self):
        r = StubResult({}, [self.edge("a", "b", [[0, 0]])])
        self.assertEqual([], C.check_edge_lengths(r))


class TestCrossingBoundary(unittest.TestCase):
    """#5：软阈值 = 边数 × 0.5，且必须**不阻塞**。"""

    def k33(self):
        return spec_of([f"a{i}" for i in (1, 2, 3)] + [f"b{i}" for i in (1, 2, 3)],
                       [(f"a{i}", f"b{j}") for i in (1, 2, 3) for j in (1, 2, 3)])

    def test_under_threshold_reports_nothing(self):
        spec = spec_of(["a1", "a2", "b1", "b2"], [("a1", "b1"), ("a2", "b2")])
        result, outcome, _ = run(spec)
        self.assertEqual([], C.check_crossings(spec, result))

    def test_over_threshold_is_soft_not_blocking(self):
        spec = self.k33()
        result, outcome, _ = run(spec)
        issues = C.check_crossings(spec, result)
        self.assertEqual(1, len(issues))
        self.assertFalse(issues[0].blocking, "交叉数不该挡输出")
        self.assertEqual([], outcome.blocking)

    def test_reports_which_edges_cross(self):
        """只有计数没法定位问题 —— 必须给出是哪几条边。"""
        spec = self.k33()
        result, _, _ = run(spec)
        issue = C.check_crossings(spec, result)[0]
        self.assertIn("✕", issue.where)
        self.assertIn("a1", issue.where)
        self.assertEqual(result.crossings, len(result.crossing_origins))


class TestTuner(unittest.TestCase):
    def test_clean_spec_passes_first_round(self):
        spec = spec_of(["web", "api", "db"], [("web", "api"), ("api", "db")])
        _, outcome, attempts = run(spec)
        self.assertEqual([], outcome.issues)
        self.assertEqual(1, len(attempts), "首轮就该过，不该多跑")

    def test_soft_crossing_is_still_tuned(self):
        """曾经的真 bug：软项永远调不动。同时断言「不阻塞」和「确实被调」。"""
        spec = spec_of([f"a{i}" for i in (1, 2, 3)] + [f"b{i}" for i in (1, 2, 3)],
                       [(f"a{i}", f"b{j}") for i in (1, 2, 3) for j in (1, 2, 3)])
        _, outcome, attempts = run(spec)
        self.assertFalse(outcome.blocking, "交叉是软项，不该阻塞")
        rounds = [a.params["barycenterRounds"] for a in attempts]
        self.assertEqual([4.0, 8.0, 12.0], rounds, "软项没有被调参")

    def test_stops_when_parameter_hits_its_limit(self):
        """到上限后该自己停下，不是把同样的计算再跑一遍。"""
        spec = spec_of([f"a{i}" for i in (1, 2, 3)] + [f"b{i}" for i in (1, 2, 3)],
                       [(f"a{i}", f"b{j}") for i in (1, 2, 3) for j in (1, 2, 3)])
        _, _, attempts = run(spec)
        self.assertLessEqual(len(attempts), C.MAX_TUNE_ROUNDS + 1)
        self.assertEqual(L.PARAM_LIMIT["barycenterRounds"],
                         attempts[-1].params["barycenterRounds"])

    def test_content_error_never_wastes_rounds(self):
        """未知 kind 改参数没用 —— 应该立刻停。"""
        spec = spec_of(["a", "b"], [("a", "b")], kind="queue")
        _, outcome, attempts = run(spec)
        self.assertEqual({"palette"}, outcome.checks_hit())
        self.assertEqual(1, len(attempts))

    def test_text_mismatch_never_wastes_rounds(self):
        spec = spec_of(["a", "b"], [("a", "b")])
        boxes = L.boxes_from_spec(spec)
        boxes["a"] = L.Box(boxes["a"].width + 40, boxes["a"].height)   # 人为篡改
        _, outcome, attempts = C.layout_with_retry(spec, boxes)
        self.assertEqual({"text"}, outcome.checks_hit())
        self.assertEqual(1, len(attempts))

    def test_tuning_does_not_change_content(self):
        """调参只能动排布，一个节点/一条边都不许增减。"""
        spec = spec_of([f"a{i}" for i in (1, 2, 3)] + [f"b{i}" for i in (1, 2, 3)],
                       [(f"a{i}", f"b{j}") for i in (1, 2, 3) for j in (1, 2, 3)])
        result, _, _ = run(spec)
        self.assertEqual(6, len(result.real_nodes()))
        self.assertEqual(9, len(result.edges))


class TestReportWording(unittest.TestCase):
    """这一层的规则不是"算得对"，是"说得对"。"""

    def test_report_never_contains_param_names(self):
        specs = [
            spec_of(["a", "b"], [("a", "b")]),
            spec_of(["a", "b"], [("a", "b")], kind="queue"),
            spec_of([f"a{i}" for i in (1, 2, 3)] + [f"b{i}" for i in (1, 2, 3)],
                    [(f"a{i}", f"b{j}") for i in (1, 2, 3) for j in (1, 2, 3)]),
            spec_of(["a"], [], kind="service"),
        ]
        for spec in specs:
            result, outcome, attempts = run(spec)
            text = C.format_report(spec, attempts, outcome)
            for name in C.PARAM_SPOKEN:
                self.assertNotIn(name, text, f"报告泄露了参数名 {name}")

    def test_guard_actually_raises(self):
        """断言本身要真的会拦 —— 否则它只是一句注释。"""
        with self.assertRaises(AssertionError):
            C._assert_no_param_names("建议调大 nodeSeparation")

    def test_tried_params_section_is_present(self):
        spec = spec_of([f"a{i}" for i in (1, 2, 3)] + [f"b{i}" for i in (1, 2, 3)],
                       [(f"a{i}", f"b{j}") for i in (1, 2, 3) for j in (1, 2, 3)])
        result, outcome, attempts = run(spec)
        text = C.format_report(spec, attempts, outcome)
        self.assertIn("已尝试过的排布", text)
        self.assertIn("4 → 8 → 12", text, "第 1 段必须给出走过的参数值")

    def test_first_round_pass_says_so(self):
        spec = spec_of(["a", "b"], [("a", "b")])
        result, outcome, attempts = run(spec)
        text = C.format_report(spec, attempts, outcome)
        self.assertIn("首轮即通过", text)

    def test_report_has_three_sections(self):
        spec = spec_of(["a", "b"], [("a", "b")], kind="queue")
        result, outcome, attempts = run(spec)
        text = C.format_report(spec, attempts, outcome)
        for section in ("已尝试过的排布", "仍然失败的项", "能动的只有内容"):
            self.assertIn(section, text)


class TestAdvice(unittest.TestCase):
    """脚本 bug 与内容问题必须给不同的建议 —— 混了会让模型替脚本背锅。"""

    def test_measurement_mismatch_blames_the_script(self):
        spec = spec_of(["a", "b"], [("a", "b")])
        boxes = L.boxes_from_spec(spec)
        boxes["a"] = L.Box(boxes["a"].width + 40, boxes["a"].height)
        _, outcome, attempts = C.layout_with_retry(spec, boxes)
        detail = outcome.blocking[0].detail
        self.assertIn("内部不一致", detail)
        self.assertIn("不是你内容的问题", detail)
        section3 = C.format_report(spec, attempts, outcome).split("### 能动的只有内容")[1]
        self.assertIn("无需改动", section3, "脚本 bug 不该给内容建议")

    def test_overlong_label_gives_content_advice(self):
        spec = {"type": "flow", "direction": "LR",
                "nodes": [{"id": "a", "kind": "service", "label": "测" * 300},
                          {"id": "b", "kind": "data", "label": "B"}],
                "edges": [{"from": "a", "to": "b"}]}
        _, outcome, attempts = C.layout_with_retry(spec, L.boxes_from_spec(spec))
        self.assertIn("text", outcome.checks_hit())
        section3 = C.format_report(spec, attempts, outcome).split("### 能动的只有内容")[1]
        self.assertIn("标签", section3)

    def test_unknown_kind_lists_allowed_values(self):
        spec = spec_of(["a", "b"], [("a", "b")], kind="queue")
        _, outcome, _ = run(spec)
        detail = outcome.blocking[0].detail
        self.assertIn("queue", detail)
        for allowed in sorted(C.palette.KINDS):
            self.assertIn(allowed, detail, "报错要列出允许值，不是只说非法")

    def test_every_issue_advice_is_content_level(self):
        """建议里不许出现"调大某某"这类话 —— 那是把旋钮交回模型。"""
        specs = [
            spec_of(["a", "b"], [("a", "b")], kind="queue"),
            spec_of([f"a{i}" for i in (1, 2, 3)] + [f"b{i}" for i in (1, 2, 3)],
                    [(f"a{i}", f"b{j}") for i in (1, 2, 3) for j in (1, 2, 3)]),
        ]
        for spec in specs:
            result, outcome, _ = run(spec)
            for issue in outcome.blocking + outcome.soft:
                if issue.advice:
                    self.assertNotIn("调大", issue.advice)
                    self.assertNotIn("间距", issue.advice)


class TestScale(unittest.TestCase):
    def test_fourteen_node_chain_is_fine(self):
        ids = [str(i) for i in range(14)]
        spec = spec_of(ids, [(str(i), str(i + 1)) for i in range(13)])
        result, outcome, _ = run(spec)
        self.assertEqual(14, len(result.real_nodes()))
        self.assertEqual([], outcome.blocking)

    def test_dense_graph_does_not_crash(self):
        """20+ 规模的邻居：边多、交叉多，但必须给出结论而不是崩掉。"""
        ids = [str(i) for i in range(14)]
        edges = [(str(i), str(i + 1)) for i in range(13)]
        edges += [(str(i), str(i + 3)) for i in range(0, 11, 2)]
        spec = spec_of(ids, edges)
        result, outcome, attempts = run(spec)
        self.assertEqual(len(edges), len(result.edges))
        self.assertLessEqual(len(attempts), C.MAX_TUNE_ROUNDS + 1)


class TestSizeSourcePremise(unittest.TestCase):
    """钉住 #1/#3 之所以是“后置断言”的那个前提：**尺寸只有一个来源**。

    只要每个节点的框都等于 `text_metrics.measure()` 的输出，容器宽度就只由断行宽度决定，
    于是“元素间隙”与“文字溢出”在构造上不可能失败（详见 `references/validation.md` 第六节）。

    **Wave 4 引入非文本的尺寸来源（图标固有宽高、分组外框…）时，这个类会先失败。**
    它失败的意思不是“快改这个测试”，而是“尺寸来源变了，先回去重新审视那两条断言的前提
    还成不成立” —— 那时候 #1/#3 会从一致性断言退化成真实的门，而且很可能先是误报。
    """

    def test_every_box_comes_from_text_metrics(self):
        spec = {"type": "architecture", "direction": "LR",
                "nodes": [{"id": "a", "kind": "service", "label": "订单服务",
                           "detail": "3 副本"},
                          {"id": "b", "kind": "data", "label": "订单库"},
                          {"id": "c", "kind": "external", "label": "Notification Service"}]}
        boxes = L.boxes_from_spec(spec)
        for node in spec["nodes"]:
            fresh = C.tm.measure(node["label"], node.get("detail", ""))
            got = boxes[node["id"]]
            self.assertAlmostEqual(
                fresh.width, got.width, places=6,
                msg=f"{node['id']} 的宽度不再等于 text_metrics 的推算 —— "
                    f"尺寸来源变了，先回去看 validation.md 第六节（#1/#3 的前提）")
            self.assertAlmostEqual(
                fresh.height, got.height, places=6,
                msg=f"{node['id']} 的高度不再等于 text_metrics 的推算 —— 同上")

    def test_gap_check_cannot_fire_with_default_spacing(self):
        """把这个“跑不到”的事实钉住，而不是只在注释里说一句。

        同层节点恰好相距一个节点间距、跨层恰好相距一个层间距 —— 两者都远大于 12px。
        这条用意是：哪天它真的报了出来，说明坐标推导被改成了不再由参数唯一决定，
        那是一个信号，不是一个普通的失败。
        """
        ids = ["web", "gw", "order", "pay", "mq", "db", "notify"]
        spec = spec_of(ids, [("web", "gw"), ("gw", "order"), ("order", "db"),
                             ("order", "mq"), ("mq", "pay"), ("mq", "notify"),
                             ("pay", "gw")])
        result, _, _ = run(spec)
        gaps = C.check_gaps(result)
        self.assertEqual([], gaps,
                         "间隙检查居然报了 —— 坐标推导已经不是“由间距参数唯一决定”了，"
                         "回去重新判断这条是后置断言还是真实防线")


class TestCli(unittest.TestCase):
    """CLI 退出码。

    路径全部由 `tempfile` 生成（不是外部输入），所以下面两处
    python-path-traversal 提示不适用。
    """

    def _write(self, spec) -> str:
        fh = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                         encoding="utf-8")
        json.dump(spec, fh)
        fh.close()
        return fh.name

    def test_clean_spec_exits_zero(self):
        path = self._write(spec_of(["a", "b"], [("a", "b")]))
        try:
            proc = subprocess.run([sys.executable, CHECK, path],
                                  capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertIn("能动的只有内容", proc.stdout)
        finally:
            os.unlink(path)

    def test_content_error_exits_one(self):
        path = self._write(spec_of(["a", "b"], [("a", "b")], kind="queue"))
        try:
            proc = subprocess.run([sys.executable, CHECK, path],
                                  capture_output=True, text=True)
            self.assertEqual(1, proc.returncode, "有阻塞项时退出码必须是 1")
        finally:
            os.unlink(path)

    def test_bad_json_exits_two(self):
        fh = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        fh.write("{not json")
        fh.close()
        try:
            proc = subprocess.run([sys.executable, CHECK, fh.name],
                                  capture_output=True, text=True)
            self.assertEqual(2, proc.returncode)
        finally:
            os.unlink(fh.name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
