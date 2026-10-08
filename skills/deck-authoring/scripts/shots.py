#!/usr/bin/env python3
"""HTML → 每页一张 PNG：等待资源就绪，按时间轴逐页捕获完全入场的静帧。

复用 animate.py 的 CDP 会话，不再截超长页面后按固定间距裁切。
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import sys
import tempfile


def _capture_module():
    path = os.path.join(os.path.dirname(__file__), "animate.py")
    spec = importlib.util.spec_from_file_location("_deck_shots_capture", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def shoot(html: str, out_dir: str, width: int, height: int, count: int) -> list[str]:
    """Capture each settled slide, sharing animation's resource-ready CDP path."""
    if not os.path.isfile(os.path.abspath(html)):
        raise SystemExit(f"✗ 读不到产物：{os.path.abspath(html)}")
    if width <= 0 or height <= 0 or count <= 0 or width * 900 != height * 1600:
        raise SystemExit("✗ 截图尺寸必须为正数且为 16:9，count 必须大于零")
    with open(html, encoding="utf-8") as fh:
        source = fh.read()
    marker = "window.__deck_timeline="
    if marker not in source:
        raise SystemExit("✗ 产物没有 deck 时间轴，请先用 render.py 生成 HTML")
    try:
        spans, _ = json.JSONDecoder().raw_decode(source.split(marker, 1)[1])
        if count > len(spans):
            raise SystemExit(f"✗ 请求 {count} 页，但产物只有 {len(spans)} 页")
        times = [s["start"] + s["enter"] + min(s["hold"] / 2, .1) for s in spans[:count]]
    except (ValueError, KeyError, TypeError) as exc:
        raise SystemExit(f"✗ deck 时间轴无效：{exc}") from exc
    capture = _capture_module()
    if capture._ws_connect() is None:
        raise SystemExit("✗ 截图需要 websockets，以等待字体、图片和图表就绪；请安装 requirements.txt")
    # Keep partial captures out of the delivery folder when resource validation fails.
    with tempfile.TemporaryDirectory(prefix="deck-shots-") as work:
        frames = asyncio.run(capture._capture_async(html, work, times, width * 2 / 1600))
        os.makedirs(out_dir, exist_ok=True)
        out = []
        for i, frame in enumerate(frames, 1):
            target = os.path.join(out_dir, f"page-{i:02d}.png")
            os.replace(frame, target)
            out.append(target)
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
