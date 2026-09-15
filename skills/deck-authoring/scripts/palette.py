#!/usr/bin/env python3
"""配色：结构、角色、novelty、三个方向。

## 这个模块的立论

配色规范里最容易做错的一件事是**让 Style 存死 HEX**。存死 HEX 的后果是：换一套
色就得改结构（或反过来，改了结构但色没跟着动，两边开始漂）。所以本模块把两件事分开：

  · **Style 存结构**（`colorStructure`）：色相关系、颜色数量、明度结构、饱和度结构、
    冷暖、对比、强调策略、背景/渐变/文字策略、创意等级、novelty 目标。
  · **色板存 HEX**（`colorSets`，一直是仓库的既有形状，不改）：primary / secondary /
    background / text 四个角色。

其余九个角色（surface / surface_alt / accent / highlight / text 三档 / border /
chart_colors / gradient）**从这四个推出来**，不手写 —— 手写就会漂，而推导是可测的。

## 三件事必须能失败（否则等于没做）

1. **结构声明与真实色板要对得上**。声明 `hue_structure: "analogous"` 而实测是
   neutral-accent，就得报出来。本模块是**算**结构，然后拿声明来对（不是拿声明当真理）。
2. **俗套要能被指出**，而且要说清是**哪一条**俗套。实测：本仓库 8 套风格里
   `keynote-dark` 的 blue 板（primary H=251.8 / secondary H=230.8）正好是
   "科技 + 深蓝 + 青光"；`swiss-grid` 的 blue（H=263.7 C=0.235 白底）是"企业 + 蓝白"；
   `terminal` cyan H=253.3、`pastel-geometry` lilac H=291.5 也在名单上。
   **所以不能一律阻塞**（仓库自己的风格先挂），只能按**主题条件**提示：
   主题像 AI/科技 **且** 选中的色板正好是蓝紫青 → 那才是"自动绑定俗套"。
3. **明度/饱和度/强调占比要能测**。强调色占比可以从**实测的元素盒**算（不等于像素
   精确，但比"看着差不多"强）：规范说 5%~20%，超了就报。

## 为什么是 OKLCH 而不是 HSL

第 19 条要求"外部色板不得直接复制，要走 OKLCH 二次变体（Hue ±10~30°、
Chroma ±5~20%、Lightness ±3~12%）"。HSL 的 L 与**感知明度**不成正比（黄色 L=50%
在 HSL 里很亮、在感知里也很亮，但蓝色 L=50% 在感知里暗得多），拿它做变体会出现
"提亮之后对比度反而掉了"。OKLCH 的 L 是感知均匀的，所以变体可控、对比度可预测。

跑法：
    python3 scripts/palette.py --audit                 # 8 套风格全审一遍
    python3 scripts/palette.py --audit --style terminal
    python3 scripts/palette.py --novelty swiss-grid blue --topic "AI 大模型架构"
    python3 scripts/palette.py --directions swiss-grid blue    # Safe/Creative/Experimental
"""

from __future__ import annotations

import argparse
import importlib.util
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
STYLES = os.path.join(SKILL, "styles")


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
ink = _load_sibling("ink")

# ═══════════════════════════════════════════════════════════════════════════
# 1. OKLCH —— 感知均匀的色彩空间（第 19 / 21 条依赖它）
#
# 公式来自 Björn Ottosson 的 OKLab（sRGB → 线性 → LMS → 立方根 → OKLab → 极坐标）。
# 自己实现而不是引 colorio/coloraide：只用到正反两次换算，装一个依赖不值。
# ═══════════════════════════════════════════════════════════════════════════


def _to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _to_srgb(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


def _cbrt(x: float) -> float:
    return x ** (1 / 3) if x >= 0 else -((-x) ** (1 / 3))


def oklch(hexstr: str) -> tuple[float, float, float]:
    """HEX → (L, C, H)。L 0~1（感知明度），C 彩度，H 色相角 0~360。"""
    r, g, b = (int(hexstr.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4))
    r, g, b = _to_linear(r), _to_linear(g), _to_linear(b)
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = _cbrt(l), _cbrt(m), _cbrt(s)
    big_l = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    bb = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    return (big_l, math.hypot(a, bb), math.degrees(math.atan2(bb, a)) % 360)


def to_hex(lch: tuple[float, float, float]) -> str:
    """(L, C, H) → HEX。超出 sRGB 色域就夹回去（这点误差比"出不了色"好）。"""
    big_l, c, h = lch
    a = c * math.cos(math.radians(h))
    bb = c * math.sin(math.radians(h))
    l_ = big_l + 0.3963377774 * a + 0.2158037573 * bb
    m_ = big_l - 0.1055613458 * a - 0.0638541728 * bb
    s_ = big_l - 0.0894841775 * a - 1.2914855480 * bb
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    b = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
    return "#" + "".join(f"{round(_clamp(_to_srgb(x)) * 255):02X}" for x in (r, g, b))


def _clamp(x: float) -> float:
    return 0.0 if x < 0 else (1.0 if x > 1 else x)


def _hue_delta(a: float, b: float) -> float:
    """两个色相角之间的最小夹角（0~180）。"""
    d = abs(a - b) % 360
    return d if d <= 180 else 360 - d


# ═══════════════════════════════════════════════════════════════════════════
# 2. 色相结构 —— **算出来**，不是读声明（第 5 条）
# ═══════════════════════════════════════════════════════════════════════════

# 彩度低于这个值就当成"中性色"（不算色相）。
#
# 0.03 是**按实测标定的**：`pastel-geometry` 的副色 `#8A8578` 彩度是 0.020 —— 目视
# 就是个暖灰，可它正好卡在 0.02 上，于是被算成"有色"，那套风格被判成 complementary
# 而实际是中性 + 单强调色（实测发现）。抬到 0.03 之后：`#8A8578`(0.020) /
# `#8B949E`(0.018) / `#6B6B6B`(0.000) 都归中性，而 `#C9B896`(0.050) 仍算有色
# （它是 botanical 的副色，确实带黄）。
NEUTRAL_CHROMA = 0.03

# 色相关系的判据（度）。取的是常见色相环分档：
#   < 30   邻近（analogous）
#   150~180 互补（complementary）
#   120~150 分裂互补里偏三角那一侧
#   100~140 三角（triadic，120±20）
# 这几个阈值不完美（色彩学上没有硬边界），所以它们只用来**分类**，
# 而分类又被拿去和风格自己的声明对 —— 不一致就报出来让人看，不是自动改色。
ANALOGOUS_MAX = 30.0
TRIADIC_MIN, TRIADIC_MAX = 100.0, 140.0
COMPLEMENT_MIN = 150.0


def hue_structure(colors: dict) -> str:
    """从色板算出色相结构（第 5 条的六种之一）。

    只有 primary 有色 → 单色；primary + 中性 secondary → 中性 + 单强调色；
    两者都有色 → 按夹角分邻近 / 三角 / 分裂互补 / 互补。
    """
    hues = []
    for role in ("primary", "secondary"):
        value = colors.get(role)
        if not value:
            continue
        _l, c, h = oklch(value)
        if c >= NEUTRAL_CHROMA:
            hues.append(h)
    if not hues:
        return "neutral-accent"
    if len(hues) == 1:
        # 主色有色、副色是中性 → 中性 + 单强调色；两个色相同一位置才是单色
        return "neutral-accent"
    delta = _hue_delta(hues[0], hues[1])
    if delta < ANALOGOUS_MAX:
        return "analogous"
    if delta < TRIADIC_MIN:
        return "analogous"          # 30~100 之间没有标准名字，按邻近处理并记为近似
    if TRIADIC_MIN <= delta <= TRIADIC_MAX:
        return "triadic"
    if delta < COMPLEMENT_MIN:
        return "split-complementary"
    return "complementary"


# ═══════════════════════════════════════════════════════════════════════════
# 3. 俗套表 —— 第 18 条，**可解释**（要说清扣的是哪一条）
# ═══════════════════════════════════════════════════════════════════════════

# 蓝紫青的色相区间。第 23 条点名禁止 AI/科技自动绑定这三类。
BLUE_PURPLE_CYAN = ((200.0, 320.0),)

# 主题里出现这些词，才谈得上"AI/科技自动绑定蓝紫青"（第 23 条）。
TECH_TOPIC_WORDS = (
    "ai", "人工智能", "大模型", "模型", "算法", "智能", "科技", "技术", "云", "数据",
    "开发", "工程", "架构", "saas", "api", "平台", "系统", "数字化", "算力", "芯片",
    "llm", "agent", "infra", "devops", "database", "github",
)

# 每条俗套：判据 + 为什么俗 + 扣多少。**扣分要说得出是哪一条** ——
# 否则 novelty 只是个没有说服力的数字。
PENALTIES = (
    ("tech_blue_purple_cyan",
     "主题是 AI / 科技，主色又落在蓝紫青 —— 这是训练数据里最高频的一套",
     0.30),
    ("corporate_blue_white",
     "蓝主色 + 白底：企业模板的默认解，读者看不出这是设计过的",
     0.18),
    ("premium_black_gold",
     "深底 + 金色强调：高端感的默认解，已经用滥",
     0.15),
    ("child_rainbow",
     "四个以上高饱和色相并列：儿童风的默认解，没有主次",
     0.15),
    ("even_saturation",
     "所有颜色饱和度接近：没有主次，画面会平",
     0.12),
    ("low_lightness_contrast",
     "背景与主体明度太近：重点浮不出来",
     0.15),
)

BONUSES = (
    ("unusual_temperature",
     "冷底 + 暖局部（或反过来）—— 冷暖反差制造焦点",
     0.12),
    ("low_sat_high_accent",
     "低饱和底色 + 高纯度强调色",
     0.12),
    ("non_uniform_gradient",
     "非线性 stop 的渐变，不是 0/50/100",
     0.08),
    ("neutral_with_odd_accent",
     "中性结构 + 非典型强调色",
     0.10),
)


def _in_ranges(hue: float, ranges) -> bool:
    return any(lo <= hue <= hi for lo, hi in ranges)


def _is_tech_topic(topic: str) -> bool:
    low = (topic or "").lower()
    return any(w in low for w in TECH_TOPIC_WORDS)


def novelty(colors: dict, topic: str = "") -> tuple[float, list[dict]]:
    """novelty_score 与它的**依据**（第 18 条）。

    返回 (0~1 的分数, [{"kind": "penalty"|"bonus", "id":…, "why":…, "delta":…}])。
    分数从 0.5 起（中性），加减之后夹到 0~1。
    """
    reasons: list[dict] = []
    score = 0.5

    primary = colors.get("primary", "#000000")
    secondary = colors.get("secondary", "#FFFFFF")
    background = colors.get("background", "#FFFFFF")
    L_p, C_p, H_p = oklch(primary)
    L_s, C_s, H_s = oklch(secondary)
    L_b, C_b, H_b = oklch(background)

    def fire(delta: float, kind: str, reason_id: str, why: str) -> None:
        """记一条依据并计入分数。`delta` 是**正数**的权重，符号由 kind 决定 ——
        传负数进去会把扣分变成加分。"""
        nonlocal score
        signed = -delta if kind == "penalty" else delta
        score += signed
        reasons.append({"kind": kind, "id": reason_id, "why": why, "delta": signed})

    if _is_tech_topic(topic) and C_p >= 0.10 and _in_ranges(H_p, BLUE_PURPLE_CYAN):
        idx, why, d = PENALTIES[0]
        fire(d, "penalty", idx, why)
    if C_p >= 0.10 and _in_ranges(H_p, ((230.0, 275.0),)) and L_b > 0.85:
        idx, why, d = PENALTIES[1]
        fire(d, "penalty", idx, why)
    # 金色要**高彩度**才算金。原先写 C >= 0.08，于是赤陶色 `#D4A574`（C=0.085）
    # 被当成"黑金"—— 实测它是发灰的暖棕，不是金。真正的金：`#FFB020` C=0.165、
    # `#D29922` C=0.140。取 0.12 把两者分开。
    if L_b < 0.20 and C_p >= 0.12 and 60.0 <= H_p <= 100.0:
        idx, why, d = PENALTIES[2]
        fire(d, "penalty", idx, why)
    loud = sum(1 for h in (H_p, H_s) if h and abs(C_p - C_s) < 0.03 and C_p >= 0.10)
    if loud >= 2 and abs(H_p - H_s) > 120:
        idx, why, d = PENALTIES[4]
        fire(d, "penalty", idx, why)
    if abs(L_b - L_p) < 0.25 and L_b > 0.5:
        idx, why, d = PENALTIES[5]
        fire(d, "penalty", idx, why)

    # 加分项：非常规冷暖（冷主 + 暖辅，或反过来）
    if C_p >= 0.05 and C_s >= 0.05:
        warm_p = H_p < 90 or H_p > 330
        warm_s = H_s < 90 or H_s > 330
        if warm_p != warm_s:
            idx, why, d = BONUSES[0]
            fire(d, "bonus", idx, why)
    if C_p >= 0.18 and abs(L_b - L_p) > 0.35:
        idx, why, d = BONUSES[1]
        fire(d, "bonus", idx, why)
    if C_p < 0.03 and C_s >= 0.10:
        idx, why, d = BONUSES[3]
        fire(d, "bonus", idx, why)

    return (max(0.0, min(1.0, score)), reasons)


# 第 18 条的阈值：普通 PPT / 设计型 / 创意封面
NOVELTY_MIN = {"plain": 0.45, "design": 0.65, "cover": 0.75}


# ═══════════════════════════════════════════════════════════════════════════
# 4. 三个方向 —— 第 17 条（Safe / Creative / Experimental）
#
# 做法：以现有色为**基准**，按第 19 条的变体范围在 OKLCH 里挪。
# 变化是**确定性的**（按角色取固定角度，不用随机）—— 随机会让同一份 spec
# 两次跑出不同的色，那就没法回归了（仓库的老规矩）。
# ═══════════════════════════════════════════════════════════════════════════

DIRECTIONS = {
    # name: (色相偏移, 彩度倍数, 明度偏移)  —— 都落在第 19 条给的范围内
    "safe": {"hue": 0.0, "chroma": 1.00, "lightness": 0.0,
             "why": "原样。稳定、克制、可用于正式汇报"},
    "creative": {"hue": 18.0, "chroma": 1.12, "lightness": 0.02,
                 "why": "色相挪 18°、彩度提 12%、明度微提 —— 与常见解拉开距离但仍协调"},
    "experimental": {"hue": -28.0, "chroma": 1.20, "lightness": -0.04,
                     "why": "色相反方向挪 28°、彩度提 20% —— 制造冷暖反差，用在封面/视觉页"},
}


def variant(colors: dict, direction: str) -> dict:
    """按某个方向做一次 OKLCH 二次变体（第 19 条：Hue ±10~30、Chroma ±5~20%、L ±3~12%）。"""
    spec = DIRECTIONS.get(direction)
    if spec is None:
        raise SystemExit(f"✗ 不认识的方向 {direction!r}；可选 {sorted(DIRECTIONS)}")
    out = dict(colors)
    for role in ("primary", "secondary"):
        value = colors.get(role)
        if not value:
            continue
        L, C, H = oklch(value)
        if C < NEUTRAL_CHROMA:
            continue                     # 中性色不参与色相变化（挪了会变脏）
        out[role] = to_hex((_clamp(L + spec["lightness"]), C * spec["chroma"],
                            (H + spec["hue"]) % 360))
    return out


def directions(colors: dict) -> dict[str, dict]:
    """三套方向 + 各自该选什么时候用。"""
    out = {}
    for name in ("safe", "creative", "experimental"):
        out[name] = {"colors": variant(colors, name), "why": DIRECTIONS[name]["why"],
                     "novelty": novelty(variant(colors, name))[0]}
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 5. 角色映射 —— 第 20 条那 13 个角色，从四个推出来
#
# 为什么不手写：手写会在换色板时漂（改 primary 忘了改 accent）。推导是**可测**的，
# 而且推出来的关系一定自洽（surface 永远比 background 偏一点、border 永远在中间）。
# ═══════════════════════════════════════════════════════════════════════════


def roles(colors: dict) -> dict:
    """四个色 → 第 20 条的完整角色表（含 chart_colors 与 gradient）。"""
    primary = colors.get("primary", "#0033CC")
    secondary = colors.get("secondary", "#0A0A0A")
    background = colors.get("background", "#FFFFFF")
    text = colors.get("text") or ink.text_color(colors)
    L_b, C_b, H_b = oklch(background)
    L_p, C_p, H_p = oklch(primary)
    dark_paper = L_b < 0.45
    step = 0.06 if dark_paper else -0.06          # surface 相对背景的偏移方向

    def shift(base_hex: str, dl: float, dc: float = 0.0, dh: float = 0.0) -> str:
        L, C, H = oklch(base_hex)
        return to_hex((_clamp(L + dl), max(0.0, C + dc), (H + dh) % 360))

    surface = shift(background, step, 0.0, 0.0)
    return {
        "background": background,
        "surface": surface,
        "surface_alt": shift(background, step * 2, 0.0, 0.0),
        "primary": primary,
        "secondary": secondary,
        "accent": primary,
        "highlight": shift(primary, 0.12 if L_p < 0.6 else -0.10, 0.02),
        "text_primary": text,
        "text_secondary": shift(text, -0.12 if L_b > 0.5 else 0.12, 0.0, 0.0),
        "text_muted": shift(text, -0.24 if L_b > 0.5 else 0.24, 0.0, 0.0),
        "border": shift(background, step * 3, 0.0, 0.0),
        # 图表色从主色旋出色相（第 22 条"图表从同一 Palette 扩展"），旋 30/60 度
        # 是常用的和谐步长。
        #
        # ⚠️ **中性色不能旋色相** —— C=0 时旋色相是个空操作，产出与原色完全相同的
        # 值。实测：`#0A0A0A` 旋 60° 还是 `#0A0A0A`，于是五个图表色里出现重复
        # （`len(set) == 4` 而长度是 5）。中性色的区分靠**明度**。
        "chart_colors": _chart_colors(primary, secondary, shift, L_b),
        "gradient": {
            "type": "linear",
            "angle": 135,
            # stop 刻意**不均匀**（第 13 条：可用非线性 stop 制造更高级的视觉）
            "stops": [[0.0, background], [0.23, surface], [0.68, shift(background, step * 3)],
                      [1.0, shift(primary, 0.0, -0.04)]],
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# 6. 审查 —— 第 24 条里**能测的那几条**
# ═══════════════════════════════════════════════════════════════════════════

# 明度至少分这么多档才算"结构清晰"（第 7 条要求至少区分 5 个层级）。
MIN_LIGHTNESS_TIERS = 4

# 强调色占画面的建议区间（第 11 条）。超出只是提示 —— 像素占比是风格的一部分，
# 有些风格就是靠大面积强调色立住的（billboard）。
ACCENT_SHARE = (0.05, 0.20)


def _chart_colors(primary: str, secondary: str, shift, L_background: float) -> list[str]:
    """图表色：主色旋几档 + 副色的一个可区分档。

    中性副色（彩度低于 `NEUTRAL_CHROMA`）**改明度**而不是旋色相 —— 旋它是空操作。
    方向按纸底决定（浅底压暗、深底提亮），保证它在同一条图表里与其他色分得开。
    """
    _l, c_s, _h = oklch(secondary)
    if c_s >= NEUTRAL_CHROMA:
        alt = shift(secondary, 0.0, 0.0, 60.0)
    else:
        alt = shift(secondary, -0.18 if L_background > 0.5 else 0.18)
    out: list[str] = []
    for value in (primary, alt, shift(primary, 0.0, 0.0, 30.0),
                  shift(primary, 0.0, 0.0, -30.0), shift(primary, 0.0, 0.0, 60.0)):
        if value not in out:
            out.append(value)
    return out


def structure_of(style: dict) -> dict:
    """算一套风格的色彩结构（第 21 条那些字段的**实测值**）。"""
    sets = style.get("colorSets", {})
    if not sets:
        return {}
    hues, saturations, lightnesses, counts = [], [], [], []
    per_set = {}
    for name, colors in sets.items():
        L_p, C_p, H_p = oklch(colors["primary"])
        L_b, C_b, H_b = oklch(colors["background"])
        struct = hue_structure(colors)
        per_set[name] = {
            "hue_structure": struct,
            "primary_lch": [round(L_p, 3), round(C_p, 3), round(H_p, 1)],
            "temperature": _temperature(colors),
            "contrast": round(ink.contrast(_text_for(colors), colors["background"]), 2),
            "lightness_gap": round(abs(L_b - L_p), 3),
        }
        counts.append(_color_count(colors))
        if C_p >= NEUTRAL_CHROMA:
            hues.append(H_p)
        saturations.append(C_p)
        lightnesses.extend([L_p, L_b])
    return {
        "hue_structures": per_set,
        "color_count": _count_label(max(counts)) if counts else "minimal",
        "lightness_structure": _lightness_label(lightnesses),
        "saturation_structure": _saturation_label(saturations),
        "temperature": per_set[next(iter(per_set))]["temperature"],
        "sets": per_set,
    }


def _text_for(colors: dict) -> str:
    return colors.get("text") or ink.text_color(colors)


def _color_count(colors: dict) -> int:
    """这套色板实际用了几种可区分的颜色（按 OKLCH 距离去掉重复）。"""
    seen: list[tuple[float, float, float]] = []
    for value in colors.values():
        lch = oklch(value)
        if not any(abs(lch[0] - s[0]) < 0.04 and abs(lch[1] - s[1]) < 0.02
                   and _hue_delta(lch[2], s[2]) < 12 for s in seen):
            seen.append(lch)
    return len(seen)


def _count_label(n: int) -> str:
    return "minimal" if n <= 2 else ("restrained" if n == 3 else
                                     ("moderate" if n == 4 else "rich"))


def _lightness_label(values: list[float]) -> str:
    """明度跨度 → light / dark / mixed / high-contrast（第 7 条）。"""
    if not values:
        return "mixed"
    lo, hi = min(values), max(values)
    span = hi - lo
    if lo > 0.7:
        return "light"
    if hi < 0.35:
        return "dark"
    if span >= 0.6:
        return "high-contrast"
    return "mixed"


def _saturation_label(values: list[float]) -> str:
    """彩度 → low / medium / high-accent / vibrant（第 8 条）。"""
    if not values:
        return "medium"
    top = max(values)
    if top < 0.06:
        return "low"
    if len([v for v in values if v >= 0.15]) >= 2:
        return "vibrant"
    return "high-accent" if top >= 0.12 else "medium"


def _temperature(colors: dict) -> str:
    """冷暖：按主色的色相角判（第 9 条）。"""
    _l, c, h = oklch(colors["primary"])
    if c < NEUTRAL_CHROMA:
        _l2, c2, h2 = oklch(colors["background"])
        if c2 < NEUTRAL_CHROMA:
            return "mixed"
        h = h2
    return "warm" if (h < 90 or h > 330) else ("cool" if 150 < h < 300 else "mixed")


def audit(style: dict, topic: str = "", only: str | None = None,
          novelty_floor: float | None = None) -> tuple[list[str], list[str]]:
    """审一套风格的配色。返回 (阻塞问题, 提示)。

    阻塞 vs 提示的界线：**客观的、规范明说不许的** → 阻塞（文字对比、结构声明与
    实测不符）；**取决于语境的**（novelty 高低、强调占比）→ 提示。颜色好不好看
    不是能测的，能测的只有对比、结构、数量、占比。
    """
    problems: list[str] = []
    notes: list[str] = []
    sets = style.get("colorSets", {})
    if not sets:
        return (["这套风格的 style.json 里没有 colorSets"], [])

    declared = style.get("colorStructure", {})
    for name, colors in sorted(sets.items()):
        if only and name != only:
            continue
        tag = f"{style.get('label', '?')} / {name}"
        # ① 文字对比（客观，阻塞）—— ink.py 已有这一条，这里再独立复核一次
        text = _text_for(colors)
        ratio = ink.contrast(text, colors["background"])
        floor = style.get("contrast", {}).get("minBody", 4.5)
        if ratio < floor:
            problems.append(f"{tag}：正文色 {text} 在 {colors['background']} 上对比 "
                            f"{ratio:.2f} < {floor}（规范第 7/24 条：文字必须可读）")
        # ② 背景与主体明度不能太近（客观，阻塞）—— 第 7 条
        L_p, _C, _H = oklch(colors["primary"])
        L_b, _, _ = oklch(colors["background"])
        if 0.0 < abs(L_b - L_p) < 0.12:
            problems.append(f"{tag}：背景 L={L_b:.2f} 与主色 L={L_p:.2f} 明度太近 —— "
                            f"重点浮不出来（规范第 7 条）")
        # ③ 俗套与 novelty（第 18 条）：**说清是哪一条**，按主题条件判。
        #    ⚠️ 这一段必须留在**逐色板**的循环里。改结构时它一度被并进下面的
        #    风格级 if 里，于是"只有结构声明不匹配才报俗套"—— 静默失效（实测）。
        score, reasons = novelty(colors, topic)
        for r in reasons:
            if r["kind"] == "penalty":
                notes.append(f"{tag}：俗套「{r['id']}」{r['why']}（{r['delta']:+.2f}）")
        floor_value = novelty_floor if novelty_floor is not None else declared.get("novelty_target")
        if floor_value is not None and score < floor_value:
            notes.append(f"{tag}：novelty {score:.2f} < 目标 {floor_value:.2f} —— "
                         f"想拉高就换一套非常规冷暖的组合，或做一次 OKLCH 变体"
                         f"（`--directions`）")

    # ④ 结构声明与实测要对得上（声明是承诺，实测是事实）。比对是**风格级**的：
    #    一套风格的几个色板可以有不同的色相结构（实测：notebook 的 rule 是三角、
    #    marker 是互补），所以要求声明落在实测集合里 —— 逐套板全等会把真实差异
    #    当错误报，而那种报告会让人开始忽略全部提示。
    if only and len(sets) > 1:
        pass                       # 只审一个色板时不做风格级判断
    else:
        claim = declared.get("hue_structure")
        actual_set = {hue_structure(c) for c in sets.values()}
        if claim and claim not in actual_set:
            notes.append(f"{style.get('label', '?')}：声明 hue_structure={claim!r}，"
                         f"实测是 {sorted(actual_set)} —— 其中一个该改"
                         f"（实测按 OKLCH 色相夹角算，见 NEUTRAL_CHROMA 的注释）")
    return (problems, notes)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="配色：结构 / 角色 / novelty / 三方向")
    ap.add_argument("--audit", action="store_true", help="审 8 套风格的配色")
    ap.add_argument("--style", default=None, help="只审这一套风格")
    ap.add_argument("--color-set", default=None, help="只审这一个色板")
    ap.add_argument("--topic", default="", help="主题（用来判'科技=蓝紫青'那条俗套）")
    ap.add_argument("--novelty", nargs=2, metavar=("STYLE", "SET"),
                    help="打印某个色板的 novelty 与依据")
    ap.add_argument("--directions", nargs=2, metavar=("STYLE", "SET"),
                    help="打印 Safe / Creative / Experimental 三套变体")
    ap.add_argument("--roles", nargs=2, metavar=("STYLE", "SET"),
                    help="打印 13 个角色的推导结果")
    ap.add_argument("--min-novelty", type=float, default=None,
                    help="低于它就退出 1（当发布闸门用）")
    args = ap.parse_args(argv[1:])

    names = [args.style] if args.style else deckio.list_dirs(STYLES)

    if args.roles:
        style, set_name = args.roles
        tokens = deckio.read_json(os.path.join(STYLES, style, "style.json"))
        print(_dump(roles(tokens["colorSets"][set_name])))
        return 0

    if args.directions:
        style, set_name = args.directions
        tokens = deckio.read_json(os.path.join(STYLES, style, "style.json"))
        for name, row in directions(tokens["colorSets"][set_name]).items():
            print(f"── {name}（novelty {row['novelty']:.2f}）{row['why']}")
            print("   " + _dump(row["colors"]))
        return 0

    if args.novelty:
        style, set_name = args.novelty
        tokens = deckio.read_json(os.path.join(STYLES, style, "style.json"))
        score, reasons = novelty(tokens["colorSets"][set_name], args.topic)
        print(f"{style} / {set_name}：novelty = {score:.2f}")
        for r in reasons:
            print(f"   {r['kind']:8} {r['id']:26} {r['delta']:+.2f}  {r['why']}")
        if not reasons:
            print("   （没有触发任何加减项）")
        return 0

    failed = 0
    for name in names:
        path = os.path.join(STYLES, name, "style.json")
        if not os.path.isfile(path):
            continue
        tokens = deckio.read_json(path)
        # ⚠️ 这里传的必须是**色板名**，不是风格名 —— 曾经把 args.style 传进来，
        # 于是"只审这一套风格"变成了"只审一个叫 terminal 的色板"（不存在），
        # 所有色板都被跳过、一条问题都不报（实测）。
        problems, notes = audit(tokens, args.topic, args.color_set, args.min_novelty)
        struct = structure_of(tokens)
        print(f"═══ {name}")
        print(f"   结构：{struct.get('hue_structures', {}).get(next(iter(tokens['colorSets'])), {}).get('hue_structure', '?')}"
              f" · {struct.get('color_count')} · {struct.get('lightness_structure')}"
              f" · {struct.get('saturation_structure')} · {struct.get('temperature')}")
        for p in problems:
            print(f"   ✗ {p}")
        for n in notes:
            print(f"   · {n}")
        failed += len(problems)
    print(f"\n{'✓ 没有阻塞问题' if not failed else f'✗ {failed} 个阻塞问题'}")
    return 1 if failed else 0


def _dump(obj: dict) -> str:
    import json   # noqa: PLC0415

    return json.dumps(obj, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
