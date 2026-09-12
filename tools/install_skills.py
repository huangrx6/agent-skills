#!/usr/bin/env python3
"""把仓库里的 skills 装到 pi 的全局目录（默认 `~/.agents/skills`）。

## 为什么需要这个脚本

pi 加载的是**安装位**，不是仓库本身。实测过一次：`~/.agents/skills/` 里是一份**副本**，
比仓库少 571 行，当天新加的能力一个都没有 —— 仓库里改得再好，没装过去就等于没改。

## 默认用**软链**，不是拷贝（这是问过 pi 的实现之后定的）

`npx skills add` 与"手动拷贝"都会留副本，于是多出"两份东西必然漂移"这件事，
还得配一套同步与漂移检查。软链从根上没有这个问题：装的就是仓库那一份。

pi 认不认软链**不能靠猜**，两处证据：

1. 源码 `dist/core/skills.js` 里是明写的 —— 对每个目录项先 `entry.isDirectory()`，
   若是 `isSymbolicLink()` 再用 `statSync`（会跟随软链）取真实类型，注释就是
   `// For symlinks, check if they point to a directory and follow them`；
2. 用**它自己的** `loadSkillsFromDir()` 实测：目录里放两个指向本仓库的软链 +
   一个普通目录，结果两个 skill 都被发现、非 skill 目录被正确忽略。

    python3 tools/install_skills.py              # 默认：装成软链（推荐）
    python3 tools/install_skills.py --copy       # 要副本（比如仓库会被移走）
    python3 tools/install_skills.py --check      # 只检查：软链指向对不对 / 副本内容一致吗

## 边界

- 只动 `<install>/<skill>/` 这几个条目，别处一律不碰；
- `__pycache__` / `.DS_Store` 这类本地产物不参与比对、也不参与复制；
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


def _same_path(left: str, right: str) -> bool:
    """两个路径是不是同一个东西。

    `realpath` 两边都要做：macOS 上 `/var` 与 `/private/var` 是同一个目录的两个名字，
    只比字符串会把"其实指对了"判成错的（这个坑在本项目的其它脚本里踩过）。
    """
    return os.path.realpath(left) == os.path.realpath(right)


def _managed_files(root: str) -> dict[str, str]:
    """目录下所有该参与比对的相对路径 → 绝对路径。"""
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
    """返回 (内容不同的文件, 只缺在安装位的, 安装位多出来的)。**按内容比**，不比 mtime。"""
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


def installed_kind(inst_skill: str) -> str:
    """安装位这个条目是什么：`link` / `copy` / `missing`。

    ⚠️ 顺序要紧：**先判软链**。`os.path.isdir()` 会跟随软链，所以一个指向目录的软链
    在它眼里也是"目录" —— 先问 isdir 就永远看不到软链。
    """
    if os.path.islink(inst_skill):
        return "link"
    if os.path.isdir(inst_skill):
        return "copy"
    return "missing"


def install_link(repo_skill: str, inst_skill: str) -> None:
    """把它装成指向仓库的软链。已经是**指对了**的软链就不动（免得每次重装）。"""
    if os.path.islink(inst_skill) and _same_path(inst_skill, repo_skill):
        return
    try:
        if os.path.islink(inst_skill) or os.path.isfile(inst_skill):
            os.remove(inst_skill)
        elif os.path.isdir(inst_skill):
            shutil.rmtree(inst_skill)          # 旧的副本：删掉，换成引用
        os.symlink(repo_skill, inst_skill)
    except OSError as exc:
        raise RuntimeError(f"装软链失败（{inst_skill}）：{exc}") from exc


def install_copy(repo_skill: str, inst_skill: str) -> None:
    """仓库 → 安装位（副本）。**先删后拷**：否则仓库里删掉的文件会留成幽灵。

    只删自己管的那些相对路径 —— 不整目录 rmtree，免得把安装位里别的工具放的东西
    一起抹了。
    """
    if os.path.islink(inst_skill):
        try:
            os.remove(inst_skill)          # 旧软链：先摘掉，否则会往仓库里拷
        except OSError as exc:
            raise RuntimeError(f"摘掉旧软链失败（{inst_skill}）：{exc}") from exc
    repo_files = _managed_files(repo_skill)
    inst_files = _managed_files(inst_skill) if os.path.isdir(inst_skill) else {}
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
        for base, dirs, files in os.walk(inst_skill, topdown=False):
            if base == inst_skill:
                continue
            if os.path.isdir(base) and not os.listdir(base):
                os.rmdir(base)
    except OSError as exc:
        raise RuntimeError(f"同步 {os.path.basename(inst_skill)} 失败：{exc}") from exc


def skill_names(skills_dir: str) -> list[str]:
    """`skills_dir` 里的 skill 目录名。目录不存在 → 空表 + 一句说明（不是堆栈）。"""
    try:
        entries = os.listdir(skills_dir)
    except OSError as exc:
        print(f"  读不到 skills 目录（{skills_dir}）：{exc}", file=sys.stderr)
        return []
    return sorted(name for name in entries
                  if os.path.isdir(os.path.join(skills_dir, name))
                  and not name.startswith("."))


def main(argv: list[str] | None = None, skills_dir: str | None = None) -> int:
    """`skills_dir` 是给测试用的注入点 —— 不传就用仓库里的 `skills/`。

    做成参数而不是让测试改模块全局：那样测试得猴补 `I.SKILLS`，读代码的人看不出
    依赖从哪来，类型检查也会报（实测报的就是它）。"""
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="只检查，不一致退出码 1")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--link", action="store_true",
                      help="装成软链（默认）—— 装的就是仓库那一份，永不漂移")
    mode.add_argument("--copy", action="store_true",
                      help="装成副本（仓库会被移走时用这个）")
    parser.add_argument("--install-dir", default=DEFAULT_INSTALL,
                        help=f"安装位（默认 {DEFAULT_INSTALL}）")
    args = parser.parse_args(argv)

    as_link = not args.copy
    if not os.path.isdir(args.install_dir):
        print(f"  安装位不存在：{args.install_dir} —— 未安装，跳过（不算失败）")
        return 0

    source = skills_dir or SKILLS
    problems: list[str] = []
    for name in skill_names(source):
        repo_skill = os.path.join(source, name)
        inst_skill = os.path.join(args.install_dir, name)
        kind = installed_kind(inst_skill)

        if args.check:
            if kind == "missing":
                problems.append(f"{name}：未安装")
                print(f"  ✗ {name}：未安装")
            elif kind == "link":
                if _same_path(inst_skill, repo_skill):
                    print(f"  ✓ {name}：软链 → 本仓库（不可能漂移）")
                else:
                    target = os.path.realpath(inst_skill) if os.path.exists(inst_skill) \
                        else "（断链）"
                    problems.append(f"{name}：软链指向别处 → {target}")
                    print(f"  ✗ {name}：软链指向别处 → {target}")
            else:
                changed, missing, extra = compare(repo_skill, inst_skill)
                if changed or missing or extra:
                    problems.append(f"{name}：副本与仓库不一致")
                    print(f"  ✗ {name}：副本与仓库不一致（内容不同 {len(changed)}、"
                          f"安装位缺 {len(missing)}、安装位多 {len(extra)}）")
                    for rel in (missing + changed + extra)[:6]:
                        print(f"      {rel}")
                else:
                    print(f"  ✓ {name}：副本与仓库一致")
            continue

        try:
            if as_link:
                if kind == "link" and _same_path(inst_skill, repo_skill):
                    print(f"  · {name}：已经是软链，跳过")
                    continue
                was = "副本" if kind == "copy" else ("旧软链" if kind == "link" else "无")
                install_link(repo_skill, inst_skill)
                print(f"  ✓ {name}：装成软链（原来：{was}）")
            else:
                if kind == "missing":
                    print(f"  ✓ {name}：装成副本")
                else:
                    print(f"  ✓ {name}：更新副本（原来：{'软链' if kind == 'link' else '副本'}）")
                install_copy(repo_skill, inst_skill)
        except RuntimeError as exc:
            print(f"  ✗ {exc}", file=sys.stderr)
            return 2

    if args.check:
        if problems:
            print(f"  → 跑 `python3 tools/install_skills.py`"
                  f"{' --copy' if any('副本' in p for p in problems) else ''}"
                  f"（默认装成软链；软链不会漂移）")
            return 1
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
