#!/usr/bin/env python3
"""把散落的 skill 配置/缓存迁到项目家目录（默认 ~/.agent-skills）。

默认只预演；加 `--apply` 才移动。规则：

- 目标不存在 → 整体移动；
- 目标已存在 → 逐个条目合并，**冲突不覆盖**，留给人工决定；
- 源目录搬空后删除，非空则保留并提示。

用法：
    python3 tools/migrate_skill_home.py
    python3 tools/migrate_skill_home.py --apply
    python3 tools/migrate_skill_home.py --home /tmp/fake-home --repo . --apply
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Move:
    src: Path
    dst: Path
    label: str


def default_moves(home: Path, repo: Path) -> list[Move]:
    return [
        Move(home / ".config" / "agent-skills", home / ".agent-skills" / "config", "共享配置"),
        Move(home / ".config" / "deck-authoring" / "fonts",
             home / ".agent-skills" / "data" / "deck-authoring" / "fonts", "deck 字体"),
        Move(home / ".config" / "deck-authoring" / "font-index.json",
             home / ".agent-skills" / "data" / "deck-authoring" / "font-index.json", "deck 字体索引"),
        Move(home / ".cache" / "diagram-authoring" / "libraries",
             home / ".agent-skills" / "data" / "diagram-authoring" / "libraries", "diagram 图标库"),
        Move(home / ".cache" / "agent-skills",
             home / ".agent-skills" / "data" / "deck-authoring" / "legacy-cache", "旧 deck 缓存"),
        Move(repo / "skills" / "learning-scout" / ".venv",
             home / ".agent-skills" / "data" / "learning-scout" / "venv", "learning-scout 环境"),
        Move(home / ".config" / "excalidraw-library-path",
             home / ".agent-skills" / "config" / "excalidraw-library-path", "Excalidraw 素材库路径"),
    ]


def _merge_dir(src: Path, dst: Path) -> tuple[list[str], list[str]]:
    """返回 (已移动, 冲突)。目标已有同名条目时保留两边，不覆盖。"""
    moved: list[str] = []
    conflicts: list[str] = []
    for child in sorted(src.iterdir()):
        target = dst / child.name
        if target.exists() or target.is_symlink():
            if child.is_dir() and target.is_dir() and not child.is_symlink():
                sub_moved, sub_conflicts = _merge_dir(child, target)
                moved.extend(f"{child.name}/{item}" for item in sub_moved)
                conflicts.extend(f"{child.name}/{item}" for item in sub_conflicts)
            else:
                conflicts.append(child.name)
            continue
        shutil.move(str(child), str(target))
        moved.append(child.name)
    return moved, conflicts


def apply_move(move: Move, dry_run: bool) -> tuple[list[str], list[str]]:
    src, dst = move.src, move.dst
    if not src.exists() and not src.is_symlink():
        return [], []
    if dry_run:
        return [f"{src} → {dst}"], []
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        shutil.move(str(src), str(dst))
        return [f"{src} → {dst}"], []
    if src.is_dir() and not src.is_symlink():
        moved, conflicts = _merge_dir(src, dst)
        if src.exists() and not any(src.iterdir()):
            src.rmdir()
        return [f"{src}/{item} → {dst}/{item}" for item in moved], [
            f"{src}/{item}（目标已有，未覆盖）" for item in conflicts
        ]
    return [], [f"{src}（目标已有，未覆盖）"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="迁移 skill 配置与缓存到 ~/.agent-skills")
    parser.add_argument("--apply", action="store_true", help="真正移动；默认只预演")
    parser.add_argument("--home", default=str(Path.home()), help="用户主目录（测试用）")
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parent.parent),
                        help="本仓库根目录")
    args = parser.parse_args(argv)

    home = Path(args.home).expanduser().resolve()
    repo = Path(args.repo).expanduser().resolve()
    if not repo.is_dir():
        print(f"仓库目录不存在：{repo}", file=sys.stderr)
        return 2

    all_moved: list[str] = []
    all_conflicts: list[str] = []
    for move in default_moves(home, repo):
        moved, conflicts = apply_move(move, dry_run=not args.apply)
        if moved:
            print(f"\n{move.label}：")
            for item in moved:
                print(f"  ✓ {item}")
        all_moved.extend(moved)
        if conflicts:
            print(f"\n{move.label} 冲突（没有覆盖）：")
            for item in conflicts:
                print(f"  ! {item}")
        all_conflicts.extend(conflicts)

    if not all_moved and not all_conflicts:
        print("没有需要迁移的内容；目录已经就位。")
        return 0
    if args.apply:
        print(f"\n完成：移动 {len(all_moved)} 项，冲突 {len(all_conflicts)} 项。")
    else:
        print(f"\n预演：将移动 {len(all_moved)} 项，冲突 {len(all_conflicts)} 项。")
        print("确认后加 --apply 执行。")
    return 1 if all_conflicts else 0


if __name__ == "__main__":
    raise SystemExit(main())
