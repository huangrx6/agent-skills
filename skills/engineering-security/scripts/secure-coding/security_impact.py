#!/usr/bin/env python3
"""根据 changed file paths 输出需要执行的安全评审领域。"""
from __future__ import annotations
import argparse
import csv
import fnmatch
from pathlib import Path

def matches(pattern: str, path: str) -> bool:
    if fnmatch.fnmatch(path, pattern):
        return True
    # 让 **/api/** 也可匹配 api/... 等根级路径
    alt = pattern.replace("**/", "")
    return fnmatch.fnmatch(path, alt)

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--rules", type=Path, required=True)
    p.add_argument("paths", nargs="+")
    a = p.parse_args()

    with a.rules.open("r", encoding="utf-8-sig", newline="") as f:
        rules = list(csv.DictReader(f))

    found = False
    seen = set()
    for path in a.paths:
        for rule in rules:
            if matches(rule["pathPattern"], path):
                key = (path, rule["securityAreas"])
                if key in seen:
                    continue
                seen.add(key)
                found = True
                print(f"{path} -> {rule['securityAreas']}")
                print(f"  原因: {rule['reason']}")
                print(f"  动作: {rule['requiredAction']}")

    if not found:
        print("未匹配预定义高风险路径；仍需根据 diff 判断是否新增 Source、Sink、权限、Secret、网络或敏感数据。")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
