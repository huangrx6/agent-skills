#!/usr/bin/env python3
"""校验 Secure Coding Skill 的 CSV 目录、模板和基础结构。"""
from __future__ import annotations
import argparse
import csv
import sys
from pathlib import Path

CONTROL_HEADERS = ["controlId","category","requirement","severity","automatable","evidence"]
TAINT_HEADERS = ["source","sink","primaryControl","secondaryControls","reviewPriority"]
IMPACT_HEADERS = ["pathPattern","securityAreas","reason","requiredAction"]
REVIEW_HEADERS = ["checkId","category","requirement","severity","automatable","evidence"]

RULE_SEVERITIES = {"MUST", "SHOULD", "MAY"}
REVIEW_SEVERITIES = {"BLOCKER", "MAJOR", "MINOR"}
AUTOMATABLE = {"true", "false", "partly"}
PRIORITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}


def g(row, key):
    """安全读取 CSV 单元格：缺列返回空串而非 KeyError。"""
    v = row.get(key)
    return "" if v is None else v

def table(path: Path, headers, key):
    errors = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        if r.fieldnames != headers:
            errors.append(f"{path.name}: 表头不正确 {r.fieldnames}")
        rows = list(r)
    if not rows:
        errors.append(f"{path.name}: 不能为空")
        return errors
    seen = set()
    for i, row in enumerate(rows, 2):
        v = g(row, key)
        if not v:
            errors.append(f"{path.name}:{i}: {key} 为空")
        elif v in seen:
            errors.append(f"{path.name}:{i}: {key} 重复 {v}")
        seen.add(v)
        for h in headers:
            if h not in row:
                errors.append(f"{path.name}:{i}: 缺少列 {h}")
    return errors


def validate_control_values(path: Path):
    """安全控制目录：severity 与 automatable 值域校验。"""
    errors = table(path, CONTROL_HEADERS, "controlId")
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for i, row in enumerate(rows, 2):
        sev = g(row, "severity").upper()
        if sev not in RULE_SEVERITIES:
            errors.append(f"{path.name}:{i}: severity 无效: {sev}（应为 {sorted(RULE_SEVERITIES)}）")
        aut = g(row, "automatable").lower()
        if aut not in AUTOMATABLE:
            errors.append(f"{path.name}:{i}: automatable 无效: {aut}（应为 {sorted(AUTOMATABLE)}）")
    return errors


def validate_review_values(path: Path):
    """评审清单：severity 与 automatable 值域校验。"""
    errors = table(path, REVIEW_HEADERS, "checkId")
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for i, row in enumerate(rows, 2):
        sev = g(row, "severity").upper()
        if sev not in REVIEW_SEVERITIES:
            errors.append(f"{path.name}:{i}: severity 无效: {sev}（应为 {sorted(REVIEW_SEVERITIES)}）")
        aut = g(row, "automatable").lower()
        if aut not in AUTOMATABLE:
            errors.append(f"{path.name}:{i}: automatable 无效: {aut}（应为 {sorted(AUTOMATABLE)}）")
    return errors


def validate_taint_values(path: Path):
    """Source/Sink 路由表：reviewPriority 值域校验。"""
    errors = table(path, TAINT_HEADERS, "source")
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for i, row in enumerate(rows, 2):
        pri = g(row, "reviewPriority").upper()
        if pri not in PRIORITIES:
            errors.append(f"{path.name}:{i}: reviewPriority 无效: {pri}（应为 {sorted(PRIORITIES)}）")
    return errors

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--assets", type=Path, required=True)
    a = p.parse_args()
    errors = []
    errors += validate_control_values(a.assets / "security-control-catalog.csv")
    errors += validate_taint_values(a.assets / "taint-source-sink-catalog.csv")
    errors += table(a.assets / "security-impact-rules.csv", IMPACT_HEADERS, "pathPattern")
    errors += validate_review_values(a.assets / "security-review-checklist.csv")

    exc = (a.assets / "security-exception.template.md").read_text(encoding="utf-8")
    for section in ("## Control being bypassed","## Business reason","## Assets and trust boundary",
                    "## Risk","## Compensating controls","## Validation","## Fix / Exit plan",
                    "## Expiration behavior"):
        if section not in exc:
            errors.append(f"security-exception.template.md 缺少 {section}")

    if errors:
        for e in errors:
            print("错误:", e, file=sys.stderr)
        return 1
    print("安全编码 Skill 资源校验通过。")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
