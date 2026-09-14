#!/usr/bin/env python3
"""解析 Obsidian vault 路径 —— 这是全仓库唯一的来源。

为什么有这个脚本:
两个 skill、链接检查脚本、vault 的 pre-commit 都要知道 vault 在哪。以前这个
路径硬编码在 10 处(PKB 的 SKILL.md frontmatter 与正文、WLRR 的 SKILL.md
frontmatter 与正文、vault-map.md、check_links.py、README)。vault 搬家或改名时
要同时改这些,漏一处就会静默用错路径 —— 而"静默用错路径"正是这个 skill 体系
一直在防的那类故障。

解析顺序:
  1. 命令行显式传入(只有 check_links.py --vault 会走到)
  2. 环境变量 OBSIDIAN_VAULT_PATH
  3. 配置文件 ~/.config/agent-skills/obsidian-vault-path (单行,内容就是路径)
  都没有 → 报错并给出配置指引

用法:
    python3 vault_path.py            # 打印解析结果
    python3 vault_path.py --explain  # 打印结果与来源
退出码:0 成功,2 无法解析。
"""

from __future__ import annotations

import os
import sys

ENV_VAR = "OBSIDIAN_VAULT_PATH"
CONFIG_DIR_VAR = "AGENT_SKILLS_CONFIG_DIR"
# **统一配置根**：所有 skill 的配置都放在这一个目录里，跨平台同一个路径
# （`AGENT_SKILLS_CONFIG_DIR` 可以把它整体搬走）。以前散在 `~/.config` 根下，
# 谁能读什么没有一处说得清 —— 那才是真正的乱。
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
