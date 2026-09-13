#!/usr/bin/env python3
"""仓库体检：一条命令算出本仓库 skill 的真实状况。

为什么要有这个
--------------
ROADMAP 里如果手抄一份「正文 147 行 / 缺 2 个 evals / 5 个 skill 没 README」的表，
它**必然过期** —— 而本仓库的规矩是「能机械校验的东西只有一处定义」。所以 ROADMAP
只写方向，数字用这条命令现算。

它**不复刻**结构校验：正文行数与上限直接读 `skills/skill-builder/scripts/validate_skill.py`
的常量与解析（那里是唯一一处定义）。这里只补 validate_skill.py 不看的几项：

  · 有没有 `README.md`（维护约定要求每个 skill 都有）
  · 有没有 `evals/`（仓库的停止判据写着「核心行为必须有 eval 覆盖」）
  · `assets/` 下有没有**没人引用的死文件**（去掉 assets 约定之后留下的）
  · 每个 skill 的脚本 / 测试规模

只报告，不判失败（退出码始终 0）。要看结构硬错误请跑 `validate_skill.py`。

用法：
    python3 tools/skill_health.py
    python3 tools/skill_health.py --json
    python3 tools/skill_health.py --root /别的/仓库
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.dirname(HERE)
VALIDATOR = os.path.join("skills", "skill-builder", "scripts", "validate_skill.py")

# 扫「谁引用了这个文件」时看这些后缀（都是文本，能直接读）。
SCAN_SUFFIXES = (".md", ".json", ".py", ".js", ".sh", ".yml", ".yaml", ".toml")
SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules", ".idea", ".pytest_cache"}
MAX_SCAN_BYTES = 2 * 1024 * 1024

# README 里的「## 目录结构」 → 第一个 ```text 块
TREE_BLOCK_RE = re.compile(r"^## 目录结构\n.*?```text\n(.*?)```", re.DOTALL | re.MULTILINE)
# 「没有 `scripts/` 与 `tests/`」这类否定句 —— 它比遗漏更糟：是句错话
NEGATION_SENTENCE_RE = re.compile(r"[^。\n]*没有[^。\n]*")
TURN_RE = re.compile(r"但|不过|然而|而是")
DIR_TOKEN_RE = re.compile(r"`?([A-Za-z0-9_\-]+)/`?")


def _load_validator(root: str):
    """加载仓库自己的结构校验器，复用它关于「正文多少行」的定义。"""
    path = os.path.join(root, VALIDATOR)
    spec = importlib.util.spec_from_file_location("_skill_health_validator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了校验器：{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read_text(path: str) -> str:
    """读文本；读不到就当空串（体检不该因为一个坏文件整体失败）。"""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read(MAX_SCAN_BYTES)
    except OSError:
        return ""


def count_lines(path: str) -> int:
    text = read_text(path)
    return text.count("\n") if text else 0


def listdir(path: str) -> list[str]:
    """列目录；读不到就当空目录（体检不该因为一个目录没权限就整体失败）。"""
    try:
        return os.listdir(path)
    except OSError:
        return []


def walk_files(base: str) -> list[str]:
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            out.append(os.path.join(dirpath, name))
    return out


def collect_repo_text(root: str, exclude_prefixes: tuple[str, ...]) -> str:
    """把仓库里所有文本拼起来（用于判断某个素材文件有没有被引用）。

    排除掉被检查的那些素材目录本身 —— 否则文件会「引用自己」而永远不算死文件。
    """
    chunks: list[str] = []
    for path in walk_files(root):
        if any(path.startswith(prefix) for prefix in exclude_prefixes):
            continue
        if not path.endswith(SCAN_SUFFIXES):
            continue
        chunks.append(read_text(path))
    return "\n".join(chunks)


def asset_report(root: str, skills_dir: str) -> dict[str, Any]:
    """assets/ 下的文件有没有被引用。返回 {相对路径: 是否被引用}。"""
    assets_roots = [os.path.join(root, "assets")]
    for name in sorted(listdir(skills_dir)):
        candidate = os.path.join(skills_dir, name, "assets")
        if os.path.isdir(candidate):
            assets_roots.append(candidate)

    corpus = collect_repo_text(root, tuple(assets_roots))
    files: dict[str, bool] = {}
    for base in assets_roots:
        if not os.path.isdir(base):
            continue
        for path in walk_files(base):
            rel = os.path.relpath(path, root)
            filename = os.path.basename(path)
            used = rel in corpus or filename in corpus or f"./{rel}" in corpus
            files[rel] = used
    return files


def contradicted_dirs(block: str, skill_dir: str) -> list[str]:
    """否定句里点名、但其实存在的目录。

    按**句**提取而不是只取「没有」紧后面那个 —— 实测：写成「没有 `scripts/` 与 `tests/`」时
    只认得到第一个。句内先砍掉转折词后面的部分（「没有 scripts/，但 tests/ 里有」
    不该把 tests 算进来）。
    """
    out: list[str] = []
    for sentence in NEGATION_SENTENCE_RE.findall(block):
        turn = TURN_RE.search(sentence)
        head = sentence[:turn.start()] if turn else sentence
        for name in DIR_TOKEN_RE.findall(head):
            if name not in out and os.path.isdir(os.path.join(skill_dir, name)):
                out.append(name)
    return out


def readme_tree_issues(skill_dir: str) -> list[str]:
    """README 的「目录结构」树与真实目录是否一致。

    这一类已经咬过两次，其中一次是**假陈述**：WLRR 的 README 写着
    「没有 `scripts/` 与 `tests/` —— 这是刻意的」，而它两个都有了。
    所以同时查两件事：
      1. 真实存在的顶层条目有没有出现在树里
      2. 有没有「没有 X」这种否定句与事实矛盾（比遗漏更糟——那是句错话）

    没有「## 目录结构」段的 README 直接放过（不是强制格式）。
    """
    text = read_text(os.path.join(skill_dir, "README.md"))
    if not text:
        return []
    match = TREE_BLOCK_RE.search(text)
    if not match:
        return []
    block = match.group(1)
    issues: list[str] = []
    for entry in sorted(listdir(skill_dir)):
        if entry in ("README.md", "SKILL.md") or entry.startswith("."):
            continue
        if entry not in block:
            issues.append(f"{entry} 存在，但树里没提")
    for name in contradicted_dirs(block, skill_dir):
        issues.append(f"树里写着「没有 {name}/」，但它确实存在")
    return issues


def scan_skill(root: str, name: str, validator) -> dict[str, Any]:
    skill_dir = os.path.join(root, "skills", name)
    skill_md = os.path.join(skill_dir, "SKILL.md")
    content = read_text(skill_md)
    body_lines = 0
    desc_len = 0
    match = validator.FM_RE.match(content)
    if match:
        data, _err = validator.load_yaml(match.group(1))
        desc_len = len(str((data or {}).get("description") or ""))
        body_lines = content[match.end():].count("\n")
    refs_dir = os.path.join(skill_dir, "references")
    return {
        "name": name,
        "body_lines": body_lines,
        "headroom": validator.MAX_BODY_LINES - body_lines,
        "desc_len": desc_len,
        "has_readme": os.path.isfile(os.path.join(skill_dir, "README.md")),
        "has_evals": os.path.isfile(os.path.join(skill_dir, "evals", "evals.json")),
        "has_skill_md": os.path.isfile(skill_md),
        "references": len(listdir(refs_dir)) if os.path.isdir(refs_dir) else 0,
        "script_lines": sum(count_lines(p) for p in walk_files(os.path.join(skill_dir, "scripts"))),
        "test_files": len([f for f in walk_files(os.path.join(skill_dir, "tests"))
                           if f.endswith(".py")]),
        "tree_issues": readme_tree_issues(skill_dir),
    }


def scan_repo(root: str) -> dict[str, Any]:
    validator = _load_validator(root)
    skills_dir = os.path.join(root, "skills")
    names: list[str] = []
    if os.path.isdir(skills_dir):
        names = sorted(n for n in listdir(skills_dir)
                       if os.path.isdir(os.path.join(skills_dir, n)) and not n.startswith("."))
    skills = [scan_skill(root, name, validator) for name in names]
    assets = asset_report(root, skills_dir)
    return {
        "root": root,
        "limits": {"max_body_lines": validator.MAX_BODY_LINES,
                   "headroom_min": validator.HEADROOM_MIN},
        "skills": skills,
        "assets": assets,
    }


def summarize(report: dict[str, Any]) -> dict[str, list[str]]:
    """把值得看的事归成几类 —— 只说事实，不替人决定要不要改。"""
    floor = report["limits"]["headroom_min"]
    skills = report["skills"]
    dead = [path for path, used in report["assets"].items() if not used]
    return {
        "正文余量偏紧": [s["name"] for s in skills if 0 <= s["headroom"] < floor],
        "正文超限": [s["name"] for s in skills if s["headroom"] < 0],
        "缺 README.md": [s["name"] for s in skills if not s["has_readme"]],
        "缺 evals": [s["name"] for s in skills if not s["has_evals"]],
        "缺 SKILL.md": [s["name"] for s in skills if not s["has_skill_md"]],
        "README 目录树过期": [f"{s['name']}（{'；'.join(s['tree_issues'])}）"
                              for s in skills if s["tree_issues"]],
        "死文件": dead,
    }


def render(report: dict[str, Any]) -> str:
    skills = report["skills"]
    groups = summarize(report)
    head = ("%-36s %5s %5s %6s %6s %7s %6s" %
            ("skill", "正文", "余量", "README", "evals", "脚本行", "测试"))
    lines = [f"仓库体检  {report['root']}", "", head, "-" * len(head)]
    for s in skills:
        lines.append("%-36s %5d %5d %6s %6s %7d %6d" % (
            s["name"], s["body_lines"], s["headroom"],
            "✓" if s["has_readme"] else "✗", "✓" if s["has_evals"] else "✗",
            s["script_lines"], s["test_files"]))
    total_assets = len(report["assets"])
    lines.append("")
    lines.append("合计 %d 个 skill、%d 个 assets 文件；上限 %d 行、余量提示线 %d 行" % (
        len(skills), total_assets, report["limits"]["max_body_lines"],
        report["limits"]["headroom_min"]))
    lines.append("")
    lines.append("值得看的（只报告，不判失败）：")
    for label, items in groups.items():
        if not items:
            continue
        shown = "、".join(items[:8]) + ("…" if len(items) > 8 else "")
        lines.append(f"  · {label}（{len(items)}）：{shown}")
    if not any(groups.values()):
        lines.append("  · 没有")
    lines.append("")
    lines.append("结构硬错误请跑：python3 skills/skill-builder/scripts/validate_skill.py")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="仓库体检（只报告，不判失败）")
    parser.add_argument("--root", default=DEFAULT_ROOT, help="仓库根目录")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)

    root = os.path.abspath(args.root)
    if not os.path.isdir(os.path.join(root, "skills")):
        print(f"这不是本仓库的根目录（没有 skills/）：{root}", file=sys.stderr)
        return 0
    try:
        report = scan_repo(root)
    except (OSError, RuntimeError) as exc:
        print(f"体检跑不下去：{exc}", file=sys.stderr)
        return 0

    if args.json:
        payload = dict(report)
        payload["summary"] = summarize(report)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    print(render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
