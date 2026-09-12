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
正文余量（见 HEADROOM_MIN）只提示，不影响退出码。
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
# 余量低于此值时提示（不判失败）。
# 2026-09-12 三个 skill 同时逼近上限（146/143/147），意味着下一次“真实需要的新规则”
# 没有空间直接加进去 —— 那时会被迫先做 references 瘦身。与其等到那一刻才发现，
# 不如每次校验都把它显出来。只说事实（余量多少、该先做什么），不替人决定要不要加。
HEADROOM_MIN = 10

# 「绑定本机」声明 与 「从配置读」表述 同时出现 = 自相矛盾，直接判失败。
#
# 2026-09-12 实测（WLRR）：同一段里上面写着
#     This skill is bound to a specific machine and Obsidian vault
# 下面写着
#     vault path resolves from $OBSIDIAN_VAULT_PATH — never hardcode it
# 成因：把硬编码路径改成配置解析之后，没删掉原来的绑定声明。agent 读到会据此
# 拒绝在别的机器上工作。
#
# 为什么必须做成检查：skill-builder 里早就有一句“声明要撤”的提醒，而同一类错误
# 又发生了一次 —— 提醒别人自己记得做，就是那个偷懒路径。
#
# 只匹配**引号外**的表述：skill-builder 会合法地引用 "bound to specific machine"
# 作为“要显式声明什么”的例子，那不该被当成矛盾。
BOUND_PATTERNS = (
    r"bound to (?:a )?specific machine",
    r"machine[- ]bound",
    r"cross-machine reuse is limited",
    r"绑定(?:到)?(?:本机|特定机器)",
    r"跨机复用(?:性)?(?:低|受限)",
)
PORTABLE_PATTERNS = (
    r"never hardcod",
    r"not hardcod",
    r"从配置(?:读取|解析|取)",
    r"解析(?:顺序|自|出)(?:见|见下方|按)",
    r"resolves? from \$",
    r"reads? from",
    r"~/\\.config/",
    r"OBSIDIAN_VAULT_PATH",
)
# 引号里的内容当例子看，不参与“矛盾”判定
QUOTED_SPAN_RE = re.compile(r'''"[^"\n]*"|“[^”\n]*”|`[^`\n]*`''')
# 否定式不算声明。“不绑定本机”说的是“不绑定”，意思正好相反。
NEGATION_CHARS = "不无非未"
FM_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def find_contradiction(desc: str, body: str) -> tuple[set[int], set[int]]:
    """找出「绑定本机」与「从配置读」同时断言的行号。返回 (bound 行号, portable 行号)。

    两个约束都是为了不误报，都是实测出来的：

    1. **否定式不算**。“路径从配置解析，**不绑定本机**”里的“绑定本机”是在说
       不绑定，意思正好相反。只看匹配前两个字符里有没有否定词。
    2. **必须在不同行**。真正出问题的形态是“上面写一边、下面写另一边”
       （WLRR：上半段 bound、下半段 resolves from）。同一行里两侧同时出现的，
       几乎都是在**描述这个失败模式本身** —— skill-builder 那句就是
       “上面说绑定本机，下面说路径从配置解析”，它不是在犯这个错。

    判定规则：存在一行有 bound 但没有 portable，且全文有 portable。
    """
    bound: set[int] = set()
    portable: set[int] = set()
    for i, line in enumerate((desc + "\n" + body).split("\n")):
        clean = QUOTED_SPAN_RE.sub(" ", line)
        if any(re.search(p, clean, re.I) for p in PORTABLE_PATTERNS):
            portable.add(i)
        for pat in BOUND_PATTERNS:
            for m in re.finditer(pat, clean, re.I):
                if any(ch in NEGATION_CHARS for ch in clean[max(0, m.start() - 2):m.start()]):
                    continue
                bound.add(i)
    return bound, portable
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
    headroom = MAX_BODY_LINES - lines
    if 0 <= headroom < HEADROOM_MIN:
        result.setdefault("notes", []).append(
            f"正文余量只剩 {headroom} 行：下次要往正文加规则前，先做 references 瘦身"
        )
    add("正文含表格或清单", "|" in body or "\n- " in body)

    # 绑定声明 vs 可移植表述：引号里的当例子看，只看引号外的
    bound, portable = find_contradiction(desc, body)
    conflicting = bound - portable
    if conflicting and portable:
        add("无「绑定本机 + 从配置读」矛盾", False,
            f"第 {sorted(conflicting)} 行声明绑定本机，全文又有“从配置读”的表述；"
            f"已改成从配置读路径的话，同一次里删掉绑定声明")
    else:
        add("无「绑定本机 + 从配置读」矛盾", True)

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
        for note in r.get("notes", []):
            print(f"      ! {note}")

    print(f"\n  检查 {len(results)} 个 skill"
          + (f"，{len(failed)} 个失败" if failed else "，全部通过"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
