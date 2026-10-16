#!/usr/bin/env python3
"""Estimate text readability in a viewing preset from this skill's editable output.

Reads generated Excalidraw JSON or draw.io XML (including compressed pages). Does not render,
resize, alter files or claim pixel accuracy. Review every page of draw.io output.
0 = no size finding (fit = no target assessment), 1 = undersized text,
2 = unsupported/unmeasurable input. Pixel density is not viewing size.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


def vocabulary():
    module_spec = importlib.util.spec_from_file_location(
        "_presentation_authoring", Path(__file__).with_name("authoring.py"))
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


A = vocabulary()


def number(value):
    if isinstance(value, bool):
        raise ValueError("几何与字号必须是有限数值")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("几何与字号必须是有限数值")
    return result


def extent(points):
    if not points:
        raise ValueError("没有可测量的内容")
    xs, ys = zip(*points)
    width, height = max(xs) - min(xs), max(ys) - min(ys)
    if width <= 0 or height <= 0:
        raise ValueError("内容尺寸必须大于零")
    return width, height


def excalidraw(source):
    scene = json.loads(source)
    if not isinstance(scene, dict) or scene.get("type") != "excalidraw":
        raise ValueError("需要 Excalidraw 场景")
    points, fonts = [], []
    for el in scene["elements"]:
        if el.get("isDeleted"):
            continue
        if number(el.get("angle", 0)) != 0:
            raise ValueError("旋转元素暂不可测量，请用真实渲染审查")
        x, y = number(el["x"]), number(el["y"])
        if el.get("type") in {"arrow", "line"}:
            points.extend((x + number(p[0]), y + number(p[1])) for p in el["points"])
        else:
            points.extend([(x, y), (x + number(el["width"]), y + number(el["height"]))])
        if el.get("type") == "text" and el.get("text", "").strip():
            fonts.append((el["id"], number(el["fontSize"])))
    return [("scene", extent(points), fonts)]


def drawio(source):
    if "<!DOCTYPE" in source.upper() or "<!ENTITY" in source.upper():
        raise ValueError("不接受 XML 文档类型或实体声明")
    module_spec = importlib.util.spec_from_file_location("_presentation_drawio_xml", Path(__file__).with_name("drawio_xml.py"))
    codec = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(codec)
    root = codec.parse(source)
    pages = []
    for page in root.findall("diagram"):
        model = page.find("mxGraphModel/root")
        if model is None:
            raise ValueError("draw.io 页缺少模型")
        points, fonts = [], []
        parents = {child: parent for parent in model.iter() for child in parent}
        vertex_ids = {element.get("id") for element in model if element.get("vertex") == "1" or (element.find("mxCell") is not None and element.find("mxCell").get("vertex") == "1")}
        for cell in model.iter("mxCell"):
            geo = cell.find("mxGeometry")
            if geo is None:
                continue
            style = dict(part.split("=", 1) for part in cell.get("style", "").split(";") if "=" in part)
            if number(style.get("rotation", 0)) != 0:
                raise ValueError("旋转单元格暂不可测量")
            if cell.get("parent") in vertex_ids:
                raise ValueError("嵌套分组中的相对坐标暂不可测量，请做实际渲染审查")
            if cell.get("vertex") == "1":
                if geo.get("relative") == "1":
                    raise ValueError("相对定位节点暂不可测量")
                x, y = number(geo.get("x", 0)), number(geo.get("y", 0))
                points.extend([(x, y), (x + number(geo.get("width", 0)),
                                       y + number(geo.get("height", 0)))])
            for point in geo.findall(".//mxPoint"):
                if point.get("as") != "offset":
                    points.append((number(point.get("x", 0)), number(point.get("y", 0))))
            parent = parents[cell]
            label = parent.get("label", "") if parent.tag in ("UserObject", "object") else cell.get("value", "")
            if label.strip():
                if "fontSize" not in style:
                    raise ValueError("标签缺少显式字号，无法可靠估算")
                fonts.append((parent.get("id", cell.get("id", "?")), number(style["fontSize"])))
                # The preset-aware emitter uses explicit secondary text spans.
                for i, size in enumerate(re.findall(r'<span style="font-size:([\d.]+)px">', label)):
                    fonts.append((parent.get("id", cell.get("id", "?")) + f":span-{i}", number(size)))
        pages.append((page.get("name", page.get("id", "page")), extent(points), fonts))
    if not pages:
        raise ValueError("没有可测量的页面")
    return pages


def assess(pages, preset):
    config = A.PRESETS[preset]
    results = []
    for name, (width, height), fonts in pages:
        if not fonts or any(size <= 0 for _, size in fonts):
            raise ValueError("没有有效文字或字号不大于零")
        ratios = []
        for axis, size in (("width", width), ("height", height)):
            if config[axis]:
                ratios.append((config[axis] - 2 * config["padding"]) / size)
        # A larger screenshot does not make text larger at its intended viewing
        # size; never invent enlargement to rescue an unreadable source figure.
        scale = min([1.0, *ratios])
        minimum = config["min_text"]
        small = [{"id": ident, "source_px": size, "viewing_px": round(size * scale, 2)}
                 for ident, size in fonts if minimum and size * scale < minimum]
        results.append({"page": name, "content_size": [round(width, 2), round(height, 2)],
                        "fit_scale": round(scale, 4), "min_viewing_px": round(min(v for _, v in fonts) * scale, 2),
                        "undersized": small,
                        "status": "not_assessed" if minimum is None else "warning" if small else "pass"})
    return {"preset": preset, "target": dict(config), "basis": "editable_geometry_estimate",
            "render_verified": False, "pages": results,
            "advice": "文字过小时拆视图、缩短非必要说明或在编辑器调整字号并重新布局；提高 PNG 倍率不能提高观看字号。"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact")
    parser.add_argument("--preset", choices=tuple(A.PRESETS), default="doc-inline")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        path = Path(args.artifact)
        source = path.read_text(encoding="utf-8")
        if path.suffix == ".excalidraw":
            pages = excalidraw(source)
        elif path.suffix == ".drawio":
            pages = drawio(source)
        else:
            raise ValueError("只接受 .excalidraw 或 .drawio")
        result = assess(pages, args.preset)
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, IndexError, AttributeError, ET.ParseError) as exc:
        print(f"无法估算：{exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for page in result["pages"]:
            print(f"{page['page']}：{page['status']}，预计最小观看字号 {page['min_viewing_px']}px")
        print(result["advice"])
        print("仅可编辑文件几何估算；尚未核验真实字体、裁切和渲染。")
    return int(any(page["status"] == "warning" for page in result["pages"]))


if __name__ == "__main__":
    sys.exit(main())
