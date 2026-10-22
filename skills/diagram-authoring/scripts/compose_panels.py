#!/usr/bin/env python3
"""把多张已生成的 Excalidraw 图拼到同一张画布，用于横竖混排。

这不是复合布局：每个面板仍是独立、单轴的图，由各自的 `direction` 生成；
脚本只做平移、背景和元素 ID 隔离。跨面板连线不自动生成。

计划文件（路径相对计划文件所在目录）：

    {
      "version": 1,
      "layout": "row",
      "gap": 80,
      "padding": 24,
      "panels": [
        {"name": "main", "file": ".source/main.excalidraw"},
        {"name": "ops", "file": ".source/ops.excalidraw"}
      ]
    }

    python3 scripts/compose_panels.py .source/panels.json -o combined.excalidraw

先分别生成并检查每个面板，再合成；跨面板关系写进边标签或图外说明。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

PLAN_FIELDS = {"version", "layout", "gap", "padding", "panels"}
PANEL_FIELDS = {"name", "file"}
LAYOUTS = ("row", "column")
DEFAULT_GAP = 80.0
DEFAULT_PADDING = 24.0


def _load_sibling(name: str):
    path = os.path.join(HERE, f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"_compose_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了同目录模块：{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_plan(path: str) -> dict:
    """读计划文件；路径解析和字段校验交给 compose()。"""
    try:
        with open(path, encoding="utf-8") as handle:
            plan = json.load(handle)
    except OSError as error:
        raise ValueError(f"读不了计划文件 {path}：{error}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"计划文件不是合法 JSON：{error}") from error
    if not isinstance(plan, dict):
        raise ValueError("计划文件顶层必须是对象")
    return plan


def _as_float(value, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} 不是数字：{value!r}") from error


def _number(value, field: str, *, default: float) -> float:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"{field} 必须是非负数")
    return _as_float(value, field)


def _text(value, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ValueError(f"{field} 必须是非空字符串")
    return value.strip()


def _prefix(name: str) -> str:
    """把面板名变成安全的 ID 前缀；不同名字不能撞到同一个前缀。"""
    safe = re.sub(r"[^\w.-]+", "-", name, flags=re.UNICODE).strip("-.")
    return safe or "panel"


def _normalize_plan(plan: dict, base_dir: str) -> dict:
    if not isinstance(plan, dict):
        raise ValueError("计划文件顶层必须是对象")
    unknown = sorted(set(plan) - PLAN_FIELDS)
    if unknown:
        raise ValueError(f"计划文件有未知字段：{', '.join(unknown)}")
    if plan.get("version") != 1:
        raise ValueError("计划文件 version 必须是 1")

    layout = plan.get("layout", "row")
    if layout not in LAYOUTS:
        raise ValueError(f"layout 只允许 {LAYOUTS}")
    gap = _number(plan.get("gap"), "gap", default=DEFAULT_GAP)
    padding = _number(plan.get("padding"), "padding", default=DEFAULT_PADDING)

    raw_panels = plan.get("panels")
    if not isinstance(raw_panels, list) or not raw_panels:
        raise ValueError("panels 必须是非空数组")

    panels = []
    names: set[str] = set()
    prefixes: set[str] = set()
    for index, raw in enumerate(raw_panels):
        where = f"panels[{index}]"
        if not isinstance(raw, dict):
            raise ValueError(f"{where} 必须是对象")
        unknown = sorted(set(raw) - PANEL_FIELDS)
        if unknown:
            raise ValueError(f"{where} 有未知字段：{', '.join(unknown)}")
        name = _text(raw.get("name"), f"{where}.name")
        if name in names:
            raise ValueError(f"面板名重复：{name}")
        names.add(name)
        prefix = _prefix(name)
        if prefix in prefixes:
            raise ValueError(f"面板名转换成 ID 前缀后重复：{name} -> {prefix}")
        prefixes.add(prefix)

        file_name = _text(raw.get("file"), f"{where}.file")
        file_path = file_name if os.path.isabs(file_name) else os.path.join(base_dir, file_name)
        if not os.path.isfile(file_path):
            raise ValueError(f"找不到面板文件：{file_name}")
        panels.append({"name": name, "file": file_path, "prefix": prefix})

    return {"layout": layout, "gap": gap, "padding": padding, "panels": panels}


def _load_scene(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            scene = json.load(handle)
    except OSError as error:
        raise ValueError(f"读不了面板 {path}：{error}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"面板不是合法 JSON（{path}）：{error}") from error
    if not isinstance(scene, dict) or scene.get("type") != "excalidraw":
        raise ValueError(f"面板不是 Excalidraw 文件：{path}")
    elements = scene.get("elements")
    if not isinstance(elements, list) or not elements:
        raise ValueError(f"面板没有 elements：{path}")
    files = scene.get("files")
    if files is not None and not isinstance(files, dict):
        raise ValueError(f"面板 files 不是对象：{path}")
    return scene


def _element_bounds(element: dict) -> tuple[float, float, float, float]:
    x = _as_float(element.get("x", 0), "element.x")
    y = _as_float(element.get("y", 0), "element.y")
    width = max(0.0, _as_float(element.get("width", 0) or 0, "element.width"))
    height = max(0.0, _as_float(element.get("height", 0) or 0, "element.height"))
    points = element.get("points")
    if isinstance(points, list) and points:
        xs = [_as_float(point[0], "element.points[x]") for point in points
              if isinstance(point, (list, tuple)) and len(point) >= 2]
        ys = [_as_float(point[1], "element.points[y]") for point in points
              if isinstance(point, (list, tuple)) and len(point) >= 2]
        if xs and ys:
            return (x + min(0.0, min(xs)), y + min(0.0, min(ys)),
                    x + max(width, max(xs)), y + max(height, max(ys)))
    return x, y, x + width, y + height


def _scene_bounds(elements: list[dict]) -> tuple[float, float, float, float]:
    boxes = [_element_bounds(element) for element in elements
             if not element.get("isDeleted")]
    if not boxes:
        raise ValueError("面板没有可绘制的元素")
    return (min(box[0] for box in boxes), min(box[1] for box in boxes),
            max(box[2] for box in boxes), max(box[3] for box in boxes))


def _namespace(scene: dict, prefix: str) -> tuple[list[dict], dict]:
    """复用方向预览的 ID/引用重映射，并额外处理图片资源。"""
    preview = _load_sibling("direction_preview")
    elements = preview._namespace(scene.get("elements") or [], prefix)
    file_map = {str(key): f"{prefix}--{key}" for key in (scene.get("files") or {})}
    for element in elements:
        if element.get("fileId"):
            element["fileId"] = file_map.get(str(element["fileId"]), element["fileId"])
    files = {file_map[str(key)]: value for key, value in (scene.get("files") or {}).items()}
    return elements, files


def _shift(elements: list[dict], dx: float, dy: float) -> list[dict]:
    out = []
    for element in elements:
        copy = dict(element)
        copy["x"] = round(_as_float(copy.get("x", 0), "element.x") + dx, 2)
        copy["y"] = round(_as_float(copy.get("y", 0), "element.y") + dy, 2)
        out.append(copy)
    return out


def _background(prefix: str, x: float, y: float, width: float, height: float,
                colour: str, used_ids: set[str]) -> dict:
    element_id = f"{prefix}--panel-bg"
    while element_id in used_ids:
        element_id += "-x"
    used_ids.add(element_id)
    return {
        "type": "rectangle", "id": element_id,
        "x": round(x, 2), "y": round(y, 2),
        "width": round(width, 2), "height": round(height, 2),
        "angle": 0, "strokeColor": "#D8D4CE", "backgroundColor": colour or "#FFFFFF",
        "fillStyle": "solid", "strokeWidth": 1, "strokeStyle": "solid",
        "roughness": 0, "opacity": 100, "groupIds": [], "frameId": None,
        "roundness": {"type": 3}, "seed": 1, "version": 1,
        "versionNonce": 1, "isDeleted": False, "boundElements": [],
        "updated": 1, "link": None, "locked": False,
    }


def compose(plan: dict, base_dir: str | None = None) -> dict:
    """按计划合成场景。`base_dir` 用于解析相对文件路径。"""
    normalized = _normalize_plan(plan, base_dir or os.getcwd())
    scenes = []
    for panel in normalized["panels"]:
        scene = _load_scene(panel["file"])
        elements, files = _namespace(scene, panel["prefix"])
        bounds = _scene_bounds(elements)
        scenes.append({
            "panel": panel,
            "elements": elements,
            "files": files,
            "bounds": bounds,
            "width": bounds[2] - bounds[0],
            "height": bounds[3] - bounds[1],
        })

    padding = normalized["padding"]
    gap = normalized["gap"]
    layout = normalized["layout"]
    if layout == "row":
        total_width = sum(scene["width"] + 2 * padding for scene in scenes) + gap * (len(scenes) - 1)
        total_height = max(scene["height"] + 2 * padding for scene in scenes)
    else:
        total_width = max(scene["width"] + 2 * padding for scene in scenes)
        total_height = sum(scene["height"] + 2 * padding for scene in scenes) + gap * (len(scenes) - 1)

    elements: list[dict] = []
    files: dict = {}
    cursor = 0.0
    used_ids = {element["id"] for scene in scenes for element in scene["elements"]}
    for scene in scenes:
        outer_width = scene["width"] + 2 * padding
        outer_height = scene["height"] + 2 * padding
        panel_x = cursor if layout == "row" else 0.0
        panel_y = 0.0 if layout == "row" else cursor
        colour = _scene_bg(scene)
        elements.append(_background(scene["panel"]["prefix"], panel_x, panel_y,
                                    outer_width, outer_height, colour, used_ids))
        dx = panel_x + padding - scene["bounds"][0]
        dy = panel_y + padding - scene["bounds"][1]
        elements.extend(_shift(scene["elements"], dx, dy))
        files.update(scene["files"])
        cursor += (outer_width if layout == "row" else outer_height) + gap

    return {
        "type": "excalidraw",
        "version": 2,
        "source": "diagram-authoring/compose_panels.py",
        "elements": elements,
        "appState": {
            "gridSize": None,
            "viewBackgroundColor": "#FFFFFF",
            "width": math.ceil(total_width),
            "height": math.ceil(total_height),
        },
        "files": files,
    }


def _scene_bg(scene: dict) -> str:
    """面板自己的画布色；合成本身只有一个全局底色。"""
    return str((scene.get("appState") or {}).get("viewBackgroundColor") or "#FFFFFF")


def _write(path: str, scene: dict) -> None:
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(scene, handle, ensure_ascii=False, indent=2)
    except OSError as error:
        raise ValueError(f"写不出 {path}：{error}") from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="把多张 Excalidraw 图按 row/column 拼到同一张画布")
    parser.add_argument("plan", help="panels 计划 JSON")
    parser.add_argument("-o", "--out", default="combined.excalidraw",
                        help="输出 .excalidraw 路径")
    args = parser.parse_args(argv)

    try:
        plan = load_plan(args.plan)
        scene = compose(plan, os.path.dirname(os.path.abspath(args.plan)))
        _write(args.out, scene)
    except ValueError as error:
        print(f"合成失败：{error}", file=sys.stderr)
        return 2

    print(f"已写出 {args.out}")
    print(f"面板：{len(plan['panels'])}；画布：{scene['appState']['width']} × "
          f"{scene['appState']['height']}")
    print("面板仍然是独立布局；跨面板连线没有自动生成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
