#!/usr/bin/env python3
"""开发/校准用预览渲染器 —— 把 `.excalidraw` 画成 PNG，给人眼看。

## 这不是运行时的一部分

**用户用这个 skill 出图不需要它。** skill 的运行时链路是
`validate_spec → layout → check_layout → emit_excalidraw`，全是纯 stdlib，
不 import 本目录里的任何东西。这里只是给自己做**目视复核与阈值校准**时用的内部手段。

依赖：`PIL`（不在运行时依赖范围内 —— 装了就用，没装就不影响出图）。
放在 `dev-tools/` 而不是 `scripts/`，就是为了让「核心链路零依赖」这句话不被含糊掉。

## 想要**真实渲染**的图，用隔壁那个

`dev-tools/export_excalidraw.py` 走 Excalidraw **官方**导出（`@excalidraw/utils`
的 `exportToBlob` / `exportToSvg`，在无头 Chrome 里跑），出的图是**渲染器自己画**的
PNG / SVG。判排版对错要看那张；本文件是"快、零依赖、看结构"的备胎。

## 它能判断什么、不能判断什么（这条最重要）

**能**：结构一眼能不能看懂、排版顺不顺眼、颜色比例、节点疏密、连线走向是否合理、
标签有没有压在节点上。

**不能**：**它不能替代真实 Excalidraw 的渲染检查。** 它画的是我们**自己的布局模型** ——
和 `layout.py` 同源，所以它**在构造上**看不见"渲染器与我们的模型不一致"这类问题。
具体说，下面这些只有真实 Excalidraw（Obsidian 插件或 excalidraw.com）才算数：

- 容器绑定文字在 Excalidraw 里的**实际断行**（字体度量不同 → 可能多出一行 → 容器被撑高）
- 手绘风格、圆角、箭头拐点的观感
- 缩放/导出裁剪是否把内容切掉

所以：本工具过了 ≠ 图没问题。`references/validation.md` 第五节把"用眼睛看一遍"
写成硬性验收条件时，指的也是**真实渲染**。

## 这里曾经有个 bug（值得留着）

第一版用 `x + width` 算所有元素的包围盒。对**箭头**这是错的：Excalidraw 的线性元素
`x`/`y` 是**首点**位置而不是包围盒左上角，折线点可以是负的（回边就是）
→ 算出来的范围比真实内容大 744px，渲染出来右侧一大片空白。

修法：线性元素的包围盒必须从 `points` 算（`element_bounds`）。这条与"检查器自己也
要被检查"是同一类教训 —— 目视工具自己有偏差时，你看到的是偏差，不是图。

用法：
    python3 dev-tools/preview.py scene.excalidraw out.png [--scale 1.5]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from typing import Any

# 包围盒实现放在 `scripts/emit_excalidraw.py` —— 那里是元素的出生地。
# 这里**刻意不存第二份**：同一件几何算两遍必然漂移，而漂移的那一份会让
# 预览和真实输出给出不同的结论（实测踩过：用 x+width 量线性元素，产生 744px 幽灵空白）。
_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
LINEAR_TYPES = {"arrow", "line"}
# 字体：拉丁 + CJK 都要有。macOS 上这几个够用；换平台要么改这里，要么接受回退字体。
FONT_CANDIDATES = (
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
)
DASH = (6, 4)
ARROW_LEN = 12.0
ARROW_HALF_WIDTH = 5.0


def _load_emit():
    """加载 `scripts/emit_excalidraw.py`（它自己会再加载兄弟模块）。"""
    import importlib.util
    path = os.path.join(_SCRIPTS, "emit_excalidraw.py")
    spec = importlib.util.spec_from_file_location("emit_excalidraw", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_EMIT = _load_emit()
element_bounds = _EMIT.element_bounds
scene_bounds = _EMIT.scene_bounds


def _colour(value: Any, fallback: Any = None) -> Any:
    """把 Excalidraw 的特殊颜色值换成 PIL 能认的。

    素材库里的元素大量使用 `transparent`（背景）和 `currentColor`（描边跟随文字色），
    而 PIL 只认 CSS 颜色名与 #RRGGBB —— 直接传会抛 `unknown color specifier`。

    实测踩过：带图标的图让预览**直接崩掉**，而这之前它只是"画不出来不吭声"。
    两种都不能要：前者看不见图，后者看着一张残图下结论。
    """
    if value is None:
        return fallback
    if not isinstance(value, str):
        return fallback
    if value in ("transparent", "none", ""):
        return None
    if value == "currentColor":
        return fallback
    return value


def _px(value: Any) -> int:
    """把算出来的浮点尺寸收成正整数像素。

    为什么单独抽一个函数：lint 规则 `unchecked-throwing-call-python` 会匹配**任何**裸
    `int()` / `float()`，不管参数是不是真会抛 —— 这里的参数都是我们自己算的浮点，
    本来不会失败。与其在 5 个调用点各写一个不会触发的 try 去哄它，不如收到一处。

    而这个 try 是**真的有用**的：尺寸可能来自外部场景文件（`width: "abc"` 这种），
    那不是我们算的值。
    """
    try:
        return max(1, int(round(float(value))))
    except (TypeError, ValueError, OverflowError):
        return 1


def _font(path: str, px: float):
    from PIL import ImageFont
    return ImageFont.truetype(path, _px(px))


# ── 手绘与虚线：预览必须看得出这两样，否则会误导判断 ──
#
# 这两样以前**完全不画**（只有折线画了虚线）。后果实测了两次：我给用户看的预览图
# 永远是笔直实线，于是他连着问"哪来的手绘感""为什么全是实线"。
# 工具不完整不是错，不完整却让人据此下结论才是错（和 render() 里 skipped 那段同一条）。
#
# 手绘的实现照 Excalidraw 的做法：**同一条边轻微错位描两遍**（不是把形状画歪）。
SKETCH_AMOUNT = {0: 0.0, 1: 1.7, 2: 3.4}


def _sketch_passes(roughness: Any) -> list[tuple[float, float]]:
    """要描几遍、每遍错开多少像素。0 档（正常直线）只有一遍且不偏移。"""
    try:
        amount = SKETCH_AMOUNT.get(int(roughness or 0), 0.0)
    except (TypeError, ValueError):
        amount = 0.0
    if amount <= 0:
        return [(0.0, 0.0)]
    return [(-amount, -amount * 0.5), (amount * 0.6, amount)]


def _rect_perimeter(x0, y0, x1, y1, r, steps: int = 4) -> list:
    """圆角矩形的周长采样（顺时针）。虚线要按点列画，PIL 的 outline 不支持虚线。"""
    r = max(0.0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    pts: list = []

    def edge(a, b):
        for k in range(1, steps + 1):
            t = k / steps
            pts.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))

    def arc(cx, cy, start):
        for k in range(1, 4):
            ang = start + (k / 3) * (math.pi / 2)
            pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))

    if r <= 0.5:
        pts = [(x0, y0)]
        edge((x0, y0), (x1, y0))
        edge((x1, y0), (x1, y1))
        edge((x1, y1), (x0, y1))
        edge((x0, y1), (x0, y0))
        return pts
    pts.append((x0 + r, y0))
    edge((x0 + r, y0), (x1 - r, y0))
    arc(x1 - r, y0 + r, -math.pi / 2)
    edge((x1, y0 + r), (x1, y1 - r))
    arc(x1 - r, y1 - r, 0.0)
    edge((x1 - r, y1), (x0 + r, y1))
    arc(x0 + r, y1 - r, math.pi / 2)
    edge((x0, y1 - r), (x0, y0 + r))
    arc(x0 + r, y0 + r, math.pi)
    return pts


def _stroke_path(draw, points, colour, width, style, roughness, passes) -> None:
    """按点列描线：支持虚线 / 点线 + 手绘重描。"""
    for dx, dy in passes:
        moved = [(x + dx, y + dy) for x, y in points]
        if style == "dashed":
            for a, b in zip(moved, moved[1:]):
                _dashed_line(draw, a, b, colour, width)
        elif style == "dotted":
            for a, b in zip(moved, moved[1:]):
                draw.line([a, b], fill=colour, width=width)
                r = max(1.0, width * 0.6)
                draw.ellipse([a[0] - r, a[1] - r, a[0] + r, a[1] + r], fill=colour)
        else:
            draw.line(moved, fill=colour, width=width, joint="curve")


def render(scene: dict, out_path: str, scale: float = 1.0, pad: float = 40.0) -> dict:
    from PIL import Image, ImageDraw

    elements = scene["elements"]
    left, top, right, bottom = scene_bounds(elements)
    width = _px((right - left) * scale + 2 * pad)
    height = _px((bottom - top) * scale + 2 * pad)
    bg = scene.get("appState", {}).get("viewBackgroundColor") or "#ffffff"

    img = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)
    to_px = lambda x, y: ((x - left) * scale + pad, (y - top) * scale + pad)

    font_path = next((p for p in FONT_CANDIDATES if os.path.exists(p)), None)
    if font_path is None:
        print("找不到可用字体，文字会省略", file=sys.stderr)
    cache: dict[float, Any] = {}

    def font_for(px: float):
        if font_path is None:
            return None
        if px not in cache:
            cache[px] = _font(font_path, px * scale)
        return cache[px]

    rects = [e for e in elements if e["type"] == "rectangle"]
    ellipses = [e for e in elements if e["type"] == "ellipse"]
    diamonds = [e for e in elements if e["type"] == "diamond"]
    arrows = [e for e in elements if e["type"] in LINEAR_TYPES]
    texts = [e for e in elements if e["type"] == "text"]
    drawn = {id(e) for e in rects + ellipses + diamonds + arrows + texts}

    # 画不出来的元素必须**显式报警**，而不是静静地不画。
    #
    # 这条是实测出来的：早期这个渲染器只认得 `rectangle`，于是加进形状之后，
    # 椭圆节点在预览里**彻底消失** —— 我看到的是“纯文字没框”，差点去改 emit。
    # 工具不完整不是错，不完整却不吭声才是错：目视检查的全部价值就在那张图上。
    skipped: dict[str, int] = {}
    for e in elements:
        if id(e) not in drawn:
            skipped[e["type"]] = skipped.get(e["type"], 0) + 1

    for e in rects:
        x0, y0 = to_px(e["x"], e["y"])
        x1, y1 = to_px(e["x"] + e["width"], e["y"] + e["height"])
        roundness = e.get("roundness") or {}
        radius = 8.0 * scale
        if roundness.get("type") == 2:
            # 胶囊：半径 = 高的一半（emit 里就是这么写的）。
            # 不用 `float()` 硬转：值本来就是我们自己 emit 的数字，而且这条 lint
            # （unchecked-throwing-call-python）会匹配**任何**裸转换，包括安全的那些。
            ratio = roundness.get("value", 0.5)
            if isinstance(ratio, (int, float)):
                radius = e["height"] * ratio * scale
        draw.rounded_rectangle([x0, y0, x1, y1], radius=radius,
                               fill=_colour(e.get("backgroundColor")))
        _stroke_path(draw, _rect_perimeter(x0, y0, x1, y1, radius * scale),
                     _colour(e.get("strokeColor"), "#666666"), _px(2 * scale),
                     e.get("strokeStyle"), e.get("roughness"),
                     _sketch_passes(e.get("roughness")))

    for e in ellipses:
        x0, y0 = to_px(e["x"], e["y"])
        x1, y1 = to_px(e["x"] + e["width"], e["y"] + e["height"])
        draw.ellipse([x0, y0, x1, y1], fill=_colour(e.get("backgroundColor")))
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        rx, ry = (x1 - x0) / 2, (y1 - y0) / 2
        ring = [(cx + rx * math.cos(t / 32 * math.tau),
                 cy + ry * math.sin(t / 32 * math.tau)) for t in range(33)]
        _stroke_path(draw, ring, _colour(e.get("strokeColor"), "#666666"),
                     _px(2 * scale), e.get("strokeStyle"), e.get("roughness"),
                     _sketch_passes(e.get("roughness")))

    for e in diamonds:
        cx0, cy0 = to_px(e["x"] + e["width"] / 2, e["y"])
        cx1, cy1 = to_px(e["x"] + e["width"], e["y"] + e["height"] / 2)
        cx2, cy2 = to_px(e["x"] + e["width"] / 2, e["y"] + e["height"])
        cx3, cy3 = to_px(e["x"], e["y"] + e["height"] / 2)
        draw.polygon([cx0, cy0, cx1, cy1, cx2, cy2, cx3, cy3],
                     fill=_colour(e.get("backgroundColor")))
        _stroke_path(draw, [(cx0, cy0), (cx1, cy1), (cx2, cy2), (cx3, cy3), (cx0, cy0)],
                     _colour(e.get("strokeColor"), "#666666"), _px(2 * scale),
                     e.get("strokeStyle"), e.get("roughness"),
                     _sketch_passes(e.get("roughness")))

    for e in arrows:
        pts = [to_px(e["x"] + p[0], e["y"] + p[1]) for p in e["points"]]
        if len(pts) < 2:
            continue
        _stroke_path(draw, pts, _colour(e.get("strokeColor"), "#666666"),
                     _px(2 * scale), e.get("strokeStyle"), e.get("roughness"),
                     _sketch_passes(e.get("roughness")))
        if e.get("endArrowhead"):
            _arrow_head(draw, pts[-2], pts[-1],
                        _colour(e.get("strokeColor"), "#666666"), scale)

    for e in texts:
        f = font_for(e["fontSize"])
        if f is None:
            continue
        lines = e["text"].split("\n")
        centered = bool(e.get("containerId"))
        line_height = e.get("lineHeight", 1.25)
        for i, line in enumerate(lines):
            if centered:
                draw.text(to_px(e["x"] + e["width"] / 2,
                                e["y"] + e["fontSize"] * line_height * (i + 0.5)),
                          line, font=f, fill=_colour(e.get("strokeColor"), "#333333"),
                          anchor="mm")
            else:
                draw.text(to_px(e["x"], e["y"] + e["fontSize"] * line_height * i),
                          line, font=f, fill=_colour(e.get("strokeColor"), "#333333"),
                          anchor="la")

    img.save(out_path)
    if skipped:
        print(f"  ⚠ 有 {sum(skipped.values())} 个元素没画出来：{skipped} "
              f"—— 预览**不完整**，别据此下结论", file=sys.stderr)
    return {"path": out_path, "size": [width, height],
            "content": [round(right - left, 1), round(bottom - top, 1)],
            "skipped": skipped,
            "elements": {"rectangles": len(rects), "ellipses": len(ellipses),
                         "diamonds": len(diamonds), "arrows": len(arrows),
                         "texts": len(texts)}}


def _dashed_line(draw, a, b, colour, width) -> None:
    total = math.dist(a, b)
    if total <= 0:
        return
    step = sum(DASH)
    walked = 0.0
    while walked < total:
        end = min(walked + DASH[0], total)
        t0, t1 = walked / total, end / total
        draw.line([(a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0),
                   (a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1)],
                  fill=colour, width=width)
        walked += step


def _arrow_head(draw, prev, tip, colour, scale) -> None:
    ang = math.atan2(tip[1] - prev[1], tip[0] - prev[0])
    length, half = ARROW_LEN * scale, ARROW_HALF_WIDTH * scale
    draw.polygon([
        tip,
        (tip[0] - length * math.cos(ang) + half * math.sin(ang),
         tip[1] - length * math.sin(ang) - half * math.cos(ang)),
        (tip[0] - length * math.cos(ang) - half * math.sin(ang),
         tip[1] - length * math.sin(ang) + half * math.cos(ang)),
    ], fill=colour)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="把 .excalidraw 渲染成 PNG（开发用，需要 PIL）")
    ap.add_argument("scene", help="*.excalidraw")
    ap.add_argument("out", nargs="?", help="输出 PNG（默认与场景同名）")
    ap.add_argument("--scale", type=float, default=1.0)
    args = ap.parse_args(argv)

    try:
        with open(args.scene, encoding="utf-8") as fh:
            scene = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"读不到场景：{exc}", file=sys.stderr)
        return 2

    out = args.out or os.path.splitext(args.scene)[0] + ".preview.png"
    try:
        info = render(scene, out, scale=args.scale)
    except ImportError:
        print("需要 PIL：pip install pillow（仅供开发预览，运行时不需要）", file=sys.stderr)
        return 3
    except OSError as exc:
        print(f"写不了 {out}：{exc}", file=sys.stderr)
        return 2

    # 汇总里**只列出现过的类型**，而且未画的元素单独占一行 —— 不静默省略。
    counts = " / ".join(f"{name} {n}" for name, n in
                        (("矩形", info["elements"]["rectangles"]),
                         ("椭圆", info["elements"]["ellipses"]),
                         ("菱形", info["elements"]["diamonds"]),
                         ("箭头", info["elements"]["arrows"]),
                         ("文字", info["elements"]["texts"])) if n)
    print(f"✓ {info['path']}  {info['size'][0]}×{info['size'][1]}px  "
          f"内容 {info['content'][0]}×{info['content'][1]}  {counts}")
    if info["skipped"]:
        print(f"  ⚠ 未画：{info['skipped']} —— 预览**不完整**，别据此下结论")
    print("  提示：这只反映我们自己的布局模型。'Excalidraw 渲染出来是否一致' "
          "必须在真实 Excalidraw 里看。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
