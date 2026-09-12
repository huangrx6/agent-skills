#!/usr/bin/env python3
"""扫描 skill 内容里是否出现了不该外发的真实名称。

为什么有这个脚本：
2026-09-12，给 WLRR 写 evals 时用了真实客户名、内部系统名、内网主机路径，而这个
仓库是 public。内容推送后，清除它们需要重写 35/38 个 commit 并 force push ——
代价远大于写的时候用中性占位符。事后复盘时，"写外发内容前先确认仓库可见性"
这条规则如果只写在文档里，大概率会重演；所以这里做成可执行检查。

blocklist 不放在本仓库里（放进去它自己就泄露了），按序解析：
  1. --blocklist PATH
  2. 环境变量 SKILL_NAME_BLOCKLIST
  3. ~/.config/skill-name-blocklist.txt   （一行一个词，# 开头为注释）

用法：
    python3 check_leakage.py                    # 扫 skills/ 工作区
    python3 check_leakage.py PATH...            # 扫指定路径
    python3 check_leakage.py --history          # 额外扫全部 git 历史（检出泄露源头）
    python3 check_leakage.py --show-blocklist   # 显示当前生效的 blocklist 与来源

退出码：0 = 无命中（或未配置 blocklist），1 = 命中，2 = 路径无效。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

ENV_VAR = "SKILL_NAME_BLOCKLIST"
CONFIG_PATH = os.path.expanduser("~/.config/skill-name-blocklist.txt")
DEFAULT_TARGET = "skills"

# 扫哪些文本文件
TEXT_EXT = (".md", ".json", ".py", ".yaml", ".yml", ".sh", ".txt", ".csv")
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv"}


def load_blocklist(explicit: str | None = None) -> tuple[list[str], str]:
    """返回 (词条列表, 来源说明)。未配置时返回 ([], 说明)。"""
    path, source = None, ""
    if explicit:
        path, source = explicit, "命令行参数"
    elif os.environ.get(ENV_VAR, "").strip():
        path, source = os.environ[ENV_VAR].strip(), f"环境变量 {ENV_VAR}"
    elif os.path.isfile(CONFIG_PATH):
        path, source = CONFIG_PATH, f"配置文件 {CONFIG_PATH}"

    if not path or not os.path.isfile(path):
        return [], "未配置"

    terms: list[str] = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#"):
                    terms.append(line)
    except OSError as exc:
        return [], f"读取失败：{exc}"
    return terms, source


def iter_files(targets: list[str]):
    """产出待扫的文本文件。"""
    for target in targets:
        if os.path.isfile(target):
            yield target
            continue
        for root, dirs, files in os.walk(target):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
            for name in sorted(files):
                if name.endswith(TEXT_EXT):
                    yield os.path.join(root, name)


def scan_worktree(targets: list[str], terms: list[str]) -> list[dict]:
    """扫工作区文件，返回命中列表。"""
    hits: list[dict] = []
    for path in iter_files(targets):
        try:
            with open(path, encoding="utf-8", errors="ignore") as fh:
                lines = fh.readlines()
        except OSError:
            continue
        for lineno, line in enumerate(lines, 1):
            for term in terms:
                if term in line:
                    hits.append({"where": path, "line": lineno, "term": term,
                                 "text": line.strip()[:110]})
    return hits


def scan_history(terms: list[str]) -> list[dict]:
    """扫全部 git 历史（所有 commit 的所有 blob），用于定位泄露源头。"""
    try:
        revs = subprocess.run(["git", "rev-list", "--all"], capture_output=True,
                              text=True, check=True).stdout.split()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []

    hits: list[dict] = []
    for term in terms:
        try:
            out = subprocess.run(["git", "grep", "-l", "-F", term, *revs],
                                 capture_output=True, text=True).stdout
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
        for entry in out.splitlines():
            if ":" in entry:
                sha, path = entry.split(":", 1)
                hits.append({"where": f"{sha[:8]}:{path}", "line": 0, "term": term,
                             "text": "(历史版本)"})
    return hits


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="扫描 skill 内容里的真实名称")
    ap.add_argument("targets", nargs="*", default=[DEFAULT_TARGET], help="要扫的路径")
    ap.add_argument("--blocklist", default=None, help="blocklist 文件路径")
    ap.add_argument("--history", action="store_true", help="额外扫全部 git 历史")
    ap.add_argument("--show-blocklist", action="store_true", help="显示生效的 blocklist")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    targets = args.targets or [DEFAULT_TARGET]
    terms, source = load_blocklist(args.blocklist)

    if args.show_blocklist:
        print(f"来源：{source}")
        print(f"词条：{len(terms)} 条")
        for t in terms:
            print(f"  {t}")
        return 0 if terms else 2

    if not terms:
        print("⚠ 未配置 blocklist，跳过检查。配置方式（三选一）:")
        print(f"    export {ENV_VAR}='/path/to/blocklist.txt'")
        print(f"    mkdir -p ~/.config && $EDITOR {CONFIG_PATH}")
        print("    python3 check_leakage.py --blocklist /path/to/blocklist.txt")
        print("  一行一个词，# 开头为注释。blocklist 不要放进本仓库。")
        return 0

    if not any(os.path.exists(t) for t in targets):
        print(f"路径无效：{targets}", file=sys.stderr)
        return 2

    hits = scan_worktree(targets, terms)
    hist_hits = scan_history(terms) if args.history else []

    if args.json:
        import json
        print(json.dumps({"blocklist_source": source, "terms": len(terms),
                          "worktree_hits": hits, "history_hits": hist_hits},
                         ensure_ascii=False, indent=2))
        return 1 if (hits or hist_hits) else 0

    print(f"blocklist：{len(terms)} 条（来源：{source}）")

    if not hits and not hist_hits:
        print("✓ 未发现不该外发的名称")
        return 0

    if hits:
        print(f"\n✗ 工作区命中 {len(hits)} 处：")
        for h in hits:
            print(f"    {h['where']}:{h['line']}  [{h['term']}]")
            print(f"        {h['text']}")
        print("\n  改法：换成中性占位符（客户 X / 内部系统 A / 内网主机 /srv/release …），")
        print("  不要在这里放真实客户名、内部系统名、内网主机与路径、内部接口名。")

    if hist_hits:
        print(f"\n✗ git 历史命中 {len(hist_hits)} 处（历史改写代价很高，尽早处理）：")
        for h in hist_hits[:20]:
            print(f"    {h['where']}  [{h['term']}]")
        if len(hist_hits) > 20:
            print(f"    …另有 {len(hist_hits) - 20} 处")

    return 1


if __name__ == "__main__":
    sys.exit(main())
