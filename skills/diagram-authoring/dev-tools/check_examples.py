#!/usr/bin/env python3
"""Check example inventory and source/artifact freshness, not aesthetic quality.

Run after regenerating examples and recording actual visual review. A matching
hash proves file identity only; it does not perform rendering or review itself.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


def verify(skill: Path, manifest: dict) -> list[str]:
    problems = []
    skill = skill.resolve()

    def check_file(relative, expected):
        path = (skill / relative).resolve()
        if not path.is_relative_to(skill):
            problems.append(f"不允许库外路径：{relative}")
            return
        if not path.is_file():
            problems.append(f"缺少文件：{relative}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            problems.append(f"内容已变化，需重新生成或审查：{relative}")

    if manifest.get("schema_version") != 1:
        problems.append("未知清单版本")
    required_inputs = {"scripts/emit_excalidraw.py", "scripts/emit_drawio.py", "scripts/layout.py",
                       "scripts/check_semantics.py", "scripts/check_presentation.py", "scripts/authoring.py",
                       "scripts/presentation.py", "scripts/color_design.py", "scripts/palette.py",
                       "dev-tools/check_render.py", "dev-tools/render_probe.js"}
    if not required_inputs.issubset(manifest.get("generator_inputs", {})):
        problems.append("清单缺少关键生成器或检查器版本")
    for path, sha in manifest.get("generator_inputs", {}).items():
        check_file(path, sha)
    cases = manifest.get("examples", [])
    names = [case.get("type") for case in cases]
    if sorted(names) != sorted(["architecture", "dependency", "flow", "state", "mindmap", "network"]):
        problems.append("必须覆盖六类图型且没有重复")
    for case in cases:
        files = case.get("files", {})
        prefix = f"examples/{case['type']}/"
        for suffix in ("source.diagram.json", "diagram.excalidraw", "diagram.drawio", "drawio.png",
                       "generation.json", "render.json", "semantics.json", "presentation.json"):
            if prefix + suffix not in files:
                problems.append(f"清单缺少必要产物：{prefix + suffix}")
        for path, sha in files.items():
            check_file(path, sha)
        if case.get("visual_review", {}).get("drawio", {}).get("status") != "reviewed":
            problems.append(f"{case['type']} 的 draw.io 目视审查尚未完成")
        if case.get("visual_review", {}).get("excalidraw", {}).get("status") == "reviewed":
            for suffix in ("excalidraw.png", "render-excalidraw.json"):
                if prefix + suffix not in files:
                    problems.append(f"Excalidraw 审查缺少渲染证据：{prefix + suffix}")
    for variant in manifest.get("variants", []):
        for path, sha in variant.get("files", {}).items():
            check_file(path, sha)
        for item in variant.get("renders", []):
            if item.get("visual_review") != "reviewed":
                problems.append(f"场景样例尚未目视审查：{item.get('artifact')}")
            for key in ("artifact", "svg", "png", "check"):
                if item.get(key) not in variant.get("files", {}):
                    problems.append(f"场景样例清单缺少 {key}：{item.get(key)}")
            report_path = (skill / item["check"]).resolve()
            if not report_path.is_relative_to(skill) or not report_path.is_file():
                continue
            report = json.loads(report_path.read_text())
            if report.get("status") != "pass":
                problems.append(f"场景样例真实渲染检查未通过：{item['check']}")
            for key, hash_key in (("artifact", "source_sha256"), ("svg", "svg_sha256")):
                if report.get(hash_key) != variant.get("files", {}).get(item[key]):
                    problems.append(f"检查回执与当前产物不一致：{item[key]}")
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    try:
        data = json.loads((args.skill / "examples/manifest.json").read_text(encoding="utf-8"))
        problems = verify(args.skill, data)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"无法验证清单：{exc}", file=sys.stderr)
        return 2
    for problem in problems:
        print(problem)
    if not problems:
        print("六类样例及场景对照与生成器/产物哈希一致；本检查未重新渲染或目视审查。")
    return int(bool(problems))


if __name__ == "__main__":
    sys.exit(main())
