#!/usr/bin/env python3
"""解析 vault：显式参数 > OBSIDIAN_VAULT_PATH > 配置文件 > 旧位置配置。

AGENT_SKILLS_CONFIG_DIR 默认 ~/.config/agent-skills，文件名 obsidian-vault-path。
用法：vault_path.py [PATH] [--explain]；退出码 0 目录存在，2 解析失败或目录不存在。
"""

from __future__ import annotations

import os
import sys

ENV_VAR = "OBSIDIAN_VAULT_PATH"
CONFIG_DIR_VAR = "AGENT_SKILLS_CONFIG_DIR"
# 配置目录可由环境变量覆盖。
CONFIG_DIR = os.path.expanduser(
    (os.environ.get(CONFIG_DIR_VAR) or "").strip() or "~/.config/agent-skills")
CONFIG_PATH = os.path.join(CONFIG_DIR, "obsidian-vault-path")
# 旧位置：只**兼容读取**，不再作为首选（老机器不用改配置）。
LEGACY_PATH = os.path.expanduser("~/.config/obsidian-vault-path")


def config_candidates() -> list[str]:
    """按优先级给出要读的配置文件：新位置 → 旧位置。"""
    both = [CONFIG_PATH, LEGACY_PATH]
    seen, out = set(), []
    for p in both:
        if os.path.abspath(p) not in seen:
            seen.add(os.path.abspath(p))
            out.append(p)
    return out


class VaultPathError(RuntimeError):
    """无法解析 vault 路径。"""


def resolve(explicit: str | None = None) -> tuple[str, str]:
    """返回 (vault 路径, 来源说明)。都解析不出时抛 VaultPathError。"""
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit)), "命令行参数"

    env = os.environ.get(ENV_VAR)
    if env and env.strip():
        return os.path.abspath(os.path.expanduser(env.strip())), f"环境变量 {ENV_VAR}"

    for candidate in config_candidates():
        if os.path.isfile(candidate):
            try:
                with open(candidate, encoding="utf-8") as fh:
                    line = fh.readline().strip()
            except OSError as exc:
                raise VaultPathError(f"配置文件存在但读不了:{candidate}({exc})") from exc
            if line:
                where = "配置文件" if candidate == CONFIG_PATH else "配置文件（旧位置）"
                return os.path.abspath(os.path.expanduser(line)), f"{where} {candidate}"

    raise VaultPathError(
        "解析不出 vault 路径。三种配置方式任选一种:\n"
        f"  1. 环境变量  export {ENV_VAR}=\"/path/to/your/vault\"\n"
        # 创建命令用 `python3 -c`：macOS / Linux / Windows 都一样能跑
        # （`mkdir -p` 与 `echo >` 在 PowerShell 里不是这个写法）。
        f"  2. 配置文件  python3 -c \"from pathlib import Path; p=Path('{CONFIG_PATH}'); "
        "p.parent.mkdir(parents=True, exist_ok=True); p.write_text('/path/to/your/vault')\"\n"
        "  3. 显式传入  python3 check_links.py --vault /path/to/your/vault"
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    explain = "--explain" in args
    args = [a for a in args if a != "--explain"]

    explicit = args[0] if args else None
    try:
        path, source = resolve(explicit)
    except VaultPathError as exc:
        print(exc, file=sys.stderr)
        return 2

    if explain:
        ok = "✓ 目录存在" if os.path.isdir(path) else "✗ 目录不存在"
        print(f"{path}\n来源:{source}\n{ok}")
    else:
        print(path)

    return 0 if os.path.isdir(path) else 2


if __name__ == "__main__":
    sys.exit(main())
