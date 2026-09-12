#!/usr/bin/env python3
"""校验 skill 是否符合 skill-builder 的 Minimum Viable SKILL.md Checklist。

为什么有这个脚本：checklist 原本是手工勾选项，但 2026-09-12 一次会话里就有
两次违反了"正文 ≤ 150 行"（WLRR 256 行、PKB 174 行），两次都是临时脚本抓出来
的，肉眼没有发现。手工勾选的 checklist 不可靠，这里把它变成可执行检查。

用法：
    python3 validate_skill.py                    # 扫本仓库 skills/ 下全部 skill
    python3 validate_skill.py skills/skill-builder
    python3 validate_skill.py --json

退出码：0 = 全部通过，1 = 有失败，2 = 路径无效。
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

MAX_DESC = 800
MAX_BODY_LINES = 150
FM_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
# description 里应出现的触发表达（中英皆可）
TRIGGER_HINTS = ("Use this skill", "Use when", "用于", "触发")


def _minimal_parse(text: str) -> dict:
    """只认顶层 `key: value` 的极简 frontmatter 解析器（PyYAML 不可用时的退路）。"""
    data: dict = {}
    key = None
    for line in text.split("\n"):
        if re.match(r"^\S", line) and ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            data[key] = val.strip()
        elif key and line.startswith((" ", "\t")):
            data[key] = (str(data.get(key, "")) + " " + line.strip()).strip()
    return data


def load_yaml(text: str):
    """解析 frontmatter，返回 (data, error)。优先 PyYAML，缺失时退回极简解析器。"""
    try:
        import yaml  # type: ignore
    except ImportError:
        return _minimal_parse(text), None

    try:
        return yaml.safe_load(text), None
    except Exception as exc:
        return None, str(exc)


def check_skill(path: str) -> dict:
    """校验单个 skill 目录，返回结果字典。"""
    name = os.path.basename(os.path.normpath(path))
    skill_md = os.path.join(path, "SKILL.md")
    result = {"skill": name, "path": path, "checks": [], "errors": []}

    def add(label: str, ok: bool, detail: str = "") -> None:
        result["checks"].append({"label": label, "ok": bool(ok), "detail": detail})
        if not ok:
            result["errors"].append(label)

    if not os.path.isfile(skill_md):
        add("SKILL.md 存在", False, skill_md)
        return result
    add("SKILL.md 存在", True)

    try:
        content = open(skill_md, encoding="utf-8").read()
    except OSError as exc:
        add("SKILL.md 可读", False, str(exc))
        return result
    add("SKILL.md 可读", True)

    m = FM_RE.match(content)
    if not m:
        add("frontmatter 存在", False)
        return result
    add("frontmatter 存在", True)

    data, err = load_yaml(m.group(1))
    add("YAML 可解析", err is None, err or "")
    if data is None:
        return result

    fm_name = data.get("name")
    desc = data.get("description") or ""
    body = content[m.end():]

    add("name == 目录名", fm_name == name, f"name={fm_name!r} dir={name!r}")
    add(f"description {len(desc)} 字符 < {MAX_DESC}", len(desc) < MAX_DESC)
    add("description 含触发表达", any(h in desc for h in TRIGGER_HINTS))
    add("description 含 Do NOT use 边界", bool(re.search(r"[Dd]o NOT use", desc)))
    lines = body.count("\n")
    add(f"正文 {lines} 行 ≤ {MAX_BODY_LINES}", lines <= MAX_BODY_LINES)
    add("正文含表格或清单", "|" in body or "\n- " in body)

    for sub in ("references", "evals"):
        d = os.path.join(path, sub)
        if not os.path.isdir(d):
            continue
        try:
            n = len([f for f in os.listdir(d) if not f.startswith(".")])
        except OSError:
            continue
        result.setdefault("assets", {})[sub] = n

    return result


def discover(targets: list[str]) -> list[str]:
    """把输入路径展开成 skill 目录列表。"""
    found: list[str] = []
    for t in targets:
        if os.path.isfile(os.path.join(t, "SKILL.md")):
            found.append(t)
        else:
            found.extend(
                sorted(os.path.dirname(p) for p in glob.glob(os.path.join(t, "*", "SKILL.md")))
            )
    return sorted(dict.fromkeys(found))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="校验 skill 是否符合 skill-builder 的 checklist")
    ap.add_argument("targets", nargs="*", default=["skills"], help="skill 目录或含 skills/ 的根目录")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    targets = args.targets or ["skills"]
    dirs = discover(targets)
    if not dirs:
        print(f"没找到任何 SKILL.md（输入：{', '.join(targets)}）", file=sys.stderr)
        return 2

    results = [check_skill(d) for d in dirs]
    failed = [r for r in results if r["errors"]]

    if args.json:
        print(json.dumps({"checked": len(results), "failed": len(failed), "results": results},
                         ensure_ascii=False, indent=2))
        return 1 if failed else 0

    for r in results:
        mark = "✗" if r["errors"] else "✓"
        print(f"\n  {mark} {r['skill']}")
        for c in r["checks"]:
            print(f"      {'✓' if c['ok'] else '✗'} {c['label']}")
        if r.get("assets"):
            extra = "  ".join(f"{k}:{v}" for k, v in r["assets"].items())
            print(f"      · {extra}")

    print(f"\n  检查 {len(results)} 个 skill"
          + (f"，{len(failed)} 个失败" if failed else "，全部通过"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
