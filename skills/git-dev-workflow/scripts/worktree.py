#!/usr/bin/env python3
"""worktree 的生命周期：建 / 列 / 查 stale / 回收。

## 放在哪（已定：**仓库同级**）

    /a/b/specforge                         ← 仓库
    /a/b/specforge-feat-ui-shadcn-vue      ← 它的 worktree，同级

好处是**在仓库之外**：不用往 `.gitignore` 里塞规则，`git status` 也看不见它们。
（放在仓库里的 `.worktrees/` 也能用，但每条新分支都要多一次「记得别提交」的自觉 ——
而自觉是这整套东西里最不可靠的一环。）

## 判据不在这里，在 git_guard.py

「这个 worktree 能不能回收」只有**一个**实现：`git_guard.py` 的 `delete-worktree`。
这个脚本调用它，不重写它 —— 两份判据必然漂移，而漂移的那一份会让你在错误的一侧
得到安全感。

判据按**实测到的事实**定：`git worktree remove` 只拿掉工作目录和记录，**不删分支、
不删提交**。所以真正会丢的只有那一件 —— **那个目录里的未提交改动**（脏 → 拦）；
分支没并进基线只是**提醒**（不丢东西，但先确认你不是做到一半）。

## 不做的事

- **不 `--force`**：`remove` 走判据，判据说不行就是不行。
- **不删还有文件的 worktree**：那是 `rm -rf` 的活，`git worktree remove` 会拒绝，
  这里也不替它绕过去。
- **不碰你的分支合并策略**：这个脚本只负责把目录建出来、把目录收回去。

## 退出码

- `0` 成功
- `1` 被拒绝（原因会打出来）或执行失败
- `3` / `4`：`remove` 沿用它拿到的 guard 结论（WARN / BLOCK），不自己另定一套

## 用法

    python3 scripts/worktree.py list
    python3 scripts/worktree.py list --stale
    python3 scripts/worktree.py create feat/ui --from main
    python3 scripts/worktree.py prune
    python3 scripts/worktree.py remove ../specforge-feat-ui
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys

SAFE, WARN, BLOCK = 0, 3, 4


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
GUARD = _load_sibling("git_guard")


class _GuardArgs:
    """喂给 guard 的参数壳子。只带它那个动作会读到的字段。"""

    def __init__(self, name: str = ""):
        self.name = name
        self.include_ignored = False
        self.shared = False
        self.branch = ""
        self.remote = "origin"


# ── 路径与命名 ────────────────────────────────────────────────────────────
def slug_for(branch: str) -> str:
    """把分支名变成目录名。

    `/` 不能留在目录名里（会变成多一层目录），所以换 `-`；其余不认识的字符也换掉。
    **不强制小写**：macOS 的文件系统默认不区分大小写，`Feat/x` 与 `feat/x` 会撞到一起 ——
    这个脚本不去"修"它，只是撞上了会因为目标已存在而拒绝。
    """
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", branch.replace("/", "-"))
    return cleaned.strip("-.") or "worktree"


def target_path(repo_root: str, branch: str) -> str:
    root = os.path.abspath(repo_root)
    return os.path.join(os.path.dirname(root), f"{os.path.basename(root)}-{slug_for(branch)}")


def _toplevel_of(path: str) -> str:
    try:
        if not os.path.isdir(path):
            return ""
    except OSError:
        return ""
    return S.git_text(path, "rev-parse", "--show-toplevel")


def create_refusals(state: dict, branch: str, target: str) -> list[str]:
    """建之前要拒绝的理由。空列表 = 可以建。

    这里全是**拒绝**：worktree 建错了不会丢东西，但会留下一个没人管的目录 +
    一个占着分支名的坑，收拾起来比一开始就拒绝麻烦。
    """
    reasons: list[str] = []
    if not branch.strip():
        reasons.append("分支名是空的")
    if os.path.exists(target):
        reasons.append(f"目标路径已经存在：{target}")
    if branch in [b["name"] for b in state["branches"]]:
        reasons.append(f"本地已经有分支 {branch} —— worktree 只能挂到一个没被占用的分支上")
    if any(S.is_dir(w["path"]) and S.same_path(w["path"], target)
           for w in state["worktrees"]):
        reasons.append(f"已经有一个 worktree 挂在这个路径上：{target}")
    parent = os.path.dirname(target)
    if not S.is_dir(parent):
        reasons.append(f"上一级目录不存在：{parent}")
    # 同级目录落在**另一个**仓库里的话，那个仓库会把新目录当成未跟踪内容收进去
    outer = _toplevel_of(parent)
    if outer and not S.same_path(outer, state["root"]):
        reasons.append(f"同级目录落在另一个 git 仓库里（{outer}）—— 换个位置，"
                       "或者把那个仓库排除掉")
    return reasons


# ── 子命令 ────────────────────────────────────────────────────────────────
def recyclable(state: dict, path: str) -> int:
    """复用 guard 的结论，不另写一套。"""
    return GUARD.evaluate("delete-worktree", state, _GuardArgs(path)).level


def render_list(state: dict, stale_only: bool) -> str:
    rows = []
    for item in state["worktrees"]:
        if item["exists"] and item["prunable"]:
            pass
        level = recyclable(state, item["path"])
        if stale_only and level != SAFE:
            continue
        flags = []
        if not item["exists"]:
            flags.append("目录已不存在")
        if item["prunable"]:
            flags.append("prunable")
        if item["dirty"]:
            flags.append(f"未提交 {item['dirty']}")
        if item["unpushed"]:
            flags.append(f"未推送 {item['unpushed']}")
        rows.append({"path": item["path"], "branch": item["branch"] or "(detached)",
                     "head": item["head"], "flags": flags,
                     "verdict": {SAFE: "SAFE", WARN: "WARN", BLOCK: "BLOCK"}[level]})
    if not rows:
        return "没有可回收的 worktree" if stale_only else "一个 worktree 都没有"
    lines = [f"{'结论':<6} {'分支':<30} {'HEAD':<9} 路径 / 备注"]
    for row in rows:
        note = "  [" + ", ".join(row["flags"]) + "]" if row["flags"] else ""
        lines.append(f"{row['verdict']:<6} {row['branch']:<30} {row['head']:<9} "
                     f"{row['path']}{note}")
    lines.append("（结论来自 git_guard.py 的三项前置：已并入基线 / 无未推送 / 无未提交）")
    return "\n".join(lines)


def run(args) -> tuple[int, str]:
    state = S.snapshot(args.repo)
    if not state.get("is_repo"):
        return 1, f"不是一个 git 仓库：{os.path.abspath(args.repo)}"

    if args.command == "list":
        rows = render_list(state, args.stale)
        if args.json:
            return 0, json.dumps({"is_repo": True, "worktrees": [
                {"path": w["path"], "branch": w["branch"], "exists": w["exists"],
                 "prunable": w["prunable"], "dirty": w["dirty"], "unpushed": w["unpushed"],
                 "verdict": {SAFE: "SAFE", WARN: "WARN", BLOCK: "BLOCK"}[
                     recyclable(state, w["path"])]} for w in state["worktrees"]
                if not args.stale or recyclable(state, w["path"]) == SAFE]},
                ensure_ascii=False, indent=2)
        return 0, rows

    if args.command == "create":
        branch = args.branch or ""
        target = args.at or target_path(state["root"], branch)
        target = os.path.abspath(target)
        reasons = create_refusals(state, branch, target)
        if reasons:
            return 1, ("建不了，先解决这些：\n"
                       + "\n".join(f"  - {reason}" for reason in reasons))
        cmd = ["worktree", "add", "-b", branch, target]
        if args.from_ref:
            cmd.append(args.from_ref)
        code, _, err = S.run_git(state["root"], *cmd)
        if code != 0:
            return 1, f"`git {' '.join(cmd)}` 失败了：{err.strip()}"
        after = S.snapshot(args.repo)
        item = next((w for w in after["worktrees"] if S.same_path(w["path"], target)), None)
        where = f"{item['branch']} @ {item['head']}" if item else "(刚建出来，快照里还没出现)"
        return 0, (f"建好了：{target}\n  {where}\n"
                   f"  注意：这个目录在仓库之外，不用改 .gitignore")

    if args.command == "prune":
        before = len(state["worktrees"])
        code, out, err = S.run_git(state["root"], "worktree", "prune", "-v")
        if code != 0:
            return 1, f"prune 失败：{err.strip()}"
        after = S.snapshot(args.repo)
        removed = [line for line in out.splitlines() if line.strip()]
        lines = [f"worktree 条目：{before} → {len(after['worktrees'])}"]
        if removed:
            lines.append("清理掉的记录：")
            lines.extend(f"  {line}" for line in removed)
        else:
            lines.append("没有需要清理的记录（prunable 的那些目录可能又回来了）")
        return 0, "\n".join(lines)

    if args.command == "remove":
        path = args.path or ""
        verdict = GUARD.evaluate("delete-worktree", state, _GuardArgs(path))
        if verdict.level != SAFE:
            return verdict.level, (GUARD.render(verdict)
                                   + "\n\n（三项前置没全过，这里不会替你动手）")
        item = next((w for w in state["worktrees"] if S.same_path(w["path"], path)), None)
        if item is None:
            return 1, f"worktree 清单里没有这个路径：{path}"
        if not item["exists"]:
            code, out, err = S.run_git(state["root"], "worktree", "prune", "-v")
            if code != 0:
                return 1, f"prune 失败：{err.strip()}"
            return 0, f"目录本来就不存在，已经用 prune 清掉记录：\n{out.strip()}"
        code, _, err = S.run_git(state["root"], "worktree", "remove", item["path"])
        if code != 0:
            return 1, f"移除失败：{err.strip()}\n（目录里还有文件的话，这里是不会替你 --force 的）"
        after = S.snapshot(args.repo)
        return 0, (f"移除了 {item['path']}\n"
                   f"worktree 条目：{len(state['worktrees'])} → {len(after['worktrees'])}"
                   f"（分支 {item['branch']} 还在，要删它用 git_guard.py delete-branch）")

    return 1, f"不认识的子命令：{args.command}"


def main(argv: list[str] | None = None) -> int:
    # `--repo` / `--json` 要能写在**子命令前面或后面**都行：argparse 的子命令不会自动
    # 继承主解析器上的选项，而人两个位置都会写（我自己第一次跑就写在了后面，
    # 拿回一句 unrecognized arguments）。
    #
    # 两边都挂同一个共同解析器，并且默认值用 SUPPRESS —— 否则子解析器的默认值会把
    # 主解析器已经解析到的值盖掉（argparse 的老坑），所以真正的默认值在 parse 之后补。
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--repo", default=argparse.SUPPRESS, help="仓库路径（默认当前目录）")
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help="list 用 JSON 输出")

    parser = argparse.ArgumentParser(description="worktree 的建 / 列 / 查 / 回收",
                                     parents=[common])
    sub = parser.add_subparsers(dest="command")

    p_list = sub.add_parser("list", parents=[common], help="列出所有 worktree 与回收结论")
    p_list.add_argument("--stale", action="store_true", help="只列可安全回收的")

    p_create = sub.add_parser("create", parents=[common],
                              help="新建一个 worktree（默认放仓库同级）")
    p_create.add_argument("branch", help="新分支名")
    p_create.add_argument("--from", dest="from_ref", default="", help="从哪个 ref 起（默认 HEAD）")
    p_create.add_argument("--at", default="", help="显式指定路径（默认仓库同级）")

    sub.add_parser("prune", parents=[common], help="清掉目录已经不存在的 worktree 记录")

    p_remove = sub.add_parser("remove", parents=[common],
                              help="回收一个 worktree（过三项前置）")
    p_remove.add_argument("path", help="worktree 路径")

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 1
    args.repo = getattr(args, "repo", ".")
    args.json = getattr(args, "json", False)
    code, message = run(args)
    stream = sys.stdout if code == 0 else sys.stderr
    print(message, file=stream)
    return code


if __name__ == "__main__":
    sys.exit(main())
