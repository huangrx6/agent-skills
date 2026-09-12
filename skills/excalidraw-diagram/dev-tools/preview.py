#!/usr/bin/env python3
"""开发/校准用预览渲染器 —— 把 `.excalidraw` 画成 PNG，给人眼看。

## 这不是运行时的一部分

**用户用这个 skill 出图不需要它。** skill 的运行时链路是
`validate_spec → layout → check_layout → emit_excalidraw`，全是纯 stdlib，
不 import 本目录里的任何东西。这里只是给自己做**目视复核与阈值校准**时用的内部手段。

依赖：`PIL`（不在运行时依赖范围内 —— 装了就用，没装就不影响出图）。
放在 `dev-tools/` 而不是 `scripts/`，就是为了让「核心链路零依赖」这句话不被含糊掉。

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


def element_bounds(el: dict) -> tuple[float, float, float, float]:
    """元素的真实包围盒 (left, top, right, bottom)。

    **线性元素不能用 `x + width`** —— 它的 `x`/`y` 是首点，折线点可以向左/向上伸出，
    所以必须从 `points` 算。非线性的用 x/y/width/height。
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
    arrows = [e for e in elements if e["type"] in LINEAR_TYPES]
    texts = [e for e in elements if e["type"] == "text"]

    for e in rects:
        x0, y0 = to_px(e["x"], e["y"])
        x1, y1 = to_px(e["x"] + e["width"], e["y"] + e["height"])
        draw.rounded_rectangle([x0, y0, x1, y1], radius=8 * scale,
                               fill=e["backgroundColor"], outline=e["strokeColor"],
                               width=_px(2 * scale))

    for e in arrows:
        pts = [to_px(e["x"] + p[0], e["y"] + p[1]) for p in e["points"]]
        if len(pts) < 2:
            continue
        lw = _px(2 * scale)
        if e.get("strokeStyle") == "dashed":
            for a, b in zip(pts, pts[1:]):
                _dashed_line(draw, a, b, e["strokeColor"], lw)
        else:
            draw.line(pts, fill=e["strokeColor"], width=lw, joint="curve")
        if e.get("endArrowhead"):
            _arrow_head(draw, pts[-2], pts[-1], e["strokeColor"], scale)

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
                          line, font=f, fill=e["strokeColor"], anchor="mm")
            else:
                draw.text(to_px(e["x"], e["y"] + e["fontSize"] * line_height * i),
                          line, font=f, fill=e["strokeColor"], anchor="la")

    img.save(out_path)
    return {"path": out_path, "size": [width, height],
            "content": [round(right - left, 1), round(bottom - top, 1)],
            "elements": {"rectangles": len(rects), "arrows": len(arrows), "texts": len(texts)}}


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

    print(f"✓ {info['path']}  {info['size'][0]}×{info['size'][1]}px  "
          f"内容 {info['content'][0]}×{info['content'][1]}  "
          f"矩形 {info['elements']['rectangles']} / 箭头 {info['elements']['arrows']} / "
          f"文字 {info['elements']['texts']}")
    print("  提示：这只反映我们自己的布局模型。'Excalidraw 渲染出来是否一致' "
          "必须在真实 Excalidraw 里看。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
