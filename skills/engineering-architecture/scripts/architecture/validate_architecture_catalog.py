#!/usr/bin/env python3
"""校验软件架构 Skill 的目录资产和模板。"""
import argparse
import csv
import re
import sys
from pathlib import Path

DECISION_HEADERS = ["style","preferWhen","avoidWhen","keyBenefits","keyCosts","evidenceRequired"]
QUALITY_HEADERS = ["id","qualityAttribute","source","stimulus","environment","artifact","response","measure","priority"]
RISK_HEADERS = ["riskId","category","risk","likelihood","impact","mitigation","owner","status","revisitTrigger"]
REVIEW_HEADERS = ["checkId","category","requirement","severity","automatable","evidence"]

SEVERITIES = {"BLOCKER", "MAJOR", "MINOR"}
AUTOMATABLE = {"true", "false", "partly"}
RISK_LEVELS = {"LOW", "MEDIUM", "HIGH"}
RISK_STATUS = {"OPEN", "MITIGATED", "ACCEPTED", "CLOSED"}
PRIORITIES = {"LOW", "MEDIUM", "HIGH"}
STYLES = {"MODULAR_MONOLITH", "MICROSERVICES", "LAYERED_HEXAGONAL", "EVENT_DRIVEN",
          "CQRS", "EVENT_SOURCING", "QUEUE_WORKER", "SERVERLESS"}

def read_csv(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        return r.fieldnames, list(r)

def validate_table(path, expected, id_field, label):
    headers, rows = read_csv(path)
    errors = []
    if headers != expected:
        errors.append(f"{label} 表头错误: {headers}")
    if not rows:
        errors.append(f"{label} 不能为空")
    seen = set()
    for i, row in enumerate(rows, 2):
        value = row.get(id_field, "").strip()
        if not value:
            errors.append(f"{label} 第{i}行 {id_field} 为空")
        elif value in seen:
            errors.append(f"{label} 第{i}行 {id_field} 重复: {value}")
        seen.add(value)
        for key in expected:
            if key not in row:
                errors.append(f"{label} 第{i}行缺少 {key}")
    return errors

def validate_quality(path):
    """质量属性场景：priority 值域校验。"""
    errors = validate_table(path, QUALITY_HEADERS, "id", "质量属性场景")
    _, rows = read_csv(path)
    for i, row in enumerate(rows, 2):
        pri = (row.get("priority") or "").strip().upper()
        if pri not in PRIORITIES:
            errors.append(f"质量属性场景 第{i}行 priority 无效: {pri}（应为 {sorted(PRIORITIES)}）")
    return errors

def validate_risk(path):
    """风险登记：likelihood/impact/status 值域校验。"""
    errors = validate_table(path, RISK_HEADERS, "riskId", "风险登记")
    _, rows = read_csv(path)
    for i, row in enumerate(rows, 2):
        for field, allowed in (("likelihood", RISK_LEVELS), ("impact", RISK_LEVELS), ("status", RISK_STATUS)):
            val = (row.get(field) or "").strip().upper()
            if val not in allowed:
                errors.append(f"风险登记 第{i}行 {field} 无效: {val}（应为 {sorted(allowed)}）")
    return errors

def validate_review(path):
    """评审清单：severity 与 automatable 值域校验。"""
    errors = validate_table(path, REVIEW_HEADERS, "checkId", "评审清单")
    _, rows = read_csv(path)
    for i, row in enumerate(rows, 2):
        sev = (row.get("severity") or "").strip().upper()
        if sev not in SEVERITIES:
            errors.append(f"评审清单 第{i}行 severity 无效: {sev}（应为 {sorted(SEVERITIES)}）")
        aut = (row.get("automatable") or "").strip().lower()
        if aut not in AUTOMATABLE:
            errors.append(f"评审清单 第{i}行 automatable 无效: {aut}（应为 {sorted(AUTOMATABLE)}）")
    return errors

def validate_decision(path):
    """决策矩阵：style 必须在已知风格集合内。"""
    errors = validate_table(path, DECISION_HEADERS, "style", "决策矩阵")
    _, rows = read_csv(path)
    for i, row in enumerate(rows, 2):
        st = (row.get("style") or "").strip().upper()
        if st not in STYLES:
            errors.append(f"决策矩阵 第{i}行 style 无效: {st}（应为 {sorted(STYLES)}）")
    return errors

def validate_templates(adr, brief):
    errors = []
    adr_text = Path(adr).read_text(encoding="utf-8")
    # 与 reference documentation-adrs.md 的 ADR 内容清单保持一致，覆盖全部 9 节
    for section in ("## Context","## Architecture Drivers","## Decision","## Alternatives",
                    "## Consequences","## Risks and Mitigations","## Validation",
                    "## Revisit Trigger","## Supersedes / Superseded By"):
        if section not in adr_text:
            errors.append(f"ADR 模板缺少 {section}")
    brief_text = Path(brief).read_text(encoding="utf-8")
    for section in ("## 1. 系统目标","## 3. Architecture Drivers","## 4. 边界与数据所有权",
                    "## 6. 集成与一致性","## 9. 关键风险"):
        if section not in brief_text:
            errors.append(f"Architecture Brief 缺少 {section}")
    return errors

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--decision", required=True)
    p.add_argument("--quality", required=True)
    p.add_argument("--risk", required=True)
    p.add_argument("--review", required=True)
    p.add_argument("--adr", required=True)
    p.add_argument("--brief", required=True)
    a = p.parse_args()

    errors = []
    errors += validate_decision(a.decision)
    errors += validate_quality(a.quality)
    errors += validate_risk(a.risk)
    errors += validate_review(a.review)
    errors += validate_templates(a.adr, a.brief)

    if errors:
        for e in errors:
            print("错误:", e, file=sys.stderr)
        return 1
    print("软件架构 Skill 资源校验通过。")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
