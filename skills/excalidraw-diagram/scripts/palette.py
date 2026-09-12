#!/usr/bin/env python3
"""色板 —— 图表语义角色与颜色的**唯一真相源**。

为什么这一个文件同时定义两件事：`kind` 的封闭枚举 与 它的颜色映射，本来就该是
同一份数据的两个视图。分开定义只会制造第二个漂移点（`diagram-spec.md` 里写着
"唯一真相源"就是这个意思）。

校验器从这里读，不从别处抄；文档只描述规则，不复述取值表 —— 复述就会漂移。

**未知 kind 一律判失败，不 fallback。** fallback 之所以最危险，是因为它会让
"颜色必须落在色板内"这条校验**自己绕过自己**：程序补的默认色当然合法，校验通过了，
但语义已经错了。

取值全部来自 Excalidraw 内置色板。理由：与手绘线条风格协调、都是浅色（符合 vault 的
"浅色系 / 白底 / 排除深色"）、且用户在 Excalidraw 里认得出来。
"""

from __future__ import annotations

import contextlib

# kind → 语义角色 + 颜色。加第 7 项之前先问"能不能归并进已有类"：
# 超过 6 类语义就无法靠颜色区分了。
#
# 【用户指定】莫兰迪色系（去饱和、灰调、偏浅、清透）。这不是从别处继承的数，
# 是用户明确要的风格，所以优先级高于任何"前作用过的颜色"。
# 文字在其上的可读性已实测（对比度 ≥ 7:1），见 tests/test_palette.py。
# 信任状态总表见 references/diagram-spec.md。
# 描边：底色压暗而来，与自己的底色对比度**已实测** ≥ 3.0（非文字元素的 WCAG 门槛）。
# 在画布上也查过（3.5 ~ 4.5），不会“碰巧和背景同色”。
# 数字由 tests/test_palette.py 守住。
# kind → 语义角色 + 颜色。加第 7 项之前先问"能不能归并进已有类"：
# 超过 6 类语义就无法靠颜色区分了。
#
# 【用户指定】莫兰迪色系（去饱和、灰调、偏浅、清透）。这不是从别处继承的数，
# 是用户明确要的风格，所以优先级高于任何"前作用过的颜色"。
#
# 描边保持柔和**且保留色相**。曾经试过把描边压到与底色 3:1 对比度，结果六条
# 全部变成近似的深灰（#8A857E / #71797D / #77737B …）—— 色相识别没了，
# 而那正是客户要的风格。所以判据改成：
#   文字 vs 底色 ≥ 4.5（WCAG AA，实测 6.15~7.79）
#   描边 vs 底色 ≥ 1.8（框边界看得见；实测 ~2.4）
#   底色 vs 画布 ΔE ≥ 5（浅色块也要从背景里分得出来）
# 全部由 tests/test_palette.py 守住。
# 当前主题的颜色。由 `_rebind()` 在导入时与切换主题时填充 ——
# 声明放这里（而不是文件末尾），是为了让静态检查看得到这两个名字：
# 声明放在使用之后，运行时没问题，但分析会说"未绑定"。
KINDS: dict[str, dict[str, str]] = {}
EDGE_KINDS: dict[str, dict[str, str]] = {}
CANVAS: dict = {}

# ── 主题：`颜色 = THEMES[主题名][语义角色]` ─────────────────────
#
# 落地机制就是两层封闭枚举：主题名封闭、语义角色封闭 —— 既不给模型自由发挥的空间，
# 也不逼所有图一个样。
#
# **只列真正实现的。** 文档里另外几个是候选，没做出来的不往这里写 ——
# 写进去就会变成"指向一个空文件"的那种指针。
THEMES: dict[str, dict] = {
    "morandi": {"zh": "莫兰迪（默认，用户指定）"},
    "bright-clean": {
        "zh": "明亮清爽",
        "canvas": {"background": "#FFFFFF", "grid": "#EEF2F6", "text": "#2E3440"},
        "kinds": {
            "client":   {"zh": "客户端 / 角色", "stroke": "#6E8CA8", "background": "#D8E6F2"},
            "service":  {"zh": "核心服务",     "stroke": "#4F8A8B", "background": "#C9E4E2"},
            "data":     {"zh": "数据 / 存储",   "stroke": "#6B6FA8", "background": "#D5D6EE"},
            "async":    {"zh": "异步 / 消息",   "stroke": "#B08040", "background": "#F0DFC0"},
            "security": {"zh": "安全 / 鉴权",   "stroke": "#B06070", "background": "#F2D2D8"},
            "external": {"zh": "外部系统",     "stroke": "#5F8A5F", "background": "#D0E4CF"},
        },
        "edges": {
            "sync":     {"zh": "同步调用", "stroke": "#6E7A86", "style": "solid"},
            "data":     {"zh": "数据流",   "stroke": "#6B6FA8", "style": "solid"},
            "async":    {"zh": "异步消息", "stroke": "#B08040", "style": "dashed"},
            "optional": {"zh": "可选 / 间接", "stroke": "#5F8A5F", "style": "dashed"},
        },
    },
    "dark-tech": {
        "zh": "深色科技",
        "canvas": {"background": "#12161C", "grid": "#1D232B", "text": "#E6E9EE"},
        "kinds": {
            # 深色底上"彼此可区分"比浅色底更难：只靠色相不够，明度也要拉开。
            # 第一版六色都在 #1E~#36 的窄明度带里，两两 ΔE 最小只有 2.5（浅色主题是 6.7）——
            # 也就是说看着是六块差不多的深灰。这版把明度和色相一起拉开，ΔE 最小 7.8。
            "client":   {"zh": "客户端 / 角色", "stroke": "#8FA8C0", "background": "#2C3644"},
            "service":  {"zh": "核心服务",     "stroke": "#6FA8D0", "background": "#13293A"},
            "data":     {"zh": "数据 / 存储",   "stroke": "#9B8FD0", "background": "#2F2545"},
            "async":    {"zh": "异步 / 消息",   "stroke": "#D0A56F", "background": "#432E12"},
            "security": {"zh": "安全 / 鉴权",   "stroke": "#D08F8F", "background": "#431F2A"},
            "external": {"zh": "外部系统",     "stroke": "#7FB08F", "background": "#12301C"},
        },
        "edges": {
            "sync":     {"zh": "同步调用", "stroke": "#A8B0BC", "style": "solid"},
            "data":     {"zh": "数据流",   "stroke": "#9B8FD0", "style": "solid"},
            "async":    {"zh": "异步消息", "stroke": "#D0A56F", "style": "dashed"},
            "optional": {"zh": "可选 / 间接", "stroke": "#7FB08F", "style": "dashed"},
        },
    },
}
DEFAULT_THEME = "morandi"

# 当前生效的主题。为什么用模块级状态而不是把主题一路传参：
# `stroke_for` / `background_for` / `CANVAS` 被几十处调用，全改成带主题参数会把
# "颜色"这件事的调用面铺得很大，而主题在**一次出图里只有一个**。
# 所以入口处 `use_theme()` 定一次，其余照旧读。
# **测试里必须用 `theme_context()`** —— 否则用例之间会互相污染。
_active = DEFAULT_THEME


# 图类型 → 建议主题（#76）。**只引用已实现的主题** —— 指向一个不存在的主题名
# 就是"指向空文件的指针"，写规格的人会照着一个永远报错的值去写。
#
# 这是**建议**，不是默认：默认永远是 `morandi`（用户明确指定过）。
# 想用建议就必须显式写 `"theme": "auto"` —— 自动覆盖用户的选择是错的。
THEME_SUGGESTION: dict[str, str] = {
    "flow": "bright-clean",          # 流程要明快、有节奏
    "mindmap": "bright-clean",       # 结构图要清爽
    "architecture": "morandi",       # 技术架构要克制、耐看
    "component": "morandi",
    "sequence": "morandi",
    "dependency": "morandi",
    "state": "morandi",
    "network": "morandi",
}
AUTO_THEME = "auto"


def suggest_theme(diagram_type: str | None) -> str:
    """按图类型给一个主题建议。没收录的类型回落到默认主题。"""
    return THEME_SUGGESTION.get(diagram_type or "", DEFAULT_THEME)


def available_themes() -> list[str]:
    return sorted(THEMES)


def is_known_theme(name: str) -> bool:
    """`auto` 也算已知 —— 它是"按图类型自己挑"，不是未知值。"""
    return name in THEMES or name == AUTO_THEME
    return sorted(THEMES)


def active_theme() -> str:
    return _active


def use_theme(name: str | None) -> str:
    """切换主题。未知主题名**判失败不 fallback** —— 同 kind / shape 一条规矩。

    `"auto"` 是特例：按图类型查表（见 `suggest_theme`）。它必须由调用方把图类型
    一起传进来，所以 emit 里是 `use_theme(spec.get("theme"), spec.get("type"))`。
    """
    global _active
    name = name if name else DEFAULT_THEME
    if name == AUTO_THEME:
        name = suggest_theme(_auto_type)
    if name not in THEMES:
        raise KeyError(f"未知主题 {name!r}；可用的：{available_themes()} 或 {AUTO_THEME!r}")
    _active = name
    _rebind()
    return name


_auto_type: str | None = None


def set_auto_type(diagram_type: str | None) -> None:
    """给 `"auto"` 用：记下当前图类型。"""
    global _auto_type
    _auto_type = diagram_type


@contextlib.contextmanager
def theme_context(name: str):
    """测试用：进出一个主题，出来时恢复原状。"""
    before = active_theme()
    use_theme(name)
    try:
        yield name
    finally:
        use_theme(before)

_MORANDI_KINDS: dict[str, dict[str, str]] = {
    "client": {
        "zh": "用户 / 客户端 / 浏览器",
        "stroke": "#A89E92",
        "background": "#F2EBDF",
    },
    "service": {
        "zh": "服务 / API / 进程",
        "stroke": "#7C93A6",
        "background": "#CBD8E0",
    },
    "data": {
        "zh": "数据库 / 持久化存储",
        "stroke": "#8B7FA0",
        "background": "#D8D0DE",
    },
    "async": {
        "zh": "消息队列 / 缓存 / 事件通道",
        "stroke": "#B08A6C",
        "background": "#EBDACB",
    },
    "security": {
        "zh": "鉴权 / 网关 / 密钥",
        "stroke": "#AC8383",
        "background": "#E8D2D2",
    },
    "external": {
        "zh": "外部系统 / 第三方 / 不受控边界",
        "stroke": "#809081",
        "background": "#D1DBD4",
    },
}

# 边（箭头）的样式：语义 → 线型。和前作一样保留"虚实表达同步/异步"的区分，
# 但**不给颜色自由度** —— 边一律用中性色，颜色只用于节点语义。
_MORANDI_EDGES: dict[str, dict[str, str]] = {
    "sync": {"zh": "同步调用", "style": "solid", "stroke": "#8A8681"},
    "data": {"zh": "数据读写", "style": "solid", "stroke": "#8B7FA0"},
    "async": {"zh": "异步 / 事件", "style": "dashed", "stroke": "#AC896F"},
    "optional": {"zh": "可选 / 条件分支", "style": "dashed", "stroke": "#849383"},
}

MAX_KINDS = 6

# 画布与视觉风格（原本写在 PKB 的 resource-notes.md，已收拢到这里）。
_MORANDI_CANVAS = {
    "background": "#FDFCFA",   # 暖白，不是纯白 —— 莫兰迪底色偏暖
    "grid": "#F1EDE8",
    # 节点里的文字色。暖调深灰，不用纯黑 —— 纯黑与莫兰迪的柔和底色打架。
    # 与 6 种底色的对比度**已实测**：6.15 ~ 7.78（全部达 WCAG AA；client 达 AAA）。
    # 数字由 tests/test_palette.py 守住，不是写在注释里的口号。
    "text": "#4A4744",
    "stroke_style": "hand-drawn",
    "font_family": 2,  # native Excalidraw scene 里 CJK-safe 的那一档
}

# 明确排除的风格。不只是审美偏好 —— 它们都会破坏"这张图是拿来理解系统的"这个前提。
EXCLUDED_STYLES = (
    "灰色底色",
    "深色背景",
    "海报风",
    "3D",
    "商业宣传风",
    "装饰性插画",
    "为了显得丰富而添加的重复图",
)


# 强调层级 —— 封闭枚举。视觉重点靠“描边粗细 + 填充浓度”表达，**不靠尺寸**。
#
# 为什么尺寸不参与：尺寸会进尺寸链（文字 → 盒子 → 坐标）。改它就得重新验证
# 12px 最小间隙那一套阈值，而“哪几处必须一眼看到”这件事本身不需要动几何。
#
# 三档的填充都由 `emphasis_fill()` 从色板**派生**，没有第二份表：
#   primary 向自己的描边色靠一点 → 颜色更实（“更有颜色 = 更重要”，
#           适合浅色底板，不能用“更深 = 更重要”那套）
#   normal  就是色板原色（所以默认档与加入 emphasis 之前的观感**完全一致**）
#   muted   向画布色靠拢一半以上 → 退到背景里
EMPHASIS: dict[str, dict] = {
    "primary": {"zh": "重点", "stroke_width": 2.5, "to_stroke": 0.14},
    "normal": {"zh": "常规", "stroke_width": 1.5, "to_stroke": 0.00},
    "muted": {"zh": "次要", "stroke_width": 1.0, "to_canvas": 0.55},
}
DEFAULT_EMPHASIS = "normal"


# ── 颜色数学：**唯一实现**在 palette 里 ────────────────────────
# 以前这套公式只写在 tests/test_palette.py 里，于是"检查颜色"的地方（图标撞色、
# 报告里的可读性）只能自己再写一份 —— 两份必然漂移，而漂移的那一份会让两边
# 给出不同结论（这个坑在这个项目里踩过好几次）。
# 测试仍然会用已知值把这几把尺子钉住（白对黑 = 21 之类），尺子本身照样是验过的。
def hex_to_rgb(colour: str) -> tuple[int, int, int]:
    if not colour.startswith("#") or len(colour) != 7:
        raise ValueError(f"不是 #RRGGBB：{colour!r}")
    return (int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16))


def relative_luminance(colour: str) -> float:
    channels = []
    for value in hex_to_rgb(colour):
        c = value / 255.0
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast(a: str, b: str) -> float:
    """WCAG 对比度。1.0 = 完全一样，21 = 纯黑对纯白。"""
    la, lb = relative_luminance(a), relative_luminance(b)
    high, low = max(la, lb), min(la, lb)
    return (high + 0.05) / (low + 0.05)


def saturation(colour: str) -> float:
    """**HSV** 里的 S（`(max-min)/max`）。莫兰迪那一族靠它判"去饱和"。

    ⚠ 别"顺手改成 HSL"：搬进本文件时我就这么干过一次，三个"填充要去饱和"的用例
    立刻变红 —— 两种饱和度的定义不同（HSL 的 S 在浅色上数值差别很大，
    而莫兰迪全是浅色）。测试挡住了它，但这条注释是为了别再犯第二次。
    """
    r, g, b = (v / 255.0 for v in hex_to_rgb(colour))
    high = max(r, g, b)
    if high <= 0:
        return 0.0
    return (high - min(r, g, b)) / high


def to_lab(colour: str) -> tuple[float, float, float]:
    r, g, b = (v / 255.0 for v in hex_to_rgb(colour))

    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = lin(r), lin(g), lin(b)
    x = (r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047
    y = r * 0.2126 + g * 0.7152 + b * 0.0722
    z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883

    def f(t: float) -> float:
        return t ** (1.0 / 3.0) if t > 0.008856 else 7.787 * t + 16.0 / 116.0

    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def delta_e(a: str, b: str) -> float:
    """CIE76 色差。两个颜色"看起来差多少"，跟亮度差不是一回事。"""
    la, lb = to_lab(a), to_lab(b)
    return sum((x - y) ** 2 for x, y in zip(la, lb)) ** 0.5


def _parse_hex(value: str) -> tuple[int, int, int]:
    raw = value.lstrip("#")
    if len(raw) != 6:
        raise ValueError(f"只接受 #RRGGBB，收到 {value!r}")
    return (int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16))


def _mix(a: str, b: str, ratio: float) -> str:
    """把 `a` 按 `ratio` 往 `b` 混。ratio=0 就是 a 本身。"""
    ra, ga, ba = _parse_hex(a)
    rb, gb, bb = _parse_hex(b)
    blend = lambda x, y: round(x + (y - x) * ratio)  # noqa: E731
    return f"#{blend(ra, rb):02X}{blend(ga, gb):02X}{blend(ba, bb):02X}"


def emphasis_stroke_width(emphasis: str) -> float:
    """未知 emphasis 直接抛错 —— 与 kind / shape 同一条规矩。"""
    try:
        return EMPHASIS[emphasis]["stroke_width"]
    except KeyError:
        raise KeyError(
            f"未知 emphasis: {emphasis!r}；允许的取值：{sorted(EMPHASIS)}"
        ) from None


def emphasis_fill(kind: str, emphasis: str) -> str:
    """这个语义角色在这档强调下的填充色。**唯一来源是色板本身。**

    未知 kind / emphasis 都抛错，不 fallback（fallback 会让“颜色必须落在板内”
    这条校验自己绕过自己）。
    """
    if emphasis not in EMPHASIS:
        raise KeyError(
            f"未知 emphasis: {emphasis!r}；允许的取值：{sorted(EMPHASIS)}"
        )
    base = background_for(kind)
    rule = EMPHASIS[emphasis]
    if "to_stroke" in rule:
        return _mix(base, stroke_for(kind), rule["to_stroke"])
    if "to_canvas" in rule:
        return _mix(base, CANVAS["background"], rule["to_canvas"])
    return base


def stroke_for(kind: str) -> str:
    """取节点边框色。未知 kind 直接抛错 —— 不 fallback。"""
    try:
        return KINDS[kind]["stroke"]
    except KeyError:
        raise KeyError(
            f"未知 kind: {kind!r}；允许的取值：{sorted(KINDS)}"
        ) from None


def background_for(kind: str) -> str:
    """取节点填充色。未知 kind 直接抛错 —— 不 fallback。"""
    try:
        return KINDS[kind]["background"]
    except KeyError:
        raise KeyError(
            f"未知 kind: {kind!r}；允许的取值：{sorted(KINDS)}"
        ) from None


def edge_style_for(kind: str) -> str:
    try:
        return EDGE_KINDS[kind]["style"]
    except KeyError:
        raise KeyError(
            f"未知边 kind: {kind!r}；允许的取值：{sorted(EDGE_KINDS)}"
        ) from None


if __name__ == "__main__":
    # 人类可读的清单：python3 palette.py
    print(f"节点语义（{len(KINDS)} 类，上限 {MAX_KINDS}）")
    for k, v in KINDS.items():
        print(f"  {k:<9} {v['zh']:<24} 边框 {v['stroke']}  填充 {v['background']}")
    print(f"\n边语义（{len(EDGE_KINDS)} 类）")
    for k, v in EDGE_KINDS.items():
        print(f"  {k:<9} {v['zh']:<12} {v['style']:<7} {v['stroke']}")


def _rebind() -> None:
    """把当前主题的颜色装进 KINDS / EDGE_KINDS / CANVAS。

    morandi 的定义就写在本文件里（历史原因），别的主题从 THEMES 取 ——
    这里做的是"两份取一份"。
    """
    global KINDS, EDGE_KINDS, CANVAS
    if _active == "morandi":
        KINDS = dict(_MORANDI_KINDS)
        EDGE_KINDS = dict(_MORANDI_EDGES)
        CANVAS = dict(_MORANDI_CANVAS)
        return
    spec = THEMES[_active]
    KINDS = {k: dict(v) for k, v in spec["kinds"].items()}
    EDGE_KINDS = {k: dict(v) for k, v in spec["edges"].items()}
    CANVAS = {**spec["canvas"],
              "stroke_style": _MORANDI_CANVAS["stroke_style"],
              "font_family": _MORANDI_CANVAS["font_family"]}


_rebind()
