#!/usr/bin/env python3
"""Extract authored reading views with complete, auditable source coverage.

This does not infer which edges are important or merge relationships. The author
chooses questions and source edge indices; missing nodes/edges fail validation.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys


def _validator():
    spec = importlib.util.spec_from_file_location("_view_spec", Path(__file__).with_name("validate_spec.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _valid(spec, where):
    errors = _validator().validate(spec).errors
    if errors:
        raise ValueError(f"{where} 规格不合法：{errors}")


def build_views(source, plan):
    """Return (specs by name, receipt, original cards), leaving inputs intact."""
    _valid(source, "源图")
    if not isinstance(plan, dict) or set(plan) != {"version", "views"} or type(plan["version"]) is not int or plan["version"] != 1:
        raise ValueError("视图计划只接受 version=1 与 views")
    if not isinstance(plan["views"], list) or not plan["views"]:
        raise ValueError("views 必须为非空数组")
    nodes = {n["id"]: n for n in source["nodes"]}
    edges = source.get("edges", [])
    edge_coverage = {i: [] for i in range(len(edges))}
    node_coverage = {key: [] for key in nodes}
    output = {}
    allowed = {"name", "title", "question", "direction", "edges", "nodes", "ranks", "pins", "style"}
    for view in plan["views"]:
        if not isinstance(view, dict) or set(view) - allowed:
            raise ValueError("视图含未知字段")
        name = view.get("name")
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", name) or name in output:
            raise ValueError("视图 name 必须为唯一的小写英文/数字/连字符/下划线名称")
        for field in ("title", "question"):
            if not isinstance(view.get(field), str) or not view[field].strip():
                raise ValueError(f"{name} 需要非空 {field}")
        indices = view.get("edges", [])
        if not isinstance(indices, list) or any(type(i) is not int or not 0 <= i < len(edges) for i in indices):
            raise ValueError(f"{name}.edges 需要有效的源边数组下标（从 0 开始）")
        if len(indices) != len(set(indices)):
            raise ValueError(f"{name} 同一条边不应重复列出")
        explicit_nodes = view.get("nodes", [])
        if not isinstance(explicit_nodes, list) or any(not isinstance(n, str) or n not in nodes for n in explicit_nodes):
            raise ValueError(f"{name}.nodes 引用了未知节点")
        selected = set(explicit_nodes)
        for i in indices:
            selected.update((edges[i]["from"], edges[i]["to"]))
        ranks = view.get("ranks", {})
        if not isinstance(ranks, dict) or any(k not in selected or type(v) is not int or v < 0 for k, v in ranks.items()):
            raise ValueError(f"{name}.ranks 只能为本视图节点指定非负整数层级")
        pins = view.get("pins", {})
        if not isinstance(pins, dict) or any(k not in selected or v not in ("left", "right", "top", "bottom") for k, v in pins.items()):
            raise ValueError(f"{name}.pins 只能为本视图节点指定方向约束")
        spec = deepcopy(source)
        spec.update(title=view["title"], nodes=[deepcopy(n) for n in source["nodes"] if n["id"] in selected],
                    edges=[deepcopy(edges[i]) for i in indices])
        spec.pop("cards", None)
        # Each view asks its own question. Source pattern may not describe a
        # partial view, so preserve audience only, not an inferred pattern.
        spec["intent"] = {"question": view["question"]}
        if "audience" in source.get("intent", {}):
            spec["intent"]["audience"] = source["intent"]["audience"]
        for field in ("direction", "style"):
            if field in view:
                spec[field] = deepcopy(view[field])
        for node in spec["nodes"]:
            if node["id"] in ranks:
                node["rank"] = ranks[node["id"]]
            if node["id"] in pins:
                node["pin"] = pins[node["id"]]
        group_ids = {n.get("group") for n in spec["nodes"]}
        if "groups" in spec:
            spec["groups"] = [g for g in spec["groups"] if g["id"] in group_ids]
        _valid(spec, name)
        output[name] = spec
        for i in indices:
            edge_coverage[i].append(name)
        for node in selected:
            node_coverage[node].append(name)
    missing_edges = [i for i, views in edge_coverage.items() if not views]
    missing_nodes = [n for n, views in node_coverage.items() if not views]
    if missing_edges or missing_nodes:
        raise ValueError(f"拆图遗漏：边 {missing_edges}；节点 {missing_nodes}")
    digest = hashlib.sha256(json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    receipt = {"status": "complete-coverage", "source_canonical_sha256": digest,
               "nodes": [{"id": n, "views": views} for n, views in node_coverage.items()],
               "edges": [{"source_index": i, "edge": edges[i], "views": views} for i, views in edge_coverage.items()],
               "cards": deepcopy(source.get("cards", [])),
               "limits": ["只验证源规格覆盖，不证明业务事实或图的可读性；每张视图需布局检查，未做真实渲染审查时另行说明。",
                          "节点可跨图重复；rank/pin、方向、样式与读者问题可按计划改变，节点事实和边内容不改写。"]}
    return output, deepcopy(receipt), deepcopy(source.get("cards", []))


def colors_for_view(colors, spec):
    """Keep project colors consistent while excluding out-of-view ID mappings."""
    result = deepcopy(colors)
    for key, ids in (("by_node", {n["id"] for n in spec["nodes"]}),
                     ("by_group", {g["id"] for g in spec.get("groups", [])})):
        if key in result:
            result[key] = {k: v for k, v in result[key].items() if k in ids}
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--colors", type=Path)
    parser.add_argument("-o", "--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        source, plan = (json.loads(p.read_text()) for p in (args.source, args.plan))
        views, receipt, notes = build_views(source, plan)
        colors = json.loads(args.colors.read_text()) if args.colors else None
        if colors is not None:
            # Check against the complete source before filtering; do not hide typos.
            _validator().palette.use_colors(colors, spec=source)
        payloads = {"coverage.json": receipt, "notes.json": notes}
        for name, spec in views.items():
            payloads[name + ".diagram.json"] = spec
            if colors is not None:
                payloads[name + ".colors.json"] = colors_for_view(colors, spec)
        inputs = {p.resolve() for p in (args.source, args.plan, args.colors) if p is not None}
        collisions = [name for name in payloads if (args.out / name).resolve() in inputs]
        if collisions:
            raise ValueError(f"输出会覆盖源规格、计划或配色输入：{collisions}；请调整视图名或输出目录")
        args.out.mkdir(parents=True, exist_ok=True)
        for name, value in payloads.items():
            (args.out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        print(f"生成 {len(views)} 张视图规格；{len(source['nodes'])} 个节点、{len(source.get('edges', []))} 条边全部覆盖")
        return 0
    except (ValueError, OSError) as error:
        parser.exit(2, str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
