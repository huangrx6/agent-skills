#!/usr/bin/env python3
"""校验服务韧性 Skill 的 CSV 目录、模板和基本结构。

运行示例：
    python scripts/validate_resilience.py --assets assets/
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

# 值域
CONTROL_CATEGORIES = {"TIMEOUT", "RETRY", "OVERLOAD", "BACKPRESSURE", "ASYNC", "DEGRADATION", "BULKHEAD", "CIRCUIT_BREAKER", "OBSERVABILITY", "TESTING"}
SEVERITIES = {"MUST", "SHOULD", "MAY"}
REVIEW_SEVERITIES = {"BLOCKER", "MAJOR", "MINOR"}
DEPENDENCY_CRITICALITY = {"CRITICAL", "HIGH", "NORMAL", "LOW", "OPTIONAL"}
RETRYABLE_VALUES = {"none", "timeout", "429", "503", "503_if_idempotent", "all_transient"}

CONTROL_HEADERS = ["controlId", "category", "requirement", "severity"]
DEPENDENCY_HEADERS = ["dependency", "criticality", "timeoutMs", "maxAttempts", "retryable", "concurrencyLimit", "fallback", "owner"]
REVIEW_HEADERS = ["checkId", "requirement", "severity"]


def g(row, key):
    """安全读取 CSV 单元格：缺列返回空串而非 KeyError。"""
    v = row.get(key)
    return "" if v is None else v


def check_table(path: Path, headers: list, key_field: str, label: str,
               value_checks: dict = None) -> list:
    """校验 CSV 表头、唯一、必填；value_checks 是 {字段: allowed_set} 的值域校验。"""
    errors = []
    if not path.is_file():
        return [f"{label} 文件不存在：{path}"]
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != headers:
            return [f"{label} 表头错误：{reader.fieldnames}（应为 {headers}）"]
        rows = list(reader)
    if not rows:
        return [f"{label} 至少需要一条数据"]
    seen = set()
    for i, row in enumerate(rows, 2):
        # 缺列防护
        for h in headers:
            if h not in row:
                errors.append(f"{label} 第{i}行缺少列 {h}")
        key_val = g(row, key_field)
        if not key_val:
            errors.append(f"{label} 第{i}行 {key_field} 为空")
        elif key_val in seen:
            errors.append(f"{label} 第{i}行 {key_field} 重复：{key_val}")
        else:
            seen.add(key_val)
        # 值域校验（支持单值或 `|` 分隔多值，如 "timeout|429|503_if_idempotent"）
        if value_checks:
            for field, allowed in value_checks.items():
                val = g(row, field)
                if not val:
                    continue
                # 拆 | 分隔多值
                for token in val.split('|'):
                    token = token.strip()
                    if token and token not in allowed:
                        errors.append(f"{label} 第{i}行 {field} 无效：{val}（应为 {sorted(allowed)}）")
                        break
    return errors


def check_failure_injection_template(path: Path) -> list:
    """Failure Injection Plan 模板必备字段校验（防止演练流程被删）。"""
    if not path.is_file():
        return [f"failure-injection-plan.template.md 不存在：{path}"]
    text = path.read_text(encoding="utf-8")
    required = ("- Service:", "- Owner:", "- Hypothesis:", "- Blast radius:", "- Stop condition:",
                "## Failure", "## Expected behavior", "## Metrics", "## Result", "## Follow-up")
    return [f"failure-injection-plan.template.md 缺少：{s}" for s in required if s not in text]


def main() -> int:
    p = argparse.ArgumentParser(description="校验服务韧性 Skill 资产")
    p.add_argument("--assets", type=Path, required=True, help="assets 目录")
    a = p.parse_args()

    errors = []
    # 三个 CSV：表头 + 唯一 + 缺列 + 值域
    errors += check_table(
        a.assets / "resilience-control-catalog.csv", CONTROL_HEADERS, "controlId", "控制目录",
        value_checks={"category": CONTROL_CATEGORIES, "severity": SEVERITIES}
    )
    errors += check_table(
        a.assets / "dependency-resilience-policy.csv", DEPENDENCY_HEADERS, "dependency", "依赖韧性策略",
        value_checks={"criticality": DEPENDENCY_CRITICALITY, "retryable": RETRYABLE_VALUES}
    )
    errors += check_table(
        a.assets / "resilience-review-checklist.csv", REVIEW_HEADERS, "checkId", "评审清单",
        value_checks={"severity": REVIEW_SEVERITIES}
    )
    # 模板
    errors += check_failure_injection_template(a.assets / "failure-injection-plan.template.md")

    if errors:
        for e in errors:
            print(f"错误：{e}", file=sys.stderr)
        return 1
    print("服务韧性 Skill 资源校验通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
