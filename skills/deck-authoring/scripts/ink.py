#!/usr/bin/env python3
"""墨色推导与对比度门禁 —— token 的**唯一**消费者。

为什么单独一层：文字色是**版面里最容易悄悄出事**的一项 —— 它是唯一一处
“颜色一变、可读性就崩”的地方，而它又分布在每页的每个元素上。所以收成一条门禁。

两种来源都要支持（`text_color`）：
  - **派生**：两墨 multiply 的叠印色（叠印类风格用；原型实测那套主/副色各自当文字色
    只有 2.35 / 2.68，乘起来才 9.55 —— 所以它不是“选”出来的）
  - **声明**：黑底白字、白底黑字这类风格直接写 `colorSets.*.text`（黑不是任何两色的乘积）

跑法：python3 ink.py [styles/swiss-grid/style.json]   # 不传就用仓库那份；任一色板不达标退出码 1
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_sibling(name: str):
    """动态加载同目录脚本（`scripts/` 不是包，同级 import 在静态层面无法解析）。

    把模块注册进 sys.modules 之后再 exec —— 写法沿用 `check_layout.py`。那一步是为
    `@dataclass` / 自引用 import 准备的（dataclasses._is_type 查
    sys.modules.get(cls.__module__)，拿到 None 会炸）。本 skill 的脚本都没有这两样，
    属防御性写法；它**不**负责“同一模块只加载一次”（实测：两次加载是两个对象）。
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{name}.py")
    mod_spec = importlib.util.spec_from_file_location(f"_deck_{name}", path)
    if mod_spec is None or mod_spec.loader is None:
        raise RuntimeError(f"加载不了同目录模块：{path}")
    module = importlib.util.module_from_spec(mod_spec)
    sys.modules[mod_spec.name] = module
    mod_spec.loader.exec_module(module)
    return module


deckio = _load_sibling("deckio")   # IO 收口：读不到就报清楚，不甩 traceback


def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#%02X%02X%02X" % rgb


def overprint(primary: str, secondary: str) -> str:
    """两墨叠印色：sRGB 逐通道相乘（打印机混色就是这个含义）。

    三通道**显式构造**，不用 `tuple(生成器)` —— 后者被推断成 `tuple[int, ...]`，
    而 `_hex` 要的是长度写死的 `tuple[int, int, int]`。
    """
    a, b = _rgb(primary), _rgb(secondary)
    return _hex((a[0] * b[0] // 255, a[1] * b[1] // 255, a[2] * b[2] // 255))


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


def text_color(color_set: dict) -> str:
    """色板的**文字色**：显式声明的优先，否则按叠印推导。

    为什么两种都要：孔版的文字色是**派生**的（两墨相乘就是真实叠印的数学，
    写死反而容易与色板脱钩）；而黑底白字、白底黑字这类风格的文字色是**声明**的
    —— 拿它们的 primary×secondary 去推会得到一个根本不适合当文字的色。
    两种走同一个入口，门槛（对比度）就只需要一条。
    """
    return color_set.get("text") or overprint(color_set["primary"], color_set["secondary"])


def check(tokens: dict) -> int:
    limits = tokens["contrast"]
    print(f"{'色板':<8}{'文字色':<20}{'对比度':>7}  {'判定':<6}{'主色/副色单独当文字':>22}")
    failed = []
    for name, set_ in tokens["colorSets"].items():
        paper = set_["background"]
        ink = text_color(set_)
        text_ratio = contrast(ink, paper)
        ok = text_ratio >= limits["minBody"]
        if not ok:
            failed.append(name)
        fringe = min(contrast(set_["primary"], paper), contrast(set_["secondary"], paper))
        print(f"{name:<8}{ink:<20}{text_ratio:>7.2f}  {'✓' if ok else '✗ 不达标':<6}"
              f"{fringe:>10.2f} {'（只能做墨层/装饰）':<12}")
    print(f"\n门槛：正文 {limits['minBody']} / 大字（≥{limits['largeTextPx']}px）{limits['minLarge']}")
    if failed:
        print(f"✗ 这些色板的文字色达不到正文门槛：{failed} —— 换色板，不要放宽门槛")
    return 1 if failed else 0


def main(argv: list[str]) -> int:
    # 风格 token 必须显式给（夹具已删，没有默认路径）—— 通常是
    # `<deck 项目>/styles/<名>/style.json`。
    if len(argv) <= 1:
        raise SystemExit("✗ 要给风格 token 路径：ink.py styles/<名>/style.json")
    return check(deckio.read_json(argv[1]))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
