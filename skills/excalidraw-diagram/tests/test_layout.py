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
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
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
        """A(0)→D(3) 跨 3 层插 2 个虚节点；A(0)→E(4) 跨 4 层插 3 个；合计 5。"""
        self.assertEqual(5, self.r.dummy_count)
        self.assertEqual(4, len(self.edge("A", "D")["points"]))
        self.assertEqual(5, len(self.edge("A", "E")["points"]))

    def test_parallel_long_edges_do_not_share_a_chain(self):
        """同一节点出发的两条长边必须各走自己的链。"""
        ad, ae = self.edge("A", "D")["points"], self.edge("A", "E")["points"]
        self.assertNotEqual(ad[1], ae[1], "两条长边在虚节点处重叠 —— 它们串线了")
        self.assertLess(ad[1][0], ae[1][0] + 10_000)   # 都存在且不同层

    def test_dummies_are_apart_by_dummy_separation(self):
        """虚节点不能吃掉整个节点间距，但也不能重合（否则平行边看起来是一条）。"""
        ad, ae = self.edge("A", "D")["points"], self.edge("A", "E")["points"]
        self.assertAlmostEqual(L.DUMMY_SEPARATION, abs(ae[1][1] - ad[1][1]), delta=0.5)

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
    def test_same_rank_nodes_are_node_separation_apart(self):
        s = spec_of("ABC", [("A", "B"), ("A", "C")])
        r = L.layout(s, boxes_for("ABC"))
        b, c = r.placed["B"], r.placed["C"]
        gap = abs(b.y - c.y) - b.height
        self.assertAlmostEqual(L.DEFAULT_PARAMS["nodeSeparation"], gap, delta=1.0)

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
