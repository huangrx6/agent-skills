#!/usr/bin/env python3
"""把几个视觉方向画成一张并排的对照图 —— 给用户**挑方向用**的。

## 为什么需要它

主题名（`soft-light` / `clean-light` / `dark`）说明不了什么 —— 用户要看了才知道喜不喜欢。
以前的做法是"模型替用户选一个然后生成"，于是经常生成完才发现颜色不是他要的，
再改一次的成本比先看一眼高得多。

**用法**：出图之前跑一次，把生成的文件给用户看，让他挑；他指定了就照做。

    python3 scripts/direction_preview.py -o /tmp/directions.excalidraw
    # 然后在 Obsidian 或 excalidraw.com 里打开

并排几块用**同一张样例图**：同一组节点、同一种布局，只有主题不同 ——
不然"哪个更好看"会被内容和版式的差异盖住。

## 一个实现上的坑

Excalidraw 的 `viewBackgroundColor` 是**整个文件一个**，没法每个面板不同。
而这里的方向有深有浅 —— 直接合并会让深色主题看起来像坏掉了。
所以每个面板自己带一块**画布色的底矩形**，深色主题就不会被白底吞掉。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

PANEL_GAP = 80.0        # 面板之间的空档
LABEL_GAP = 40.0        # 标题在面板上方的距离

# 样例图：故意覆盖全部 5 个层级，这样一张对照图就能看出每个主题的完整色阶。
SAMPLE: dict = {
    "type": "architecture",
    "direction": "LR",
    "title": "示例：下单链路",
    "visual": "auto",        # 走 AUTO：按图类型和用户意图自己挑方向
    "nodes": [
        {"id": "web", "kind": "client", "label": "Web 前端"},
        {"id": "gw", "kind": "security", "label": "API 网关"},
        {"id": "order", "kind": "service", "label": "订单服务", "emphasis": "primary"},
        {"id": "risk", "kind": "plain", "label": "风控校验"},
        {"id": "db", "kind": "data", "label": "订单库"},
        {"id": "mq", "kind": "async", "label": "事件队列"},
        {"id": "pay", "kind": "external", "label": "支付网关"},
        {"id": "bad", "kind": "plain", "label": "对账失败", "emphasis": "critical"},
    ],
    "edges": [
        {"from": "web", "to": "gw", "label": "HTTPS"},
        {"from": "gw", "to": "order"},
        {"from": "order", "to": "risk"},
        {"from": "order", "to": "db", "kind": "data"},
        {"from": "order", "to": "mq", "kind": "async"},
        {"from": "order", "to": "pay"},
        {"from": "risk", "to": "bad", "kind": "optional"},
    ],
}


def _load(name: str):
    path = os.path.join(HERE, f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"_preview_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了同目录模块：{path}")
    module = importlib.util.module_from_spec(spec)
    # 先注册再 exec —— 否则被加载模块里的 @dataclass 会炸（这个坑踩过）
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build(directions: list[str] | None = None) -> dict:
    """生成一张含 N 个面板的场景。返回 Excalidraw 文件结构。"""
    palette = _load("palette")
    emit = _load("emit_excalidraw")

    names = directions or palette.available_directions()
    elements: list[dict] = []
    x_cursor = 0.0
    tallest = 0.0

    for index, direction in enumerate(names):
        with palette.direction_context(direction):
            scene, _placed, outcome, _ = emit.emit(dict(SAMPLE))
            canvas = palette.CANVAS["background"]
            width = scene["appState"].get("width", 0) or _span(
                scene["elements"], "x", "width")
            height = scene["appState"].get("height", 0) or _span(
                scene["elements"], "y", "height")

            panel = _namespace(scene["elements"], direction)
            if index:                       # 第 0 块不动，其余整体右移
                for element in panel:
                    element["x"] = round(element["x"] + x_cursor, 2)
            # 面板自己的底色（见模块 docstring：一个文件只能有一个画布色）
            elements.append(_panel_background(direction, x_cursor, width, height))
            elements.append(_panel_label(direction, x_cursor + width / 2, -LABEL_GAP))
            elements.extend(panel)
            if outcome.blocking:
                # 预览脚本不该静默吞掉校验失败 —— 那样"图看起来还行"会骗人
                raise RuntimeError(
                    f"{direction} 出图有阻塞项：{[i.line() for i in outcome.blocking]}")
            x_cursor += width + PANEL_GAP
            tallest = max(tallest, height)

    return {
        "type": "excalidraw",
        "version": 2,
        "source": "diagram-authoring/direction_preview.py",
        "elements": elements,
        "appState": {"gridSize": None, "viewBackgroundColor": "#FFFFFF",
                     # round 而不是 int：这两个数来自自己的布局运算，不是外部输入
                     "width": round(x_cursor), "height": round(tallest)},
        "files": {},
    }


def _namespace(elements: list[dict], direction: str) -> list[dict]:
    """把这一面板所有元素的 id（**连同内部引用**）加上主题前缀。

    为什么必须做：三个面板走的是同一个 `emit()`，节点 id 全一样（`node-web`…）。
    Excalidraw 里 id 重复会让元素互相覆盖 —— 脚本会正常打印"已写出"，
    但打开只能看到一个面板。这就是"跑通了 ≠ 产物是对的"。

    要一起重映射的引用：`containerId`（绑到容器的文字）、`boundElements`（反向）、
    箭头两端的 `startBinding` / `endBinding`。少改一处就是一个悬空引用。
    """
    mapping = {e["id"]: f"{direction}--{e['id']}" for e in elements}
    out = []
    for element in elements:
        copy = dict(element)
        copy["id"] = mapping[element["id"]]
        if copy.get("containerId"):
            copy["containerId"] = mapping.get(copy["containerId"], copy["containerId"])
        if copy.get("frameId"):
            copy["frameId"] = mapping.get(copy["frameId"], copy["frameId"])
        if copy.get("boundElements"):
            copy["boundElements"] = [
                {**item, "id": mapping.get(item["id"], item["id"])}
                for item in copy["boundElements"]]
        for key in ("startBinding", "endBinding"):
            binding = copy.get(key)
            if binding and binding.get("elementId"):
                copy[key] = {**binding,
                             "elementId": mapping.get(binding["elementId"],
                                                      binding["elementId"])}
        out.append(copy)
    return out


def _span(elements: list[dict], axis: str, size: str) -> float:
    lo = min(e[axis] for e in elements)
    hi = max(e[axis] + e.get(size, 0) for e in elements)
    return hi - lo


def _make_id(kind: str, direction: str) -> str:
    """面板元素的 id。用**主题名**而不是数字 —— 同一个主题在一个文件里只出现一次，
    天然唯一，也就省掉了 int() 转换（int() 对非法输入会抛，而这里本来不需要数字）。"""
    return f"panel-{kind}-{direction}"


def _panel_background(direction: str, x: float, width: float, height: float) -> dict:
    palette = _load("palette")
    with palette.direction_context(direction):
        colour = palette.CANVAS["background"]
        ink = palette.CANVAS["text"]
    return {
        "type": "rectangle", "id": _make_id("bg", direction),
        "x": round(x - 20, 2), "y": -20.0,
        "width": round(width + 40, 2), "height": round(height + 40, 2),
        "angle": 0, "strokeColor": ink, "backgroundColor": colour,
        "fillStyle": "solid", "strokeWidth": 1, "strokeStyle": "solid",
        "roughness": 0, "opacity": 100, "groupIds": [], "frameId": None,
        "roundness": {"type": 3}, "seed": 1, "version": 1,
        "versionNonce": 1, "isDeleted": False, "boundElements": [],
        "updated": 1, "link": None, "locked": False,
    }


def _panel_label(direction: str, centre_x: float, y: float) -> dict:
    palette = _load("palette")
    text = f"{direction}（{palette.VISUAL_DIRECTIONS[direction]['zh']}）"
    width = len(text) * 12.0
    return {
        "type": "text", "id": _make_id("label", direction), "text": text,
        "x": round(centre_x - width / 2, 2), "y": round(y, 2),
        "width": round(width, 2), "height": 24.0, "angle": 0,
        "fontSize": 20, "fontFamily": 2, "textAlign": "center",
        "verticalAlign": "top", "containerId": None, "originalText": text,
        "autoResize": True, "lineHeight": 1.25, "strokeColor": "#4A4744",
        "backgroundColor": "transparent", "fillStyle": "solid",
        "strokeWidth": 1, "strokeStyle": "solid", "roughness": 0,
        "opacity": 100, "groupIds": [], "frameId": None,
        "roundness": None, "seed": 1, "version": 1, "versionNonce": 1,
        "isDeleted": False, "boundElements": [], "updated": 1,
        "link": None, "locked": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成几个视觉方向的并排对照图")
    parser.add_argument("-o", "--out", default="direction-preview.excalidraw")
    parser.add_argument("--directions", nargs="*", default=None,
                        help="默认全部；也可以只预览其中几个")
    args = parser.parse_args(argv)

    scene = build(args.directions)
    try:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(scene, handle, ensure_ascii=False, indent=2)
    except OSError as error:
        print(f"写不出 {args.out}：{error}", file=sys.stderr)
        return 1

    palette = _load("palette")
    print(f"已写出 {args.out}")
    print("可用视觉方向：" + "、".join(
        f"{name}（{palette.VISUAL_DIRECTIONS[name]['zh']}）"
        for name in palette.available_directions()))
    print("打开看：把它拖进 Obsidian，或者用 scripts/open_excalidraw_com.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
