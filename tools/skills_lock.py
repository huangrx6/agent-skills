#!/usr/bin/env python3
"""生成或核对 skills-lock.json（SKILL.md 字节的 sha256）。

默认读取工作区；--staged 从 git 暂存区读取正文和既有来源。
--sync-index 供 hook 使用：从暂存区生成并直接更新 index，保留工作区未暂存内容。
--update 显式写回工作区的锁文件，不自行暂存。--check 不一致时返回 1。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
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
    with open(path, "rb") as handle:
        return handle.read()


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


def _git_bytes(root: str, *args: str, input: bytes | None = None) -> bytes:
    result = subprocess.run(["git", "-C", root, *args], input=input, capture_output=True)
    if result.returncode:
        raise ValueError(f"git {args[0]} 失败；请检查仓库状态与文件权限")
    return result.stdout


def read_staged_lock_bytes(root: str) -> bytes | None:
    entries = _git_bytes(root, "ls-files", "--cached", "-z", "--", LOCK_NAME)
    if not entries:
        return None
    return _git_bytes(root, "show", f":{LOCK_NAME}")


def read_staged_lock(root: str) -> dict[str, Any]:
    content = read_staged_lock_bytes(root)
    if content is None:
        return {"version": LOCK_VERSION, "skills": {}}
    try:
        payload = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"version": LOCK_VERSION, "skills": {}}
    if not isinstance(payload, dict):
        return {"version": LOCK_VERSION, "skills": {}}
    if not isinstance(payload.get("skills"), dict):
        payload["skills"] = {}
    return payload


def staged_expected(root: str) -> dict[str, dict[str, str]]:
    """锁住本次将提交的正文，不混入工作区尚未暂存的修改或新 skill。"""
    entries = _git_bytes(root, "ls-files", "--cached", "-z").decode("utf-8").split("\0")
    old = read_staged_lock(root)["skills"]
    out: dict[str, dict[str, str]] = {}
    for path in sorted(set(entries)):
        parts = path.split("/")
        if len(parts) != 3 or parts[0] != "skills" or parts[2] != "SKILL.md":
            continue
        name = parts[1]
        if name.startswith("."):
            continue
        previous = old.get(name)
        previous = previous if isinstance(previous, dict) else {}
        out[name] = {
            "source": str(previous.get("source") or DEFAULT_SOURCE),
            "sourceType": str(previous.get("sourceType") or DEFAULT_SOURCE_TYPE),
            "skillPath": path,
            "computedHash": hashlib.sha256(_git_bytes(root, "show", f":{path}")).hexdigest(),
        }
    return out


def expected(root: str) -> dict[str, dict[str, str]]:
    """按仓库现状算出来的应有内容。source / sourceType 继承旧值，不给就取默认。"""
    old = read_lock(root).get("skills") or {}
    out: dict[str, dict[str, str]] = {}
    for name in skill_names(root):
        previous = old.get(name)
        previous = previous if isinstance(previous, dict) else {}
        out[name] = {
            "source": str(previous.get("source") or DEFAULT_SOURCE),
            "sourceType": str(previous.get("sourceType") or DEFAULT_SOURCE_TYPE),
            "skillPath": f"skills/{name}/SKILL.md",
            "computedHash": sha256_of(os.path.join(root, out_path(name))),
        }
    return out


def out_path(name: str) -> str:
    return os.path.join("skills", name, "SKILL.md")


def diff(root: str, want: dict | None = None, have: dict | None = None) -> dict[str, list[str]]:
    """返回 {缺登记, 哈希过期, 多出来的}。"""
    have = (read_lock(root).get("skills") or {}) if have is None else have
    want = expected(root) if want is None else want
    missing = sorted(set(want) - set(have))
    extra = sorted(set(have) - set(want))
    stale = sorted(name for name in set(want) & set(have)
                   if not isinstance(have[name], dict)
                   or str(have[name].get("computedHash") or "") != want[name]["computedHash"])
    return {"缺登记": missing, "哈希过期": stale, "多出来的": extra}


def build(root: str) -> dict[str, Any]:
    return {"version": LOCK_VERSION, "skills": expected(root)}


def lock_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_lock(root: str, payload: dict[str, Any]) -> str:
    path = os.path.join(root, LOCK_NAME)
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(lock_text(payload))
    except OSError as exc:
        print(f"写不了 {path}：{exc}", file=sys.stderr)
        return ""
    return path


def sync_index(root: str, payload: dict[str, Any]) -> str:
    """直接暂存生成内容；只同步原本不存在或与旧 index 字节一致的普通文件。"""
    previous = read_staged_lock_bytes(root)
    content = lock_text(payload).encode("utf-8")
    oid = _git_bytes(root, "hash-object", "-w", "--stdin", input=content).decode("ascii").strip()
    _git_bytes(root, "update-index", "--add", "--cacheinfo", f"100644,{oid},{LOCK_NAME}")

    # 在 index 更新成功后再检查工作区；工作区未暂存的来源、格式乃至无效 JSON
    # 都属于维护者的内容，不能用解析后的相等性判断或 git add 覆盖它们。
    path = os.path.join(root, LOCK_NAME)
    try:
        if os.path.lexists(path):
            if os.path.islink(path) or read_bytes(path) != previous:
                return f"⚠ 工作区 {LOCK_NAME} 有未暂存内容，已按字节保留；仅更新暂存版本"
            with open(path, "wb") as handle:
                handle.write(content)
        else:
            # 独占创建：检查后才出现的新文件也不能覆盖。
            with open(path, "xb") as handle:
                handle.write(content)
    except OSError as exc:
        return f"⚠ 暂存版本已更新；工作区 {LOCK_NAME} 未同步：{exc}"
    return "（工作区锁文件已同步）"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="维护 skills-lock.json（派生文件）")
    parser.add_argument("--root", default=DEFAULT_ROOT, help="仓库根目录")
    parser.add_argument("--staged", action="store_true", help="从 git 暂存区计算哈希（供 hook 使用）")
    parser.add_argument("--sync-index", action="store_true", help="按暂存区更新 index，保留工作区未暂存内容")
    parser.add_argument("--check", action="store_true", help="对不上就退出 1")
    parser.add_argument("--update", action="store_true", help="按仓库现状重写")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)
    if args.sync_index and (args.update or args.check or args.json):
        parser.error("--sync-index 不能与 --update、--check 或 --json 一起使用")
    args.staged = args.staged or args.sync_index

    root = os.path.abspath(os.path.expanduser(args.root))
    if not args.staged and not os.path.isdir(os.path.join(root, "skills")):
        print(f"这不是仓库根目录（没有 skills/）：{root}", file=sys.stderr)
        return 2

    try:
        want = staged_expected(root) if args.staged else expected(root)
        have = read_staged_lock(root)["skills"] if args.staged else None
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    report = diff(root, want, have)
    problems = sum(len(v) for v in report.values())

    if args.sync_index:
        try:
            note = sync_index(root, {"version": LOCK_VERSION, "skills": want})
        except (OSError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(f"✓ 已自动更新 {LOCK_NAME} 的暂存版本"
              f"（{len(want)} 个 skill，哈希取自暂存区 SKILL.md 的 sha256）")
        print(note)
        return 0

    if args.json:
        print(json.dumps({"diff": report, "expected": want},
                         ensure_ascii=False, indent=2, sort_keys=True))
        return 1 if (args.check and problems) else 0

    if args.update:
        path = write_lock(root, {"version": LOCK_VERSION, "skills": want})
        if not path:
            return 1
        print(f"✓ 已按{'暂存区' if args.staged else '仓库现状'}重写 {LOCK_NAME}"
              f"（{len(want)} 个 skill，哈希取自 SKILL.md 的 sha256）")
        return 0

    if args.check:
        if not problems:
            print(f"✓ {LOCK_NAME} 与{'暂存区' if args.staged else '仓库'}一致（{len(want)} 个 skill）")
            return 0
        for label, names in report.items():
            if names:
                print(f"✗ {label}：{'、'.join(names)}", file=sys.stderr)
        print(f"  改法：python3 tools/skills_lock.py --update"
              f"（这是派生文件，不要手改）", file=sys.stderr)
        return 1

    for name, entry in want.items():
        print(f"  skills/{name}/SKILL.md   {entry['computedHash'][:16]}…")
    print(f"\n共 {len(want)} 个 skill；"
          f"{'与锁文件一致' if not problems else f'锁文件有 {problems} 处不一致（--check 看详情）'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
