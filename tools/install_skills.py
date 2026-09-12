#!/usr/bin/env python3
"""把仓库里的 skills 同步到 pi 的全局安装位（默认 `~/.agents/skills`）。

## 为什么需要这个脚本（这是评审查出来的真问题，不是预防性设计）

pi 加载的是**副本**，不是仓库本身。实测：`~/.agents/skills/excalidraw-diagram/`
里的 `layout.py`(2079 行) 比仓库 (2650 行) **少 571 行**，`region_boxes` /
`STYLE_AXES` / `frame_stroke` 这些当天新加的能力**一个都没有** ——
也就是说**仓库里改得再好，不跑这个脚本就等于没改**，下一个会话调这个 skill 时
会画出旧配色、旧框线，而且根本不知道「区域」这个能力存在。

同一个东西两份副本、没有同步、没有检查 —— 这正是本项目一直反对的
「两处实现必然漂移」。所以两个子命令缺一不可：

    --check   只比对，有不一致就退出码 1（给 preflight / 钩子 / CI 用）
    （默认）  仓库 → 安装位（会删掉安装位里多出来的文件）

## 边界（写清楚，免得以后被这个脚本自己坑）

- 只动 `<install>/<skill>/` 这几个目录，别处一律不碰；
- `__pycache__` / `.DS_Store` 不参与比对也不复制（本地产物，不是内容）；
- **安装位不存在**时 `--check` 报「未安装」并退出码 0 —— 这是唯一一个不算失败的
  情况（换台机器、CI 里没装都很正常）。除它之外任何不一致都是失败。
"""

from __future__ import annotations

import argparse
import filecmp
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SKILLS = os.path.join(REPO, "skills")

DEFAULT_INSTALL = os.path.join(os.path.expanduser("~"), ".agents", "skills")

# 本地产物：不比对、不复制、不算漂移。
IGNORE_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache"}
IGNORE_FILES = {".DS_Store", ".skill-lock.json"}


def _managed_files(root: str) -> dict[str, str]:
    """目录下所有该参与比对的相对路径 → 绝对路径。

    只收录文件（跳过 `__pycache__` 这类本地产物），并**排序**返回 ——
    比对与复制都按同一份顺序走，输出才稳定、diff 才有意义。
    """
    out: dict[str, str] = {}
    for base, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in IGNORE_DIRS)
        for name in sorted(files):
            if name in IGNORE_FILES:
                continue
            full = os.path.join(base, name)
            out[os.path.relpath(full, root)] = full
    return out


def compare(repo_skill: str, inst_skill: str) -> tuple[list[str], list[str], list[str]]:
    """返回 (内容不同的文件, 只缺在安装位的, 安装位多出来的)。

    用**内容**比对（`filecmp`），不用 mtime/size —— 复制过去之后 mtime 就是新的，
    比时间只会永远说"不一致"。
    """
    repo_files = _managed_files(repo_skill)
    inst_files = _managed_files(inst_skill)
    changed, missing = [], []
    for rel, path in repo_files.items():
        other = inst_files.get(rel)
        if other is None:
            missing.append(rel)
        elif not filecmp.cmp(path, other, shallow=False):
            changed.append(rel)
    extra = sorted(set(inst_files) - set(repo_files))
    return sorted(changed), sorted(missing), extra


def sync_skill(repo_skill: str, inst_skill: str) -> None:
    """仓库 → 安装位。**先删后拷**：否则仓库里删掉的文件会在安装位留成幽灵。

    只删自己管的那些相对路径 —— 不整目录 `rmtree`，免得把安装位里别的工具放的
    东西（比如本地的配置文件）一起抹了。

    读写都包在一个 try 里：这个脚本会去改**用户目录**，出错时必须给一句能懂的话
    （哪一步、哪个文件），不能甩一屏 traceback —— 那种报错没人敢接着按回车。
    """
    repo_files = _managed_files(repo_skill)
    inst_files = _managed_files(inst_skill)
    try:
        for rel in sorted(set(inst_files) - set(repo_files)):
            os.remove(inst_files[rel])
        for rel, path in repo_files.items():
            target = os.path.join(inst_skill, rel)
            parent = os.path.dirname(target)
            if parent:
                os.makedirs(parent, exist_ok=True)
            if not (os.path.exists(target) and filecmp.cmp(path, target, shallow=False)):
                shutil.copy2(path, target)
        # 空目录（比如某个 reference 目录被删空）也清掉
        for base, dirs, files in os.walk(inst_skill, topdown=False):
            if base == inst_skill:
                continue
            if os.path.isdir(base) and not os.listdir(base):
                os.rmdir(base)
    except OSError as exc:
        raise RuntimeError(f"同步 {os.path.basename(inst_skill)} 失败：{exc}") from exc


def skill_names() -> list[str]:
    """仓库里的 skill 目录名。`skills/` 不存在 → 空表 + 一句说明（不是堆栈）。"""
    try:
        entries = os.listdir(SKILLS)
    except OSError as exc:
        print(f"  读不到 skills 目录（{SKILLS}）：{exc}", file=sys.stderr)
        return []
    return sorted(name for name in entries
                  if os.path.isdir(os.path.join(SKILLS, name))
                  and not name.startswith("."))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="只比对，不一致退出码 1")
    parser.add_argument("--install-dir", default=DEFAULT_INSTALL,
                        help=f"安装位（默认 {DEFAULT_INSTALL}）")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.install_dir):
        print(f"  安装位不存在：{args.install_dir} —— 未安装，跳过（不算失败）")
        return 0

    drifted, synced, absent = [], [], []
    for name in skill_names():
        repo_skill = os.path.join(SKILLS, name)
        inst_skill = os.path.join(args.install_dir, name)
        if not os.path.isdir(inst_skill):
            absent.append(name)
            continue
        changed, missing, extra = compare(repo_skill, inst_skill)
        if not (changed or missing or extra):
            synced.append(name)
            continue
        drifted.append((name, changed, missing, extra))
        if not args.check:
            try:
                sync_skill(repo_skill, inst_skill)
            except RuntimeError as exc:
                print(f"  ✗ {exc}", file=sys.stderr)
                return 2

    if args.check:
        for name, changed, missing, extra in drifted:
            print(f"  ✗ {name}：与仓库不一致 "
                  f"（内容不同 {len(changed)}、安装位缺 {len(missing)}、"
                  f"安装位多 {len(extra)}）")
            for rel in (missing + changed + extra)[:6]:
                print(f"      {rel}")
        for name in synced:
            print(f"  ✓ {name}：与仓库一致")
        if absent:
            print(f"  · 未安装：{'、'.join(absent)}")
        if drifted:
            print("  → 跑 `python3 tools/install_skills.py` 同步（别手动拷，会漏）")
            return 1
        return 0

    for name, changed, missing, extra in drifted:
        print(f"  ✓ 已同步 {name}（改 {len(changed)}、补 {len(missing)}、删 {len(extra)}）")
    for name in synced:
        print(f"  · {name} 本来就一致")
    if absent:
        print(f"  · 未安装（跳过）：{'、'.join(absent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
