#!/usr/bin/env python3
"""检查 Obsidian 配置里指向不存在位置的绝对路径。

为什么有这个脚本：
2026-09-12，vault 从 ~/obsidian 搬到 ~/Documents/obsidian 之后，
.obsidian/plugins/better-export-pdf/data.json 里的 cssSnippet 仍指向旧位置。
插件的读取逻辑是

    try   { await fs2.readFile(config.cssSnippet, ...); await preview.insertCSS(...); }
    catch (e) { console.warn(e); }        // ← 只打 console

ENOENT 被吞掉，UI 上零提示，PDF 静默地不带自定义样式。更糟的是插件每次导出都执行
`settings.prevConfig = this.config`，错误路径被一遍遍重新固化。而发现它纯属偶然 ——
我当时在查别的问题。

这类"配置指向虚空 + 失败静默"没法靠自觉发现，只能靠机械检查。

范围只限 .obsidian/ 下的**配置**文件（.json/.yaml/.yml/.toml/.json5），刻意不含：

  · 笔记正文 —— 里面的绝对路径绝大多数是示例（/Users/me/workspace/app、
    /Users/path/to/project、/opt/app）。实测 64 处，全部纳入会淹没真问题。
  · 插件的打包 JS —— 里面的路径是"候选列表"（逐个尝试直到命中）。
    例如 feishu-lark-cli-sync 依次试 ~/.local/bin/lark-cli、/opt/homebrew/bin/lark-cli …
    不存在的候选是设计如此，不是缺陷。

分层判定（决定要不要阻塞提交）：
  · 以文件扩展名结尾（.css / .json / .png …）→ 明确在引用一个**文件** → 必须存在 → 失效即失败
  · 无扩展名 → 大概率是**目录**（导出目录、缓存目录），可能本来就还没建 → 仅提示

不用绝对路径就完了吗：不行。插件的读取用的是 Node 的 fs/promises（不是 Obsidian 的
vault.adapter），相对路径会相对进程 cwd 解析、不可靠。所以绝对路径是插件的硬性要求，
这里能做的只是把"它失效了"这件事变成可见。

用法：
    python3 check_paths.py                  # 扫自动解析出的 vault
    python3 check_paths.py --vault PATH     # 显式指定 vault
    python3 check_paths.py --json           # 机器可读输出
    python3 check_paths.py --quiet          # 只输出统计

vault 路径不在本文件硬编码，由同目录的 vault_path.py 按
「环境变量 OBSIDIAN_VAULT_PATH → ~/.config/agent-skills/obsidian-vault-path」解析。

退出码：0 = 未发现失效的**文件**路径，1 = 有，2 = vault 路径解析失败或不存在。
       目录类路径不存在只提示，不影响退出码。
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
BARE_RE = re.compile(r"""["'\s:=[](""" + _ABS_PREFIX + r"""[^\s"'`,;)\]}#]+)""")


def _load_sibling(name: str):
    """动态加载同目录脚本。

    用 importlib 而不是 `from vault_path import ...`：scripts/ 不是 Python 包，
    同级 import 在静态层面无法解析。与其用 type: ignore 盖住那条报错，
    不如把「动态加载同级脚本」写明白。
    """
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
    """判断这条路径是在引用一个文件（而不是目录）。

    只看最后一段是否有扩展名。带扩展名 = 引用文件 → 不存在就是硬错误；
    不带 = 多半是目录（导出目录、缓存目录）→ 可能还没建，只提示。

    已知的盲区：末尾无扩展名的**可执行文件**（/…/bin/lark-cli）会被归成目录。
    没法从路径本身区分“待创建的输出目录”和“无扩展名的可执行文件”，而前者很常见，
    所以这里宁可保守 —— 归成目录只提示，不阻塞提交。误判的代价是多看一眼，
    而不是被一个正常的输出目录配置挡住提交（那会把人逼向 --no-verify）。
    """
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

    每行先按引号取（能拿到含空格的完整路径）；这一行没有任何带引号的绝对路径时，
    再退回逐字符取。不是两种都跑 —— 那会把同一处报两遍。
    """
    found = []
    for lineno, line in enumerate(text.split("\n"), 1):
        quoted = QUOTED_RE.findall(line)
        if quoted:
            found.extend((lineno, p) for p in quoted)
            continue
        found.extend((lineno, m.group(1)) for m in BARE_RE.finditer(line))
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
            # ~ 开头的路径：Node 的 fs 不做展开，一定会失败
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
        print("✓ 配置里的绝对路径全部存在" if not args.quiet else "0")
        return 0

    if file_refs and not args.quiet:
        print(f"✗ {len(file_refs)} 处配置引用了不存在的文件：\n")
        for it in file_refs:
            print(f"  {it['file']}:{it['line']}")
            print(f"      {it['path']}")
            if it["tilde"]:
                print("      （~ 开头的路径 Node 的 fs 不会展开，必然失败）")
        print()

    if dir_refs and not args.quiet:
        print(f"· {len(dir_refs)} 处引用了不存在的目录（可能本来就还没建，仅提示）：\n")
        for it in dir_refs:
            print(f"  {it['file']}:{it['line']}  {it['path']}")
        print()

    if args.quiet:
        print(len(file_refs))
    print(f"合计：{len(file_refs)} 个失效文件引用，{len(dir_refs)} 个不存在的目录")
    return 1 if file_refs else 0


if __name__ == "__main__":
    sys.exit(main())
