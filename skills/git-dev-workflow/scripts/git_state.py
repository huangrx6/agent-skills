#!/usr/bin/env python3
"""只读状态快照 —— 报告里的 git 状态只能来自这里。

## 为什么要有它

「现在 git 是什么状态」这件事，凭记忆答一定会错：分支可能早被切走、工作区可能是
上一个 agent 留下的、上游可能根本不存在、worktree 的目录可能已经被人删了。
这个脚本只做一件事：**把当前真实状态原样读出来**，让上层照抄，而不是回忆。

## 它不做的事（边界，写在最前面）

- **不改任何东西**：只用 `rev-parse` / `status` / `log` / `worktree list` 这类只读命令。
- **不做判断**：不说「可以安全删」。那是 `git_guard.py` 的事。
- **不读文件内容**：分类只看**路径与文件名**。所以「疑似凭据」是**名字启发式** ——
  命中不等于真含密钥，没命中也不等于安全。它唯一的作用是：让「我要丢掉这些东西」
  这句话里**至少那些显眼的**被看见。
- **不猜远端**：拿不到远端状态时明说拿不到，不当成 0。

## 退出码

- `0` 正常
- `1` 不是一个 git 仓库（stderr 说清）
- `2` 正处于中间态（rebase / merge / cherry-pick / revert / bisect / 有冲突）——
  给上层一个机械信号：现在别乱动。

## 用法

    python3 scripts/git_state.py                 # 当前目录
    python3 scripts/git_state.py --repo /path    # 指定仓库
    python3 scripts/git_state.py --json          # 给 agent 读
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

# ── 名字启发式（只用于告警；.gitignore 才是「什么不该进版本库」的权威）──────
ARTIFACT_DIRS = (
    "node_modules", "dist", "build", "target", ".venv", "venv", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".next", ".nuxt",
    "coverage", ".gradle", ".idea", ".vscode",
)
ARTIFACT_SUFFIXES = (
    ".pyc", ".pyo", ".log", ".class", ".o", ".a", ".so", ".dylib",
    ".dll", ".exe", ".tmp", ".bak", ".orig", ".rej", ".swp",
)
SECRET_NAMES = (
    ".npmrc", ".pypirc", ".netrc", ".htpasswd", "credentials",
    "id_rsa", "id_ed25519", "id_ecdsa",
)
# `.env` 是一整族（`.env.local` / `.env.production` / `.envrc` …），
# 逐个列名字一定会漏 —— 用例里 `.env.local` 就是这么漏掉的。所以按前缀判。
SECRET_PREFIXES = (".env",)
SECRET_TOKENS = (
    "secret", "token", "credential", "password", "passwd", "apikey",
    "api-key", "api_key", "private_key", "privatekey", "service-account",
)
SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".ppk", ".asc")
SOURCE_SUFFIXES = (
    ".py", ".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs", ".go", ".rs", ".java",
    ".kt", ".kts", ".swift", ".c", ".h", ".cc", ".cpp", ".hpp", ".cs", ".rb",
    ".php", ".sh", ".bash", ".zsh", ".fish", ".sql", ".vue", ".svelte",
    ".scala", ".lua", ".pl", ".dart", ".ex", ".exs", ".clj", ".hs", ".ml",
)
DOC_SUFFIXES = (".md", ".mdx", ".rst", ".txt", ".adoc", ".org")

BASELINE_CANDIDATES = ("main", "dev", "master")

CONFLICT_CODES = ("DD", "AU", "UD", "UA", "DU", "AA", "UU")


# ── 文件系统小工具：全部吞掉 OSError ────────────────────────────────────────
# 路径可能不存在、可能是断链、可能没权限。这些都不该让整张快照失败 ——
# 快照的价值恰恰在于「把拿不到的部分也如实说出来」。
def is_dir(path: str) -> bool:
    try:
        return os.path.isdir(path)
    except OSError:
        return False


def is_file(path: str) -> bool:
    try:
        return os.path.isfile(path)
    except OSError:
        return False


def is_executable(path: str) -> bool:
    try:
        return os.path.isfile(path) and os.access(path, os.X_OK)
    except OSError:
        return False


def list_dir(path: str) -> list[str]:
    try:
        return sorted(os.listdir(path))
    except OSError:
        return []


def as_int(text: str, default: int = 0) -> int:
    """把 git 输出的数字转成 int。拿不到就给 default —— 不抛异常。

    这里必须自己包一层：数字来自 git 输出，格式变了或输出被截断都可能拿到非数字。
    """
    try:
        return int(text.strip())
    except (TypeError, ValueError):
        return default


def absolute(path: str, base: str) -> str:
    """把 git 报回来的**可能是相对**的路径按 base 解析成绝对路径。"""
    try:
        return os.path.abspath(path if os.path.isabs(path) else os.path.join(base, path))
    except OSError:
        return path


# ── 跑 git ────────────────────────────────────────────────────────────────
def run_git(repo: str, *args: str) -> tuple[int, str, str]:
    """跑一条 git 命令，返回 (退出码, stdout, stderr)。"""
    try:
        proc = subprocess.run(
            ["git", "-C", repo, *args],
            capture_output=True, text=True, check=False,
        )
    except OSError as exc:                     # git 本身没装
        return 127, "", str(exc)
    return proc.returncode, proc.stdout, proc.stderr


def git_lines(repo: str, *args: str) -> list[str]:
    code, out, _ = run_git(repo, *args)
    return out.splitlines() if code == 0 else []


def git_text(repo: str, *args: str) -> str:
    code, out, _ = run_git(repo, *args)
    return out.strip() if code == 0 else ""


def repo_root(start: str) -> str | None:
    code, out, _ = run_git(start, "rev-parse", "--show-toplevel")
    return out.strip() if code == 0 and out.strip() else None


def git_dir(repo: str) -> str:
    return git_text(repo, "rev-parse", "--absolute-git-dir")


# ── 分类：只看名字 ────────────────────────────────────────────────────────
def classify(path: str) -> str:
    """把路径粗分成 secret / artifact / source / docs / other。

    **这是名字启发式，不是安全检查**：不读内容，也不认识私有命名习惯。
    """
    lowered = path.lower()
    parts = lowered.split("/")
    base = parts[-1]
    _, ext = os.path.splitext(base)

    if base in SECRET_NAMES or ext in SECRET_SUFFIXES:
        return "secret"
    if any(base.startswith(prefix) for prefix in SECRET_PREFIXES):
        return "secret"
    if any(token in base for token in SECRET_TOKENS):
        return "secret"
    if any(part in ARTIFACT_DIRS for part in parts[:-1]) or ext in ARTIFACT_SUFFIXES:
        return "artifact"
    if ext in DOC_SUFFIXES:
        return "docs"
    if ext in SOURCE_SUFFIXES:
        return "source"
    return "other"


# ── 各种采集器 ────────────────────────────────────────────────────────────
def mid_operation(repo: str) -> list[str]:
    """正在进行的操作 —— 这时候任何写操作都该先停下来问清楚。"""
    root = git_dir(repo)
    if not root:
        return []
    in_progress: list[str] = []
    if is_dir(os.path.join(root, "rebase-merge")) or \
            is_dir(os.path.join(root, "rebase-apply")):
        in_progress.append("rebase")
    for marker, label in (("MERGE_HEAD", "merge"), ("CHERRY_PICK_HEAD", "cherry-pick"),
                          ("REVERT_HEAD", "revert"), ("BISECT_LOG", "bisect")):
        if is_file(os.path.join(root, marker)):
            in_progress.append(label)
    if is_dir(os.path.join(root, "sequencer")):
        in_progress.append("sequencer")
    return in_progress


def dirty_entries(repo: str, ignored: bool = False) -> list[dict]:
    """工作区条目。用 `-z` 解析：路径含空格/中文/换行时不会串行。"""
    args = ["status", "--porcelain=v1", "-z", "--untracked-files=all"]
    if ignored:
        args.append("--ignored=matching")
    code, out, _ = run_git(repo, *args)
    if code != 0:
        return []
    fields = out.split("\0")
    entries: list[dict] = []
    index = 0
    while index < len(fields):
        raw = fields[index]
        index += 1
        if not raw:
            continue
        status = raw[:2]
        path = raw[3:] if len(raw) > 3 else ""
        origin = None
        if status[0] in "RC":            # 重命名/复制：下一段是原路径
            if index < len(fields):
                origin = fields[index]
                index += 1
        entries.append({"code": status, "path": path, "origin": origin,
                        "kind": classify(path)})
    return entries


def buckets(entries: list[dict]) -> dict:
    """按「它处于哪个位置」分桶；冲突是独立的桶（不能和别的混着看）。"""
    return {
        "staged": [e for e in entries if e["code"][0] not in " ?!"],
        "unstaged": [e for e in entries if e["code"][1] not in " ?!"],
        "untracked": [e for e in entries if e["code"] == "??"],
        "conflicted": [e for e in entries if e["code"] in CONFLICT_CODES],
        "ignored": [e for e in entries if e["code"] == "!!"],
    }


def by_kind(entries: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry["kind"]] = counts.get(entry["kind"], 0) + 1
    return counts


def protected_paths(entries: list[dict]) -> list[dict]:
    """**看起来不该被提交**的那些（凭据）—— 单独拎出来，别埋在计数里。"""
    return [e for e in entries if e["kind"] == "secret"]


def branch_state(repo: str) -> dict:
    code, out, _ = run_git(repo, "symbolic-ref", "-q", "--short", "HEAD")
    branch = out.strip() if code == 0 else ""
    baseline = ""
    for candidate in BASELINE_CANDIDATES:
        if git_text(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{candidate}"):
            baseline = candidate
            break
    # 在 worktree 里时 git-dir 与 git-common-dir 不同 —— 两个都可能是相对路径，
    # 所以要先按仓库根解析再比，不然主检出也会被误判成 worktree。
    common = absolute(git_text(repo, "rev-parse", "--git-common-dir"), repo)
    return {"branch": branch, "detached": not branch,
            "head": git_text(repo, "rev-parse", "--short", "HEAD"),
            "baseline": baseline, "in_worktree": common != git_dir(repo)}


def upstream_state(repo: str) -> dict:
    """相对上游的位置。**没有上游时明说**，不能当成 0（这是踩过的坑）。"""
    code, out, _ = run_git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name",
                           "@{upstream}")
    upstream = out.strip() if code == 0 else ""
    if not upstream:
        return {"upstream": "", "ahead": None, "behind": None,
                "note": "没有上游：ahead/behind 无从谈起（不是 0）"}
    code, out, _ = run_git(repo, "rev-list", "--left-right", "--count",
                           f"{upstream}...HEAD")
    if code != 0:
        return {"upstream": upstream, "ahead": None, "behind": None,
                "note": "算不出来（上游 ref 可能已失效）"}
    parts = (out.split() + ["?", "?"])[:2]
    return {"upstream": upstream, "ahead": as_int(parts[1], -1),
            "behind": as_int(parts[0], -1), "note": ""}


def unpushed(repo: str, ref: str = "HEAD") -> dict:
    """未推送 = 不被任何远端 ref 覆盖。

    **没有远端时如实说明**，否则会报出「未推送 = 整个历史」这种吓人的数字，
    让人以为有几百条没推上去。
    """
    if not git_lines(repo, "remote"):
        return {"has_remote": False,
                "count": as_int(git_text(repo, "rev-list", "--count", ref)),
                "subjects": git_lines(repo, "log", "--oneline", "-n", "10", ref),
                "note": "这个仓库没有任何远端 —— 这个数字是整个历史，不是没推上去的"}
    return {"has_remote": True,
            "count": as_int(git_text(repo, "rev-list", "--count", ref, "--not", "--remotes")),
            "subjects": git_lines(repo, "log", "--oneline", "-n", "10",
                                  ref, "--not", "--remotes"),
            "note": ""}


def merged_into(repo: str, ref: str, baseline: str) -> bool | None:
    """ref 是否已并入 baseline。

    **baseline 不存在时返回 None，不是 False**：`git branch --merged main dev`
    在两个 ref 不都存在时会静默失败、返回空列表，结果看起来就像「没有任何分支已并入」。
    这个坑踩过 —— 所以每个基线都要先确认它真的存在，再问问题。
    """
    if not baseline or not git_text(repo, "rev-parse", "--verify", "--quiet",
                                    f"refs/heads/{baseline}"):
        return None
    code, _, _ = run_git(repo, "merge-base", "--is-ancestor", ref, baseline)
    return code == 0


def local_branches(repo: str, baseline: str = "") -> list[dict]:
    current = branch_state(repo)["branch"]
    out = []
    for name in git_lines(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads"):
        if not name:
            continue
        out.append({"name": name, "current": name == current,
                    "merged": merged_into(repo, name, baseline) if baseline else None,
                    "unpushed": unpushed(repo, name)["count"]})
    return out


def same_path(first: str, second: str) -> bool:
    """比较路径时**解析符号链接**。

    macOS 上这是必须的：`tempfile` 给的 `/var/folders/...` 实际是
    `/private/var/folders/...`，只比 abspath 会把同一个目录认成两个。
    用例就是这么把它抓出来的：worktree 明明在清单里，却被判成「清单里没有这个路径」。
    真实环境里同样会撞上（`/tmp`、symlink 过的家目录）。

    **唯一实现**：worktree 清单、guard 的路径比对都用它。
    （写这个脚本时先在 guard 里写了一份、又在 state 里写了一份 —— 两份必然漂移，已收回。）
    """
    try:
        return os.path.realpath(first) == os.path.realpath(second)
    except OSError:
        return first == second


def worktree_state(repo: str, known: dict | None = None) -> list[dict]:
    """worktree 清单。

    **目录不存在时明说** —— 那正是 `prunable` 的含义，也是「能不能回收」的第一个判据。
    （手工排查时踩过：把命令跑失败当成「0 个未提交」，于是看起来一切正常。）

    `known` 是已经算过的 {路径: {dirty, unpushed}}：当前站在里面的那个仓库就是主
    worktree，它的脏文件/未推送数在 `snapshot()` 里刚算过，再算一遍不只是浪费 ——
    两次调用之间文件真的会变，两个数字还会不一致。
    """
    known = known or {}
    out: list[dict] = []
    for block in git_text(repo, "worktree", "list", "--porcelain").split("\n\n"):
        if not block.strip():
            continue
        item: dict = {"path": "", "head": "", "branch": "", "detached": False,
                      "prunable": False, "exists": False, "dirty": None,
                      "unpushed": None}
        for line in block.splitlines():
            if line.startswith("worktree "):
                item["path"] = line[len("worktree "):]
            elif line.startswith("HEAD "):
                item["head"] = line[5:13]
            elif line.startswith("branch "):
                item["branch"] = line[len("branch refs/heads/"):]
            elif line.strip() == "detached":
                item["detached"] = True
            elif line.startswith("prunable"):
                item["prunable"] = True
        if item["path"]:
            item["exists"] = is_dir(item["path"])
            if item["exists"]:
                cached = next((v for k, v in known.items()
                               if same_path(k, item["path"])), None)
                if cached:
                    item["dirty"] = cached["dirty"]
                    item["unpushed"] = cached["unpushed"]
                else:
                    item["dirty"] = len(dirty_entries(item["path"]))
                    item["unpushed"] = unpushed(item["path"])["count"]
        out.append(item)
    return out


def stash_state(repo: str) -> list[dict]:
    out = []
    for line in git_lines(repo, "stash", "list", "--format=%gd%x1f%s%x1f%ci"):
        parts = line.split("\x1f")
        if len(parts) >= 2:
            out.append({"ref": parts[0], "subject": parts[1],
                        "date": parts[2] if len(parts) > 2 else ""})
    return out


def submodule_state(repo: str) -> dict:
    if not is_file(os.path.join(repo, ".gitmodules")):
        return {"present": False, "items": []}
    items = []
    for line in git_lines(repo, "submodule", "status", "--recursive"):
        flag, rest = (line[0], line[1:]) if line[:1] in "-+U " else (" ", line)
        parts = rest.split()
        if len(parts) >= 2:
            items.append({"path": parts[1], "sha": parts[0][:8],
                          "state": {"-": "未初始化", "+": "与父仓库记录不一致",
                                    "U": "有冲突"}.get(flag, "正常"),
                          "modified": flag in "+U"})
    return {"present": True, "items": items}


def hooks_state(repo: str) -> dict:
    """仓库有没有启用的钩子 —— guard 用它来判定「不许绕过」。

    只看有没有装，不看钩子内容：`--no-verify` 会跳过它们，装了什么都要拦。
    """
    configured = git_text(repo, "config", "--get", "core.hooksPath")
    if configured:
        path = absolute(configured, repo)
        source = f"core.hooksPath = {configured}"
    else:
        path = os.path.join(git_dir(repo), "hooks")
        source = "默认 .git/hooks"
    enabled = [name for name in list_dir(path)
               if not name.endswith(".sample") and is_executable(os.path.join(path, name))]
    return {"source": source, "path": path, "enabled": enabled}


def snapshot(start: str) -> dict:
    """整个快照。键名稳定 —— 上层脚本与用例都按这些键取值。"""
    root = repo_root(start)
    if not root:
        return {"is_repo": False, "start": start}

    entries = dirty_entries(root)
    parts = buckets(entries)
    branch = branch_state(root)
    # 被 .gitignore 挡住的文件只数个数是不够的：`clean -x` 会把它们一起删，
    # 而 `.env` 这类**本地才有**的凭据通常正是在 .gitignore 里 —— 它们不在版本库里，
    # 所以删掉就是真的没了。这里把「像凭据的那些」单独拎出来。
    ignored_entries = buckets(dirty_entries(root, ignored=True))["ignored"]
    return {
        "is_repo": True,
        "root": root,
        "branch": branch,
        "upstream": upstream_state(root),
        "unpushed": unpushed(root),
        "mid_operation": mid_operation(root),
        "dirty": {
            "total": len(entries),
            "counts": {name: len(items) for name, items in parts.items()},
            "by_kind": by_kind(entries),
            "protected": protected_paths(entries),
            "files": entries,
        },
        "ignored_count": len(ignored_entries),
        "ignored_protected": protected_paths(ignored_entries),
        "branches": local_branches(root, branch["baseline"]),
        "worktrees": worktree_state(root, {root: {
            "dirty": len(entries), "unpushed": unpushed(root)["count"]}}),
        "stash": stash_state(root),
        "submodules": submodule_state(root),
        "hooks": hooks_state(root),
    }


# ── 人类可读输出 ──────────────────────────────────────────────────────────
def render(state: dict) -> str:
    if not state.get("is_repo"):
        return f"不是一个 git 仓库：{state['start']}"

    branch = state["branch"]
    lines = [f"仓库     {state['root']}"]
    lines.append("分支     " + (branch["branch"] or f"detached HEAD @ {branch['head']}")
                 + (f"（基线 {branch['baseline']}）" if branch["baseline"] else "")
                 + ("  [在 worktree 里]" if branch["in_worktree"] else ""))

    if state["mid_operation"]:
        lines.append(f"⚠ 中间态  正在 {' / '.join(state['mid_operation'])} —— 别乱动写操作")

    up = state["upstream"]
    if up["upstream"]:
        lines.append(f"上游     {up['upstream']}  领先 {up['ahead']} / 落后 {up['behind']}")
    else:
        lines.append("上游     没有（领先/落后无从谈起）")

    push = state["unpushed"]
    lines.append(f"未推送   {push['count']} 条"
                 + (f"（{push['note']}）" if push["note"] else ""))

    dirty = state["dirty"]
    lines.append(f"未提交   {dirty['total']} 项"
                 f"  已暂存 {dirty['counts']['staged']}"
                 f" / 未暂存 {dirty['counts']['unstaged']}"
                 f" / 未跟踪 {dirty['counts']['untracked']}"
                 f" / 冲突 {dirty['counts']['conflicted']}")
    kinds = "  ".join(f"{k} {v}" for k, v in sorted(dirty["by_kind"].items()))
    if kinds:
        lines.append(f"         分类（按文件名猜的）：{kinds}")
    if state["ignored_count"]:
        lines.append(f"         被 .gitignore 挡住：{state['ignored_count']} 项"
                     "（`clean -x` 会连它们一起删）")
    for entry in state.get("ignored_protected", [])[:5]:
        lines.append(f"         ⚠ 被挡住的文件里疑似凭据：{entry['path']}")
        lines.append("           它不在版本库里 —— 删了就真的没了")
    for entry in dirty["protected"][:10]:
        lines.append(f"         ⚠ 疑似凭据：{entry['path']}")
    if len(dirty["protected"]) > 10:
        lines.append(f"         ⚠ 疑似凭据还有 {len(dirty['protected']) - 10} 个（见 --json）")

    if state["worktrees"]:
        lines.append("worktree")
        for item in state["worktrees"]:
            flags = []
            if not item["exists"]:
                flags.append("目录已不存在")
            if item["prunable"]:
                flags.append("prunable")
            if item["dirty"]:
                flags.append(f"未提交 {item['dirty']}")
            if item["unpushed"]:
                flags.append(f"未推送 {item['unpushed']}")
            name = item["branch"] or "(detached)"
            lines.append(f"         {name:<28} {item['path']}"
                         + (f"   [{', '.join(flags)}]" if flags else ""))

    if state["stash"]:
        lines.append(f"stash    {len(state['stash'])} 条")
        for item in state["stash"][:5]:
            lines.append(f"         {item['ref']}  {item['subject'][:60]}")

    subs = state["submodules"]
    if subs["present"]:
        modified = [i for i in subs["items"] if i["modified"]]
        lines.append(f"子模块   {len(subs['items'])} 个"
                     + (f"，其中 {len(modified)} 个与父仓库记录不一致"
                        if modified else "，全部一致"))
        for item in modified[:5]:
            lines.append(f"         {item['path']}  {item['state']}  {item['sha']}")

    hooks = state["hooks"]
    lines.append(f"钩子     {hooks['source']}"
                 + (f"  已启用：{' '.join(hooks['enabled'])}" if hooks["enabled"]
                    else "  没有启用的钩子"))

    stale = [b for b in state["branches"] if not b["current"] and b["merged"]]
    if stale:
        lines.append(f"可回收   已并入基线且非当前的本地分支 {len(stale)} 个："
                     + " ".join(b["name"] for b in stale[:6]))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="git 只读状态快照")
    parser.add_argument("--repo", default=".", help="仓库路径（默认当前目录）")
    parser.add_argument("--json", action="store_true", help="输出 JSON（给 agent 读）")
    args = parser.parse_args(argv)

    state = snapshot(args.repo)
    if not state.get("is_repo"):
        print(f"不是一个 git 仓库：{os.path.abspath(args.repo)}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(state, ensure_ascii=False, indent=2))
    else:
        print(render(state))
    return 2 if state["mid_operation"] else 0


if __name__ == "__main__":
    sys.exit(main())
