#!/usr/bin/env python3
"""Review observable semantic omissions; never change or delete graph content.

0 = valid input (findings are advisory), 1 = findings with --strict,
2 = unreadable or invalid spec. Passing does not establish factual correctness.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys


def sibling(name):
    spec = importlib.util.spec_from_file_location(
        f"_semantic_{name}", Path(__file__).with_name(f"{name}.py"))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


AUTHORING = sibling("authoring")


def check(spec: dict) -> list[dict]:
    """Accept a structurally valid spec. Findings are prompts for author judgment."""
    findings = []

    def add(code, subject, message, fix, **evidence):
        findings.append({"code": f"semantic/{code}", "severity": "warning",
                         "subject": subject, "message": message,
                         "evidence": evidence, "suggestedFixes": [fix]})

    nodes, edges = spec["nodes"], spec.get("edges", [])
    outgoing = {n["id"]: [] for n in nodes}
    connected = set()
    for i, edge in enumerate(edges):
        outgoing[edge["from"]].append((i, edge))
        connected.update((edge["from"], edge["to"]))
        if spec["type"] == "state" and not edge.get("label", "").strip():
            add("unlabeled-transition", f"edges[{i}]", "状态转移没有触发事件或条件。",
                "根据来源补充事件、条件或动作；未知时明确待确认。",
                source=edge["from"], target=edge["to"])

    for node in nodes:
        nid = node["id"]
        branches = outgoing[nid]
        if spec["type"] == "flow" and node.get("shape") == "diamond":
            labels = [e.get("label", "").strip() for _, e in branches]
            if len(branches) < 2:
                add("decision-outcomes", nid, "判断节点不足两个出向结果。",
                    "核对是否漏分支；单一路径若并非判断，应使用动作节点。",
                    outgoing=len(branches))
            if any(not label for label in labels) or len(set(labels)) != len(labels):
                add("decision-labels", nid, "判断结果缺少标签或标签重复，路径难以区分。",
                    "按真实结果标注互相可区分的条件，不自动假定是/否。", labels=labels)
        if len(nodes) > 1 and nid not in connected:
            add("isolated-node", nid, "节点没有任何关系。它可能是漏连线，也可能是独立对象。",
                "核对来源并说明其独立原因；不要自动删除节点。")

    focus = [n["id"] for n in nodes if n.get("emphasis") == "primary"]
    if len(nodes) >= 3 and len(focus) > len(nodes) / 2:
        add("competing-focus", "nodes", "超过半数节点都被标为主要重点。",
            "检查阅读重点是否清楚；允许有依据的多焦点，不为达标删除重点。",
            primary=focus, total=len(nodes))

    if spec["type"] == "mindmap":
        incoming = {n["id"]: 0 for n in nodes}
        for edge in edges:
            incoming[edge["to"]] += 1
        roots = [nid for nid, count in incoming.items() if not count]
        # A forest plus a disconnected cycle can still have n-1 edges; explicitly
        # traverse so a circular component cannot masquerade as a rooted tree.
        visited, pending = set(), list(roots)
        while pending:
            nid = pending.pop()
            if nid in visited:
                continue
            visited.add(nid)
            pending.extend(e["to"] for _, e in outgoing[nid])
        if (len(roots) != 1 or any(count > 1 for count in incoming.values())
                or len(visited) != len(nodes) or len(edges) != len(nodes) - 1
                or roots[0] != nodes[0]["id"]):
            add("non-tree-mindmap", "edges", "关系不是以第一个节点为根的有向树。",
                "核对父子方向；真实多父关系或环改用 dependency/network，不删边凑树。",
                roots=roots, reachable=len(visited))

    pattern = spec.get("intent", {}).get("pattern")
    if pattern and AUTHORING.PATTERNS[pattern]["type"] != spec["type"]:
        add("pattern-type", "intent.pattern", "表达模式与当前图型不一致。",
            "核对读者要理解的问题，明确选择依据或调整图型。",
            pattern=pattern, recommended=AUTHORING.PATTERNS[pattern]["type"])
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true", help="发现提示时返回 1；不改图")
    args = parser.parse_args(argv)
    try:
        spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
        issues = sibling("validate_spec").validate(spec)
        if issues.errors:
            raise ValueError(json.dumps(issues.errors, ensure_ascii=False))
        findings = check(spec)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"无法检查：{exc}", file=sys.stderr)
        return 2
    result = {"findings": findings, "factual_verification": "not_performed"}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for item in findings:
            print(f"· {item['code']} {item['subject']}：{item['message']}")
        print(f"{len(findings)} 项审稿提示；未核验来源事实。")
    return 1 if findings and args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
