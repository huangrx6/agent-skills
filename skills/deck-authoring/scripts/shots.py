#!/usr/bin/env python3
"""整页 HTML → 每页一张 PNG：用系统 Chrome 截图，再按固定几何裁开。

不装 Playwright：macOS 上一定有 Chrome，`--headless=new --screenshot` 就够。
"""
from __future__ import annotations

import argparse
import glob
import os
import subprocess
import sys

from PIL import Image

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
GAP = 36          # 页间距，和 render_deck.py 的 CSS 一致


def shoot(html: str, out_dir: str, width: int, height: int, count: int) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    full = os.path.join(out_dir, "_full.png")
    total = height * count + GAP * (count - 1)
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    "--force-device-scale-factor=2",      # 2x：投影/打印不糊
                    f"--screenshot={full}", f"--window-size={width},{total}",
                    f"file://{os.path.abspath(html)}"], check=True, capture_output=True)
    image = Image.open(full)
    out = []
    for i in range(count):
        top = i * (height + GAP) * 2                     # 2x 缩放后要乘 2
        box = (0, top, width * 2, top + height * 2)
        page = os.path.join(out_dir, f"page-{i + 1:02d}.png")
        image.crop(box).save(page)
        out.append(page)
    os.remove(full)
    return out


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
