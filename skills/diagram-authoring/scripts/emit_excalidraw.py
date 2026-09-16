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
SOURCE = "diagram-authoring skill"
ELEMENT_VERSION = 1
STROKE_WIDTH = 2
ROUGHNESS = 1
TEXT_ALIGN = "center"
VERTICAL_ALIGN = "middle"
# 边标签与连线之间至少要留的空隙。太小会被线穿过（实测过：只上移一个字号时，
# 标签高 15px 而上移 12px，线正好从文字中间过）。
LABEL_GAP = 6.0
NODE_WEIGHT = 10.0      # 标签打分时“压到节点”相对于“压到线”的权。
                        # 线从字上穿过还看得清，字压在框上就分不清这行字属于谁了 ——
                        # 所以兜底选“最不脏”的时候，先避开框。
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
icons = _load_sibling("icons")
sigils = _load_sibling("sigils")


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
          # 默认 solid 而不是 hachure：**文字与箭头也走这里**，它们没有填充，
          # 继承一个"斜条纹"只会让产物里多一堆无意义的字段（Excalidraw 自己的
          # 文字元素就是 solid）。真正的填充档位由 shape_elements / region_elements
          # 显式传进来 —— 那两处才是"用户能选的填充"。
          fill_style: str = "solid", roughness: int = ROUGHNESS,
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
        "fillStyle": fill_style,
        "strokeWidth": stroke_width,
        "strokeStyle": stroke_style,
        "roughness": roughness,
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
                    arrows_in: list[str], icon_src: list | None = None,
                    icon_height: float | None = None,
                    style: dict | None = None,
                    detail_level: str | None = None) -> list[dict]:
    nid = node["id"]
    shape_id = _eid("node", nid)
    title_id = _eid("title", nid)
    detail_id = _eid("detail", nid)
    # 档位由 layout 那份判据决定（盒子尺寸也是按它算的，两处必须同一个判据）
    has_detail = bool(node.get("detail")) and L.shows_node_detail(node, detail_level)
    text = box.text          # 形状包围盒里面的文字信息（见 layout.NodeBox）

    bound = [{"type": "text", "id": title_id}]
    if has_detail:
        bound.append({"type": "text", "id": detail_id})
    bound += [{"type": "arrow", "id": a} for a in arrows_out + arrows_in]
    # 带图标的节点例外：标签要**解绑**才能让"图标 + 文字"整组居中，见下面那段。
    # 带说明的节点同样解绑 —— **一个容器只能有一个绑定文字**，Excalidraw 只画第一个：
    # 标题绑了容器，说明就永远不出现（JSON 里明明有那个元素，渲染器就是不画）。
    # 实测见 references/validation.md（2026-09-16：解绑后说明立刻出现）。
    free_text = bool(icon_src) or has_detail
    if free_text:
        bound = [{"type": "arrow", "id": a} for a in arrows_out + arrows_in]

    kind = node.get("kind")
    emphasis = node.get("emphasis", palette.DEFAULT_EMPHASIS)
    # stroke 也要带上 emphasis —— 否则 critical 节点的填充是警示色、
    # 描边却还是基础层级那一档，而线宽又按 emphasis 来，三者对不上。
    stroke = palette.stroke_for(kind, emphasis)
    fill = palette.fill_for(kind, emphasis)
    stroke_width = palette.emphasis_stroke_width(emphasis)
    elements = shape_elements(shape_id, box.shape, placed, stroke, fill,
                              stroke_width=stroke_width, style=style)
    # 文字与箭头都绑到**主体**那个元素上；圆柱的顶盖只是一个装饰性叠加
    elements[0]["boundElements"] = bound

    # 文字在**形状里能放字的那块区域**居中（不是在整个包围盒里居中）——
    # 圆柱要下沉一个盖高，否则标题会压在椭圆盖上。
    inner_y, inner_h = text_band(box.shape, placed)
    title_h = len(text.lines) * text.font_size * tm.LINE_HEIGHT
    detail_h = len(text.detail_lines) * tm.FONT_DETAIL * tm.LINE_HEIGHT
    top = inner_y + (inner_h - (title_h + detail_h)) / 2.0
    content_w = text.break_units * text.font_size

    # 图标（可选）与文字的摆放，要按**真实 Excalidraw 的规矩**来算。
    #
    # 关键事实（官方渲染实测，复核工具见 dev-tools/export_excalidraw.py）：
    # `containerId` 非空的文字，官方会**自己重算位置、水平垂直居中于容器**，
    # 我们写进去的 x/y 只影响预览。所以"图标 + 文字"整组居中，在**绑定**的前提下
    # 数学上做不到：文字被钉在容器中心，只把图标贴到可见文字左边，整组重心就
    # 必然偏左 (图标宽 + 间隔) / 2。实测 19px —— 这就是用户那句"图标和文本，
    # 不应该居中吗"。
    #
    # 解法：**带图标的节点，标签不绑容器**（`containerId: None`）。官方就按我们给的
    # 坐标落笔（已实测：写 145.6，渲染出来就是 145.6），整组于是能精确居中。
    # 带说明的节点同样解绑（原因不同：一个容器只认一个绑定文字，见上面 `free_text`）。
    # 代价与补偿：解绑后改标签不会自动重排，且拖动形状时文字不会跟着走 ——
    # 所以形状 / 图标 / 标签**同挂一个 groupId**，在编辑器里它们仍是一体。
    # （本项目的"有 groupId 的就不是节点"那条判据随之改成**按 id 前缀认节点**。）
    # 没有图标也没有说明的节点不牵涉这件事，保持绑定。
    icon_w = 0.0
    height = icon_height if icon_height else icons.ICON_HEIGHT
    if icon_src:
        scale = icons.fit_scale(icon_src, height)
        icon_w = icons.intrinsic_size(icon_src)[0] * scale

    gap = (layout_gap() if icon_w else 0.0)
    # 可见文字宽度：**每桶按自己的字号算**（标题 16px、说明 12px）。
    # 拿标题字号去乘说明行会高估 33% —— 说明变宽之后这个高估直接超出框宽，
    # 图标就被推到左边框外面去了（用户截图里的溢出就是这么来的，2026-09-16 修）。
    label_visible = (max([tm.weighted_units(line) for line in text.lines] or [0.0])
                     * text.font_size)
    detail_visible = (max([tm.weighted_units(line) for line in text.detail_lines] or [0.0])
                      * tm.FONT_DETAIL)
    visible_w = max(label_visible, detail_visible)
    center = placed.x + placed.width / 2.0
    # 有图标时：文字中心右移半个"图标位"，让 (图标 + 间隔 + 可见文字) 整组居中；
    # 没有图标时就是盒子中心。
    text_center = center + (icon_w + gap) / 2.0 if icon_src else center
    tx = text_center - content_w / 2.0
    # 自由文字还是绑定文字：
    #  - 有图标 → 必须自由，否则整组居中做不到（见下面那段）；
    #  - 有说明 → 必须自由，否则 Excalidraw 只画容器里的第一个绑定文字（标题），
    #    说明永不出现；而且两个绑定文字会互相压在一起（标题被拉回容器中心）。
    # 其余（只有标题）保持绑定 —— 那个在编辑器里更顺手（改完自动重排）。
    label_container = None if free_text else shape_id

    node_group = [_eid("group", nid)] if free_text else []
    if node_group:
        # 形状、圆柱顶盖、图标、标签同组：解绑之后它们必须靠分组才能"一起动"
        for el in elements:
            if el["groupIds"]:
                if node_group[0] not in el["groupIds"]:
                    el["groupIds"] = list(el["groupIds"]) + node_group
            else:
                el["groupIds"] = list(node_group)

    if icon_src:
        # 图标紧贴可见文字的左边（间隔 = 设计值），竖向与文字块中心对齐。
        # 位置由"整组居中"推出来；**框在布局阶段已经适配过内容宽度**
        # （layout.boxes_from_spec：宽 ≥ 内边距×2 + 图标 + 间隔 + 可见文字），
        # 所以这里算出来必定在框内，不需要（也不应该）钳位 —— 钳位只会把图标
        # 推到文字底下，看起来像"图标没了"（用户 2026-09-16 的反馈）。
        icon_left = text_center - visible_w / 2.0 - gap - icon_w
        icon_els = icons.place(icon_src, icon_left,
                               top + (title_h + detail_h) / 2.0 - height / 2.0,
                               key=_eid("icon", nid), target_height=height,
                               # 单色素材用**所属节点自己的描边色**（图标与框同色）；
                               # 多色素材（品牌 logo）保留配色，按画布对比度压到可读。
                               # 策略由样式轴 `style.icons` 决定（auto / ink / native）
                               stroke=stroke,
                               canvas=palette.CANVAS.get("background"),
                               colours=palette.resolve_style(style).get("icons", "auto"))
        for el in icon_els:
            el["groupIds"] = list(el["groupIds"]) + node_group
        elements += icon_els

    labels = [_text_block(title_id, label_container, text.lines, tx, top,
                          content_w, text.font_size)]
    if has_detail:
        labels.append(_text_block(detail_id, label_container, text.detail_lines,
                                  tx, top + title_h, content_w, tm.FONT_DETAIL))
    if node_group:
        for el in labels:
            el["groupIds"] = list(node_group)
    elements += labels
    return elements


def layout_gap() -> float:
    """图标与文字之间留的空隙。**单一来源**：布局算盒子宽度时用的是同一个数。"""
    return L.ICON_GAP


def text_band(shape_name: str, placed) -> tuple[float, float]:
    """形状里“能放文字的那一条带”的 (顶边, 高)。"""
    if shape_name == "cylinder":
        cap = shapes.cylinder_cap(placed.width)
        return placed.y + cap, placed.height - cap
    return placed.y, placed.height


def shape_elements(element_id: str, shape_name: str, placed,
                   stroke: str, fill: str,
                   stroke_width: float = STROKE_WIDTH,
                   style: dict | None = None) -> list[dict]:
    """按形状建元素。除圆柱外都是一个元素。

    **圆柱刻意让柱体跨满整个包围盒**，而不是“柱体在下半、盖子在右上”：
    柱体就是箭头与文字绑定的主体，它的包围盒必须等于整个盒子，
    否则箭头会连到柱体上、看起来像“连到了下半截”。
    顶盖椭圆只是叠在上面的装饰（元素顺序 = 叠放顺序，它在后面所以在上）。
    """
    entry = shapes.SHAPES[shape_name]
    # 这里必须换名字：`style` 现在是样式轴那份字典，而旧代码把它当"描边风格串"用
    # （`shapes.stroke_style_for` 的返回值）。同名会被后一次赋值悄悄覆盖。
    resolved = palette.resolve_style(style)
    stroke_style = palette.stroke_style_of(resolved, shapes.stroke_style_for(shape_name))
    fill_style, roughness = resolved["fill"], palette.roughness_of(resolved)
    if shape_name == "cylinder":
        cap = shapes.cylinder_cap(placed.width)
        body = _base(element_id, "rectangle", placed.x, placed.y, placed.width,
                     placed.height, stroke, fill, stroke_style=stroke_style,
                     roundness=palette.roundness_of(resolved, entry.get("roundness")),
                     stroke_width=stroke_width, fill_style=fill_style,
                     roughness=roughness)
        # 顶盖必须跟柱体同一套线型 —— 少了 stroke_style，柱体是虚线、盖子却是实线
        lid = _base(f"{element_id}-lid", "ellipse", placed.x, placed.y,
                    placed.width, cap, stroke, fill, stroke_width=stroke_width,
                    stroke_style=stroke_style, fill_style=fill_style,
                    roughness=roughness)
        # 顶盖与柱体成组：在 Excalidraw 里拖动时它们一起动（否则一拖就散开），
        # 同时这也是一个明确标记 —— “groupIds 非空的是装饰，不是节点”，
        # 校验/量图那边靠它区分顶盖与真节点。
        lid["groupIds"] = [element_id]
        return [body, lid]
    roundness = entry.get("roundness")
    if shape_name == "capsule" and resolved["corners"] == "shape":
        # Excalidraw 没有原生胶囊。type 2 是“按比例取半径”，0.5 就是高的一半 → 真正的胶囊。
        # 只在默认档（听形状自己的）时用它 —— 显式写 sharp 就是要一个普通直角矩形。
        roundness = {"type": 2, "value": 0.5}
    return [_base(element_id, entry["excalidraw"], placed.x, placed.y,
                  placed.width, placed.height, stroke, fill,
                  stroke_style=stroke_style,
                  roundness=palette.roundness_of(resolved, roundness),
                  stroke_width=stroke_width, fill_style=fill_style,
                  roughness=roughness)]


# 比节点细（节点 1.5 / 强调 2.5）：区域是背景层。但不低于 1.0 ——
# 0.75 时手绘的那点抖动几乎看不出来，整块区域会显得比周围"更机械"。
REGION_STROKE_WIDTH = 1.0
# 区域标题的字号住在 `layout.REGION_LABEL_SIZE` —— 它**决定了标题带的高度**
# （带高 = 上边距 + 行数 × 字号 × 行高 + 间隙），所以尺寸链在 layout 那一侧。
# 这里只用它，不再另存一份（两份数值必然漂，而漂的那一份会让框和字对不上）。


def edge_kind_label(edge: dict, level: str | None) -> str | None:
    """`detail: diagnostic` 时，给**不是默认 kind** 的边补上它的中文说明。

    为什么这算「诊断用」：一条虚线的边，光看图分不出它是**异步**还是**可选** ——
    那是语义差别，排查问题时恰恰要看这个。（放在 emit 而不是 layout，是因为它要用
    `palette`；layout 里色板叫 `_palette`，那边没必要为这一处多引一个字段。）

    **默认 kind（`sync`）不补。** 实线 + 箭头方向已经说明了“同步调用”，再写一遍
    是零信息量，而密集图上它会变成一大片重复的字 —— 用户的原话是
    “太拥挤了看着”（一片区域里四五个“同步调用”）。实测一张 12 条边的图里，
    默认 kind 占绝大多数，所以这条一下子就去掉了大部分标签。
    `data` 仍然要补：它也是实线，光看线看不出它是“调用”还是“读写”。

    用户自己写了 `label` 就听用户的 —— 自动补的从不让位给人写的东西。
    """
    if level != "diagnostic" or edge.get("label"):
        return None
    kind = edge.get("kind") or palette.DEFAULT_EDGE_KIND
    if kind == palette.DEFAULT_EDGE_KIND:
        return None
    return palette.EDGE_KINDS.get(kind, {}).get("zh")


def _region_label_x(region: dict, width: float,
                     polylines: list | None) -> tuple[float, bool]:
    """区域标题在标题带里**挑一个不被连线穿过**的横坐标。

    实测踩到：标题原来固定在区域顶部**居中**，而进入该区第一条边是从上一个区下来的
    竖段，正好从中间穿过 —— 端到端夹具一次报出两个区域标题被穿（`07-regions`）。
    区域是背景，可它的标题是要读的字，不能让线从字上过。

    候选是标题带里的一串位置（居中 + 两边各扫若干点）。返回 `(横坐标, 是否脏)` ——
    第二个值决定要不要给标题铺底色：标题带里**每一个候选都被线穿过**时
    （实测 420px 的标题在 468px 的区域里，而竖线正在正中），只能靠底色。
    打分只看"这条线会不会从这段文字的圈里过" —— 和边标签用的是同一套判据。
    """
    if not polylines or width <= 0:
        return region["label_x"], False
    # 搜索范围**是整块区域的宽度**，只留 `REGION_LABEL_MARGIN` 不允许贴到框线后面 ——
    # 一开始卡了 12px 内边距，结果 `boot` 那个 276px 宽的标题在 [−14, 230] 里
    # **每一个候选都被穿过**：竖线在区域正中 x=259，而整个候选区间落在 [−17, 259] 内。
    # 贴着右边缘（268）反而是干净的 —— 标题本来就可以靠边，不必留那么宽的边距。
    margin = L.REGION_LABEL_MARGIN
    left = region["x"] + margin
    right = region["x"] + region["width"] - margin - width
    if right < left:
        # 构上到不了：标题按区域宽度断行（`layout.region_label_lines`），
        # 所以 width ≤ 区域宽 - 2×margin。留着当护栅 —— 真要走到这里，说明尺寸链被改坏了。
        return region["label_x"], False
    centre = region["label_x"] - width / 2.0
    best, best_hits = region["label_x"], None
    spans = [0.5, 0.0, 1.0] + [step / 16 for step in range(1, 16, 2)]
    for fraction in spans:
        x = centre if fraction == 0.5 else left + (right - left) * fraction
        x = max(left, min(right, x))
        hits = _line_hits(x, region["label_y"], width,
                          region.get("label_height") or L.REGION_LABEL_SIZE * tm.LINE_HEIGHT,
                          polylines)
        if best_hits is None or hits < best_hits:
            best, best_hits = x + width / 2.0, hits
        if not hits:
            break
    return best, bool(best_hits)


def region_elements(region: dict, style: dict | None = None,
                    polylines: list | None = None) -> list[dict]:
    """一个区域 = 圆角矩形（交叉网格填充）+ 顶部居中的标题。

    ⚠️ **必须先进 `build_scene` 的 elements 数组。** Excalidraw 的绘制顺序就是
    数组顺序，区域是背景 —— 后进数组的话它会盖住里面的节点（参考图里节点是
    清清楚楚压在网格上面的）。

    ⚠️ 贴一个 `groupIds`：装饰件靠它被认出来（**认节点看 id 前缀 `node-`**，
    不再看有没有组号 —— 带图标的节点形状/标签/图标也挂着组号，见
    `node_elements` 附近的说明）。区域是装饰，不带会把自己混进节点。

    颜色走**层级**而不是写死：`tint`（默认）用极轻的一片，`critical` 用来圈
    "这一段是异常路径"。区域是图上**唯一的整片颜色** —— 在节点只能承载
    单点关注的预算下，它就是让图不沉闷的那一层。
    """
    level = region.get("level", "tint")
    if level not in palette.LEVELS:
        raise ValueError(f"区域 {region['id']!r} 的 level 不认识：{level!r}"
                         f"（可用 {sorted(palette.LEVELS)}；未知值判失败，不 fallback）")
    stroke = palette.frame_stroke(level)      # 退到背景层的颜色，不再和连线撞脸
    fill = palette.LEVELS[level]["fill"]
    # 区域的**局部覆盖**：顶层 style 打底，这个区域自己写的轴盖在上面。
    # 用户要过「只让区域用虚线、节点保持实线」—— 全局 style 表达不了这件事。
    resolved = palette.merge_style(palette.resolve_style(style), region.get("style"))
    el_id = _eid("region", region["id"])
    elements = [_base(el_id, "rectangle", region["x"], region["y"],
                      region["width"], region["height"], stroke, fill,
                      stroke_width=REGION_STROKE_WIDTH,
                      roundness=palette.roundness_of(resolved, {"type": 3}),
                      stroke_style=palette.stroke_style_of(resolved, "solid"),
                      fill_style=resolved["fill"],
                      roughness=palette.roughness_of(resolved),
                      extra={"groupIds": [el_id]})]
    label = region.get("label")
    if label:
        # **断行与尺寸直接用 layout 算好的那份**，不在这里重新量一遂 ——
        # 标题带的高度就是按那几个数算出来的，这里再量一次就可能对不上
        # （而“框与字对不上”正是用户报的那个溢出的根。“同一件几何算两遂必然漂移”
        # 这句在 `_sample_points`/`_segment_may_hit_box` 那两处已经写下过一次）。
        lines = list(region.get("label_lines") or (label,))
        size = region.get("label_size", L.REGION_LABEL_SIZE)
        width = region.get("label_width", 0.0)
        height = region.get("label_height", 0.0)
        text = "\n".join(lines)
        label_id = _eid("region-label", region["id"])
        label_x, dirty = _region_label_x(region, width, polylines)
        # 底色与边标签同步**常开**（同一个办法，两处一致）：标题是要读的字，
        # 不论搜到的位置干不干净都垫一枚画布色小牌。`dirty` 仍然返回，
        # 作为“标题带里没有干净位置”的机器可读标记。
        _ = dirty
        elements.append({
            **_base(label_id, "text", label_x - width / 2.0,
                   region["label_y"], width, height,
                   palette.LEVELS[level]["stroke"], "transparent",
                   extra={"groupIds": [el_id]}),
            "text": text,
            "fontSize": size,
            "fontFamily": palette.CANVAS["font_family"],
            "textAlign": "center",
            "verticalAlign": "top",
            "containerId": None,
            "originalText": text,
            "lineHeight": tm.LINE_HEIGHT,
            "baseline": round(size * BASELINE_RATIO, 2),
        })
        elements[-1]["backgroundColor"] = palette.CANVAS["background"]
        elements[-1]["roundness"] = {"type": 3}
    return elements


def _text_block(el_id: str, container_id: str | None, lines: tuple[str, ...],
                x: float, y: float, content_width: float, font_size: float) -> dict:
    """一个文字块。`container_id` 为空 = **自由文字**。

    x/y 对绑定文字只是初值 —— Excalidraw 对 `containerId` 非空的文字会自己重算
    位置与换行（见模块顶部那条限制）；`container_id=None`（自由文字）则**完全按
    我们给的位置落笔**，图标节点就是靠这一点让"图标 + 文字"整组居中。
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
def arrow_element(edge: dict, index: int,
                  style: dict | None = None) -> dict:
    pts = edge["points"]
    x0, y0 = pts[0]
    rel = [[round(px - x0, 2), round(py - y0, 2)] for px, py in pts]
    xs = [p[0] for p in rel]
    ys = [p[1] for p in rel]
    kind = edge.get("kind") or palette.DEFAULT_EDGE_KIND
    edge_style = palette.EDGE_KINDS.get(kind, palette.EDGE_KINDS[palette.DEFAULT_EDGE_KIND])

    el_id = _eid("edge", f"{edge['from']}-{edge['to']}", index)
    # 拐角**不圆**。用户的原话是「就是那种 90 度拐弯的线不行吗」，而 Excalidraw 的
    # `roundness` type 2 会把每个拐角都倒成弧 —— 多段折线的短拐角被糊得几乎看不出角度，
    # 实测图里那几处「钩子」有一半是它造成的。手绘感由 `roughness` 提供，不靠倒角。
    # （`roundness: None` 就是界面上的 Sharp；两点直线没有拐角，不受影响。）
    el = _base(el_id, "arrow", x0, y0, max(xs) - min(xs), max(ys) - min(ys),
               edge_style["stroke"], "transparent", stroke_style=edge_style["style"],
               roundness=None, roughness=palette.roughness_of(
                   palette.resolve_style(style)))
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


def _line_hits(x: float, y: float, width: float, height: float,
               obstacles: list) -> int:
    """标签矩形压到了多少段线（或多少条边）。0 = 干净。

    数出来的个数有第二个用途：**一个干净的位置都找不到时，退到"最不脏"的那个**。
    以前是“全都不干净就回到第一个候选”，于是密集图上会出现标签压在节点上 ——
    实测过（正交路由之后线更多了，“注册与装配”直接压在 kernel 的框上）。
    几何只有这一份实现，`_hits_lines` 是它的布尔包装。
    """
    right, bottom = x + width, y + height
    hits = 0
    for polyline in obstacles:
        for a, b in zip(polyline, polyline[1:]):
            if _segment_enters_rect(a, b, x, y, right, bottom):
                hits += 1
    return hits


def _hits_lines(x: float, y: float, width: float, height: float,
                obstacles: list) -> bool:
    return _line_hits(x, y, width, height, obstacles) > 0


def _box_hits(x: float, y: float, width: float, height: float, boxes: list) -> int:
    """标签矩形和这些矩形**重叠**了几处。

    这里必须用**面积重叠**，不能用轮廓：标签整个落在框**里面**时，框的轮廓和它
    根本不相交 —— 实测就是这么漏掉的（标签压在框里，打分却算它干净，底色也就
    永远不触发）。线段用轮廓判据是对的（线是线），矩形要用矩形判据。
    """
    right, bottom = x + width, y + height
    hits = 0
    for left, top, box_right, box_bottom in boxes:
        if x < box_right and right > left and y < box_bottom and bottom > top:
            hits += 1
    return hits


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
                   keepouts: list | None = None,
                   gap: float = LABEL_GAP) -> tuple[float, float, bool]:
    """找一个**不与任何连线相交**的标签位置 —— 由脚本自己搜，不靠一个魔法偏移量。

    为什么不能只算一个偏移量：

    1. 旧写法 `(mid.x + 6, mid.y - fontSize)` 只上移了一个字号（12px）而标签高 15px，
       线正好从文字中间穿过 —— 用户看到的“还是有遮挡”就是这个。
    2. 改成“沿法线退开”之后，**拐点**上仍然会盖：中点落在 V 形折线的顶点时，
       标签以顶点为中心，它有一半会压回入射那一段。
    3. 而且标签还可能撞上**别的边**，那是单纯算自家法线永远避不开的。

    返回 `(x, y, 需要底色吗)`。

    `keepouts` 是**节点矩形**（`(x, y, w, h)` 四元组，按面积重叠判，不是轮廓）。
    压到节点比压到线严重得多 —— 线从字上过去
    还看得清，字压在框上就分不清这行字属于谁了。所以打分时节点按 `NODE_WEIGHT` 计权，
    「最不脏」的兜底会优先避开框（实测：五层架构那张里「上传 / 建 job」正好压在
    apps/api 框里 —— 就是因为节点和线同权，兜底选了一个压框但没压线的位置）。

    全都不干净时返回 `True`：调用方会给文字铺一个**底色**，让“被穿过看不清”
    在结构上不可能发生，而不是继续挪到一个一样脏的地方。
    """
    obstacles = obstacles or [list(pts)]
    keepouts = keepouts or []
    radius = math.hypot(width, height) / 2
    # 先试中点，不行再沿边滑 —— 标签本来就可以不在中点，
    # 而死守中点会把“附近明明有位置”变成“只能压线”。
    # 顺序是“离中点由近到远”，所以能用中点时一定用中点。
    first: tuple[float, float] | None = None
    best: tuple[float, float] | None = None
    best_score = -1
    # 取样点与退让量都给足：正交路由之后线段变多，密集图上常常整片中招。
    # 多试一些点的代价很小（一次搜索也就几百次矩形相交判断），比压上去划算。
    #
    # **循环顺序是「先沿线滑、再往外推」**（退让量在外层）。
    # 写反的代价实测过：标签会为了躲开一个障碍而**先往外推 100px**，
    # 而不肯沿着自己那条线滑开一段 —— 结果一堆标签飘在离自己那条线很远的地方，
    # 看着又乱又拥挤（实测最大偏离 **191px**），还说不清这行字到底属于哪条边。
    # 换成先滑再推、最大偏离降到 **31px**，同一张密集图上的重叠仍然是 0。
    for extra in (0.0, 6.0, 12.0, 20.0, 30.0, 45.0, 65.0, 90.0, 120.0, 160.0):
        for frac in (0.5, 0.42, 0.58, 0.34, 0.66, 0.26, 0.74, 0.18, 0.82, 0.1, 0.9):
            mid, back, fwd = _midpoint_frame(pts, frac)
            directions = _candidate_directions(back, fwd)
            for dx, dy in directions:
                reach = radius + gap + extra
                x = mid[0] + dx * reach - width / 2
                y = mid[1] + dy * reach - height / 2
                if first is None:
                    first = (x, y)
                score = (_line_hits(x, y, width, height, obstacles)
                         + NODE_WEIGHT * _box_hits(x, y, width, height, keepouts))
                if score == 0:
                    return round(x, 2), round(y, 2), False
                if best is None or score < best_score:
                    best, best_score = (x, y), score    # 兜底：最不脏的那个
    if best is not None:
        return round(best[0], 2), round(best[1], 2), True
    if first is None:                       # 理论上不可达（候选方向非空），但不靠 assert
        mid = _midpoint_frame(pts)[0]
        first = (mid[0] - width / 2, mid[1] - radius - gap - height / 2)
    return round(first[0], 2), round(first[1], 2), True


def edge_label_element(edge: dict, index: int, obstacles: list | None = None,
                       keepouts: list | None = None) -> dict | None:
    """边标签：一个独立的文字元素，位置由 `label_position` 搜出来。

    刻意**不**绑到箭头上 —— 箭头标签在 Excalidraw 里有自己的定位规则，
    绑上去容易在编辑时漂移；独立元素至少位置是可预测的。

    `obstacles` 传**所有**边的折线（不只是自己那条），`keepouts` 传**节点矩形** ——
    前者撞上就不好读，后者撞上就更糟：分不清这行字属于谁。
    """
    label = edge.get("label")
    if not label:
        return None
    width = round(tm.weighted_units(label) * tm.FONT_DETAIL, 2)
    height = round(tm.FONT_DETAIL * tm.LINE_HEIGHT, 2)
    x, y, needs_backdrop = label_position(edge["points"], width, height,
                                          obstacles, keepouts)
    el_id = _eid("elabel", f"{edge['from']}-{edge['to']}", index)
    el = _base(el_id, "text", x, y, width, height,
               palette.CANVAS["text"], "transparent", extra={"roundness": None})
    # **底色常开**：每个标签都垫一枚画布色小牌。
    # 以前只在“搜不到干净位置”时才铺，但“线从字旁边掠过”在密集图上同样难读；
    # 常开后线到字跟前断开，任何位置都读得清。`needs_backdrop` 保留在返回值里，
    # 只是“这个位置被穿过”的机器可读标记（测试与预览用它）。
    el["backgroundColor"] = palette.CANVAS["background"]
    el["roundness"] = {"type": 3}
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


# 标题底边到内容顶边的距离。定义在 `layout`（两个后端都要用，同一件几何量只留一处）。
TITLE_GAP = L.TITLE_GAP
# 打开文件时用的**名义视口**与留白（Excalidraw 不会告诉我们真实视口有多大）。
# 顶部那条留白是给工具栏的 —— 不留的话内容会压在工具下面。
OPEN_VIEW = (1400.0, 800.0)
OPEN_MARGIN = (60.0, 110.0, 50.0)


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


# ── 结论卡片（cards：支撑性细节放卡片，不堆进图里）────
# 几何与折行住在 `layout.card_rows`（两个后端同一份推导，常量也在那边）；
# 这里只负责把排好的卡落成 Excalidraw 元素。


def card_elements(laid: list[dict], level: str = "tint") -> list[dict]:
    """卡片 = 便签风矩形（虚线框 + 极轻填充）+ 标题 + 条目。

    与区域同一条规矩：挂 `groupIds`（装饰件都挂组号）；文字**不绑容器**
    （卡片不是可拖址的节点，自由文字的位置我们自己算得准）。
    认节点看 id 前缀（`node-`），不看有没有组号。
    """
    if level not in palette.LEVELS:
        level = "tint"
    if not laid:
        return []
    elements: list[dict] = []
    for card in laid:
        gid = f"card-{card['index']}"
        stroke = palette.frame_stroke(level)
        fill = palette.LEVELS[level]["fill"]
        elements.append(_base(_eid("card", gid), "rectangle",
                              card["x"], card["y"], card["width"], card["height"],
                              stroke, fill, stroke_style="dashed",
                              stroke_width=1.0,
                              roundness={"type": 3},
                              extra={"groupIds": [gid]}))
        tx = card["x"] + L.CARD_PAD_X
        ty = card["y"] + L.CARD_PAD_Y
        if card["title_lines"]:
            text = "\n".join(card["title_lines"])
            w = max(tm.weighted_units(l) for l in card["title_lines"]) * tm.FONT_NODE
            h = len(card["title_lines"]) * tm.FONT_NODE * tm.LINE_HEIGHT
            elements.append({
                **_base(_eid("card-title", gid), "text", tx, ty, round(w, 2),
                        round(h, 2), palette.LEVELS[level]["stroke"],
                        "transparent", extra={"groupIds": [gid], "roundness": None}),
                "text": text, "originalText": text,
                "fontSize": tm.FONT_NODE,
                "fontFamily": palette.CANVAS["font_family"],
                "textAlign": "left", "verticalAlign": "top",
                "containerId": None, "lineHeight": tm.LINE_HEIGHT,
                "baseline": round(tm.FONT_NODE * BASELINE_RATIO, 2),
                "strokeWidth": 1,
            })
            ty += h + L.CARD_PAD_Y
        if card["item_lines"]:
            text = "\n".join(card["item_lines"])
            w = max(tm.weighted_units(l) for l in card["item_lines"]) * tm.FONT_DETAIL
            # 行距用卡片段位（CARD_ITEM_LINE_HEIGHT），与 card_rows 算高度同一个数
            h = len(card["item_lines"]) * tm.FONT_DETAIL * L.CARD_ITEM_LINE_HEIGHT
            elements.append({
                **_base(_eid("card-items", gid), "text", tx, ty, round(w, 2),
                        round(h, 2), palette.CANVAS["text"],
                        "transparent", extra={"groupIds": [gid], "roundness": None}),
                "text": text, "originalText": text,
                "fontSize": tm.FONT_DETAIL,
                "fontFamily": palette.CANVAS["font_family"],
                "textAlign": "left", "verticalAlign": "top",
                "containerId": None, "lineHeight": L.CARD_ITEM_LINE_HEIGHT,
                "baseline": round(tm.FONT_DETAIL * BASELINE_RATIO, 2),
                "strokeWidth": 1,
            })
    return elements


def build_scene(spec: dict, result, boxes: dict,
                icon_lookup=None, icon_height=None) -> dict:
    elements: list[dict] = []
    by_id = {n["id"]: n for n in spec.get("nodes", [])}
    # 四组样式轴解析一次，透传给每个元素（未知值在 resolve_style 里就抛错了）
    style = palette.resolve_style(spec.get("style"))
    # `detail` 以前是空壳（声明了没人读）。现在它就是信息量档位：见 layout 里
    # shows_node_detail / shows_edge_label 的说明。
    detail_level = spec.get("detail", L.DEFAULT_DETAIL)

    # 区域**第一个**进数组：它是背景，后进会盖住节点（见 region_elements）。
    # 区域标题要在标题带里避开连线，所以这里就得把折线算出来 —— 区域虽然画在最前，
    # 但折线本来就是 `result.edges` 里的现成数据（绝对坐标），不必等箭头那一步。
    region_polylines = [list(edge["points"]) for edge in result.edges]
    for region in L.region_boxes(spec, result.placed, boxes):
        elements += region_elements(region, style, region_polylines)
    # 区域标题也是要读的字，而它不是节点、也不是连线 —— 以前没有任何标签避让它。
    # 用户截图里的那处鸿就是：两条边的“同步调用”压在一个区域标题「探针与门禁」上。
    region_title_boxes = [(e["x"], e["y"], e["x"] + e["width"], e["y"] + e["height"])
                          for e in elements if e["id"].startswith("region-label-")]

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
        icon_src = None
        if icon_lookup is not None and by_id[nid].get("icon"):
            icon_src = icon_lookup(by_id[nid]["icon"])
        if icon_src:
            # 图标高度按节点各算各的（`icon_height` 是整数时是"全部用这个"，否则是表）。
            per_node = (icon_height.get(nid) if isinstance(icon_height, dict)
                        else icon_height)
            elements += node_elements(by_id[nid], placed, boxes[nid],
                                      arrows_out.get(nid, []), arrows_in.get(nid, []),
                                      icon_src=icon_src, icon_height=per_node,
                                      style=style, detail_level=detail_level)
        else:
            elements += node_elements(by_id[nid], placed, boxes[nid],
                                      arrows_out.get(nid, []), arrows_in.get(nid, []),
                                      style=style, detail_level=detail_level)

    # `result.edges` 里的 points **已经是绝对坐标**（`layout._points` 用的是 placed 的坐标），
    # 所以这里直接用，**不能再加一遍起点**。
    #
    # 以前写的是 `edge["points"][0] + p`，把一条真线平移成了另一条假线 ——
    # 标签搜索于是一直在躲不存在的障碍：它返回的位置在自己眼里是干净的，
    # 落到图上却压在真线上（实测某条边被压 19 个采样点）。
    # 这就是 P3“标签压线”反复修不掉的根因。
    polylines = [list(edge["points"]) for edge in result.edges]
    # 节点框单独传给标签搜索（`keepouts`），**不混进 `polylines`**：压到框比压到线
    # 严重得多，打分时要分别计权（NODE_WEIGHT）。只算**真节点** —— 虚节点是布局
    # 内部的东西，不画出来，不该把标签赶走。
    box_keepouts = [(placed.x, placed.y, placed.x + placed.width,
                     placed.y + placed.height)
                    for placed in result.real_nodes().values()]
    # **已经放好的标签自己也是避让物。** 以前每个标签只看连线和节点，
    # 互相不知道对方存在 —— 密集图上实测 12 个标签里 **7 对重叠**
    # （用户的原话：“线上的文本和其他线上的文本可能会重叠”）。
    # 重叠的两个标签谁也读不清，严重性跟压在节点框上一样，所以与节点同权。
    # 外扩半个 `LABEL_GAP`：只求“不重叠”会贴在一起，看着一样拥挤。
    label_keepouts = list(box_keepouts) + region_title_boxes
    for i, (edge, _) in enumerate(arrow_specs):
        elements.append(arrow_element(edge, i, style))
        if not L.shows_edge_label(edge, detail_level):
            continue                      # executive：摘要里不堆边标签
        label = edge_label_element(edge, i, polylines, label_keepouts)
        if label is None:
            auto = edge_kind_label(edge, detail_level)
            if auto:
                label = edge_label_element({**edge, "label": auto}, i, polylines,
                                           label_keepouts)
        if label:
            elements.append(label)
            pad = LABEL_GAP / 2.0
            label_keepouts.append((label["x"] - pad, label["y"] - pad,
                                   label["x"] + label["width"] + pad,
                                   label["y"] + label["height"] + pad))

    # 结论卡片（可选）：排在内容下方 —— 先于标题落位，标题居中时把卡片也算进去。
    left, top, right, bottom = scene_bounds(elements) if elements else (0, 0, 0, 0)
    elements += card_elements(L.card_rows(spec, left, right, bottom))

    # 图标题最后加：它要按已排好的内容来居中，而它自己**不参与**布局。
    # 放的位置是“内容顶边往上 TITLE_GAP”，所以不需要把别的元素往下挪 ——
    # 标题落到 y 为负的地方没关系：下面会把视图滚到内容左上角（见 OPEN_MARGIN_*）。
    title = title_element(spec.get("title"))
    if title is not None and elements:
        left, top, right, _bottom = scene_bounds(elements)
        title["x"] = round(left + (right - left) / 2.0 - title["width"] / 2.0, 2)
        title["y"] = round(top - TITLE_GAP - title["height"], 2)
        elements.append(title)

    # ── 打开时停在哪儿：**必须自己写** ──
    #
    # 实测（真实 excalidraw.com，2026-09-12）：appState 里不给 scrollX/scrollY 时，
    # 应用停在画布原点 —— 内容偏到屏幕角落，得先按一次"缩放至适合"才看得见。
    # 以前这里写着"载入时会自动居中视图"，那是个**没验过的假设**，实测不成立。
    #
    # ⚠ 但这三个字段**有没有被采纳，取决于打开方式**（同一次实测）：
    #   - `#url=` 导入（open_excalidraw_com.py 那条路）：**忽略** —— 它只采纳了
    #     `viewBackgroundColor`（画布真的是我们那个底色），视图仍是 100% 停在原点。
    #   - 当成**场景**打开（Obsidian 插件、编辑器里 Ctrl+O）：**尚未实测**。
    # 写它们仍然是对的（真实 Excalidraw 存盘时就是这些字段，我们的文件应该像一份
    # 正常的场景），但**别把"打开就框住内容"当成已验证的事实** —— 上面那条路不是。
    #
    # 视口按名义尺寸估：Excalidraw 不会告诉我们它多大，但"打开就框住内容"这件事
    # 只需要一个合理的默认值。margin 除以 zoom 是因为屏幕位置 = (场景 + scroll) × zoom。
    left, top, right, bottom = scene_bounds(elements)
    span_x = max(1.0, right - left)
    span_y = max(1.0, bottom - top)
    zoom = round(min(1.0, (OPEN_VIEW[0] - 2 * OPEN_MARGIN[0]) / span_x,
                     (OPEN_VIEW[1] - OPEN_MARGIN[1] - OPEN_MARGIN[2]) / span_y), 2)
    scroll_x = -left + OPEN_MARGIN[0] / zoom
    scroll_y = -top + OPEN_MARGIN[1] / zoom

    return {
        "type": SCENE_TYPE,
        "version": SCENE_VERSION,
        "source": SOURCE,
        "elements": elements,
        "appState": {
            "gridSize": None,
            "viewBackgroundColor": palette.CANVAS["background"],
            "scrollX": round(scroll_x, 2),
            "scrollY": round(scroll_y, 2),
            "zoom": zoom,
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


def load_icons(spec: dict, library_path: str | None = None,
               icon_height: float | None = None, full: bool = False):
    """把规格里用到的图标取出来。**一个都不要就完全不碰文件。**

    返回 `(lookup, sizes)`：
      - `lookup(name)` → 那一项的元素数组
      - `sizes` → `{node_id: (宽, 高)}`，给布局算盒子用

    名字不存在时**判失败不 fallback** —— 静默换一个图标，看图的人根本不知道
    原本想要的是什么（与 `kind` / `shape` / `emphasis` 同一条规矩）。

    名字分两个来源，**内置 sigil 优先**（见 `sigils.py`）：
      1. `sigils.NAMES` 里的内置名 —— 由脚本自绘，不需要任何外部文件；
      2. 其余名字 —— 照旧走 `.excalidrawlib` 素材库。
    两源同名时永远取内置：静默挑另一个等于"我写了 A 出来的是 B"。
    全部图标都是内置名时，素材库路径**完全不接触** —— "出图零依赖"不受影响。
    """
    wanted = {n["icon"] for n in spec.get("nodes", []) if n.get("icon")}
    if not wanted:
        return None, {}, {}

    lookup = {}
    for name in sorted(wanted):
        if sigils.is_builtin(name):
            # 颜色用当前画布墨色 —— 调用时机在主题切定之后（emit 的顺序保证）。
            lookup[name] = sigils.glyph(name, palette.CANVAS.get("text", "#1f2937"))

    library_names = wanted - set(lookup)
    if library_names:
        path, source = icons.library_path(library_path)
        if not path:
            raise icons.LibraryError(
                f"规格里有节点指定了图标 {sorted(library_names)}，其中没有内置 sigil，"
                f"需要素材库但没找到（{source}）。用 --library 指定，或写一行路径到 "
                f"~/.config/excalidraw-library-path，或改用内置名（scripts/sigils.py 可列）")
        library = icons.load(path)
        for name in sorted(library_names):
            elements = icons.resolve(library, name)      # 找不到会抛错并列出可用名字
            # 默认只留图形：节点自己已经有标签，素材自带的文字是冗余的，
            # 而且缩到节点尺寸后只有几个像素（见 icons.glyph_only）。
            lookup[name] = list(elements) if full else icons.glyph_only(elements)

    # 每个节点算自己的图标高度 —— 用户要的"适配每一个元素"。
    sizes = {}
    heights = {}
    for node in spec.get("nodes", []):
        name = node.get("icon")
        if not name:
            continue
        elements = lookup[name]
        if icon_height:
            want = icon_height
        else:
            text_box = tm.measure(node.get("label", ""),
                                  node.get("detail", "") if L.shows_node_detail(
                                      node, spec.get("detail", L.DEFAULT_DETAIL)) else "")
            want = icons.height_for(text_box.height)
        heights[node["id"]] = want
        width, height = icons.intrinsic_size(elements)
        scale = icons.fit_scale(elements, want)
        sizes[node["id"]] = (width * scale, height * scale)
    return lookup, sizes, heights


def icon_readability_issues(spec: dict, lookup: dict,
                            icon_height: float | None = None) -> list:
    """图标自带的文字缩到目标高度后看不清 —— 是**选型问题**，不是布局问题。

    实测：vault 里那个素材库是厂商**示意图**集合（图形 + 自带标签），缩到节点里
    当图标用，标签会变成 2px 噪点。图长得没错，是素材选错了。
    这件事只有拿到素材库才知道，所以只能在这里报。
    """
    if not lookup:
        return []
    out = []
    for node in spec.get("nodes", []):
        name = node.get("icon")
        if not name:
            continue
        got = icons.readability(lookup[name], icon_height or icons.ICON_HEIGHT)
        if got is None:
            continue
        smallest, _scale = got
        if smallest < icons.MIN_LEGIBLE_PT:
            out.append(_check_layout().Issue(
                "icon", False, node["id"],
                f"图标 {name!r} 自带的文字缩到 {smallest:.1f}px，看不清",
                advice="这个素材是带文字的示意图、不是单图形图标：换一个更简单的，"
                       "或把图标高度调大。"))
    return out + icon_contrast_issues(spec, lookup)


# 图标与它所在节点底色对比度低于这个值，基本就看不见了。**待验证**。
ICON_FILL_CONTRAST_MIN = 1.5


def icon_contrast_issues(spec: dict, lookup: dict) -> list:
    """图标自带的颜色与它所在节点的底色撞车 —— 撞了就看不见。

    ## 为什么需要这条

    素材自带品牌色（黑 / 蓝 / 红），**不随主题变**。在浅色主题下没问题，
    换到深色主题就会出现"黑底图标压在深色填充上"——图长得没错，是它看不见。

    这件事只有把"图标的颜色"和"节点的填充"放在一起算才知道，
    而且纯机械（算对比度），所以做成检查而不是写在文档里让人自己注意。

    ## 为什么不自动改色

    改色会破坏品牌标识的识别性（一个被改成蓝紫色的 AWS logo 更糟）。
    所以只报，并建议换一个**同义但亮一些**的素材。
    """
    out = []
    for node in spec.get("nodes", []):
        name = node.get("icon")
        if not name or name not in lookup:
            continue
        try:
            fill = palette.fill_for(node.get("kind"),
                                    node.get("emphasis", palette.DEFAULT_EMPHASIS))
        except KeyError:
            continue          # kind / emphasis 不合法的问题由 check_palette 报
        colours = icons.visible_colours(lookup[name])
        if not colours:
            continue
        worst = min((palette.contrast(c, fill), c) for c in colours)
        if worst[0] < ICON_FILL_CONTRAST_MIN:
            out.append(_check_layout().Issue(
                "icon", False, node["id"],
                f"图标 {name!r} 自带的颜色与它所在节点的底色几乎一样"
                f"（对比度 {worst[0]:.2f}），在当前主题下看不见",
                advice="换成同义但亮一些的素材；或换回浅色主题。"
                       "不建议自动改色 —— 那会破坏品牌标识的识别性。"))
    return out


def emit(spec: dict, *, params=None, library: str | None = None,
         icon_height: float | None = None, icon_full: bool = False,
         quality: str = "standard"
         ) -> tuple[dict, Any, Any, list]:
    """跑完整条流水线并返回场景。**校验有阻塞项就不出图。**

    顺序刻意是 validate → layout → check → emit：出图是最后一步，
    前一步不过就不该走到这里。跳过校验直接出图，等于把“不重叠/不溢出”的保证丢掉。

    `quality`：standard（默认）= 现有行为；showcase = 交付档 ——
    调参循环照常先跑，试尽后结构类软项（交叉/重合/斜段/折点/相交/穿节点）
    升级为阻塞，有残留就不出图（见 `check_layout.Outcome.promote`）。
    """
    validator = _load_sibling("validate_spec")
    report = validator.validate(spec)
    if getattr(report, "errors", None):
        detail = "\n".join(f"  - {e.line() if hasattr(e, 'line') else e}"
                           for e in report.errors)
        raise SpecError(f"规格不通过，没有出图：\n{detail}")

    # 主题在**一切之前**定：颜色要被尺寸/校验/标签各处读到，切晚了会前后不一致。
    # `visual` 是视觉方向（旧字段 `theme` 已废弃）；`mood` 是**用户的原话**，
    # 用于 §19"用户明确指定风格时优先用户意图"。
    palette.set_context(spec.get("mood"))
    palette.use_direction(spec.get("visual"), diagram_type=spec.get("type"))

    # 图标必须在算盒子**之前**解析出来 —— 它会影响节点尺寸（第一个外部尺寸来源）
    lookup, icon_sizes, icon_heights = load_icons(spec, library, icon_height,
                                                  icon_full)
    boxes = L.boxes_from_spec(spec, icon_sizes)
    result, outcome, attempts = _check_layout().layout_with_retry(spec, boxes, params)
    extra = icon_readability_issues(spec, lookup or {}, icon_height)
    if extra:
        outcome = _check_layout().Outcome(issues=[*outcome.issues, *extra])
    # showcase 升级在调参之后：调参循环全程用原始 outcome 判断收敛（见 promote 的说明）。
    outcome = outcome.promote(quality)
    if outcome.blocking:
        return {}, result, outcome, attempts
    icon_lookup = (lambda name: lookup.get(name)) if lookup else None
    return (build_scene(spec, result, boxes, icon_lookup,
                        icon_heights or icon_height),
            result, outcome, attempts)


def _check_layout():
    return _load_sibling("check_layout")


def _atomic_write(path: str, payload: str) -> None:
    """先写同目录临时文件，再原子换入。

    为什么不直接写目标：写到一半被打断（磁盘满 / 进程被杀）会留下**半个文件**，
    而它看起来和正常产物一样 —— 同目录临时文件 + `os.replace` 保证目标路径上
    要么是旧版、要么是完整新版，永远不会是半张图。
    """
    tmp = os.path.join(os.path.dirname(os.path.abspath(path)),
                       f".{os.path.basename(path)}.tmp-{os.getpid()}")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _delivery_receipt(out_path: str, spec_path: str, spec_bytes: bytes,
                      artifact: str, receipt: dict) -> None:
    """三档声明 + SHA-256 双回执。三档互不冒充：

    1. 确定性校验 —— 本脚本机器可证；
    2. 自研预览渲染 —— 未验证，须 dev-tools/preview.py 或 excalidraw.com 核对；
       要渲染器自己画的图用 dev-tools/export_excalidraw.py（官方导出）；
    3. 感知审查 —— pending，**只能人眼看真实渲染**；校验全绿 ≠ 图讲清楚了。
    """
    digest = lambda b: hashlib.sha256(b).hexdigest()
    checks = receipt.get("checks", [])
    passed = sum(1 for c in checks if c.get("ok"))
    print("── 交付回执 ──")
    print(f"确定性校验: 通过（{passed}/{len(checks)} 项，档位 {receipt.get('quality', 'standard')}）")
    print("自研预览渲染: 未验证（官方导出 dev-tools/export_excalidraw.py，或预览 dev-tools/preview.py，或在 Excalidraw 里打开核对）")
    print("感知审查: pending（校验全绿 ≠ 图讲清楚了；须人眼看真实渲染）")
    print(f"规格 sha256: {digest(spec_bytes)[:16]}…  "
          f"产物 sha256: {digest(artifact.encode('utf-8'))[:16]}…")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="规格 → .excalidraw（plain JSON）")
    ap.add_argument("spec", help="*.diagram.json")
    ap.add_argument("-o", "--out", help="输出路径（默认与规格同名，后缀 .excalidraw）")
    ap.add_argument("--stdout", action="store_true", help="打到标准输出，不写文件")
    ap.add_argument("--library", help="*.excalidrawlib（规格里用到 icon 时才需要）")
    ap.add_argument("--icon-height", type=float,
                    help="强制图标高度（默认按每个节点自身高度算，见 references/icons.md）")
    ap.add_argument("--icon-full", action="store_true",
                    help="保留素材自带的文字（默认只取图形：节点自己已经有标签了）")
    ap.add_argument("--quality", choices=("standard", "showcase"), default="standard",
                    help="showcase=交付档：结构类软项升级为阻塞，有残留就不出图")
    ap.add_argument("--json", action="store_true", help="附带机器可读回执（结构化诊断）")
    args = ap.parse_args(argv)

    try:
        with open(args.spec, encoding="utf-8") as fh:
            spec_bytes = fh.read().encode("utf-8")
        spec = json.loads(spec_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"读不到规格：{exc}", file=sys.stderr)
        return 2

    try:
        scene, result, outcome, attempts = emit(spec, library=args.library,
                                                icon_height=args.icon_height,
                                                icon_full=args.icon_full,
                                                quality=args.quality)
    except SpecError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"布局失败：{exc}", file=sys.stderr)
        return 1
    except KeyError as exc:
        print(f"规格里有个值不认识：{exc}", file=sys.stderr)
        return 1
    except icons.LibraryError as exc:
        print(f"图标素材库：{exc}", file=sys.stderr)
        return 1

    if not scene:
        print("校验有阻塞项，不出图：", file=sys.stderr)
        print(_check_layout().format_report(spec, attempts, outcome), file=sys.stderr)
        if args.json:
            receipt = _check_layout().build_receipt(spec, result, attempts,
                                                    outcome, args.quality)
            print(json.dumps(receipt, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    payload = json.dumps(scene, ensure_ascii=False, indent=2)
    if args.stdout:
        print(payload)
        return 0

    out = args.out or os.path.splitext(args.spec)[0] + ".excalidraw"
    try:
        _atomic_write(out, payload + "\n")
    except OSError as exc:
        print(f"写不了 {out}：{exc}", file=sys.stderr)
        return 2
    n_nodes = len(result.real_nodes())
    print(f"✓ {out}  （{n_nodes} 个节点 / {len(result.edges)} 条边 / "
          f"{len(scene['elements'])} 个元素 / 交叉 {result.crossings}）")
    receipt = _check_layout().build_receipt(spec, result, attempts,
                                            outcome, args.quality)
    _delivery_receipt(out, args.spec, spec_bytes, payload, receipt)
    if args.json:
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
