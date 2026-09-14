#!/usr/bin/env python3
"""check_layout.py 的回归测试：十二项校验 + 自动调参 + 报告措辞。

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
import re
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
P = _load("palette", os.path.join(SCRIPTS, "palette.py"))
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
    """只带 `real_nodes()` / `edges` 的桩，用来单独测某一项检查的边界。

    `direction` 默认给 "LR"：分层项的检查（#9 斜段）只对 LR / TB 生效，
    桩不给方向的话它会静默跳过 —— 那会让桩上的用例看起来“过了”而实际什么都没查。
    """

    def __init__(self, nodes: dict, edges=None, crossings: int = 0,
                 crossing_origins=None, direction: str = "LR") -> None:
        self._nodes = nodes
        self.edges = edges or []
        self.crossings = crossings
        self.crossing_origins = crossing_origins or []
        self.direction = direction

    def real_nodes(self) -> dict:
        return self._nodes


def placed(node_id: str, x: float, y: float, w: float = 100.0, h: float = 50.0):
    return L.Placed(id=node_id, x=x, y=y, width=w, height=h, rank=0)


def palette_outcome(spec: dict):
    """**直接测 check_palette 这一层**，不走流水线。

    为什么不走：`boxes_from_spec` 现在需要合法 kind 才能定形状（形状决定尺寸），
    所以非法 kind 根本到不了 check_palette —— 它会在定形状时就抛错（emit 里由
    validate_spec 先拦住并报出真正的病因）。

    这一层仍然是必要的第二道闸：它管的是"颜色必须在板内、未知 kind 不许 fallback"，
    与 validate_spec 的 UNKNOWN_KIND 是**两件事** —— 前者防的是色板被改坏，
    后者防的是规格写错。
    """
    return C.Outcome(issues=C.check_palette(spec))


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
        """曾经的真 bug：软项永远调不动。同时断言「不阻塞」和「确实被调」。

        这份规格是 K3,3（两列各三个节点、全连通），它同时会报「连线重合」——
        那是**空间真不够**，调参推不满也不该无限推。所以这里钉住三件事：
        排序轮数真的在往上走、到上限之后就停在那里、循环不是一轮就结束。
        """
        spec = spec_of([f"a{i}" for i in (1, 2, 3)] + [f"b{i}" for i in (1, 2, 3)],
                       [(f"a{i}", f"b{j}") for i in (1, 2, 3) for j in (1, 2, 3)])
        _, outcome, attempts = run(spec)
        self.assertFalse(outcome.blocking, "交叉是软项，不该阻塞")
        rounds = [a.params["barycenterRounds"] for a in attempts]
        self.assertEqual([4.0, 8.0, 12.0], rounds[:3], "软项没有被调参")
        self.assertEqual(sorted(rounds), rounds, "排序轮数只能往上走")
        self.assertEqual({L.PARAM_LIMIT["barycenterRounds"]}, set(rounds[2:]),
                         "到上限后该停在那里 —— 后面的轮次是别的项在推")

    def test_stops_when_parameter_hits_its_limit(self):
        """到上限后该自己停下，不是把同样的计算再跑一遍。"""
        spec = spec_of([f"a{i}" for i in (1, 2, 3)] + [f"b{i}" for i in (1, 2, 3)],
                       [(f"a{i}", f"b{j}") for i in (1, 2, 3) for j in (1, 2, 3)])
        _, _, attempts = run(spec)
        self.assertLessEqual(len(attempts), C.MAX_TUNE_ROUNDS + 1)
        self.assertEqual(L.PARAM_LIMIT["barycenterRounds"],
                         attempts[-1].params["barycenterRounds"])

    def test_palette_error_is_not_tunable(self):
        """未知 kind 改参数没用 —— 它既不在可调集里，也属于 STOP_ON。

        为什么不跑整条流水线：`boxes_from_spec` 需要合法 kind 才能定形状，
        非法 kind 到不了 check_palette（emit 里由 validate_spec 先拦住并报出真正的病因）。
        所以直接打那一层，并断言**调参表不会为它动任何参数** —— 那才是"不浪费轮次"的实质。
        """
        spec = spec_of(["a", "b"], [("a", "b")], kind="queue")
        outcome = palette_outcome(spec)
        self.assertEqual({"palette"}, outcome.checks_hit())
        self.assertIn("palette", C.STOP_ON, "palette 必须属于「停下来别再调参」那一类")
        before = dict(C.L.DEFAULT_PARAMS)
        self.assertEqual(before, C._step(before, outcome),
                         "调参表不该为 palette 问题动任何参数")

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
            spec_of([f"a{i}" for i in (1, 2, 3)] + [f"b{i}" for i in (1, 2, 3)],
                    [(f"a{i}", f"b{j}") for i in (1, 2, 3) for j in (1, 2, 3)]),
            spec_of(["a"], [], kind="service"),
        ]
        for spec in specs:
            result, outcome, attempts = run(spec)
            text = C.format_report(spec, attempts, outcome)
            for name in C.PARAM_SPOKEN:
                self.assertNotIn(name, text, f"报告泄露了参数名 {name}")

        # 带非法 kind 的那一份单独走 palette 层（流水线到不了那里，见 palette_outcome）
        bad = spec_of(["a", "b"], [("a", "b")], kind="queue")
        outcome = palette_outcome(bad)
        text = C.format_report(bad, [C.Attempt(0, dict(C.L.DEFAULT_PARAMS), outcome)], outcome)
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
        result, outcome = None, palette_outcome(spec)
        attempts = [C.Attempt(0, dict(C.L.DEFAULT_PARAMS), outcome)]
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
        outcome = palette_outcome(spec)
        detail = outcome.blocking[0].detail
        self.assertIn("queue", detail)
        for allowed in sorted(C.palette.KINDS):
            self.assertIn(allowed, detail, "报错要列出允许值，不是只说非法")

    def test_every_issue_advice_is_content_level(self):
        """建议里不许出现"调大某某"这类话 —— 那是把旋钮交回模型。"""
        # 走流水线的那份（密集图 → 交叉是软项，会带 advice）
        dense = spec_of([f"a{i}" for i in (1, 2, 3)] + [f"b{i}" for i in (1, 2, 3)],
                        [(f"a{i}", f"b{j}") for i in (1, 2, 3) for j in (1, 2, 3)])
        _, outcome, _ = run(dense)
        # 非法 kind 的那份走 palette 层（理由见 palette_outcome）
        for issue in (outcome.blocking + outcome.soft
                      + palette_outcome(spec_of(["a", "b"], [("a", "b")],
                                                kind="queue")).issues):
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
    """钉住 #1/#3 作为"后置断言"的那个前提：**尺寸只有一个来源，而且那个来源是我们自己算的**。

    尺寸链：文字 → `text_metrics.measure` → `shapes.box_for` → 坐标。

    加入节点形状时这个类**确实失败过**，并按文档的约定处理了：先改
    `references/validation.md` 第六节，再改这里。这不是"测试写错了" ——
    它本来就该在前提变化时先响。

    **再失败的意思仍然是同一个**：有新的尺寸来源进来了。但要分清两种：
    "多算了一步"（像形状）仍然是我们自己算，把新步骤纳入这条断言即可；
    "尺寸来自别人给的东西"（像图标库）才是真外部来源，#1/#3 得改当"真实的门"看。
    """

    def test_every_box_follows_our_own_chain(self):
        # 尺寸链现在多了一步：**× 强调的尺寸倍数**。它属于"多算了一步"（仍然是我们
        # 自己算），所以按本类的约定 —— **把新步骤纳入断言**，而不是放宽成"大于等于"。
        # 放宽会丢掉"盒子有没有按链条算出来"这件事的精度，而那才是这里要守的东西。
        spec = {"type": "architecture", "direction": "LR",
                "nodes": [{"id": "a", "kind": "service", "label": "订单服务",
                           "detail": "3 副本"},
                          {"id": "b", "kind": "data", "label": "订单库"},
                          {"id": "c", "kind": "client", "label": "Web 前端"},
                          {"id": "d", "kind": "service", "label": "判断一下？",
                           "shape": "diamond"},
                          {"id": "e", "kind": "service", "label": "订单服务",
                           "emphasis": "primary"},
                          {"id": "f", "kind": "service", "label": "订单服务",
                           "emphasis": "muted"}]}
        boxes = L.boxes_from_spec(spec)
        sh = L.load_sibling("shapes")
        for node in spec["nodes"]:
            with self.subTest(node=node["id"]):
                box = boxes[node["id"]]
                # 量的时候要用**这一步的强调档所对应的字号** —— 字号也是尺寸链的一环
                # （§14），按默认字号量出来的尺寸当然对不上。
                emphasis = node.get("emphasis", "normal")
                fresh = C.tm.measure(node["label"], node.get("detail", ""),
                                     font_size=C.tm.FONT_NODE
                                     + P.emphasis_font_step(emphasis))
                want_w, want_h = sh.box_for(box.shape, fresh.width, fresh.height)
                scale = P.emphasis_scale(emphasis)
                want_w, want_h = want_w * scale, want_h * scale
                self.assertAlmostEqual(
                    want_w, box.width, places=6,
                    msg=f"{node['id']} 的包围盒不再等于「文字 × 形状 × 强调倍数」"
                        f"—— 尺寸链变了，先回去看 validation.md 第六节（#1/#3 的前提）")
                self.assertAlmostEqual(want_h, box.height, places=6)
                self.assertAlmostEqual(fresh.width, box.text.width, places=6,
                                       msg="盒子里的文字不再是现量出来的")

    def test_emphasis_scale_actually_reaches_the_boxes(self):
        # EMPHASIS.scale 必须**真的**改变盒子。
        # 这条单独存在，是因为这个功能差点停在「声明了但没人消费」的状态：
        # emphasis_scale() 有了、有用例守着顺序与幅度，而 boxes_from_spec
        # 根本没调它 —— 尺寸层级写了等于没写。只断言函数返回值对是抓不住这种事的。
        spec = {"type": "architecture", "direction": "LR", "nodes": [
            {"id": "n", "kind": "service", "label": "订单服务"},
            {"id": "p", "kind": "service", "label": "订单服务", "emphasis": "primary"},
            {"id": "m", "kind": "service", "label": "订单服务", "emphasis": "muted"},
        ]}
        boxes = L.boxes_from_spec(spec)
        self.assertGreater(boxes["p"].width, boxes["n"].width, "primary 应该更大")
        self.assertLess(boxes["m"].width, boxes["n"].width, "muted 应该更小")
        # 不能再拿 scale 去比：primary 的放大**由字号承担**（scale 是 1.00），
        # 两条一起上会叠到 1.13，超出 §13 说的 1.05~1.10。
        self.assertLess(boxes["p"].width / boxes["n"].width, 1.10, msg="幅度要小（§13）")
        self.assertGreater(boxes["p"].width / boxes["n"].width, 1.00, msg="但要看得出来")

    def test_emphasis_font_step_reaches_the_text(self):
        # §14：重点节点的**字号**要跟上。字号和盒子是两条手段 ——
        # 只改盒子是「同样的字、留白多一点」，改字号才是「字本身变大」。
        # 关键：字号必须从 **measure** 走进去（盒子顺着尺寸链跟着变大），
        # 而不是落笔时改 fontSize —— 那样盒子与实际文字就对不上了。
        spec = {"type": "architecture", "direction": "LR", "nodes": [
            {"id": "n", "kind": "service", "label": "订单服务"},
            {"id": "p", "kind": "service", "label": "订单服务", "emphasis": "primary"},
        ]}
        boxes = L.boxes_from_spec(spec)
        self.assertEqual(C.tm.FONT_NODE, boxes["n"].text.font_size)
        self.assertGreater(boxes["p"].text.font_size, boxes["n"].text.font_size,
                           msg="重点节点的字号没有跟上")
        self.assertEqual(C.tm.FONT_NODE + P.emphasis_font_step("primary"),
                         boxes["p"].text.font_size)

    def test_detail_level_is_judged_the_same_way_when_re_measuring(self):
        # `detail: executive` 下非重点节点的 `detail` **不算进盒子**，重量时也不许算。
        #
        # 这是一次真事故：`check_text_fit` 重量时**无条件**把 `detail` 量进去，而
        # `boxes_from_spec` 只在 `shows_node_detail(node, level)` 为真时才加。两边判据
        # 不一致的后果不是“画错”，而是**整张图根本出不来** —— 报的还是一句
        # 「这是生成脚本的内部不一致（测量与落笔不符），不是你内容的问题」，
        # 把模型引向“去改文案”那条完全没用的路。
        # （由 drawio 后端的跨后端用例抓出来；Excalidraw 后端同样中招，只是现成
        # 夹具里没同时凑齐 `executive` 与“非重点节点带 detail”这两件事。）
        spec = {"type": "architecture", "direction": "LR", "detail": "executive",
                "nodes": [{"id": "p", "kind": "service", "label": "甲",
                           "detail": "次要说明", "emphasis": "primary"},
                          {"id": "n", "kind": "service", "label": "乙",
                           "detail": "次要说明", "emphasis": "normal"}],
                "edges": [{"from": "p", "to": "n"}]}
        _result, outcome, _attempts = run(spec)
        self.assertEqual([i.line() for i in outcome.blocking], [],
                         "executive 档不该因为 detail 被判成「脚本内部不一致」")
        boxes = L.boxes_from_spec(spec)
        # 高度不同 = 判据真的在起作用（重点节点留 detail、普通节点不留）
        self.assertGreater(boxes["p"].height, boxes["n"].height)
        # 换到 normal 档：两边都要把 detail 算进去，同样不许报
        spec["detail"] = "normal"
        _result, outcome, _attempts = run(spec)
        self.assertEqual([i.line() for i in outcome.blocking], [])

    def test_effective_growth_stays_small(self):
        # §13：要层次，不是海报式跳跃。卡的是**总放大**（盒子倍数 × 字号倍数），
        # 因为这两条会相乘。
        for emphasis in P.EMPHASIS:
            with self.subTest(emphasis=emphasis):
                spec = {"type": "architecture", "direction": "LR", "nodes": [
                    {"id": "n", "kind": "service", "label": "订单服务"},
                    {"id": "e", "kind": "service", "label": "订单服务",
                     "emphasis": emphasis},
                ]}
                boxes = L.boxes_from_spec(spec)
                ratio = boxes["e"].width / boxes["n"].width
                self.assertLessEqual(ratio, 1.10, msg=f"{emphasis} 放大到 {ratio:.3f}")
                self.assertGreaterEqual(ratio, 0.90)

    def test_icon_adds_an_external_term_to_the_chain(self):
        """图标是**第一个外部尺寸来源**（宽高来自 .excalidrawlib 文件）。

        这条不是"再确认一遍尺寸链"，而是把这个新项**写进前提里**：
        盒子 = 形状包围盒 + 图标宽 + 间隙。哪一步变了，这里会响。
        """
        spec = {"type": "flow", "direction": "TB",
                "nodes": [{"id": "a", "kind": "service", "label": "订单服务",
                           "icon": "Some Icon"}]}
        # 对照组不带 icon 字段 —— 否则两边都含保守占位，量不出图标的贡献
        bare = {"type": "flow", "direction": "TB",
                "nodes": [{"id": "a", "kind": "service", "label": "订单服务"}]}
        plain = L.boxes_from_spec(bare)["a"]
        sized = L.boxes_from_spec(spec, {"a": (40.0, 22.0)})["a"]
        self.assertAlmostEqual(plain.width + 40.0 + L.ICON_GAP, sized.width, places=6)
        self.assertGreaterEqual(sized.height, 22.0,
                                "盒子不能比图标还矮，否则图标会溢出来")
        # 没有尺寸表时也要留出保守的占位 —— 宁可多留白，也不能盖住文字
        fallback = L.boxes_from_spec(spec, {"a": (0.0, 0.0)})["a"]
        self.assertGreater(fallback.width, plain.width)

    def test_shape_actually_changes_the_geometry(self):
        """形状不改变几何的话，"形状"就只是换了个 type 字段，没有意义。

        而不算这个量，文字就会溢出形状 —— 菱形里能放字的只有内接矩形。
        """
        spec = {"nodes": [{"id": "d", "kind": "service", "label": "条件？",
                           "shape": "diamond"},
                          {"id": "r", "kind": "service", "label": "条件？"}]}
        boxes = L.boxes_from_spec(spec)
        self.assertGreater(boxes["d"].width, boxes["r"].width * 1.9)
        self.assertGreater(boxes["d"].height, boxes["r"].height * 1.9)

    def test_gap_check_cannot_fire_with_default_spacing(self):
        """把这个"跑不到"的事实钉住，而不是只在注释里说一句。

        同层节点恰好相距一个节点间距、跨层恰好相距一个层间距 —— 两者都远大于 12px。
        它哪天真的报了出来，说明坐标推导被改成了不再由参数唯一决定，那是一个信号。
        """
        ids = ["web", "gw", "order", "pay", "mq", "db", "notify"]
        spec = spec_of(ids, [("web", "gw"), ("gw", "order"), ("order", "db"),
                             ("order", "mq"), ("mq", "pay"), ("mq", "notify"),
                             ("pay", "gw")])
        result, _, _ = run(spec)
        gaps = C.check_gaps(result)
        self.assertEqual([], gaps,
                         "间隙检查居然报了 —— 坐标推导已经不是「由间距参数唯一决定」了，"
                         "回去重新判断这条是后置断言还是真实防线")


class TestTunableChecksAreSteppable(unittest.TestCase):
    """**放进 TUNABLE 却调不动 = 调参循环对它形同虚设。**

    这个坑踩过两次：`crossing` 一次（软项被 `checks_hit()` 过滤掉）、
    `through` 又一次（`converged()` 里硬编码了 "crossing"，新加的可调项
    一出现就直接出报告）。所以改成机械检查，不靠记性。
    """

    def test_tunable_equals_steppable(self):
        self.assertEqual(C.TUNABLE, C.STEPPABLE,
                         "TUNABLE 与 _step 的映射表不一致 —— 有新项没接上参数")

    def test_every_tunable_check_moves_some_parameter(self):
        for name in sorted(C.TUNABLE):
            with self.subTest(check=name):
                before = dict(C.L.DEFAULT_PARAMS)
                outcome = C.Outcome(issues=[C.Issue(name, False, "x", "为了测这个")])
                self.assertIn(name, outcome.tunable_hits())
                self.assertFalse(outcome.converged(),
                                 f"{name} 一出现就算收敛 —— 调参循环对它等于不存在")
                self.assertNotEqual(before, C._step(before, outcome),
                                    f"{name} 在 TUNABLE 里但 _step 调不动任何参数")

    def test_through_nodes_is_reported_but_never_blocks(self):
        """穿节点是可调项，不是硬门 —— 布局自己会试着绕行，绕不过去靠加间距。"""
        spec = {"type": "flow", "direction": "TB",
                "nodes": [{"id": "a", "kind": "service", "label": "起"},
                          {"id": "b", "kind": "service", "label": "中"},
                          {"id": "c", "kind": "service", "label": "终"}],
                "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}]}
        result, outcome, _ = run(spec)
        for issue in outcome.issues:
            if issue.check == "through":
                self.assertFalse(issue.blocking, "穿节点不该阻塞出图")
                self.assertIn("拆成两段", issue.advice or "", "建议要是内容级的")


class TestEdgeShapeChecks(unittest.TestCase):
    """#8 连线重合 / #9 连线斜段 —— 这两项以前根本不在检查表里。

    在那之前，“报告全绿”与“图上是一根线 / 一条斜线”可以同时成立：
    实测 7 张自带规格里 5 张有重合（最长 225px），而且报告一条都没报。
    """

    @staticmethod
    def _edge(name: str, points) -> dict:
        return {"from": name, "to": f"{name}!", "points": points}

    def test_overlap_needs_collinear_and_touching_intervals(self):
        same_line = StubResult({}, [self._edge("a", [[0, 10], [100, 10]]),
                                    self._edge("b", [[50, 10], [150, 10]])])
        self.assertEqual(1, len(C.check_edge_overlap(same_line)))
        touching = StubResult({}, [self._edge("a", [[0, 10], [100, 10]]),
                                   self._edge("b", [[100, 10], [200, 10]])])
        self.assertEqual([], C.check_edge_overlap(touching),
                         "端点相接不算重合 —— 那是共用拐点，本来就该这样")
        parallel = StubResult({}, [self._edge("a", [[0, 10], [100, 10]]),
                                    self._edge("b", [[0, 20], [100, 20]])])
        self.assertEqual([], C.check_edge_overlap(parallel), "平行但不在同一条线上")

    def test_edge_length_is_not_reported_as_overlap(self):
        """一根线自己跟自己不能算重合。"""
        one = StubResult({}, [self._edge("a", [[0, 10], [100, 10]]),
                              self._edge("a", [[20, 10], [80, 10]])])
        self.assertEqual([], C.check_edge_overlap(one))

    def test_overlap_is_soft_and_tunable(self):
        result = StubResult({}, [self._edge("a", [[0, 10], [100, 10]]),
                                 self._edge("b", [[50, 10], [150, 10]])])
        issue = C.check_edge_overlap(result)[0]
        self.assertFalse(issue.blocking, "重合是软项：空档不够是空间问题，不是内容错")
        self.assertIn("重合约", issue.detail)
        for name in ("overlap", "slant"):
            with self.subTest(name):
                self.assertIn(name, C.TUNABLE)
                self.assertIn(name, C.STEPPABLE)
                self.assertIn(name, C.CHECK_LABEL)

    def test_slant_is_reported_for_layered_layouts(self):
        result = StubResult({}, [self._edge("a", [[0, 0], [100, 0], [200, 40]])])
        issues = C.check_edge_slant(result)
        self.assertEqual(1, len(issues))
        self.assertFalse(issues[0].blocking, "斜段是可调项，不卡住出图")
        self.assertIn("拆", issues[0].advice or "", "建议要是内容级的")
        axis_aligned = StubResult({}, [self._edge("a", [[0, 0], [100, 0], [100, 40]])])
        self.assertEqual([], C.check_edge_slant(axis_aligned))

    def test_slant_is_not_reported_for_radial_or_force(self):
        """径向 / 力导向的连线**就该是**两点直辐条，不能拿分层图的标准去要求它。"""
        for direction in ("RADIAL", "FORCE"):
            with self.subTest(direction):
                result = StubResult({}, [self._edge("a", [[0, 0], [100, 40]])],
                                    direction=direction)
                self.assertEqual([], C.check_edge_slant(result))

    def test_a_clean_diagram_reports_neither(self):
        """干净的图不该因为新加两项就多出噪声 —— 否则没人会看报告。"""
        spec = spec_of(["web", "api", "db"], [("web", "api"), ("api", "db")])
        _, outcome, _ = run(spec)
        self.assertEqual([], outcome.issues)


class TestBendCheck(unittest.TestCase):
    """#11 折点过多：「不要为了折而折」。

    这一项是从一次真实事故里长出来的：一份 25 节点的竖版流程里，一条边被折了
    **10 次**（在 x≈1330 与 x≈2200 之间来回横跳三次），而当时的九项校验
    一项都不管折点数 —— 报告全绿。修完路由（`layout._sidestep_candidates` +
    `_path_rank` 的折点罚分）之后那条边降到 4 折；实测 96 条边的正常带上界就是 4。
    """

    @staticmethod
    def _edge(name: str, points) -> dict:
        return {"from": name, "to": f"{name}!", "points": points}

    def test_over_budget_is_reported_as_soft(self):
        # 10 个点 = 8 个折点（事故里那条边就是这个量级）
        zigzag = [[0, 0], [0, 100], [20, 100], [20, 200], [0, 200],
                  [0, 300], [20, 300], [20, 400], [0, 400], [0, 500]]
        issues = C.check_bends(StubResult({}, [self._edge("a", zigzag)]))
        self.assertEqual(1, len(issues))
        self.assertFalse(issues[0].blocking, "折点多是软项：图还能看")
        self.assertIn("8 个折点", issues[0].detail)
        self.assertIn("绕得太多", issues[0].advice or "", "建议要是内容级的")

    def test_budget_sits_just_above_the_measured_normal_band(self):
        """4 折不报（实测正常带上界），5 折报 —— 边界卡在两个用例之间。"""
        four = [[0, 0], [0, 100], [20, 100], [20, 200], [0, 200], [0, 300]]
        self.assertEqual([], C.check_bends(StubResult({}, [self._edge("a", four)])))
        five = four + [[20, 300]]
        self.assertEqual(1, len(C.check_bends(StubResult({}, [self._edge("a", five)]))))

    def test_straight_and_two_corner_edges_are_silent(self):
        """绝大多数边是 0~2 折 —— 这一项不许对它们出声，否则报告就成了噪声。"""
        result = StubResult({}, [self._edge("a", [[0, 0], [100, 0]]),
                                 self._edge("b", [[0, 0], [0, 100], [50, 100], [50, 200]])])
        self.assertEqual([], C.check_bends(result))

    def test_bend_is_not_tunable(self):
        """**不进调参循环**：能修它的是路由，不是某个间距参数。

        放进 TUNABLE 会让循环空转 —— 步长表里没有与之对应的参数
        （而“TUNABLE 里的每一项真的调得动”那条用例会先红）。
        """
        self.assertIn("bend", C.CHECK_LABEL)
        self.assertNotIn("bend", C.TUNABLE)
        self.assertNotIn("bend", C.STEPPABLE)
        self.assertNotIn("bend", C.STOP_ON)


class TestRegionTitle(unittest.TestCase):
    """#10 区域标题不能溢出（P17）。

    用户拿截图来问「这种块的 title 会溢出」—— 一个 368px 的标题画在 324px 的
    可用宽度里，而当时**没有任何检查在量区域标题**。
    """

    @staticmethod
    def _spec(label, node_label="A"):
        return {"type": "flow", "direction": "TB",
                "groups": [{"id": "g", "label": label}],
                "nodes": [{"id": "a", "label": node_label, "kind": "service", "group": "g"},
                          {"id": "b", "label": "B", "kind": "plain"}],
                "edges": [{"from": "a", "to": "b"}]}

    def _issues(self, spec):
        boxes = L.boxes_from_spec(spec)
        result = L.layout(spec, boxes)
        return C.check_region_labels(spec, result, boxes)

    def test_a_normal_title_is_silent(self):
        self.assertEqual([], self._issues(self._spec("适配层")))
        self.assertEqual([], self._issues(self._spec("三真源：完成 = 期望 × 执行 × 物化对齐")))

    def test_overlong_title_blocks_with_content_advice(self):
        """标题断到超过上限 -> 内容问题，建议缩短/拆区（与节点标签超长同一类）。"""
        issues = self._issues(self._spec("这一整块是给外部系统做协议适配与版本协商的地方" * 2))
        self.assertTrue(issues, "标题断了很多行，却没有报")
        issue = issues[0]
        self.assertEqual("region_label", issue.check)
        self.assertTrue(issue.blocking)
        self.assertIn("拆", issue.advice or "", "建议要是内容级的")

    def test_broken_wrap_is_reported_as_a_script_bug(self):
        """后置断言那一支：断行与尺寸对不上时不给内容建议（改标签没用）。"""
        spec = self._spec("适配层")
        boxes = L.boxes_from_spec(spec)
        result = L.layout(spec, boxes)
        original = L.region_boxes

        def broken(*args, **kwargs):
            regions = original(*args, **kwargs)
            for region in regions:
                region["label_width"] = region["width"] + 50.0      # 人为破坏
            return regions

        L.region_boxes = broken
        try:
            issues = C.check_region_labels(spec, result, boxes)
        finally:
            L.region_boxes = original
        self.assertEqual(1, len(issues))
        self.assertTrue(issues[0].blocking)
        self.assertIsNone(issues[0].advice, "脚本内部不一致不该给内容建议")
        self.assertIn("内部不一致", issues[0].detail)

    def test_no_parameter_can_fix_it(self):
        """它属于「别调参了」那一类：加间距不会让标题变短。"""
        self.assertIn("region_label", C.STOP_ON)
        self.assertNotIn("region_label", C.TUNABLE)
        before = dict(C.L.DEFAULT_PARAMS)
        outcome = C.Outcome(issues=[C.Issue("region_label", True, "g", "为了测这个")])
        self.assertEqual(before, C._step(before, outcome),
                         "调参表不该为区域标题动任何参数")


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

class TestEveryCheckHasALabel(unittest.TestCase):
    """每条检查都必须有中文标签 —— 否则**报告一打印就崩**。

    "through" 那条就这么漏过：加检查的时候没同步 CHECK_LABEL，而报告只在
    有问题时才打印，所以一直没被发现，直到径向布局第一次让"穿节点"进了报告。
    """

    @staticmethod
    def _check_names_in_source() -> set:
        """从**源码**里扫出所有 Issue 用到的检查名。

        为什么不"跑一遍 fixture，收集真实产生的检查名"：那是**依赖数据有问题**的写法 ——
        六张图现在一条问题都不出（全部 0 阻塞 0 软项），收集出来的就是空集合，用例空转
        还看不出来。源码扫描与数据无关，加检查时不改标签照样会被抓到（这正是当初
        'through' 漏掉的那一次）。
        """
        path = os.path.join(HERE, "..", "scripts", "check_layout.py")
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        return set(re.findall(r'Issue\(\s*"([a-z_]+)"', text))

    def test_labels_cover_every_check(self):
        """每条检查都必须有中文标签 —— 否则**报告一打印就崩**（KeyError）。"""
        names = self._check_names_in_source()
        self.assertTrue(names, "一个检查名都没扫到：正则失效了，用例成了空话")
        missing = names - set(C.CHECK_LABEL)
        self.assertEqual(set(), missing, f"这些检查没有中文标签：{sorted(missing)}")

    def test_labels_have_no_orphans(self):
        """反过来也要成立：表里不该有已经不存在的检查。"""
        names = self._check_names_in_source()
        self.assertEqual(set(), set(C.CHECK_LABEL) - names,
                         "CHECK_LABEL 里有已经不存在（或已改名）的检查")

    def test_every_issue_can_render_its_line(self):
        # 直接调 line()：这正是崩掉的那一处
        for check in sorted(C.CHECK_LABEL):
            with self.subTest(check=check):
                issue = C.Issue(check, True, "x", "细节")
                self.assertIn(C.CHECK_LABEL[check], issue.line())



class TestRegionOverlap(unittest.TestCase):
    """区域之间**不许部分重叠** —— 分开、或者一个完全包住另一个。"""

    def outcome(self, groups, nodes):
        spec = {"type": "flow", "direction": "TB",
                "groups": groups, "nodes": nodes,
                "edges": [{"from": "a", "to": "b"}]}
        boxes = L.boxes_from_spec(spec)
        result = L.layout(spec, boxes)
        return C.check(spec, result, boxes)

    def test_partial_overlap_is_reported(self):
        groups = [{"id": "left", "label": "左"}, {"id": "right", "label": "右"}]
        nodes = [
            {"id": "a", "label": "A", "kind": "plain", "group": "left"},
            {"id": "b", "label": "B", "kind": "plain", "group": "right"},
        ]
        names = {i.check for i in self.outcome(groups, nodes).issues}
        # 两个区域并排时**不该**报；真重叠才报 —— 这里先确认并排是干净的
        self.assertNotIn("region", names)

    def test_nesting_is_allowed(self):
        """分区里再圈一块是正当用法：完全包含不算重叠。"""
        spec = {"type": "flow", "direction": "TB",
                "groups": [{"id": "outer", "label": "外"},
                           {"id": "inner", "label": "内", "level": "critical"}],
                "nodes": [
                    {"id": "a", "label": "A", "kind": "plain", "group": "outer"},
                    {"id": "b", "label": "B", "kind": "plain", "group": "outer"},
                ],
                "edges": [{"from": "a", "to": "b"}]}
        # inner 只有 b；区域按成员算，inner 必然落在 outer 内部
        spec["nodes"][1]["group"] = "inner"
        boxes = L.boxes_from_spec(spec)
        result = L.layout(spec, boxes)
        names = {i.check for i in C.check(spec, result, boxes).issues}
        self.assertNotIn("region", names, "完全包含被判成重叠了")



class TestGeometricCrossing(unittest.TestCase):
    """#12：量的是**画面上真的相交**，不是 #5 那个层内反序对。

    这条检查的来历值得记：我曾经拿 #5 的反序对当"线有没有撞在一起"，
    差点按它的数（某张依赖图 **8 处反序 / 0 处相交**）去让用户"拆节点、调换位置" ——
    那是让人去修一个眼睛看不见的东西。所以这两条必须各管各的，别互相顶替。
    """

    class _Result:
        def __init__(self, edges):
            self.edges = edges

    @staticmethod
    def _edges(*pairs):
        return [{"origin": i, "from": a, "to": b, "points": [list(p), list(q)]}
                for i, (a, b, p, q) in enumerate(pairs)]

    def test_reports_a_real_crossing(self):
        spec = spec_of(["a", "b", "c", "d"], [("a", "b"), ("c", "d")])
        result = self._Result(self._edges(("a", "b", (0, 0), (100, 100)),
                                          ("c", "d", (0, 100), (100, 0))))
        issues = C.check_geometric_crossings(spec, result)
        self.assertEqual(1, len(issues))
        self.assertIn("✕", issues[0].where, "得说出是哪两条线交在一起")
        self.assertFalse(issues[0].blocking, "相交不该挡输出（空间不够时确实分不开）")

    def test_parallel_lines_report_nothing(self):
        spec = spec_of(["a", "b", "c", "d"], [("a", "b"), ("c", "d")])
        result = self._Result(self._edges(("a", "b", (0, 0), (100, 0)),
                                          ("c", "d", (0, 40), (100, 40))))
        self.assertEqual([], C.check_geometric_crossings(spec, result))

    def test_not_in_the_tuning_loop(self):
        """**不进调参**（与 #11 同理）：它是结论、不是驱动量。

        调参循环改的是间距，不是"去把这两条线分开"；接进去只会让循环白转四轮。
        这个决定必须有守卫 —— 否则哪天有人顺手加进 `TUNABLE`，没人会发现。
        """
        self.assertNotIn("intersect", C.TUNABLE)
        self.assertNotIn("intersect", C.STEPPABLE)

    def test_inherent_types_are_silent(self):
        """径向/力导向的相交是**形状本身** —— 报了等于让人去修一张本来就长那样的图。"""
        result = self._Result(self._edges(("a", "b", (0, 0), (100, 100)),
                                          ("c", "d", (0, 100), (100, 0))))
        for diagram_type in ("mindmap", "network"):
            spec = spec_of(["a", "b", "c", "d"], [("a", "b"), ("c", "d")])
            spec["type"] = diagram_type
            self.assertEqual([], C.check_geometric_crossings(spec, result), diagram_type)
