#!/usr/bin/env python3
"""校验代码书写规范的命名、文件头、设计模式和评审目录。"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

NAMING_HEADERS = [
    "ruleId", "scope", "language", "convention", "example", "severity", "rationale"
]
HEADER_POLICY_HEADERS = [
    "policyId", "fileType", "field", "requirement", "sourceOfTruth", "example", "notes"
]
PATTERN_HEADERS = [
    "pattern", "useWhen", "avoidWhen", "requiredEvidence", "reviewQuestions"
]
REVIEW_HEADERS = [
    "checkId", "category", "requirement", "severity", "automatable", "evidence"
]
STD_HEADERS = [
    "checkId", "section", "requirement", "severity", "guidance"
]

RULE_SEVERITIES = {"MUST", "SHOULD", "MAY"}
HEADER_REQUIREMENTS = {"REQUIRED", "CONDITIONAL", "OPTIONAL", "PROHIBITED"}
REVIEW_SEVERITIES = {"BLOCKER", "MAJOR", "MINOR"}
# STD 清单与评审清单严重度枚举刻意保持一致，复用同一集合。
STD_SEVERITIES = REVIEW_SEVERITIES
AUTOMATABLE = {"true", "false", "partly"}


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.is_file():
        raise ValueError(f"文件不存在：{path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"缺少表头：{path}")
        return reader.fieldnames, list(reader)


def require_headers(actual: list[str], expected: list[str], label: str) -> list[str]:
    if actual == expected:
        return []
    return [f"{label}表头必须严格为 {expected}，实际为 {actual}"]


def require_unique(rows: list[dict[str, str]], field: str, label: str) -> list[str]:
    seen: set[str] = set()
    errors: list[str] = []
    for index, row in enumerate(rows, start=2):
        value = (row.get(field) or "").strip()
        if not value:
            errors.append(f"{label}第 {index} 行：{field} 不能为空")
        elif value in seen:
            errors.append(f"{label}第 {index} 行：{field} 重复：{value}")
        else:
            seen.add(value)
    return errors


def validate_required(
    rows: list[dict[str, str]],
    fields: tuple[str, ...],
    label: str,
) -> list[str]:
    errors: list[str] = []
    for index, row in enumerate(rows, start=2):
        for field in fields:
            value = row.get(field)
            if value is None:
                errors.append(f"{label}第 {index} 行：缺少列 {field}")
            elif not value.strip():
                errors.append(f"{label}第 {index} 行：{field} 不能为空")
    return errors


def validate_naming(path: Path) -> list[str]:
    headers, rows = read_csv(path)
    errors = require_headers(headers, NAMING_HEADERS, "命名目录：")
    errors.extend(require_unique(rows, "ruleId", "命名目录"))
    errors.extend(validate_required(
        rows, ("scope", "language", "convention", "example", "severity", "rationale"), "命名目录"
    ))
    for index, row in enumerate(rows, start=2):
        if (row.get("severity") or "").strip().upper() not in RULE_SEVERITIES:
            errors.append(f"命名目录第 {index} 行：severity 必须属于 {sorted(RULE_SEVERITIES)}")
    if not rows:
        errors.append("命名目录至少需要一条数据")
    return errors


def validate_header_policy(path: Path) -> list[str]:
    headers, rows = read_csv(path)
    errors = require_headers(headers, HEADER_POLICY_HEADERS, "文件头策略：")
    errors.extend(require_unique(rows, "policyId", "文件头策略"))
    errors.extend(validate_required(
        rows, ("fileType", "field", "requirement", "sourceOfTruth"), "文件头策略"
    ))
    for index, row in enumerate(rows, start=2):
        requirement = (row.get("requirement") or "").strip().upper()
        if requirement not in HEADER_REQUIREMENTS:
            errors.append(
                f"文件头策略第 {index} 行：requirement 必须属于 {sorted(HEADER_REQUIREMENTS)}"
            )
        if requirement == "REQUIRED" and not (row.get("example") or "").strip():
            errors.append(f"文件头策略第 {index} 行：REQUIRED 项必须提供 example")
    if not rows:
        errors.append("文件头策略至少需要一条数据")
    return errors


def validate_patterns(path: Path) -> list[str]:
    headers, rows = read_csv(path)
    errors = require_headers(headers, PATTERN_HEADERS, "设计模式目录：")
    errors.extend(require_unique(rows, "pattern", "设计模式目录"))
    errors.extend(validate_required(
        rows, ("useWhen", "avoidWhen", "requiredEvidence", "reviewQuestions"), "设计模式目录"
    ))
    if not rows:
        errors.append("设计模式目录至少需要一条数据")
    return errors


def validate_review(path: Path) -> list[str]:
    headers, rows = read_csv(path)
    errors = require_headers(headers, REVIEW_HEADERS, "评审清单：")
    errors.extend(require_unique(rows, "checkId", "评审清单"))
    errors.extend(validate_required(
        rows, ("category", "requirement", "severity", "automatable", "evidence"), "评审清单"
    ))
    for index, row in enumerate(rows, start=2):
        if (row.get("severity") or "").strip().upper() not in REVIEW_SEVERITIES:
            errors.append(f"评审清单第 {index} 行：severity 无效")
        if (row.get("automatable") or "").strip().lower() not in AUTOMATABLE:
            errors.append(f"评审清单第 {index} 行：automatable 必须为 true、false 或 partly")
    if not rows:
        errors.append("评审清单至少需要一条数据")
    return errors


def validate_standard_completeness(path: Path) -> list[str]:
    headers, rows = read_csv(path)
    errors = require_headers(headers, STD_HEADERS, "规范完整性清单：")
    errors.extend(require_unique(rows, "checkId", "规范完整性清单"))
    errors.extend(validate_required(
        rows, ("section", "requirement", "severity", "guidance"), "规范完整性清单"
    ))
    for index, row in enumerate(rows, start=2):
        if (row.get("severity") or "").strip().upper() not in STD_SEVERITIES:
            errors.append(f"规范完整性清单第 {index} 行：severity 必须属于 {sorted(STD_SEVERITIES)}")
    if not rows:
        errors.append("规范完整性清单至少需要一条数据")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("naming_catalog", type=Path, help="命名规则目录 CSV")
    parser.add_argument("--header-policy", type=Path, help="文件头策略 CSV")
    parser.add_argument("--pattern-catalog", type=Path, help="设计模式目录 CSV")
    parser.add_argument("--review-checklist", type=Path, help="代码评审清单 CSV")
    parser.add_argument("--standard-completeness", type=Path, help="规范完整性清单 CSV")
    args = parser.parse_args()

    try:
        errors = validate_naming(args.naming_catalog)
        if args.header_policy:
            errors.extend(validate_header_policy(args.header_policy))
        if args.pattern_catalog:
            errors.extend(validate_patterns(args.pattern_catalog))
        if args.review_checklist:
            errors.extend(validate_review(args.review_checklist))
        if args.standard_completeness:
            errors.extend(validate_standard_completeness(args.standard_completeness))
    except (OSError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2

    if errors:
        for error in errors:
            print(f"错误：{error}", file=sys.stderr)
        return 1

    print("代码书写规范目录校验通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
