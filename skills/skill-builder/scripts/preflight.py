#!/usr/bin/env python3
"""运行结构、泄露、指针检查，并报告文件快照与安装状态。

不运行回归测试；测试文件数不能代表用例数或通过数。
文档未提及的脚本与安装差异只提示，不证明无用或阻塞检查。
退出码：0 = 已执行检查通过，1 = 检查失败，2 = 找不到仓库根。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

FM_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


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
MAX_BODY_LINES = _vs.MAX_BODY_LINES


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


def _count_test_files(skill_path: str, root: str) -> int:
    """统计仓库顶层对应目录中的测试文件，不导入或执行它们。"""
    tests_dir = os.path.join(root, "tests", os.path.basename(skill_path))
    count = 0
    for _path, dirs, files in os.walk(tests_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
        count += sum(f.startswith("test") and f.endswith(".py") for f in files)
    return count


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
        # 与结构校验共用 frontmatter 解析规则。
        data, _err = _vs.load_yaml(fm.group(1)) if fm else (None, None)
        desc_val = data.get("description") if isinstance(data, dict) else ""
        if not isinstance(desc_val, str):
            desc_val = ""
        doc_text = _skill_doc_text(path)

        def count_sub(sub: str) -> int:
            return len([f for f in _safe_listdir(os.path.join(path, sub))
                        if not f.startswith(".") and f != "__pycache__"])

        scripts = [f for f in _safe_listdir(os.path.join(path, "scripts")) if f.endswith(".py")]
        # 仅供人工核对：内部模块可以有代码调用者而没有文档入口。
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
            "test_files": _count_test_files(path, root),
        })
    return facts


def hook_steps(root: str) -> list[str]:
    text = _safe_read(os.path.join(root, ".githooks", "pre-commit"))
    return re.findall(r"^# ── (\d+\.\s+.+?)\s*──", text, re.M)


def checks(root: str) -> list[dict]:
    sb = os.path.join(root, "skills", "skill-builder", "scripts")
    return [
        {"name": "结构校验", "cmd": [sys.executable, os.path.join(sb, "validate_skill.py")]},
        {"name": "泄露扫描", "cmd": [sys.executable, os.path.join(sb, "check_leakage.py")]},
        {"name": "指针目标", "cmd": [sys.executable, os.path.join(sb, "check_pointers.py"),
                                     "--root", root, "skills"]},
    ]


def install_drift(root: str) -> tuple[bool, str]:
    """报告默认安装位状态；本机安装差异不阻塞仓库校验。"""
    code, out = _run([sys.executable, os.path.join(root, "tools", "install_skills.py"),
                      "--check"], root)
    lines = [line.strip() for line in out.split("\n") if line.strip()]
    if code == 0:
        oks = [line for line in lines if line.startswith("✓")]
        linked = sum(1 for line in oks if "软链" in line)
        if oks and linked == len(oks):
            return True, f"{linked} 个 skill 以软链指向本仓库"
        return True, f"与仓库一致（{len(oks)} 个）"
    bad = [line for line in lines if line.startswith("✗")]
    return False, "；".join(bad) or out or "无法检查安装状态"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="结构、泄露、指针检查与文件快照（不运行测试）")
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
    total_test_files = sum(f["test_files"] for f in facts)
    orphans = [(f["skill"], s) for f in facts for s in f["orphan_scripts"]]
    install_ok, install_note = install_drift(root)

    if args.json:
        print(json.dumps({"root": root, "checks": results, "skills": facts,
                          "hook_steps": steps, "total_test_files": total_test_files,
                          "tests_run": False, "max_body_lines": MAX_BODY_LINES,
                          "orphan_scripts": orphans,
                          "install_in_sync": install_ok, "install_note": install_note},
                         ensure_ascii=False, indent=2))
        failed = any(r["exit"] != 0 for r in results)
        return 1 if failed else 0

    if results:
        print("检查")
        for r in results:
            tail = r["output"].split("\n")[-1] if r["output"] else ""
            print(f"  {'✓' if r['exit'] == 0 else '✗'} {r['name']}  {tail}")
        print()

    print("文件快照（未运行测试）")
    print(f"  {'skill':<34}{'正文':>10}{'余量':>6}{'desc':>6}{'refs':>6}{'测试文件':>7}")
    for f in facts:
        limit = "  ← 超限!" if f["over_limit"] else ""
        print(f"  {f['skill']:<34}{f['body_lines']:>6}/{MAX_BODY_LINES}{f['headroom']:>6}"
              f"{f['description_chars']:>6}{f['references']:>6}{f['test_files']:>7}{limit}")
    print(f"\n  测试文件合计 {total_test_files}（用例数与结果须实际运行测试取得）")
    if steps:
        names = " / ".join(s.split(". ", 1)[-1] for s in steps)
        print(f"  hook 步骤 {len(steps)}: {names}")
    else:
        print("  hook 步骤 0（没找到 .githooks/pre-commit）")

    if orphans:
        print("\n  ⚠ 文档未提及的脚本（仅提示；删除前核对代码调用与动态加载）")
        for skill, script in orphans:
            print(f"      {skill}/scripts/{script}")
    else:
        print("\n  ✓ 未发现文档未提及的脚本")

    if install_ok:
        print(f"  ✓ 安装位 {install_note}")
    else:
        print(f"  ⚠ 安装状态：{install_note}")
        print("      → python3 tools/install_skills.py")

    failed = any(r["exit"] != 0 for r in results)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
