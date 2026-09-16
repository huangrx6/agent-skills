#!/usr/bin/env python3
"""用 **draw.io 桌面版自己的命令行导出**把 `.drawio` 渲染成 PNG / SVG / PDF。

## 这是"官方导出"吗

是。draw.io 官方提供的批处理导出就是桌面版（Electron）的二进制的 `--export`：

    draw.io -x -f png -o out.png in.drawio        # -x = export，-f = format

除了它，官方没有别的 CLI（网页版只能人在界面上点 File → Export as）。
本工具只是把这套参数封一层：探测可执行文件、给结构化回执、给清楚的失败原因。

## 实测（2026-09-17，draw.io 31.4.5，macOS）

本机装上 draw.io 之后实测通过：`-x -f png -o out.png -s 2` 出图正确（PNG 889×446
的场景在 `-s 2` 下是 1778×892）。参数语义按 `draw.io --help` 的官方说明对齐，其中两条
**容易踩**：

- **`--crop` 是 PDF 专用的**（官方原话："crops PDF to diagram size"）。图片的裁切
  默认就是按内容来（`--size diagram`），所以对 PNG/SVG 传 `--crop` 是**静默无效**——
  本工具遇到这种组合直接报错，不给你一份"看起来成功了"的假结果。
- **`-t/--transparent` 有效，但对我们生成的 `.drawio` 常常看不出效果**：emit 时写了
  显式底色（`mxGraphModel background="…"`，刻意的 —— 不写底色导出时不稳定），
  `-t` 只能去掉 draw.io 自己的画布底色，去不掉图里那块。工具会在回执里提示这件事。

定位不变：它是**可选加速器**（`references/drawio-backend.md` 第五节）。`.drawio` 是纯
XML，我们自己就能生成；导出也可以人在应用里点一下。没装 draw.io 时明确报环境，不假装成功。

## 用法

    python3 dev-tools/export_drawio.py x.drawio -o x.png
    python3 dev-tools/export_drawio.py x.drawio -o x.svg --format svg --scale 2
    python3 dev-tools/export_drawio.py x.drawio -o x.png --border 48 --embed
    python3 dev-tools/export_drawio.py x.drawio -o x.pdf --format pdf --crop

- `-s/--scale` 倍率；`-b/--border` 四周留白（**按图内单位算**，**默认 48**）。
  官方默认是 0，导出来内容紧贴边框、像被框卡住 —— 外面的留白比图内节点自己的
  内边距（22~24）还小就不自然。实测官方 `-b N` 每边只加 0.75×N 图内单位
  （16→12 / 32→24 / 64→48，72dpi 换算），本工具已经替你换算过，写 48 就是每边 48。
  **但官方分得不均**：总量对，落到四边是左/上 ≈1.31×B、右/下 ≈0.69×B（下表），
  所以默认按**最紧的一边**定 —— 48 时最紧的一边仍有 ≈33 图内单位（66px@2×），
  比图内间距还松一点。`--border 0` 仍可显式要贴边。
- `-e/--embed` 把图**嵌进产物**（PNG/SVG/PDF）—— 出来的图还能在 draw.io 里打开继续改
- `--size page` 导出整页（默认 `diagram`：按内容裁切）
- `--crop` 只对 PDF 有效（见上）

退出码：0 = 成功；1 = 导出器跑失败（详见 --json 的 message）；
2 = 环境不具备（找不到 draw.io）或参数/输入不可用。
环境变量 `DRAWIO_BIN` 或 `--binary` 可以指定可执行文件路径。
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
from typing import Sequence

# 封闭集合：不认识的格式直接报错（与"未知 kind 不 fallback"同一条规矩）
FORMATS = ("png", "svg", "pdf", "jpg")
# 官方 `--size`：diagram（默认，按内容裁切）/ page（整页）
SIZE_MODES = ("diagram", "page")
# 实测（2026-09-17，31.4.5）：`-b N` 每边只加 **0.75×N** 图内单位
# （实测 -b 16 → 每边 +12，-b 32 → +24，-b 64 → +48）。换算来自 72dpi/96dpi。
# 所以对外承诺"--border 32 = 每边 32 图内单位"时，传给 draw.io 的要除以它。
BORDER_TO_DIAGRAM = 0.75
# 默认留白。官方默认 0（贴边），而图内节点自己的内边距是 22~24 —— 外面比里面还紧
# 就不自然。**但官方把 border 分得不均**（实测 2026-09-17，31.4.5，scale 2）：
#   总量对（每轴 +2B 图内单位），落到四边却是 左/上 ≈1.31×B、右/下 ≈0.69×B：
#     --border 16 → 21.0 / 26.5 / 11.5 / 11.5 图内单位（左/上/右/下）
#     --border 32 → 42.0 / 47.5 / 22.0 / 22.0
#     --border 64 → 85.0 / 90.5 / 43.5 / 43.5
# 「挤不挤」看的是**最紧的一边**，所以默认按右/下算：48 → 最紧 ≈33 图内单位
# （≈1.4 × 图内内边距），四个方向都松得下来。
DEFAULT_BORDER = 48.0
TIMEOUT_S = 180

_MAC_CANDIDATES = (
    "/Applications/draw.io.app/Contents/MacOS/draw.io",
    "/Applications/drawio.app/Contents/MacOS/drawio",
)
_OTHER_CANDIDATES = (
    os.path.expanduser("~/Applications/draw.io.app/Contents/MacOS/draw.io"),
    "/usr/bin/drawio",
    "/opt/drawio/drawio",
    "/snap/bin/drawio",
    r"C:\Program Files\draw.io\draw.io.exe",
    r"C:\Program Files (x86)\draw.io\draw.io.exe",
)
_PATH_NAMES = ("drawio", "draw.io", "draw.io-desktop")


def find_binary(explicit: str | None) -> str | None:
    """找 draw.io 桌面版可执行文件；找不到返回 None（不抛）。"""
    if explicit:
        return explicit if os.path.exists(explicit) else shutil.which(explicit)
    env = os.environ.get("DRAWIO_BIN", "").strip()
    if env:
        got = env if os.path.exists(env) else shutil.which(env)
        if got:
            return got
    for pattern in _MAC_CANDIDATES + _OTHER_CANDIDATES:
        for hit in glob.glob(pattern):
            if os.path.exists(hit):
                return hit
    for name in _PATH_NAMES:
        got = shutil.which(name)
        if got:
            return got
    return None


def build_command(binary: str, source: str, out: str, fmt: str, scale: float,
                  transparent: bool = False, crop: bool = False,
                  no_sandbox: bool = False, border: float | None = None,
                  embed: bool = False, size: str = "diagram") -> list[str]:
    """拼官方导出命令。**纯函数**，方便测试（不依赖机器上有没有 draw.io）。

    参数语义照 `draw.io --help`（31.4.5）：`-x` 导出、`-f` 格式、`-o` 输出、
    `-s` 倍率、`-t` 透明、`-b` 留白、`-e` 嵌入图、`--crop` **只对 PDF**、
    `--size` 是 diagram（默认，按内容裁切）/ page（整页）。
    """
    cmd = [binary, "-x", "-f", fmt, "-o", out, "-s", f"{scale:g}"]
    if size != "diagram":                 # diagram 是官方默认值，不用写
        cmd += ["--size", size]
    if transparent:
        cmd.append("-t")
    if border is not None:
        cmd += ["-b", f"{border:g}"]
    if embed:
        cmd.append("-e")
    if crop:
        cmd.append("--crop")
    if no_sandbox:
        # Docker / root 下 Electron 需要它；普通桌面会话不需要（也不该默认加）
        cmd.append("--no-sandbox")
    cmd.append(source)
    return cmd


def _declares_background(source: str) -> str | None:
    """文件里是否写了**显式底色**（`background="#RRGGBB"`）。

    为什么关心它：`-t/--transparent` 只能去掉 draw.io 自己的画布底色，
    去不掉图里那块 —— 我们 emit 时刻意写了显式底色（不写的话导出底色不稳定），
    所以"导出透明图"这件事在我们生成的文件上常常看不出效果。这种事必须说出来，
    不能让你拿到一份"看起来成功了"的图还以为透明了。
    """
    try:
        with open(source, encoding="utf-8") as fh:
            head = fh.read(4096)
    except OSError:
        return None
    hit = re.search(r'background="(#[0-9A-Fa-f]{6})"', head)
    return hit.group(1) if hit else None


def export(source: str, out: str, fmt: str = "png", scale: float = 2.0,
           transparent: bool = False, crop: bool = False, no_sandbox: bool = False,
           binary: str | None = None, border: float | None = None,
           embed: bool = False, size: str = "diagram") -> dict:
    """跑一次官方导出。结果一律进回执，不抛业务异常。"""
    if fmt not in FORMATS:
        return {"ok": False, "stage": "input",
                "message": f"不支持的格式 {fmt!r}；可选：{'/'.join(FORMATS)}"}
    if size not in SIZE_MODES:
        return {"ok": False, "stage": "input",
                "message": f"--size 只能是 {'/'.join(SIZE_MODES)}（收到 {size!r}）"}
    if crop and fmt != "pdf":
        # 官方：--crop 是 PDF 专用的。对图片传它是**静默无效** —— 这种"看着成功了
        # 其实没生效"是本项目最不能接受的失败模式，所以直接报错并给出正确写法。
        return {"ok": False, "stage": "input",
                "message": f"--crop 只对 PDF 有效（官方：crops PDF to diagram size）；"
                           f"{fmt} 的裁切默认就是按内容来（--size diagram），"
                           f"要整页用 --size page"}
    try:
        scale = float(scale)
    except (TypeError, ValueError) as exc:
        return {"ok": False, "stage": "input", "message": f"scale 不合法：{exc}"}
    if border is not None:
        try:
            # 对外是"图内单位"，传给 draw.io 前按实测比例换算（见 BORDER_TO_DIAGRAM）
            border = float(border) / BORDER_TO_DIAGRAM
        except (TypeError, ValueError) as exc:
            return {"ok": False, "stage": "input", "message": f"border 不合法：{exc}"}
    if not os.path.exists(source):
        return {"ok": False, "stage": "input", "message": f"读不到 {source}"}

    declared = _declares_background(source)
    exe = find_binary(binary)
    if not exe:
        return {"ok": False, "stage": "environment",
                "message": "找不到 draw.io 桌面版（官方命令行导出在它里面）。"
                           "装了就会自动找到；也可用 --binary / 环境变量 DRAWIO_BIN 指定。"
                           "不装也行：在 app.diagrams.net 打开这个 .drawio，"
                           "File → Export as 手动导出（references/drawio-backend.md 第五节）。"}
    cmd = build_command(exe, source, out, fmt, scale, transparent, crop,
                        no_sandbox, border, embed, size)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return {"ok": False, "stage": "export", "binary": exe,
                "message": f"导出超时（{TIMEOUT_S}s）"}
    except OSError as exc:
        return {"ok": False, "stage": "environment", "binary": exe,
                "message": f"起不了 draw.io：{exc}"}

    if proc.returncode != 0 or not os.path.exists(out):
        return {"ok": False, "stage": "export", "binary": exe,
                "message": f"退出码 {proc.returncode}；stderr："
                           f"{(proc.stderr or proc.stdout or '')[-400:]}"}
    receipt = {"ok": True, "binary": exe, "format": fmt,
               "out": os.path.abspath(out),
               "engine": "draw.io desktop --export (官方命令行导出)"}
    if transparent and declared:
        # 不静默：你以为是透明图，其实里面还有一块底色
        receipt["note"] = (f"文件里写了显式底色 {declared}（emit 时刻意的），"
                           f"所以 -t 只能去掉 draw.io 自己的画布底色，"
                           f"图内那块底色仍在。要真透明就得先删掉 mxGraphModel 的"
                           f" background 属性。")
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="draw.io 官方命令行导出（PNG/SVG/PDF）")
    ap.add_argument("source", help="*.drawio")
    ap.add_argument("-o", "--out", required=True, help="输出文件")
    ap.add_argument("-f", "--format", default=None,
                    help="png / svg / pdf / jpg（默认按 -o 的后缀猜）")
    ap.add_argument("-s", "--scale", type=float, default=2.0, help="倍率（默认 2）")
    ap.add_argument("-t", "--transparent", action="store_true", help="透明背景")
    ap.add_argument("-b", "--border", type=float, default=DEFAULT_BORDER,
                    help=f"四周留白，图内单位（默认 {DEFAULT_BORDER:g}；官方默认 0 = 贴边）")
    ap.add_argument("-e", "--embed", action="store_true",
                    help="把图嵌进产物（PNG/SVG/PDF）—— 导出的图还能在 draw.io 里打开继续改")
    ap.add_argument("--size", choices=D.MODE_CHOICES if False else SIZE_MODES,
                    default="diagram",
                    help="diagram（默认，按内容裁切）/ page（整页）")
    ap.add_argument("--crop", action="store_true",
                    help="裁到图大小 —— **只对 PDF 有效**（官方说明）；图片默认就按内容裁")
    ap.add_argument("--no-sandbox", action="store_true",
                    help="Docker/root 环境需要（普通桌面会话不要加）")
    ap.add_argument("--binary", help="draw.io 可执行文件路径（默认自动探测）")
    ap.add_argument("--json", action="store_true", help="输出机器可读回执")
    args = ap.parse_args(argv)

    fmt = args.format or os.path.splitext(args.out)[1].lstrip(".").lower() or "png"
    receipt = export(args.source, args.out, fmt=fmt, scale=args.scale,
                     transparent=args.transparent, crop=args.crop,
                     no_sandbox=args.no_sandbox, binary=args.binary,
                     border=args.border, embed=args.embed, size=args.size)
    if args.json:
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
    if not receipt["ok"]:
        print(f"✗ draw.io 导出未完成（{receipt.get('stage')}）：{receipt.get('message')}",
              file=sys.stderr)
        return 2 if receipt.get("stage") in ("environment", "input") else 1
    print(f"✓ draw.io 导出完成（{receipt['format']}，scale {args.scale:g}）：")
    print(f"  {receipt['out']}")
    if receipt.get("note"):
        print(f"  ⚠ {receipt['note']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
