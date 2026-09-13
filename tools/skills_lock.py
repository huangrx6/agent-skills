#!/usr/bin/env python3
"""维护 `skills-lock.json`：它是**派生文件**，不该靠手写。

为什么有这个
------------
仓库里早就有这条 checklist（`skills/skill-builder/SKILL.md`）：

> - [ ] 同步更新 `skills-lock.json`，新增一条 entry

而它靠人记。实测（2026-09-14）：文件被手工改过 10 次，但当下 6 个 skill 里
**3 个没登记、2 个的哈希已经过期**，只有 1 个是对的。

格式是**验证过**的（不是猜的）：`computedHash` = `sha256(SKILL.md 的字节)` ——
拿当时没改过的那个 skill 对，完全一致。

用法
----
    python3 tools/skills_lock.py --check     # 对不上就退出 1（给 hook 用）
    python3 tools/skills_lock.py --update    # 按仓库现状重写
    python3 tools/skills_lock.py --json      # 看现状

退出码：0 一致/成功 / 1 不一致 / 2 用法或读不到
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.dirname(HERE)
LOCK_NAME = "skills-lock.json"
DEFAULT_SOURCE = "huangrx6/agent-skills"
DEFAULT_SOURCE_TYPE = "github"
LOCK_VERSION = 1


def listdir(path: str) -> list[str]:
    try:
        return os.listdir(path)
    except OSError:
        return []


def read_bytes(path: str) -> bytes:
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError:
        return b""


def read_lock(root: str) -> dict[str, Any]:
    path = os.path.join(root, LOCK_NAME)
    if not os.path.isfile(path):
        return {"version": LOCK_VERSION, "skills": {}}
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {"version": LOCK_VERSION, "skills": {}}
    if not isinstance(data, dict):
        return {"version": LOCK_VERSION, "skills": {}}
    skills = data.get("skills")
    if not isinstance(skills, dict):
        data["skills"] = {}
    return data


def sha256_of(path: str) -> str:
    return hashlib.sha256(read_bytes(path)).hexdigest()


def skill_names(root: str) -> list[str]:
    skills_dir = os.path.join(root, "skills")
    return sorted(n for n in listdir(skills_dir)
                  if os.path.isdir(os.path.join(skills_dir, n))
                  and not n.startswith(".")
                  and os.path.isfile(os.path.join(skills_dir, n, "SKILL.md")))


def expected(root: str) -> dict[str, dict[str, str]]:
    """按仓库现状算出来的应有内容。source / sourceType 继承旧值，不给就取默认。"""
    old = read_lock(root).get("skills") or {}
    out: dict[str, dict[str, str]] = {}
    for name in skill_names(root):
        previous = old.get(name) or {}
        out[name] = {
            "source": str(previous.get("source") or DEFAULT_SOURCE),
            "sourceType": str(previous.get("sourceType") or DEFAULT_SOURCE_TYPE),
            "skillPath": f"skills/{name}/SKILL.md",
            "computedHash": sha256_of(os.path.join(root, out_path(name))),
        }
    return out


def out_path(name: str) -> str:
    return os.path.join("skills", name, "SKILL.md")


def diff(root: str) -> dict[str, list[str]]:
    """返回 {缺登记, 哈希过期, 多出来的}。"""
    have = read_lock(root).get("skills") or {}
    want = expected(root)
    missing = sorted(set(want) - set(have))
    extra = sorted(set(have) - set(want))
    stale = sorted(name for name in set(want) & set(have)
                   if str((have.get(name) or {}).get("computedHash") or "") != want[name]["computedHash"])
    return {"缺登记": missing, "哈希过期": stale, "多出来的": extra}


def build(root: str) -> dict[str, Any]:
    return {"version": LOCK_VERSION, "skills": expected(root)}


def write_lock(root: str, payload: dict[str, Any]) -> str:
    path = os.path.join(root, LOCK_NAME)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    except OSError as exc:
        print(f"写不了 {path}：{exc}", file=sys.stderr)
        return ""
    return path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="维护 skills-lock.json（派生文件）")
    parser.add_argument("--root", default=DEFAULT_ROOT, help="仓库根目录")
    parser.add_argument("--check", action="store_true", help="对不上就退出 1")
    parser.add_argument("--update", action="store_true", help="按仓库现状重写")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)

    root = os.path.abspath(os.path.expanduser(args.root))
    if not os.path.isdir(os.path.join(root, "skills")):
        print(f"这不是仓库根目录（没有 skills/）：{root}", file=sys.stderr)
        return 2

    report = diff(root)
    problems = sum(len(v) for v in report.values())

    if args.json:
        print(json.dumps({"diff": report, "expected": expected(root)},
                         ensure_ascii=False, indent=2, sort_keys=True))
        return 1 if (args.check and problems) else 0

    if args.update:
        path = write_lock(root, build(root))
        if not path:
            return 1
        print(f"✓ 已按仓库现状重写 {LOCK_NAME}"
              f"（{len(skill_names(root))} 个 skill，哈希取自 SKILL.md 的 sha256）")
        return 0

    if args.check:
        if not problems:
            print(f"✓ {LOCK_NAME} 与仓库一致（{len(skill_names(root))} 个 skill）")
            return 0
        for label, names in report.items():
            if names:
                print(f"✗ {label}：{'、'.join(names)}", file=sys.stderr)
        print(f"  改法：python3 tools/skills_lock.py --update"
              f"（这是派生文件，不要手改）", file=sys.stderr)
        return 1

    for name in skill_names(root):
        print(f"  skills/{name}/SKILL.md   {sha256_of(os.path.join(root, out_path(name)))[:16]}…")
    print(f"\n共 {len(skill_names(root))} 个 skill；"
          f"{'与锁文件一致' if not problems else f'锁文件有 {problems} 处不一致（--check 看详情）'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
