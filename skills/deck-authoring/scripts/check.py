#!/usr/bin/env python3
"""#76 六项机械校验 —— 只查能机械判定的东西，不承诺审美。

1. 对比度   文字色必须是两墨叠印色（主/副色天生 2.3~3.0，承载不了文字），且按字号分档过门槛
2. 文字溢出 按字宽估算表算文本盒，超出内容区就报
3. 错位区间 从**产物 HTML** 里读实际写进去的 --dx/--dy/--rot，比对 token 区间
4. 装饰不压文字 墨块必须落在安全区，不与文字栏相交
5. 图表成比例 柱高两两之间必须与数据成比例（基准取数据最大那条，不拿图形最高那根）
6. 图表区无错位 图表容器里不许出现 riso 错位元素（错位会毁掉柱与刻度的可读性）

跑法：python3 check.py deck-spec.json out.html      # 全过退出 0，任一不过退出 1
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
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


ink = _load_sibling("ink")

TOKENS = os.path.join(HERE, "..", "styles", "risograph", "style.json")

# **两个不同的框，别混用**（我自己第一版就混了 ✗，导致正常产物被误判"溢出"）：
#   内容区 = 版面减去内边距，量"放不放得下"（宽 1600-2×84 = 1432）
#   文字栏 = 文字实际占的窄带，只用来判"墨块进没进栏"（更保守）
CONTENT = (84.0, 132.0, 1516.0, 838.0)
TEXT_BAND = (84.0, 132.0, 1000.0, 770.0)
SLIDE_W, SLIDE_H = 1600.0, 900.0
CORNER = {  # zone → (右偏移, 下/上偏移, 靠上?)
    "tr": (60.0, 40.0, True), "br": (130.0, 140.0, False),
    "tl": (60.0, 40.0, True), "bl": (130.0, 140.0, False),
}


def text_width(text: str, size: float) -> float:
    """字宽估算：CJK/全角按 1em，ASCII 按 0.55em。是**估算**，不是度量表 ——
    它只为挡住"明显放不下"，精确断行要靠浏览器（这一点写清楚，别让它看起来像精确值）。"""
    wide = sum(1 for ch in text if ord(ch) > 0x2E80)
    return (wide + (len(text) - wide) * 0.55) * size


def check(spec: dict, html_path: str, tokens: dict) -> list[str]:
    problems: list[str] = []
    deck = spec["deck"]
    colors = tokens["colorSets"][deck["colorSet"]]
    paper = colors["background"]
    ink_text = ink.overprint(colors["primary"], colors["secondary"])
    limits = tokens["contrast"]
    x0, y0, x1, y1 = CONTENT
    width = x1 - x0
    bx0, by0, bx1, by1 = TEXT_BAND
    # 每种版式的可用文字宽度**不一样**：图文页左栏 820、双栏每栏 660、时间线每格 300，
    # 其余用满宽。用同一个宽度去判，必然一边误报一边漏报（我踩过一次同类错 ✗）。
    LIMIT = {"title": width, "content-text": width, "end": width,
             "content-image": 820.0, "two-column": 660.0, "timeline": 1320.0, "chart": width}

    # ① 对比度 + ② 文字溢出
    height = 0.0
    for i, slide in enumerate(deck["slides"], 1):
        for key, size, factor in (("title", 152 if slide["type"] == "title" else 86, 1.15),):
            text = slide.get(key, "")
            if not text:
                continue
            w = text_width(text, size)
            limit = LIMIT.get(slide["type"], width)
            if w > limit:
                problems.append(f"第 {i} 页 {key} 估算宽 {w:.0f}px > 该版式上限 {limit:.0f}px（文字溢出）")
            height += size * factor
            ratio = ink.contrast(ink_text, paper)
            floor = limits["minLarge"] if size >= limits["largeTextPx"] else limits["minBody"]
            if ratio < floor:
                problems.append(f"第 {i} 页 {key} 对比度 {ratio:.2f} < {floor}（文字色不达标）")
            declared = slide.get("color")
            if declared and declared != "overprint":
                problems.append(f"第 {i} 页 {key} 声明 color={declared!r} —— 主/副色不能承载文字，只允许 overprint")
        items = list(slide.get("bullets", []))
        items += [b for col in slide.get("columns", []) for b in col.get("bullets", [])]
        items += [n.get("label", "") for n in slide.get("nodes", [])]
        size = 40 if slide["type"] != "two-column" else 30
        for bullet in items:
            w = text_width(bullet, size)
            limit = LIMIT.get(slide["type"], width)
            if w > limit:
                problems.append(f"第 {i} 页条目估算宽 {w:.0f}px > 该版式上限 {limit:.0f}px（文字溢出）")
            height += 40 * 1.85
        height += 64
        if height > y1 - y0:
            problems.append(f"第 {i} 页累计高 {height:.0f}px > 内容区 {y1 - y0:.0f}px（文字溢出）")
        height = 0.0

    # ④ 图表：柱高必须与数据成比例（独立复核，不看渲染器自觉），且图表区不许带错位
    for i, slide in enumerate(deck["slides"], 1):
        if slide.get("type") != "chart":
            continue
        heights = [float(v) for v in re.findall(r'class="bar"[^>]*height="([\d.]+)"', open(html_path, encoding="utf-8").read())]
        values = [float(d["value"]) for d in slide.get("data", [])]
        if len(heights) != len(values):
            problems.append(f"第 {i} 页图表：柱子 {len(heights)} 根 ≠ 数据 {len(values)} 条")
        elif values:
            # **两两比例**判据，不是"对峰值归一"：一旦有一根被改高，峰值基准就跟着错，
            # 于是六根全报（实测过 ✗）—— 那种输出等于没说清是谁错了。
            # 两两比例与基准无关，只会指向真的那一根。
            # 基准取**数据最大**的那条，不是图形最高的那根 —— 拿图形当基准的话，
            # 被篡改的那根一旦成为最高，它自己就被跳过、而无辜的柱子被报（实测过 ✗）。
            base = max(range(len(values)), key=lambda k: values[k])
            for k, (h, v) in enumerate(zip(heights, values)):
                if k == base or not values[base]:
                    continue
                want = heights[base] * v / values[base]
                if abs(h - want) > 1.5:
                    problems.append(f"第 {i} 页图表第 {k + 1} 根柱高 {h:.1f}px 与数据 {v} 不成比例"
                                    f"（按最高那根的长度换算应为 {want:.1f}px）")
    chart_html = open(html_path, encoding="utf-8").read()
    for block in re.findall(r'<div class="chartwrap".*?</div>', chart_html, re.S):
        if "riso" in block:
            problems.append("图表容器里出现了错位叠印元素（riso 只允许做容器与背景，不能进图表区）")

    page = open(html_path, encoding="utf-8").read()

    # ③ 错位区间：读产物里真正写进去的值
    m = tokens["misregistration"]
    for dx, dy, rot in re.findall(r"--dx:([-\d.]+)px;--dy:([-\d.]+)px;--rot:([-\d.]+)deg", page):
        for value, (lo, hi), name in ((float(dx), m["offsetRangeX"], "dx"),
                                      (float(dy), m["offsetRangeY"], "dy"),
                                      (float(rot), m["rotationRange"], "rot")):
            if not (lo <= value <= hi):
                problems.append(f"错位参数 {name}={value} 越出 token 区间 [{lo}, {hi}]")

    # ④ 装饰不压文字
    for zone, size in re.findall(r'data-zone="(\w+)" data-size="(\d+)"', page):
        if zone not in CORNER:
            problems.append(f"未知装饰 zone={zone!r}"); continue
        right_off, top_off, up = CORNER[zone]
        s = float(size)
        left = SLIDE_W + right_off - s if "r" in zone else -right_off
        top = -top_off if up else SLIDE_H + top_off - s
        rect = (left, top, left + s, top + s)
        if not (rect[2] <= bx0 or rect[0] >= bx1 or rect[3] <= by0 or rect[1] >= by1):
            problems.append(f"装饰墨块 zone={zone} 与文字栏相交 rect={tuple(round(v) for v in rect)}"
                            f"（安全区规则：只放右侧两角）")
    return problems


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="deck 产物六项机械校验")
    ap.add_argument("spec")
    ap.add_argument("html")
    ap.add_argument("--tokens", default=TOKENS)
    args = ap.parse_args(argv[1:])
    spec = json.load(open(args.spec, encoding="utf-8"))
    tokens = json.load(open(args.tokens, encoding="utf-8"))
    problems = check(spec, args.html, tokens)
    if problems:
        print(f"✗ {len(problems)} 个问题：")
        for p in problems:
            print("  ·", p)
        return 1
    print("✓ 校验全过（对比度 / 文字溢出 / 错位区间 / 装饰不压文字 / 图表成比例 / 图表区无错位）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
