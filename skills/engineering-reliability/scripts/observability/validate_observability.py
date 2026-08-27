#!/usr/bin/env python3
"""校验可观测性 Skill 的 CSV 目录和基本结构。

运行示例：
    python scripts/validate_observability.py --assets assets/
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

# 值域
SIGNAL_TYPES = {"METRICS", "TRACES", "LOGS", "PROFILES"}
ALERT_SEVERITIES = {"PAGE", "TICKET", "INFO"}
SEVERITIES = {"BLOCKER", "MAJOR", "MINOR"}

SIGNAL_HEADERS = ["signal", "purpose", "requiredIdentity", "cardinalityPolicy", "owner"]
SLI_HEADERS = ["sliId", "service", "name", "numerator", "denominator", "window", "target", "owner"]
ALERT_HEADERS = ["alert", "condition", "severity", "action", "runbook", "owner"]
REVIEW_HEADERS = ["checkId", "requirement", "severity"]


def g(row, key):
    """安全读取 CSV 单元格：缺列返回空串而非 KeyError。"""
    v = row.get(key)
    return "" if v is None else v


def check_table(path: Path, headers: list, key_field: str, label: str,
               value_checks: dict | None = None) -> list:
    """校验 CSV 表头、唯一、必填、缺列；value_checks 是 {字段: allowed_set} 值域校验。"""
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
        if value_checks:
            for field, allowed in value_checks.items():
                val = g(row, field)
                if val and val not in allowed:
                    errors.append(f"{label} 第{i}行 {field} 无效：{val}（应为 {sorted(allowed)}）")
    return errors


def main() -> int:
    p = argparse.ArgumentParser(description="校验可观测性 Skill 资产")
    p.add_argument("--assets", type=Path, required=True, help="assets 目录")
    a = p.parse_args()

    errors = []
    errors += check_table(
        a.assets / "telemetry-signal-catalog.csv", SIGNAL_HEADERS, "signal", "信号目录",
        value_checks={"signal": SIGNAL_TYPES}
    )
    errors += check_table(
        a.assets / "sli-catalog.csv", SLI_HEADERS, "sliId", "SLI 目录"
    )
    errors += check_table(
        a.assets / "alert-policy.csv", ALERT_HEADERS, "alert", "告警策略",
        value_checks={"severity": ALERT_SEVERITIES}
    )
    errors += check_table(
        a.assets / "observability-review-checklist.csv", REVIEW_HEADERS, "checkId", "评审清单",
        value_checks={"severity": SEVERITIES}
    )

    if errors:
        for e in errors:
            print(f"错误：{e}", file=sys.stderr)
        return 1
    print("可观测性 Skill 资源校验通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
