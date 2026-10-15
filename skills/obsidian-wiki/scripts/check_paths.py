#!/usr/bin/env python3
"""只读提取 .obsidian 配置中的常见 POSIX 绝对路径并检查存在性。

这是文本与扩展名启发式，不解析插件语义、Windows 路径或所有配置转义。
用法：check_paths.py [--vault PATH] [--json | --quiet]
退出码：0 无疑似文件缺失（可有目录提示），1 有缺失，2 vault 不可用。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys

DEFAULT_VAULT = None  # 不再硬编码；由 vault_path.py 解析（见下方说明）

# 只看配置文件。不含 .js/.css：那两种是代码，路径常是候选列表或 url()，噪音大。
CONFIG_EXTS = (".json", ".yaml", ".yml", ".toml", ".json5")

# 配置文件的根目录（相对 vault）。整体只在这个子树里找。
CONFIG_ROOT = ".obsidian"

# 绝对路径：/ 或 ~ 开头。两种取法，优先按引号取 ——
# 带空格的路径（/Users/x/my folder/a.css）用“遇空白即停”的取法会被截断，
# 而截断后的路径必然不存在，会变成误报。配置文件里路径几乎总是带引号，
# 所以先按引号取完整的；取不到再退回逐字符取（应对 YAML 里未加引号的写法）。
_ABS_PREFIX = r"(?:~/|/(?:Users|home|opt|Volumes|var|srv|private|tmp|Applications|Library|etc|usr)/)"
QUOTED_RE = re.compile(r"""["'](""" + _ABS_PREFIX + r"""[^"'\n]*)["']""")
BARE_RE = re.compile(r"""(?:^|["'\s:=\[])(""" + _ABS_PREFIX + r"""[^\s"'`,;)\]}#]+)""")


def _load_sibling(name: str):
    """按文件位置加载共享解析器，不依赖调用者的 sys.path。"""
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


def is_file_reference(path: str) -> bool:
    """按尾斜杠与扩展名分类；无法可靠区分带点目录和无扩展名可执行文件。"""
    if path.endswith("/"):
        return False
    base = os.path.basename(path.rstrip("/"))
    if not base:
        return False
    return bool(os.path.splitext(base)[1])


def iter_configs(vault: str):
    """产出 .obsidian/ 下所有配置文件的相对路径。"""
    root = os.path.join(vault, CONFIG_ROOT)
    if not os.path.isdir(root):
        return
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in {".git", "node_modules"} and not d.startswith("."))
        for name in sorted(files):
            if name.endswith(CONFIG_EXTS):
                yield os.path.relpath(os.path.join(dirpath, name), vault)


def extract_paths(text: str) -> list[tuple[int, str]]:
    """提取 (行号, 路径)。行号用于让人能直接跳过去改。

    先读取完整的带引号路径，再遮蔽这些片段提取未加引号的路径，避免漏掉同一行的混合写法。
    """
    found = []
    for lineno, line in enumerate(text.split("\n"), 1):
        found.extend((lineno, m.group(1)) for m in QUOTED_RE.finditer(line))
        remaining = QUOTED_RE.sub(lambda m: " " * len(m.group(0)), line)
        found.extend((lineno, m.group(1)) for m in BARE_RE.finditer(remaining))
    return found


def scan(vault: str) -> dict:
    """扫描并返回 {"file_refs": [...], "dir_refs": [...]}。

    file_refs —— 引用了不存在的文件（硬错误）
    dir_refs  —— 引用了不存在的目录（提示；可能本来就还没建）
    """
    file_refs: list[dict] = []
    dir_refs: list[dict] = []

    for rel in iter_configs(vault):
        try:
            with open(os.path.join(vault, rel), encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
        except OSError:
            continue

        seen: set[str] = set()
        for lineno, raw in extract_paths(text):
            # 仅检查展开后的存在性；具体插件是否展开 ~ 仍需人工确认
            expanded = os.path.expanduser(raw)
            if os.path.exists(expanded):
                continue
            if raw in seen:
                continue
            seen.add(raw)

            item = {"file": rel, "line": lineno, "path": raw,
                    "tilde": raw.startswith("~/")}
            (file_refs if is_file_reference(raw) else dir_refs).append(item)

    return {"file_refs": file_refs, "dir_refs": dir_refs}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="检查 Obsidian 配置里的失效绝对路径")
    ap.add_argument(
        "--vault",
        default=DEFAULT_VAULT,
        help="vault 路径；省略时从 $OBSIDIAN_VAULT_PATH 或 ~/.config/agent-skills/obsidian-vault-path 解析",
    )
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--quiet", action="store_true", help="只输出统计")
    args = ap.parse_args(argv)

    try:
        vault, vault_source = resolve_vault(args.vault)
    except VaultPathError as exc:
        print(exc, file=sys.stderr)
        return 2
    if not os.path.isdir(vault):
        print(f"vault 不存在：{vault}（来源：{vault_source}）", file=sys.stderr)
        return 2

    result = scan(vault)
    file_refs, dir_refs = result["file_refs"], result["dir_refs"]

    if args.json:
        print(json.dumps({"vault": vault, "vault_source": vault_source,
                          "missing_file_count": len(file_refs),
                          "missing_dir_count": len(dir_refs),
                          "missing_files": file_refs, "missing_dirs": dir_refs},
                         ensure_ascii=False, indent=2))
        return 1 if file_refs else 0

    if not file_refs and not dir_refs:
        print("✓ 未发现扫描范围内的缺失路径" if not args.quiet else "0")
        return 0

    if file_refs and not args.quiet:
        print(f"✗ {len(file_refs)} 处配置引用了不存在的文件：\n")
        for it in file_refs:
            print(f"  {it['file']}:{it['line']}")
            print(f"      {it['path']}")
            if it["tilde"]:
                print("      （含 ~；需确认插件是否支持展开用户目录）")
        print()

    if dir_refs and not args.quiet:
        print(f"· {len(dir_refs)} 处引用了不存在的目录（可能本来就还没建，仅提示）：\n")
        for it in dir_refs:
            print(f"  {it['file']}:{it['line']}  {it['path']}")
        print()

    if args.quiet:
        print(len(file_refs))
    else:
        print(f"合计：{len(file_refs)} 个失效文件引用，{len(dir_refs)} 个不存在的目录")
    return 1 if file_refs else 0


if __name__ == "__main__":
    sys.exit(main())
