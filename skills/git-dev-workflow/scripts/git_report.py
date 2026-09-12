#!/usr/bin/env python3
"""动手前后的事实对照 + 一段**可原样粘贴**的原始输出。

## 为什么要有它

「我刚才做了什么」这句话，用叙述写一定会漂：少说一条、把两次操作合并成一句、
或者把"我打算做"写成"已经做了"。这个项目里已经栽过两次（把没执行的动作写进报告、
把旧数字当新数字抄）。结论是：**报告里的数字不靠誊写，靠把原始输出贴出来给人对照。**

所以这个脚本干两件事：

1. 动手前 `--capture` 存一份快照；动手后不带参数跑一次，输出**确定性**的差异
   （分支、HEAD、未提交构成、worktree 数、stash 数、未推送数、以及新增了哪些提交）。
2. 末尾附一段命令 + 原始输出的粘贴块 —— 它才是报告里该出现的东西。

## 它不做什么

- **不评价**「这次做得好不好」—— 只报事实。
- **不猜**：拿不到的就写拿不到（例如快照里没有的字段）。
- **不美化**：差异是 0 就写 0。

## 用法

    python3 scripts/git_report.py --capture      # 动手前
    python3 scripts/git_report.py                # 动手后
    python3 scripts/git_report.py --json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys

DEFAULT_NAME = "git-dev-workflow-snapshot.json"


def _load_sibling(name: str):
    """按显式文件路径加载同目录模块（先注册 sys.modules 再 exec）。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"_gitdev_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了同目录模块：{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


S = _load_sibling("git_state")

# 粘贴块里固定跑这几条：全是只读命令，而且都是「报告里会写到」的那些数字。
# 加命令要克制 —— 这个块是给人对照的，不是 log 倾倒。
RAW_COMMANDS = (
    ("分支", ["branch", "--show-current"]),
    ("HEAD", ["rev-parse", "--short", "HEAD"]),
    ("HEAD 的主题", ["log", "-1", "--pretty=%s"]),
    ("未提交条数", ["status", "--porcelain"]),
    ("worktree 条数", ["worktree", "list", "--porcelain"]),
    ("stash 条数", ["stash", "list"]),
    ("未推送条数", ["rev-list", "--count", "HEAD", "--not", "--remotes"]),
)


def snapshot_for_diff(state: dict) -> dict:
    """只留对照需要的字段 —— 快照文件是给人看的，不是把整个 state 倒进去。"""
    return {
        "root": state["root"],
        "branch": state["branch"]["branch"],
        "detached": state["branch"]["detached"],
        "head": state["branch"]["head"],
        "head_subject": S.git_text(state["root"], "log", "-1", "--pretty=%s"),
        "dirty": state["dirty"]["counts"],
        "dirty_total": state["dirty"]["total"],
        "worktrees": len(state["worktrees"]),
        "stash": len(state["stash"]),
        "unpushed": state["unpushed"]["count"],
        "taken_at": S.git_text(state["root"], "log", "-1", "--pretty=%cI") or "",
    }


def snapshot_path(state: dict, explicit: str = "") -> str:
    if explicit:
        return os.path.abspath(explicit)
    common = S.absolute(S.git_text(state["root"], "rev-parse", "--git-common-dir"),
                        state["root"])
    return os.path.join(common, DEFAULT_NAME)


def raw_block(repo: str) -> str:
    """命令 + 原始输出。**报告里该贴的就是这段**，不是转述。"""
    lines = ["```text"]
    for label, args in RAW_COMMANDS:
        code, out, _ = S.run_git(repo, *args)
        value = out.strip()
        if label in ("未提交条数", "worktree 条数", "stash 条数"):
            # 这几条命令本身输出的是列表，这里只数条数 —— 把数的过程写出来，
            # 免得看的人以为我直接"知道"了条数。
            value = str(len([line for line in value.splitlines() if line.strip()]))
        if label == "HEAD 的主题" and not value:
            value = "(还没有提交)"
        lines.append(f"$ git {' '.join(args)}")
        lines.append(f"{value}")
    lines.append("```")
    return "\n".join(lines)


def diff(before: dict, after: dict, repo: str) -> list[str]:
    lines = []

    def row(label: str, old, new) -> None:
        mark = "  " if old == new else "→ "
        lines.append(f"  {mark}{label:<14} {old}  →  {new}" if old != new
                     else f"     {label:<14} {new}（没变）")

    row("分支", before["branch"] or "(detached)", after["branch"] or "(detached)")
    row("HEAD", before["head"], after["head"])
    if before["head"] != after["head"]:
        lines.append(f"     └ 现在的主题：{after['head_subject']}")
        moves = S.git_lines(repo, "log", "--oneline", f"{before['head']}..{after['head']}",
                            "--")
        backs = S.git_lines(repo, "log", "--oneline", f"{after['head']}..{before['head']}",
                            "--")
        if moves:
            lines.append(f"     新增 {len(moves)} 条提交：")
            lines.extend(f"       {item}" for item in moves[:10])
        if backs:
            lines.append(f"     ⚠ 消失了 {len(backs)} 条提交（之前可达、现在不可达）：")
            lines.extend(f"       {item}" for item in backs[:10])
    row("未提交", before["dirty_total"], after["dirty_total"])
    for bucket in ("staged", "unstaged", "untracked", "conflicted"):
        row(f"  {bucket}", before["dirty"].get(bucket, 0), after["dirty"].get(bucket, 0))
    row("worktree 数", before["worktrees"], after["worktrees"])
    row("stash 数", before["stash"], after["stash"])
    row("未推送", before["unpushed"], after["unpushed"])
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="git 动手前后的事实对照")
    parser.add_argument("--repo", default=".", help="仓库路径（默认当前目录）")
    parser.add_argument("--capture", action="store_true", help="存一份快照（动手前跑）")
    parser.add_argument("--file", default="", help="快照文件路径（默认藏在 .git 里）")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)

    state = S.snapshot(args.repo)
    if not state.get("is_repo"):
        print(f"不是一个 git 仓库：{os.path.abspath(args.repo)}", file=sys.stderr)
        return 1

    path = snapshot_path(state, args.file)
    if args.capture:
        payload = snapshot_for_diff(state)
        try:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
        except OSError as exc:
            print(f"写不了快照：{exc}", file=sys.stderr)
            return 1
        print(f"快照已存：{path}")
        print(f"  分支 {payload['branch'] or '(detached)'}  HEAD {payload['head']}  "
              f"未提交 {payload['dirty_total']}  worktree {payload['worktrees']}")
        return 0

    try:
        with open(path, encoding="utf-8") as handle:
            before = json.load(handle)
    except OSError:
        print(f"没有快照文件：{path}", file=sys.stderr)
        print("先跑一次 `--capture`（动手前），再回来跑这条。", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"快照文件坏了（{exc}）：{path}", file=sys.stderr)
        return 1

    if before.get("root") and not S.same_path(before["root"], state["root"]):
        print(f"快照是另一个仓库的：{before['root']}", file=sys.stderr)
        return 1

    after = snapshot_for_diff(state)
    if args.json:
        print(json.dumps({"before": before, "after": after}, ensure_ascii=False, indent=2))
        return 0

    print(f"仓库 {state['root']}")
    print(f"对照（快照：{before.get('taken_at') or '时间未知'}）")
    print("\n".join(diff(before, after, state["root"])))
    print()
    print("原始输出（要贴进报告就贴这一段，别转述）")
    print(raw_block(state["root"]))
    print()
    print("（快照只记了对照需要的字段；没记的就写没记 —— 不猜。）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
