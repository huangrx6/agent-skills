#!/usr/bin/env python3
"""管理 SessionStart 提醒钩子，写入 <项目>/.claude/settings.local.json（不入库，只对本机生效）。

  hook.py install --root DIR   添加或更新提醒；会替换旧的 repo-baseline 条目，不动其他钩子
  hook.py remove  --root DIR   删除 repo-baseline 的条目
  hook.py status  --root DIR   查看是否已安装

安全约定：settings.local.json 解析失败时直接停止，不覆盖用户文件。
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from pathlib import Path

MARK = "repo-baseline"
DETECT = Path(__file__).resolve().parent / "detect.py"


def command() -> str:
    # 用 CLAUDE_PROJECT_DIR 定位项目；检测失败也不能阻断会话，所以 || true
    return (f'python3 {shlex.quote(str(DETECT))} --root "${{CLAUDE_PROJECT_DIR:-.}}" --quick '
            f"|| true  # {MARK}")


def settings_path(root: Path) -> Path:
    return root / ".claude" / "settings.local.json"


def load(path: Path) -> dict:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    data = json.loads(text)  # 解析失败会抛错，外层捕获后停止，不覆盖
    if not isinstance(data, dict):
        raise ValueError("settings.local.json 顶层不是 JSON 对象，已停止，未修改")
    return data


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / (path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def strip(groups: list) -> list:
    """去掉 repo-baseline 的条目，保留其他钩子。"""
    kept = []
    for g in groups:
        hs = g.get("hooks", []) if isinstance(g, dict) else []
        rest = [h for h in hs if MARK not in str(h.get("command", ""))]
        if len(rest) == len(hs):
            kept.append(g)
        elif rest:
            kept.append({**g, "hooks": rest})
    return kept


def cmd_install(root: Path) -> dict:
    path = settings_path(root)
    data = load(path)
    hooks = data.setdefault("hooks", {})
    groups = strip(hooks.get("SessionStart", []))
    groups.append({"hooks": [{"type": "command", "command": command()}]})
    hooks["SessionStart"] = groups
    save(path, data)
    return {"status": "installed", "path": str(path), "script": str(DETECT)}


def cmd_remove(root: Path) -> dict:
    path = settings_path(root)
    if not path.exists():
        return {"status": "absent"}
    data = load(path)
    hooks = data.get("hooks", {})
    if "SessionStart" in hooks:
        hooks["SessionStart"] = strip(hooks["SessionStart"])
        if not hooks["SessionStart"]:
            del hooks["SessionStart"]
    if not hooks:
        data.pop("hooks", None)
    save(path, data)
    return {"status": "removed", "path": str(path)}


def cmd_status(root: Path) -> dict:
    path = settings_path(root)
    installed = path.exists() and MARK in path.read_text(encoding="utf-8", errors="replace")
    return {"status": "installed" if installed else "absent", "path": str(path)}


def main() -> int:
    ap = argparse.ArgumentParser(description="管理 repo-baseline 的 SessionStart 提醒")
    ap.add_argument("action", choices=["install", "remove", "status"])
    ap.add_argument("--root", default=".")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    if not root.is_dir():
        print(json.dumps({"error": f"目录不存在：{root}"}, ensure_ascii=False))
        return 2
    try:
        result = {"install": cmd_install, "remove": cmd_remove, "status": cmd_status}[args.action](root)
    except (ValueError, json.JSONDecodeError) as e:
        print(json.dumps({"error": str(e), "path": str(settings_path(root))}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
