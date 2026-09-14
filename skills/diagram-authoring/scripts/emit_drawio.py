#!/usr/bin/env python3
"""规格 → `.drawio`（mxGraph XML，**不压缩**）。

为什么要第二个后端
------------------
同一份 `*.diagram.json`（只有结构、没有坐标）现在有两种落笔：

- `emit_excalidraw.py` → `.excalidraw`：手绘感，在 Obsidian 里就地编辑
- 本文件 → `.drawio`：要发出去的交付件，能在 draw.io / app.diagrams.net 里打开、
  导出 PNG/SVG/PDF，也能用厂商标框图库

**几何全部复用**：`validate_spec` / `layout` / `check_layout` / `text_metrics` /
`shapes` / `palette` 一行没改 —— 这一层只做 mxGraph 的序列化。所以两个后端的排版
是**同一份推导**，不会出现「改了一个后端、另一个还按旧规矩画」。

四件必须记住的事
----------------
1. **不压缩**。draw.io 应用保存时默认把 `<diagram>` 的内容 deflate+base64 压成一串
   （2014 年起），人能读但没法 diff。程序生成必须写纯 XML。
2. **`<root>` 里必须先有 `id="0"` 与 `id="1"` 两个结构 cell** —— 少了打不开。
3. **顺序就是层叠顺序**：区域先进（背景），节点其次，边最后。和 Excalidraw 那边同一条规矩。
4. **不写 `modified` 时间戳**。写进去的话「同一份规格重复生成」每次都是一个不同的文件，
   于是这套东西最有用的一条性质（幂等、可 diff、能被测试钉住）当场没了。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from typing import Any


def _load_sibling(name: str):
    """动态加载同目录脚本（`scripts/` 不是包）。同一个模块只加载一次。"""
    key = f"_drawio_{name}"
    loaded = sys.modules.get(key)
    if loaded is not None:
        return loaded
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{name}.py")
    spec = importlib.util.spec_from_file_location(key, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


L = _load_sibling("layout")
palette = _load_sibling("palette")
shapes = _load_sibling("shapes")
tm = _load_sibling("text_metrics")

XML_DECL = '<?xml version="1.0" encoding="UTF-8"?>\n'
PAGE_PAD = 24.0          # 画布四周留白：内容平移到这里开始
PAGE_WIDTH = 1169.0      # 内容比 A4 横版还大时的兜底页宽（drawio 的默认值）
PAGE_HEIGHT = 826.0
EDGE_STROKE_WIDTH = 2
# `<root>` 的三个结构 cell：
#   id="0"  图本身（必须有）
#   id="2"  **区域图层**。声明在默认图层**之前** —— drawio 的图层按声明顺序叠，
#           先声明的在下。区域是背景，必须在节点下面；而把节点写在区域之后
#           已经不够了：一旦分了图层，层序就压过单元顺序。
#   id="1"  默认图层（节点 / 边 / 图标题）
ROOT_CELL = ('        <mxCell id="0" />\n'
             '        <mxCell id="2" value="区域与标题（锁定）" parent="0" />\n'
             '        <mxCell id="1" parent="0" />')
REGION_LAYER = "2"


class SpecError(Exception):
    """规格或流水线不通过 —— 不写文件。"""


# ── 形状 → drawio style ───────────────────────────────────────────
#
# 这是本文件**唯一**需要新定的封闭集合：`shapes.SHAPES` 里的语义形状名
# （矩形 / 圆角 / 胶囊 / 椭圆 / 菱形 / 圆柱 / 便签）映射到 drawio 的 style 片段。
# 没映射到的形状**直接报错**，不 fallback 成矩形 —— 静默换形状比报错难查得多。
SHAPE_STYLE: dict[str, str] = {
    "rect": "",
    "round": "rounded=1",
    "capsule": "rounded=1;arcSize=50",
    "ellipse": "ellipse",
    "diamond": "rhombus",
    "cylinder": "shape=cylinder3;boundedLbl=1;backgroundOutline=1;size=12",
    "note": "shape=note;size=12;align=left;verticalAlign=top;spacingLeft=8;spacingTop=6",
}

# 强调档 → 线宽。drawio 的 strokeWidth 是数值；Excalidraw 那边是 1/1.5/2 的花样，
# 这里取整数档（同一条语义轴，两边的画法各自适配自己的渲染器）。
EMPHASIS_STROKE_WIDTH = {"muted": 1, "normal": 2, "primary": 3}


def escape_xml(text: object) -> str:
    """XML 文本属性转义。`&` 必须先换，否则会把后面造出来的实体再转一次。"""
    out = str(text if text is not None else "")
    out = out.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return out.replace('"', "&quot;").replace("'", "&#39;")


def label_value(lines: Any) -> str:
    """把**我们自己算好的折行**变成 drawio 的 value。

    为什么用显式 `<br>` 而不是交给 drawio 的 `whiteSpace=wrap` 再折一次：
    盒子尺寸本来就是按我们这份折行量出来的；交给 drawio 再折一遍，两边断行点不一样时
    字就压出框 —— 而「框与字对不上」正是这个 skill 反复吃过的那类亏。
    同一件几何量两遍必然漂移，所以**只量一遍**。

    ⚠️ 折行符要写成 `&lt;br&gt;`：这个 HTML 是放在 **XML 属性**里的，
    裸 `<` 会让整份文件解析失败（「打不开」而不是「画得不对」）。
    第一版就是裸 `<br>`，被 `check_drawio` 当场拦住 —— 那个自检存在的理由就是这个。
    """
    return "&lt;br&gt;".join(escape_xml(line) for line in lines if line != "")


def as_float(value: object, what: str) -> float:
    """折点坐标必须是数。上游给了坏数据就当场说清，别让它变成 NaN 写进文件。"""
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise SpecError(f"{what} 不是数：{value!r}") from exc


def stable_id(raw: str) -> str:
    """由内容派生的稳定 id：同一份规格重复生成，字节要一致（测试会断言）。"""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _cell(cell_id: str, value: str, style: str, geometry: str,
          *, vertex: bool = True, edge: bool = False,
          source: str | None = None, target: str | None = None,
          parent: str = "1") -> str:
    attrs = [f'id="{escape_xml(cell_id)}"', f'value="{value}"',
             f'style="{escape_xml(style)}"']
    if vertex:
        attrs.append('vertex="1"')
    if edge:
        attrs.append('edge="1"')
    if source:
        attrs.append(f'source="{escape_xml(source)}"')
    if target:
        attrs.append(f'target="{escape_xml(target)}"')
    attrs.append(f'parent="{escape_xml(parent)}"')
    return (f"        <mxCell {' '.join(attrs)}>\n"
            f"          {geometry}\n"
            f"        </mxCell>")


def _rect_geometry(x: float, y: float, width: float, height: float) -> str:
    return (f'<mxGeometry x="{round(x, 2)}" y="{round(y, 2)}" '
            f'width="{round(width, 2)}" height="{round(height, 2)}" as="geometry" />')


class Frame:
    """把画布坐标平移到 (PAGE_PAD, PAGE_PAD) 起，并记下内容的边界。

    为什么要平移：布局给的坐标是「相对自己的原点」的，可能负、也可能离原点很远。
    不平移的话 `<mxfile>` 的页尺寸要么裁掉内容、要么大得离谱 —— 而文件里到处是绝对坐标，
    与其在每处判正负，不如一开始就统一一次。

    `extra` 是标题那类**不属于布局**但要占画布的矩形：不算进来的话，标题会被页边裁掉。
    """

    def __init__(self, result: Any, regions: list[dict],
                 extra: list[tuple[float, float, float, float]] | None = None) -> None:
        rects = [(p.x, p.y, p.width, p.height) for p in result.placed.values()]
        rects += [(r["x"], r["y"], r["width"], r["height"]) for r in regions]
        rects += list(extra or [])
        self.min_x = min((r[0] for r in rects), default=0.0)
        self.min_y = min((r[1] for r in rects), default=0.0)
        self.max_x = max((r[0] + r[2] for r in rects), default=0.0)
        self.max_y = max((r[1] + r[3] for r in rects), default=0.0)
        self.dx = PAGE_PAD - self.min_x
        self.dy = PAGE_PAD - self.min_y
        self.width = self.max_x - self.min_x
        self.height = self.max_y - self.min_y

    def x(self, value: float) -> float:
        return value + self.dx

    def y(self, value: float) -> float:
        return value + self.dy

    def point(self, xy: tuple[float, float]) -> tuple[float, float]:
        return (self.x(xy[0]), self.y(xy[1]))


def node_cell(node: dict, placed, box, detail_level: str | None,
              frame: Frame) -> str:
    """一个节点 = 一个 `<UserObject>` 包着一个 mxCell（形状与文字都在里面）。

    文字用**我们量好的折行**（见 `label_value`）；`detail` 行按 layout 那份判据决定
    要不要画 —— 和 Excalidraw 后端同一个判据，两边的信息量必须一致。

    **为什么要 `<UserObject>`**：drawio 的“编辑数据”与悬停提示都存在它上面
    （这是官方格式，不是我们的发明）。存了它才有两件事：

    - 悬停看得到 `detail` 与角色信息（图面不必为了“可追溯”而堆字）；
    - 将来“读回用户改过的 .drawio”（P1）有**锚点** —— 否则只能靠标签字符串
      去猜哪个框原来是哪个节点。
    """
    kind = node.get("kind")
    emphasis = node.get("emphasis", palette.DEFAULT_EMPHASIS)
    shape_name = box.shape
    if shape_name not in SHAPE_STYLE:
        raise SpecError(
            f"节点 {node.get('id')!r} 的形状 {shape_name!r} 还没有 drawio 映射；"
            f"已有的：{'、'.join(sorted(SHAPE_STYLE))}")

    knobs = palette.knobs()
    text = box.text
    lines = list(text.lines)
    shown_detail = bool(node.get("detail")) and L.shows_node_detail(node, detail_level)
    if shown_detail:
        # detail 是次要说明：drawio 一个 cell 只有一档字号，所以这里同字号换行，
        # 不像 Excalidraw 那样单独一块小字。见 references/drawio-backend.md。
        lines += list(text.detail_lines)

    parts = [_shape_style(shape_name, knobs), "whiteSpace=wrap", "html=1",
             f"fillColor={palette.fill_for(kind, emphasis)}",
             f"strokeColor={palette.stroke_for(kind, emphasis)}",
             f"strokeWidth={EMPHASIS_STROKE_WIDTH.get(emphasis, 2)}",
             f"fontSize={round(text.font_size * knobs['font_scale'])}",
             f"fontFamily={knobs['font_family']}"]
    if shapes.stroke_style_for(shape_name) == "dashed":
        parts.append("dashed=1")
    cell_style = ";".join(part for part in parts if part)

    geometry = _rect_geometry(frame.x(placed.x), frame.y(placed.y),
                              placed.width, placed.height)
    return _user_object(
        f"n-{node['id']}", label_value(lines),
        # tooltip 拿 `detail`，但**档位说了不画就不放** —— `detail: executive`
        # 是用户对信息量的明示，不能从悬停里把它漏出去（声明了就得算数）。
        # 没 detail 时**不写 tooltip 属性**：那样 drawio 悬停会显示自定义属性
        # （“编辑数据”那几项），正好是“这个框是谁”这个问题的答案。
        tooltip=str(node.get("detail") or "") if shown_detail else "",
        props={"node_id": node["id"], "kind": str(kind),
               "group": str(node.get("group") or ""),
               "emphasis": str(emphasis),
               "level": palette.level_for(kind, emphasis)},
        style=cell_style, geometry=geometry)


def _shape_style(shape_name: str, knobs: dict) -> str:
    """形状 → drawio style，并把**方案的圆角**接进去。

    `round` 的圆角幅度是方案的一部分（经典企业扁平 4%、工程文档风 8%、黑白/蓝图 0%）——
    所以不能像第一版那样把它写死在 `SHAPE_STYLE` 里。胶囊的 `arcSize=50`（两端半圆）
    是**形状身份**而不是风格，不跟着方案走。
    """
    base = SHAPE_STYLE[shape_name]
    if not base.startswith("rounded=1"):
        return base
    arc = knobs.get("arc") or 0          # `knobs()` 保证这里是 int（方案自己的数）
    if arc <= 0:
        return base.replace("rounded=1", "rounded=0") if "arcSize" not in base else base
    if shape_name == "capsule":
        return base                      # 胶囊的两端半圆不跟方案走
    return f"rounded=1;arcSize={arc}"


def _user_object(cell_id: str, label: str, *, tooltip: str, props: dict[str, str],
                 style: str, geometry: str) -> str:
    """drawio 的 `<UserObject>`：自带 id / label / tooltip 与自定义属性。

    ⚠️ 被它包住的 `<mxCell>` **不能再带 id** —— 身份在 UserObject 上。
    （官方格式如此；两个都带 id 会让 drawio 把图看成两个东西。）
    """
    attrs = [f'id="{escape_xml(cell_id)}"', f'label="{label}"']
    if tooltip:
        attrs.append(f'tooltip="{escape_xml(tooltip)}"')
    attrs += [f'{key}="{escape_xml(value)}"' for key, value in props.items() if value]
    return (f"        <UserObject {' '.join(attrs)}>\n"
            f'          <mxCell style="{escape_xml(style)}" vertex="1" parent="1">\n'
            f"          {geometry}\n"
            f"          </mxCell>\n"
            f"        </UserObject>")


def region_cells(region: dict, style: dict | None, frame: Frame,
                 parent: str = "1") -> list[str]:
    """一个区域 = 背景矩形 + 一个居中的标题 cell。

    标题用 `layout` 算好的那几样（折行 / 尺寸 / 位置），**不在这里重新量一遂** ——
    标题带的高度本来就是按那几个数算出来的，重量一次就可能对不上。

    区域是**背景装饰**，所以放在独立图层上并锁住（`parent` 指向那个图层）——
    手工编辑时最容易被拖歪的就是它们，而拖歪了整张图就散了。
    """
    level = region.get("level", "tint")
    if level not in palette.LEVELS:
        raise SpecError(f"区域 {region['id']!r} 的 level 不认识：{level!r}"
                        f"（可用 {sorted(palette.LEVELS)}；未知值判失败，不 fallback）")
    knobs = palette.knobs()
    resolved = palette.merge_style(palette.resolve_style(style), region.get("style"))
    # 圆角/虚实都走 palette 那两个解析器，判据与 Excalidraw 后端**逐字一致**：
    # 区域在那边默认是圆的（`corners: shape` → 形状默认 `{"type": 3}`），
    # 只有显式 `corners: sharp` 才是直角。第一版我硬写了 `rounded=0`，等于把默认值改掉。
    rounded = palette.roundness_of(resolved, {"type": 3}) is not None
    dashed = palette.stroke_style_of(resolved, "solid") == "dashed"
    arc = knobs.get("arc") or 0          # `knobs()` 保证这里是 int（方案自己的数）
    corner = f"rounded=1;arcSize={max(arc, 2)}" if (rounded and arc > 0) else "rounded=0"
    rect_style = ";".join([
        corner,
        "whiteSpace=wrap", "html=1",
        # 锁定：区域框是背景，拖歪了整张图就散了。`locked` 是 mxGraph 的样式键。
        "locked=1", "movable=0", "resizable=0", "editable=0",
        f"fillColor={palette.LEVELS[level]['fill']}",
        f"strokeColor={palette.frame_stroke(level)}",
        "strokeWidth=1",
        f"dashed={'1' if dashed else '0'}",
    ])
    cells = [_cell(f"region-{region['id']}", "", rect_style,
                   _rect_geometry(frame.x(region["x"]), frame.y(region["y"]),
                                  region["width"], region["height"]),
                   parent=parent)]
    if region.get("label"):
        label_style = ";".join([
            "text", "html=1", "align=center", "verticalAlign=middle",
            "strokeColor=none", "fillColor=none",
            "locked=1", "movable=0", "resizable=0", "editable=0",
            # 标题的颜色走**层级描边色**（和 Excalidraw 后端同一个取值），
            # 不加粗 —— 那边的视觉重量来自字号（20，比节点大一步）与颜色，不是粗体。
            f"fontColor={palette.LEVELS[level]['stroke']}",
            f"fontSize={round(region.get('label_size', L.REGION_LABEL_SIZE) * knobs['font_scale'])}",
            f"fontFamily={knobs['font_family']}",
        ])
        width = region["label_width"]
        cells.append(_cell(
            f"region-label-{region['id']}", label_value(list(region["label_lines"])),
            label_style,
            _rect_geometry(frame.x(region["label_x"] - width / 2.0),
                           frame.y(region["label_y"]), width,
                           region["label_height"]),
            parent=parent))
    return cells


def endpoint_fraction(point: tuple[float, float], placed) -> tuple[float, float]:
    """端点落在盒子的哪个比例位置（drawio 的 exitX/exitY 就是这么算的）。"""
    fx = (point[0] - placed.x) / placed.width if placed.width else 0.5
    fy = (point[1] - placed.y) / placed.height if placed.height else 0.5
    return (min(max(fx, 0.0), 1.0), min(max(fy, 0.0), 1.0))


def edge_path(edge: dict, placed: dict) -> tuple[str, str, tuple, tuple, list]:
    """把一条边的折线拆成 drawio 要的形状：源、目标、出口比例、入口比例、中间折点。

    **端点归属靠测量，不靠 `reversed` 标记**：折线是从哪个盒子上出来的，量一下就知道。
    信一个可能被上游改动的布尔量，出问题时很难查。
    """
    raw = edge.get("points") or []
    pts = [(as_float(x, f"边 {edge.get('from')}→{edge.get('to')} 的折点 x"),
            as_float(y, f"边 {edge.get('from')}→{edge.get('to')} 的折点 y"))
           for x, y in raw]
    if len(pts) < 2:
        raise SpecError(f"边 {edge.get('from')}→{edge.get('to')} 的折线少于两个点")
    src, dst = edge["from"], edge["to"]

    def dist(point: tuple[float, float], node: str) -> float:
        p = placed[node]
        cx, cy = p.x + p.width / 2.0, p.y + p.height / 2.0
        return (point[0] - cx) ** 2 + (point[1] - cy) ** 2

    if dist(pts[0], src) > dist(pts[0], dst):        # 折线是反着走的
        pts = list(reversed(pts))
    return (src, dst,
            endpoint_fraction(pts[0], placed[src]),
            endpoint_fraction(pts[-1], placed[dst]),
            pts[1:-1])


def edge_label(edge: dict, detail_level: str | None) -> str | None:
    """边上的字。判据与 Excalidraw 后端**逐条一致**：

    - `executive` 档丢掉用户写的标签（摘要不堆细节）
    - `diagnostic` 档给非默认 kind 的边补上中文说明（虚线看不出是异步还是可选）
    - 默认 kind（同步调用）不补 —— 实线加箭头方向已经说明了，再写一遍是零信息量
    """
    if not L.shows_edge_label(edge, detail_level):
        return None
    if edge.get("label"):
        return str(edge["label"])
    return edge_kind_label(edge, detail_level)


def edge_kind_label(edge: dict, level: str | None) -> str | None:
    """与 `emit_excalidraw.edge_kind_label` 同一条规则（这里单独实现，避免后端互相 import）。"""
    if level != "diagnostic":
        return None
    kind = edge.get("kind") or palette.DEFAULT_EDGE_KIND
    if kind == palette.DEFAULT_EDGE_KIND:
        return None
    return palette.EDGE_KINDS.get(kind, {}).get("zh")


def edge_cell(edge: dict, index: int, placed: dict,
              detail_level: str | None, frame: Frame) -> str:
    src, dst, (ex, ey), (nx, ny), inner = edge_path(edge, placed)
    kind = edge.get("kind") or palette.DEFAULT_EDGE_KIND
    spec = palette.EDGE_KINDS.get(kind, palette.EDGE_KINDS[palette.DEFAULT_EDGE_KIND])
    label = edge_label(edge, detail_level)

    knobs = palette.knobs()
    style_parts = [
        "edgeStyle=orthogonalEdgeStyle", "rounded=0", "html=1",
        f"endArrow={knobs.get('arrow') or 'classic'}", "endFill=1",
        f"strokeColor={spec['stroke']}",
        f"strokeWidth={knobs.get('edge_width') or EDGE_STROKE_WIDTH}",
        f"dashed={'1' if spec['style'] == 'dashed' else '0'}",
    ]
    if label:
        style_parts += [f"fontSize={round(12 * (knobs.get('font_scale') or 1.0))}",
                        f"fontFamily={knobs['font_family']}",
                        f"labelBackgroundColor={palette.CANVAS['background']}"]
    else:
        style_parts.append("noLabel=1")
    style_parts += [
        f"exitX={round(ex, 4)}", f"exitY={round(ey, 4)}", "exitPerimeter=0",
        f"entryX={round(nx, 4)}", f"entryY={round(ny, 4)}", "entryPerimeter=0",
    ]
    if inner:
        moved = [frame.point(point) for point in inner]
        points = "".join(f'<mxPoint x="{round(x, 2)}" y="{round(y, 2)}" />'
                         for x, y in moved)
        geometry = ('<mxGeometry relative="1" as="geometry">'
                    f'<Array as="points">{points}</Array></mxGeometry>')
    else:
        geometry = '<mxGeometry relative="1" as="geometry" />'

    return _cell(f"e-{index}", label_value([label]) if label else "", ";".join(style_parts),
                 geometry, vertex=False, edge=True,
                 source=f"n-{src}", target=f"n-{dst}")


def content_bounds(result: Any, regions: list[dict]) -> tuple[float, float, float, float]:
    """内容的包围盒（只算布局的东西，不算标题）。标题要靠它居中、要靠它往上让。"""
    rects = [(p.x, p.y, p.width, p.height) for p in result.placed.values()]
    rects += [(r["x"], r["y"], r["width"], r["height"]) for r in regions]
    if not rects:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(r[0] for r in rects), min(r[1] for r in rects),
            max(r[0] + r[2] for r in rects), max(r[1] + r[3] for r in rects))


def title_rect(title: str | None, bounds: tuple[float, float, float, float]
               ) -> tuple[float, float, float, float] | None:
    """图标题的矩形：居中于内容上方，离内容顶边 `L.TITLE_GAP`。

    **与 Excalidraw 后端同一条算法、同一个常数、同一份字号**（见 `layout.TITLE_GAP`）。
    标题不参与布局，y 可以是负的。
    """
    if not title:
        return None
    box = tm.measure(title, "", font_size=tm.FONT_TITLE)
    lines = list(box.lines)
    width = max([tm.weighted_units(line) for line in lines] or [0.0]) * tm.FONT_TITLE
    height = len(lines) * tm.FONT_TITLE * tm.LINE_HEIGHT
    left, top, right = bounds[0], bounds[1], bounds[2]
    return (left + (right - left) / 2.0 - width / 2.0,
            top - L.TITLE_GAP - height, width, height)


def title_cell(title: str, rect: tuple[float, float, float, float],
               frame: Frame) -> str:
    """标题是一个**自由文字** cell（不属于任何形状）。

    ⚠️ 必须画在画布上，不能只写进 `<diagram name=...>` —— 那只是页签的名字，
    导出的 PNG/PDF 上根本没有它。跨后端一致性测试就是这么发现本文件漏了标题的：
    Excalidraw 侧 6/6 张图都有标题，drawio 侧一张都没有。
    """
    box = tm.measure(title, "", font_size=tm.FONT_TITLE)
    knobs = palette.knobs()
    style = ";".join([
        "text", "html=1", "align=center", "verticalAlign=middle",
        "strokeColor=none", "fillColor=none",
        # 锁住：标题是 chrome，被拖歪了很难发现（但保持可编辑 —— 改字是正当需求）
        "locked=1", "movable=0", "resizable=0",
        f"fontColor={palette.CANVAS['text']}",
        f"fontSize={round(tm.FONT_TITLE * (knobs.get('font_scale') or 1.0))}",
        f"fontFamily={knobs['font_family']}",
    ])
    return _cell("diagram-title", label_value(list(box.lines)), style,
                 _rect_geometry(frame.x(rect[0]), frame.y(rect[1]),
                                rect[2], rect[3]))


def build_page(spec: dict, result: Any, boxes: dict,
               detail_level: str | None = None) -> str:
    """一页 = 一个 `<diagram>` 块（含它自己的 mxGraphModel）。

    页尺寸与背景都是**每页各算**的 —— 多页文件里每张图的宽高差很远，
    共用一套页尺寸会让每页都留一大片空白。
    """
    style = palette.resolve_style(spec.get("style"))
    level = detail_level if detail_level is not None else spec.get("detail", L.DEFAULT_DETAIL)
    regions = L.region_boxes(spec, result.placed, boxes)
    title = spec.get("title")
    rect = title_rect(title, content_bounds(result, regions))
    frame = Frame(result, regions, [rect] if rect else [])

    by_id = {node["id"]: node for node in spec.get("nodes", [])}
    body: list[str] = []
    # 区域先进：drawio 里**后面的元素压在前面的上面**，所以背景必须先写。
    for region in regions:
        body += region_cells(region, style, frame, parent=REGION_LAYER)
    for node_id, placed in result.placed.items():
        if node_id not in by_id:
            continue          # 虚节点（为折线插入的），drawio 里不需要画出来
        body.append(node_cell(by_id[node_id], placed, boxes[node_id], level, frame))
    for index, edge in enumerate(result.edges):
        body.append(edge_cell(edge, index, result.placed, level, frame))
    if rect and title:
        # 标题最后加：和 Excalidraw 侧一样画在最上层（它是 chrome，不是内容）
        body.append(title_cell(title, rect, frame))

    page_width = max(PAGE_WIDTH, frame.width + PAGE_PAD * 2)
    page_height = max(PAGE_HEIGHT, frame.height + PAGE_PAD * 2)
    model = (
        '        <mxGraphModel dx="800" dy="600" grid="0" gridSize="10" guides="1" '
        'tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" '
        f'pageWidth="{round(page_width)}" pageHeight="{round(page_height)}" '
        f'background="{palette.CANVAS["background"]}" '
        'math="0" shadow="0">\n'
        "          <root>\n"
        f"{ROOT_CELL}\n"
        + "\n".join(body) + "\n"
        "          </root>\n"
        "        </mxGraphModel>"
    )
    # 页签名：没写 title 就退到图型名（drawio 的页签总得有个名字）。
    page_name = str(title or spec.get("type") or "diagram")
    diagram_id = stable_id(page_name + json.dumps(sorted(by_id), ensure_ascii=False))
    return (f'  <diagram id="{diagram_id}" name="{escape_xml(page_name)}">\n'
            f"{model}\n"
            "  </diagram>")


def build_file(pages: list[str]) -> str:
    """把 N 页拼成一个 `.drawio`。

    **一个文件多页**是 draw.io 的原生能力（底部一排页签，像 Excel 的工作表）：
    十张图一个文件，比十个文件好用得多；导出时还能选整本或只导当前页。
    """
    body = "\n".join(pages)
    return (XML_DECL
            + '<mxfile host="diagram-authoring" agent="diagram-authoring" '
              'version="24.0.0" type="device">\n'
            + f"{body}\n"
            + "</mxfile>\n")


def build_model(spec: dict, result: Any, boxes: dict,
                detail_level: str | None = None) -> str:
    """单页文件的便捷入口（= `build_file([build_page(...)])`）。"""
    return build_file([build_page(spec, result, boxes, detail_level)])


def emit_page(spec: dict, *, params: dict | None = None,
              scheme: str | None = None) -> tuple[str, Any, Any, list]:
    """跑完整条流水线并返回 XML。**校验有阻塞项就不出图。**

    顺序与 Excalidraw 后端**逐条一致**（validate → layout → check → 落笔）：
    出图是最后一步，前一步不过就不该走到这里。
    """
    validator = _load_sibling("validate_spec")
    report = validator.validate(spec)
    if getattr(report, "errors", None):
        detail = "\n".join(f"  - {e.line() if hasattr(e, 'line') else e}"
                           for e in report.errors)
        raise SpecError(f"规格不通过，没有出图：\n{detail}")

    # **选后端 = 选画法**：Excalidraw 走方向系统（手绘 + 植物/杂志…那五套），
    # drawio 走自己的配色方案（4 个种子色 + 交付件配比）。两者共用的是**语义档位**。
    palette.use_backend("drawio", scheme=scheme, mood=spec.get("mood"),
                        visual=spec.get("visual"))

    icons_used = [n["id"] for n in spec.get("nodes", []) if n.get("icon")]
    if icons_used:
        raise SpecError(
            f"drawio 后端还不支持图标（用到的节点：{'、'.join(icons_used[:5])}）。"
            "图标要映射到 drawio 的 image/custom shape，属于 P2；"
            "先用 Excalidraw 后端出这张图，或者把 icon 去掉。")

    boxes = L.boxes_from_spec(spec)
    result, outcome, attempts = _load_sibling("check_layout").layout_with_retry(
        spec, boxes, params)
    if outcome.blocking:
        return "", result, outcome, attempts
    return build_page(spec, result, boxes), result, outcome, attempts


def emit(spec: dict, *, params: dict | None = None,
         scheme: str | None = None) -> tuple[str, Any, Any, list]:
    """单份规格 → 整个 `.drawio` 文件（一页）。多份请用 `build_file` 拼。"""
    page, result, outcome, attempts = emit_page(spec, params=params, scheme=scheme)
    return (build_file([page]) if page else ""), result, outcome, attempts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="规格 → .drawio（不压缩的 mxGraph XML；多份规格 = 多页）")
    ap.add_argument("spec", nargs="+",
                    help="一份或多份 *.diagram.json（多份 = 一个文件多页）")
    ap.add_argument("-o", "--out", help="输出路径（单份时默认与规格同名，后缀 .drawio）")
    ap.add_argument("--scheme",
                    help="配色方案（默认 " + palette.DEFAULT_SCHEME + "）；可选："
                         + "、".join(palette.available_schemes()))
    ap.add_argument("--stdout", action="store_true", help="打到标准输出，不写文件")
    args = ap.parse_args(argv)

    if len(args.spec) > 1 and not args.out:
        print("多份规格要显式指定 -o：页数多了之后，用第一份的名字当输出名会很难预料",
              file=sys.stderr)
        return 2

    pages: list[str] = []
    node_total = edge_total = 0
    for path in args.spec:
        try:
            with open(path, encoding="utf-8") as fh:
                spec = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"读不到规格 {path}：{exc}", file=sys.stderr)
            return 2
        try:
            page, _result, outcome, attempts = emit_page(spec, scheme=args.scheme)
        except (SpecError, KeyError) as exc:
            print(f"{path}：{exc}", file=sys.stderr)
            return 1
        if outcome.blocking:
            print(f"✗ {path} 的布局有阻塞项，没有出图（试了 {len(attempts)} 组参数）：",
                  file=sys.stderr)
            for issue in outcome.issues:
                print(f"  - {issue}", file=sys.stderr)
            return 1
        pages.append(page)
        node_total += len(spec.get("nodes", []))
        edge_total += len(spec.get("edges", []))

    xml = build_file(pages)

    checker = _load_sibling("check_drawio")
    problems = checker.check_text(xml)
    if problems:
        print("✗ 生成的 XML 没过结构自检（这是 bug，请报出来）：", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    if args.stdout:
        sys.stdout.write(xml)
        return 0

    out = args.out or (os.path.splitext(args.spec[0])[0] + ".drawio")
    try:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(xml)
    except OSError as exc:
        print(f"写不了 {out}：{exc}", file=sys.stderr)
        return 1
    nodes = node_total
    page_note = f"{len(pages)} 页 / " if len(pages) > 1 else ""
    print(f"✓ 已写出 {out}（{page_note}{nodes} 个节点 / {edge_total} 条边 / "
          f"{len(xml.splitlines())} 行 XML，配色 {args.scheme or palette.DEFAULT_SCHEME}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
