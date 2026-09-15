#!/usr/bin/env python3
"""图表引擎：Chart DSL（语义层）→ 确定性 SVG（Web/静态层）。

## 三层分离（规范定的架构，本模块是前两层）

```text
AI 只写 DSL（type / intent / message / data / series / emphasis / annotations）
        ↓
本模块：意图树 + 规则 + 确定性 SVG          ←—— Web/预览/PDF 都用它
        ↓
pptx_native.py：按 type 映射成原生图表       ←—— 可编辑的 PPT 层
```

**为什么 Web 层是手写 SVG 而不是 G2/ECharts** —— 这不是没考虑，是按本仓库的
四条硬约束选的：

1. **零依赖**（仓库的老规矩：GIF 用 Pillow、H.264 用 AVFoundation、截帧用系统
   Chrome）—— G2 minified 几百 KB，要么打进每份产物、要么走 CDN 断网即裂；
2. **自包含产物**（logo base64、字体 @font-face 本地路径）—— JS 依赖会破坏它；
3. **PDF 矢量** —— SVG 直接进 PDF 的文字与形状层；Canvas 出来是位图；
4. **确定性** —— `animate.py` 靠"同一 t 渲出同一帧"做 MP4，手写 SVG 的几何是纯函数。

DSL 的边界设计成**库可替换**：`svg()` 的输入是纯数据 + 颜色 + 字号，哪天要换
G2 渲染器，把这层换成 `g2.js` 生成器即可，DSL 与 PPT 层都不用动。

## 图表不是"选样式"，是"判意图"（规范第 3 条）

意图 → 图形类型的映射是**确定性的**，不交给 AI 随便选：

| 意图 | 图形 | 说明 |
| --- | --- | --- |
| trend 趋势 | line / area | 时间横向展开 |
| ranking 排名 | bar-horizontal | 大的排上面 |
| comparison 比较 | bar | |
| composition 组成 | bar-stacked（≤5 份）/ donut | |
| correlation 相关 | scatter | |
| progress 进度 | donut | 中心放达成率 |
| deviation / distribution | bar（第一版） | 直方图/瀑布是第二阶段 |

没写 `chart` 也没写 `intent` 时，按**数据形状**推：多系列 → line；单系列且标签
像时间（Q1/月份/年份）→ line；否则 bar。推出来的会在 `--explain` 里说明理由。

## 好看的三条硬规则（规范第 4 / 5 条）

1. **muted + 1 accent**：给了 `emphasis` 就只有被强调的那根是 Accent，其余全部
   降成 muted（主色向纸色褪 55%）—— 八根柱子八种颜色是业余的第一特征。
2. **标题必须是结论**：`message` 显示为大标题（titleblock），原来的 `title`
   降为小标签（数据集名）。没写 message 时维持旧行为（title 当标题）。
3. **不画图例、不画坐标轴数字、不画网格线**：数值直接标在图形上（这本来就是
   本仓库的既定风格，PDF/PPTX 两侧都验证过）。

跑法：
    python3 scripts/chart.py --demo bar        # 八类各渲一个样例
    python3 scripts/chart.py --explain spec.json
"""

from __future__ import annotations

import argparse
import html
import importlib.util
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)


def _load_sibling(name: str):
    key = f"_deck_{name}"
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, os.path.join(HERE, f"{name}.py"))
    if spec is None or spec.loader is None:
        raise SystemExit(f"✗ 加载不了 scripts/{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


deckio = _load_sibling("deckio")

# ═══════════════════════════════════════════════════════════════════════════
# 图形类型与意图（规范第 3 / 16 条）—— **第一版就这八类**
# ═══════════════════════════════════════════════════════════════════════════

CHART_TYPES = ("bar", "bar-horizontal", "line", "area", "bar-stacked", "donut",
               "scatter", "combo")

INTENTS = ("trend", "ranking", "comparison", "composition", "correlation",
           "progress", "deviation", "distribution")

INTENT_TO_TYPE = {
    "trend": "line",
    "ranking": "bar-horizontal",
    "comparison": "bar",
    "composition": "donut",
    "correlation": "scatter",
    "progress": "donut",
    "deviation": "bar",
    "distribution": "bar",
}

# 意图的中文名（报错与人读的提示里用）
INTENT_ZH = {
    "trend": "趋势", "ranking": "排名", "comparison": "比较",
    "composition": "组成", "correlation": "相关性", "progress": "进度",
    "deviation": "偏差", "distribution": "分布",
}

# 标签"像时间"的判据：Q1/Q3、2025、1月、W12、Q3'25 ……
_TIME_LABEL = re.compile(
    r"^\s*(\d{4}|[12]\d{3}[./-]\d{1,2}|Q[1-4]\b|W\d{1,2}\b|\d{1,2}\s*月|\d{1,2}\s*月\S*|"
    r"jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|一月|二月|三月|四月|五月|六月|"
    r"七月|八月|九月|十月|十一月|十二月|上年|去年|今年|上月|本月)", re.IGNORECASE)


def looks_temporal(labels: list) -> bool:
    return bool(labels) and sum(1 for x in labels if _TIME_LABEL.match(str(x))) >= max(1, len(labels) // 2)


def infer_chart_type(slide: dict) -> tuple[str, str]:
    """决定这一页用什么图形。返回 (chart 类型, 理由)。

    顺序：显式 `chart` > `intent` 映射 > 按**数据形状**推。理由会写进 `--explain`，
    因为"为什么是这张图"本身是信息（AI 改了意图，图就该跟着换）。
    """
    declared = slide.get("chart")
    if declared:
        if declared not in CHART_TYPES:
            raise SystemExit(f"✗ chart={declared!r} 不在八类里（{list(CHART_TYPES)}）")
        return declared, "spec 里显式写了 chart"
    intent = slide.get("intent")
    if intent:
        if intent not in INTENTS:
            raise SystemExit(f"✗ intent={intent!r} 不认识（{list(INTENTS)}）")
        return INTENT_TO_TYPE[intent], f"intent={intent}（{INTENT_ZH[intent]}）映射"
    # ⚠️ 什么都不写时**缺省是 bar** —— 与历史行为一致，不悄悄改观感。
    #
    # 第一版在这里按数据形状推：标签像时间就给 line。实测后果：压测 deck 的
    # 图表页（标签是 Q1/Q2…）从柱状图静默变成折线图，八套风格全挂 —— 旧 spec
    # 没写 chart/intent，它没同意被改。形状推断只当**建议**（--explain 会说），
    # 不当缺省。要折线就写 intent: trend 或 chart: line。
    series = slide.get("series") or []
    data = slide.get("data") or []
    # 多系列**必须声明**：bar 只画第一系列 —— 猜错就是静默丢数据，那比报错糟。
    # line / area / bar-stacked / combo 都合理，选哪个是表达意图，不是数据形状能定的。
    if series:
        raise SystemExit(
            "✗ 多系列图表需要写 chart 或 intent —— line / area / bar-stacked / combo "
            "都合理，缺省会只画第一系列（静默丢数据）。想看各系列走势就 intent: trend")
    why = "没写 chart 也没写 intent → 缺省 bar（与历史一致）"
    if looks_temporal([d.get("label", "") for d in data]):
        why += "；标签像时间 → 建议 intent: trend（line）"
    return "bar", why


# ═══════════════════════════════════════════════════════════════════════════
# 颜色：muted + 1 accent（规范第 4 条）—— 图表配色从色板推，不自立一套
# ═══════════════════════════════════════════════════════════════════════════


def _hex_mix(a: str, b: str, t: float) -> str:
    """线性混两个 HEX（t=0 是 a，t=1 是 b）。"""
    pa, pb = a.lstrip("#"), b.lstrip("#")
    ea = [int(pa[i:i + 2], 16) for i in (0, 2, 4)]
    eb = [int(pb[i:i + 2], 16) for i in (0, 2, 4)]
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(ea, eb))


def muted(primary: str, background: str) -> str:
    """muted = 主色向纸色褪 55% —— 有色相但退到背景里，让 accent 独占注意力。"""
    return _hex_mix(primary, background, 0.55)


def series_colors(primary: str, background: str, n: int) -> list[str]:
    """多系列用主色的**深浅阶**（不是彩虹）：向纸色分档褪色。"""
    if n <= 1:
        return [primary]
    # 首系列最深、末系列最浅；t 从 0 到 0.62
    return [_hex_mix(primary, background, 0.62 * i / max(1, n - 1)) for i in range(n)]


def emphasis_set(slide: dict) -> set[str]:
    """被强调的标签集合。`emphasis.values` 是标签名列表。"""
    em = slide.get("emphasis") or {}
    return {str(v) for v in em.get("values", [])}


# ═══════════════════════════════════════════════════════════════════════════
# 动画令牌（规范第 6~9 条）—— 数值先成文，接线在第二阶段
#
# 为什么先成文：动画的"高级感"不在效果多，而在**克制且一致**。令牌不先定下来，
# 每张图各写各的 731ms/1247ms，那就是"弹跳杂耍"的来源。每类图形的动画语言：
#   bar → growInY（0 → 实际高度）  bar-horizontal → growInX
#   line/area → pathIn（左到右画出来）  scatter → scale+fade（0.6→1）
#   donut → sweep + 中心数字 fade   axis/grid/label → fade（永远不是主角）
# ═══════════════════════════════════════════════════════════════════════════

MOTION_TOKENS = {
    "duration_fast": 300, "duration_normal": 600, "duration_slow": 1000,
    "stagger_small": 40, "stagger_normal": 80, "stagger_large": 120,
    "chart_enter": 700, "chart_stagger": 60, "highlight": 300,
    "page_total_max": 1500, "story_total_max": 3000,
    "easing_enter": "ease-out", "easing_update": "ease-in-out", "easing_exit": "ease-in",
}


# ═══════════════════════════════════════════════════════════════════════════
# SVG 渲染 —— 八类，共用一张 1100×330 的画布（与既有 .chartwrap 高度钉死配套）
# ═══════════════════════════════════════════════════════════════════════════

W, PLOT_H, BASE = 1100, 250, 286          # 总高 = BASE + 44 = 330
FONT = 'font-family="inherit"'


def _norm_series(slide: dict) -> list[dict]:
    """统一成 [{name, data:[{label,value}]}]。单系列 data 与多系列 series 都收。"""
    series = slide.get("series")
    if series:
        out = []
        for s in series:
            out.append({"name": str(s.get("name", "")), "data": list(s.get("data", []))})
        return out
    return [{"name": "", "data": list(slide.get("data", []))}]


def _values(series: list[dict]) -> list[float]:
    return [d.get("value") for s in series for d in s["data"]
            if isinstance(d.get("value"), (int, float))]


def svg(slide: dict, colors: dict, tag_attr: str = "") -> str:
    """按这一页的 DSL 渲 SVG。几何是纯函数 —— 同输入同输出（MP4 依赖这一点）。"""
    kind, _why = infer_chart_type(slide)
    primary = colors["primary"]
    background = colors["background"]
    text = colors.get("text") or "#0A0A0A"
    muted_c = muted(primary, background)
    emph = emphasis_set(slide)
    unit = slide.get("unit", "")
    head = (f'<svg viewBox="0 0 {W} {BASE + 44}" role="img" data-chart="{kind}" {tag_attr}>')
    body = {"bar": _svg_bar, "bar-horizontal": _svg_hbar, "line": _svg_line,
            "area": _svg_area, "bar-stacked": _svg_stacked, "donut": _svg_donut,
            "scatter": _svg_scatter, "combo": _svg_combo}[kind](
        slide, colors, primary, muted_c, text, emph, unit)
    ann = _svg_annotations(slide, colors, emph, unit)
    return head + body + ann + "</svg>"


def _svg_bar(slide, colors, primary, muted_c, text, emph, unit) -> str:
    """竖柱：柱高与数据成比例是硬要求（check.py 独立复核 `class="bar"` 的 height）。"""
    data = _norm_series(slide)[0]["data"]
    values = [d["value"] for d in data]
    peak = max(values) or 1.0
    slot = W / max(1, len(data))
    bar_w = min(120.0, slot * 0.55)
    out = []
    for k, (d, v) in enumerate(zip(data, values)):
        bh = PLOT_H * (v / peak)
        x = k * slot + (slot - bar_w) / 2
        y = BASE - bh
        fill = primary if (not emph or str(d["label"]) in emph) else muted_c
        out.append(f'<rect class="bar" x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" '
                   f'height="{bh:.1f}" fill="{fill}"/>')
        out.append(f'<text class="val" x="{x + bar_w / 2:.1f}" y="{y - 10:.1f}" '
                   f'text-anchor="middle" fill="{text}">{v}{unit}</text>')
        out.append(f'<text class="lbl" x="{x + bar_w / 2:.1f}" y="{BASE + 26:.1f}" '
                   f'text-anchor="middle" fill="{text}">{html.escape(str(d["label"]))}</text>')
    out.append(f'<line class="axis" x1="0" y1="{BASE}" x2="{W}" y2="{BASE}" '
               f'stroke="{muted_c}" stroke-width="2"/>')
    return "".join(out)


def _svg_hbar(slide, colors, primary, muted_c, text, emph, unit) -> str:
    """横条（排名）：大的在上 —— 读完名字就看到长度，不用回头对数轴。"""
    data = sorted(_norm_series(slide)[0]["data"], key=lambda d: -d.get("value", 0))
    values = [d["value"] for d in data]
    peak = max(values) or 1.0
    left, right = 210, W - 40
    plot_w = right - left
    rows = max(1, len(data))
    row_h = min(52.0, (PLOT_H - 10) / rows)
    bar_h = row_h * 0.62
    out = []
    for k, (d, v) in enumerate(zip(data, values)):
        bw = plot_w * (v / peak)
        y = 12 + k * row_h
        fill = primary if (not emph or str(d["label"]) in emph) else muted_c
        out.append(f'<text class="lbl" x="{left - 14}" y="{y + bar_h / 2 + 6:.1f}" '
                   f'text-anchor="end" fill="{text}">{html.escape(str(d["label"]))}</text>')
        out.append(f'<rect class="bar" x="{left}" y="{y:.1f}" width="{bw:.1f}" '
                   f'height="{bar_h:.1f}" fill="{fill}"/>')
        out.append(f'<text class="val" x="{left + bw + 12:.1f}" y="{y + bar_h / 2 + 6:.1f}" '
                   f'text-anchor="start" fill="{text}">{v}{unit}</text>')
    out.append(f'<line class="axis" x1="{left}" y1="6" x2="{left}" '
               f'y2="{6 + rows * row_h:.1f}" stroke="{muted_c}" stroke-width="2"/>')
    return "".join(out)


def _points(data: list[dict]) -> tuple[float, float]:
    """折线/散点的 (peak, n)。"""
    values = [d.get("value", 0) for d in data]
    return (max(values) or 1.0), len(data)


def _svg_line(slide, colors, primary, muted_c, text, emph, unit) -> str:
    """折线：左到右展开（pathIn 的动画语言）；数值只标 首/尾/峰 三处，避免一排数字。"""
    series = _norm_series(slide)
    left, right, top = 40, W - 40, 26
    all_v = _values(series) or [1]
    peak = max(all_v)
    palette = series_colors(primary, colors["background"], len(series))
    out = []
    for si, s in enumerate(series):
        data = s["data"]
        if not data:
            continue
        n = max(2, len(data))
        pts = []
        for k, d in enumerate(data):
            x = left + (right - left) * k / (n - 1)
            y = BASE - PLOT_H * (d.get("value", 0) / peak)
            pts.append((x, y, d))
        path = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in pts)
        color = palette[si]
        out.append(f'<polyline class="line" points="{path}" fill="none" '
                   f'stroke="{color}" stroke-width="4" stroke-linejoin="round" '
                   f'stroke-linecap="round"/>')
        # 标 首/尾/峰：一排数字会把线埋掉
        marks = {0, len(pts) - 1}
        if pts:
            marks.add(max(range(len(pts)), key=lambda i: pts[i][2].get("value", 0)))
        for i in sorted(marks):
            x, y, d = pts[i]
            big = str(d["label"]) in emph
            r = 7 if big else 5
            out.append(f'<circle class="dot" cx="{x:.1f}" cy="{y:.1f}" r="{r}" '
                       f'fill="{primary if big else color}"/>')
            out.append(f'<text class="val" x="{x:.1f}" y="{y - 14:.1f}" '
                       f'text-anchor="middle" fill="{text}">{d["value"]}{unit}</text>')
        for x, y, d in pts:
            out.append(f'<text class="lbl" x="{x:.1f}" y="{BASE + 26:.1f}" '
                       f'text-anchor="middle" fill="{text}">'
                       f'{html.escape(str(d["label"]))}</text>')
    if len(series) > 1:
        # 多系列：名字直接标在线尾（不画图例 —— 这是既定风格）
        for si, s in enumerate(series):
            if s["data"]:
                last = s["data"][-1]
                x = right + 2
                y = BASE - PLOT_H * (last.get("value", 0) / peak)
                out.append(f'<text class="lbl" x="{x:.0f}" y="{y + 4:.1f}" fill="{palette[si]}">'
                           f'{html.escape(s["name"] or f"S{si + 1}")}</text>')
    out.append(f'<line class="axis" x1="{left}" y1="{BASE}" x2="{right}" y2="{BASE}" '
               f'stroke="{muted_c}" stroke-width="2"/>')
    return "".join(out)


def _svg_area(slide, colors, primary, muted_c, text, emph, unit) -> str:
    """面积 = 折线 + 向基线闭合的淡填充（accent 的 14%，压得住文字）。"""
    line = _svg_line(slide, colors, primary, muted_c, text, emph, unit)
    series = _norm_series(slide)[0]
    data = series["data"]
    if not data:
        return line
    all_v = _values([series]) or [1]
    peak = max(all_v)
    left, right = 40, W - 40
    n = max(2, len(data))
    pts = [(left + (right - left) * k / (n - 1),
            BASE - PLOT_H * (d.get("value", 0) / peak)) for k, d in enumerate(data)]
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    poly += f" {right:.1f},{BASE} {left:.1f},{BASE}"
    return (f'<polygon class="area" points="{poly}" fill="{primary}" opacity="0.14"/>'
            + line)


def _svg_stacked(slide, colors, primary, muted_c, text, emph, unit) -> str:
    """堆叠柱：每系列一档深浅（不是彩虹），段内标系列名、顶上标总量。"""
    series = _norm_series(slide)
    labels = [str(d.get("label", "")) for d in series[0]["data"]] if series else []
    rows = max(1, len(labels))
    palette = series_colors(primary, colors["background"], len(series))
    slot = W / max(1, rows)
    bar_w = min(120.0, slot * 0.55)
    out = []
    totals = [0.0] * rows
    for s in series:
        for i, d in enumerate(s["data"]):
            totals[i] += d.get("value", 0) or 0
    peak = max(totals) or 1.0
    for i, label in enumerate(labels):
        x = i * slot + (slot - bar_w) / 2
        y = BASE
        for si, s in enumerate(series):
            v = s["data"][i].get("value", 0) or 0
            seg_h = PLOT_H * (v / peak)
            y -= seg_h
            out.append(f'<rect class="bar seg" x="{x:.1f}" y="{y:.1f}" '
                       f'width="{bar_w:.1f}" height="{seg_h:.1f}" fill="{palette[si]}"/>')
            if seg_h >= 26 and len(series) <= 4:
                out.append(f'<text class="lbl" x="{x + bar_w / 2:.1f}" y="{y + seg_h / 2 + 5:.1f}" '
                           f'text-anchor="middle" fill="{colors["background"]}">'
                           f'{html.escape(s["name"] or str(v))}</text>')
        out.append(f'<text class="val" x="{x + bar_w / 2:.1f}" y="{y - 10:.1f}" '
                   f'text-anchor="middle" fill="{text}">{totals[i]:g}{unit}</text>')
        out.append(f'<text class="lbl" x="{x + bar_w / 2:.1f}" y="{BASE + 26:.1f}" '
                   f'text-anchor="middle" fill="{text}">{html.escape(label)}</text>')
    out.append(f'<line class="axis" x1="0" y1="{BASE}" x2="{W}" y2="{BASE}" '
               f'stroke="{muted_c}" stroke-width="2"/>')
    return "".join(out)


def _donut_arc(cx: float, cy: float, r: float, a0: float, a1: float) -> str:
    """一段环弧的 path（SVG 弧命令，large-arc 按跨度决定）。"""
    x0, y0 = cx + r * math.cos(a0), cy + r * math.sin(a0)
    x1, y1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
    large = 1 if (a1 - a0) > math.pi else 0
    return (f"M {x0:.1f} {y0:.1f} A {r:.1f} {r:.1f} 0 {large} 1 {x1:.1f} {y1:.1f}")


def _svg_donut(slide, colors, primary, muted_c, text, emph, unit) -> str:
    """环图：进度/组成。中心放**达成率或总量**（那是结论），标签在环外。"""
    data = _norm_series(slide)[0]["data"]
    total = sum(d.get("value", 0) for d in data) or 1.0
    cx, cy, r = W * 0.38, 158, 108
    out = []
    a = -math.pi / 2
    peak_label = None
    if slide.get("intent") == "progress":
        peak_label = f"{data[0]['value']}{unit}" if data else ""
        sub = html.escape(str(data[0].get("label", ""))) if data else ""
    else:
        top = max(data, key=lambda d: d.get("value", 0)) if data else None
        peak_label = f"{top['value']}{unit}" if top else ""
        sub = html.escape(str(top.get("label", ""))) if top else ""
    for d in data:
        v = d.get("value", 0)
        frac = v / total
        a1 = a + frac * 2 * math.pi
        fill = primary if (not emph or str(d["label"]) in emph) else muted_c
        out.append(f'<path class="arc" d="{_donut_arc(cx, cy, r, a, a1)}" fill="none" '
                   f'stroke="{fill}" stroke-width="58" stroke-linecap="butt"/>')
        # 外侧标签（值 + 名）
        mid = (a + a1) / 2
        lx, ly = cx + (r + 52) * math.cos(mid), cy + (r + 52) * math.sin(mid)
        anchor = "start" if math.cos(mid) >= 0 else "end"
        out.append(f'<text class="lbl" x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" '
                   f'fill="{text}">{html.escape(str(d["label"]))} {v}{unit}</text>')
        a = a1
    out.append(f'<text class="val big" x="{cx:.1f}" y="{cy + 4:.1f}" text-anchor="middle" '
               f'fill="{text}" font-size="46" font-weight="700">{peak_label}</text>')
    out.append(f'<text class="lbl" x="{cx:.1f}" y="{cy + 34:.1f}" text-anchor="middle" '
               f'fill="{text}">{sub}</text>')
    return "".join(out)


def _svg_scatter(slide, colors, primary, muted_c, text, emph, unit) -> str:
    """散点：x/y 两个连续量。data 项是 {label, x, y}（value 视同 y，向后兼容）。"""
    data = slide.get("data") or []
    left, right, top = 60, W - 40, 26
    xs = [d.get("x", i) for i, d in enumerate(data)]
    ys = [d.get("value", d.get("y", 0)) for d in data]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    sx = (lambda v: left + (right - left) * ((v - x0) / (x1 - x0) if x1 > x0 else 0.5))
    sy = (lambda v: BASE - PLOT_H * ((v - y0) / (y1 - y0) if y1 > y0 else 0.5))
    out = []
    for d, xv, yv in zip(data, xs, ys):
        px, py = sx(xv), sy(yv)
        big = str(d["label"]) in emph
        fill = primary if (not emph or big) else muted_c
        out.append(f'<circle class="dot" cx="{px:.1f}" cy="{py:.1f}" '
                   f'r="{9 if big else 6}" fill="{fill}"/>')
        out.append(f'<text class="lbl" x="{px:.1f}" y="{py - 14:.1f}" '
                   f'text-anchor="middle" fill="{text}">{html.escape(str(d["label"]))}</text>')
    out.append(f'<line class="axis" x1="{left}" y1="{BASE}" x2="{right}" y2="{BASE}" '
               f'stroke="{muted_c}" stroke-width="2"/>')
    return "".join(out)


def _svg_combo(slide, colors, primary, muted_c, text, emph, unit) -> str:
    """组合：柱（muted，第一系列）+ 线（accent，第二系列）—— 量与率同页。"""
    series = _norm_series(slide)
    if len(series) < 2:
        return _svg_bar(slide, colors, primary, muted_c, text, emph, unit)
    bars, line_s = series[0], series[1]
    left, right = 40, W - 40
    all_v = _values(series) or [1]
    peak = max(all_v)
    data = bars["data"]
    slot = W / max(1, len(data))
    bar_w = min(120.0, slot * 0.55)
    out = []
    for k, d in enumerate(data):
        bh = PLOT_H * (d.get("value", 0) / peak)
        x = k * slot + (slot - bar_w) / 2
        out.append(f'<rect class="bar" x="{x:.1f}" y="{BASE - bh:.1f}" width="{bar_w:.1f}" '
                   f'height="{bh:.1f}" fill="{muted(primary, colors["background"])}"/>')
        out.append(f'<text class="lbl" x="{x + bar_w / 2:.1f}" y="{BASE + 26:.1f}" '
                   f'text-anchor="middle" fill="{text}">{html.escape(str(d["label"]))}</text>')
    n = max(2, len(line_s["data"]))
    pts = []
    for k, d in enumerate(line_s["data"]):
        x = left + (right - left) * k / (n - 1)
        y = BASE - PLOT_H * (d.get("value", 0) / peak)
        pts.append((x, y, d))
    path = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in pts)
    out.append(f'<polyline class="line" points="{path}" fill="none" stroke="{primary}" '
               f'stroke-width="4" stroke-linejoin="round"/>')
    for x, y, d in pts:
        big = str(d["label"]) in emph
        out.append(f'<circle class="dot" cx="{x:.1f}" cy="{y:.1f}" r="{7 if big else 5}" '
                   f'fill="{primary}"/>')
        if big or d is pts[-1][2]:
            out.append(f'<text class="val" x="{x:.1f}" y="{y - 14:.1f}" text-anchor="middle" '
                       f'fill="{text}">{d["value"]}{unit}</text>')
    out.append(f'<line class="axis" x1="0" y1="{BASE}" x2="{W}" y2="{BASE}" '
               f'stroke="{muted_c}" stroke-width="2"/>')
    return "".join(out)


# ═══════════════════════════════════════════════════════════════════════════
# 标注（规范第 12 条）—— 好图表与普通图表的差距多半在这里
# ═══════════════════════════════════════════════════════════════════════════

ANN_TYPES = ("callout", "reference", "peak")


def _svg_annotations(slide: dict, colors: dict, emph: set[str], unit: str) -> str:
    anns = slide.get("annotations") or []
    if not anns:
        return ""
    primary = colors["primary"]
    text = colors.get("text") or "#0A0A0A"
    series = _norm_series(slide)
    data = series[0]["data"]
    all_v = _values(series) or [1]
    peak = max(all_v)
    out = []
    for ann in anns:
        kind = ann.get("type")
        if kind not in ANN_TYPES:
            raise SystemExit(f"✗ annotation.type={kind!r} 不认识（{list(ANN_TYPES)}）")
        if kind == "reference":
            v = ann.get("value")
            if not isinstance(v, (int, float)):
                raise SystemExit("✗ reference 标注需要 value（画在那条水平线上）")
            y = BASE - PLOT_H * (v / peak)
            out.append(f'<line class="ref" x1="0" y1="{y:.1f}" x2="{W}" y2="{y:.1f}" '
                       f'stroke="{primary}" stroke-width="2" stroke-dasharray="7 6" '
                       f'opacity="0.75"/>')
            label = html.escape(str(ann.get("text", f"{v}{unit}")))
            out.append(f'<text class="lbl" x="{W - 6}" y="{y - 8:.1f}" text-anchor="end" '
                       f'fill="{primary}">{label}</text>')
            continue
        # callout / peak 都指向某个标签
        target = ann.get("target") or (max(data, key=lambda d: d.get("value", 0))["label"]
                                       if data and kind == "peak" else None)
        idx = next((i for i, d in enumerate(data) if str(d.get("label")) == str(target)), None)
        if idx is None:
            raise SystemExit(f"✗ 标注的 target={target!r} 在 data 里找不到")
        slot = W / max(1, len(data))
        x = idx * slot + slot / 2
        v = data[idx].get("value", 0)
        y = BASE - PLOT_H * (v / peak)
        txt = html.escape(str(ann.get("text", "")))
        out.append(f'<line class="ann" x1="{x:.1f}" y1="{y - 16:.1f}" x2="{x:.1f}" '
                   f'y2="{y - 44:.1f}" stroke="{primary}" stroke-width="2"/>')
        out.append(f'<text class="annlbl" x="{x:.1f}" y="{y - 52:.1f}" text-anchor="middle" '
                   f'fill="{primary}" font-weight="600">{txt}</text>')
    return "".join(out)


# ═══════════════════════════════════════════════════════════════════════════
# CLI：--demo 渲八类样例；--explain 说清"为什么是这张图"
# ═══════════════════════════════════════════════════════════════════════════

_DEMO = {
    "bar": {"chart": "bar", "data": [
        {"label": "DeepSeek", "value": 86}, {"label": "Qwen", "value": 61},
        {"label": "Llama", "value": 34}, {"label": "GLM", "value": 28}],
        "emphasis": {"values": ["DeepSeek"]}, "unit": "%"},
    "bar-horizontal": {"chart": "bar-horizontal", "data": [
        {"label": "华东", "value": 312}, {"label": "华南", "value": 268},
        {"label": "华北", "value": 201}, {"label": "西南", "value": 96},
        {"label": "东北", "value": 54}]},
    "line": {"chart": "line", "data": [
        {"label": "1月", "value": 22}, {"label": "2月", "value": 28},
        {"label": "3月", "value": 31}, {"label": "4月", "value": 45},
        {"label": "5月", "value": 58}, {"label": "6月", "value": 81}],
        "emphasis": {"values": ["6月"]},
        "annotations": [{"type": "callout", "target": "5月", "text": "开始加速"}]},
    "area": {"chart": "area", "data": [
        {"label": "Q1", "value": 30}, {"label": "Q2", "value": 41},
        {"label": "Q3", "value": 66}, {"label": "Q4", "value": 92}], "unit": "万"},
    "bar-stacked": {"chart": "bar-stacked", "series": [
        {"name": "直连", "data": [{"label": "Q1", "value": 30}, {"label": "Q2", "value": 36},
                                   {"label": "Q3", "value": 44}]},
        {"name": "渠道", "data": [{"label": "Q1", "value": 18}, {"label": "Q2", "value": 22},
                                   {"label": "Q3", "value": 31}]}]},
    "donut": {"chart": "donut", "intent": "progress", "data": [
        {"label": "已完成", "value": 72}, {"label": "剩余", "value": 28}], "unit": "%"},
    "scatter": {"chart": "scatter", "data": [
        {"label": "A", "x": 12, "y": 30}, {"label": "B", "x": 25, "y": 44},
        {"label": "C", "x": 38, "y": 52}, {"label": "D", "x": 51, "y": 78}],
        "emphasis": {"values": ["D"]}},
    "combo": {"chart": "combo", "series": [
        {"name": "调用量", "data": [{"label": "Q1", "value": 40}, {"label": "Q2", "value": 55},
                                     {"label": "Q3", "value": 78}, {"label": "Q4", "value": 96}]},
        {"name": "毛利率", "data": [{"label": "Q1", "value": 30}, {"label": "Q2", "value": 38},
                                     {"label": "Q3", "value": 52}, {"label": "Q4", "value": 61}]}],
        "unit": "%"},
}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="图表引擎：DSL → 确定性 SVG")
    ap.add_argument("--demo", default=None, metavar="TYPE",
                    help=f"渲一个样例（{list(CHART_TYPES)} / all）")
    ap.add_argument("--explain", default=None, metavar="SPEC",
                    help="说明这份 spec 里每张图表为什么用那个图形")
    args = ap.parse_args(argv[1:])

    if args.demo:
        kinds = list(CHART_TYPES) if args.demo == "all" else [args.demo]
        colors = {"primary": "#0033CC", "secondary": "#0A0A0A",
                  "background": "#FFFFFF", "text": "#0A0A0A"}
        for kind in kinds:
            if kind not in _DEMO:
                raise SystemExit(f"✗ 没有 {kind!r} 的样例")
            print(f"<!-- {kind} -->")
            print(svg(_DEMO[kind], colors))
        return 0

    if args.explain:
        spec = deckio.read_json(args.explain)
        for i, slide in enumerate(spec.get("deck", {}).get("slides", []), 1):
            if slide.get("type") != "chart":
                continue
            kind, why = infer_chart_type(slide)
            print(f"第 {i} 页 → {kind}（{why}）")
            if slide.get("message"):
                print(f"        message：{slide['message']}")
            else:
                print("        ⚠️ 没写 message —— 标题会退回数据集名（规范第 5 条："
                      "标题应是结论）")
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
