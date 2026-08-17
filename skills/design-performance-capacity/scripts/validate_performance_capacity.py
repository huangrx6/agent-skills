#!/usr/bin/env python3
"""校验性能与容量 Skill 的 CSV 目录、模板和基本结构。

运行示例：
    python scripts/validate_performance_capacity.py --assets assets/
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

# 值域
SCENARIO_TYPES = {"LOAD", "STRESS", "SPIKE", "SOAK"}
SEVERITIES = {"BLOCKER", "MAJOR", "MINOR"}

BUDGET_HEADERS = ["operation", "workload", "p50Ms", "p95Ms", "p99Ms", "throughput", "errorRate", "owner"]
SCENARIO_HEADERS = ["scenario", "type", "duration", "workload", "target", "stopCondition"]
CAPACITY_HEADERS = ["component", "workUnit", "capacityPerInstance", "limitingResource", "safeUtilization", "headroom", "owner"]
REVIEW_HEADERS = ["checkId", "requirement", "severity"]


def g(row, key):
    """安全读取 CSV 单元格：缺列返回空串而非 KeyError。"""
    v = row.get(key)
    return "" if v is None else v


def check_table(path: Path, headers: list, key_field: str, label: str,
               value_checks: dict = None) -> list:
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


def check_experiment_template(path: Path) -> list:
    """性能实验模板必备字段校验。"""
    if not path.is_file():
        return [f"performance-experiment.template.md 不存在：{path}"]
    text = path.read_text(encoding="utf-8")
    required = ("- Hypothesis:", "- Baseline version:", "- Candidate version:",
                "- Environment:", "- Dataset:", "- Workload:",
                "## Metrics", "## Single variable changed", "## Result",
                "## Bottleneck", "## Decision", "## Follow-up")
    return [f"performance-experiment.template.md 缺少：{s}" for s in required if s not in text]


def main() -> int:
    p = argparse.ArgumentParser(description="校验性能与容量 Skill 资产")
    p.add_argument("--assets", type=Path, required=True, help="assets 目录")
    a = p.parse_args()

    errors = []
    errors += check_table(
        a.assets / "performance-budget.csv", BUDGET_HEADERS, "operation", "性能预算"
    )
    errors += check_table(
        a.assets / "load-test-scenarios.csv", SCENARIO_HEADERS, "scenario", "负载测试场景",
        value_checks={"type": SCENARIO_TYPES}
    )
    errors += check_table(
        a.assets / "capacity-model.csv", CAPACITY_HEADERS, "component", "容量模型"
    )
    errors += check_table(
        a.assets / "performance-review-checklist.csv", REVIEW_HEADERS, "checkId", "评审清单",
        value_checks={"severity": SEVERITIES}
    )
    errors += check_experiment_template(a.assets / "performance-experiment.template.md")

    if errors:
        for e in errors:
            print(f"错误：{e}", file=sys.stderr)
        return 1
    print("性能与容量 Skill 资源校验通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
