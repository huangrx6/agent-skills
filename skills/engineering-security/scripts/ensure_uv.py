#!/usr/bin/env python3
"""ensure_uv.py — 检测 uv 是否可用，不可用则自动安装。

uv 是本 Skill 所有 Python 脚本的运行入口（uv run 自动管理隔离 Python + 依赖，
不污染宿主环境）。本脚本纯标准库，用任何可用的 python 运行一次即可确保 uv 就绪。

运行：python scripts/ensure_uv.py   （或 uv 已装时：uv run scripts/ensure_uv.py）

逻辑：
1. uv 已在 PATH → 输出路径，退出 0
2. uv 不在 PATH → 下载官方安装脚本并执行（装到 ~/.local/bin/uv）
3. 安装后提示 PATH（首次需 source 或重开终端）
"""
from __future__ import annotations
import os
import shutil
import subprocess
import sys
import urllib.request

INSTALL_URL = "https://astral.sh/uv/install.sh"
UV_INSTALL_DIR = os.path.expanduser("~/.local/bin")


def find_uv():
    """返回 uv 的完整路径，找不到返回 None。"""
    return shutil.which("uv") or (
        os.path.join(UV_INSTALL_DIR, "uv") if os.path.isfile(os.path.join(UV_INSTALL_DIR, "uv")) else None
    )


def install_uv():
    """下载并执行 uv 官方安装脚本。"""
    print(f"uv 未检测到，正在从 {INSTALL_URL} 安装（装到 {UV_INSTALL_DIR}，不污染系统）...", file=sys.stderr)
    try:
        req = urllib.request.Request(INSTALL_URL, headers={"User-Agent": "ensure_uv/1.0"})
        script = urllib.request.urlopen(req, timeout=60).read()
    except Exception as e:
        print(f"下载安装脚本失败: {type(e).__name__}: {e}", file=sys.stderr)
        print(f"请手动安装: curl -LsSf {INSTALL_URL} | sh", file=sys.stderr)
        return 1
    try:
        # 通过 sh 执行安装脚本；UV_INSTALL_DIR 已是默认路径
        result = subprocess.run(["sh"], input=script, check=False)
        if result.returncode != 0:
            print(f"安装脚本返回非零退出码: {result.returncode}", file=sys.stderr)
            return result.returncode
    except Exception as e:
        print(f"执行安装脚本失败: {type(e).__name__}: {e}", file=sys.stderr)
        print(f"请手动安装: curl -LsSf {INSTALL_URL} | sh", file=sys.stderr)
        return 1
    return 0


def main():
    uv_path = find_uv()
    if uv_path:
        print(f"uv 已就绪: {uv_path}")
        return 0
    rc = install_uv()
    if rc != 0:
        return rc
    uv_path = find_uv()
    if uv_path:
        print(f"uv 安装成功: {uv_path}", file=sys.stderr)
        if UV_INSTALL_DIR not in os.environ.get("PATH", ""):
            print(f"提示：请将 {UV_INSTALL_DIR} 加入 PATH，或重新打开终端。", file=sys.stderr)
            print(f"  临时生效：export PATH=\"{UV_INSTALL_DIR}:$PATH\"", file=sys.stderr)
        return 0
    print("安装后仍找不到 uv，请检查安装日志或手动安装。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
