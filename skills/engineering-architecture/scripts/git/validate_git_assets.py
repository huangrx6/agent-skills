#!/usr/bin/env python3
"""校验 Git 工作流 Skill 的 CSV 目录和模板。

运行示例：
    python scripts/validate_git_assets.py --assets assets/
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

SAFETY_LEVELS = {"readonly", "need-confirm", "high-risk", "dangerous"}
COMMIT_TYPES = {"feat", "fix", "docs", "style", "refactor", "perf",
                "test", "build", "ci", "chore", "revert"}
SEMVER_IMPACTS = {"MAJOR", "MINOR", "PATCH", "NONE", "VARIES"}
SEVERITIES = {"BLOCKER", "MAJOR", "MINOR"}
BOOLEANS_STR = {"true", "false"}

COMMAND_HEADERS = ["command", "category", "safetyLevel", "changesHistory",
                   "affectsRemote", "requiresConfirm", "notes"]
TYPE_HEADERS = ["type", "purpose", "semverImpact", "example", "scopeExample"]
MERGE_HEADERS = ["strategy", "command", "when", "producesMergeCommit",
                 "preservesHistory", "recommendedFor"]
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


def check_commit_template(path: Path) -> list:
    """commit message 模板必备章节校验。"""
    if not path.is_file():
        return [f"commit-message.template.md 不存在：{path}"]
    text = path.read_text(encoding="utf-8")
    required = ["# Conventional Commit", "<type>", "feat", "fix",
                "BREAKING CHANGE", "## 撰写检查"]
    return [f"commit-message.template.md 缺少：{s}" for s in required if s not in text]


def main() -> int:
    p = argparse.ArgumentParser(description="校验 Git 工作流 Skill 资产")
    p.add_argument("--assets", type=Path, required=True, help="assets 目录")
    a = p.parse_args()

    errors = []
    errors += check_table(
        a.assets / "git-command-safety-matrix.csv", COMMAND_HEADERS,
        "command", "命令安全矩阵",
        value_checks={"safetyLevel": SAFETY_LEVELS,
                      "changesHistory": BOOLEANS_STR,
                      "affectsRemote": BOOLEANS_STR,
                      "requiresConfirm": BOOLEANS_STR}
    )
    errors += check_table(
        a.assets / "commit-type-catalog.csv", TYPE_HEADERS,
        "type", "提交类型目录",
        value_checks={"type": COMMIT_TYPES, "semverImpact": SEMVER_IMPACTS}
    )
    errors += check_table(
        a.assets / "merge-strategy-matrix.csv", MERGE_HEADERS,
        "strategy", "合并策略矩阵"
    )
    errors += check_table(
        a.assets / "git-review-checklist.csv", REVIEW_HEADERS,
        "checkId", "评审清单",
        value_checks={"severity": SEVERITIES}
    )
    errors += check_commit_template(a.assets / "commit-message.template.md")

    if errors:
        for e in errors:
            print(f"错误：{e}", file=sys.stderr)
        return 1
    print("Git 工作流 Skill 资源校验通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())