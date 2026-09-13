#!/usr/bin/env python3
"""触发日志：**哪个 skill 真的在被用** —— 从会话记录里读出来，不靠印象。

为什么需要它
------------
`ROADMAP.md` 里「该不该建下一个 skill」的四个候选，判据全都指向同一件事：真实触发频率。
而在这之前，没有任何数据 —— 只能靠"感觉经常"。本仓库立身之本是「不做 11 个 skill 只用 2 个」，
那就必须知道**现在到底在用哪几个**。

它为什么不需要新埋点
--------------------
pi 的会话记录里已经写了两类信号（`~/.pi/agent/sessions/**/*.jsonl`）：

| customType | 含义 | 字段 |
| --- | --- | --- |
| `inline-skill` | pi 按 description **自动内联**了 SKILL.md（真·自动触发） | `content` 里有 `<skill name location>` |
| `loaded-skill` | 通过工具**显式加载**（`$name` 那种） | `data.name`、`data.source` |

所以历史数据**直接能算**，装个 hook 反而多一处会坏的零件。

口径（都写在输出里，别当成"全部历史"）
--------------------------------------
- 只统计 **pi** 的会话（这台机器上没装 Claude Code / Codex）。
- 排除 `forks/`（父会话的副本，会把同一个触发重复计数）与 `subagent-artifacts/`（子代理产物，不是触发）。
- 统计的是**磁盘上还留着的**会话，不是全部历史。
- 同一会话里同一 skill 被自动触发多次会分别计数 —— 这正是"用得多不多"的信号。

用法
----
    python3 tools/skill_trigger_log.py
    python3 tools/skill_trigger_log.py --json
    python3 tools/skill_trigger_log.py --sessions-dir <目录>   # 测试 / 别的机器
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.dirname(HERE)
DEFAULT_SESSIONS = os.path.expanduser("~/.pi/agent/sessions")

INLINE = "inline-skill"
LOADED = "loaded-skill"
SKILL_TAG = re.compile(r'<skill name="([^"]+)"(?: location="([^"]*)")?')

# 这两类目录要排除，理由见文件头的「口径」。
# **按目录名剪枝，不能靠子串匹配**：".../forks/" 这种写法匹配不到 ".../--proj--/forks"
# 本身（结尾没斜杠），于是 forks 下的文件会被照收进去 —— 测试拓到过这个坑。
SKIP_DIR_NAMES = {"__pycache__", "node_modules", ".git", "forks", "subagent-artifacts"}


def listdir(path: str) -> list[str]:
    try:
        return os.listdir(path)
    except OSError:
        return []


def read_lines(path: str):
    """逐行读；读不到就当成空文件（统计不该因为一个坏文件整体失败）。"""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                yield line
    except OSError:
        return


def session_files(root: str) -> list[str]:
    """会话 jsonl 列表（排除 fork 副本与子代理产物）。

    剪枝发生在**下降之前**（`dirnames[:] = ...`），所以根本不会进那两个目录。
    """
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES]
        for name in filenames:
            if name.endswith(".jsonl"):
                found.append(os.path.join(dirpath, name))
    return sorted(found)


def skill_of_record(record: dict[str, Any]) -> str:
    """从一条记录里取出 skill 名。

    优先用 `<skill location=...>` 的**父目录名** —— 比 name 稳（skill 改过名时 location
    指向的是当前名字），拿不到再退回 name。
    """
    content = str(record.get("content") or "")
    match = SKILL_TAG.search(content)
    if match:
        location = match.group(2) or ""
        if location:
            parent = os.path.basename(os.path.dirname(location))
            if parent:
                return parent
        return match.group(1)
    data = record.get("data")
    if isinstance(data, dict):
        name = str(data.get("name") or "")
        if name:
            return name
    return ""


def parse_session(path: str) -> list[dict[str, str]]:
    """一条会话里的全部触发记录。只对含标记的行做 json 解析（jsonl 可能很大）。"""
    out: list[dict[str, str]] = []
    for line in read_lines(path):
        inline = INLINE in line
        loaded = LOADED in line
        if not (inline or loaded):
            continue
        try:
            record = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        custom = str(record.get("customType") or "")
        if custom == INLINE:
            signal = "自动触发"
        elif custom == LOADED:
            signal = "显式加载"
        else:
            continue
        skill = skill_of_record(record)
        if not skill:
            continue
        out.append({"skill": skill, "signal": signal,
                    "timestamp": str(record.get("timestamp") or "")})
    return out


def repo_skills(root: str) -> list[str]:
    skills_dir = os.path.join(root, "skills")
    return sorted(n for n in listdir(skills_dir)
                  if os.path.isdir(os.path.join(skills_dir, n)) and not n.startswith("."))


def collect(sessions_root: str) -> dict[str, Any]:
    files = session_files(sessions_root)
    per_skill: dict[str, dict[str, Any]] = {}
    for path in files:
        project = os.path.basename(os.path.dirname(path))
        for entry in parse_session(path):
            bucket = per_skill.setdefault(entry["skill"], {
                "自动触发": 0, "显式加载": 0, "sessions": 0, "projects": set(),
                "first": "", "last": "", "_seen_sessions": set(),
            })
            bucket[entry["signal"]] += 1
            bucket["projects"].add(project)
            bucket["_seen_sessions"].add(path)
            stamp = entry["timestamp"][:10]
            if stamp:
                bucket["first"] = min(bucket["first"] or stamp, stamp)
                bucket["last"] = max(bucket["last"] or stamp, stamp)
    for bucket in per_skill.values():
        bucket["sessions"] = len(bucket.pop("_seen_sessions"))
        bucket["projects"] = sorted(bucket["projects"])
        bucket["total"] = bucket["自动触发"] + bucket["显式加载"]
    return {"sessions_scanned": len(files), "skills": per_skill}


def summarize(data: dict[str, Any], root: str) -> dict[str, Any]:
    known = set(repo_skills(root))
    seen = set(data["skills"])
    windows = sorted(t for b in data["skills"].values() for t in (b["first"], b["last"]) if t)
    return {
        "从未触发的 skill": sorted(known - seen),
        "已不在仓库里的 skill": sorted(seen - known),
        "窗口": (windows[0], windows[-1]) if windows else ("", ""),
    }


def _sorted_rows(data: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return sorted(data["skills"].items(), key=lambda kv: (-kv[1]["total"], kv[0]))


def render(data: dict[str, Any], root: str) -> str:
    groups = summarize(data, root)
    lines = ["skill 触发日志（来源：pi 会话记录）", ""]
    head = "%-34s %8s %8s %6s %7s %10s" % ("skill", "自动触发", "显式加载", "合计", "会话数", "最近")
    lines += [head, "-" * len(head)]
    rows = _sorted_rows(data)
    if not rows:
        lines.append("（一个触发记录都没有）")
    for name, bucket in rows:
        lines.append("%-34s %8d %8d %6d %7d %10s" % (
            name, bucket["自动触发"], bucket["显式加载"], bucket["total"],
            bucket["sessions"], bucket["last"] or "-"))
    lines.append("")
    if groups["从未触发的 skill"]:
        lines.append("仓库里有、但窗口内一次都没触发过：")
        for name in groups["从未触发的 skill"]:
            lines.append(f"  · {name}")
    else:
        lines.append("仓库里的每个 skill 都在窗口内被触发过。")
    if groups["已不在仓库里的 skill"]:
        lines.append("")
        lines.append("触发了、但不属于本仓库（改过名 / 已删 / 或来自别的项目，这里没法区分）：")
        for name in groups["已不在仓库里的 skill"]:
            lines.append(f"  · {name}")
    first, last = groups["窗口"]
    lines += [
        "",
        f"口径：扫了 {data['sessions_scanned']} 个 pi 会话文件"
        + (f"，记录时间 {first} → {last}" if first else ""),
        "  · 只统计 pi 的会话（这台机器上没装 Claude Code / Codex）",
        "  · 已排除 forks/（父会话副本，会重复计数）与 subagent-artifacts/（子代理产物）",
        "  · 统计的是磁盘上还留着的会话，不是全部历史",
        "  · 「从未触发」不等于「没用」：可能只是这个窗口里没用到，也可能它该退休",
    ]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="从 pi 会话记录统计 skill 的真实触发频率")
    parser.add_argument("--sessions-dir", default=DEFAULT_SESSIONS, help="会话目录")
    parser.add_argument("--root", default=DEFAULT_ROOT, help="仓库根目录（用来对照有哪些 skill）")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)

    sessions_root = os.path.abspath(os.path.expanduser(args.sessions_dir))
    if not os.path.isdir(sessions_root):
        print(f"找不到会话目录：{sessions_root}", file=sys.stderr)
        print("（指定别的目录：--sessions-dir <路径>）", file=sys.stderr)
        return 0

    data = collect(sessions_root)
    if args.json:
        payload = {"sessions_scanned": data["sessions_scanned"],
                   "skills": data["skills"],
                   "summary": summarize(data, os.path.abspath(args.root))}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    print(render(data, os.path.abspath(args.root)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
