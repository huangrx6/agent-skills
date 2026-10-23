#!/usr/bin/env python3
"""Quality gate for learning-scout notes.

Checks what the renderer cannot: required sections, source-code evidence,
independence and environment leakage. Length is advisory: it only warns when a
note is far from the reference range, so authors are not pushed to pad.
Reads plan.json (v2) to know each note's `kind`.

Usage:
    python3 scripts/check_notes.py --plan plan.json
    python3 scripts/check_notes.py --plan plan.json --strict
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# 参考区间（低, 高）；低于低值的 60% 才提示“偏薄”，不直接判错。
RANGES = {
    "concept": (220, 400),
    "mechanism": (320, 520),
    "practice": (320, 520),
    "source-review": (450, 650),
}

# 跨篇引用：正文不得依赖同系列或库内其他文章。
CROSS_REFS = re.compile(
    r"(上一篇|下一篇|前一篇|后一篇|见第\s*\d+\s*篇|本系列第\s*\d+|参见第\s*\d+\s*篇|"
    r"见另一篇|详见另一篇|另一篇笔记|其他笔记|其他文章)"
)
PERSONAL_PATHS = re.compile(r"(/Users/[^/\s]+|/home/[^/\s]+|[A-Z]:\\\\Users\\\\[^\\\\\s]+)")
HEADING_RE = re.compile(r"^#{1,3}\s+(.*)$", re.M)
FENCE_RE = re.compile(r"^```", re.M)


def note_stats(text: str) -> dict:
    lines = text.splitlines()
    fences = [line for line in lines if line.startswith("```")]
    code_lines = 0
    inside = False
    for line in lines:
        if line.startswith("```"):
            inside = not inside
            continue
        if inside:
            code_lines += 1
    headings = [m.group(1).strip() for m in HEADING_RE.finditer(text)]
    return {
        "lines": len(lines),
        "code_lines": code_lines,
        "code_blocks": len(fences) // 2,
        "headings": headings,
    }


def check_note(path: Path, kind: str, strict: bool) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    text = path.read_text(encoding="utf-8")
    stats = note_stats(text)
    lines = stats["lines"]

    low, high = RANGES.get(kind, (0, 10**9))
    if kind in RANGES:
        if lines < low * 0.6:
            warnings.append(f"{path.name}: 只有 {lines} 行，明显低于 {kind} 的参考下限 {low}，检查是否缺示例/失败模式/边界")
        elif lines < low:
            warnings.append(f"{path.name}: {lines} 行，略低于 {kind} 的参考下限 {low}，确认内容是紧凑而不是缺项")
        elif lines > high:
            warnings.append(f"{path.name}: {lines} 行，超过 {kind} 的参考上限 {high}，检查是否重复或该拆篇")

    if not any("核验" in heading for heading in stats["headings"]):
        errors.append(f"{path.name}: 缺少“核验”一节")

    if kind in {"mechanism", "practice"} and not any("故障" in h or "失败" in h for h in stats["headings"]):
        warnings.append(f"{path.name}: 机制/实践篇建议有“故障矩阵”或“失败模式”一节")

    if not any("边界" in h or "反例" in h for h in stats["headings"]):
        warnings.append(f"{path.name}: 缺少“边界”或“反例”一节")

    if kind == "source-review":
        if stats["code_blocks"] < 8:
            errors.append(f"{path.name}: 源码篇需要至少 8 段代码，当前 {stats['code_blocks']} 段")
        if stats["code_lines"] < 120:
            errors.append(f"{path.name}: 源码篇代码总量需 ≥120 行，当前 {stats['code_lines']} 行")

    for match in CROSS_REFS.finditer(text):
        errors.append(f"{path.name}: 出现跨篇引用“{match.group(0)}”，改为独立成篇")

    for match in PERSONAL_PATHS.finditer(text):
        errors.append(f"{path.name}: 出现个人环境路径“{match.group(0)}”")

    if "TODO" in text or "待补" in text:
        warnings.append(f"{path.name}: 含 TODO/待补 标记")

    if strict:
        errors.extend(warnings)
        warnings = []
    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检查学习笔记的深度与独立性")
    parser.add_argument("--plan", required=True, help="plan.json 路径")
    parser.add_argument("--strict", action="store_true", help="把警告当作错误")
    args = parser.parse_args(argv)

    plan_path = Path(args.plan).expanduser().resolve()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    base = plan_path.parent.resolve()

    errors: list[str] = []
    warnings: list[str] = []
    for note in plan.get("notes", []):
        rel = note.get("file")
        if not rel:
            errors.append(f"notes 缺少 file：{note.get('id')}")
            continue
        path = (base / rel).resolve()
        if not path.is_file():
            errors.append(f"找不到笔记：{rel}")
            continue
        note_errors, note_warnings = check_note(path, str(note.get("kind") or ""), args.strict)
        errors.extend(note_errors)
        warnings.extend(note_warnings)

    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for error in errors:
        print(f"error: {error}", file=sys.stderr)

    if errors:
        print(f"\n{len(errors)} 个错误，{len(warnings)} 个警告", file=sys.stderr)
        return 1
    print(f"通过：{len(plan.get('notes', []))} 篇，{len(warnings)} 个警告")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
