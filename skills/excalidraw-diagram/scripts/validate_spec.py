#!/usr/bin/env python3
"""规格校验 —— 检查模型写出来的 `*.diagram.json`。

这是**内容层**的校验（规格对不对），不是布局结果的校验（那是 `validation.md` 里那五项）。
两者分开，是因为修复动作完全不同：规格错了要改内容，布局不好要调参数。

## 字段集是**封闭**的（这条是核心设计）

未知字段直接判失败，而不是忽略。因为忽略的后果是：

> 有人"顺手加个可选 `x`/`y`" → 字段生效 → 模型开始填坐标 → 前作的病根原样复发。

前作 `draw-excalidraw` 的 schema 里就有 `nodes[].x` / `y` / `width` / `height`，
且 `layout.engine: "manual"` 会**直接用填的坐标**。所以这里宁可把字段集写死并拒绝未知项。

`kind` 的取值从 `palette.py` 读（唯一真相源），不从本文件或文档复述。

用法：
    python3 validate_spec.py spec.diagram.json
    python3 validate_spec.py spec.diagram.json --json

退出码：0 = 通过，1 = 有 error，2 = 读不到 / 不是合法 JSON。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys

# 封闭字段集。加字段要同时改这里和 references/diagram-spec.md —— 这正是设计意图：
# 让"顺手加一个"变得有摩擦。
TOP_FIELDS = {"type", "title", "direction", "detail", "groups", "nodes", "edges", "theme"}
GROUP_FIELDS = {"id", "label", "description"}
NODE_FIELDS = {"id", "label", "kind", "shape", "emphasis", "icon", "group",
               "detail", "rank", "pin"}
EDGE_FIELDS = {"id", "from", "to", "label", "kind"}

DIAGRAM_TYPES = {"architecture", "flow", "state", "dependency", "mindmap", "network"}
DIRECTIONS = {"LR", "TB"}
DETAIL_LEVELS = {"executive", "standard", "diagnostic"}
PINS = {"left", "right", "top", "bottom"}

# 刻意的空缺 —— 报错时给专门的说明，而不是只说"未知字段"
COORD_FIELDS = {"x", "y", "width", "height", "w", "h", "cx", "cy"}
LAYOUT_FIELDS = {"layout", "nodeSeparation", "rankSeparation", "barycenterRounds",
                 "margin", "marginx", "marginy", "spacing", "gap"}

DEPRECATION_HINTS = {
    "x": "坐标是刻意不存在的字段。一旦 schema 里有 x/y，模型就会开始填数字 —— "
         "而空间计算正是本 skill 要交给脚本的那部分。用 rank / pin 表达方向约束。",
    "y": "同上。用 rank / pin 表达方向约束，不要给坐标。",
    "layout": "布局参数只属于脚本，不属于规格。schema 里放着它，模型就会去填它 —— "
              "这是前作 `draw-excalidraw` 的失败之一。",
}


def _load_sibling(name: str):
    """动态加载同目录脚本（scripts/ 不是包，同级 import 在静态层面无法解析）。

    必须把模块注册进 sys.modules 之后再 exec：不注册的话，被加载模块里的
    `@dataclass` 会炸 —— dataclasses._is_type 会去查 sys.modules.get(cls.__module__)
    并拿到 None，报 "'NoneType' object has no attribute '__dict__'"。
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"_diagram_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了同目录模块：{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_palette = _load_sibling("palette")
KINDS = _palette.KINDS
EDGE_KINDS = _palette.EDGE_KINDS
SHAPES = _load_sibling("shapes").SHAPES
palette = _load_sibling("palette")
EMPHASIS = palette.EMPHASIS


class Issues:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def error(self, code: str, where: str, message: str) -> None:
        self.items.append({"level": "error", "code": code, "where": where, "message": message})

    def warn(self, code: str, where: str, message: str) -> None:
        self.items.append({"level": "warn", "code": code, "where": where, "message": message})

    @property
    def errors(self) -> list[dict]:
        return [i for i in self.items if i["level"] == "error"]


def _check_fields(obj: dict, allowed: set[str], where: str, issues: Issues) -> None:
    for key in obj:
        if key in allowed:
            continue
        extra = DEPRECATION_HINTS.get(key)
        if key in COORD_FIELDS:
            issues.error("COORD_FIELD", f"{where}.{key}",
                         extra or "坐标字段不存在是刻意的，用 rank / pin 代替。")
        elif key in LAYOUT_FIELDS:
            issues.error("LAYOUT_FIELD", f"{where}.{key}",
                         extra or "布局参数只属于脚本，不属于规格。")
        else:
            issues.error("UNKNOWN_FIELD", f"{where}.{key}",
                         f"未知字段 {key!r}；允许：{sorted(allowed)}")


def validate(spec: dict) -> Issues:
    issues = Issues()
    if not isinstance(spec, dict):
        issues.error("NOT_OBJECT", "$", "规格必须是一个 JSON 对象")
        return issues

    _check_fields(spec, TOP_FIELDS, "$", issues)

    # type
    dtype = spec.get("type")
    if dtype is None:
        issues.error("MISSING_TYPE", "$.type", "缺少必填字段 type")
    elif dtype not in DIAGRAM_TYPES:
        issues.error("BAD_TYPE", "$.type",
                     f"未知图类型 {dtype!r}；允许：{sorted(DIAGRAM_TYPES)}")

    if "direction" in spec and spec["direction"] not in DIRECTIONS:
        issues.error("BAD_DIRECTION", "$.direction",
                     f"direction 只允许 {sorted(DIRECTIONS)}")
    theme = spec.get("theme")
    if theme is not None and not palette.is_known_theme(theme):
        # 同 kind / shape 一条原则：不 fallback。静默换主题会让"风格"这件事
        # 变成"我明明写了 A 出来的是 B"，而且看图的人不知道为什么。
        issues.error("UNKNOWN_THEME", "$.theme",
                     f"未知主题 {theme!r}；可用的：{palette.available_themes()}"
                     f" 或 {palette.AUTO_THEME!r}（按图类型自己挑）")
    if "detail" in spec and spec["detail"] not in DETAIL_LEVELS:
        issues.error("BAD_DETAIL", "$.detail",
                     f"detail 只允许 {sorted(DETAIL_LEVELS)}")

    # groups
    group_ids: set[str] = set()
    groups = spec.get("groups", [])
    if not isinstance(groups, list):
        issues.error("BAD_GROUPS", "$.groups", "groups 必须是数组")
        groups = []
    for gi, g in enumerate(groups):
        where = f"$.groups[{gi}]"
        if not isinstance(g, dict):
            issues.error("BAD_GROUP", where, "group 必须是对象")
            continue
        _check_fields(g, GROUP_FIELDS, where, issues)
        gid = g.get("id")
        if not gid:
            issues.error("MISSING_GROUP_ID", where, "group 缺少 id")
        elif gid in group_ids:
            issues.error("DUPLICATE_GROUP_ID", where, f"group id 重复：{gid!r}")
        else:
            group_ids.add(gid)

    # nodes
    nodes = spec.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        issues.error("MISSING_NODES", "$.nodes", "nodes 必须是非空数组")
        nodes = []
    node_ids: set[str] = set()
    for ni, n in enumerate(nodes):
        where = f"$.nodes[{ni}]"
        if not isinstance(n, dict):
            issues.error("BAD_NODE", where, "node 必须是对象")
            continue
        _check_fields(n, NODE_FIELDS, where, issues)

        nid = n.get("id")
        if not nid:
            issues.error("MISSING_NODE_ID", where, "node 缺少 id")
        elif nid in node_ids:
            issues.error("DUPLICATE_NODE_ID", where, f"node id 重复：{nid!r}")
        else:
            node_ids.add(nid)

        if not n.get("label"):
            issues.error("MISSING_LABEL", where, f"node {nid!r} 缺少 label")

        kind = n.get("kind")
        if kind is None:
            issues.error("MISSING_KIND", where, f"node {nid!r} 缺少 kind")
        elif kind not in KINDS:
            # 判失败而不是 fallback —— fallback 会让"颜色必须在板内"这条校验自己绕过自己
            issues.error("UNKNOWN_KIND", f"{where}.kind",
                         f"未知 kind {kind!r}；允许的取值（色板唯一真相源）：{sorted(KINDS)}")

        shape = n.get("shape")
        if shape is not None and shape not in SHAPES:
            # 同 kind 一条原则：不 fallback。静默换成 rect 会让
            # “形状必须与语义有关”变成空话 —— 写错的人不知道，看图的人也看不出。
            issues.error("UNKNOWN_SHAPE", f"{where}.shape",
                         f"未知 shape {shape!r}；允许的取值：{sorted(SHAPES)}")

        emphasis = n.get("emphasis")
        if emphasis is not None and emphasis not in EMPHASIS:
            # 同 kind / shape 一条原则：不 fallback。
            issues.error("UNKNOWN_EMPHASIS", f"{where}.emphasis",
                         f"未知 emphasis {emphasis!r}；允许的取值：{sorted(EMPHASIS)}")

        icon = n.get("icon")
        if icon is not None and (not isinstance(icon, str) or not icon.strip()):
            # 只查"是个非空字符串" —— 素材库里有没有这个名字，要到出图时才知道
            # （那里才有库）。库没给却指定了图标，emit 会明确报错，不静默忽略。
            issues.error("BAD_ICON", f"{where}.icon",
                         "icon 必须是素材库里的项名（非空字符串）")

        grp = n.get("group")
        if grp is not None and grp not in group_ids:
            issues.error("UNKNOWN_GROUP", f"{where}.group",
                         f"node {nid!r} 指向未声明的 group {grp!r}；已声明：{sorted(group_ids)}")

        rank = n.get("rank")
        if rank is not None and (not isinstance(rank, int) or isinstance(rank, bool) or rank < 0):
            issues.error("BAD_RANK", f"{where}.rank", "rank 必须是非负整数")

        pin = n.get("pin")
        if pin is not None and pin not in PINS:
            issues.error("BAD_PIN", f"{where}.pin", f"pin 只允许 {sorted(PINS)}")

    # edges
    for ei, e in enumerate(spec.get("edges", []) or []):
        where = f"$.edges[{ei}]"
        if not isinstance(e, dict):
            issues.error("BAD_EDGE", where, "edge 必须是对象")
            continue
        _check_fields(e, EDGE_FIELDS, where, issues)
        for end in ("from", "to"):
            if not e.get(end):
                issues.error("MISSING_EDGE_END", where, f"edge 缺少 {end}")
            elif e[end] not in node_ids:
                issues.error("DANGLING_EDGE", f"{where}.{end}",
                             f"edge 指向不存在的 node {e[end]!r}")
        if e.get("from") and e.get("from") == e.get("to"):
            issues.error("SELF_LOOP", where, "edge 的起点和终点是同一个节点")
        ekind = e.get("kind")
        if ekind is not None and ekind not in EDGE_KINDS:
            issues.error("UNKNOWN_EDGE_KIND", f"{where}.kind",
                         f"未知边 kind {ekind!r}；允许：{sorted(EDGE_KINDS)}")

    return issues


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="校验 *.diagram.json 规格")
    ap.add_argument("spec", help="规格文件路径")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    try:
        with open(args.spec, encoding="utf-8") as fh:
            spec = json.load(fh)
    except OSError as exc:
        print(f"读不到规格文件：{exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"不是合法 JSON：{exc}", file=sys.stderr)
        return 2

    issues = validate(spec)

    if args.json:
        print(json.dumps({"spec": args.spec, "error_count": len(issues.errors),
                          "issues": issues.items}, ensure_ascii=False, indent=2))
        return 1 if issues.errors else 0

    if not issues.items:
        print("✓ 规格通过")
        return 0

    for it in issues.items:
        mark = "✗" if it["level"] == "error" else "·"
        print(f"  {mark} [{it['code']}] {it['where']}")
        print(f"      {it['message']}")

    print(f"\n{len(issues.errors)} 个 error，{len(issues.items) - len(issues.errors)} 个 warn")
    return 1 if issues.errors else 0


if __name__ == "__main__":
    sys.exit(main())
