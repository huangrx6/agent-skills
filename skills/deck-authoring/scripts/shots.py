#!/usr/bin/env python3
"""整页 HTML → 每页一张 PNG：用系统 Chrome 截图，再按固定几何裁开。

不装 Playwright：macOS 上一定有 Chrome，`--headless=new --screenshot` 就够。
"""
from __future__ import annotations

import argparse
import contextlib
import os
import subprocess
import sys

from PIL import Image

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
GAP = 36          # 页间距，和 render.py 的 `.slide{margin-bottom}` 是同一个数


def shoot(html: str, out_dir: str, width: int, height: int, count: int) -> list[str]:
    # 产物不存在就别启 Chrome：它会乐颠颠地截一张**自己的错误页**（深灰底），
    # 而这里会把它切成 `page-01.png…` 并报“✓ 截出 N 页” —— 于是一整份
    # “错误页 PPTX”静默进了交付（贴图版 pptx 只吃 pages/，看不出区别）。
    if not os.path.isfile(os.path.abspath(html)):
        raise SystemExit(f"✗ 读不到产物：{os.path.abspath(html)}")
    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError as exc:
        raise SystemExit(f"✗ 建不了输出目录 {out_dir}：{exc}") from exc
    full = os.path.join(out_dir, "_full.png")
    total = height * count + GAP * (count - 1)
    argv = [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
            "--force-device-scale-factor=2",           # 2x：投影/打印不模糊
            f"--screenshot={full}", f"--window-size={width},{total}",
            f"file://{os.path.abspath(html)}"]
    try:
        proc = subprocess.run(argv, check=False, capture_output=True)
    except FileNotFoundError:
        raise SystemExit(f"✗ 找不到 Chrome：{CHROME}（这一步要本机 Chrome）") from None
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace").strip()[:300]
        raise SystemExit(f"✗ Chrome 截图失败（返回码 {proc.returncode}）：{err}")
    try:
        image = Image.open(full)
        out = []
        for i in range(count):
            top = i * (height + GAP) * 2               # 2x 缩放后要乘 2
            box = (0, top, width * 2, top + height * 2)
            page = os.path.join(out_dir, f"page-{i + 1:02d}.png")
            image.crop(box).save(page)
            out.append(page)
        return out
    except OSError as exc:
        raise SystemExit(f"✗ 裁页失败（{full} 不是可读的 PNG？）：{exc}") from exc
    finally:
        with contextlib.suppress(OSError):
            os.remove(full)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="HTML → 每页 PNG")
    ap.add_argument("html")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--width", type=int, default=1600)
    ap.add_argument("--height", type=int, default=900)
    ap.add_argument("--count", type=int, required=True)
    args = ap.parse_args(argv[1:])
    pages = shoot(args.html, args.out_dir, args.width, args.height, args.count)
    print(f"✓ 截出 {len(pages)} 页：" + ", ".join(os.path.basename(p) for p in pages))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
