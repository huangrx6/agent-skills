#!/usr/bin/env python3
"""layout.py 的回归测试。

## 用例的选择标准

这一轮实测踩到的 bug 全部进了用例 —— 每个都对应一个**具体的、曾经真实发生过**的错，
而不是"为了覆盖面"补的：

| 用例 | 对应的真实 bug |
| --- | --- |
| `test_split_edge_is_still_routed` | 跨层边在 `route_edges` 里被整条漏掉（首段被当虚节点段跳过） |
| `test_parallel_long_edges_do_not_share_a_chain` | 同一节点出发的两条长边串线（按 `from` 匹配虚节点） |
| `test_duplicate_edges_stay_separate` | 重复边被当成同一条（origin 用 from/to 对不够） |
| `test_explicit_rank_conflict_raises` | 显式 rank 被静默放宽（B 写了 rank 0，代码把它推成 6） |
| `test_empty_rank_does_not_crash` | 空层导致 KeyError |
| `test_crossings_recounted_after_pin` | pin 改了层内顺序后交叉数没重算 |
| `test_pin_conflict_falls_back_and_records` | 主轴 pin 不校验边约束，排不出合法分层 |

## 交叉数为什么用"已知答案的小图"

层内排序是 Sugiyama 里唯一不 trivial 的部分（`layout.py` 自己也这么说）。
它的质量只有一个客观指标 —— 交叉数。所以这个指标必须先被证明**测得准**，
否则"排序变好了"是没有依据的。K3,3 的答案可以手算：2 层直线画法下
C(3,2) × C(3,2) = 9，且与顺序无关。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/test_layout.py
"""

from __future__ import annotations

import importlib.util
import os
import random
import subprocess
import sys
import math
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
# 测试住在仓库顶层 `tests/<skill>/`（**刻意不在 skill 目录里**：AI 调用 skill 时读的是
# `skills/<skill>/` 那棵树，测试放在里面会被顺手读进去）。
# 所以从 `tests/<skill>/` 往上两级到仓库根，再进 `skills/<skill>/`。
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
SCRIPTS = os.path.join(SKILL, "scripts")
LAYOUT = os.path.join(SCRIPTS, "layout.py")


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    # 先注册再 exec —— 不注册的话被加载模块里的 @dataclass 会炸
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


L = _load("layout", LAYOUT)


def box(w: float = 120.0, h: float = 60.0):
    """布局用的尺寸。真实尺寸由 text_metrics 反推，测试里固定住以便手算。"""
    return L.Box(w, h)


def spec_of(node_ids, edges, **kw) -> dict:
    return {"type": kw.pop("type", "architecture"), "direction": kw.pop("direction", "LR"),
            "nodes": [{"id": n, "kind": "service", "label": n} for n in node_ids],
            "edges": [{"from": a, "to": b} for a, b in edges], **kw}


def boxes_for(node_ids, w: float = 120.0, h: float = 60.0) -> dict:
    return {n: box(w, h) for n in node_ids}


def segs(pairs) -> list[dict]:
    return [{"from": a, "to": b} for a, b in pairs]


class TestCrossingCount(unittest.TestCase):
    """交叉数是这个模块唯一的客观质量指标，先证明它测得准。"""

    def test_crossing_pair_counts_as_one(self):
        order = {0: ["a1", "a2"], 1: ["b1", "b2"]}
        self.assertEqual(1, L.count_crossings(order, segs([("a1", "b2"), ("a2", "b1")])))

    def test_reordering_target_layer_removes_crossing(self):
        order = {0: ["a1", "a2"], 1: ["b2", "b1"]}
        self.assertEqual(0, L.count_crossings(order, segs([("a1", "b2"), ("a2", "b1")])))

    def test_parallel_edges_never_cross(self):
        order = {0: ["a1", "a2"], 1: ["b1", "b2"]}
        self.assertEqual(0, L.count_crossings(order, segs([("a1", "b1"), ("a2", "b2")])))

    def test_k33_has_nine_crossings(self):
        """K3,3：2 层直线画法下 C(3,2)×C(3,2) = 9，且与顺序无关。"""
        order = {0: ["a1", "a2", "a3"], 1: ["b1", "b2", "b3"]}
        e = segs([(a, b) for a in ("a1", "a2", "a3") for b in ("b1", "b2", "b3")])
        self.assertEqual(9, L.count_crossings(order, e))

    def test_non_adjacent_layers_are_not_counted(self):
        """跨层边必须先拆虚节点，否则相邻层之间没有定义。"""
        order = {0: ["a1"], 1: ["m1"], 2: ["b1"]}
        self.assertEqual(0, L.count_crossings(order, segs([("a1", "b1")])))

    def test_count_and_pairs_share_one_implementation(self):
        """计数与定位必须一致 —— 对不上比没有指标更糟，人会先怀疑自己的图。"""
        order = {0: ["a1", "a2", "a3"], 1: ["b1", "b2", "b3"]}
        e = segs([(a, b) for a in ("a1", "a2", "a3") for b in ("b1", "b2", "b3")])
        self.assertEqual(L.count_crossings(order, e), len(L.crossing_pairs(order, e)))


class TestRanking(unittest.TestCase):
    def test_longest_path_layering(self):
        """菱形：A → (B,C) → D。D 取最长路径，落在 rank 2。"""
        s = spec_of("ABCD", [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")])
        r = L.layout(s, boxes_for("ABCD"))
        self.assertEqual({"A": 0, "B": 1, "C": 1, "D": 2}, r.ranks)

    def test_explicit_rank_is_respected(self):
        """A→B→C 链上把 B 钉到 rank 3，C 必须被推到 4。"""
        s = spec_of("ABC", [("A", "B"), ("B", "C")])
        s["nodes"][1]["rank"] = 3
        r = L.layout(s, boxes_for("ABC"))
        self.assertEqual(3, r.ranks["B"])
        self.assertEqual(4, r.ranks["C"])

    def test_explicit_rank_conflict_raises(self):
        """B 写了 rank 0，但 A→B 要求 B 在 A 之后 —— 该报错，不该静默放宽。"""
        s = spec_of("AB", [("A", "B")])
        s["nodes"][0]["rank"] = 5
        s["nodes"][1]["rank"] = 0
        with self.assertRaises(ValueError) as ctx:
            L.layout(s, boxes_for("AB"))
        self.assertIn("rank", str(ctx.exception))

    def test_empty_rank_does_not_crash(self):
        """显式 rank 把节点抬到高处后，中间会留下一整段没有节点的层。"""
        s = spec_of("AB", [("A", "B")])
        s["nodes"][0]["rank"] = 3
        r = L.layout(s, boxes_for("AB"))
        self.assertEqual(3, r.ranks["A"])
        self.assertEqual(4, r.ranks["B"])


class TestCycles(unittest.TestCase):
    def test_back_edge_is_reversed_and_kept(self):
        s = spec_of("ABC", [("A", "B"), ("B", "C"), ("C", "A")], type="flow",
                    direction="TB")
        r = L.layout(s, boxes_for("ABC"))
        self.assertTrue(r.reversed_edges, "环上的回边没被识别")
        self.assertEqual(3, len(r.edges), "环上的边丢了")

    def test_cycle_still_produces_distinct_ranks(self):
        s = spec_of("ABC", [("A", "B"), ("B", "C"), ("C", "A")], type="flow")
        r = L.layout(s, boxes_for("ABC"))
        self.assertEqual(3, len(set(r.ranks.values())), "有环时排不出不同的层")


class TestLongEdges(unittest.TestCase):
    """虚节点。这组用例全部对应实测踩到的 bug。"""

    SPEC = spec_of("ABCDE", [("A", "B"), ("B", "C"), ("C", "D"), ("D", "E"),
                             ("A", "D"), ("A", "E")])
    IDS = "ABCDE"

    def setUp(self):
        self.r = L.layout(self.SPEC, boxes_for(self.IDS))

    def edge(self, a: str, b: str) -> dict:
        return next(e for e in self.r.edges if e["from"] == a and e["to"] == b)

    def test_split_edge_is_still_routed(self):
        """跨层边不能在 route_edges 里被整条漏掉（首段带虚节点，按段遍历会跳过它）。"""
        self.assertEqual(6, len(self.r.edges), "边数不对 —— 跨层边很可能被漏掉了")

    def test_dummy_count_matches_span(self):
        """A(0)→D(3) 跨 3 层插 2 个虚节点；A(0)→E(4) 跨 4 层插 3 个；合计 5。

        数的是**布局内**的虚节点（`dummy_count`），不是渲染出来的折点数 ——
        渲染会拉直，两者本来就不该永远相等（以前这里断 `len(points)`，
        把「虚节点链」和「画出来的折线」当成了同一个东西）。
        这一段同时守住渲染后的两条硬性质：不穿节点、每一段都比可见下限长。
        """
        self.assertEqual(5, self.r.dummy_count)
        for a, b in (("A", "D"), ("A", "E")):
            pts = self.edge(a, b)["points"]
            self.assertGreaterEqual(len(pts), 2)
            self.assertEqual([], L.nodes_hit_by_polyline(pts, self.r.placed, {a, b}),
                             f"{a}→{b} 的折线穿过了节点")
            for first, second in zip(pts, pts[1:]):
                self.assertGreaterEqual(math.dist(first, second), L.EDGE_MIN - 0.01,
                                        f"{a}→{b} 有一段短于可见下限")

    def test_parallel_long_edges_do_not_share_a_chain(self):
        """同一节点出发的两条长边必须各走自己的链。"""
        ad, ae = self.edge("A", "D")["points"], self.edge("A", "E")["points"]
        # 断「整条路径不相同、而且都不穿节点」—— 比原来的「第 1 个拐点不同」结实：
        # 正交路由可能把某一条拉成两点直线（没有拐点），那时按下标取点就没有意义了。
        self.assertNotEqual(ad, ae, "两条长边画成了同一条线 —— 它们串线了")
        for name, pts in (("A→D", ad), ("A→E", ae)):
            self.assertEqual([], L.nodes_hit_by_polyline(pts, self.r.placed, {"A", "D", "E"}),
                             f"{name} 穿过了别的节点")

    def test_dummies_are_apart_by_dummy_separation(self):
        """虚节点不能吃掉整个节点间距，但也不能重合（否则平行边看起来是一条）。

        查的是**虚节点自己的位置**（`placed` 里带前缀的那些），不是渲染出来的折点 ——
        渲染那一步会「能直就直」（`straighten`），折点跟虚节点已经不是一回事了。
        以前这里读 `points[1]`，等于把两个东西当成一个。
        """
        dummies = {nid: p for nid, p in self.r.placed.items()
                   if nid.startswith(L.DUMMY_PREFIX)}
        self.assertTrue(dummies, "一条跨层边都没插虚节点")
        by_rank: dict[int, list[float]] = {}
        for p in dummies.values():
            by_rank.setdefault(p.rank, []).append(p.y)
        first = sorted(by_rank[min(by_rank)])
        self.assertEqual(2, len(first), "第一层里的虚节点数不对（两条长边各一个）")
        self.assertAlmostEqual(L.DUMMY_SEPARATION, first[1] - first[0], delta=0.5)

    def test_dummy_boxes_are_not_visual(self):
        """虚节点不进 real_nodes()，否则会被当成元素去查间隙。"""
        self.assertEqual(set(self.IDS), set(self.r.real_nodes()))

    def test_reversed_edge_points_are_flipped_back(self):
        """回边的折线要反回来，而且 from/to 得跟着一起反 —— 只反点不反 from/to
        会让两端与走向相反，下游照着 from→to 画箭头就会画反。"""
        s = spec_of("ABC", [("A", "B"), ("B", "C"), ("C", "A")], type="flow",
                    direction="LR")
        r = L.layout(s, boxes_for("ABC"))
        back = next(e for e in r.edges if e["reversed"])
        # 原始边是 C→A（C 在右、A 在左），所以保持原始方向
        self.assertEqual(("C", "A"), (back["from"], back["to"]))
        c_node, a_node = r.placed["C"], r.placed["A"]
        pts = back["points"]
        # 折线应从 C 的左边缘出发，连到 A 的右边缘 —— 两端确实贴在 from/to 上
        self.assertAlmostEqual(c_node.x, pts[0][0], delta=1.0)
        self.assertAlmostEqual(a_node.x + a_node.width, pts[-1][0], delta=1.0)
        self.assertGreater(pts[0][0], pts[-1][0], "回边应当从右往左走")


class TestDuplicateEdges(unittest.TestCase):
    def test_duplicate_edges_stay_separate(self):
        """同一对节点之间两条边：origin 用 (from,to) 对会让它们并成一条。"""
        s = spec_of("ABC", [("A", "B"), ("A", "B")])
        r = L.layout(s, boxes_for("ABC"))
        self.assertEqual(2, len(r.edges))


class TestPins(unittest.TestCase):
    def test_cross_axis_pin_moves_node_to_extreme(self):
        """LR 下 pin: top → 该层排最前。"""
        s = spec_of("ABC", [("A", "B"), ("A", "C")])
        s["nodes"][2]["pin"] = "top"          # C 排到 B 前面
        r = L.layout(s, boxes_for("ABC"))
        self.assertEqual(["C", "B"], r.order[1])

    def test_main_axis_pin_sets_rank(self):
        """LR 下 pin: right → 强制最大 rank。"""
        s = spec_of("ABC", [("A", "B"), ("B", "C")])
        s["nodes"][0]["pin"] = "right"        # A 想排到最右，但它有后继 B
        r = L.layout(s, boxes_for("ABC"))
        self.assertTrue(r.pin_conflicts, "与结构冲突的 pin 该被记录")
        self.assertLess(r.ranks["A"], r.ranks["B"], "退回后仍须满足边约束")

    def test_crossings_recounted_after_pin(self):
        """pin 会改层内顺序，交叉数必须在 pin 之后重算。"""
        ids = ["A1", "A2", "B1", "B2"]
        s = spec_of(ids, [("A1", "B2"), ("A2", "B1")])
        s["nodes"][3]["pin"] = "bottom"       # 把 B2 钉到后面，交叉又回来了
        r = L.layout(s, boxes_for(ids))
        self.assertEqual(L.count_crossings(r.order, _segments_of(r, s)),
                         r.crossings, "报告的交叉数与实际层内顺序对不上")


def _segments_of(result, spec) -> list[dict]:
    """按 spec 复原边段（含虚节点），供“报告的交叉数与实际顺序一致”这类断言用。

    依赖前提：该 spec 里的 pin 不改变 rank（只改层内顺序）。改 rank 的 pin 会
    让这里的复算与 layout() 内部不一致 —— 那种情况在 `TestPins` 里单独测。
    """
    node_ids = [n["id"] for n in spec["nodes"]]
    dag, _ = L.break_cycles(node_ids, spec["edges"])
    explicit = {n["id"]: n["rank"] for n in spec["nodes"] if n.get("rank") is not None}
    ranks = L.assign_ranks(node_ids, dag, explicit)
    _, segments, _, _ = L.insert_dummies(ranks, dag)
    return segments


class TestOrdering(unittest.TestCase):
    IDS = ("A1", "A2", "B1", "B2")   # 元组：类属性用可变对象会被多个用例共享

    def test_barycenter_removes_a_crossing(self):
        """种子顺序差时，barycenter 该把交叉降到 0。"""
        s = spec_of(self.IDS, [("A1", "B2"), ("A2", "B1")])
        r = L.layout(s, boxes_for(self.IDS))
        self.assertEqual(0, r.crossings)

    def test_more_rounds_never_make_it_worse(self):
        """保留最优的意义：barycenter 不是单调改进的启发式。"""
        s = spec_of(self.IDS, [("A1", "B2"), ("A2", "B1")])
        boxes = boxes_for(self.IDS)
        counts = [L.layout(s, boxes, {"barycenterRounds": n}).crossings
                  for n in (0, 1, 2, 4, 12)]
        self.assertLessEqual(counts[1], counts[0], "多跑一轮反而更差了")
        for a, b in zip(counts[1:], counts[2:]):
            self.assertLessEqual(b, a, "轮数增加后结果变差 —— 最优排列被丢掉了")


class TestCoordinates(unittest.TestCase):
    def test_same_rank_nodes_never_touch(self):
        """同层节点之间**任何时候**都不许小于 NODE_CLEARANCE。

        以前这条断的是「间隙正好等于 nodeSeparation」。现在不能再这么断了：主轴拉直
        （`_align_spine`）会把主线的节点对齐到父节点正下方，挡路的分支被往外推一次 ——
        于是分支与主线之间的间隙会比默认值小。`nodeSeparation` 是**默认间距**，
        不是下限；下限是 NODE_CLEARANCE，那才是「挨住了」的判据
        （`check_layout` 的 gap 检查用的也是它）。
        """
        s = spec_of("ABC", [("A", "B"), ("A", "C")])
        r = L.layout(s, boxes_for("ABC"))
        b, c = r.placed["B"], r.placed["C"]
        gap = abs(b.y - c.y) - b.height
        self.assertGreaterEqual(gap, L.NODE_CLEARANCE - 0.01,
                                "同层节点贴到一起了")

    def test_spine_alignment_keeps_branches_clear(self):
        """拉直之后，被推开的分支仍然不许和主线贴住。"""
        s = spec_of("ABCD", [("A", "B"), ("B", "C"), ("A", "D")])
        r = L.layout(s, boxes_for("ABCD"))
        row = [p for p in r.real_nodes().values() if p.rank == r.placed["C"].rank]
        for i, a in enumerate(row):
            for b in row[i + 1:]:
                gap = abs((a.y + a.height / 2) - (b.y + b.height / 2)) - a.height / 2 - b.height / 2
                self.assertGreaterEqual(gap, L.NODE_CLEARANCE - 0.01)

    def test_main_axis_advances_by_rank_separation(self):
        s = spec_of("AB", [("A", "B")])
        r = L.layout(s, boxes_for("AB"))
        gap = r.placed["B"].x - (r.placed["A"].x + r.placed["A"].width)
        self.assertAlmostEqual(L.DEFAULT_PARAMS["rankSeparation"], gap, delta=1.0)

    def test_nodes_in_one_rank_never_overlap(self):
        s = spec_of("ABCD", [("A", "B"), ("A", "C"), ("A", "D")])
        r = L.layout(s, boxes_for("ABCD"))
        layer = sorted(r.order[1])
        ys = [(r.placed[n].y, r.placed[n].height) for n in layer]
        for i in range(len(ys) - 1):
            self.assertGreaterEqual(ys[i + 1][0], ys[i][0] + ys[i][1], "同层节点重叠了")


class TestBoxesFromSpec(unittest.TestCase):
    def test_boxes_carry_both_shape_and_text(self):
        """盒子现在是「形状包围盒 + 里面的文字」两样 —— 尺寸仍由文字反推，不由模型给。"""
        tm = L.load_sibling("text_metrics")
        s = {"nodes": [{"id": "a", "kind": "service", "label": "订单服务",
                        "detail": "3 副本"}]}
        box = L.boxes_from_spec(s)["a"]
        want = tm.measure("订单服务", "3 副本")
        self.assertAlmostEqual(want.width, box.text.width, places=6)
        self.assertAlmostEqual(want.height, box.text.height, places=6)
        self.assertEqual("round", box.shape)
        self.assertGreaterEqual(box.width, want.width)
        self.assertGreaterEqual(box.height, want.height)


class TestCli(unittest.TestCase):
    def test_explain_runs(self):
        import json
        import tempfile
        s = spec_of("AB", [("A", "B")])
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                         encoding="utf-8") as fh:
            json.dump(s, fh)
            path = fh.name
        try:
            proc = subprocess.run([sys.executable, LAYOUT, path, "--explain"],
                                  capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertIn("交叉数", proc.stdout)
        finally:
            os.unlink(path)

    def test_bad_json_exits_2(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            fh.write("{not json")
            path = fh.name
        try:
            proc = subprocess.run([sys.executable, LAYOUT, path],
                                  capture_output=True, text=True)
            self.assertEqual(2, proc.returncode)
        finally:
            os.unlink(path)


class TestAvoidNodes(unittest.TestCase):
    """连线不许穿过别的节点（P2 / P10）。

    这一层的输入是**已经算好的折线**，它只负责把挡路的段推开。
    """

    @staticmethod
    def _placed(nid, x, y, w, h):
        return L.Placed(id=nid, x=x, y=y, width=w, height=h, rank=0)

    def test_clear_line_is_left_exactly_alone(self):
        """没有障碍时**一个点都不该动** —— 否则每次布局都会莫名漂移。"""
        placed = {"a": self._placed("a", 0, 0, 40, 40),
                  "b": self._placed("b", 400, 0, 40, 40),
                  "far": self._placed("far", 0, 500, 40, 40)}
        pts = [[40.0, 20.0], [400.0, 20.0]]
        self.assertEqual(pts, L.avoid_nodes(pts, placed, {"a", "b"}))

    def test_line_through_a_box_is_pushed_out(self):
        placed = {"a": self._placed("a", 0, 0, 40, 40),
                  "b": self._placed("b", 400, 0, 40, 40),
                  "wall": self._placed("wall", 180, -40, 80, 120)}
        pts = [[40.0, 20.0], [400.0, 20.0]]
        pushed = L.avoid_nodes(pts, placed, {"a", "b"})
        self.assertEqual([], L.nodes_hit_by_polyline(pushed, placed, {"a", "b"}),
                         "推完还是穿过节点")

    def test_endpoints_are_never_moved(self):
        """两端必须原样 —— 它们连着箭头绑定，动了就对不上了。"""
        placed = {"a": self._placed("a", 0, 0, 40, 40),
                  "b": self._placed("b", 400, 0, 40, 40),
                  "wall": self._placed("wall", 180, -40, 80, 120)}
        pts = [[40.0, 20.0], [400.0, 20.0]]
        pushed = L.avoid_nodes(pts, placed, {"a", "b"})
        self.assertEqual(pts[0], pushed[0])
        self.assertEqual(pts[-1], pushed[-1])

    def test_own_endpoints_do_not_count_as_obstacles(self):
        """自己的两端本来就被线贴着一排点，不能当成障碍，否则永远推不完。"""
        placed = {"a": self._placed("a", 0, 0, 200, 200),
                  "b": self._placed("b", 400, 0, 200, 200)}
        pts = [[200.0, 100.0], [400.0, 100.0]]
        self.assertEqual([], L.nodes_hit_by_polyline(pts, placed, {"a", "b"}))

    def test_dummy_nodes_are_not_obstacles(self):
        """虚节点只是路径上的拐点，不是看得见的东西。"""
        placed = {"a": self._placed("a", 0, 0, 40, 40),
                  "b": self._placed("b", 400, 0, 40, 40),
                  f"{L.DUMMY_PREFIX}0": self._placed(f"{L.DUMMY_PREFIX}0", 180, 0, 0, 0)}
        pts = [[40.0, 20.0], [200.0, 20.0], [400.0, 20.0]]
        self.assertEqual([], L.nodes_hit_by_polyline(pts, placed, {"a", "b"}))

    def test_giving_up_is_bounded(self):
        """推不出去时要**原样返回**，不能无限加拐点。"""
        # 一整排节点横在中间，且上下都堵死
        placed = {"a": self._placed("a", 0, 0, 40, 40),
                  "b": self._placed("b", 400, 0, 40, 40)}
        for i, y in enumerate(range(-400, 401, 40)):
            placed[f"w{i}"] = self._placed(f"w{i}", 180, y, 120, 40)
        pts = [[40.0, 20.0], [400.0, 20.0]]
        pushed = L.avoid_nodes(pts, placed, {"a", "b"})
        self.assertLessEqual(len(pushed), len(pts) + 2 * L.DETOUR_ROUNDS,
                             "拐点数量要有上限")
        self.assertEqual(pts[0], pushed[0])
        self.assertEqual(pts[-1], pushed[-1])


class TestOrthogonalRouting(unittest.TestCase):
    """连线的形状：不许斜、不许重合（P15 / P16）。

    两个用例都对应真实使用里报回来的问题 —— 用户的两句话就是用例名字：
    「不能像我一样，直接直直的下来吗」与「线与线又重合了」。
    """

    # 五层架构 + 三条长边：这份规格在修之前会把 `app→parse` 画成一条
    # **1475px 的对角线**（正交候选里有一小段 3px，而排序键当年把毛刺排在斜段前面）。
    ARCH = {
        "type": "architecture", "direction": "LR",
        "nodes": [{"id": n, "kind": k, "label": lb} for n, k, lb in (
            ("http", "client", "HTTP 层"), ("app", "service", "Application 用例层"),
            ("kernel", "plain", "kernel/contracts"), ("cap", "service", "Capability 层"),
            ("prov", "service", "Provider 层"), ("infra", "data", "Infrastructure"),
            ("ir", "data", "IR (materialized)"), ("parse", "data", "ParsePlan (expected)"),
            ("wfs", "data", "WorkflowStore (execution)"))],
        "edges": [{"from": a, "to": b} for a, b in (
            ("http", "app"), ("app", "kernel"), ("kernel", "cap"), ("cap", "prov"),
            ("prov", "infra"), ("infra", "ir"), ("infra", "parse"), ("infra", "wfs"),
            ("app", "wfs"), ("app", "ir"), ("app", "parse"), ("app", "infra"),
            ("kernel", "wfs"))],
    }

    @staticmethod
    def _slant(pts) -> float:
        return sum(math.dist(a, b) for a, b in zip(pts, pts[1:])
                   if abs(b[0] - a[0]) > 0.5 and abs(b[1] - a[1]) > 0.5)

    @staticmethod
    def _overlap(result) -> list:
        """共线且区间重叠的段对（与 `check_layout.check_edge_overlap` 同一件事）。"""
        segs = []
        for e in result.edges:
            name = f"{e['from']}→{e['to']}"
            for a, b in zip(e["points"], e["points"][1:]):
                if abs(a[0] - b[0]) <= 0.5:
                    segs.append((0, a[0], min(a[1], b[1]), max(a[1], b[1]), name))
                elif abs(a[1] - b[1]) <= 0.5:
                    segs.append((1, a[1], min(a[0], b[0]), max(a[0], b[0]), name))
        out = []
        for i, first in enumerate(segs):
            for second in segs[i + 1:]:
                if first[0] != second[0] or first[4] == second[4]:
                    continue
                if abs(first[1] - second[1]) > 0.75:
                    continue
                if min(first[3], second[3]) - max(first[2], second[2]) > L.EDGE_OVERLAP_MIN:
                    out.append((first[4], second[4]))
        return out

    def test_ports_align_when_they_almost_line_up(self):
        """两个**宽度不同**的节点之间的两条边：两端贴点各按自己的跨度摊开，
        差不到 24px 时就成了一根歪线 —— 现在必须并到同一列上。

        尺寸直接给定，不靠标签长短去凑（`box()` 是测试用的固定尺寸）：
        源 300 / 目标 270 → 跨度差 30×0.72 = **21.6px < EDGE_MIN**。
        """
        spec = {"type": "flow", "direction": "TB",
                "nodes": [{"id": "src", "kind": "service", "label": "src"},
                          {"id": "dst", "kind": "data", "label": "dst"}],
                "edges": [{"from": "src", "to": "dst"},
                          {"from": "src", "to": "dst"}]}
        for name, sizes in (("差一点点", (300.0, 270.0)),
                            ("差得远", (300.0, 120.0))):
            with self.subTest(name):
                result = L.layout(spec, {"src": box(sizes[0]), "dst": box(sizes[1])})
                offsets = []
                for edge in result.edges:
                    pts = edge["points"]
                    self.assertEqual(0.0, self._slant(pts), f"画歪了：{pts}")
                    offsets.append(round(pts[0][0] - pts[-1][0], 2))
                if name == "差一点点":
                    self.assertEqual([0.0, 0.0], offsets,
                                     "只差 21.6px 却不同列 —— 该直着下来的没直")
                else:
                    self.assertTrue(all(abs(d) >= L.EDGE_MIN for d in offsets),
                                    f"差得远时应当是正常的 Z 形折线，不该硬对齐：{offsets}")

    def test_short_leg_is_closed_not_deleted(self):
        """3px 的拐弯段要**就地并掉**（平移走线），不是删拐点 ——
        删掉一个拐点只会把正交路径拉成一条斜线。"""
        pts = [[0.0, 0.0], [100.0, 0.0], [100.0, 3.0], [300.0, 3.0], [300.0, 100.0]]
        out = L._simplify_path(pts)
        self.assertFalse(L._is_slanted(out), f"并毛刺之后反而出现了斜段：{out}")
        for first, second in zip(out, out[1:]):
            self.assertGreaterEqual(math.dist(first, second), L.EDGE_MIN - 0.01,
                                    f"还有过短的段：{out}")

    def test_snap_ports_moves_the_arrival_not_the_departure(self):
        """`_snap_ports` 的直接契约：只把**到达点**并到离开点那一列上。

        离开端连着上一段（已经在图上定好了），动它会连带把上游的线拉偏；
        到达端只是贴点，动它不欠任何人的。
        """
        placed = {"src": L.Placed("src", 0.0, 0.0, 300.0, 60.0, 0),
                  "dst": L.Placed("dst", 0.0, 200.0, 270.0, 60.0, 1)}
        near = [[136.0, 60.0], [141.4, 200.0]]
        out = L._snap_ports(near, ["src", "dst"], placed, "TB")
        self.assertEqual(near[0], out[0], "离开端不该动")
        self.assertAlmostEqual(out[0][0], out[-1][0], delta=0.01)
        # 差得远（>= EDGE_MIN）时是**正常的折线**，一律不动
        far = [[136.0, 60.0], [200.0, 200.0]]
        self.assertEqual(far, L._snap_ports(far, ["src", "dst"], placed, "TB"))

    def test_rank_key_prefers_orthogonal_over_slant(self):
        """排序键：**斜段排在毛刺前面** —— 这一点曾经写反。

        写反的代价是一条 1475px 的对角线（见 `test_orthogonal_route_beats_a_slanted_chord`）。
        `_close_short_legs` 现在会把大多数毛刺就地并掉，但并不掉的仍然会走到排序键这一步；
        那时宁可让校验报一条「连线过短」（可调项，看得见），也不能把整条线画成斜线。
        """
        orthogonal_with_burr = [[0.0, 0.0], [60.0, 0.0], [60.0, 5.0], [200.0, 5.0]]
        slanted_chord = [[0.0, 0.0], [200.0, 5.0]]
        self.assertLess(L._path_rank(orthogonal_with_burr, 1),
                        L._path_rank(slanted_chord, 2),
                        "含毛刺的正交路径输给了斜弦 —— 排序键又被写反了")

    def test_orthogonal_route_beats_a_slanted_chord(self):
        """一份五层架构 + 三条长边：以前它们会变成横穿全图的斜线（实测 1475px）。

        断言的是**整张图一点斜段都没有**，而不是“某一条边看起来还行” ——
        这个病的形态就是“正交候选明明可用，却因为一小段毛刺被整条换掉”。
        """
        result = L.layout(self.ARCH, L.boxes_from_spec(self.ARCH))
        worst = max(self._slant(e["points"]) for e in result.edges)
        self.assertEqual(0.0, worst, "还有斜段 —— 排序键又把正交路径让给斜弦了")
        for edge in result.edges:
            self.assertEqual([], L.nodes_hit_by_polyline(
                edge["points"], result.placed, {edge["from"], edge["to"]}))

    def test_no_two_edges_share_a_lane(self):
        """同一个空档里的段必须错开（01-architecture 里重合 225px 的那个 bug）。

        用**小图**复现：一个扇出 4 的节点 → 下一层四个节点，四条边出在同一层。
        """
        spec = spec_of("order user stock pay cache".split(),
                       [("order", t) for t in ("user", "stock", "pay", "cache")])
        result = L.layout(spec, L.boxes_from_spec(spec))
        self.assertEqual([], self._overlap(result), "有两条边画在了同一条线上")

    def test_overlap_report_matches_the_geometry(self):
        """校验侧与生成侧必须对同一份几何给出一致结论。

        两边不一致时，“生成侧说错开了”与“校验侧说重合了”会同时成立 ——
        那正是这一轮要修的毛病（报告全绿，图上却是一根线）。
        """
        CL = _load("check_layout_for_overlap", os.path.join(SCRIPTS, "check_layout.py"))
        spec = spec_of("order user stock pay cache".split(),
                       [("order", t) for t in ("user", "stock", "pay", "cache")])
        boxes = L.boxes_from_spec(spec)
        result, _, _ = CL.layout_with_retry(spec, boxes)
        issued = CL.check_edge_overlap(result)
        self.assertEqual([], issued,
                         f"校验报了重合，图上却查不出来：{[i.where for i in issued]}")
        self.assertEqual([], self._overlap(result))


if __name__ == "__main__":
    unittest.main(verbosity=2)

class TestWrapLongChains(unittest.TestCase):
    """折段（P7）：主轴太长的链式图折成几段并排。

    这些用例存在的理由：折段的**每一个条件**都是被现实打回来之后才加上的，
    而原来那两个坐标用例是"因为测试图太小不再折了"才通过的 —— 等于没有覆盖。
    """

    def _spec(self, count: int, direction: str, width: int = 1) -> dict:
        nodes = [{"id": f"n{i}", "kind": "service", "label": f"步骤{i}"} for i in range(count)]
        edges = [{"from": f"n{i}", "to": f"n{i+1}"} for i in range(count - 1)]
        for i in range(count - 1):
            for w in range(1, width):
                nodes.append({"id": f"n{i}x{w}", "kind": "external", "label": f"旁支{i}{w}"})
                edges.append({"from": f"n{i}", "to": f"n{i}x{w}"})
        return {"type": "flow", "direction": direction, "nodes": nodes, "edges": edges}

    def _main_extent(self, spec: dict) -> float:
        result = L.layout(spec, L.boxes_from_spec(spec))
        placed = result.placed
        if result.direction == "TB":
            return max(p.y + p.height for p in placed.values()) - min(p.y for p in placed.values())
        return max(p.x + p.width for p in placed.values()) - min(p.x for p in placed.values())

    def test_long_vertical_chain_gets_folded(self):
        """真的长 + 链式 + 竖着 → 折，而且**主轴必须变短**。

        只断言"比例变好"是不够的：第一版只加了宽度、没有重置主轴，比例数字同样变好看，
        但图反而更大（斜着错开的楼梯）。所以这里断言的是绝对长度。
        """
        spec = self._spec(14, "TB")
        # 判据层：这样的图该折
        self.assertGreater(L.segments_needed(2400.0, 200.0, 1, "TB"), 1)
        # 结果层：折完主轴**真的短了**。注意不能只断言比例 —— 第一版只加宽不缩高，
        # 比例数字一样好看，但图反而更大（斜着错开的楼梯）。
        self.assertLess(self._main_extent(spec), 1600,
                        "折完之后主轴应该短到一屏以内，而不是只是变宽")

    def test_short_chain_is_left_alone(self):
        """三个节点排一行也是 13:1，但那是一张小图 —— 不折。"""
        self.assertEqual(L.segments_needed(600.0, 44.0, 1, "TB"), 1)

    def test_dense_diagram_is_left_alone(self):
        """密集图本来就不是长条，折它只会把段间连线拉长（实测穿节点 1 → 4）。"""
        self.assertEqual(L.segments_needed(3000.0, 400.0, 6, "TB"), 1)

    def test_long_horizontal_chain_is_left_alone(self):
        """横向的长流程不折（阈值更高）—— 见 WRAP_MIN_MAIN 上的说明。"""
        self.assertEqual(L.segments_needed(2090.0, 172.0, 2, "LR"), 1)
        # 但真长到两屏以上还是要折
        self.assertGreater(L.segments_needed(5000.0, 172.0, 2, "LR"), 1)

    def test_cross_segment_edge_does_not_cross_nodes(self):
        """跨段那条连线要走空档，不能斜穿两栏（实测斜穿撞掉 2 个节点）。"""
        spec = self._spec(14, "TB")
        result = L.layout(spec, L.boxes_from_spec(spec))
        self.assertTrue(any(len(e["points"]) > 2 for e in result.edges),
                        "折段之后应该有一条绕行的跨段连线")
        for e in result.edges:
            hits = L.nodes_hit_by_polyline(e["points"], result.placed,
                                           {e["from"], e["to"]})
            self.assertEqual(hits, [], f"{e['from']} → {e['to']} 穿过了 {hits}")


class TestFastRejectChangesNothing(unittest.TestCase):
    """加速用的**精确否定**必须不改变结果。

    `_segment_hits_box` 前面加了一步 slab 法排除（一条 900px 的弦原本要采 452 个点）。
    它唯一的正确性依据是这条不变量：**线段与矩形不相交 ⇒ 线段上任何采样点都不在矩形内**。
    不成立的话，绕行、校验、fixture 基线会一起漂 —— 而且是"同一件几何给出两个答案"
    那种最难查的漂法。

    所以这里拿一个**采样版参照实现**逐例比对：随机撒 2000 组线段/盒子（含 pad），
    断言加速版与参照版**逐例相同**。参照实现故意写在测试里、不放进 layout ——
    它代表的是"改动前的行为"，不是第二个权威口径。
    """

    @staticmethod
    def _sampling_only(a, b, box, pad):
        left, top = box.x - pad, box.y - pad
        right, bottom = box.x + box.width + pad, box.y + box.height + pad
        return any(left <= x <= right and top <= y <= bottom
                   for x, y in L._sample_points(a, b))

    def test_same_answer_as_sampling_only(self):
        rng = random.Random(20260101)      # 固定种子：失败可复现
        rejected = 0
        for index in range(2000):
            box = L.Placed(id="box", x=rng.uniform(-200, 200),
                           y=rng.uniform(-200, 200), width=rng.uniform(10, 200),
                           height=rng.uniform(10, 120), rank=0)
            a = [rng.uniform(-320, 320), rng.uniform(-320, 320)]
            b = [rng.uniform(-320, 320), rng.uniform(-320, 320)]
            pad = rng.choice([0.0, 12.0])
            if not L._segment_may_hit_box(a, b, box, pad):
                rejected += 1
            with self.subTest(case=index, pad=pad):
                self.assertEqual(self._sampling_only(a, b, box, pad),
                                 L._segment_hits_box(a, b, box, pad))
        # 反向保险：一条都没否掉的话，上面那条用例就成了空话（加速也没发生）
        self.assertGreater(rejected, 100, f"只否掉了 {rejected} 例，加速没起作用")

    def test_reject_is_exact_not_approximate(self):
        """两个方向各钉一个确定答案 —— 免得用例只在随机例子上自洽。"""
        box = L.Placed(id="box", x=0, y=0, width=50, height=50, rank=0)
        self.assertFalse(L._segment_may_hit_box([200, 200], [300, 300], box))
        self.assertFalse(L._segment_may_hit_box([60, 25], [90, 25], box))
        self.assertTrue(L._segment_may_hit_box([-10, 25], [60, 25], box))
        self.assertTrue(L._segment_may_hit_box([25, -5], [25, 55], box))
        # 贴着盒子外沿擦过：不相交，但也不许误判成交叉
        self.assertFalse(L._segment_may_hit_box([-50, 50.001], [100, 50.001], box))


def _network_spec() -> dict:
    """一张最小的网状图：5 个节点绕成一圈（没有天然层级）。"""
    return {
        "type": "network",
        "nodes": [{"id": f"n{i}", "label": f"服务{i}", "kind": "service"}
                  for i in range(5)],
        "edges": [{"from": "n0", "to": "n1"}, {"from": "n1", "to": "n2"},
                  {"from": "n2", "to": "n3"}, {"from": "n3", "to": "n4"},
                  {"from": "n4", "to": "n0"}, {"from": "n0", "to": "n3"}],
    }


def _coords(placed: dict) -> list[tuple]:
    return sorted((n, round(p.x, 3), round(p.y, 3)) for n, p in placed.items())


def _spread(placed: dict) -> float:
    xs = [p.x for p in placed.values()]
    ys = [p.y for p in placed.values()]
    return (max(xs) - min(xs)) * (max(ys) - min(ys))


class TestForceLayout(unittest.TestCase):
    """力导向（网状图）的几条硬性质。"""

    def _run(self, params=None):
        spec = _network_spec()
        boxes = L.boxes_from_spec(spec)
        nids = [n["id"] for n in spec["nodes"]]
        return L.force_layout(nids, boxes, spec["edges"],
                              dict(L.DEFAULT_PARAMS, **(params or {})))

    def test_same_spec_gives_the_same_picture(self):
        """**确定性**：同一份规格永远出同一张图。

        力导向最容易在这件事上翻车（随机初始位置、多次重启取最优）—— 那样"改一个
        标签"就会让整张图重排，用户没法对着图讨论、diff 也失去意义。所以初始位置用
        确定的圆、不做重启。这条用例跑两遍逐坐标比。
        """
        first = self._run()[0]
        second = self._run()[0]
        self.assertEqual(_coords(first), _coords(second))
        self.assertTrue(first, "没摆出任何节点，用例是空话")

    def test_no_two_boxes_overlap(self):
        """力学收敛**不保证**没有重叠 —— 收尾那步"量出来再推开"必须真的生效。"""
        placed = self._run()[0]
        worst = None
        ids = sorted(placed)
        for i, first in enumerate(ids):
            for second in ids[i + 1:]:
                gap = L.aabb_gap(placed[first], placed[second])
                if worst is None or gap < worst:
                    worst = gap
        self.assertIsNotNone(worst)
        self.assertGreaterEqual(worst, L.NODE_CLEARANCE,
                                f"最窄的一对只隔了 {worst:.1f}px")

    def test_the_two_knobs_actually_reach_the_drawing(self):
        """`rankSeparation` / `nodeSeparation` 必须真的连着画面。

        它们是给调参器用的，而调参器只会**加大**间距（单向）。旋钮没接上的话那几轮
        调参就是空转 —— 前作正是"有旋钮没人拧"，最后靠人手挪坐标。所以这里不只是
        "参数变了"，还要断言**变化的方向对**：加大间距必须把图撑开。
        """
        base = self._run()[0]
        wider = self._run({"rankSeparation": 600.0})[0]
        self.assertNotEqual(_coords(base), _coords(wider), "改参数没影响画面：旋钮没接上")
        self.assertGreater(_spread(wider), _spread(base),
                           "加大理想间距反而更挤 —— 力的方向反了")

        roomier = self._run({"nodeSeparation": 260.0})[0]
        self.assertGreater(_spread(roomier), _spread(base),
                           "加大最小间隙没有把节点推开")


class TestRegions(unittest.TestCase):
    """`groups` → 区域（圆角矩形 + 顶部标题）。以前这个字段**一处都不被读**。"""

    def spec(self, **over):
        base = {
            "type": "flow", "direction": "TB", "title": "T",
            "groups": [{"id": "g1", "label": "第一区", "level": "tint"}],
            "nodes": [
                {"id": "a", "label": "A", "kind": "plain", "group": "g1"},
                {"id": "b", "label": "B", "kind": "plain", "group": "g1"},
                {"id": "c", "label": "C", "kind": "plain"},
            ],
            "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}],
        }
        base.update(over)
        return base

    def box_of(self, spec):
        boxes = L.boxes_from_spec(spec)
        return L.region_boxes(spec, L.layout(spec, boxes).placed, boxes)

    def test_region_is_offered_to_the_renderer(self):
        """区域必须真的算得出来 —— 声明了没效果正是这个字段以前的毛病。"""
        regions = self.box_of(self.spec())
        self.assertEqual(["g1"], [g["id"] for g in regions])
        self.assertEqual("第一区", regions[0]["label"])

    def test_region_encloses_every_member(self):
        """区域框一定框得住它的每个成员：少了哪一个都是画错。"""
        spec = self.spec()
        boxes = L.boxes_from_spec(spec)
        placed = L.layout(spec, boxes).placed
        for region in L.region_boxes(spec, placed, boxes):
            for nid, node in placed.items():
                if nid == "c":
                    continue                      # 不在这一区里
                self.assertLessEqual(region["x"], node.x)
                self.assertLessEqual(region["y"], node.y)
                self.assertGreaterEqual(region["x"] + region["width"],
                                        node.x + node.width)
                self.assertGreaterEqual(region["y"] + region["height"],
                                        node.y + node.height)

    def test_title_band_is_above_the_members(self):
        """标题带留在成员上方 —— 这样标题在结构上不可能压到节点。"""
        spec = self.spec()
        boxes = L.boxes_from_spec(spec)
        placed = L.layout(spec, boxes).placed
        region = L.region_boxes(spec, placed, boxes)[0]
        top_of_members = min(placed[n].y for n in ("a", "b"))
        self.assertLess(region["label_y"] + L.REGION_HEAD, top_of_members)

    # ── 区域标题不许溢出（P17）───────────────────────────────
    # 用户拿截图来问「这种块的 title 会溢出」：一个 368px 的标题画在 324px 的
    # 可用宽度里，两头各冒出去 22px，而当时**没有任何检查在量区域标题**。

    def test_region_head_matches_the_single_line_band(self):
        """单行标题时的标题带高度 = 上边距 + 一行字 + 间隙。

        `REGION_HEAD` 是个字面量（它定义在 `load_sibling` 之前，拿不到行高），
        所以这里把那个恒等式钉死 —— 两处各写一个数迟早会漂。
        """
        tm = _load("tm_for_region_test", os.path.join(SCRIPTS, "text_metrics.py"))
        self.assertAlmostEqual(
            L.REGION_HEAD,
            L.REGION_LABEL_TOP + L.REGION_LABEL_SIZE * tm.LINE_HEIGHT + L.REGION_LABEL_GAP,
            places=2, msg="REGION_HEAD 与单行标题带的公式对不上了")

    def test_region_title_wraps_to_the_region_width(self):
        """标题按**区域的宽度**断行：任何长度、任何宽度的区域都不许冒出去。

        这是构造性的：宽度 → 断行 → 行数 → 标题带高度，不反过来。
        """
        for label in ("三真源：完成 = 期望 × 执行 × 物化对齐",
                      "这一整块是给外部系统做协议适配的地方",
                      "short", "A",
                      "x" * 160):
            for node_label in ("A", "宽一点的节点标签", "very long node label here"):
                with self.subTest(label=label, node=node_label):
                    spec = self.spec(nodes=[
                        {"id": "a", "label": node_label, "kind": "service", "group": "g1"},
                        {"id": "b", "label": "B", "kind": "plain"}],
                        groups=[{"id": "g1", "label": label}],
                        edges=[{"from": "a", "to": "b"}])
                    region = self.box_of(spec)[0]
                    self.assertLessEqual(
                        region["label_width"],
                        region["width"] - 2 * L.REGION_LABEL_MARGIN + 0.01,
                        f"标题还是比区域宽：{region['label_width']} vs {region['width']}")

    def test_region_title_band_grows_with_the_lines(self):
        """断成两行时标题带跟着变高，而且**不许压到成员节点**。

        固定高度 + 多行文字 = 文字从标题带里溢出来盖住第一排节点 ——
        所以带高必须由断行结果算。
        """
        spec = self.spec(groups=[{"id": "g1", "label": "三真源：完成 = 期望 × 执行 × 物化对齐"}])
        boxes = L.boxes_from_spec(spec)
        placed = L.layout(spec, boxes).placed
        region = L.region_boxes(spec, placed, boxes)[0]
        self.assertGreater(len(region["label_lines"]), 1, "这份用例需要标题断成多行")
        self.assertGreater(region["height"], 0)
        self.assertAlmostEqual(
            region["label_height"],
            len(region["label_lines"]) * L.REGION_LABEL_SIZE
            * _load("tm_for_region_test", os.path.join(SCRIPTS, "text_metrics.py")).LINE_HEIGHT,
            places=2)
        top_of_members = min(placed[n].y for n in ("a", "b"))
        self.assertLessEqual(region["label_y"] + region["label_height"],
                             top_of_members - L.REGION_PAD + 0.01)

    def test_region_title_break_is_balanced_not_greedy(self):
        """行数定下来之后挑**最均衡**的一版：贪心会把最后一行剩一两个字。

        实测贪心给的是 `三真源：完成 = 期望 × 执行 × 物 / 化对齐`（把「物化对齐」
        从中间切开），收窄一档就能断在空格上：`三真源：完成 = 期望 / × 执行 × 物化对齐`。
        """
        label = "三真源：完成 = 期望 × 执行 × 物化对齐"
        lines, _width = L.region_label_lines(label, 340.0)
        self.assertEqual(2, len(lines))
        self.assertNotIn("化", lines[0][-1:], f"还是从中间切开了词：{lines}")
        shortest, longest = sorted(lines, key=len)
        self.assertGreaterEqual(len(shortest), 0.5 * len(longest), f"两行不均衡：{lines}")

    def test_region_title_check_stays_silent_on_a_good_figure(self):
        """好图不该多出噪声 —— 这条检查是断言，不是体检。"""
        CL = _load("check_layout_for_region_label",
                   os.path.join(SCRIPTS, "check_layout.py"))
        spec = self.spec(groups=[{"id": "g1", "label": "三真源：完成 = 期望 × 执行 × 物化对齐"}])
        boxes = L.boxes_from_spec(spec)
        result = L.layout(spec, boxes)
        self.assertEqual([], CL.check_region_labels(spec, result, boxes))


class TestSidestepCandidates(unittest.TestCase):
    """「逐个障碍让开」的候选**必须是干净的**（不含穿节点）。

    这条不变量是踩出来的：第一版只查了"剩下的那条直线"，于是让开中间几个障碍之后，
    尾部仍会撞上目标附近的节点 —— 候选自己带着 1 处穿节点，永远进不了 viable，
    而症状是"那条边宁可折 9 次也不走这条路"。现在改成**按整条路径查**，
    并且只把干净的候选交出去（脏的直接丢掉，不指望调用方再筛一遍）。
    """

    @staticmethod
    def _placed(node_id: str, x: float, y: float, w: float = 80.0, h: float = 50.0):
        return L.Placed(id=node_id, x=x, y=y, width=w, height=h, rank=0)

    def test_every_candidate_is_free_of_node_hits(self):
        # 两个障碍横在直线 a→b 上（a 在上、b 在下，竖向为主）
        placed = {"a": self._placed("a", 0, 0), "b": self._placed("b", 0, 600),
                  "x": self._placed("x", -30, 180), "y": self._placed("y", -30, 380)}
        steps = L._sidestep_candidates([40, 25], [40, 575], placed, {"a", "b"})
        self.assertTrue(steps, "挡了两个节点却一个候选都没给出")
        for path in steps:
            self.assertEqual([], L.nodes_hit_by_polyline(path, placed, {"a", "b"}),
                             f"交出来的候选自己还穿着节点：{path}")

    def test_clear_line_yields_no_candidate(self):
        """一个障碍都没有时不该伪造候选 —— 那是"为了绕而绕"。"""
        placed = {"a": self._placed("a", 0, 0), "b": self._placed("b", 0, 600)}
        self.assertEqual([], L._sidestep_candidates([40, 25], [40, 575], placed, {"a", "b"}))
