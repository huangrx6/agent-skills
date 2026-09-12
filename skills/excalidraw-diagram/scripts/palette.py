#!/usr/bin/env python3
"""颜色不是模板，而是**有审美锚点的自适应系统**：规则决定颜色如何工作，
Seed 决定颜色往哪里走，视觉层级最终由构图、尺寸、留白、线条、文字与颜色共同完成。

## 这套系统回答的是什么问题

不是"这张图用什么颜色"，而是"**这张图应该是什么气质，以及怎么用最少的颜色把它表达出来**"。
前一版把它当配色模板做（六种语义六种颜色 → 五档层级五个色相），工程上干净，
视觉上一定丑 —— 实测色相跨度 310°、一张 14 节点的图出现 9 种颜色，
最后的效果是"看起来专业，但没有生命力"。

## 三层各自负责什么

    用户意图 / 图表内容
            ↓
    Visual Direction（视觉母体：什么气质）
            ↓
    Character（形容词，给**模型**判断"该选哪个方向"用）
    Seed（人工审美锚点，给**代码**一个品味基准）
            ↓
    Adaptive Color System（wash / soft / edge / muted 全部派生）
            ↓
    Semantic Role → Visual Level → 实际 Excalidraw 颜色

**Character 是给模型读的，Seed 是给代码读的** —— 这是两者唯一的区别。
形容词生成不出 `#2F5D46`；而"哪一个是高级的绿"恰恰就是审美本身。

## 颜色数量 ≠ 语义数量

语义角色可以自由增加（`plain` 就是这么来的），**颜色只有 4 档层级**。
加一个角色只是让它指向已有的层级之一，不会多出一个颜色。

## 两条不可协商的规矩

1. **未知值判失败，绝不 fallback。** fallback 会让"颜色必须落在板内"这条校验
   自己绕过自己 —— 程序补的默认色当然合法，校验通过了，但语义已经错了。
2. **禁止灰蓝企业风成为默认。** 白底 + 灰字 + 灰蓝节点 + 蓝灰线这一套
   （`#6E879B` / `#7F96A5` / `#AAB8C0` 那一路）是被明确否掉的结果。
   `tests/test_palette.py` 里有用例守着这条。
"""

from __future__ import annotations

import colorsys
import contextlib
import math

# ══════════════════════════════════════════════════════════════════
# Visual Levels —— 只有 4 档
# ══════════════════════════════════════════════════════════════════
#
# 上一版有 5 档（多一个 `secondary`）。删掉它是因为：**多一档就多诱惑一次** ——
# "这个也重要、那个也重要"最后会变成每个节点都有颜色。4 档已经把该说的说完：
#
#   普通  →  轻微区分  →  重点  →  异常 / 关键状态
#
# `tint` 是"退到背景里的那一片"（极轻的分组 / 次级区域），
# 它与画布的差**不大**，但必须**看得出来** —— 见 WASH_MIX 那行的实测记录。
VISUAL_LEVELS = ("neutral", "tint", "accent", "critical")
_LEVEL_ORDER = {name: i for i, name in enumerate(VISUAL_LEVELS)}

# 层级 → 视觉角色（描边角色, 填充角色）。这一层把"我有多重要"翻译成"用哪几个颜色"。
LEVEL_ROLES: dict[str, tuple[str, str]] = {
    "neutral":  ("ink",      "canvas"),         # 完全中性：填充就是画布色
    "tint":     ("ink",      "accent-wash"),    # 极轻的一片，**不是第二种颜色**
    "accent":   ("accent",   "accent-soft"),    # 整张图真正的视觉重点
    "critical": ("critical", "critical-soft"),  # 唯一允许跳出主色系的
}

# 派生配比。放一起，方便一眼看出"深浅关系"是从哪来的。
WASH_MIX = 0.18        # tint 填充：**要能被看见**（见下面那条实测）
SOFT_MIX = 0.44        # accent 填充
CRITICAL_MIX = 0.34    # critical 填充：一层浅洗染，警示主要靠描边 + 线宽
EDGE_MIX = 0.42        # 普通连线：画布与墨色之间
EDGE_MUTED_MIX = 0.24  # 弱连线：更靠近画布

# ══════════════════════════════════════════════════════════════════
# 样式轴 —— Excalidraw 原生的四组档位
# ══════════════════════════════════════════════════════════════════
#
# 颜色之外，图上还有四组"怎么画"的档位。用户点名要能选的就是这四组：
#
#   填充   斜条纹 / 网格 / 实心        （Excalidraw 的 fillStyle）
#   描边   实线 / 虚线 / 小圆点         （strokeStyle）
#   边角   直角 / 圆角                 （roundness）
#   线条   正常直线 / 轻微手绘 / 更明显的手绘（roughness 0 / 1 / 2）
#
# ⚠️ `stroke` **只管节点的框和区域**，不管连线。连线的虚实是**语义**（§7：
# 虚线 = 异步 / 可选）—— 让 `style.stroke` 去改它会把语义一起改掉。
#
# ⚠️ 默认**不是实心**。用户的要求是"尽量不要用实心的颜色"：斜条纹的填充是把
# 浅色画成一组细线，整体更轻更透，一屏十几个框也不会糊成一片色块。
# 实心要显式要（`"fill": "solid"`）。
FILL_STYLES = ("hachure", "cross-hatch", "solid")
# `shape` = **听形状自己的**（`shapes.SHAPES` 的 roundness / stroke_style）。
# 做成一个默认档位而不是"默认 None"，是为了让"显式覆盖"和"不改"两件事都说得清楚：
#   note 形状天生虚线框、rect 天生直角 —— 不写就等于保留它们；
#   写了 `stroke: solid` / `corners: round` 就是**明确要覆盖**，包括 capsule 那种
#   靠圆角定义自己的形状（覆盖成直角它就变成一个普通矩形，那是你要的就要）。
STROKE_STYLES = ("shape", "solid", "dashed", "dotted")
CORNER_STYLES = ("shape", "sharp", "round")
LINE_STYLES = ("straight", "sketch", "rough")
ROUGHNESS_OF = {"straight": 0, "sketch": 1, "rough": 2}

STYLE_AXES: dict[str, tuple[str, ...]] = {
    "fill": FILL_STYLES,
    "stroke": STROKE_STYLES,
    "corners": CORNER_STYLES,
    "line": LINE_STYLES,
}
STYLE_DEFAULT = {"fill": "hachure", "stroke": "shape", "corners": "shape",
                 "line": "sketch"}


def resolve_style(raw: dict | None) -> dict:
    """把 spec 里的 `style` 补全成一份完整样式。

    **未知的轴、未知的取值都判失败，绝不 fallback** —— 和颜色那两条规矩同源：
    fallback 会让"样式必须落在档位内"这条校验自己绕过自己（程序补的默认值当然
    合法，校验通过，但画出来的不是你要的）。
    """
    style = dict(STYLE_DEFAULT)
    for key, value in (raw or {}).items():
        if key not in STYLE_AXES:
            raise ValueError(f"style 里没有 {key!r} 这一项，可用 {sorted(STYLE_AXES)}")
        if value not in STYLE_AXES[key]:
            raise ValueError(f"style.{key} = {value!r} 不在档位里，可用 "
                             f"{list(STYLE_AXES[key])}")
        style[key] = value
    return style


FRAME_MIX = 0.52          # 区域边框：层级描边色往画布方向退这么多


def frame_stroke(level: str) -> str:
    """**区域边框的颜色** —— 它不是节点的框，所以不该用节点的颜色。

    踩过的坑：区域边框原来是 `LEVELS[level]["stroke"]`（`ink`，近黑），和节点框
    一模一样，再加上样式轴把两者都设成虚线时，区域边框和连线在视觉上就分不开了 ——
    用户看到"三根线只到两个箭头"，其中两根其实是相邻两个区域的边框。

    判据：区域是**背景**，它的框只该表示"到这儿为止"，不该和前景抢。所以往画布
    方向退一半多，让它明确落在"背景层"那一档。
    """
    return _mix(CANVAS["background"], LEVELS[level]["stroke"], 1.0 - FRAME_MIX)


def merge_style(base: dict | None, override: dict | None) -> dict:
    """把**已解析**的样式与一份**局部覆盖**合并：覆盖里没写的轴保持原值。

    用途只有一个：区域的局部覆盖（`groups[].style`）。用户要过「只让区域用虚线、
    节点保持实线」—— 全局 `style` 做不到，得有一条"只改这一块"的路径。

    ⚠️ 与 `resolve_style` 的区别：那个是**补默认值**（缺的轴按默认），这个是**盖在上层**
    （缺的轴继承下层）。两件事混在一起会出现"局部覆盖把别的轴悄悄打回默认"的怪事。
    """
    out = dict(base) if base else dict(STYLE_DEFAULT)
    for key, value in (override or {}).items():
        if key not in STYLE_AXES:
            raise ValueError(f"style 里没有 {key!r} 这一项，可用 {sorted(STYLE_AXES)}")
        if value not in STYLE_AXES[key]:
            raise ValueError(f"style.{key} = {value!r} 不在档位里，可用 "
                             f"{list(STYLE_AXES[key])}")
        out[key] = value
    return out


def roundness_of(style: dict, shape_default: dict | None) -> dict | None:
    """圆角给 Excalidraw 的 roundness 对象，直角给 None（不是 type 0）。

    `corners: shape`（默认）原样交回形状自己的值 —— 这样"不改"和"显式改成直角"
    是同一条路径上的两个取值，不存在"没生效"这种中间状态。
    """
    corners = style.get("corners", STYLE_DEFAULT["corners"])
    if corners == "shape":
        return shape_default
    return {"type": 3} if corners == "round" else None


def stroke_style_of(style: dict, shape_default: str) -> str:
    """节点的框线虚实。`stroke: shape` 时保留形状自己的（note 天生虚线）。"""
    value = style.get("stroke", STYLE_DEFAULT["stroke"])
    return shape_default if value == "shape" else value


def roughness_of(style: dict) -> int:
    return ROUGHNESS_OF[style.get("line", STYLE_DEFAULT["line"])]


# ══════════════════════════════════════════════════════════════════
# Visual Directions —— 5 个视觉母体，每个 1~2 个 Seed
# ══════════════════════════════════════════════════════════════════
#
# ⚠️ 这些不是"五套主题色"。它们是 5 个**母体**：Character 说"应该什么感觉"，
# Seed 给一个品味基准，实际颜色仍然由下面的派生规则算出来。
#
# ⚠️ Seed 的色值状态：**待验证** —— 是按 Character 的描述人工定的品味锚点，
# 没有经过真实使用校准。按本项目的规矩，量过之前不标"已确认"。
#
# Seeds are curated visual anchors, not fixed output palettes.
#
# A seed establishes the aesthetic baseline for:
# - canvas temperature
# - ink character
# - accent hue
# - critical hue
#
# All secondary colors are derived from these seeds.
#
# The renderer may select among seeds based on context,
# but must preserve the visual direction's character.
VISUAL_DIRECTIONS: dict[str, dict] = {
    "botanical": {
        "zh": "自然 / 植物",
        "character": {
            "temperature": "warm",
            "density": "sparse",
            "contrast": "moderate",
            "accent_character": "botanical",
            "canvas_character": "warm-airy",
            "use_for": "架构、关系图、知识体系",
        },
        "seeds": {
            # 大面积空气感 + 少量自然色渗进去 —— 不是满屏绿色
            "mature-natural": {"canvas": "#FBFAF2", "ink": "#243024",
                               "accent": "#2E9E63", "critical": "#D2663C"},
            "lively-leaf": {"canvas": "#FCFDF4", "ink": "#1E2E22",
                            "accent": "#3FAB73", "critical": "#DE7748"},
        },
    },
    "editorial": {
        "zh": "杂志 / 精炼",
        "character": {
            "temperature": "neutral-warm",
            "density": "sparse",
            "contrast": "high",
            "accent_character": "restrained",
            "canvas_character": "ivory-neutral",
            "use_for": "产品架构、方案、展示型图",
        },
        "seeds": {
            # 高对比、单一主色、极少量强调 —— 像设计作品集
            "warm-editorial": {"canvas": "#FCFBF6", "ink": "#1A1815",
                               "accent": "#8F5A32", "critical": "#B23A24"},
            "neutral-editorial": {"canvas": "#FAFAF8", "ink": "#141414",
                                  "accent": "#3A4A6B", "critical": "#9C3A28"},
        },
    },
    "fresh": {
        "zh": "轻盈 / 春夏",
        "character": {
            "temperature": "bright",
            "density": "sparse",
            "contrast": "moderate",
            "accent_character": "youthful",
            "canvas_character": "bright-airy",
            "use_for": "流程、产品、轻量知识图",
        },
        "seeds": {
            # 高明度、通透、冷暖交替
            "spring": {"canvas": "#FFFFFA", "ink": "#28382C",
                       "accent": "#48B88C", "critical": "#F0803C"},
            "clear": {"canvas": "#FBFDFD", "ink": "#22343C",
                      "accent": "#3FA9C4", "critical": "#EE8B52"},
        },
    },
    "coastal": {
        "zh": "清透 / 海风",
        "character": {
            "temperature": "cool",
            "density": "sparse",
            "contrast": "moderate",
            "accent_character": "airy",
            "canvas_character": "clean-air",
            "use_for": "数据流、网络、流动关系",
        },
        "seeds": {
            # 阳光 / 海 / 空气 —— **不是科技蓝**（那是被否掉的那条路）
            "sea-air": {"canvas": "#FCFDFB", "ink": "#1C2E3A",
                        "accent": "#1E9BB0", "critical": "#E0873F"},
            "sun-washed": {"canvas": "#FDFDF8", "ink": "#272F38",
                           "accent": "#2AA3B8", "critical": "#E07C3A"},
        },
    },
    "night": {
        "zh": "墨夜 / 深色",
        "character": {
            "temperature": "warm-dark",
            "density": "sparse",
            "contrast": "high",
            "accent_character": "characterful",
            "canvas_character": "warm-dark",
            "use_for": "深色场景、技术 / 复杂架构",
        },
        "seeds": {
            # 暖墨底 + 暖白字 + 一个有性格的颜色 —— 不是"程序员深色"
            "warm-night": {"canvas": "#14110F", "ink": "#F2EDE4",
                           "accent": "#E0B32E", "critical": "#E06045"},
            "amber-night": {"canvas": "#161310", "ink": "#F0E9DE",
                            "accent": "#E09540", "critical": "#E06045"},
        },
    },
}

# 默认方向。**auto 不是"随便挑一个"** —— 它按图类型 + 内容 + 用户意图选，
# 见 `suggest_direction()`。默认走 auto 是刻意的：不让某一个方向成为"永远的结果"。
DEFAULT_DIRECTION = "auto"
AUTO_DIRECTION = "auto"

# 图类型 → 倾向的方向。**只列倾向，不是强制映射**。
# 用户说了风格意图时，用户意图优先（见 `resolve_direction`）。
DIRECTION_FOR_TYPE: dict[str, list[str]] = {
    "architecture": ["botanical", "editorial"],
    "dependency":   ["botanical", "editorial"],
    "flow":         ["fresh", "coastal"],
    "state":        ["editorial", "fresh"],
    "mindmap":      ["botanical", "fresh"],
    "network":      ["coastal", "editorial"],
}

# 用户嘴里的话 → 方向。**用户意图优先于图类型**。
# 例如"做一个很有春天气息的架构图"：不能因为 type=architecture 就强行 editorial。
DIRECTION_FOR_MOOD: dict[str, str] = {
    "春天": "fresh", "spring": "fresh", "夏": "fresh", "轻": "fresh", "明亮": "fresh",
    "自然": "botanical", "植物": "botanical", "绿": "botanical", "生命": "botanical",
    "海": "coastal", "夏威夷": "coastal", "水": "coastal", "清透": "coastal", "流动": "coastal",
    "杂志": "editorial", "高级": "editorial", "克制": "editorial", "设计感": "editorial",
    "深色": "night", "夜": "night", "dark": "night", "墨": "night",
}

# ══════════════════════════════════════════════════════════════════
# 语义角色 → 默认层级
# ══════════════════════════════════════════════════════════════════
#
# ⚠️ **没有角色默认拿到 accent。** 这是刻意的，也是这一版最重要的解耦：
# `service` 不等于"重要" —— 一张图里有五个 service 是常事。谁是重点由**每张图**
# 决定（`emphasis: primary`），不是由角色的名字决定。
#
# 上一版 `service → accent`，结果 01-architecture 里 4 个服务全是强调色。
DEFAULT_KIND_LEVELS: dict[str, str] = {
    "client":   "neutral",
    "service":  "neutral",
    "data":     "neutral",
    "async":    "neutral",
    "security": "neutral",
    "external": "neutral",
    # 通用角色：流水线步骤 / 状态机状态 / 普通模块 / 思维导图叶子。
    # 没有它的时候这些节点只能硬套 service。
    "plain":    "neutral",
}

# 边型 → 视觉角色。**边默认全部退出颜色竞争**（§10）：
# "大量蓝色关系线"是上一版最明显的问题之一 —— 节点控制得再好，线也能把整张图染色。
# 语义靠**线型**表达，颜色留给节点。
EDGE_ROLES: dict[str, str] = {
    "sync":     "edge",
    "data":     "edge",        # 不是"数据流 = 蓝" —— 重要与否由 emphasis 决定
    "async":    "edge-muted",
    "optional": "edge-muted",
}

EDGE_STYLES: dict[str, tuple[str, str]] = {
    "sync":     ("同步调用", "solid"),
    "data":     ("数据读写", "solid"),
    "async":    ("异步 / 事件", "dashed"),
    "optional": ("可选 / 条件分支", "dashed"),
}

# ══════════════════════════════════════════════════════════════════
# 强调：层级 + 尺寸 + 线宽（颜色不再是唯一手段）
# ══════════════════════════════════════════════════════════════════
#
# 优先级（视觉层级从强到弱）：构图 / 位置 > 留白 / 间距 > 尺寸 > 线宽 > 字体 > 颜色。
#
# `scale` 只是**建议值**，由布局层在盒子上应用 —— **不要**把它硬编码进
# 每个元素的 width/height，那样会把文字从容器里挤出去（盒子是从文字反推的）。
#
# 幅度刻意小：0.92 / 1.00 / 1.06 / 1.03。我们要的是"有层次"，不是海报式跳跃。
# 实测（#114）1.08 的放大在整图尺度上几乎看不见 —— 所以尺寸是**辅助**，
# 第一眼看到哪里仍然由颜色和位置决定。
#
# `font_step` 是**字号档位的步数**（§14）。它和 `scale` 是两条不同的手段：
#   `scale`     乘在形状盒子上 → 同样的字，留白多一点
#   `font_step` 加在字号上     → **字本身变大**，盒子顺着尺寸链跟着变大
#
# 重点档用的是**字号**而不是盒子倍数 —— 一是"重点节点的字要跟上"（§14），
# 二是两条一起上会叠成 1.0625 × 1.06 ≈ 1.13，超出 §13 说的 1.05~1.10。
# 所以 `primary` 的 scale 是 1.00，放大全交给字号。
EMPHASIS: dict[str, dict] = {
    "muted":    {"zh": "次要", "level": "neutral",  "scale": 0.94, "font_step": 0,
                 "stroke_width": 1.0},
    "normal":   {"zh": "常规", "level": None,       "scale": 1.00, "font_step": 0,
                 "stroke_width": 1.5},
    "primary":  {"zh": "重点", "level": "accent",   "scale": 1.00, "font_step": 1,
                 "stroke_width": 2.5},
    "critical": {"zh": "警示", "level": "critical", "scale": 1.03, "font_step": 0,
                 "stroke_width": 2.5},
}


def emphasis_font_step(emphasis: str) -> int:
    """这档强调的字号步数（0 = 用节点默认字号）。未知值抛错，不 fallback。"""
    try:
        return int(EMPHASIS[emphasis]["font_step"])
    except KeyError:
        raise KeyError(
            f"未知 emphasis: {emphasis!r}；允许的取值：{sorted(EMPHASIS)}"
        ) from None
DEFAULT_EMPHASIS = "normal"

# ══════════════════════════════════════════════════════════════════
# 当前生效状态（模块级）
# ══════════════════════════════════════════════════════════════════
#
# 为什么用模块级状态而不是把方向一路传参：`stroke_for` / `fill_for` / `CANVAS`
# 被几十处调用，全改成带参数会把"颜色"这件事的调用面铺得很大，
# 而**一次出图里只有一个方向**。入口处定一次，其余照旧读。
#
# ⚠️ **测试里必须用 `direction_context()`** —— 否则用例之间会互相污染。
_active_direction = "botanical"     # 内部值；入口是 use_direction()
_active_seed: str | None = None
_active_mood: str | None = None

ROLES: dict[str, str] = {}
LEVELS: dict[str, dict[str, str]] = {}
KINDS: dict[str, str] = {}
EDGE_KINDS: dict[str, dict[str, str]] = {}
CANVAS: dict = {}


# ══════════════════════════════════════════════════════════════════
# 颜色数学：**唯一实现**在这里
# ══════════════════════════════════════════════════════════════════
#
# 以前这套公式只写在 tests/test_palette.py 里，于是"检查颜色"的地方（图标撞色、
# 报告里的可读性）只能自己再写一份 —— 两份必然漂移。测试仍然会用已知值把这几把
# 尺子钉住（白对黑 = 21 之类），尺子本身照样是验过的。

def hex_to_rgb(colour: str) -> tuple[int, int, int]:
    return _parse_hex(colour)


def _parse_hex(value: str) -> tuple[int, int, int]:
    text = value.lstrip("#")
    if len(text) != 6:
        raise ValueError(f"只接受 #RRGGBB 形式，收到 {value!r}")
    try:
        return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
    except ValueError as error:
        raise ValueError(f"不是合法的十六进制颜色：{value!r}") from error


def relative_luminance(colour: str) -> float:
    """WCAG 相对亮度。"""
    channels = []
    for value in _parse_hex(colour):
        srgb = value / 255.0
        channels.append(srgb / 12.92 if srgb <= 0.03928
                        else ((srgb + 0.055) / 1.055) ** 2.4)
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast(a: str, b: str) -> float:
    """WCAG 对比度（1 ~ 21）。"""
    la, lb = relative_luminance(a), relative_luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def saturation(colour: str) -> float:
    """HSV 饱和度 = (max - min) / max。

    ⚠️ **不要"顺手改成 HSL"** —— HSL 的分母不同，中间值会变，而"填充要去饱和"
    那几个用例是按 HSV 定的阈值。搬家的那一次真发生过，三个用例变红才挡住。
    """
    red, green, blue = (value / 255.0 for value in _parse_hex(colour))
    high, low = max(red, green, blue), min(red, green, blue)
    return 0.0 if high == 0 else (high - low) / high


def hue(colour: str) -> float:
    """HSV 色相（度）。

    ⚠️ 只对**有饱和度**的颜色有意义：`#FDFCFA` 这种近无彩色的色相是噪声，
    拿它去比"色相跨度"会得出荒谬的结论（这个坑踩过）。
    """
    red, green, blue = (value / 255.0 for value in _parse_hex(colour))
    return colorsys.rgb_to_hsv(red, green, blue)[0] * 360.0


def to_lab(colour: str) -> tuple[float, float, float]:
    red, green, blue = (value / 255.0 for value in _parse_hex(colour))
    to_linear = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    red, green, blue = to_linear(red), to_linear(green), to_linear(blue)
    x = (red * 0.4124 + green * 0.3576 + blue * 0.1805) / 0.95047
    y = (red * 0.2126 + green * 0.7152 + blue * 0.0722) / 1.00000
    z = (red * 0.0193 + green * 0.1192 + blue * 0.9505) / 1.08883
    f = lambda t: t ** (1 / 3) if t > 0.008856 else (7.787 * t + 16 / 116)
    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def delta_e(a: str, b: str) -> float:
    """CIE76 色差。可区分性用它，**不要用对比度** ——
    本系统的相邻色特点正是"亮度相近、色相不同"，对比度量不出来。"""
    la, lb = to_lab(a), to_lab(b)
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(la, lb)))


def _mix(a: str, b: str, ratio: float) -> str:
    """在 a 与 b 之间线性插值。ratio=0 得到 a，ratio=1 得到 b。

    **所有派生颜色都走这里** —— 这是"一张图只有一个主色系"的实现处：
    wash / soft / edge 都是同一个主色与画布 / 墨色按固定配比混出来的，
    想弄出第二个色相都做不到。
    """
    ar, ag, ab = _parse_hex(a)
    br, bg, bb = _parse_hex(b)
    mixed = (
        round(ar + (br - ar) * ratio),
        round(ag + (bg - ag) * ratio),
        round(ab + (bb - ab) * ratio),
    )
    return "#{:02X}{:02X}{:02X}".format(*mixed)


# ══════════════════════════════════════════════════════════════════
# 派生：Seed → ROLES → LEVELS / EDGE_KINDS / CANVAS
# ══════════════════════════════════════════════════════════════════

def _rebind() -> None:
    global ROLES, LEVELS, KINDS, EDGE_KINDS, CANVAS
    spec = VISUAL_DIRECTIONS[_active_direction]
    seeds = spec["seeds"]
    name = _active_seed if _active_seed in seeds else next(iter(seeds))
    seed = seeds[name]

    canvas, ink = seed["canvas"], seed["ink"]
    accent, critical = seed["accent"], seed["critical"]
    ROLES = {
        "canvas":        canvas,
        "ink":           ink,
        "accent":        accent,
        "accent-wash":   _mix(canvas, accent, WASH_MIX),
        "accent-soft":   _mix(canvas, accent, SOFT_MIX),
        "critical":      critical,
        "critical-soft": _mix(canvas, critical, CRITICAL_MIX),
        "edge":          _mix(canvas, ink, EDGE_MIX),
        "edge-muted":    _mix(canvas, ink, EDGE_MUTED_MIX),
    }
    # 层级 → 描边 / 填充，全部走**角色**，没有一处直接写十六进制
    LEVELS = {level: {"stroke": ROLES[LEVEL_ROLES[level][0]],
                      "fill": ROLES[LEVEL_ROLES[level][1]]}
              for level in VISUAL_LEVELS}
    KINDS = dict(DEFAULT_KIND_LEVELS)
    EDGE_KINDS = {kind: {"zh": zh, "style": style, "stroke": ROLES[EDGE_ROLES[kind]]}
                  for kind, (zh, style) in EDGE_STYLES.items()}
    CANVAS = {"background": canvas, "grid": _mix(canvas, ink, 0.06), "text": ink,
              "stroke_style": "hand-drawn",
              "font_family": 2}      # native Excalidraw scene 里 CJK-safe 的那一档


# ── 选择方向：AUTO 与用户意图 ────────────────────────────────────

def available_directions() -> list[str]:
    return sorted(VISUAL_DIRECTIONS)


def available_seeds(direction: str | None = None) -> list[str]:
    spec = VISUAL_DIRECTIONS[direction or _active_direction]
    return sorted(spec["seeds"])


def is_known_direction(name: str) -> bool:
    return name in VISUAL_DIRECTIONS or name == AUTO_DIRECTION


def suggest_direction(diagram_type: str | None,
                      mood: str | None = None) -> str:
    """按**用户意图 → 图类型**的优先级选一个方向。

    用户意图优先：说了"春天气息"就不该因为 type=architecture 强行走 editorial。
    两样都没有时回落到 `botanical`（默认推荐方向）。
    """
    if mood:
        for word, direction in DIRECTION_FOR_MOOD.items():
            if word in mood:
                return direction
    for direction in DIRECTION_FOR_TYPE.get(diagram_type or "", []):
        return direction
    return "botanical"


def resolve_direction(name: str | None, diagram_type: str | None = None,
                      mood: str | None = None) -> str:
    """把外部给的方向名解成真实方向。`auto` / 空 → 按内容选。"""
    if not name or name == AUTO_DIRECTION:
        return suggest_direction(diagram_type, mood)
    if name not in VISUAL_DIRECTIONS:
        raise KeyError(
            f"未知视觉方向 {name!r}；可用的：{available_directions()} 或 {AUTO_DIRECTION!r}。"
            f"（旧主题名 soft-light / morandi 之类已经废弃 —— 它们代表的正是被否掉的"
            f"灰蓝企业风，静默映射过来只会让人以为改动没生效。）"
        )
    return name


def use_direction(name: str | None = None, seed: str | None = None,
                  diagram_type: str | None = None,
                  mood: str | None = None) -> str:
    """切换视觉方向。**未知方向判失败，不 fallback** —— 同 kind 一条规矩。"""
    global _active_direction, _active_seed
    resolved = resolve_direction(name, diagram_type, mood)
    if seed and seed not in VISUAL_DIRECTIONS[resolved]["seeds"]:
        raise KeyError(
            f"方向 {resolved!r} 下没有 seed {seed!r}；可用的："
            f"{available_seeds(resolved)}"
        )
    _active_direction = resolved
    _active_seed = seed
    _rebind()
    return resolved


def set_context(mood: str | None = None) -> None:
    """给 `auto` 用：记下用户的风格意图（原话即可）。"""
    global _active_mood
    _active_mood = mood


def active_direction() -> str:
    return _active_direction


def active_seed() -> str:
    return _active_seed or next(iter(VISUAL_DIRECTIONS[_active_direction]["seeds"]))


@contextlib.contextmanager
def direction_context(name: str | None = None, seed: str | None = None):
    """测试用：进出一个方向，出来时恢复原状。"""
    global _active_direction, _active_seed
    before = (_active_direction, _active_seed)
    use_direction(name, seed)
    try:
        yield _active_direction
    finally:
        _active_direction, _active_seed = before
        _rebind()


# ── 层级与颜色 ───────────────────────────────────────────────────

def level_for(kind: str, emphasis: str = DEFAULT_EMPHASIS) -> str:
    """这个角色在这档强调下落在哪个视觉层级。**颜色的唯一入口。**

    未知 kind / emphasis 都抛错，不 fallback。
    """
    if emphasis not in EMPHASIS:
        raise KeyError(f"未知 emphasis: {emphasis!r}；允许的取值：{sorted(EMPHASIS)}")
    if kind not in KINDS:
        raise KeyError(f"未知 kind: {kind!r}；允许的取值：{sorted(KINDS)}")
    override = EMPHASIS[emphasis]["level"]
    return override if override else KINDS[kind]


def stroke_for(kind: str, emphasis: str = DEFAULT_EMPHASIS) -> str:
    """取节点边框色。未知值直接抛错 —— 不 fallback。"""
    return LEVELS[level_for(kind, emphasis)]["stroke"]


def fill_for(kind: str, emphasis: str = DEFAULT_EMPHASIS) -> str:
    """取节点填充色。**唯一来源是方向派生出的层级表**，没有第二张表。"""
    return LEVELS[level_for(kind, emphasis)]["fill"]


def emphasis_scale(emphasis: str) -> float:
    """这档强调建议的尺寸倍数。**由布局层应用在盒子上**，不要写进元素宽高。"""
    try:
        return float(EMPHASIS[emphasis]["scale"])
    except KeyError:
        raise KeyError(
            f"未知 emphasis: {emphasis!r}；允许的取值：{sorted(EMPHASIS)}"
        ) from None


def emphasis_stroke_width(emphasis: str) -> float:
    """未知 emphasis 直接抛错 —— 与 kind / shape 同一条规矩。"""
    try:
        return float(EMPHASIS[emphasis]["stroke_width"])
    except KeyError:
        raise KeyError(
            f"未知 emphasis: {emphasis!r}；允许的取值：{sorted(EMPHASIS)}"
        ) from None


def edge_style_for(kind: str) -> str:
    try:
        return EDGE_KINDS[kind]["style"]
    except KeyError:
        raise KeyError(
            f"未知边 kind: {kind!r}；允许的取值：{sorted(EDGE_KINDS)}"
        ) from None


_rebind()


if __name__ == "__main__":
    print("视觉方向（5 个母体，各有 1~2 个 seed）")
    for name in available_directions():
        spec = VISUAL_DIRECTIONS[name]
        char = spec["character"]
        print(f"  {name:<11} {spec['zh']:<12} {char['temperature']:<12} "
              f"{char['canvas_character']:<14} 用于：{char['use_for']}")
        for seed_name, seed in spec["seeds"].items():
            print(f"      {seed_name:<18} 画布 {seed['canvas']}  墨 {seed['ink']}  "
                  f"主色 {seed['accent']}  警示 {seed['critical']}")
    print(f"\n视觉层级（{len(VISUAL_LEVELS)} 档）—— 当前方向 {active_direction()} / "
          f"seed {active_seed()}")
    for level in VISUAL_LEVELS:
        entry = LEVELS[level]
        print(f"    {level:<10} 描边 {entry['stroke']}  填充 {entry['fill']}")
    print("\n语义角色 → 默认层级（**没有角色默认拿到 accent**）")
    for kind, level in KINDS.items():
        print(f"    {kind:<10} → {level}")
    print("\n边型 —— 默认全部退出颜色竞争，语义靠线型")
    for kind, entry in EDGE_KINDS.items():
        print(f"    {kind:<10} {entry['zh']:<12} {entry['style']:<7} {entry['stroke']}")
    print("\n强调（层级 + 尺寸 + 线宽）")
    for name, entry in EMPHASIS.items():
        print(f"    {name:<10} 层级 {entry['level'] or '(随 kind)':<10} "
              f"尺寸 ×{entry['scale']}  线宽 {entry['stroke_width']}")
