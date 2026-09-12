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

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
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


def spec_of(ids, edges, **kw) -> dict:
    return {"type": kw.pop("type", "architecture"), "direction": kw.pop("direction", "LR"),
            "nodes": [{"id": n, "kind": kw.get("kind", "service"), "label": n} for n in ids],
            "edges": [{"from": a, "to": b} for a, b in edges]}


def build(spec: dict) -> dict:
    scene, result, outcome, attempts = E.emit(spec)
    assert scene, f"没出图：{[i.line() for i in outcome.blocking]}"
    return scene


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
            allowed.update(v for k, v in entry.items() if k in ("stroke", "background"))
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
        """跨层边要保留虚节点拐点，不能压成一条直线。"""
        scene = build(spec_of("ABCDE", [("A", "B"), ("B", "C"), ("C", "D"), ("D", "E"),
                                        ("A", "D"), ("A", "E")]))
        arrows = [e for e in scene["elements"] if e["type"] == "arrow"]
        self.assertEqual(6, len(arrows), "边丢了")
        self.assertTrue(any(len(a["points"]) > 2 for a in arrows),
                        "没有任何箭头带拐点 —— 跨层边被压直了")


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


class TestRefusesBlockedSpecs(unittest.TestCase):
    """校验有阻塞项就不该出图 —— 出图是流水线最后一步。"""

    def test_unknown_kind_produces_no_scene(self):
        spec = spec_of(["a", "b"], [("a", "b")], kind="queue")
        scene, result, outcome, attempts = E.emit(spec)
        self.assertEqual({}, scene)
        self.assertTrue(outcome.blocking)


class TestEdgeLabels(unittest.TestCase):
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
            self.assertFalse(os.path.exists(out), "阻塞时不该留下文件")
            self.assertIn("不出图", proc.stderr)
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
