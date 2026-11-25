#!/usr/bin/env python3
"""按顺序运行给定测试文件列表，定位首个制造指定污染产物的测试文件。

只依赖 Python 3.10+ 标准库，跨平台可用。
退出码：0 未发现污染；1 找到污染源；2 参数错误或开始前产物已存在。
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path


def resolve_artifact(cwd: Path, artifact: str) -> Path:
    path = Path(artifact)
    return path if path.is_absolute() else (cwd / path)


def build_command(template: str, file_path: str) -> list[str]:
    if "{file}" not in template:
        raise ValueError("--cmd 模板必须包含 {file} 占位符")
    tokens = shlex.split(template)
    return [token.replace("{file}", file_path) for token in tokens]


def find_polluter(
    *,
    artifact: str,
    cmd_template: str,
    files: list[str],
    cwd: Path,
    timeout: int | None = None,
) -> dict:
    artifact_path = resolve_artifact(cwd, artifact)
    if artifact_path.exists():
        raise FileExistsError(f"开始检查前污染产物已存在，请先清理：{artifact_path}")

    checked: list[dict] = []
    for index, target in enumerate(files, start=1):
        argv = build_command(cmd_template, target)
        proc = subprocess.run(
            argv,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        entry = {
            "index": index,
            "file": target,
            "command": argv,
            "returncode": proc.returncode,
            "polluted": artifact_path.exists(),
        }
        checked.append(entry)
        if entry["polluted"]:
            return {
                "found": True,
                "polluter": target,
                "artifact": str(artifact_path),
                "returncode": proc.returncode,
                "checked": checked,
            }

    return {
        "found": False,
        "polluter": None,
        "artifact": str(artifact_path),
        "returncode": 0,
        "checked": checked,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="逐个执行测试文件，找出首个创建指定污染产物的文件"
    )
    parser.add_argument(
        "--artifact",
        required=True,
        help="不该出现的污染文件或目录路径（相对 --cwd 或绝对路径）",
    )
    parser.add_argument(
        "--cmd",
        required=True,
        help="单文件执行命令模板，需包含 {file}，例如：'python3 -m unittest {file}'",
    )
    parser.add_argument(
        "--cwd",
        default=".",
        help="执行测试的工作目录（默认当前目录）",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="单个测试文件的超时秒数（可选）",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 输出定位结果",
    )
    parser.add_argument(
        "files",
        nargs="+",
        help="待排查的测试文件路径列表",
    )
    args = parser.parse_args(argv)

    cwd = Path(os.path.abspath(args.cwd))
    if not cwd.is_dir():
        print(f"错误：工作目录不存在：{cwd}", file=sys.stderr)
        return 2

    try:
        report = find_polluter(
            artifact=args.artifact,
            cmd_template=args.cmd,
            files=args.files,
            cwd=cwd,
            timeout=args.timeout,
        )
    except (ValueError, FileExistsError, subprocess.TimeoutExpired) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif report["found"]:
        print(
            f"发现污染源：{report['polluter']}\n"
            f"  产物：{report['artifact']}\n"
            f"  退出码：{report['returncode']}\n"
            f"  已排查：{len(report['checked'])}/{len(args.files)}"
        )
    else:
        print(f"未发现污染源（共排查 {len(report['checked'])} 个文件）")

    return 1 if report["found"] else 0


if __name__ == "__main__":
    sys.exit(main())
