#!/usr/bin/env python3
"""对 Obsidian vault 做只读健康检查。

默认检查失效 wikilink 和配置中的失效文件路径；`--strict` 额外检查
初始化脚本提供的核心入口，适合新建或共享前的 vault。不会修改文件。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent


def _load(name: str):
    path = HERE / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_obsidian_health_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了同目录模块：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LINKS = _load("check_links")
PATHS = _load("check_paths")
VAULT_PATH = _load("vault_path")
INIT = _load("init_vault")
EXPECTED_FILES = tuple(sorted(INIT.LAYOUT))


def _expected_dirs() -> tuple[str, ...]:
    dirs: set[str] = set()
    for relative in INIT.LAYOUT:
        current = Path(relative).parent
        while current != Path("."):
            dirs.add(current.as_posix())
            current = current.parent
    return tuple(sorted(dirs))


EXPECTED_DIRS = _expected_dirs()


def inspect(vault: str, *, strict: bool = False) -> dict[str, object]:
    root = os.path.abspath(os.path.expanduser(vault))
    if not os.path.isdir(root):
        raise ValueError(f"vault 不存在或不是目录：{root}")

    missing_dirs = [rel for rel in EXPECTED_DIRS if not os.path.isdir(os.path.join(root, rel))]
    missing_files = [rel for rel in EXPECTED_FILES if not os.path.isfile(os.path.join(root, rel))]
    broken_links = LINKS.scan(root, ignore_template=True)
    path_report = PATHS.scan(root)
    errors = []
    if broken_links:
        errors.append(f"{len(broken_links)} 个失效 wikilink/嵌入")
    if path_report["file_refs"]:
        errors.append(f"{len(path_report['file_refs'])} 个配置文件路径失效")
    if strict and missing_dirs:
        errors.append(f"缺少 {len(missing_dirs)} 个约定目录")
    if strict and missing_files:
        errors.append(f"缺少 {len(missing_files)} 个约定入口文件")

    return {
        "vault": root,
        "strict": strict,
        "ok": not errors,
        "errors": errors,
        "missing_dirs": missing_dirs,
        "missing_files": missing_files,
        "broken_links": broken_links,
        "missing_config_files": path_report["file_refs"],
        "missing_config_dirs": path_report["dir_refs"],
    }


def _render(report: dict[str, object], quiet: bool) -> None:
    errors = report["errors"]
    if quiet:
        print("0" if report["ok"] else str(len(errors)))
        return
    if report["ok"]:
        print(f"✓ vault 健康检查通过：{report['vault']}")
    else:
        print(f"✗ vault 健康检查发现 {len(errors)} 类阻塞问题：{report['vault']}")
        for item in errors:
            print(f"  - {item}")
    if report["strict"] and report["missing_dirs"]:
        print("  缺少目录：" + "、".join(report["missing_dirs"]))
    if report["strict"] and report["missing_files"]:
        print("  缺少入口：" + "、".join(report["missing_files"]))
    if report["missing_config_dirs"]:
        print(f"  配置引用了 {len(report['missing_config_dirs'])} 个不存在目录（仅提示）")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", help="vault 路径；省略时按 vault_path.py 解析")
    parser.add_argument("--strict", action="store_true", help="把缺少初始化结构视为失败")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--quiet", action="store_true", help="只输出失败数量")
    args = parser.parse_args(argv)
    try:
        vault, _ = VAULT_PATH.resolve(args.vault)
        report = inspect(vault, strict=args.strict)
    except (VAULT_PATH.VaultPathError, ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _render(report, args.quiet)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
