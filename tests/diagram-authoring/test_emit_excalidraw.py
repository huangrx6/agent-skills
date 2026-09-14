#!/usr/bin/env python3
"""emit_excalidraw.py 的回归测试：规格 → `.excalidraw` 结构正确性。

## 这一层的失败方式与前几波不同

前几波算的是**数字**（交叉数、间隙、阈值），错了能看出来。这一层产出的是**结构**：
元素之间的引用关系。它的典型失败是"生成的 JSON 语法完全合法、但引用指错了" ——
比如 `boundElements` 指向一个不存在的 id、或者文字的 `containerId` 没指回容器。
这种错**不会让任何东西崩**，只会让图在编辑器里行为异常（拖动时文字不跟着走、
箭头断开绑定）。所以用例的重点是**引用完整性**，不是数值。

另一类是**保真**：出图上的文字必须和规格里写的 label 一致。
曾经的真实 bug：`text_metrics._tokens` 在全角字符前吃掉空格，
"Web 前端" 出了图变成 "Web前端" —— 而"脚本忠实地把结构画出来"正是这个 skill 的前提。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/test_emit_excalidraw.py
"""

from __future__ import annotations

import glob
import importlib.util
import json
import math
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
# 测试住在仓库顶层 `tests/<skill>/`（**刻意不在 skill 目录里**：AI 调用 skill 时读的是
# `skills/<skill>/` 那棵树，测试放在里面会被顺手读进去）。
# 所以从 `tests/<skill>/` 往上两级到仓库根，再进 `skills/<skill>/`。
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
SCRIPTS = os.path.join(SKILL, "scripts")
EMIT = os.path.join(SCRIPTS, "emit_excalidraw.py")

# Excalidraw 元素共有的字段（照 `_ExcalidrawElementBase`）
BASE_FIELDS = {
    "id", "type", "x", "y", "width", "height", "angle", "strokeColor",
    "backgroundColor", "fillStyle", "strokeWidth", "strokeStyle", "roughness",
    "opacity", "groupIds", "frameId", "roundness", "seed", "version",
    "versionNonce", "isDeleted", "boundElements", "updated", "link", "locked",
}


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


E = _load("emit_excalidraw", EMIT)
L = E.L
palette = E.palette
V = E._load_sibling("validate_spec")
# 量文字用的那一份（跟 E / L 同源）：区域标题的行宽得用它算。
tm = L._tm


def spec_of(ids, edges, **kw) -> dict:
    return {"type": kw.pop("type", "architecture"), "direction": kw.pop("direction", "LR"),
            "nodes": [{"id": n, "kind": kw.get("kind", "service"), "label": n} for n in ids],
            "edges": [{"from": a, "to": b} for a, b in edges]}


def build(spec: dict) -> dict:
    scene, result, outcome, attempts = E.emit(spec)
    assert scene, f"没出图：{[i.line() for i in outcome.blocking]}"
    return scene


def _point_segment_distance(point, first, second) -> float:
    """点到线段的距离 —— 边标签“离自己那条线多远”就靠它量。"""
    ax, ay = first
    bx, by = second
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.dist(point, first)
    t = max(0.0, min(1.0, ((point[0] - ax) * dx + (point[1] - ay) * dy) / (dx * dx + dy * dy)))
    return math.dist(point, (ax + t * dx, ay + t * dy))


class TestSceneEnvelope(unittest.TestCase):
    def setUp(self):
        self.scene = build(spec_of(["a", "b"], [("a", "b")]))

    def test_top_level_shape(self):
        self.assertEqual({"type", "version", "source", "elements", "appState", "files"},
                         set(self.scene))
        self.assertEqual("excalidraw", self.scene["type"])
        self.assertEqual(2, self.scene["version"])
        self.assertEqual({}, self.scene["files"])

    def test_app_state_uses_canvas_colour(self):
        self.assertEqual(palette.CANVAS["background"],
                         self.scene["appState"]["viewBackgroundColor"])

    def test_scene_is_json_serialisable(self):
        """不能有 NaN / Infinity —— 那不是合法 JSON，插件读不了。"""
        text = json.dumps(self.scene, ensure_ascii=False, allow_nan=False)
        self.assertEqual(self.scene, json.loads(text))


class TestElementBase(unittest.TestCase):
    def setUp(self):
        self.scene = build(spec_of(["a", "b", "c"], [("a", "b"), ("b", "c")]))

    def test_every_element_has_base_fields(self):
        for el in self.scene["elements"]:
            missing = BASE_FIELDS - set(el)
            self.assertEqual(set(), missing, f"{el['id']} 缺字段 {missing}")

    def test_ids_are_unique(self):
        ids = [e["id"] for e in self.scene["elements"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_ids_are_strings(self):
        for el in self.scene["elements"]:
            self.assertIsInstance(el["id"], str)
            self.assertTrue(el["id"])

    def test_colours_come_from_the_palette(self):
        allowed = set()
        for entry in list(palette.KINDS.values()) + list(palette.EDGE_KINDS.values()):
            # 颜色住在**层级**表 + **边型**表里；语义角色只指向层级，本身不带颜色。
            for level in palette.VISUAL_LEVELS:
                allowed.update(palette.LEVELS[level].values())
            for edge in palette.EDGE_KINDS.values():
                allowed.add(edge["stroke"])
        allowed.update(palette.CANVAS.values())
        allowed.add("transparent")
        for el in self.scene["elements"]:
            self.assertIn(el["strokeColor"], allowed, f"{el['id']} 描边色不在板内")
            self.assertIn(el["backgroundColor"], allowed, f"{el['id']} 填充色不在板内")

    def test_deterministic_seeds(self):
        """同一份规格两次生成必须字节相同 —— 否则图没法进 git。"""
        again = build(spec_of(["a", "b", "c"], [("a", "b"), ("b", "c")]))
        self.assertEqual(json.dumps(self.scene, sort_keys=True),
                         json.dumps(again, sort_keys=True))


class TestBindings(unittest.TestCase):
    """引用完整性 —— 这一层最典型的失败。"""

    def setUp(self):
        spec = {"type": "architecture", "direction": "LR",
                "nodes": [{"id": "web", "kind": "client", "label": "Web 前端"},
                          {"id": "api", "kind": "service", "label": "API",
                           "detail": "3 副本"}],
                "edges": [{"from": "web", "to": "api"}]}
        self.scene = build(spec)
        self.by_id = {e["id"]: e for e in self.scene["elements"]}

    def test_bound_elements_all_exist(self):
        for el in self.scene["elements"]:
            for bound in (el.get("boundElements") or []):
                self.assertIn(bound["id"], self.by_id,
                              f"{el['id']} 的 boundElements 指向不存在的 {bound['id']}")

    def test_container_id_points_back(self):
        """text 说它属于某个 container，那个 container 也必须把它列进 boundElements。"""
        for el in self.scene["elements"]:
            cid = el.get("containerId")
            if not cid:
                continue
            self.assertIn(cid, self.by_id)
            listed = [b["id"] for b in (self.by_id[cid].get("boundElements") or [])]
            self.assertIn(el["id"], listed, f"{el['id']} 的 container 没把它列回去")

    def test_arrows_bound_to_both_ends(self):
        arrows = [e for e in self.scene["elements"] if e["type"] == "arrow"]
        self.assertEqual(1, len(arrows))
        arrow = arrows[0]
        for key, node_id in (("startBinding", "web"), ("endBinding", "api")):
            self.assertEqual(E._eid("node", node_id), arrow[key]["elementId"])
            bound = [b["id"] for b in (self.by_id[E._eid("node", node_id)]
                                       ["boundElements"] or [])]
            self.assertIn(arrow["id"], bound, f"{key} 单向 —— 节点没登记这条箭头")

    def test_every_arrow_has_both_bindings(self):
        for el in self.scene["elements"]:
            if el["type"] == "arrow":
                self.assertTrue(el["startBinding"])
                self.assertTrue(el["endBinding"])

    def test_detail_produces_a_second_text(self):
        def texts_of(node_id: str) -> list[dict]:
            return [e for e in self.scene["elements"]
                    if e["type"] == "text"
                    and e.get("containerId") == E._eid("node", node_id)]

        self.assertEqual(2, len(texts_of("api")), "带 detail 的节点应该有两个文字块")
        self.assertEqual(1, len(texts_of("web")), "不带 detail 的节点只该有一个")


class TestArrowGeometry(unittest.TestCase):
    def test_points_are_relative_and_start_at_origin(self):
        """Excalidraw 的箭头：x/y 是绝对起点，points 相对它，首点必须是 [0,0]。"""
        scene = build(spec_of("ABCDE", [("A", "B"), ("B", "C"), ("C", "D"), ("D", "E"),
                                        ("A", "D"), ("A", "E")]))
        for el in scene["elements"]:
            if el["type"] != "arrow":
                continue
            self.assertEqual([0, 0], el["points"][0], f"{el['id']} 首点不是原点")
            for px, py in el["points"]:
                self.assertLessEqual(abs(px), el["width"] + 0.01)
                self.assertLessEqual(abs(py), el["height"] + 0.01)

    def test_multi_waypoint_arrow_keeps_its_waypoints(self):
        """跨层边**必须**保留拐点 —— 当首尾直线会穿过中间节点时。

        原版用的是 A→D / A→E 那组。实测它们的直线并不穿过任何节点，所以
        「能直就直」（`straighten`）之后被正常拉直了 —— 那正是要的效果，不是丢东西。
        这里换成一个真的绕不过去的形状：B 正好夹在 A 与 C 之间。
        """
        scene = build(spec_of("ABC", [("A", "B"), ("B", "C"), ("A", "C")],
                              direction="TB"))
        arrows = [e for e in scene["elements"] if e["type"] == "arrow"]
        self.assertEqual(3, len(arrows), "边丢了")
        self.assertTrue(any(len(a["points"]) > 2 for a in arrows),
                        "A→C 的直线明明是穿过 B 的，却被压直了")


class TestTextFidelity(unittest.TestCase):
    """出图上的文字必须和规格里写的一致。曾经在这里吃掉过空格。"""

    def _labels(self, spec):
        scene = build(spec)
        return {e["id"]: e["text"] for e in scene["elements"]
                if e["type"] == "text" and e.get("containerId")}

    def test_space_between_latin_and_cjk_survives(self):
        spec = {"type": "architecture", "direction": "LR",
                "nodes": [{"id": "a", "kind": "client", "label": "Web 前端"},
                          {"id": "b", "kind": "service", "label": "API 网关"}],
                "edges": [{"from": "a", "to": "b"}]}
        got = self._labels(spec)
        self.assertEqual("Web 前端", got[E._eid("title", "a")])
        self.assertEqual("API 网关", got[E._eid("title", "b")])

    def test_no_characters_are_dropped_by_wrapping(self):
        """断行可以插换行，但不许吞字符。"""
        label = "一个很长的中文节点标题需要断行处理并且不能丢字"
        spec = {"type": "architecture", "direction": "LR",
                "nodes": [{"id": "a", "kind": "service", "label": label},
                          {"id": "b", "kind": "data", "label": "DB"}],
                "edges": [{"from": "a", "to": "b"}]}
        got = self._labels(spec)
        emitted = got[E._eid("title", "a")].replace("\n", "")
        self.assertEqual(label, emitted)

    def test_text_elements_carry_required_text_fields(self):
        scene = build(spec_of(["a", "b"], [("a", "b")]))
        for el in scene["elements"]:
            if el["type"] != "text":
                continue
            for field_name in ("text", "fontSize", "fontFamily", "textAlign",
                               "verticalAlign", "containerId", "originalText",
                               "lineHeight", "baseline"):
                self.assertIn(field_name, el, f"{el['id']} 缺 {field_name}")


class TestTextGeometry(unittest.TestCase):
    def test_text_block_fits_inside_its_container(self):
        scene = build(spec_of(["a", "b", "c"], [("a", "b"), ("b", "c")]))
        by_id = {e["id"]: e for e in scene["elements"]}
        for el in scene["elements"]:
            if el["type"] != "text" or not el.get("containerId"):
                continue
            box = by_id[el["containerId"]]
            self.assertLessEqual(el["width"], box["width"] + 0.5, f"{el['id']} 横向溢出")
            self.assertLessEqual(el["height"], box["height"] + 0.5, f"{el['id']} 纵向溢出")

    def test_text_position_is_inside_its_container(self):
        scene = build(spec_of(["a", "b"], [("a", "b")]))
        by_id = {e["id"]: e for e in scene["elements"]}
        for el in scene["elements"]:
            if el["type"] != "text" or not el.get("containerId"):
                continue
            box = by_id[el["containerId"]]
            self.assertGreaterEqual(el["x"], box["x"] - 0.5)
            self.assertGreaterEqual(el["y"], box["y"] - 0.5)
            self.assertLessEqual(el["y"] + el["height"], box["y"] + box["height"] + 0.5)


class TestRefusesBadSpecs(unittest.TestCase):
    """规格不合法就不该出图 —— 出图是流水线最后一步。

    emit 现在**自己先跑一遍 validate_spec**（以前它不跑，靠调用方自觉；
    调用方忘了就会在半路崩，而且崩出来的错还是误导性的）。
    """

    def test_unknown_kind_raises_spec_error(self):
        spec = spec_of(["a", "b"], [("a", "b")], kind="queue")
        with self.assertRaises(E.SpecError) as ctx:
            E.emit(spec)
        message = str(ctx.exception)
        self.assertIn("queue", message, "报错要说清是哪个值不认识")
        self.assertIn("async", message, "还要列出允许的取值")

    def test_unknown_shape_raises_spec_error(self):
        spec = spec_of(["a", "b"], [("a", "b")])
        spec["nodes"][0]["shape"] = "star"
        with self.assertRaises(E.SpecError) as ctx:
            E.emit(spec)
        self.assertIn("star", str(ctx.exception))


class TestDiagramTitle(unittest.TestCase):
    """图标题。以前 `title` 字段被**完全忽略**（6/6 张 fixture 都写了，一张都没画出来）。"""

    @staticmethod
    def _titles(scene):
        return [e for e in scene["elements"]
                if e["type"] == "text" and e.get("containerId") is None
                and e["fontSize"] == E.tm.FONT_TITLE]

    def test_no_title_field_means_no_element(self):
        spec = spec_of(["a", "b"], [("a", "b")])
        scene, _, _, _ = E.emit(spec)
        self.assertEqual([], self._titles(scene))

    def test_title_exists_and_uses_the_title_font(self):
        spec = spec_of(["a", "b"], [("a", "b")])
        spec["title"] = "下单链路"
        scene, _, _, _ = E.emit(spec)
        titles = self._titles(scene)
        self.assertEqual(1, len(titles))
        self.assertEqual("下单链路", titles[0]["text"])
        self.assertEqual(E.tm.FONT_TITLE, titles[0]["fontSize"])
        self.assertEqual("center", titles[0]["textAlign"])

    def test_title_is_centred_on_the_content(self):
        spec = spec_of(["a", "b", "c"], [("a", "b"), ("b", "c")])
        spec["title"] = "居中检查"
        scene, _, _, _ = E.emit(spec)
        title = self._titles(scene)[0]
        others = [e for e in scene["elements"] if e is not title]
        left, top, right, bottom = E.scene_bounds(others)
        self.assertAlmostEqual((left + right) / 2.0,
                               title["x"] + title["width"] / 2.0, places=1,
                               msg="标题的中心要落在内容水平中心上")

    def test_title_sits_above_everything(self):
        spec = spec_of(["a", "b"], [("a", "b")])
        spec["title"] = "在上方"
        scene, _, _, _ = E.emit(spec)
        title = self._titles(scene)[0]
        content_top = min(e["y"] for e in scene["elements"] if e is not title)
        self.assertLessEqual(title["y"] + title["height"], content_top,
                             "标题压到内容上了")

    def test_title_width_is_the_real_line_width_not_the_size_class(self):
        """两字标题不能被撑成档位宽度。

        `text_metrics.measure` 返回的 `break_units` 是**容器的断行档位**（给形状用的）。
        标题不该用容器逻辑：按档位算，一个两字标题会占 10 个字宽（240px），白占画布。
        """
        spec = spec_of(["a", "b"], [("a", "b")])
        spec["title"] = "两头"
        scene, _, _, _ = E.emit(spec)
        title = self._titles(scene)[0]
        two_chars = 2 * E.tm.FONT_TITLE
        self.assertLess(title["width"], two_chars * 1.35,
                        f"两字标题占了 {title['width']:.0f}px —— 是不是用档位宽算了")
        self.assertGreaterEqual(title["width"], two_chars * 0.9)

    def test_long_title_wraps_into_one_element(self):
        """超长标题要断行，但**仍然只是一个元素**。

        断行档位是给容器用的（最大一档 24 个单位），标题沿用它 ——
        所以 22 个字的标题本来就不会断。这里用真正超长的来试。
        """
        spec = spec_of(["a", "b"], [("a", "b")])
        spec["title"] = "这是一个特别特别长的图标题它长到了必须断行的程度因为超过了最大断行档位"
        scene, _, _, _ = E.emit(spec)
        titles = self._titles(scene)
        self.assertEqual(1, len(titles), "断行也不该变成多个元素")
        self.assertIn("\n", titles[0]["text"])
        self.assertLess(titles[0]["width"], 28 * E.tm.FONT_TITLE,
                        "断了行就不该还占着没断时的宽度")


class TestEdgeLabels(unittest.TestCase):
    @staticmethod
    def _hits(label: dict, arrows: list[dict]) -> list:
        """沿箭头折线密集采样（每 0.5px 一点），返回落进标签框里的采样点。

        用采样而不是线段-矩形求交：前者更容易确认对（阈值一目了然），
        而这条用例要扶的就是一个“差几像素”的缺陷。
        """
        hits = []
        left, right = label["x"], label["x"] + label["width"]
        top, bottom = label["y"], label["y"] + label["height"]
        for arrow in arrows:
            pts = [(arrow["x"] + p[0], arrow["y"] + p[1]) for p in arrow["points"]]
            for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                steps = int(max(abs(x1 - x0), abs(y1 - y0)) / 0.5) + 1
                for i in range(steps + 1):
                    t = i / steps
                    x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
                    if left <= x <= right and top <= y <= bottom:
                        hits.append((round(x), round(y)))
        return hits

    def _labels_and_arrows(self, spec):
        scene = build(spec)
        labels = [e for e in scene["elements"]
                  if e["type"] == "text" and not e.get("containerId")]
        arrows = [e for e in scene["elements"] if e["type"] == "arrow"]
        return labels, arrows

    def test_label_is_not_crossed_by_its_arrow(self):
        """**用户看到的真实缺陷**：“还是有遮挡” —— `HTTPS` 被箭头线从中间穿过。

        根因：只上移了一个字号（12px）而标签本身高 15px，于是文字跨 [y-12, y+2]，
        线就落在里面。修法是沿**法线**退开。
        """
        spec = {"type": "architecture", "direction": "LR",
                "nodes": [{"id": "a", "kind": "client", "label": "Web 前端"},
                          {"id": "b", "kind": "security", "label": "API 网关"},
                          {"id": "c", "kind": "service", "label": "订单服务"}],
                "edges": [{"from": "a", "to": "b", "label": "HTTPS"},
                          {"from": "b", "to": "c", "label": "gRPC"}]}
        labels, arrows = self._labels_and_arrows(spec)
        self.assertEqual(2, len(labels))
        for label in labels:
            hits = self._hits(label, arrows)
            self.assertEqual([], hits,
                             f"标签 {label['id']} 被连线穿过（{len(hits)} 个采样点）")

    def test_midpoint_frame_survives_the_equal_length_vertex(self):
        """两段等长的折线，中点是拐点 —— 这时角平分线**必须**还在。

        真实缺陷：等长时 `walked + seg_len >= half` 会在第 1 段就成立
        （浮点上 seg0 比 half 小约 1e-14），中点被算成“第 1 段的 t≈0”。
        而顶点检测只认“落在段终点”那一种到达方式，于是这里被当成直段中间
        → back 与 fwd 互为精确反向 → 角平分线退化 → 只剩法线候选
        → 标签必然压在自己的折线臂上（实测那条 b→d 的边压了 30 个采样点）。
        """
        # 两段等长（都是 45°），拐点在中间。三组：
        #   ① 严格等长（路径上算得刚好落在拐点）
        #   ② 第一段短 1e-7（**实测真实发生的偏移量**，端点裁切引入）
        #   ③ 第一段长 1e-7（镜像情形）
        cases = [
            ("严格等长", [[272.0, 464.0], [403.0, 606.0], [272.0, 748.0]]),
            ("首段短 1e-7", [[272.0, 464.0], [403.0, 606.0 - 1e-7], [272.0, 748.0]]),
            ("首段长 1e-7", [[272.0, 464.0], [403.0, 606.0 + 1e-7], [272.0, 748.0]]),
        ]
        for name, pts in cases:
            with self.subTest(case=name):
                mid, back, fwd = E._midpoint_frame(pts)
                self.assertAlmostEqual(pts[1][0], mid[0], places=3)
                self.assertAlmostEqual(pts[1][1], mid[1], places=3)
                cross = abs(back[0] * fwd[1] - back[1] * fwd[0])
                self.assertGreater(
                    cross, 1e-6,
                    f"{name}: back={back} 与 fwd={fwd} 共线 —— 角平分线退化了，"
                    f"标签会压在自己的折线臂上。"
                    f"注意别用“到端点的绝对距离”当判据：实测差约 1e-6 像素，"
                    f"1e-9 的阈值会漏")

    def test_label_clears_diagonal_arrows_too(self):
        """斜线上的标签必须沿法线退开。

        “再往上挪一点”这个直觉写法在斜线上仍会压线 —— 所以这条用例用 TB 方向、
        多层级的图造出陡峭的斜边。
        """
        spec = {"type": "flow", "direction": "TB",
                "nodes": [{"id": "a", "kind": "client", "label": "开始"},
                          {"id": "b", "kind": "async", "label": "构建缓存"},
                          {"id": "c", "kind": "service", "label": "跑测试"},
                          {"id": "d", "kind": "security", "label": "审批"},
                          {"id": "e", "kind": "external", "label": "发布"}],
                "edges": [{"from": "a", "to": "b", "label": "触发"},
                          {"from": "b", "to": "c", "label": "命中"},
                          {"from": "c", "to": "d", "label": "通过"},
                          {"from": "d", "to": "e", "label": "合入"},
                          {"from": "b", "to": "d", "label": "长边"}]}
        labels, arrows = self._labels_and_arrows(spec)
        self.assertGreaterEqual(len(labels), 4)
        for label in labels:
            hits = self._hits(label, arrows)
            self.assertEqual([], hits,
                             f"标签 {label['id']} 被连线穿过（{len(hits)} 个采样点）")

    def test_label_gap_is_configurable_not_eyeballed(self):
        """退开量必须由参数/常量驱动，而不是拍脑袋的像素值。

        断言的是“间隙真的在起作用”—— 把 gap 调大，标签必须跟着退得更远。
        只断言某个具体坐标会把搜索策略写死，改实现就挂。

        gap 做成可传参而不是改模块常量：一来测试不必去改一个动态加载模块的属性，
        二来“退多远”本来就是一个调用方该能说的事。
        """
        pts = [[0.0, 0.0], [100.0, 0.0]]
        width, height = 40.0, 15.0
        _, y_tight, _ = E.label_position(pts, width, height, gap=2.0)
        _, y_loose, _ = E.label_position(pts, width, height, gap=40.0)
        self.assertLess(y_loose, y_tight, "把间隙调大，标签必须退得更远")
        self.assertGreaterEqual(0.0 - (y_tight + height), 1.9)
        self.assertLess(y_tight + height, 0.0, "标签必须整块在线的上方")

    def test_label_avoids_other_edges_too(self):
        """标签不能只躲自己那条边 —— **别的边穿过它同样是遮挡**。

        这是单纯算自家法线永远避不开的情况，也是改成候选搜索的主要理由之一。
        """
        own = [[0.0, 0.0], [200.0, 0.0]]
        other = [[0.0, -20.0], [200.0, -20.0]]
        x, y, needs_backdrop = E.label_position(own, 40.0, 15.0, [own, other])
        self.assertFalse(E._hits_lines(x, y, 40.0, 15.0, [own, other]),
                         "标签仍然撞在线段上")
        self.assertFalse(needs_backdrop, "有干净位置时不该要底色")

    def test_polyline_midpoint_is_by_arc_length(self):
        """中点是“走一半弧长”处的点，不是“中间那个拐点”。"""
        # 两个点的折线：中点应是两点平均，而不是第二个点（那正是曾经的 bug）
        self.assertEqual([5.0, 0.0], E.polyline_midpoint([[0, 0], [10, 0]]))
        # 不均等的两段：走一半长度，落在长的那段内部
        self.assertEqual([10.0, 45.0], E.polyline_midpoint([[0, 0], [10, 0], [10, 100]]))
        # 退化情况：长度为 0 时不除零
        self.assertEqual([3.0, 3.0], E.polyline_midpoint([[3, 3], [3, 3]]))

    def test_label_never_lands_on_top_of_a_node(self):
        """**用眼睛看到过的真实缺陷**：`HTTPS` 标签压在 `API 网关` 的左边缘。

        当时五项校验、绑定完整性、字段完整性全部绿 —— 只有看图才发现。
        根因是取“中间那个拐点”当中点：对 2 个点的折线，`pts[1]` 就是终点。
        这条用例把修复钉住，并且对**任意**边都要求标签不落在任何节点上。
        """
        spec = {"type": "architecture", "direction": "LR",
                "nodes": [{"id": "a", "kind": "client", "label": "Web 前端"},
                          {"id": "b", "kind": "security", "label": "API 网关"},
                          {"id": "c", "kind": "service", "label": "订单服务"}],
                "edges": [{"from": "a", "to": "b", "label": "HTTPS"},
                          {"from": "b", "to": "c", "label": "gRPC"}]}
        scene = build(spec)
        boxes = [e for e in scene["elements"] if e["type"] == "rectangle"]
        labels = [e for e in scene["elements"]
                  if e["type"] == "text" and not e.get("containerId")]
        self.assertEqual(2, len(labels))
        for lb in labels:
            for box in boxes:
                dx = min(lb["x"] + lb["width"], box["x"] + box["width"]) - max(lb["x"], box["x"])
                dy = min(lb["y"] + lb["height"], box["y"] + box["height"]) - max(lb["y"], box["y"])
                self.assertFalse(dx > 0 and dy > 0,
                                 f"标签 {lb['id']} 压在 {box['id']} 上")

    def test_label_becomes_a_standalone_text(self):
        spec = {"type": "architecture", "direction": "LR",
                "nodes": [{"id": "a", "kind": "client", "label": "A"},
                          {"id": "b", "kind": "service", "label": "B"}],
                "edges": [{"from": "a", "to": "b", "label": "HTTPS"}]}
        scene = build(spec)
        free = [e for e in scene["elements"]
                if e["type"] == "text" and not e.get("containerId")]
        self.assertEqual(1, len(free))
        self.assertEqual("HTTPS", free[0]["text"])

    def test_no_label_means_no_extra_text(self):
        scene = build(spec_of(["a", "b"], [("a", "b")]))
        free = [e for e in scene["elements"]
                if e["type"] == "text" and not e.get("containerId")]
        self.assertEqual([], free)


class TestCli(unittest.TestCase):
    def _write(self, spec) -> str:
        fh = tempfile.NamedTemporaryFile("w", suffix=".diagram.json", delete=False,
                                         encoding="utf-8")
        json.dump(spec, fh)
        fh.close()
        return fh.name

    def test_writes_file_next_to_spec(self):
        path = self._write(spec_of(["a", "b"], [("a", "b")]))
        out = os.path.splitext(path)[0] + ".excalidraw"
        try:
            proc = subprocess.run([sys.executable, EMIT, path],
                                  capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertTrue(os.path.exists(out))
            with open(out, encoding="utf-8") as fh:
                scene = json.load(fh)
            self.assertEqual("excalidraw", scene["type"])
        finally:
            for p in (path, out):
                if os.path.exists(p):
                    os.unlink(p)

    def test_blocked_spec_exits_one_and_writes_nothing(self):
        path = self._write(spec_of(["a", "b"], [("a", "b")], kind="queue"))
        out = os.path.splitext(path)[0] + ".excalidraw"
        try:
            proc = subprocess.run([sys.executable, EMIT, path],
                                  capture_output=True, text=True)
            self.assertEqual(1, proc.returncode)
            self.assertFalse(os.path.exists(out), "不通过时不该留下文件")
            self.assertIn("没有出图", proc.stderr)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_bad_json_exits_two(self):
        fh = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        fh.write("{not json")
        fh.close()
        try:
            proc = subprocess.run([sys.executable, EMIT, fh.name],
                                  capture_output=True, text=True)
            self.assertEqual(2, proc.returncode)
        finally:
            os.unlink(fh.name)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestOpeningView(unittest.TestCase):
    """写进 appState 的视图必须**真的把内容框在视口里**。

    只断言"字段存在"是没有用的 —— 数写错了字段照样存在。这里按 Excalidraw 的换算关系
    反推：屏幕位置 = (场景坐标 + scroll) × zoom，于是内容左上角应该正落在留白处。

    ⚠ 边界（实测）：这三个字段**在 `#url=` 导入那条路上会被忽略**（详见
    references/validation.md 的第三次对账）。这条用例管的是"我们写出去的值是对的"，
    管不了"应用一定采纳它"。
    """

    def test_content_left_top_lands_at_the_margin(self):
        scene = build(spec_of(["a", "b", "c"], [("a", "b"), ("b", "c")]))
        state = scene["appState"]
        left, top, right, bottom = E.scene_bounds(scene["elements"])
        self.assertGreater(right - left, 0)
        self.assertGreater(bottom - top, 0)
        self.assertAlmostEqual(E.OPEN_MARGIN[0], (left + state["scrollX"]) * state["zoom"],
                               delta=1.0)
        self.assertAlmostEqual(E.OPEN_MARGIN[1], (top + state["scrollY"]) * state["zoom"],
                               delta=1.0)

    def test_zooms_out_when_the_content_is_larger_than_the_viewport(self):
        """内容装不下时靠**缩小**来适配。

        用 TB 方向、1 个根挂 10 个叶子来构造"装不下"：它不会触发折段
        （折段只对每层 ≤ 2 个节点的链式图生效），所以横向真的会超出名义视口。
        最早想用 9 个节点的链来试，结果被折段折成了几列，比例只有 0.61 —— 覆盖不到。
        """
        leaves = [f"leaf{i}" for i in range(10)]
        scene = build(spec_of(["root", *leaves], [("root", leaf) for leaf in leaves],
                              direction="TB"))
        state = scene["appState"]
        left, top, right, bottom = E.scene_bounds(scene["elements"])
        room_x = E.OPEN_VIEW[0] - 2 * E.OPEN_MARGIN[0]
        self.assertGreater(right - left, room_x,
                           "这张图在 100% 下就装得下，覆盖不到缩小那条路径 —— 换个更大的场景")
        self.assertLess(state["zoom"], 1.0, "装不下却没有缩小")
        self.assertLessEqual((right - left) * state["zoom"], E.OPEN_VIEW[0])
        self.assertLessEqual((bottom - top) * state["zoom"],
                             E.OPEN_VIEW[1] - E.OPEN_MARGIN[1])


class TestLabelNeverSitsOnANode(unittest.TestCase):
    """标签压到**框**上比压到线上更糟 —— 分不清这行字属于谁。

    实测来由：五层架构那张里「上传 / 建 job」正好压在 apps/api 的框里、
    「注册与装配」压在 kernel/contracts 上。原因是节点矩形和线**同权**，
    兜底选“最不脏”时压框不压线的位置胜出。
    """

    def test_fallback_prefers_a_line_over_a_node(self):
        own = [[0.0, 0.0], [200.0, 0.0]]
        # 正上方放一个节点矩形（闭合折线），更远处放一条线
        node = (60.0, -40.0, 140.0, -10.0)          # keepouts 是矩形 (x0, y0, x1, y1)
        width, height = 40.0, 15.0
        x, y, needs_backdrop = E.label_position(own, width, height, [own], [node])
        self.assertEqual(0, E._box_hits(x, y, width, height, [node]),
                         "宁可压线也不能压框 —— 兜底没避开节点")
        self.assertFalse(needs_backdrop, "避开了节点又没压线，不需要底色")

    def test_no_clean_spot_anywhere_asks_for_a_backdrop(self):
        # 把标签整个包在一个节点矩形里，四周再缠上线：真的没有干净位置
        node_rect = (-200.0, -200.0, 200.0, 200.0)
        lines = [[[-200.0, -200.0], [200.0, -200.0], [200.0, 200.0], [-200.0, 200.0],
                  [-200.0, -200.0]],
                 [[-300.0, 0.0], [300.0, 0.0]], [[0.0, -300.0], [0.0, 300.0]]]
        _, _, needs_backdrop = E.label_position([[0.0, 0.0], [10.0, 0.0]], 40.0, 15.0,
                                                lines, [node_rect])
        self.assertTrue(needs_backdrop, "完全没有干净位置时应当要底色")



class TestStyleAxes(unittest.TestCase):
    """四组样式轴：默认不是实心、未知值判失败、落笔真的跟着变。"""

    def spec(self, style=None):
        spec = {
            "type": "flow", "direction": "TB",
            "nodes": [{"id": "a", "label": "A", "kind": "plain"},
                      {"id": "b", "label": "B", "kind": "plain"}],
            "edges": [{"from": "a", "to": "b"}],
        }
        if style is not None:
            spec["style"] = style
        return spec

    def elements(self, style=None):
        spec = self.spec(style)
        boxes = L.boxes_from_spec(spec)
        result = L.layout(spec, boxes)
        return E.build_scene(spec, result, boxes, None, None)["elements"]

    def node(self, style=None):
        return next(e for e in self.elements(style) if e["id"].startswith("node-"))

    def test_default_is_not_solid(self):
        """默认**不是实心** —— 用户明确要求"尽量不要用实心的颜色"。"""
        self.assertEqual("hachure", self.node()["fillStyle"])

    def test_fill_axis_reaches_the_element(self):
        for value in palette.FILL_STYLES:
            with self.subTest(value=value):
                self.assertEqual(value, self.node({"fill": value})["fillStyle"])

    def test_stroke_axis_reaches_the_shape_only(self):
        """`stroke` 改节点的框，**不改连线** —— 连线的虚实是语义。"""
        self.assertEqual("dotted", self.node({"stroke": "dotted"})["strokeStyle"])
        arrow = next(e for e in self.elements({"stroke": "dotted"}) if e["type"] == "arrow")
        self.assertEqual("solid", arrow["strokeStyle"], "边是同步的，本来就该是实线")
        dashed = next(e for e in self.elements({"stroke": "dotted"}) if e["type"] == "arrow")
        self.assertNotEqual("dotted", dashed["strokeStyle"])

    def test_corners_axis_reaches_the_element(self):
        self.assertIsNone(self.node({"corners": "sharp"})["roundness"])
        self.assertIsNotNone(self.node({"corners": "round"})["roundness"])

    def test_line_axis_reaches_nodes_and_arrows(self):
        for value, expected in palette.ROUGHNESS_OF.items():
            with self.subTest(value=value):
                elements = self.elements({"line": value})
                self.assertEqual(expected, self.node({"line": value})["roughness"])
                arrow = next(e for e in elements if e["type"] == "arrow")
                self.assertEqual(expected, arrow["roughness"])

    def test_unknown_axis_is_rejected(self):
        with self.assertRaises(ValueError) as caught:
            palette.resolve_style({"colour": "red"})
        self.assertIn("colour", str(caught.exception))

    def test_unknown_value_is_rejected(self):
        with self.assertRaises(ValueError) as caught:
            palette.resolve_style({"fill": "sparkles"})
        self.assertIn("sparkles", str(caught.exception))

    def test_validate_reports_bad_axes(self):
        issues = V.validate(self.spec({"fill": "sparkles", "colour": "red"})).items
        codes = {i["code"] for i in issues}
        self.assertIn("BAD_STYLE_VALUE", codes)
        self.assertIn("BAD_STYLE_AXIS", codes)


class TestRegionLabelElements(unittest.TestCase):
    """区域标题的落笔：断行与尺寸**来自 layout**，不在这里重新量一遂（P17）。

    重新量一遂就会漂 —— 而“框与字对不上”正是用户报的那个溢出的根。
    """

    SPEC = {
        "type": "architecture", "direction": "LR", "title": "T",
        "groups": [{"id": "truth", "label": "三真源：完成 = 期望 × 执行 × 物化对齐"}],
        "nodes": [{"id": "a", "label": "A", "kind": "service", "group": "truth"},
                  {"id": "b", "label": "B", "kind": "plain"}],
        "edges": [{"from": "a", "to": "b"}],
    }

    def scene(self):
        boxes = L.boxes_from_spec(self.SPEC)
        result = L.layout(self.SPEC, boxes)
        return E.build_scene(self.SPEC, result, boxes, None, None), boxes, result

    def label(self):
        scene, _boxes, _result = self.scene()
        return next(e for e in scene["elements"] if e["id"].startswith("region-label-"))

    def test_text_carries_the_wrapped_lines(self):
        element = self.label()
        self.assertIn("\n", element["text"], "长标题没有被断行 —— 它会从区域里冒出去")
        self.assertEqual(element["text"], element["originalText"])

    def test_区域的_style_真的落到矩形上(self):
        """`groups[].style` 必须真的生效。

        漏过一次：校验器允许这个字段、落笔那边也读 `region.get("style")`，
        但 `region_boxes` 没把它带出去 —— 规格里写明 `{stroke: dashed,
        fill: cross-hatch}`，出图仍是 solid + hachure（夹具 07-regions.json 实测）。
        「写了、校验通过、静默无效」比报错难查得多，所以这条钉在端到端上。
        """
        spec = {
            "type": "architecture", "direction": "LR", "title": "T",
            "groups": [{"id": "g", "label": "G",
                        "style": {"stroke": "dashed", "fill": "cross-hatch"}}],
            "nodes": [{"id": "a", "label": "A", "kind": "service", "group": "g"},
                      {"id": "b", "label": "B", "kind": "plain"}],
            "edges": [{"from": "a", "to": "b"}],
        }
        boxes = L.boxes_from_spec(spec)
        scene = E.build_scene(spec, L.layout(spec, boxes), boxes, None, None)
        rect = next(e for e in scene["elements"]
                    if e["type"] == "rectangle" and e["id"].startswith("region-"))
        self.assertEqual("dashed", rect["strokeStyle"])
        self.assertEqual("cross-hatch", rect["fillStyle"])

    def test_没写_style_时区域回到默认(self):
        """没写 `style` 就不该被自己的空值影响 —— 默认仍是实线。"""
        spec = {
            "type": "architecture", "direction": "LR", "title": "T",
            "groups": [{"id": "g", "label": "G"}],
            "nodes": [{"id": "a", "label": "A", "kind": "service", "group": "g"},
                      {"id": "b", "label": "B", "kind": "plain"}],
            "edges": [{"from": "a", "to": "b"}],
        }
        boxes = L.boxes_from_spec(spec)
        scene = E.build_scene(spec, L.layout(spec, boxes), boxes, None, None)
        rect = next(e for e in scene["elements"]
                    if e["type"] == "rectangle" and e["id"].startswith("region-"))
        self.assertEqual("solid", rect["strokeStyle"])

    def test_element_geometry_equals_the_layout_box(self):
        """宽高必须**逐字**等于 `region_boxes` 算好的那一份。"""
        element = self.label()
        scene, boxes, result = self.scene()
        region = next(r for r in L.region_boxes(self.SPEC, result.placed, boxes)
                      if r["id"] == "truth")
        self.assertAlmostEqual(element["width"], region["label_width"], places=2)
        self.assertAlmostEqual(element["height"], region["label_height"], places=2)
        self.assertAlmostEqual(element["y"], region["label_y"], places=2)
        self.assertEqual(element["fontSize"], region["label_size"])

    def test_every_line_fits_inside_the_region(self):
        element = self.label()
        scene, boxes, result = self.scene()
        region = L.region_boxes(self.SPEC, result.placed, boxes)[0]
        usable = region["width"] - 2 * L.REGION_LABEL_MARGIN + 0.01
        self.assertLessEqual(element["width"], usable)
        for line in element["text"].split("\n"):
            self.assertLessEqual(tm.weighted_units(line) * element["fontSize"], usable,
                                 f"这一行还是比区域宽：{line!r}")

    def test_label_is_not_container_bound(self):
        """区域标题是**独立文字**（`containerId: None`）—— 所以断行由我们说了算。

        节点标签是容器绑定的，Excalidraw 会按真实字体**重排**它（那是已知限制）；
        区域标题带显式换行符且不绑容器，渲染器不会自己再断一遂。
        """
        self.assertIsNone(self.label()["containerId"])


class TestEdgeLabelCollisions(unittest.TestCase):
    """P18：边标签互相压 / 压区域标题 / 飘得离自己那条线太远。

    这一组用例用**密集图**：自带 fixture 里最多只有 5 个边标签，
    在它们上面根本触发不了重叠（实测：把修复退回去，7 张 fixture 仍然是 0）。
    用户报回来的正是密集那种：“线上的文本和其他线上的文本可能会重叠，
    特别是线比较密集的时候”。
    """

    # 12 条边、每条一个计数标签（用户那张包依赖图的形状）。
    DENSE = {
        "type": "dependency", "direction": "LR", "title": "密集标签",
        "nodes": [{"id": "cap", "kind": "service", "label": "capabilities",
                   "group": "rt"},
                  {"id": "prov", "kind": "service", "label": "providers",
                   "group": "rt"},
                  {"id": "app", "kind": "service", "label": "application",
                   "group": "rt"}],
        "groups": [{"id": "rt", "label": "运行时链路"}],
        "edges": [{"from": "cap", "to": "app", "label": "18 处"},
                  {"from": "prov", "to": "app", "label": "2 处"},
                  {"from": "cap", "to": "prov", "label": "4 处"},
                  {"from": "prov", "to": "cap", "label": "31 处"},
                  {"from": "cap", "to": "app", "label": "33 处"},
                  {"from": "prov", "to": "app", "label": "15 处"},
                  {"from": "cap", "to": "prov", "label": "16 处"},
                  {"from": "prov", "to": "cap", "label": "29 处"},
                  {"from": "cap", "to": "app", "label": "24 处"},
                  {"from": "prov", "to": "app", "label": "0 处"},
                  {"from": "cap", "to": "prov", "label": "3 处"},
                  {"from": "prov", "to": "cap", "label": "42 处"}],
    }

    # 用户截图里那一处：边的自动 kind 标签压在一个区域标题上。
    # 这份规格是**最小的可复现**：把“区域标题不算避让物”退回去，它就会重叠（实测 1 处）。
    # 边用 `async` 是因为**默认 kind 不再自动补标签**（那正是“同步调用”满屏的原因）——
    # 要复现“标签压标题”，就得用会真的补出标签的那种边。
    WITH_TITLE = {
        "type": "flow", "direction": "TB", "title": "T", "detail": "diagnostic",
        "groups": [{"id": "g", "label": "探针与门禁"}],
        "nodes": [{"id": "src", "kind": "service", "label": "入口"},
                  {"id": "n0", "kind": "service", "label": "步骤0", "group": "g"},
                  {"id": "n1", "kind": "service", "label": "步骤1", "group": "g"}],
        "edges": [{"from": "src", "to": "n0", "kind": "async"},
                  {"from": "src", "to": "n1", "kind": "async"},
                  {"from": "n0", "to": "n1", "kind": "async"}],
    }

    @staticmethod
    def _rects(elements, prefix, container=False):
        out = []
        for el in elements:
            if prefix and el["id"].startswith(prefix):
                out.append(el)
            elif container and el["type"] == "text" and el.get("containerId"):
                out.append(el)
        return out

    @staticmethod
    def _overlaps(first, second):
        pairs = []
        for i, a in enumerate(first):
            for j, b in enumerate(second):
                if a is b or (first is second and j <= i):
                    continue
                if (a["x"] < b["x"] + b["width"] and a["x"] + a["width"] > b["x"]
                        and a["y"] < b["y"] + b["height"]
                        and a["y"] + a["height"] > b["y"]):
                    pairs.append((a.get("text"), b.get("text")))
        return pairs

    def test_dense_labels_do_not_overlap(self):
        """12 个标签挤在同一片空档里 —— 以前实测 **7 对重叠**，且没有任何校验会报。"""
        scene, _result, _outcome, _attempts = E.emit(self.DENSE)
        labels = self._rects(scene["elements"], "elabel")
        self.assertEqual(12, len(labels), "这份规格应该每个边都有标签")
        self.assertEqual([], self._overlaps(labels, labels), "边标签之间还在重叠")

    def test_labels_avoid_region_titles(self):
        """区域标题也是要读的字 —— 而它不是节点、也不是连线。"""
        scene, _result, _outcome, _attempts = E.emit(self.WITH_TITLE)
        labels = self._rects(scene["elements"], "elabel")
        titles = self._rects(scene["elements"], "region-label-")
        self.assertTrue(labels, "这份规格应该补出自动 kind 标签")
        self.assertTrue(titles)
        self.assertEqual([], self._overlaps(labels, titles), "边标签压在区域标题上")

    def test_labels_do_not_sit_on_node_text(self):
        scene, _result, _outcome, _attempts = E.emit(self.WITH_TITLE)
        labels = self._rects(scene["elements"], "elabel")
        node_texts = self._rects(scene["elements"], "", container=True)
        self.assertEqual([], self._overlaps(labels, node_texts), "边标签压在节点文字上")

    def test_labels_stay_near_their_own_edge(self):
        """标签要**贴着自己那条线**、沿它滑开，而不是为了避让飘到很远的地方。

        实测：把“先沿线滑、再往外推”写反（先进退让量）时，最大偏离 **191px**，
        一堆标签飘在离自己那条线很远的地方 —— 用户看到的“太拥挤”就是那个。
        换回来之后同一张图最大偏离降到 **35px**。
        """
        scene, result, _outcome, _attempts = E.emit(self.DENSE)
        labels = self._rects(scene["elements"], "elabel")
        self.assertEqual(len(result.edges), len(labels), "标签与边一一对应才能配对")
        worst = 0.0
        for edge, label in zip(result.edges, labels):
            centre = (label["x"] + label["width"] / 2.0,
                      label["y"] + label["height"] / 2.0)
            pts = edge["points"]
            worst = max(worst, min(_point_segment_distance(centre, a, b)
                                   for a, b in zip(pts, pts[1:])))
        self.assertLessEqual(worst, 60.0,
                             f"有标签离自己那条线 {worst:.0f}px —— 看不出它属于哪条边")


class TestDetailLevels(unittest.TestCase):
    """`detail` 档位：executive 只留重点、standard 全留、diagnostic 额外补边语义。

    ⚠️ 这个字段以前是**空壳**（校验器认它、别的脚本一处都不读），而 SKILL.md 的硬规则
    表里写着「信息量用 detail 控制」。同一类静默失败，旧的 `groups` 也是。
    """

    def spec(self, level=None, detail="一行说明"):
        spec = {
            "type": "flow", "direction": "TB",
            "nodes": [{"id": "a", "label": "A", "kind": "plain", "detail": detail},
                      {"id": "b", "label": "B", "kind": "plain", "detail": detail,
                       "emphasis": "primary"}],
            "edges": [{"from": "a", "to": "b", "kind": "async", "label": "用户写的"}],
        }
        if level:
            spec["detail"] = level
        return spec

    def texts(self, level=None, detail="一行说明"):
        spec = self.spec(level, detail)
        boxes = L.boxes_from_spec(spec)
        result = L.layout(spec, boxes)
        scene = E.build_scene(spec, result, boxes, None, None)
        return [el.get("text", "") for el in scene["elements"] if el["type"] == "text"]

    def test_default_keeps_everything(self):
        """不写 `detail` = standard = 实现之前的行为（所以不影响任何既有规格）。"""
        self.assertIn("一行说明", self.texts())
        self.assertIn("用户写的", self.texts())

    def test_executive_drops_secondary_text(self):
        """executive：普通节点的次要说明不要，**重点节点留着** —— 摘要只留结论。"""
        got = self.texts("executive")
        self.assertEqual(1, sum(1 for t in got if t == "一行说明"),
                         "普通节点的那行说明该被丢掉，重点节点的该留着")

    def test_executive_drops_user_edge_labels(self):
        self.assertNotIn("用户写的", self.texts("executive"))

    def test_executive_shrinks_the_box(self):
        """少了那行字，**盒子就该变小** —— 尺寸链必须跟着档位走，不能只有文字变。"""
        plain = L.boxes_from_spec(self.spec("standard"))["a"]
        short = L.boxes_from_spec(self.spec("executive"))["a"]
        self.assertLess(short.height, plain.height)

    def test_diagnostic_labels_edge_kinds(self):
        """diagnostic：**用户没写**标签的边，自动补上 kind 的中文说明（异步 / 可选…）。"""
        spec = self.spec("diagnostic")
        spec["edges"][0].pop("label")          # 这条边用户没写标签
        boxes = L.boxes_from_spec(spec)
        result = L.layout(spec, boxes)
        scene = E.build_scene(spec, result, boxes, None, None)
        texts = [el.get("text", "") for el in scene["elements"] if el["type"] == "text"]
        # 文案取自 palette.EDGE_KINDS 的 zh（"异步 / 事件"），所以查子串不查相等
        self.assertTrue(any("异步" in t for t in texts), texts)

    def test_diagnostic_does_not_override_user_labels(self):
        """自动补的**从不**让位给人写的东西。"""
        spec = self.spec("diagnostic")
        boxes = L.boxes_from_spec(spec)
        result = L.layout(spec, boxes)
        scene = E.build_scene(spec, result, boxes, None, None)
        texts = [el.get("text", "") for el in scene["elements"] if el["type"] == "text"]
        self.assertIn("用户写的", texts)
        self.assertFalse(any("异步" in t for t in texts),
                         "用户已经写了标签，就不该再自动补一个")

    def test_diagnostic_skips_the_default_kind(self):
        """**默认 kind 不补标签** —— 实线 + 箭头方向已经说明“同步调用”了。

        不补的理由是密集图上的观感：一片区域里四五个“同步调用”是零信息量的重复，
        用户的原话是“太拥挤了看着”。实测一张 12 条边的图里默认 kind 占绝大多数，
        这条一下子就去掉了大部分标签。
        """
        for explicit in (True, False):
            with self.subTest(explicit_sync=explicit):
                spec = self.spec("diagnostic")
                spec["edges"][0].pop("label")
                if explicit:
                    spec["edges"][0]["kind"] = palette.DEFAULT_EDGE_KIND
                else:
                    spec["edges"][0].pop("kind")          # 不写 = 默认
                boxes = L.boxes_from_spec(spec)
                result = L.layout(spec, boxes)
                scene = E.build_scene(spec, result, boxes, None, None)
                texts = [el.get("text", "") for el in scene["elements"]
                         if el["type"] == "text"]
                self.assertFalse(any("同步" in t for t in texts),
                                 f"默认 kind 还是被补了标签：{texts}")

    def test_diagnostic_still_labels_non_default_solid_kinds(self):
        """`data` 也是实线，但**不是默认** —— 光看线分不出“调用”与“读写”，所以要补。

        判据是“这条边不是默认那一种”，不是“它是不是虚线”。
        """
        spec = self.spec("diagnostic")
        spec["edges"][0].pop("label")
        spec["edges"][0]["kind"] = "data"
        boxes = L.boxes_from_spec(spec)
        result = L.layout(spec, boxes)
        scene = E.build_scene(spec, result, boxes, None, None)
        texts = [el.get("text", "") for el in scene["elements"] if el["type"] == "text"]
        self.assertTrue(any("数据读写" in t for t in texts), texts)


class TestEveryTopFieldIsRead(unittest.TestCase):
    """spec 的每个顶层字段，必须至少被一个**非校验**脚本读一次。

    这条是被两次真实事故逼出来的：`groups` 与 `detail` 都曾经是「校验器认它、
    layout / check_layout / emit 一处都不读」的空壳 —— 声明了、校验通过了、图上
    什么都不发生，而且一个字都不报。单元测试抓不到它（每个零件单独看都正常），
    只有把「有没有人读」本身当成断言才抓得到。

    读的方式不限于 `spec.get("x")`：也可能是 `spec["x"]`，或者由调用方取出来传进去。
    所以这里只查**字段名这个字符串**在非校验脚本里出现过 —— 宁可松一点，
    也不要为了精确而漏掉真正的空壳。
    """

    @staticmethod
    def _script_text() -> str:
        import glob
        import os
        # 用模块级的 SKILL（测试搬到顶层 `tests/<skill>/` 之后，"上一级"不再是 skill 目录）
        folder = SCRIPTS
        chunks = []
        for path in sorted(glob.glob(os.path.join(folder, "*.py"))):
            if os.path.basename(path) == "validate_spec.py":
                continue                      # 校验器读字段名不算「有人用它」
            with open(path, encoding="utf-8") as handle:
                chunks.append(handle.read())
        return "\n".join(chunks)

    def test_no_declared_field_is_a_no_op(self):
        text = self._script_text()
        self.assertTrue(text.strip(), "一个脚本都没读到，用例成了空话")
        missing = sorted(f for f in V.TOP_FIELDS if f'"{f}"' not in text)
        self.assertEqual([], missing,
                         f"这些顶层字段只有校验器认识，没有任何脚本读它们（空壳）：{missing}")


class TestEveryLabelSurvives(unittest.TestCase):
    """规格里写了标注的边，**每一条都必须真的画出标注**。

    落位搜索找不到干净位置时有一条静默路径：先用自动标注顶替（`同步`/`异步`），
    再不行就干脆不画。实测 0 次触发，但那条分支存在 —— 一旦触发就是
    **信息悄悄消失**（仓库里最讨厌的那类失败），所以用夹具把它钉住：
    只要某条带标注的边被丢了或换了字，这条用例就红。
    """

    def test_fixture_labels_all_rendered_verbatim(self):
        specs = sorted(glob.glob(os.path.join(HERE, "fixtures", "specs", "*.json")))
        self.assertTrue(specs, "一个夹具规格都没找到")
        checked = 0
        for path in specs:
            spec = json.load(open(path, encoding="utf-8"))
            scene = build(spec)
            drawn = {e["id"]: e["text"] for e in scene["elements"]
                     if e["type"] == "text" and str(e["id"]).startswith("elabel-")}
            for i, edge in enumerate(spec.get("edges") or []):
                if not edge.get("label"):
                    continue
                checked += 1
                # 用发射器自己的 `_eid` 拼 id，别手搓 —— 索引为 0 时它**不带** `-0`
                # 后缀（`f"{kind}-{safe}-{index}" if index else ...`），手搓必错。
                eid = E._eid("elabel", f"{edge['from']}-{edge['to']}", i)
                self.assertIn(eid, drawn,
                              f"{os.path.basename(path)}：{eid} 的标注没画出来")
                self.assertEqual(edge["label"], drawn[eid],
                                 f"{os.path.basename(path)}：{eid} 的标注被换成了别的字")
        self.assertGreater(checked, 0, "夹具里居然没有一条带标注的边，这条用例等于没跑")
