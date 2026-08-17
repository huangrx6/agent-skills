#!/usr/bin/env python3
"""校验工程文档 Skill 资产，或可选校验一个项目的文档入口。"""
from __future__ import annotations
import argparse
import csv
import re
import sys
from pathlib import Path

TYPE_HEADERS = ["type","canonicalLocation","purpose","createWhen","updateWhen","newVsUpdate","lifecycle"]
IMPACT_HEADERS = ["pathPattern","documentAreas","reason","requiredAction"]
REVIEW_HEADERS = ["checkId","category","requirement","severity","automatable","evidence"]

SEVERITIES = {"BLOCKER", "MAJOR", "MINOR"}
AUTOMATABLE = {"true", "false", "partly"}
# 跨文档类型的状态枚举（参见 references/document-lifecycle.md §状态总表）
DOC_LIFECYCLE_STATES = {"draft", "active", "deprecated", "superseded", "archived"}
ADR_LIFECYCLE_STATES = {"Proposed", "Accepted", "Rejected", "Superseded"}
HANDOFF_LIFECYCLE_STATES = {"active", "blocked", "completed", "abandoned"}
# 默认校验覆盖长期文档状态枚举（type-policy 的 lifecycle 列）
LIFECYCLE_STATES = DOC_LIFECYCLE_STATES | {"historical", "temporary", "generated"}


def check_csv(path: Path, headers, key):
    errors = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        if r.fieldnames != headers:
            errors.append(f"{path.name}: 表头错误 {r.fieldnames}")
        rows = list(r)
    if not rows:
        errors.append(f"{path.name}: 不能为空")
    seen = set()
    for i, row in enumerate(rows, 2):
        value = row.get(key, "").strip()
        if not value:
            errors.append(f"{path.name}:{i} {key} 为空")
        elif value in seen:
            errors.append(f"{path.name}:{i} {key} 重复 {value}")
        seen.add(value)
        # 列缺失防护：其他字段也应存在
        for h in headers:
            if h not in row:
                errors.append(f"{path.name}:{i} 缺少列 {h}")
    return errors


def check_review_values(path: Path):
    """评审清单：severity 与 automatable 值域校验。"""
    errors = check_csv(path, REVIEW_HEADERS, "checkId")
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for i, row in enumerate(rows, 2):
        sev = (row.get("severity") or "").strip().upper()
        if sev not in SEVERITIES:
            errors.append(f"{path.name}:{i} severity 无效: {sev}（应为 {sorted(SEVERITIES)}）")
        aut = (row.get("automatable") or "").strip().lower()
        if aut not in AUTOMATABLE:
            errors.append(f"{path.name}:{i} automatable 无效: {aut}（应为 {sorted(AUTOMATABLE)}）")
    return errors


def check_type_values(path: Path):
    """文档类型策略：lifecycle 值域校验。"""
    errors = check_csv(path, TYPE_HEADERS, "type")
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for i, row in enumerate(rows, 2):
        lc = (row.get("lifecycle") or "").strip().lower()
        if lc not in LIFECYCLE_STATES:
            errors.append(f"{path.name}:{i} lifecycle 无效: {lc}（应为 {sorted(LIFECYCLE_STATES)}）")
    return errors

def check_examples(assets: Path):
    """示例文档（examples/）的必备段落校验，防止示例过期。"""
    errors = []
    readme = assets.parent / "examples" / "README.md"
    if readme.exists():
        text = readme.read_text(encoding="utf-8")
        # 示例 README 必须有边界声明，避免被误当项目模板使用
        if "不抄用" not in text and "不参考" not in text and "作参照" not in text:
            errors.append("examples/README.md 应包含边界声明（如'不抄用，作参照'）")
    return errors
    text = path.read_text(encoding="utf-8")
    return [f"{path.name}: 缺少 {x}" for x in required if x not in text]


def check_template(path: Path, required):
    """检查模板文件是否含必备章节。"""
    text = path.read_text(encoding="utf-8")
    return [f"{path.name}: 缺少 {x}" for x in required if x not in text]


def check_project(project: Path):
    errors = []
    warnings = []
    agents = project / "AGENTS.md"
    context = project / "PROJECT_CONTEXT.md"
    index = project / "docs" / "index.md"

    for p in (agents, context, index):
        if not p.exists():
            warnings.append(f"建议创建: {p.relative_to(project)}")

    if agents.exists():
        size = agents.stat().st_size
        if size > 12288:
            warnings.append(f"AGENTS.md 为 {size} bytes；建议根级保持 <= 12 KiB，详细知识下沉到子目录 AGENTS.override.md。")

    if context.exists():
        size = context.stat().st_size
        if size > 12288:
            warnings.append(f"PROJECT_CONTEXT.md 为 {size} bytes；建议保持 <= 12 KiB。")
        text = context.read_text(encoding="utf-8")
        if "docs/" not in text:
            warnings.append("PROJECT_CONTEXT.md 建议链接到详细 docs。")

    active = project / "docs" / "handoffs" / "active"
    if active.exists():
        for md in active.glob("*.md"):
            text = md.read_text(encoding="utf-8")
            if "expires_or_close_when:" not in text:
                warnings.append(f"{md}: active handoff 缺少关闭条件。")

    if index.exists():
        text = index.read_text(encoding="utf-8")
        # 索引应包含指向详细文档的链接（.md 引用），而非空文件/纯文本
        if "(" not in text or ".md" not in text:
            warnings.append("docs/index.md 建议包含指向详细文档的链接，而非纯文本列表。")

    return errors, warnings

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--assets", type=Path, required=True)
    p.add_argument("--project", type=Path)
    a = p.parse_args()

    errors = []
    errors += check_type_values(a.assets / "document-type-policy.csv")
    errors += check_csv(a.assets / "document-impact-rules.csv", IMPACT_HEADERS, "pathPattern")
    errors += check_review_values(a.assets / "documentation-review-checklist.csv")

    errors += check_template(
        a.assets / "project-context.template.md",
        ["## Purpose","## Repository Map","## Architecture Summary","## Critical Invariants","## Canonical Documentation"]
    )
    errors += check_template(
        a.assets / "agents.template.md",
        ["## Before work","## Guardrails","## Documentation workflow"]
    )
    errors += check_template(
        a.assets / "handoff.template.md",
        ["## Goal","## Current State","## Remaining","## Exact Next Step","## Close"]
    )
    errors += check_template(
        a.assets / "decision.template.md",
        ["## Context", "## Decision", "## Decision Drivers", "## Consequences", "## Revisit Trigger"]
    )
    errors += check_template(
        a.assets / "docs-index.template.md",
        ["## Start here", "## I want to"]
    )
    errors += check_template(
        a.assets / "working-agreements.template.md",
        ["## Development", "## AI Coding", "## Change policy"]
    )
    errors += check_examples(a.assets)

    warnings = []
    if a.project:
        pe, pw = check_project(a.project)
        errors += pe
        warnings += pw

    for w in warnings:
        print("提示:", w)

    if errors:
        for e in errors:
            print("错误:", e, file=sys.stderr)
        return 1

    print("工程文档 Skill 校验通过。")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
