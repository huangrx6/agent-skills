#!/usr/bin/env python3
"""规格 + 布局 → `.excalidraw`（plain JSON 场景）。

## 为什么是 `.excalidraw` 而不是 `.excalidraw.md`

Obsidian 的 Excalidraw 插件把 `.excalidraw.md` 里的场景压成 **lz-string**（实测插件
`main.js` 里有 24 处 `LZString`、`compressToBase64` / `compressToUint8Array` / `compressToUTF16`）——
**lz-string 没有 stdlib Python 等价物**，用它意味着要手抄一份 JS 的压缩算法，或者引依赖。

`*.excalidraw` 是普通 JSON，插件原生读写（同目录的 `my-obsidian-library.excalidrawlib`
就是 plain JSON）。所以本 skill 输出 plain JSON，不碰 lz-string。

## ⚠ 一处必须说清楚的限制：Excalidraw 会重新排版文字

`text_metrics` 的尺寸是我们对"文字占多大"的**推算**（CJK 1.00 em / Latin 0.56 em）。
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
          roundness: dict | None = None, extra: dict | None = None) -> dict:
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
        "strokeWidth": STROKE_WIDTH,
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
    rect_id = _eid("node", nid)
    title_id = _eid("title", nid)
    detail_id = _eid("detail", nid)
    has_detail = bool(node.get("detail"))

    bound = [{"type": "text", "id": title_id}]
    if has_detail:
        bound.append({"type": "text", "id": detail_id})
    bound += [{"type": "arrow", "id": a} for a in arrows_out + arrows_in]

    rect = _base(rect_id, "rectangle", placed.x, placed.y, placed.width, placed.height,
                 palette.stroke_for(node.get("kind")), palette.background_for(node.get("kind")),
                 roundness={"type": 3})
    rect["boundElements"] = bound

    # 文字块整体在容器里垂直居中；标题在上，detail 紧随其后。
    # 两个高度都由行数与字号算出 —— 与容器高度无关（容器高度本就是它们加内边距推出来的）。
    title_h = len(box.lines) * tm.FONT_NODE * tm.LINE_HEIGHT
    detail_h = len(box.detail_lines) * tm.FONT_DETAIL * tm.LINE_HEIGHT
    top = placed.y + (placed.height - (title_h + detail_h)) / 2.0
    tx = placed.x + tm.PADDING_X
    content_w = box.break_units * tm.FONT_NODE

    elements = [rect, _text_block(title_id, rect_id, box.lines, tx, top,
                                  content_w, tm.FONT_NODE)]
    if has_detail:
        elements.append(_text_block(detail_id, rect_id, box.detail_lines, tx,
                                    top + title_h, content_w, tm.FONT_DETAIL))
    return elements


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


def edge_label_element(edge: dict, index: int) -> dict | None:
    """边标签：一个独立的文字元素放在折线中点。

    刻意**不**绑到箭头上 —— 箭头标签在 Excalidraw 里有自己的定位规则，
    绑上去容易在编辑时漂移；独立元素至少位置是可预测的。
    """
    label = edge.get("label")
    if not label:
        return None
    pts = edge["points"]
    mid = pts[len(pts) // 2] if len(pts) % 2 == 0 else pts[(len(pts) - 1) // 2]
    el_id = _eid("elabel", f"{edge['from']}-{edge['to']}", index)
    el = _base(el_id, "text", mid[0] + 6, mid[1] - tm.FONT_DETAIL, 0, 0,
               palette.CANVAS["text"], "transparent", extra={"roundness": None})
    el.update({
        "text": label,
        "fontSize": tm.FONT_DETAIL,
        "fontFamily": palette.CANVAS["font_family"],
        "textAlign": "left",
        "verticalAlign": "top",
        "containerId": None,
        "originalText": label,
        "lineHeight": tm.LINE_HEIGHT,
        "baseline": round(tm.FONT_DETAIL * BASELINE_RATIO, 2),
        "strokeWidth": 1,
        "width": round(tm.weighted_units(label) * tm.FONT_DETAIL, 2),
        "height": round(tm.FONT_DETAIL * tm.LINE_HEIGHT, 2),
    })
    return el


# ── 场景 ────────────────────────────────────────────────────
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

    for i, (edge, _) in enumerate(arrow_specs):
        elements.append(arrow_element(edge, i))
        label = edge_label_element(edge, i)
        if label:
            elements.append(label)

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


def emit(spec: dict, *, params=None) -> tuple[dict, Any, Any, list]:
    """跑完整条流水线并返回场景。**校验有阻塞项就不出图。**

    顺序刻意是 validate → layout → check → emit：出图是最后一步，
    前一步不过就不该走到这里。跳过校验直接出图，等于把"不重叠/不溢出"的保证丢掉。
    """
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
    except ValueError as exc:
        print(f"布局失败：{exc}", file=sys.stderr)
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
