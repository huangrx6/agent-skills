#!/usr/bin/env python3
"""根据 changed file paths 输出应该检查的文档区域。"""
from __future__ import annotations
import argparse
import csv
import fnmatch
from pathlib import Path

def match(pattern: str, path: str) -> bool:
    # fnmatch 把 ** 当单层 * 处理（非 globstar），因此规则应按 fnmatch 语义编写；
    # 结果是候选提示，不是合并阻塞事实。
    return fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(path, pattern.replace("**/", ""))

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--rules", type=Path, required=True)
    p.add_argument("paths", nargs="+")
    a = p.parse_args()

    with a.rules.open("r", encoding="utf-8-sig", newline="") as f:
        rules = list(csv.DictReader(f))

    matches = []
    for changed in a.paths:
        for rule in rules:
            if match(rule["pathPattern"], changed):
                matches.append((
                    changed,
                    rule["documentAreas"],
                    rule["reason"],
                    rule["requiredAction"],
                ))

    if not matches:
        print("未匹配到预定义文档影响规则；仍需人工/Agent 判断行为和长期知识是否变化。")
        return 0

    seen = set()
    for row in matches:
        if row in seen:
            continue
        seen.add(row)
        print(f"{row[0]} -> {row[1]}")
        print(f"  原因: {row[2]}")
        print(f"  动作: {row[3]}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
