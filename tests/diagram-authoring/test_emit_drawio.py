#!/usr/bin/env python3
"""emit_drawio.py 的回归测试：规格 → `.drawio` 的正确性，以及**跨后端一致性**。

## 这一层真正要钉的两件事

1. **几何是共用的，不是重新推的。** 两个后端读同一份 `*.diagram.json`、走同一套
   `layout` —— 所以 `.drawio` 里的坐标必须能对上 `layout` 的结果，只差一个整图平移。
   如果哪天有人"顺手"在 drawio 这边重算一次位置，这条会红，而图看起来还是对的
   （这就是为什么必须写成断言，光看图看不出来）。

2. **坏文件绝不落盘。** `emit` 在写之前调 `check_drawio`；结构自检不过就报错退出。
   本轮真出过一次这类事故：`value` 属性里写了裸 `<br>`（XML 里必须写成 `&lt;br&gt;`），
   生成的文件**打不开** —— 被自检当场拦住，一次都没写进用户的目录。
   `test_structural_check_failure_blocks_the_write` 就是钉这件事。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/test_emit_drawio.py
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
# 测试住在仓库顶层 `tests/<skill>/`（**刻意不在 skill 目录里**：AI 调用 skill 时读的是
# `skills/<skill>/` 那棵树，测试放在里面会被顺手读进去）。
# 所以从 `tests/<skill>/` 往上两级到仓库根，再进 `skills/<skill>/`。
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
SCRIPTS = os.path.join(SKILL, "scripts")
SPECS = os.path.join(HERE, "fixtures", "specs")
FIXTURES = sorted(os.path.join(SPECS, name) for name in os.listdir(SPECS)
                  if name.endswith(".json"))


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


D = _load("emit_drawio", os.path.join(SCRIPTS, "emit_drawio.py"))
C = _load("check_drawio", os.path.join(SCRIPTS, "check_drawio.py"))
E = _load("emit_excalidraw", os.path.join(SCRIPTS, "emit_excalidraw.py"))
L = D.L
shapes = D.shapes


# ── 造规格 ────────────────────────────────────────────────────────

def spec_of(ids: list[str], edges: list[tuple], **kw) -> dict:
    """最小规格。`edges` 的元素是 `(from, to)` 或 `(from, to, {额外字段})`。"""
    built = []
    for edge in edges:
        item = {"from": edge[0], "to": edge[1]}
        if len(edge) > 2:
            item.update(edge[2])
        built.append(item)
    spec = {"type": kw.pop("type", "architecture"),
            "direction": kw.pop("direction", "LR"),
            "nodes": kw.pop("nodes", [{"id": n, "kind": "service", "label": n}
                                      for n in ids]),
            "edges": built}
    spec.update(kw)
    return spec


def spec_from_file(path: str) -> dict:
    with open(path, encoding="utf-8") as handle:
        loaded: dict = json.load(handle)
    return loaded


def build(spec: dict, scheme: str | None = None,
          seeds: dict | None = None) -> str:
    xml, _result, outcome, _attempts = D.emit(spec, scheme=scheme, seeds=seeds)
    assert xml, f"没出图：{[i.line() for i in outcome.blocking]}"
    return xml


# ── 读文件 ────────────────────────────────────────────────────────
#
# ⚠️ 节点的 id 现在在 `<UserObject>` 上（不是内层 mxCell）—— 所以**一切查找都要走
# “身份元素”**：带 UserObject 的取外层，裸 mxCell 取自己。直接遍历 `//mxCell` 会
# 找不到任何节点 id，而症状是"区域没包住成员"这种看着像布局问题的假象。

def _inner(element: ET.Element) -> ET.Element:
    """身份元素 → 真正带 vertex / edge / style 的那个 mxCell。"""
    if element.tag != "UserObject":
        return element
    inner = element.find("mxCell")
    assert inner is not None, "UserObject 里没有 mxCell"
    return inner


def identity(xml: str) -> list[tuple[str, ET.Element]]:
    """[(id, 身份元素)]，**按文档顺序**（顺序就是层叠顺序，z-order 用例靠它）。

    内层 mxCell 不带 id，所以一遍遍历就能两种写法都收全。
    """
    root: ET.Element = ET.fromstring(xml)
    out: list[tuple[str, ET.Element]] = []
    for element in root.iter():
        cell_id = element.get("id")
        if cell_id and element.tag in ("UserObject", "mxCell"):
            out.append((cell_id, element))
    return out


def _attr(element: ET.Element, name: str) -> str:
    """属性：先看身份元素，没有就钻进 UserObject 取内层（style / parent 都在内层）。"""
    value = element.get(name)
    if value is None and element.tag == "UserObject":
        inner = element.find("mxCell")
        value = None if inner is None else inner.get(name)
    return value or ""


def _num(element: ET.Element, field: str) -> float:
    raw = element.get(field)
    assert raw is not None, f"缺少属性 {field}"
    return float(raw)


def cells(xml: str) -> list[ET.Element]:
    root: ET.Element = ET.fromstring(xml)
    return [element for element in root.iter("mxCell")]


def by_id(xml: str) -> dict[str, ET.Element]:
    return dict(identity(xml))


def diagram_id(xml: str) -> str:
    element = ET.fromstring(xml).find(".//diagram")
    assert element is not None, "没有 <diagram>"
    return element.get("id") or ""


def rect_of(element: ET.Element) -> tuple[float, float, float, float]:
    geometry = element.find(".//mxGeometry")
    assert geometry is not None, f"{_attr(element, 'id')} 没有几何"
    return (_num(geometry, "x"), _num(geometry, "y"),
            _num(geometry, "width"), _num(geometry, "height"))


def node_rects(xml: str) -> dict[str, tuple[float, float, float, float]]:
    return {cid[2:]: rect_of(element) for cid, element in identity(xml)
            if cid.startswith("n-")}


def region_rects(xml: str) -> dict[str, tuple[float, float, float, float]]:
    return {cid[7:]: rect_of(element) for cid, element in identity(xml)
            if cid.startswith("region-") and not cid.startswith("region-label-")}


def _label_of(element: ET.Element) -> str:
    """文字：`UserObject` 用 `label`，裸 mxCell 用 `value`。"""
    return _attr(element, "label") if element.tag == "UserObject" else _attr(element, "value")


def value_lines(element: ET.Element) -> list[str]:
    """把文字还原成行（`<br>` → 换行）。

    ⚠️ 换的是 **`<br>`**，不是 `&lt;br&gt;` —— `ElementTree` 读属性时已经把 XML 实体
    解开了。第一版换的是 `&lt;br&gt;`，于是每一行都还原成带 `<br>` 的一坨，
    跳后端逐行比对当即全红（那正是那条测试该干的事）。
    """
    return _label_of(element).replace("<br>", "\n").split("\n")


def inside(inner: tuple, outer: tuple, tol: float = 0.01) -> bool:
    ix, iy, iw, ih = inner
    ox, oy, ow, oh = outer
    return (ix >= ox - tol and iy >= oy - tol
            and ix + iw <= ox + ow + tol and iy + ih <= oy + oh + tol)


def layout_of(spec: dict) -> Any:
    """按发射器同一条流水线跑一次布局，用来对照文件里的坐标。"""
    boxes = L.boxes_from_spec(spec)
    result, outcome, _attempts = D._load_sibling("check_layout").layout_with_retry(
        spec, boxes, None)
    assert not outcome.blocking, [i.line() for i in outcome.blocking]
    return result


class TestEveryFixtureEmits(unittest.TestCase):
    """七个端到端夹具（覆盖全部图型与样式轴）都要能出图，并通过结构自检。"""

    def test_all_fixtures_emit_and_pass_checker(self):
        for path in FIXTURES:
            with self.subTest(fixture=os.path.basename(path)):
                spec = spec_from_file(path)
                xml = build(spec)
                self.assertEqual(C.check_text(xml), [])
                self.assertEqual(len(node_rects(xml)), len(spec.get("nodes", [])))
                self.assertEqual(len([c for c in cells(xml) if c.get("edge")]),
                                 len(spec.get("edges", [])))

    def test_regeneration_is_byte_identical(self):
        """幂等的**意义**：重跑不产生 diff，于是"这张图变了没有"能被工具判断。

        所以文件里不能有时间戳（`modified` 那一类）—— 设计时差点写进去。
        """
        for path in FIXTURES:
            with self.subTest(fixture=os.path.basename(path)):
                spec = spec_from_file(path)
                self.assertEqual(build(spec), build(spec))

    def test_no_timestamp_or_random_value_in_output(self):
        xml = build(spec_from_file(FIXTURES[0]))
        self.assertNotIn("modified=", xml)
        for token in ("versionNonce", "seed", "updated", "random"):
            self.assertNotIn(token, xml)

    def test_diagram_id_is_derived_from_content(self):
        """id 由内容派生：同一份规格两次生成同一个 id（否则每次都是新页面）。"""
        first = build(spec_from_file(FIXTURES[0]))
        self.assertEqual(diagram_id(first), diagram_id(build(spec_from_file(FIXTURES[0]))))
        self.assertEqual(_attr(by_id(first)["1"], "parent"), "0")


class TestZOrder(unittest.TestCase):
    """顺序就是层叠顺序：区域在最下，节点其次，边在最上。"""

    def test_regions_then_nodes_then_edges(self):
        xml = build(spec_from_file(os.path.join(SPECS, "07-regions.json")))
        case_ids = identity(xml)
        kinds = []
        for cell_id, element in case_ids:
            if _inner(element).get("vertex") is None and _inner(element).get("edge") is None:
                continue
            if cell_id.startswith("region-label-"):
                kinds.append("label")
            elif cell_id.startswith("region-"):
                kinds.append("region")
            elif cell_id.startswith("n-"):
                kinds.append("node")
            else:
                kinds.append("edge")
        first_seen: list[str] = []
        for kind in kinds:
            if kind not in first_seen:
                first_seen.append(kind)
        self.assertEqual(first_seen, ["region", "label", "node", "edge"])
        self.assertNotIn("region", kinds[kinds.index("node"):], "区域跑到节点后面去了")


class TestGeometryIsShared(unittest.TestCase):
    """`.drawio` 的坐标必须就是 `layout` 的结果，只差一个整图平移。"""

    def test_node_rects_match_layout_exactly(self):
        spec = spec_from_file(os.path.join(SPECS, "01-architecture.json"))
        rects = node_rects(build(spec))
        result = layout_of(spec)
        first = next(iter(result.placed))
        dx = rects[first][0] - result.placed[first].x
        dy = rects[first][1] - result.placed[first].y
        for node_id, position in result.placed.items():
            if node_id not in rects:
                continue          # 虚节点不该出现在文件里
            self.assertAlmostEqual(rects[node_id][0], position.x + dx, places=2)
            self.assertAlmostEqual(rects[node_id][1], position.y + dy, places=2)
            self.assertAlmostEqual(rects[node_id][2], position.width, places=2)
            self.assertAlmostEqual(rects[node_id][3], position.height, places=2)

    def test_edge_waypoints_match_layout_polyline(self):
        """中间的折点就是 layout 折线去掉首尾 —— 不是 drawio 自己绕的路。"""
        spec = spec_from_file(os.path.join(SPECS, "02-flow.json"))
        xml = build(spec)
        result = layout_of(spec)
        rects = node_rects(xml)
        node_id = next(iter(result.placed))
        dx = rects[node_id][0] - result.placed[node_id].x
        dy = rects[node_id][1] - result.placed[node_id].y
        edges = [cell for cell in cells(xml) if cell.get("edge")]
        self.assertEqual(len(edges), len(result.edges))
        for edge, cell in zip(result.edges, edges):
            geometry = cell.find("mxGeometry")
            assert geometry is not None
            points = [(_num(point, "x"), _num(point, "y"))
                      for point in geometry.iter("mxPoint")]
            expected = [(round(x + dx, 2), round(y + dy, 2))
                        for x, y in edge["points"][1:-1]]
            self.assertEqual(points, expected, f"边 {_attr(cell, 'id')} 的折点对不上")

    def test_regions_encloses_members_and_do_not_overlap(self):
        """区域框真的包住成员 —— **从文件读**，不看内存里的中间量。"""
        spec = spec_from_file(os.path.join(SPECS, "07-regions.json"))
        xml = build(spec)
        rects, regions = node_rects(xml), region_rects(xml)
        member_of: dict[str, list[str]] = {}
        for node in spec["nodes"]:
            if node.get("group"):
                member_of.setdefault(node["group"], []).append(node["id"])
        self.assertTrue(member_of, "夹具里应该有分组")
        for group_id, members in member_of.items():
            for member in members:
                self.assertTrue(
                    inside(rects[member], regions[group_id]),
                    f"节点 {member} 不在区域 {group_id} 里："
                    f"{rects[member]} vs {regions[group_id]}")
        keys = list(regions)
        for index, left in enumerate(keys):
            for right in keys[index + 1:]:
                a, b = regions[left], regions[right]
                overlap = (a[0] < b[0] + b[2] and b[0] < a[0] + a[2]
                           and a[1] < b[1] + b[3] and b[1] < a[1] + a[3])
                self.assertFalse(overlap, f"区域 {left} 与 {right} 重叠了")

    def test_group_style_reaches_the_file(self):
        """`groups[].style` 必须落到文件里。

        这条有来历：`layout.region_boxes` 曾经把 `style` 漏传出去 —— 规格里写了、
        校验通过、出图却**静默无效**（实测那个 `dashed` 根本没生效）。
        """
        spec = spec_from_file(os.path.join(SPECS, "07-regions.json"))
        found = by_id(build(spec))
        self.assertIn("dashed=1", _attr(found["region-boot"], "style"))
        self.assertIn("dashed=1", _attr(found["region-guard"], "style"))
        stripped = json.loads(json.dumps(spec))
        for group in stripped["groups"]:
            group.pop("style", None)
        stripped["style"]["stroke"] = "solid"
        quiet = by_id(build(stripped))
        self.assertIn("dashed=0", _attr(quiet["region-boot"], "style"))


class TestEdges(unittest.TestCase):
    def test_edge_refs_point_at_existing_nodes(self):
        for path in FIXTURES:
            with self.subTest(fixture=os.path.basename(path)):
                xml = build(spec_from_file(path))
                known = set(node_rects(xml))
                for cell in cells(xml):
                    if not cell.get("edge"):
                        continue
                    self.assertIn(_attr(cell, "source")[2:], known)
                    self.assertIn(_attr(cell, "target")[2:], known)

    def test_endpoint_fractions_are_in_range(self):
        """drawio 的 exit/entry 是 0..1 的比例；越界会让箭头贴到别处。"""
        for path in FIXTURES:
            with self.subTest(fixture=os.path.basename(path)):
                for cell in cells(build(spec_from_file(path))):
                    if not cell.get("edge"):
                        continue
                    for chunk in _attr(cell, "style").split(";"):
                        key, _, raw = chunk.partition("=")
                        if key in ("exitX", "exitY", "entryX", "entryY"):
                            self.assertGreaterEqual(float(raw), 0.0, chunk)
                            self.assertLessEqual(float(raw), 1.0, chunk)

    def test_edge_direction_follows_the_spec(self):
        """`from`/`to` 是规格写的方向，不因为内部绕线而反过来。"""
        spec = spec_of(["a", "b"], [("b", "a")])
        edge = [cell for cell in cells(build(spec)) if cell.get("edge")][0]
        self.assertEqual(_attr(edge, "source"), "n-b")
        self.assertEqual(_attr(edge, "target"), "n-a")

    def test_default_kind_is_solid_and_async_is_dashed(self):
        spec = spec_of(["a", "b", "c"], [("a", "b"), ("b", "c", {"kind": "async"})])
        edges = [cell for cell in cells(build(spec)) if cell.get("edge")]
        self.assertIn("dashed=0", _attr(edges[0], "style"))
        self.assertIn("dashed=1", _attr(edges[1], "style"))


class TestLabels(unittest.TestCase):
    def test_xml_escaping_round_trips(self):
        """`<` `&` `"` 必须能原样读回来。

        这里也顺带钉住那个真事故：`<br>` 要写成 `&lt;br&gt;` —— 裸 `<` 在 XML
        属性里非法，整份文件**打不开**（不是"画得不对"）。
        """
        spec = spec_of(["a"], [], nodes=[{"id": "a", "kind": "service",
                                          "label": 'A<B & "C" > D'}])
        xml = build(spec)
        self.assertNotIn('value="A<B', xml)
        # 断言要拿**原始 XML 文本**看转义：`cell.get(...)` 读出来的已经被 ElementTree
        # 解开了（所以才会看到 `<`）—— 第一版弄反了，断言一直红。
        self.assertIn("&lt;", xml)
        self.assertIn("&amp;", xml)
        self.assertEqual(value_lines(by_id(xml)["n-a"]), ['A<B & "C" > D'])

    def test_labels_use_our_line_breaks(self):
        """断行来自**我们**（`&lt;br&gt;` 钉死），不许让 drawio 再折一次。

        顺便记一条实测结论：节点标签超过约 24 字会自动折成 2 行，而同一次测量又被
        `too_long_for_largest` 判成「标签太长」（阻塞，建议改短）。所以这套设计里真正的
        多行文字来自三处：**显式换行**、`detail` 那一行、区域标题。这条用例钉显式换行。
        """
        spec = spec_of(["a"], [], nodes=[{"id": "a", "kind": "service",
                                          "label": "第一行\n第二行"}])
        xml = build(spec)
        self.assertIn("&lt;br&gt;", xml, "换行要写成转义过的 <br>")
        self.assertEqual(value_lines(by_id(xml)["n-a"]), ["第一行", "第二行"])

    def test_detail_is_drawn_at_normal_and_kind_hint_only_at_diagnostic(self):
        """`detail` 在默认档就画（`shows_node_detail`：只有 executive 才挑挑捡捡），
        而自动补的 kind 中文说明**只在诊断档**出现。这两件事经常被混为一谈。
        """
        spec = spec_of(["a", "b"], [("a", "b", {"kind": "async"})],
                       nodes=[{"id": "a", "kind": "service", "label": "甲",
                               "detail": "补充说明"},
                              {"id": "b", "kind": "service", "label": "乙"}])
        plain = build(spec)
        self.assertIn("补充说明", plain, "默认档就该画 detail")
        self.assertNotIn("异步", plain, "默认档不该自动补 kind 说明")
        spec["detail"] = "diagnostic"
        self.assertIn("异步", build(spec), "诊断档要补上非默认 kind 的中文说明")

    def test_executive_drops_detail_and_edge_labels(self):
        """executive = 摘要：非重点节点的 detail 丢掉（重点的留），用户写的边标签也丢掉。"""
        spec = spec_of(["a", "b"], [("a", "b", {"label": "用户写的标签", "kind": "data"})],
                       nodes=[{"id": "a", "kind": "service", "label": "甲",
                               "detail": "重点说明", "emphasis": "primary"},
                              {"id": "b", "kind": "service", "label": "乙",
                               "detail": "次要说明", "emphasis": "normal"}])
        full = build(spec)
        self.assertIn("用户写的标签", full)
        self.assertIn("重点说明", full)
        self.assertIn("次要说明", full)
        spec["detail"] = "executive"
        summary = build(spec)
        self.assertNotIn("用户写的标签", summary, "摘要不堆边标签")
        self.assertNotIn("次要说明", summary, "摘要只留重点节点的说明")
        self.assertIn("重点说明", summary, "重点节点的说明要留下")

    def test_user_label_wins_over_auto_kind_label(self):
        spec = spec_of(["a", "b"], [("a", "b", {"kind": "async", "label": "消息"})],
                       detail="diagnostic")
        edge = [cell for cell in cells(build(spec)) if cell.get("edge")][0]
        self.assertEqual(_attr(edge, "value"), "消息")
        self.assertNotIn("异步", _attr(edge, "value"))


class TestCrossBackendAgreement(unittest.TestCase):
    """两个后端必须画出**同一套文字**。

    「几何与判据只有一份」这句话光靠代码结构保不住（谁都能在那边拼一个临时字符串），
    所以拿同一份规格出两张图，逐行比文字。本轮就是这样发现 Excalidraw 侧把 `detail`
    单独成块、而 drawio 侧拼进同一个 cell 的 —— 那是**可接受的差异**（渲染器不同），
    但必须"逐行相等"才行：不能多一行，也不能少一行。
    """

    def _lines(self, xml: str) -> list[str]:
        """文件里出现的**所有文字行**（节点/标题/区域标题 + **边标签**）。

        ⚠️ 边标签在这边是**边 cell 自己的 value**，不是单独的元素 —— 所以这里必须连
        `edge=1` 的 cell 一起收。第一版只看 `vertex=1`，于是每张图都少了几行
        （`HTTPS`、`失败`、`异步 / 事件`……），看起来像“drawio 后端丢了标签”，
        其实是比较器自己少看了东西。
        """
        lines: list[str] = []
        for _cid, element in identity(xml):
            inner = _inner(element)
            if inner.get("vertex") or inner.get("edge"):
                lines += [line for line in value_lines(element) if line != ""]
        return sorted(lines)

    def _scene_lines(self, spec: dict) -> list[str]:
        scene, _result, outcome, _attempts = E.emit(spec)
        assert scene, [i.line() for i in outcome.blocking]
        lines: list[str] = []
        for element in scene["elements"]:
            if element.get("type") == "text" and element.get("text"):
                lines += [line for line in element["text"].split("\n") if line != ""]
        return sorted(lines)

    def test_text_lines_match_excalidraw_backend(self):
        for path in FIXTURES:
            with self.subTest(fixture=os.path.basename(path)):
                spec = spec_from_file(path)
                self.assertEqual(self._lines(build(spec)), self._scene_lines(spec))

    def test_text_lines_match_at_diagnostic_level(self):
        """诊断档最容易分叉（两边各有自己的"补说明"逻辑）。"""
        for path in FIXTURES:
            with self.subTest(fixture=os.path.basename(path)):
                spec = spec_from_file(path)
                spec["detail"] = "diagnostic"
                self.assertEqual(self._lines(build(spec)), self._scene_lines(spec))


class TestRefusesToDoWrongThings(unittest.TestCase):
    def test_every_shape_has_a_drawio_mapping(self):
        """形状映射表与 `shapes.SHAPES` 必须**一一对应**。

        少一个键的后果是那张图的某个节点直接报错 —— 所以宁可在这里就红，
        也不要在用户已经给了图之后才发现。
        """
        self.assertEqual(set(shapes.SHAPES), set(D.SHAPE_STYLE))

    def test_unknown_region_level_is_refused(self):
        region = {"id": "g", "label": "区", "level": "purple", "x": 0, "y": 0,
                  "width": 10, "height": 10, "label_lines": ["区"],
                  "label_width": 10, "label_height": 10, "label_x": 5, "label_y": 0}

        class _Frame:
            def x(self, value: float) -> float:
                return value

            def y(self, value: float) -> float:
                return value

        with self.assertRaises(D.SpecError) as caught:
            D.region_cells(region, None, _Frame())
        self.assertIn("level", str(caught.exception))

    def test_icons_fail_loudly(self):
        """图标是 P2。**报错**，不是悄悄丢掉一个视觉元素。"""
        spec = spec_of(["a", "b"], [("a", "b")],
                       nodes=[{"id": "a", "kind": "service", "label": "甲",
                               "icon": "postgres"},
                              {"id": "b", "kind": "service", "label": "乙"}])
        with self.assertRaises(D.SpecError) as caught:
            D.emit(spec)
        self.assertIn("图标", str(caught.exception))

    def test_invalid_spec_is_refused_before_layout(self):
        spec = {"type": "architecture", "direction": "LR",
                "nodes": [{"id": "a", "kind": "service", "label": "甲"},
                          {"id": "a", "kind": "service", "label": "重复 id"}],
                "edges": []}
        with self.assertRaises(D.SpecError) as caught:
            D.emit(spec)
        self.assertIn("规格不通过", str(caught.exception))

    def test_non_numeric_edge_points_are_refused(self):
        """上游给了坏坐标要**当场报错**，不许把 NaN 写进文件。

        写进去的后果不是“画得不对”：NaN 的元素在 drawio 里点不中、也看不见。
        （原来这条测的是“结构自检会拦住 NaN”，但自检只看几何、不看 style 字符串 ——
        拦住它的是 `as_float` 这道闸，所以用例改成直接量那道闸。）
        """
        node = lambda x: L.Placed(id="x", x=x, y=0.0, width=10.0, height=10.0, rank=0)
        placed = {"a": node(0.0), "b": node(100.0)}
        edge = {"from": "a", "to": "b", "points": [(0.0, 0.0), ("左边一点", 5.0)]}
        with self.assertRaises(D.SpecError) as caught:
            D.edge_path(edge, placed)
        self.assertIn("不是数", str(caught.exception))


class TestCli(unittest.TestCase):
    def test_writes_file_and_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec_path = os.path.join(tmp, "订单图.json")
            with open(spec_path, "w", encoding="utf-8") as handle:
                json.dump(spec_from_file(FIXTURES[0]), handle, ensure_ascii=False)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = D.main([spec_path])
            self.assertEqual(code, 0)
            # 默认输出名 = 规格文件名换后缀（只换最后一节，`a.diagram.json` → `a.diagram.drawio`）
            target = os.path.join(tmp, "订单图.drawio")
            self.assertTrue(os.path.exists(target))
            # 比的是文件名：临时目录在 macOS 上是 `/var/...` 而真实路径是 `/private/var/...`,
            # 拿整个路径比会因为一个符号链接红掉（和被测代码没关系）。
            self.assertIn("订单图.drawio", out.getvalue())
            with open(target, encoding="utf-8") as handle:
                self.assertEqual(C.check_text(handle.read()), [])

    def test_stdout_mode_writes_nothing_to_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec_path = os.path.join(tmp, "s.json")
            with open(spec_path, "w", encoding="utf-8") as handle:
                json.dump(spec_from_file(FIXTURES[0]), handle, ensure_ascii=False)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = D.main([spec_path, "--stdout"])
            self.assertEqual(code, 0)
            self.assertIn("<mxfile", out.getvalue())
            self.assertEqual(os.listdir(tmp), ["s.json"])

    def test_missing_spec_exits_two(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = D.main(["/nonexistent/x.json"])
        self.assertEqual(code, 2)
        self.assertIn("读不到规格", err.getvalue())

    def test_broken_spec_writes_no_file_and_no_stdout(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec_path = os.path.join(tmp, "bad.json")
            with open(spec_path, "w", encoding="utf-8") as handle:
                handle.write('{"type": "architecture", "direction": "LR", '
                             '"nodes": [], "edges": [{"from": "x", "to": "y"}]}')
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = D.main([spec_path, "--stdout"])
            self.assertEqual(code, 1)
            self.assertEqual(out.getvalue(), "", "失败时不许往 stdout 写半个文件")
            self.assertEqual(os.listdir(tmp), ["bad.json"], "失败时不许落盘")

    def test_structural_check_failure_blocks_the_write(self):
        """**这条测的是守门人本身**：把转义改坏（= 生成一份打不开的文件），
        emit 必须在写之前拦住它，目录里什么都不许多出来。
        """

        def _no_escape(_text: object) -> str:
            return ""       # 什么都不转义：`<` 会原样进属性

        original = D.escape_xml
        # 用 setattr 打补丁：动态加载出来的模块，静态检查认不出它有哪些属性
        setattr(D, "escape_xml", _no_escape)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                spec_path = os.path.join(tmp, "s.json")
                with open(spec_path, "w", encoding="utf-8") as handle:
                    json.dump(spec_from_file(FIXTURES[0]), handle, ensure_ascii=False)
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    code = D.main([spec_path])
                self.assertEqual(code, 1)
                self.assertIn("结构自检", err.getvalue())
                self.assertEqual(os.listdir(tmp), ["s.json"])
        finally:
            setattr(D, "escape_xml", original)

    def test_blocking_layout_writes_no_file(self):
        """布局有阻塞项时也不落盘（`emit` 那条早退分支）。"""

        class _Issue:
            def __str__(self) -> str:
                return "假的阻塞项（测试用）"

        class _Outcome:
            blocking = [_Issue()]
            issues = [_Issue()]

        real = D._load_sibling("check_layout")
        original = real.layout_with_retry

        def _fake(_spec: dict, _boxes: dict, _params: dict | None):
            return (None, _Outcome(), [])

        real.layout_with_retry = _fake
        try:
            with tempfile.TemporaryDirectory() as tmp:
                spec_path = os.path.join(tmp, "s.json")
                with open(spec_path, "w", encoding="utf-8") as handle:
                    json.dump(spec_from_file(FIXTURES[0]), handle, ensure_ascii=False)
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    code = D.main([spec_path])
                self.assertEqual(code, 1)
                self.assertIn("阻塞项", err.getvalue())
                self.assertEqual(os.listdir(tmp), ["s.json"])
        finally:
            real.layout_with_retry = original


class TestSchemesAndPlatform(unittest.TestCase):
    """配色方案 + 平台适配（图层/锁定/编辑数据/白底/多页）。

    这些都在**真实 app.diagrams.net 里看过**（2026-09-14）：图层面板里出现「区域与标题（锁定）」
    并带锁图标、区域渲染在节点下面、底部页签可切、等宽标签不溢出。
    这里的用例钉的是“别再改回没图层/没 id/没背景那个样子”。
    """

    def _spec(self) -> dict:
        return spec_from_file(os.path.join(SPECS, "07-regions.json"))

    def test_default_scheme_is_engineering_and_uses_offset_font(self):
        xml = build(self._spec())
        self.assertIn('background="#FFFFFF"', xml, "白底要显式写")
        self.assertIn("fontFamily=Courier New", xml)
        # 等宽字体配了缩小比例（16 → 14），否则标签会顶出框
        self.assertIn("fontSize=14", xml)

    def test_scheme_changes_the_palette(self):
        spec = self._spec()
        engineering = build(spec)
        classic = build(spec, scheme="classic")
        self.assertNotEqual(engineering, classic)
        self.assertIn("fontFamily=Helvetica", classic, "classic 用比例字体")
        # 深色方案连页面底色一起变
        night = build(spec, scheme="night")
        self.assertIn('background="#0D1117"', night)

    def test_unknown_scheme_is_refused(self):
        with self.assertRaises(KeyError):
            build(self._spec(), scheme="花哨")

    def test_regions_live_on_a_locked_layer(self):
        """区域在**独立图层**上并锁住 —— 没做之前它们是普通单元，拖歪了就散了。"""
        xml = build(self._spec())
        cells = by_id(xml)
        layer = cells["2"]
        self.assertIn("区域", _attr(layer, "value"))
        self.assertEqual(_attr(layer, "parent"), "0", "图层是 root 的直接子元素")
        for region_id in ("region-boot", "region-guard", "region-label-boot"):
            self.assertEqual(_attr(cells[region_id], "parent"), "2", region_id)
            self.assertIn("locked=1", _attr(cells[region_id], "style"), region_id)
            self.assertIn("movable=0", _attr(cells[region_id], "style"), region_id)

    def test_nodes_are_user_objects_with_data(self):
        """`<UserObject>` 带 tooltip 与自定义属性（将来读回改过的文件的锚点）。"""
        xml = build(self._spec())
        node = by_id(xml)["n-load"]
        self.assertEqual(node.tag, "UserObject")
        self.assertEqual(_attr(node, "node_id"), "load")
        self.assertTrue(_attr(node, "kind"))
        self.assertTrue(_attr(node, "level"))
        inner = node.find("mxCell")
        assert inner is not None
        self.assertIsNone(inner.get("id"), "身份只能有一处：内层不许再带 id")
        self.assertEqual(inner.get("vertex"), "1")

    def test_detail_level_also_gates_the_tooltip(self):
        """`detail: executive` 是对信息量的明示 —— 不能从悬停里把它漏出去。"""
        spec = spec_of(["a"], [], nodes=[{"id": "a", "kind": "service", "label": "甲",
                                          "detail": "次要说明", "emphasis": "normal"}])
        spec["detail"] = "executive"
        self.assertNotIn("tooltip=", build(spec))
        spec["detail"] = "standard"      # `detail` 的合法值是 standard，不是 normal
        self.assertIn('tooltip="次要说明"', build(spec))

    def test_preview_has_one_page_per_scheme(self):
        """`scheme_preview`：**一页一套**，给用户切页签挑 —— 这是“先问”那一步的载体。"""
        preview = D._load_sibling("scheme_preview")
        xml = preview.build()
        self.assertEqual(xml.count("<diagram "), len(D.palette.available_schemes()))
        self.assertEqual(C.check_text(xml), [])
        for name in D.palette.available_schemes():
            self.assertIn(f"（{name}）", xml, f"页签名要写清是哪套：{name}")

    def test_preview_can_be_limited_to_a_few_schemes(self):
        preview = D._load_sibling("scheme_preview")
        xml = preview.build(schemes=["classic", "print"])
        self.assertEqual(xml.count("<diagram "), 2)
        self.assertNotIn("（night）", xml)

    @staticmethod
    def _spec_with_accent() -> dict:
        """带一个 `emphasis: primary` 节点的规格 —— 只有它才会用到 accent 那个种子色。

        （第一版拿 07-regions 当夹具，而它一个重点节点都没有，于是种子色根本没被渲染，
        断言“找不到 #0B5FFF”就红了 —— 是**夹具选错**，不是覆盖没生效。）
        """
        return spec_of(["a", "b"], [("a", "b")], nodes=[
            {"id": "a", "kind": "service", "label": "重点", "emphasis": "primary"},
            {"id": "b", "kind": "service", "label": "普通"}])

    def test_seed_overrides_one_color_on_top_of_a_scheme(self):
        """“用 classic，但主色换成品牌蓝”—— 只动他说的那一个，其余照方案。"""
        spec = self._spec_with_accent()
        plain = build(spec, scheme="classic")
        branded = build(spec, scheme="classic", seeds={"accent": "#0B5FFF"})
        self.assertIn("#0B5FFF", branded)
        self.assertNotIn("#0B5FFF", plain)
        # “只动他说的那一个”：classic 原来的强调色必须消失（而这个规格里
        # 没有警示节点，所以别拿 critical 的色值去断言 —— 它压根不会被渲染）
        self.assertIn("#2563EB", plain)
        self.assertNotIn("#2563EB", branded)
        self.assertIn("#374151", branded, "没点名的 ink 照旧")

    def test_bad_seed_is_refused(self):
        spec = self._spec_with_accent()
        with self.assertRaises(KeyError):
            D.emit(spec, seeds={"brand": "#0B5FFF"})       # 没有这个种子键
        with self.assertRaises(KeyError):
            D.emit(spec, seeds={"accent": "蓝色"})          # 不是 #RRGGBB

    def test_seed_flag_from_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec_path = os.path.join(tmp, "s.json")
            with open(spec_path, "w", encoding="utf-8") as handle:
                json.dump(self._spec_with_accent(), handle, ensure_ascii=False)
            with contextlib.redirect_stdout(io.StringIO()):
                code = D.main([spec_path, "--scheme", "classic", "--seed", "accent=#0B5FFF"])
            self.assertEqual(code, 0)
            with open(os.path.join(tmp, "s.drawio"), encoding="utf-8") as handle:
                self.assertIn("#0B5FFF", handle.read())
            # 写法不对要当场说清楚，而不是默默忽略
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(D.main([spec_path, "--seed", "乱写"]), 2)
            self.assertIn("键=#RRGGBB", err.getvalue())

    def test_multi_page_writes_one_file_with_n_pages(self):
        first = spec_from_file(os.path.join(SPECS, "01-architecture.json"))
        second = self._spec()
        pages = [D.build_page(first, layout_of(first), D.L.boxes_from_spec(first)),
                 D.build_page(second, layout_of(second), D.L.boxes_from_spec(second))]
        xml = D.build_file(pages)
        self.assertEqual(xml.count("<diagram "), 2)
        self.assertEqual(xml.count("<mxGraphModel"), 2, "每页各自一套模型（页尺寸/背景各算）")
        self.assertEqual(C.check_text(xml), [])

    def test_multi_page_cli_needs_an_explicit_output(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = D.main([FIXTURES[0], FIXTURES[1]])
        self.assertEqual(code, 2)
        self.assertIn("-o", err.getvalue())

    def test_multi_page_cli_writes_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "book.drawio")
            with contextlib.redirect_stdout(io.StringIO()):
                code = D.main([FIXTURES[0], FIXTURES[1], "-o", out])
            self.assertEqual(code, 0)
            with open(out, encoding="utf-8") as handle:
                text = handle.read()
            self.assertEqual(text.count("<diagram "), 2)
            self.assertEqual(C.check_text(text), [])

    def test_scheme_flag_from_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec_path = os.path.join(tmp, "s.json")
            with open(spec_path, "w", encoding="utf-8") as handle:
                json.dump(self._spec(), handle, ensure_ascii=False)
            with contextlib.redirect_stdout(io.StringIO()):
                code = D.main([spec_path, "--scheme", "print"])
            self.assertEqual(code, 0)
            with open(os.path.join(tmp, "s.drawio"), encoding="utf-8") as handle:
                self.assertIn("fontFamily=Helvetica", handle.read())


if __name__ == "__main__":
    unittest.main()
