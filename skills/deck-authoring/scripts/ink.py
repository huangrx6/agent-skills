#!/usr/bin/env python3
"""墨色推导与对比度门禁 —— token 的**唯一**消费者。

为什么单独一层：原型实测「两墨各自当文字色」对比度不达标（2.35 / 2.68），
而两墨 multiply 的叠印色达标（9.55）。所以文字色不是**选**出来的，是**推导**出来的：
换色板时它自动跟着变，不许手写第二个值。

跑法：python3 ink.py design-tokens.json      # 三组色板逐个校验，任一不达标退出码 1
"""
from __future__ import annotations

import json
import sys


def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#%02X%02X%02X" % rgb


def overprint(primary: str, secondary: str) -> str:
    """两墨叠印色：sRGB 逐通道相乘（打印机混色就是这个含义）。"""
    return _hex(tuple(a * b // 255 for a, b in zip(_rgb(primary), _rgb(secondary))))


def luminance(color: str) -> float:
    channels = []
    for value in _rgb(color):
        x = value / 255
        channels.append(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast(fg: str, bg: str) -> float:
    a, b = luminance(fg), luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def check(tokens: dict) -> int:
    limits = tokens["contrast"]
    print(f"{'色板':<8}{'叠印墨（文字色）':<20}{'对比度':>7}  {'判定':<6}{'主色/副色单独当文字':>22}")
    failed = []
    for name, set_ in tokens["colorSets"].items():
        paper = set_["background"]
        ink = overprint(set_["primary"], set_["secondary"])
        text_ratio = contrast(ink, paper)
        ok = text_ratio >= limits["minBody"]
        if not ok:
            failed.append(name)
        fringe = min(contrast(set_["primary"], paper), contrast(set_["secondary"], paper))
        print(f"{name:<8}{ink:<20}{text_ratio:>7.2f}  {'✓' if ok else '✗ 不达标':<6}"
              f"{fringe:>10.2f} {'（只能做墨层/装饰）':<12}")
    print(f"\n门槛：正文 {limits['minBody']} / 大字（≥{limits['largeTextPx']}px）{limits['minLarge']}")
    if failed:
        print(f"✗ 这些色板的叠印墨色达不到正文门槛：{failed} —— 换色板，不要放宽门槛")
    return 1 if failed else 0


def main(argv: list[str]) -> int:
    path = argv[1] if len(argv) > 1 else "design-tokens.json"
    with open(path, encoding="utf-8") as fh:
        return check(json.load(fh))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
