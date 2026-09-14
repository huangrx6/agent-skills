#!/usr/bin/env python3
"""`.drawio` 的结构自检：**打不开的图要在这里被拦住**。

官方有 `mxfile.xsd`（jgraph 发的），这里**刻意不 vendor**：多一个第三方文件就多一处要
同步的源，而真正会让人吃亏的只有下面这几条结构事实。想换成 xsd 校验随时可以，
但那要连"xsd 变了怎么发现"一起解决，那是另一件事。

要守的事实
----------
1. `<root>` 里必须有 `id="0"` 与 `id="1"` 两个结构 cell —— 少了 draw.io 直接说文件损坏
2. 每个 cell 的 `id` 唯一（重复 id 的图能打开，但拖动会串）
3. 每个 cell 的 `parent` 指向一个存在的 id
4. `vertex` / `edge` cell 必须有 `<mxGeometry>`，且数值是有限数
5. 边给了 `source` / `target` 的话，必须指向存在的 **vertex**
6. `<mxGeometry>` 的宽高必须 > 0（0 尺寸的元素点不中、也看不见）

**压缩过的文件不解**：draw.io 应用保存时默认把 `<diagram>` 的内容压缩成 base64。
那不是一个可以"顺手支持一下"的格式（要 zlib + urllib 解 base64 + 再解析），
所以这里明确报出来，而不是当空文件放行 —— 静默放行是最坏的一种做法。
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import xml.etree.ElementTree as ET
from typing import Any

REQUIRED_IDS = ("0", "1")
ROOT_TAG = "root"


def _diagrams(root: ET.Element) -> list[ET.Element]:
    return [element for element in root.iter("diagram")]


def check_text(text: str) -> list[str]:
    """检查一段 mxfile XML 文本，返回问题列表（空 = 通过）。"""
    problems: list[str] = []
    if not text.strip():
        return ["文件是空的"]
    try:
        root = ET.fromstring(text)  # noqa: S314 - 本地自检工具，输入是自己生成的文件
    except ET.ParseError as exc:
        return [f"XML 解析失败：{exc}"]

    diagrams = _diagrams(root)
    if not diagrams:
        problems.append("没有 <diagram> 元素")
    for diagram in diagrams:
        name = diagram.get("name") or "?"
        models = list(diagram.iter("mxGraphModel"))
        if not models:
            inner = (diagram.text or "").strip()
            if inner and "<" not in inner[:1]:
                problems.append(
                    f"<diagram name=\"{name}\"> 的内容是压缩过的（app 保存的默认形态）—— "
                    "本 checker 不解压。要检查就先在 draw.io 里另存为未压缩，"
                    "或者用 emit 重新生成一份")
            else:
                problems.append(f"<diagram name=\"{name}\"> 里没有 <mxGraphModel>")
            continue
        for model in models:
            problems += _check_model(model, name)

    return problems


def _finite(value: str | None) -> float | None:
    """能当成有限数就返回它，否则 None（NaN / ±inf 都算不行 —— 它们会画成看不见的元素）。"""
    if value is None:
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _check_model(model: ET.Element, diagram_name: str) -> list[str]:
    problems: list[str] = []
    roots = [element for element in model.iter(ROOT_TAG)]
    if not roots:
        return [f"[{diagram_name}] 没有 <root>"]
    root = roots[0]
    cells = [element for element in root if element.tag == "mxCell"]
    by_id: dict[str, ET.Element] = {}
    for cell in cells:
        cell_id = cell.get("id")
        if cell_id is None:
            problems.append(f"[{diagram_name}] 有一个 cell 没有 id")
            continue
        if cell_id in by_id:
            problems.append(f"[{diagram_name}] id 重复：{cell_id}")
        by_id[cell_id] = cell

    for required in REQUIRED_IDS:
        if required not in by_id:
            problems.append(
                f"[{diagram_name}] 缺少结构 cell id=\"{required}\" —— "
                "draw.io 会直接说文件损坏")

    vertex_ids = {cid for cid, cell in by_id.items() if cell.get("vertex")}
    for cell_id, cell in by_id.items():
        parent = cell.get("parent")
        if parent is not None and parent not in by_id:
            problems.append(f"[{diagram_name}] cell {cell_id} 的 parent={parent} 不存在")
        if cell.get("edge"):
            for side in ("source", "target"):
                ref = cell.get(side)
                if ref is not None and ref not in vertex_ids:
                    problems.append(
                        f"[{diagram_name}] 边 {cell_id} 的 {side}={ref} 不是存在的节点")
        is_vertex = bool(cell.get("vertex"))
        is_edge = bool(cell.get("edge"))
        if not (is_vertex or is_edge):
            continue
        geometry = cell.find("mxGeometry")
        if geometry is None:
            problems.append(f"[{diagram_name}] cell {cell_id} 没有 <mxGeometry>")
            continue
        if is_edge:
            # 边的几何是**相对**的：没有 x/y/width/height，路由由 source/target 与
            # 折点决定。要求它带宽高是错的（第一版本 checker 就是这么错的）。
            for point in geometry.iter("mxPoint"):
                for field in ("x", "y"):
                    raw = point.get(field)
                    if raw is None or _finite(raw) is None:
                        problems.append(
                            f"[{diagram_name}] 边 {cell_id} 的折点 {field}={raw!r} 不是有限数")
            continue
        for field in ("x", "y", "width", "height"):
            raw = geometry.get(field)
            if raw is None:
                problems.append(f"[{diagram_name}] cell {cell_id} 的 mxGeometry 缺 {field}")
            elif _finite(raw) is None:
                problems.append(
                    f"[{diagram_name}] cell {cell_id} 的 mxGeometry.{field}={raw!r} 不是有限数")
        for field in ("width", "height"):
            value = _finite(geometry.get(field))
            if value is not None and value <= 0:
                problems.append(f"[{diagram_name}] cell {cell_id} 的 {field} = {value}（必须 > 0）")
    return problems


def check_file(path: str) -> list[str]:
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        return [f"读不到 {path}：{exc}"]
    return check_text(text)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=".drawio 结构自检（打不开的图在这里拦住）")
    ap.add_argument("path", nargs="+", help="一个或多个 .drawio")
    args = ap.parse_args(argv)

    total = 0
    for path in args.path:
        problems = check_file(path)
        name = os.path.basename(path)
        if problems:
            total += len(problems)
            print(f"✗ {name}")
            for problem in problems:
                print(f"  - {problem}")
        else:
            print(f"✓ {name}")
    if total:
        print(f"\n共 {total} 个问题。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
