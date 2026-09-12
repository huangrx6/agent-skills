#!/usr/bin/env python3
"""规格 + 布局 → `.excalidraw`（plain JSON 场景）。

## 为什么是 `.excalidraw` 而不是 `.excalidraw.md`

Obsidian 的 Excalidraw 插件把 `.excalidraw.md` 里的场景压成 **lz-string**（实测插件
`main.js` 里有 24 处 `LZString`、`compressToBase64` / `compressToUint8Array` / `compressToUTF16`）——
**lz-string 没有 stdlib Python 等价物**，用它意味着要手抄一份 JS 的压缩算法，或者引依赖。

`*.excalidraw` 是普通 JSON，插件原生读写（同目录的 `my-obsidian-library.excalidrawlib`
就是 plain JSON）。所以本 skill 输出 plain JSON，不碰 lz-string。

## ⚠ 一处必须说清楚的限制：Excalidraw 会重新排版文字

`text_metrics` 的尺寸是我们对"文字占多大"的**推算**（按 Helvetica 实测的字符宽度表算，一律向上取整）。
但容器绑定的文字（`containerId`）在 Excalidraw 里是**由它自己按真实字体重新断行**的。

也就是说：**渲染器是第二个尺寸来源，而且不在我们控制之内。**
如果它的断行跟我们算的不一样（多一行），Excalidraw 会把容器撑高 —— 布局随之偏移，
间隙保证也就不再成立。

这不是猜测出来的隐患，是"同一份文字在两套字体度量下必然有偏差"的必然结果。
它只可能通过**看一张真实渲染的图**来发现，我没法靠本脚本自己验证。

所以：**规格与校验全绿不等于渲染出来就是那样。** 详见 `references/validation.md` 第六节。

## 确定性

同一份规格每次生成**字节相同**（seed 由元素 id 的 sha256 推出，不用随机数），
这样图能进 git、diff 有意义。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import sys
from typing import Any

SCENE_TYPE = "excalidraw"
SCENE_VERSION = 2
SOURCE = "excalidraw-diagram skill"
ELEMENT_VERSION = 1
STROKE_WIDTH = 2
ROUGHNESS = 1
TEXT_ALIGN = "center"
VERTICAL_ALIGN = "middle"
# 边标签与连线之间至少要留的空隙。太小会被线穿过（实测过：只上移一个字号时，
# 标签高 15px 而上移 12px，线正好从文字中间过）。
LABEL_GAP = 6.0
# Excalidraw 文本元素的 baseline（从文本块顶部到首行基线的距离）。
# 容器绑定的文字在加载时由 Excalidraw 重算，这里给一个合理初值即可。
BASELINE_RATIO = 0.875
_ID_SAFE = re.compile(r"[^A-Za-z0-9_-]+")


def _load_sibling(name: str):
    """动态加载同目录脚本（`scripts/` 不是包，同级 import 在静态层面无法解析）。

    必须把模块注册进 sys.modules 之后再 exec，否则被加载模块里的 `@dataclass` 会炸。
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{name}.py")
    mod_spec = importlib.util.spec_from_file_location(f"_diagram_{name}", path)
    if mod_spec is None or mod_spec.loader is None:
        raise RuntimeError(f"加载不了同目录模块：{path}")
    module = importlib.util.module_from_spec(mod_spec)
    sys.modules[mod_spec.name] = module
    mod_spec.loader.exec_module(module)
    return module


L = _load_sibling("layout")
palette = _load_sibling("palette")
tm = _load_sibling("text_metrics")
shapes = _load_sibling("shapes")


def _stable_int(key: str, salt: str = "") -> int:
    """由字符串推出稳定的伪随机整数。不用 random —— 否则每次生成的文件都不一样，
    图就没法进 git、diff 也没意义。"""
    digest = hashlib.sha256(f"{salt}\x00{key}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def _eid(kind: str, raw: str, index: int = 0) -> str:
    safe = _ID_SAFE.sub("-", str(raw)).strip("-") or "x"
    return f"{kind}-{safe}-{index}" if index else f"{kind}-{safe}"


def _base(el_id: str, el_type: str, x: float, y: float, w: float, h: float,
          stroke: str, background: str, *, stroke_style: str = "solid",
          roundness: dict | None = None, stroke_width: float = STROKE_WIDTH,
          extra: dict | None = None) -> dict:
    """所有元素共有的字段。字段集照 Excalidraw 的 `_ExcalidrawElementBase` 来。"""
    el = {
        "id": el_id,
        "type": el_type,
        "x": round(x, 2),
        "y": round(y, 2),
        "width": round(w, 2),
        "height": round(h, 2),
        "angle": 0,
        "strokeColor": stroke,
        "backgroundColor": background,
        "fillStyle": "solid",
        "strokeWidth": stroke_width,
        "strokeStyle": stroke_style,
        "roughness": ROUGHNESS,
        "opacity": 100,
        "groupIds": [],
        "frameId": None,
        "roundness": roundness,
        "seed": _stable_int(el_id, "seed"),
        "version": ELEMENT_VERSION,
        "versionNonce": _stable_int(el_id, "nonce"),
        "isDeleted": False,
        "boundElements": None,
        "updated": 1,
        "link": None,
        "locked": False,
        "index": None,
    }
    if extra:
        el.update(extra)
    return el


# ── 节点：矩形 + 容器绑定的文字 ─────────────────────────────
def node_elements(node: dict, placed, box, arrows_out: list[str],
                    arrows_in: list[str]) -> list[dict]:
    nid = node["id"]
    shape_id = _eid("node", nid)
    title_id = _eid("title", nid)
    detail_id = _eid("detail", nid)
    has_detail = bool(node.get("detail"))
    text = box.text          # 形状包围盒里面的文字信息（见 layout.NodeBox）

    bound = [{"type": "text", "id": title_id}]
    if has_detail:
        bound.append({"type": "text", "id": detail_id})
    bound += [{"type": "arrow", "id": a} for a in arrows_out + arrows_in]

    kind = node.get("kind")
    emphasis = node.get("emphasis", palette.DEFAULT_EMPHASIS)
    stroke = palette.stroke_for(kind)
    fill = palette.emphasis_fill(kind, emphasis)
    stroke_width = palette.emphasis_stroke_width(emphasis)
    elements = shape_elements(shape_id, box.shape, placed, stroke, fill,
                              stroke_width=stroke_width)
    # 文字与箭头都绑到**主体**那个元素上；圆柱的顶盖只是一个装饰性叠加
    elements[0]["boundElements"] = bound

    # 文字在**形状里能放字的那块区域**居中（不是在整个包围盒里居中）——
    # 圆柱要下沉一个盖高，否则标题会压在椭圆盖上。
    inner_y, inner_h = text_band(box.shape, placed)
    title_h = len(text.lines) * tm.FONT_NODE * tm.LINE_HEIGHT
    detail_h = len(text.detail_lines) * tm.FONT_DETAIL * tm.LINE_HEIGHT
    top = inner_y + (inner_h - (title_h + detail_h)) / 2.0
    content_w = text.break_units * tm.FONT_NODE
    tx = placed.x + (placed.width - content_w) / 2.0    # 形状内水平居中

    elements.append(_text_block(title_id, shape_id, text.lines, tx, top,
                                content_w, tm.FONT_NODE))
    if has_detail:
        elements.append(_text_block(detail_id, shape_id, text.detail_lines, tx,
                                    top + title_h, content_w, tm.FONT_DETAIL))
    return elements


def text_band(shape_name: str, placed) -> tuple[float, float]:
    """形状里“能放文字的那一条带”的 (顶边, 高)。"""
    if shape_name == "cylinder":
        cap = shapes.cylinder_cap(placed.width)
        return placed.y + cap, placed.height - cap
    return placed.y, placed.height


def shape_elements(element_id: str, shape_name: str, placed,
                   stroke: str, fill: str,
                   stroke_width: float = STROKE_WIDTH) -> list[dict]:
    """按形状建元素。除圆柱外都是一个元素。

    **圆柱刻意让柱体跨满整个包围盒**，而不是“柱体在下半、盖子在右上”：
    柱体就是箭头与文字绑定的主体，它的包围盒必须等于整个盒子，
    否则箭头会连到柱体上、看起来像“连到了下半截”。
    顶盖椭圆只是叠在上面的装饰（元素顺序 = 叠放顺序，它在后面所以在上）。
    """
    entry = shapes.SHAPES[shape_name]
    style = shapes.stroke_style_for(shape_name)
    if shape_name == "cylinder":
        cap = shapes.cylinder_cap(placed.width)
        body = _base(element_id, "rectangle", placed.x, placed.y, placed.width,
                     placed.height, stroke, fill, stroke_style=style,
                     roundness={"type": 3}, stroke_width=stroke_width)
        lid = _base(f"{element_id}-lid", "ellipse", placed.x, placed.y,
                    placed.width, cap, stroke, fill, stroke_width=stroke_width)
        # 顶盖与柱体成组：在 Excalidraw 里拖动时它们一起动（否则一拖就散开），
        # 同时这也是一个明确标记 —— “groupIds 非空的是装饰，不是节点”，
        # 校验/量图那边靠它区分顶盖与真节点。
        lid["groupIds"] = [element_id]
        return [body, lid]
    roundness = entry.get("roundness")
    if shape_name == "capsule":
        # Excalidraw 没有原生胶囊。type 2 是“按比例取半径”，0.5 就是高的一半 → 真正的胶囊。
        roundness = {"type": 2, "value": 0.5}
    return [_base(element_id, entry["excalidraw"], placed.x, placed.y,
                  placed.width, placed.height, stroke, fill,
                  stroke_style=style, roundness=roundness,
                  stroke_width=stroke_width)]


def _text_block(el_id: str, container_id: str, lines: tuple[str, ...],
                x: float, y: float, content_width: float, font_size: float) -> dict:
    """一个容器绑定的文字块。

    x/y 只是初值 —— Excalidraw 对 `containerId` 非空的文字会自己重算位置与换行（见模块顶部那条限制）。
    高度只由行数与字号决定。
    """
    text = "\n".join(lines)
    content_h = len(lines) * font_size * tm.LINE_HEIGHT
    el = _base(el_id, "text", x, y, content_width, content_h,
               palette.CANVAS["text"], "transparent", extra={"roundness": None})
    el.update({
        "text": text,
        "fontSize": font_size,
        "fontFamily": palette.CANVAS["font_family"],
        "textAlign": TEXT_ALIGN,
        "verticalAlign": VERTICAL_ALIGN,
        "containerId": container_id,
        "originalText": text,
        "lineHeight": tm.LINE_HEIGHT,
        "baseline": round(font_size * BASELINE_RATIO, 2),
        "strokeWidth": 1,
    })
    return el


# ── 边：箭头 ────────────────────────────────────────────────
def arrow_element(edge: dict, index: int) -> dict:
    pts = edge["points"]
    x0, y0 = pts[0]
    rel = [[round(px - x0, 2), round(py - y0, 2)] for px, py in pts]
    xs = [p[0] for p in rel]
    ys = [p[1] for p in rel]
    kind = edge.get("kind") or "sync"
    style = palette.EDGE_KINDS.get(kind, palette.EDGE_KINDS["sync"])

    el_id = _eid("edge", f"{edge['from']}-{edge['to']}", index)
    el = _base(el_id, "arrow", x0, y0, max(xs) - min(xs), max(ys) - min(ys),
               style["stroke"], "transparent", stroke_style=style["style"],
               roundness={"type": 2})
    el.update({
        "points": rel,
        "startArrowhead": None,
        "endArrowhead": "arrow",
        "startBinding": {"elementId": _eid("node", edge["from"]), "focus": 0, "gap": 4},
        "endBinding": {"elementId": _eid("node", edge["to"]), "focus": 0, "gap": 4},
    })
    return el


def polyline_midpoint(pts: list) -> list:
    """沿折线走**一半弧长**处的点 —— 也就是视觉上的中点。"""
    return _midpoint_frame(pts)[0]


def _midpoint_frame(pts: list, frac: float = 0.5) -> tuple[list, tuple[float, float], tuple[float, float]]:
    """折线上某个位置 + 该处的两个方向（反向的入边、出边）。

    两个方向都是相对“沿折线前进”而言的：`back` 指回到来处，`fwd` 指向前方。
    落在一条直段中间时两者共线（角平分退化，只能用法线）；
    落在拐点上时两者不同向 —— 那是真正需要区别对待的情况。

    `frac` 是沿**弧长**的比例，默认 0.5（中点）。之所以可调：标签本来就可以
    沿边滑动，死守中点会把“附近明明有位置”变成“只能压线”。
    """
    if not pts:
        return [0.0, 0.0], (-1.0, 0.0), (1.0, 0.0)
    if len(pts) < 2:
        return list(pts[0]), (-1.0, 0.0), (1.0, 0.0)
    segs = [(pts[i], pts[i + 1], math.dist(pts[i], pts[i + 1]))
            for i in range(len(pts) - 1)]
    total = sum(s[2] for s in segs)
    if total <= 0:
        return list(pts[0]), (-1.0, 0.0), (1.0, 0.0)
    half = total * frac
    walked = 0.0

    def _dir(seg):
        return (seg[1][0] - seg[0][0], seg[1][1] - seg[0][1])

    for i, (a, b, seg_len) in enumerate(segs):
        if walked + seg_len >= half:
            t = (half - walked) / seg_len if seg_len else 0.0
            point = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]
            this = _dir(segs[i])
            # 中点落在拐点上有**两种**到达方式，两种都必须认出：
            #   ① 落在本段终点（t≈1）→ 入边是本段，出边是下一段
            #   ② 落在本段起点且 i>0（t≈0）→ 入边是**上一段**，出边是本段
            #
            # ② 不是理论情况，实测真实发生过：两段**近似**等长（实测差约 1e-3 像素）时，
            # 中点会被算在第 1 段的 t≈0 处。那时若按“直段中间”处理，
            # back 与 fwd 会互为**精确反向** → 角平分线退化 → 只剩法线候选
            # → 标签必然压在自己的折线臂上（实测那条 b→d 的边压了 30 个采样点）。
            #
            # 判据是“到拐点的距离 < 半个像素”。这个阈值我前后改过三次，前两次都是猜的：
            #   ① `<= 1e-9`（到端点的**绝对距离**）→ 漏；
            #   ② `t <= 1e-6`（无量纲）→ 还是漏，实测偏差比它大一个量级。
            # 错的根源不是数字大小，是**猜** —— 根本不知道两段长度到底差多少。
            # 换成半个像素就不再依赖猜测：渲染分辨率是 1px，小于半像素的位置差在屏幕上
            # 不可分辨，在本项目尺度上也远小于任何布局阈值（最小间隙 12px）。
            # 要改这个数，依据得是分辨率或布局阈值，不能是为了让某张图好看。
            SUB_PIXEL = 0.5
            near_end = (1.0 - t) * seg_len <= SUB_PIXEL
            near_start = t * seg_len <= SUB_PIXEL
            if near_end and i + 1 < len(segs):
                return list(segs[i][1]), (-this[0], -this[1]), _dir(segs[i + 1])
            if near_start and i > 0:
                back = _dir(segs[i - 1])
                return list(segs[i][0]), (-back[0], -back[1]), this
            return point, (-this[0], -this[1]), this
        walked += seg_len
    a, b = segs[-1][0], segs[-1][1]
    return list(pts[-1]), (a[0] - b[0], a[1] - b[1]), (b[0] - a[0], b[1] - a[1])


def _unit(vector: tuple[float, float]) -> tuple[float, float] | None:
    length = math.hypot(*vector)
    return None if length <= 1e-9 else (vector[0] / length, vector[1] / length)


def _segment_enters_rect(a: tuple[float, float], b: tuple[float, float],
                         left: float, top: float, right: float, bottom: float) -> bool:
    """线段是否从矩形里穿过（密集采样，步长 0.5px）。

    用采样而不是精确求交：这条路径要在“搜一个干净位置”里被调用很多次，
    而正确的标准自带 ≥6px 的空白带 —— 0.5px 的采样误差在这个尺度下无关。
    搜索与守卫用例用**同一个步长**，两者不会结论不一。
    """
    steps = math.ceil(max(abs(b[0] - a[0]), abs(b[1] - a[1])) / 0.5) + 1
    for i in range(steps + 1):
        t = i / steps
        x, y = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        if left <= x <= right and top <= y <= bottom:
            return True
    return False


def _hits_lines(x: float, y: float, width: float, height: float,
                obstacles: list) -> bool:
    right, bottom = x + width, y + height
    for polyline in obstacles:
        for a, b in zip(polyline, polyline[1:]):
            if _segment_enters_rect(a, b, x, y, right, bottom):
                return True
    return False


def _candidate_directions(back: tuple[float, float],
                          fwd: tuple[float, float]) -> list[tuple[float, float]]:
    """标签可以往哪几个方向退。先试最合理的，再试备选。

    顺序刻意如此：
    1. **角平分线的外侧** —— 拐点处唯一正确的选择（用法线会有一半盖回入边）
    2. 出边的法线（朝上）—— 直线段的常规位置
    3. 出边的法线（朝下）
    4. 反向入边的两条法线 —— 拐点很尖时靠它绕到另一侧
    """
    out: list[tuple[float, float]] = []
    u, v = _unit(back), _unit(fwd)
    if u and v:
        bisector = _unit((-(u[0] + v[0]), -(u[1] + v[1])))
        if bisector:
            out.append(bisector)
    for base in (v, u):
        if not base:
            continue
        for n in ((-base[1], base[0]), (base[1], -base[0])):
            if n[1] <= 0 and n not in out:      # 优先朝上
                out.append(n)
    for base in (v, u):
        if not base:
            continue
        for n in ((-base[1], base[0]), (base[1], -base[0])):
            if n not in out:
                out.append(n)
    return out or [(0.0, -1.0)]


def label_position(pts: list, width: float, height: float,
                   obstacles: list | None = None,
                   gap: float = LABEL_GAP) -> tuple[float, float]:
    """找一个**不与任何连线相交**的标签位置 —— 由脚本自己搜，不靠一个魔法偏移量。

    为什么不能只算一个偏移量：

    1. 旧写法 `(mid.x + 6, mid.y - fontSize)` 只上移了一个字号（12px）而标签高 15px，
       线正好从文字中间穿过 —— 用户看到的“还是有遮挡”就是这个。
    2. 改成“沿法线退开”之后，**拐点**上仍然会盖：中点落在 V 形折线的顶点时，
       标签以顶点为中心，它有一半会压回入射那一段（实测：`长边` 标签的左半边被
       自己的入边穿过）。
    3. 而且标签还可能撞上**别的边**，那是单纯算自家法线永远避不开的。

    所以改成：按候选方向 × 递增退让量试位置，取第一个干净的。全都不干净时回到第一个
    候选（法线朝上）—— 那种情况说明图太密，应该由报告建议拆节点，而不是在这里硬拗。
    """
    obstacles = obstacles or [list(pts)]
    radius = math.hypot(width, height) / 2
    # 先试中点，不行再沿边滑 —— 标签本来就可以不在中点，
    # 而死守中点会把“附近明明有位置”变成“只能压线”。
    # 顺序是“离中点由近到远”，所以能用中点时一定用中点。
    first: tuple[float, float] | None = None
    for frac in (0.5, 0.42, 0.58, 0.34, 0.66, 0.26, 0.74):
        mid, back, fwd = _midpoint_frame(pts, frac)
        directions = _candidate_directions(back, fwd)
        for extra in (0.0, 6.0, 12.0, 20.0, 30.0, 45.0, 65.0):
            for dx, dy in directions:
                reach = radius + gap + extra
                x = mid[0] + dx * reach - width / 2
                y = mid[1] + dy * reach - height / 2
                if first is None:
                    first = (x, y)
                if not _hits_lines(x, y, width, height, obstacles):
                    return round(x, 2), round(y, 2)
    if first is None:                       # 理论上不可达（候选方向非空），但不靠 assert
        mid = _midpoint_frame(pts)[0]
        first = (mid[0] - width / 2, mid[1] - radius - gap - height / 2)
    return round(first[0], 2), round(first[1], 2)


def edge_label_element(edge: dict, index: int, obstacles: list | None = None) -> dict | None:
    """边标签：一个独立的文字元素，位置由 `label_position` 搜出来。

    刻意**不**绑到箭头上 —— 箭头标签在 Excalidraw 里有自己的定位规则，
    绑上去容易在编辑时漂移；独立元素至少位置是可预测的。

    `obstacles` 传**所有**边的折线，不只是自己那条 —— 标签撞上别的边同样是遮挡。
    """
    label = edge.get("label")
    if not label:
        return None
    width = round(tm.weighted_units(label) * tm.FONT_DETAIL, 2)
    height = round(tm.FONT_DETAIL * tm.LINE_HEIGHT, 2)
    x, y = label_position(edge["points"], width, height, obstacles)
    el_id = _eid("elabel", f"{edge['from']}-{edge['to']}", index)
    el = _base(el_id, "text", x, y, width, height,
               palette.CANVAS["text"], "transparent", extra={"roundness": None})
    el.update({
        "text": label,
        "fontSize": tm.FONT_DETAIL,
        "fontFamily": palette.CANVAS["font_family"],
        "textAlign": "center",
        "verticalAlign": "top",
        "containerId": None,
        "originalText": label,
        "lineHeight": tm.LINE_HEIGHT,
        "baseline": round(tm.FONT_DETAIL * BASELINE_RATIO, 2),
        "strokeWidth": 1,
    })
    return el


# ── 场景 ────────────────────────────────────────────────────
LINEAR_TYPES = {"arrow", "line"}


def element_bounds(el: dict) -> tuple[float, float, float, float]:
    """元素的真实包围盒 (left, top, right, bottom)。

    **线性元素不能用 `x + width`** —— 它的 `x`/`y` 是首点，折线点可以向左/向上
    伸出，所以必须从 `points` 算。

    这条是实测出来的：早期用 `x + width` 量图，得到 744px 的**幽灵空白** ——
    一个箭头让整张图的包围盒无端变宽，于是“图看着不对称”之类的结论全是错的。
    本函数就是那一份实现（`dev-tools/preview.py` 从这里 import，不存第二份）。
    """
    if el.get("type") in LINEAR_TYPES and el.get("points"):
        xs = [el["x"] + p[0] for p in el["points"]]
        ys = [el["y"] + p[1] for p in el["points"]]
        return min(xs), min(ys), max(xs), max(ys)
    return el["x"], el["y"], el["x"] + el["width"], el["y"] + el["height"]


def scene_bounds(elements: list[dict]) -> tuple[float, float, float, float]:
    boxes = [element_bounds(e) for e in elements]
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


# 标题底边到内容顶边的距离。数值来源：与最小元素间隙（12px）同量级再放大一档，
# 让标题与图之间看得出“这不是图的一部分”。**未经真实数据校准**，属于待验证。
TITLE_GAP = 28.0


def title_element(title: str | None) -> dict | None:
    """图标题。以前 `title` 字段被**完全忽略**（6/6 张图的标题都没画出来）。

    与节点文字不同，标题是**不绑定容器**的自由文字（`containerId = None`）——
    它不属于任何形状，所以 Excalidraw 不会自己重算它的位置，x/y 要算准。
    宽度用**实际行宽**而不是断行档位：档位是给容器用的，标题按档位宽算会
    把一个两字标题撑成 240px，白占画布。
    """
    if not title:
        return None
    box = tm.measure(title, "", font_size=tm.FONT_TITLE)
    lines = box.lines
    width = max(tm.weighted_units(line) for line in lines) * tm.FONT_TITLE
    height = len(lines) * tm.FONT_TITLE * tm.LINE_HEIGHT
    text = "\n".join(lines)
    return {
        "id": _eid("diagram-title", title),
        "type": "text",
        "x": 0.0,          # 居中放在 build_scene 里算（那里才知道内容多宽）
        "y": 0.0,
        "width": round(width, 2),
        "height": round(height, 2),
        "angle": 0,
        "strokeColor": palette.CANVAS["text"],
        "backgroundColor": "transparent",
        "fillStyle": "solid",
        "strokeWidth": 1,
        "strokeStyle": "solid",
        "roughness": ROUGHNESS,
        "opacity": 100,
        "groupIds": [],
        "frameId": None,
        "roundness": None,
        "seed": _stable_int("diagram-title", title),
        "version": ELEMENT_VERSION,
        "versionNonce": _stable_int("diagram-title-nonce", title),
        "isDeleted": False,
        "boundElements": None,
        "updated": 1,
        "link": None,
        "locked": False,
        "index": None,
        "text": text,
        "fontSize": tm.FONT_TITLE,
        "fontFamily": palette.CANVAS["font_family"],
        "textAlign": "center",
        "verticalAlign": "top",
        "containerId": None,
        "originalText": text,
        "lineHeight": tm.LINE_HEIGHT,
        "baseline": round(tm.FONT_TITLE * BASELINE_RATIO, 2),
    }


def build_scene(spec: dict, result, boxes: dict) -> dict:
    elements: list[dict] = []
    by_id = {n["id"]: n for n in spec.get("nodes", [])}

    arrows_out: dict[str, list[str]] = {nid: [] for nid in by_id}
    arrows_in: dict[str, list[str]] = {nid: [] for nid in by_id}
    arrow_specs: list[tuple[dict, str]] = []
    for i, edge in enumerate(result.edges):
        eid = _eid("edge", f"{edge['from']}-{edge['to']}", i)
        arrows_out.setdefault(edge["from"], []).append(eid)
        arrows_in.setdefault(edge["to"], []).append(eid)
        arrow_specs.append((edge, eid))

    for nid in by_id:
        placed = result.placed.get(nid)
        if placed is None:
            continue
        elements += node_elements(by_id[nid], placed, boxes[nid],
                                  arrows_out.get(nid, []), arrows_in.get(nid, []))

    # `result.edges` 里的 points **已经是绝对坐标**（`layout._points` 用的是 placed 的坐标），
    # 所以这里直接用，**不能再加一遍起点**。
    #
    # 以前写的是 `edge["points"][0] + p`，把一条真线平移成了另一条假线 ——
    # 标签搜索于是一直在躲不存在的障碍：它返回的位置在自己眼里是干净的，
    # 落到图上却压在真线上（实测某条边被压 19 个采样点）。
    # 这就是 P3“标签压线”反复修不掉的根因。
    polylines = [list(edge["points"]) for edge in result.edges]
    for i, (edge, _) in enumerate(arrow_specs):
        elements.append(arrow_element(edge, i))
        label = edge_label_element(edge, i, polylines)
        if label:
            elements.append(label)

    # 图标题最后加：它要按已排好的内容来居中，而它自己**不参与**布局。
    # 放的位置是“内容顶边往上 TITLE_GAP”，所以不需要把别的元素往下挪 ——
    # 标题可能落到 y 为负的地方，对 Excalidraw 没有影响（载入时会自动居中视图）。
    title = title_element(spec.get("title"))
    if title is not None and elements:
        left, top, right, _bottom = scene_bounds(elements)
        title["x"] = round(left + (right - left) / 2.0 - title["width"] / 2.0, 2)
        title["y"] = round(top - TITLE_GAP - title["height"], 2)
        elements.append(title)

    return {
        "type": SCENE_TYPE,
        "version": SCENE_VERSION,
        "source": SOURCE,
        "elements": elements,
        "appState": {
            "gridSize": None,
            "viewBackgroundColor": palette.CANVAS["background"],
        },
        "files": {},
    }


class SpecError(ValueError):
    """规格本身不合法 —— 出图之前就该拦住它。

    为什么不让它半路崩：`boxes_from_spec` 要先定形状才能算尺寸，而形状要读 kind；
    kind 写错时它会报一个误导性的错（实测：“未知 shape: None”）。
    所以 emit 先跑一遍 `validate_spec`，把真正的病因说清楚。

    以前 emit **根本不调用 validate_spec** —— 文档写着“先校验规格再出图”，
    但实际靠调用方自觉；调用方忘了就会在半路崩。
    """


def emit(spec: dict, *, params=None) -> tuple[dict, Any, Any, list]:
    """跑完整条流水线并返回场景。**校验有阻塞项就不出图。**

    顺序刻意是 validate → layout → check → emit：出图是最后一步，
    前一步不过就不该走到这里。跳过校验直接出图，等于把“不重叠/不溢出”的保证丢掉。
    """
    validator = _load_sibling("validate_spec")
    report = validator.validate(spec)
    if getattr(report, "errors", None):
        detail = "\n".join(f"  - {e.line() if hasattr(e, 'line') else e}"
                           for e in report.errors)
        raise SpecError(f"规格不通过，没有出图：\n{detail}")

    boxes = L.boxes_from_spec(spec)
    result, outcome, attempts = _check_layout().layout_with_retry(spec, boxes, params)
    if outcome.blocking:
        return {}, result, outcome, attempts
    return build_scene(spec, result, boxes), result, outcome, attempts


def _check_layout():
    return _load_sibling("check_layout")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="规格 → .excalidraw（plain JSON）")
    ap.add_argument("spec", help="*.diagram.json")
    ap.add_argument("-o", "--out", help="输出路径（默认与规格同名，后缀 .excalidraw）")
    ap.add_argument("--stdout", action="store_true", help="打到标准输出，不写文件")
    args = ap.parse_args(argv)

    try:
        with open(args.spec, encoding="utf-8") as fh:
            spec = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"读不到规格：{exc}", file=sys.stderr)
        return 2

    try:
        scene, result, outcome, attempts = emit(spec)
    except SpecError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"布局失败：{exc}", file=sys.stderr)
        return 1
    except KeyError as exc:
        print(f"规格里有个值不认识：{exc}", file=sys.stderr)
        return 1

    if not scene:
        print("校验有阻塞项，不出图：", file=sys.stderr)
        print(_check_layout().format_report(spec, attempts, outcome), file=sys.stderr)
        return 1

    payload = json.dumps(scene, ensure_ascii=False, indent=2)
    if args.stdout:
        print(payload)
        return 0

    out = args.out or os.path.splitext(args.spec)[0] + ".excalidraw"
    try:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(payload + "\n")
    except OSError as exc:
        print(f"写不了 {out}：{exc}", file=sys.stderr)
        return 2
    n_nodes = len(result.real_nodes())
    print(f"✓ {out}  （{n_nodes} 个节点 / {len(result.edges)} 条边 / "
          f"{len(scene['elements'])} 个元素 / 交叉 {result.crossings}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
