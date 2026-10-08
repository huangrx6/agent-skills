#!/usr/bin/env python3
"""只读检查 wikilink/嵌入的目标文件，忽略代码；不检查锚点或 Markdown 链接。

用法：check_links.py [--vault PATH] [--json | --quiet] [--ignore-template]
退出码：0 无失效目标，1 有失效目标，2 vault 不可用。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys

DEFAULT_VAULT = None  # 不再硬编码；由 vault_path.py 解析（见下方说明）

# 不参与扫描的目录（版本控制、编辑器状态、缓存、嵌套仓库、废纸篓）
SKIP_DIRS = {".git", ".obsidian", ".cache", ".theme-publish", ".trash", "node_modules"}

# 脚本也供按路径加载的测试和其他 skill 使用，避免依赖调用者的 sys.path。
def _load_sibling(name: str):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"_obsidian_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了同目录模块：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_VAULT = _load_sibling("vault_path")
VaultPathError = _VAULT.VaultPathError
resolve_vault = _VAULT.resolve

# 围栏代码块起始标记
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
# 行内代码
INLINE_CODE_RE = re.compile(r"(?<!`)(`+)(?!`)(.*?)\1(?!`)")
# wikilink：可选前置 `!` 表示嵌入
LINK_RE = re.compile(r"(!?)\[\[([^\[\]]+)\]\]")


def iter_notes(vault: str):
    """产出 vault 内所有 .md 的相对路径。"""
    for root, dirs, files in os.walk(vault):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(files):
            if name.endswith(".md"):
                yield os.path.relpath(os.path.join(root, name), vault)


def iter_all_files(vault: str):
    """产出 vault 内所有文件的相对路径（用于索引附件）。"""
    for root, dirs, files in os.walk(vault):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(files):
            yield os.path.relpath(os.path.join(root, name), vault)


def build_index(vault: str) -> tuple[set[str], set[str]]:
    """建立解析索引。

    返回 (paths, basenames)：
      paths     —— 每个文件相对 vault 的路径，Markdown 同时登记省略 .md 的形式
      basenames —— 文件名及 Markdown 短名称；附件扩展名不可混淆
    """
    paths: set[str] = set()
    basenames: set[str] = set()
    for rel in iter_all_files(vault):
        paths.add(rel)
        stem, ext = os.path.splitext(rel)
        if ext == ".md":
            paths.add(stem)
        base = os.path.basename(rel)
        basenames.add(base)
        if ext == ".md":
            basenames.add(os.path.splitext(base)[0])
    return paths, basenames


def strip_code(text: str) -> str:
    """剥掉围栏代码块与行内代码，其余原样保留（含空行，以保持行号）。"""
    out = []
    fence = None
    for line in text.split("\n"):
        m = FENCE_RE.match(line)
        if m:
            mark, tail = m.groups()
            if fence is None:
                fence = mark
            elif fence[0] == mark[0] and len(mark) >= len(fence) and not tail.strip():
                fence = None
            out.append("")
            continue
        if fence is not None:
            out.append("")
            continue
        out.append(INLINE_CODE_RE.sub("", line))
    return "\n".join(out)


def normalize(target: str) -> str:
    """去掉别名、锚点与表格转义反斜杠。"""
    t = target.split("|")[0]
    t = t.split("#")[0]
    return t.strip().rstrip("\\").strip()


def resolve(target: str, note_rel: str, paths: set[str], basenames: set[str]) -> bool:
    """判断一个链接目标能否解析。

    覆盖 Obsidian 的主要解析方式：
      - 相对 vault 的路径（可带/不带扩展名）
      - 相对当前笔记的路径（../ 开头）
      - 短链接（按 basename）
    """
    t = normalize(target)
    if not t:
        return True  # 纯锚点如 [[#标题]]

    if t.startswith(("./", "../")):
        return os.path.normpath(os.path.join(os.path.dirname(note_rel), t)) in paths
    if t in paths:
        return True
    if "/" in t:
        joined = os.path.normpath(os.path.join(os.path.dirname(note_rel), t))
        normalized = os.path.normpath(t)
        return (joined in paths or normalized in paths or
                any(p.endswith("/" + normalized) for p in paths))
    return t in basenames


def scan(vault: str, ignore: tuple[str, ...] = ()) -> list[dict]:
    """扫描并返回失效链接列表。"""
    paths, basenames = build_index(vault)
    broken: list[dict] = []

    for rel in iter_notes(vault):
        if any(pat in rel for pat in ignore):
            continue
        try:
            with open(os.path.join(vault, rel), encoding="utf-8", errors="ignore") as fh:
                raw = fh.read()
        except OSError:
            continue
        for lineno, line in enumerate(strip_code(raw).split("\n"), 1):
            for bang, target in LINK_RE.findall(line):
                if resolve(target, rel, paths, basenames):
                    continue
                broken.append(
                    {
                        "file": rel,
                        "line": lineno,
                        "target": normalize(target),
                        "kind": "embed" if bang else "link",
                    }
                )
    return broken


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="检查 Obsidian vault 的失效 wikilink")
    ap.add_argument(
        "--vault",
        default=DEFAULT_VAULT,
        help="vault 路径；省略时从 $OBSIDIAN_VAULT_PATH 或 ~/.config/agent-skills/obsidian-vault-path 解析",
    )
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--quiet", action="store_true", help="只输出统计")
    ap.add_argument(
        "--ignore-template",
        action="store_true",
        help="跳过 Templates/ 下的占位符链接（模板占位符是有意为之）",
    )
    args = ap.parse_args(argv)

    try:
        vault, vault_source = resolve_vault(args.vault)
    except VaultPathError as exc:
        print(exc, file=sys.stderr)
        return 2
    if not os.path.isdir(vault):
        print(f"vault 不存在：{vault}（来源：{vault_source}）", file=sys.stderr)
        return 2

    ignore = ("Templates/",) if args.ignore_template else ()
    broken = scan(vault, ignore)

    if args.json:
        print(json.dumps({"vault": vault, "vault_source": vault_source,
                          "broken_count": len(broken), "broken": broken},
                         ensure_ascii=False, indent=2))
        return 1 if broken else 0

    if not broken:
        if not args.quiet:
            print("✓ 未发现失效链接")
        else:
            print("0")
        return 0

    if not args.quiet:
        grouped: dict[str, list[dict]] = {}
        for item in broken:
            grouped.setdefault(item["file"], []).append(item)
        print(f"发现 {len(broken)} 个失效链接，涉及 {len(grouped)} 个文件\n")
        for rel, items in sorted(grouped.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            print(f"  {rel}  ({len(items)})")
            for it in items:
                tag = "嵌入" if it["kind"] == "embed" else "链接"
                print(f"      L{it['line']:<5} [{tag}] {it['target']}")
            print()
    print(len(broken) if args.quiet else f"合计 {len(broken)} 个失效链接")
    return 1


if __name__ == "__main__":
    sys.exit(main())
