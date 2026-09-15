#!/usr/bin/env python3
"""#76 产物校验 —— 只查能机械判定的东西，不承诺审美。

分两类（这个区分很重要，照仓库既有做法，同 `check_pointers.py` 的 broken / suspect）：

**阻塞**（`check()`）：
1. 对比度     文字色必须是两墨叠印色（主/副色天生 2.3~3.0，承载不了文字），且分档过门槛
2. 版面越界   **实测**：元素盒子越出**它所在那一页**的边界（`.slide` 是 overflow:hidden）
3. 容器裁切   **实测**：元素**自己会裁**（overflow 不是 visible）且 scroll 大于 client
4. 产物健康   **实测**：图片没加载 / 产物里的脚本报错
5. 错位区间   从**产物 HTML** 里读实际写进去的 --dx/--dy/--rot，比对 token 区间
6. 装饰不压文字 墨块必须落在安全区，不与文字栏相交
7. 图表成比例 柱高两两之间必须与数据成比例（基准取数据最大那条，不拿图形最高那根）
8. 图表区无错位 图表容器（逐层配对地扫完整个容器）里不许出现 riso 错位元素

**提示**（`advisories()`，不阻塞）：字体回退 —— 启发式，衬线撞衬线会误报。

2~4 条的数字来自 `measure.py`（真浏览器实测），**不是估算**：原先用
`text_width()` 估宽，对同一行汉字能差 2 倍多，而且偏差随字体/字距/折行变。

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
deckio = _load_sibling("deckio")   # IO 收口：读不到产物要报清楚，不甩 traceback
measure_mod = _load_sibling("measure")   # 实测层：版面判断全部走它，不估算

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


def _div_subtree(html: str, start: int) -> str:
    """从 `start` 处的 `<div` 开始，逐层配对，返回那个 div 的整段 HTML。

    为什么不用 `.*?</div>`：那是**非贪婪**的，遇到容器里第一个 `</div>` 就停。
    图表容器里有 `.hf` 那一层，于是正则实际只扫了最外面一层 —— 把 riso 塞到
    更深处（比如 svg 区域里）旧写法直接放行。这是真实漏报，不是杞人忧天。
    """
    depth = 0
    i = start
    while i < len(html):
        nxt_open = html.find("<div", i)
        nxt_close = html.find("</div>", i)
        if nxt_close == -1:
            return html[start:]
        if nxt_open != -1 and nxt_open < nxt_close:
            depth += 1
            i = nxt_open + 4
        else:
            depth -= 1
            i = nxt_close + 6
            if depth == 0:
                return html[start:i]
    return html[start:]


def _num(raw: str, where: str, problems: list[str]) -> float | None:
    """转 float；转不了就**报成问题**，不抛异常。

    `check()` 是库函数，契约是「返回问题清单」，不是「甩 traceback」。而且产物里
    的数字读不出来本身就是一种产物损坏 —— 应该被报出来，而不是静默跳过或炸掉。
    """
    try:
        return float(raw)
    except ValueError:
        problems.append(f"{where} 不是合法数字：{raw!r}（产物损坏？）")
        return None


def _check_layout(measured: dict) -> list[str]:
    """② 版面越界 / 容器裁切 —— 全部来自**真浏览器实测**，不是估算。

    为什么必须实测：原先靠 `text_width()` 估算（CJK 1em / ASCII 0.55em），对同一行
    12 个汉字标题，估算给 1032px、真渲出来是 2124px —— **低估 2 倍多**，于是
    end 页（180px 字号）越出版面 612px、被 `overflow:hidden` 静静裁掉，而校验说"全过"。

    两条判据（都是"已经发生的事"，不是推测）：
    甲・越出版面：`.slide` 是 overflow:hidden，元素盒子出去就是被裁。
    乙・容器内裁切：元素自己会裁（overflow 不是 visible）且 scrollW/H > clientW/H。

    ⚠️ 比的是**该元素所在那一页**的盒子，不是全局 1600×900 —— 产物是竖向堆叠的多页，
    第 2 页的元素 y 本来就在 900 以下；拿全局边界比会把后面每页都误报（实测踩过）。

    注意：装饰墨块**故意**溢出到版面外（right:-60px），但它们没有 `data-m`、
    不进这份清单，所以不会误报。
    """
    out: list[str] = []
    slides = measured.get("slides") or []
    for el in measured.get("elements", []):
        if not el.get("visible", True):
            continue
        mid = el.get("id", "?")
        role = el.get("role") or "元素"
        x, y, w, h = el["x"], el["y"], el["w"], el["h"]
        # 元素属于清单里的哪一页（1-based）→ 取那一页的盒子
        idx = el.get("slide")
        if isinstance(idx, int) and 1 <= idx <= len(slides):
            sl = slides[idx - 1]
            sx, sy, sw, sh = sl["x"], sl["y"], sl["w"], sl["h"]
        else:
            sx, sy, sw, sh = 0.0, 0.0, SLIDE_W, SLIDE_H
        right, bottom = x + w, y + h
        box_r, box_b = sx + sw, sy + sh
        overs = []
        if right - box_r > 1:
            overs.append(f"右缘 {right:.0f}px 越出该页右边界 {box_r:.0f}px（超出 {right - box_r:.0f}px）")
        if bottom - box_b > 1:
            overs.append(f"下缘 {bottom:.0f}px 越出该页下边界 {box_b:.0f}px（超出 {bottom - box_b:.0f}px）")
        if x < sx - 1:
            overs.append(f"左缘 {x:.0f}px 越出该页左边界 {sx:.0f}px")
        if y < sy - 1:
            overs.append(f"上缘 {y:.0f}px 越出该页上边界 {sy:.0f}px")
        if overs:
            out.append(f"{mid}（{role}）越出版面：" + "；".join(overs)
                       + " —— 该页是 overflow:hidden，会被裁掉")
            continue
        if el.get("text"):
            pass
        # 容器内裁切：**只有元素自己会裁**（overflow 不是 visible）时才算数。
        # `.foot` 这种 overflow:visible 的，scrollHeight 比 clientHeight 大 2px 是
        # 行高与字面度的正常差 —— 没被裁，报它就是误报（实测踩过）。
        clips = el.get("overflow") not in (None, "visible")
        if clips and (el["scrollW"] - el["clientW"] > 1 or el["scrollH"] - el["clientH"] > 1):
            out.append(f"{mid}（{role}）内容被容器裁切："
                       f"scroll {el['scrollW']}×{el['scrollH']} > client {el['clientW']}×{el['clientH']}")
    return out


def _check_measured_health(measured: dict) -> list[str]:
    """产物健康度：页面报错 / 图片没加载 —— 这两类以前根本没人看。"""
    out: list[str] = []
    for err in measured.get("errors", []):
        out.append(f"产物里的脚本报错：{err}")
    for im in measured.get("images", []):
        if not (im.get("complete") and im.get("naturalW")):
            out.append(f"图片没加载：{im.get('src')!r} —— "
                       f"相对路径的产物挪个目录就会全员裂图（交付前要么同目录交付，要么 base64 内嵌）")
    return out


def _check_font_fallback(measured: dict) -> list[str]:
    """字体回退**提示**（不判失败）—— 而且要说清楚**谁顶上了**。

    启发式：拿一个一定不存在的族当基准比宽度，宽度一样 = 那个族没生效。
    通用族（serif / monospace）排除 —— 它们不是字体而是**回退目标**，不排会误报“缺失”。
    即便如此仍可能误报（衬线撞衬线），所以只提示。

    只跟**有文字的元素**的栈算（探针已经滤掉无文字的，见 `measure.py`）。
    早先按全部元素统计，结果报了 `<figure>` 的 'PingFang SC' —— 那是 Chrome 给 CJK 的
     UA 默认值，而那个元素不渲染任何字形（实测踩过）。
    """
    fonts = measured.get("fonts", {})
    out: list[str] = []
    for stack in measured.get("stacks", []):
        first = stack[0] if stack else None
        if not first or fonts.get(first, {}).get("available"):
            continue                       # 首选能用，没有回退
        winner = next((f for f in stack if fonts.get(f, {}).get("available")), None)
        tail = (f"，实际用的是 {winner!r}" if winner
                else "，栈里没有一个可用 —— 会落到系统默认")
        out.append(f"字体回退（启发式提示）：声明的 {first!r} 在本机不可用{tail}"
                   f" —— 排版会随机器变，交付前确认一下")
    return out


def check(spec: dict, html_path: str, tokens: dict,
          measured: dict | None = None) -> list[str]:
    problems: list[str] = []
    page = deckio.read_text(html_path)      # 读一次就够（以前读了三次）
    deck = spec["deck"]
    colors = tokens["colorSets"][deck["colorSet"]]
    paper = colors["background"]
    ink_text = ink.overprint(colors["primary"], colors["secondary"])
    limits = tokens["contrast"]
    # 文字栏（判"墨块进没进栏"用；版面越界那一套已经改成实测了，不再靠推算）
    bx0, by0, bx1, by1 = TEXT_BAND

    # ① 对比度（解析式：叠印色相对纸色）—— 这条不需要测量，色值是推导出来的
    ratio = ink.contrast(ink_text, paper)
    if ratio < limits["minBody"]:
        problems.append(f"叠印墨对比度 {ratio:.2f} < {limits['minBody']}（文字色不达标）")

    # ② 版面越界 / 容器裁切 —— **实测**（不估）；同时看产物健康度
    data: dict = measure_mod.measure(html_path) if measured is None else measured
    problems.extend(_check_layout(data))
    problems.extend(_check_measured_health(data))

    for i, slide in enumerate(deck["slides"], 1):
        declared = slide.get("color")
        if declared and declared != "overprint":
            problems.append(f"第 {i} 页 声明 color={declared!r} —— 主/副色不能承载文字，只允许 overprint")

    # ④ 图表：柱高必须与数据成比例（独立复核，不看渲染器自觉），且图表区不许带错位
    for i, slide in enumerate(deck["slides"], 1):
        if slide.get("type") != "chart":
            continue
        heights: list[float] = []
        for raw in re.findall(r'class="bar"[^>]*height="([^"]+)"', page):
            num = _num(raw, f"第 {i} 页图表柱高", problems)
            if num is not None:
                heights.append(num)
        values: list[float] = []
        for k, d in enumerate(slide.get("data", [])):
            num = _num(str(d.get("value")), f"第 {i} 页图表 data[{k}].value", problems)
            if num is not None:
                values.append(num)
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
    # ④ 图表区无错位：**逐层配对**扫整个容器，不是扫到第一个 </div> 就停。
    for hit in re.finditer(r'<div class="chartwrap"', page):
        block = _div_subtree(page, hit.start())
        if "riso" in block:
            problems.append("图表容器里出现了错位叠印元素（riso 只允许做容器与背景，不能进图表区）")

    # ③ 错位区间：读产物里真正写进去的值
    m = tokens["misregistration"]
    for dx, dy, rot in re.findall(r"--dx:([-\d.]+)px;--dy:([-\d.]+)px;--rot:([-\d.]+)deg", page):
        for raw, (lo, hi), name in ((dx, m["offsetRangeX"], "dx"),
                                    (dy, m["offsetRangeY"], "dy"),
                                    (rot, m["rotationRange"], "rot")):
            value = _num(raw, f"错位参数 {name}", problems)
            if value is None:
                continue
            if not (lo <= value <= hi):
                problems.append(f"错位参数 {name}={value} 越出 token 区间 [{lo}, {hi}]")

    # ④ 装饰不压文字
    for zone, raw_size in re.findall(r'data-zone="(\w+)" data-size="([^"]*)"', page):
        if zone not in CORNER:
            problems.append(f"未知装饰 zone={zone!r}")
            continue
        right_off, top_off, up = CORNER[zone]
        s = _num(raw_size, f"装饰墨块 zone={zone} 的 data-size", problems)
        if s is None:
            continue
        left = SLIDE_W + right_off - s if "r" in zone else -right_off
        top = -top_off if up else SLIDE_H + top_off - s
        rect = (left, top, left + s, top + s)
        if not (rect[2] <= bx0 or rect[0] >= bx1 or rect[3] <= by0 or rect[1] >= by1):
            problems.append(f"装饰墨块 zone={zone} 与文字栏相交 rect={tuple(round(v) for v in rect)}"
                            f"（安全区规则：只放右侧两角）")
    return problems


def advisories(measured: dict) -> list[str]:
    """**不阻塞**的提示。

    与 `check()` 的分工照仓库既有做法（同 `check_pointers.py` 的 broken / suspect）：
    能确定性判定的才阻塞；启发式的只提示。字体那条是启发式 —— 拿一个一定不存在的
    族当基准比宽度，衬线撞衬线时可能误报，拿它挡交付会把人逼到忽略整个检查。
    """
    return _check_font_fallback(measured)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="deck 产物校验（版面靠真浏览器实测）")
    ap.add_argument("spec")
    ap.add_argument("html")
    ap.add_argument("--tokens", default=TOKENS)
    args = ap.parse_args(argv[1:])
    spec = deckio.read_json(args.spec)
    tokens = deckio.read_json(args.tokens)
    measured = measure_mod.measure(args.html)      # 只量一次，校验与提示共用
    problems = check(spec, args.html, tokens, measured=measured)
    if problems:
        print(f"✗ {len(problems)} 个问题：")
        for p in problems:
            print("  ·", p)
        for n in advisories(measured):
            print("  ·", n)
        return 1
    print("✓ 校验全过（对比度 / 版面越界与裁切 / 错位区间 / 装饰不压文字 / "
          "图表成比例 / 图表区无错位 / 图片加载 / 页面报错）")
    for n in advisories(measured):
        print("  ·", n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
