#!/usr/bin/env python3
"""校验配置管理 Skill 的 CSV 目录、模板和基本结构。

运行示例：
    python scripts/validate_configuration.py --assets assets/
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

# 值域
RELOAD_MODES = {"ATOMIC_SNAPSHOT", "POLLING", "PUSH", "RESTART"}
FALLBACKS = {"LAST_KNOWN_GOOD", "SAFE_DEFAULT", "FAIL_CLOSED", "NONE"}
SEVERITIES = {"BLOCKER", "MAJOR", "MINOR"}
CONFIG_TYPES = {"STRING", "INTEGER", "FLOAT", "BOOLEAN", "DURATION", "LIST", "MAP"}

SCHEMA_HEADERS = ["key", "type", "unit", "required", "default", "dynamic", "secret", "owner", "description"]
PRECEDENCE_HEADERS = ["priority", "source", "allowedFor", "notes"]
DYNAMIC_HEADERS = ["keyPattern", "reloadMode", "validation", "fallback", "maxStale", "owner"]
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


def check_change_template(path: Path) -> list:
    """配置变更模板必备字段校验。"""
    if not path.is_file():
        return [f"config-change.template.md 不存在：{path}"]
    text = path.read_text(encoding="utf-8")
    required = ("- Key:", "- Owner:", "- Current:", "- Proposed:", "- Scope:", "- Risk:",
                "## Validation", "## Canary", "## Metrics", "## Rollback", "## Cleanup")
    return [f"config-change.template.md 缺少：{s}" for s in required if s not in text]


def main() -> int:
    p = argparse.ArgumentParser(description="校验配置管理 Skill 资产")
    p.add_argument("--assets", type=Path, required=True, help="assets 目录")
    a = p.parse_args()

    errors = []
    errors += check_table(
        a.assets / "config-schema-catalog.csv", SCHEMA_HEADERS, "key", "配置 Schema 目录",
        value_checks={"type": CONFIG_TYPES}
    )
    errors += check_table(
        a.assets / "config-source-precedence.csv", PRECEDENCE_HEADERS, "source", "来源优先级"
    )
    errors += check_table(
        a.assets / "dynamic-config-policy.csv", DYNAMIC_HEADERS, "keyPattern", "动态配置策略",
        value_checks={"reloadMode": RELOAD_MODES, "fallback": FALLBACKS}
    )
    errors += check_table(
        a.assets / "config-review-checklist.csv", REVIEW_HEADERS, "checkId", "评审清单",
        value_checks={"severity": SEVERITIES}
    )
    errors += check_change_template(a.assets / "config-change.template.md")

    if errors:
        for e in errors:
            print(f"错误：{e}", file=sys.stderr)
        return 1
    print("配置管理 Skill 资源校验通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
