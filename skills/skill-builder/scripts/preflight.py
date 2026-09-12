#!/usr/bin/env python3
"""报告前的强制一步：跑全部检查 + 打印所有可核对的事实。

## 为什么有这个脚本

2026-09-12 两处报告错误，共同点是**数字与存在性来自记忆，而不是测量**：

1. 报告里写"已加入 skill-builder 的检查表（check_leakage）" —— **文件其实没变**。
   编辑工具回了"成功替换 1 块"，我没验证就写进了报告。
   事后核查：`git log -S"check_leakage.py" -- skills/skill-builder/SKILL.md` 无输出。

2. 报告里写"SKILL.md（142 行）" —— 实际 74 行。那个数是凭印象写的。

"下次记得验证"解决不了这件事 —— "记得"正是本仓库反复证明不可靠的东西。
所以把它变成一条**可执行的前置步骤**：

    写任何声称"完成了 X"的报告之前，先跑这个脚本。
    报告里的每个数字、每个存在性声明，都从它的输出里抄。

它做三件事：
  1. 跑全部检查（结构 / 泄露 / 指针目标）
  2. 打印可核对的事实快照（行数、余量、文件数、hook 步骤、测试数）
  3. 额外查一类错：**孤儿脚本** —— `scripts/` 里有文件，但本 skill 的任何文档都没提到它。
     这正是错误 1 的形态：脚本存在、检查在跑，但从 skill-builder 的 checklist 里找不到它。

用法：
    python3 preflight.py            # 检查 + 快照
    python3 preflight.py --json
    python3 preflight.py --snapshot-only

退出码：0 = 全部检查通过且无孤儿脚本，1 = 有失败，2 = 找不到仓库根。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

FM_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
RAN_RE = re.compile(r"Ran (\d+) test")
MAX_BODY_LINES = 150


def _load_sibling(name: str):
    """动态加载同目录脚本。先注册进 sys.modules 再 exec（否则 @dataclass 会炸）。"""
    import importlib.util

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"_sb_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了同目录模块：{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_vs = _load_sibling("validate_skill")


def _safe_listdir(path: str) -> list[str]:
    """列目录。不存在、没权限、路径其实是文件 —— 一律返回空列表。"""
    try:
        return sorted(os.listdir(path))
    except OSError:
        return []


def _safe_read(path: str) -> str:
    """读文本文件。读不到返回空串。"""
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def find_root(start: str) -> str | None:
    """从 start 往上找含 skills/ 的仓库根。"""
    cur = os.path.abspath(start)
    while True:
        if os.path.isdir(os.path.join(cur, "skills")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def _run(cmd: list[str], cwd: str) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
        return proc.returncode, (proc.stdout + proc.stderr).strip()
    except OSError as exc:
        return 2, str(exc)


def _skill_doc_text(path: str) -> str:
    """把 skill 下所有 .md 的内容拼起来，用来判断脚本有没有被文档提到。"""
    chunks: list[str] = []
    for dirpath, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in {"__pycache__", "tests"} and not d.startswith(".")]
        for name in files:
            if name.endswith(".md"):
                chunks.append(_safe_read(os.path.join(dirpath, name)))
    return "\n".join(chunks)


def _count_tests(skill_path: str, root: str) -> int:
    """跑一个 skill 的测试目录，取用例数。跑不动就算 0。"""
    tests_dir = os.path.join(skill_path, "tests")
    if not os.path.isdir(tests_dir):
        return 0
    code, out = _run([sys.executable, "-m", "unittest", "discover", "-s", tests_dir], root)
    m = RAN_RE.search(out)
    if not m:
        return 0
    try:
        return int(m.group(1))
    except ValueError:
        return 0


def skill_facts(root: str) -> list[dict]:
    base = os.path.join(root, "skills")
    facts: list[dict] = []
    for name in _safe_listdir(base):
        path = os.path.join(base, name)
        skill_md = os.path.join(path, "SKILL.md")
        if not os.path.isfile(skill_md):
            continue

        raw = _safe_read(skill_md)
        fm = FM_RE.match(raw)
        body = raw[fm.end():] if fm else raw
        # description 用 validate_skill.py 的解析器 —— 它是折叠标量（`>-`）感知的。
        # 本文件最初用单行正则，结果把 `>-` 后面的折叠正文全漏掉，报出“2 字符”
        # 而真值是 754/636。一个“数字要准”的工具，自己的数字不准，所以改成复用。
        data, _err = _vs.load_yaml(fm.group(1)) if fm else (None, None)
        desc_val = (data or {}).get("description") or ""
        doc_text = _skill_doc_text(path)

        def count_sub(sub: str) -> int:
            return len([f for f in _safe_listdir(os.path.join(path, sub))
                        if not f.startswith(".") and f != "__pycache__"])

        scripts = [f for f in _safe_listdir(os.path.join(path, "scripts")) if f.endswith(".py")]
        # 孤儿脚本：scripts/ 里有，但本 skill 的任何 .md 都没提到文件名
        orphans = [s for s in scripts if s not in doc_text]

        lines = body.count("\n")
        facts.append({
            "skill": name,
            "body_lines": lines,
            "headroom": MAX_BODY_LINES - lines,
            "over_limit": lines > MAX_BODY_LINES,
            "description_chars": len(desc_val),
            "references": count_sub("references"),
            "scripts": scripts,
            "orphan_scripts": orphans,
            "tests": _count_tests(path, root),
        })
    return facts


def hook_steps(root: str) -> list[str]:
    text = _safe_read(os.path.join(root, ".githooks", "pre-commit"))
    return re.findall(r"^# ── (\d+\.\s+.+?) ──", text, re.M)


def checks(root: str) -> list[dict]:
    sb = os.path.join(root, "skills", "skill-builder", "scripts")
    return [
        {"name": "结构校验", "cmd": [sys.executable, os.path.join(sb, "validate_skill.py")]},
        {"name": "泄露扫描", "cmd": [sys.executable, os.path.join(sb, "check_leakage.py")]},
        {"name": "指针目标", "cmd": [sys.executable, os.path.join(sb, "check_pointers.py"),
                                     "--root", root, "skills"]},
    ]


def install_drift(root: str) -> tuple[bool, str]:
    """仓库 vs pi 安装位（`~/.agents/skills`）的状态。

    为什么进 preflight：pi 加载的是**安装位**，不是仓库 —— 实测过一次「仓库改了 13 个
    文件、安装位一个都没有」，那个 skill 在下一个会话里会画出旧配色旧框线，
    而且不知道新能力存在。这类“改得再好、没装过去就等于没改”的事必须在报告里可见。

    安装器默认装**软链**（那种永不漂移，这里报的就是“软链指向本仓库”）；装成副本时
    比内容。两种都报出来，读报告的人不用猜装的是哪种。

    ⚠️ 只报告、**不算失败**：钩子是在 commit **之前**跑的，那时候副本形态的安装位
    按定义就是旧的 —— 把它算成失败，等于每次提交都挂。
    """
    code, out = _run([sys.executable, os.path.join(root, "tools", "install_skills.py"),
                      "--check"], root)
    lines = [line.strip() for line in out.split("\n") if line.strip()]
    if code == 0:
        oks = [line for line in lines if line.startswith("✓")]
        linked = sum(1 for line in oks if "软链" in line)
        if oks and linked == len(oks):
            return True, f"{linked} 个 skill 以软链指向本仓库（不可能漂移）"
        return True, f"与仓库一致（{len(oks)} 个）"
    bad = [line for line in lines if line.startswith("✗")]
    return False, "；".join(bad) or "与仓库不一致"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="报告前的强制一步：检查 + 事实快照")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--snapshot-only", action="store_true", help="只打印快照，不跑检查")
    args = ap.parse_args(argv)

    root = find_root(os.getcwd())
    if root is None:
        print("找不到含 skills/ 的仓库根", file=sys.stderr)
        return 2

    results: list[dict] = []
    if not args.snapshot_only:
        for c in checks(root):
            code, out = _run(c["cmd"], root)
            results.append({"name": c["name"], "exit": code, "output": out})

    facts = skill_facts(root)
    steps = hook_steps(root)
    total_tests = sum(f["tests"] for f in facts)
    orphans = [(f["skill"], s) for f in facts for s in f["orphan_scripts"]]
    install_ok, install_note = install_drift(root)

    if args.json:
        print(json.dumps({"root": root, "checks": results, "skills": facts,
                          "hook_steps": steps, "total_tests": total_tests,
                          "orphan_scripts": orphans,
                          "install_in_sync": install_ok, "install_note": install_note},
                         ensure_ascii=False, indent=2))
        failed = any(r["exit"] != 0 for r in results) or bool(orphans)
        return 1 if failed else 0

    if results:
        print("检查")
        for r in results:
            tail = r["output"].split("\n")[-1] if r["output"] else ""
            print(f"  {'✓' if r['exit'] == 0 else '✗'} {r['name']}  {tail}")
        print()

    print("事实快照（报告里的数字从这里抄，不要凭印象写）")
    print(f"  {'skill':<34}{'正文':>10}{'余量':>6}{'desc':>6}{'refs':>6}{'tests':>7}")
    for f in facts:
        limit = "  ← 超限!" if f["over_limit"] else ""
        print(f"  {f['skill']:<34}{f['body_lines']:>6}/150{f['headroom']:>6}"
              f"{f['description_chars']:>6}{f['references']:>6}{f['tests']:>7}{limit}")
    print(f"\n  测试合计 {total_tests}")
    if steps:
        names = " / ".join(s.split(". ", 1)[-1] for s in steps)
        print(f"  hook 步骤 {len(steps)}: {names}")
    else:
        print("  hook 步骤 0（没找到 .githooks/pre-commit）")

    if orphans:
        print("\n  ✗ 孤儿脚本（scripts/ 里有，但本 skill 的文档一个字都没提）")
        for skill, s in orphans:
            print(f"      {skill}/scripts/{s}")
        print("      这类脚本等于没接线 —— 谁都不知道该跑它。"
              "把用法写进 SKILL.md 或 references/。")
    else:
        print("\n  ✓ 无孤儿脚本")

    # ⚠️ 只报告、不算失败（原因见 install_drift 的 docstring：钩子在 commit 前跑，
    # 那时安装位按定义就是旧的）。
    if install_ok:
        print(f"  ✓ 安装位 {install_note}")
    else:
        print(f"  ⚠ 安装位落后于仓库：{install_note}")
        print("      → python3 tools/install_skills.py")

    failed = any(r["exit"] != 0 for r in results) or bool(orphans)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
