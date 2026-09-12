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
LEVELS: dict[str, dict[str, str]] = {}   # 层级名 → {stroke, fill}
KINDS: dict[str, str] = {}               # 语义角色 → **层级名**（不是颜色）
EDGE_KINDS: dict[str, dict[str, str]] = {}
CANVAS: dict = {}

# ⚠️ **本文件有一个历史特例：`morandi`。**
# 它是默认主题，但定义**不在** `THEMES` 里 —— `THEMES["morandi"]` 只有一个名字，
# 真正的颜色在下面的 `_MORANDI_KINDS` / `_MORANDI_EDGES` / `_MORANDI_CANVAS` 三个常量里，
# `_rebind()` 对它单独开了一个分支。
#
# **动 KINDS / EDGE_KINDS 结构的人必须同时改这三个常量。**
# 否则新加的 kind 在里面没有对应项 → 未知 kind 会抛错，不是静默降级（这点还好），
# 但错误信息会指向主题而不是"你漏改了一个常量"。
#
# 这是封闭枚举里唯一的例外分支，是未来最容易漏改的地方。
# 待办：把 morandi 迁进 `THEMES` 的标准结构，去掉 `_rebind()` 的分支。

# ── 主题：`颜色 = THEMES[主题名][语义角色]` ─────────────────────
#
# 落地机制就是两层封闭枚举：主题名封闭、语义角色封闭 —— 既不给模型自由发挥的空间，
# 也不逼所有图一个样。
#
# **只列真正实现的。** 文档里另外几个是候选，没做出来的不往这里写 ——
# 写进去就会变成"指向一个空文件"的那种指针。
#
# **语义不直接决定颜色。** 中间隔一层"视觉层级"：
#
#   kind ──(语义)──→ 默认层级 ──┐
#                               ├──→ THEMES[主题][层级] ──→ 描边 + 填充
#   emphasis ──(强调)──────────┘
#
# 为什么必须有这一层：六种语义各绑一套颜色，工程上干净，**视觉上一定丑** ——
# 实测旧色板的六种填充色相跨度 310°（占整个色环 86%），眼睛读到的是"六个颜色"
# 而不是"一个结构"；一张 14 节点的架构图会出现 6 种节点色 + 3 种边色。
#
# 目标是**视觉上只有少数几个颜色，语义上仍然能区分** —— 这两件事不一样。
# 层级只有 5 档，其中 neutral / tint / accent 承担绝大多数节点，
# secondary 少量，critical 只在真的异常时用。
VISUAL_LEVELS = ("neutral", "tint", "accent", "secondary", "critical")
_LEVEL_ORDER = {name: i for i, name in enumerate(VISUAL_LEVELS)}
DEFAULT_LEVEL = "tint"

THEMES: dict[str, dict] = {
    "morandi": {
        "zh": "莫兰迪（默认，用户指定）",
        "canvas": {"background": "#FDFCFA", "grid": "#F1EDE8", "text": "#4A4744"},
        "levels": {
            "neutral":   {"stroke": "#A9A49C", "fill": "#FFFFFF"},
            "tint":      {"stroke": "#A9A49C", "fill": "#F4F1EC"},
            "accent":    {"stroke": "#7C93A6", "fill": "#CBD8E0"},
            "secondary": {"stroke": "#8B7FA0", "fill": "#DDD6E4"},
            "critical":  {"stroke": "#B0888A", "fill": "#F2DEDA"},
        },
        "kinds": {
            "client":   "tint",
            "service":  "accent",
            "data":     "tint",
            "async":    "secondary",
            "security": "neutral",
            "external": "neutral",
            # 通用角色：状态机里的状态、思维导图的叶子、任何"就是个节点"的东西。
            # 它存在是因为分类学覆盖不到所有图型 —— 状态机里的节点不是"服务"，
            # 硬套一个角色会让整张图变成强调色（实测过：04-state 75% 是 accent）。
            # 通用角色：流水线步骤 / 状态机状态 / 普通模块 / 思维导图叶子 ——
            # 任何“就是个节点、不是那个特殊角色”的东西。没有它的时候这些节点
            # 只能硬套 service，整张图就变成强调色（实测 04-state 75%、05-network 75%）。
            # 注意：**加角色不会加颜色** —— 角色映射到已有层级，颜色数由层级封顶。
            "plain":    "tint",
        },
        "edges": {
            "sync":     {"zh": "同步调用", "stroke": "#A9A49C", "style": "solid"},
            "data":     {"zh": "数据读写", "stroke": "#A9A49C", "style": "solid"},
            "async":    {"zh": "异步 / 事件", "stroke": "#A9A49C", "style": "dashed"},
            "optional": {"zh": "可选 / 条件分支", "stroke": "#A9A49C", "style": "dashed"},
        },
    },
    "bright-clean": {
        "zh": "明亮清爽",
        "canvas": {"background": "#FFFFFF", "grid": "#EEF2F6", "text": "#2E3440"},
        "levels": {
            "neutral":   {"stroke": "#8A94A0", "fill": "#FFFFFF"},
            "tint":      {"stroke": "#8A94A0", "fill": "#EDF2F5"},
            "accent":    {"stroke": "#3F7C8C", "fill": "#C9E4E2"},
            "secondary": {"stroke": "#6B6FA8", "fill": "#DFE1F2"},
            "critical":  {"stroke": "#B06070", "fill": "#F5DDE1"},
        },
        # 语义角色 → **默认层级**。注意大多数角色落在 neutral / tint：
        # 一张图里"有颜色的"节点应该是少数，颜色才有信息量。
        "kinds": {
            "client":   "tint",
            "service":  "accent",
            "data":     "tint",
            "async":    "secondary",
            "security": "neutral",
            "external": "neutral",
            # 通用角色：状态机里的状态、思维导图的叶子、任何"就是个节点"的东西。
            # 它存在是因为分类学覆盖不到所有图型 —— 状态机里的节点不是"服务"，
            # 硬套一个角色会让整张图变成强调色（实测过：04-state 75% 是 accent）。
            # 通用角色：流水线步骤 / 状态机状态 / 普通模块 / 思维导图叶子 ——
            # 任何“就是个节点、不是那个特殊角色”的东西。没有它的时候这些节点
            # 只能硬套 service，整张图就变成强调色（实测 04-state 75%、05-network 75%）。
            # 注意：**加角色不会加颜色** —— 角色映射到已有层级，颜色数由层级封顶。
            "plain":    "tint",
        },
        # 默认连线**统一中性**，只有真的需要区分才上色 ——
        # 否则会出现"蓝框─蓝线、绿框─绿线"，那是技术 PPT 风。
        "edges": {
            "sync":     {"zh": "同步调用", "stroke": "#8A94A0", "style": "solid"},
            "data":     {"zh": "数据流",   "stroke": "#8A94A0", "style": "solid"},
            "async":    {"zh": "异步消息", "stroke": "#8A94A0", "style": "dashed"},
            "optional": {"zh": "可选 / 间接", "stroke": "#8A94A0", "style": "dashed"},
        },
    },
    "dark-tech": {
        "zh": "深色科技",
        "canvas": {"background": "#12161C", "grid": "#1D232B", "text": "#E6E9EE"},
        "levels": {
            "neutral":   {"stroke": "#5A6472", "fill": "#181D24"},
            "tint":      {"stroke": "#5A6472", "fill": "#2A3540"},
            "accent":    {"stroke": "#6FA8D0", "fill": "#13293A"},
            "secondary": {"stroke": "#9B8FD0", "fill": "#2A2340"},
            "critical":  {"stroke": "#D08F8F", "fill": "#3A1D26"},
        },
        "kinds": {
            "client":   "tint",
            "service":  "accent",
            "data":     "tint",
            "async":    "secondary",
            "security": "neutral",
            "external": "neutral",
            # 通用角色：状态机里的状态、思维导图的叶子、任何"就是个节点"的东西。
            # 它存在是因为分类学覆盖不到所有图型 —— 状态机里的节点不是"服务"，
            # 硬套一个角色会让整张图变成强调色（实测过：04-state 75% 是 accent）。
            # 通用角色：流水线步骤 / 状态机状态 / 普通模块 / 思维导图叶子 ——
            # 任何“就是个节点、不是那个特殊角色”的东西。没有它的时候这些节点
            # 只能硬套 service，整张图就变成强调色（实测 04-state 75%、05-network 75%）。
            # 注意：**加角色不会加颜色** —— 角色映射到已有层级，颜色数由层级封顶。
            "plain":    "tint",
        },
        "edges": {
            "sync":     {"zh": "同步调用", "stroke": "#7A828E", "style": "solid"},
            "data":     {"zh": "数据流",   "stroke": "#7A828E", "style": "solid"},
            "async":    {"zh": "异步消息", "stroke": "#7A828E", "style": "dashed"},
            "optional": {"zh": "可选 / 间接", "stroke": "#7A828E", "style": "dashed"},
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

# 画布与画风：与主题无关的部分（三个主题共用）。画风偏好和字体都不该随配色变。
CANVAS_STYLE = {
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


# ── 强调：**在层级上上下挪一档**，而不是另给一套颜色 ──────────────
#
# 两个能力分开：
#   `kind`     决定**默认层级**（这是语义，"这是个什么角色"）
#   `emphasis` 决定**在这基础上提/降多少**（这是强调，"这一处要不要突出"）
#
# 视觉重点靠"描边粗细 + 层级升降"表达，**不靠尺寸** —— 尺寸会进尺寸链
# （文字 → 盒子 → 坐标），改它就得重新验证 12px 最小间隙那一套阈值。
EMPHASIS: dict[str, dict] = {
    "muted":    {"zh": "次要", "stroke_width": 1.0, "promote": -1},
    "normal":   {"zh": "常规", "stroke_width": 1.5, "promote": 0},
    "primary":  {"zh": "重点", "stroke_width": 2.5, "promote": 1},
    # 警示是**唯一**能进 critical 的入口，而且只给"真的异常/危险"用。
    # 不要把某个语义角色永久绑成红色（"security = 红"就是那种绑定）。
    "critical": {"zh": "警示", "stroke_width": 2.5, "promote": 0, "level": "critical"},
}
DEFAULT_EMPHASIS = "normal"


def level_for(kind: str, emphasis: str = DEFAULT_EMPHASIS) -> str:
    """这个角色在这档强调下，落在哪个视觉层级。**颜色的唯一入口。**

    未知 kind / emphasis 都抛错，不 fallback（fallback 会让"颜色必须落在板内"
    这条校验自己绕过自己）。

    提级**封顶在 secondary**：普通节点被"强调"不该变成警示色 ——
    critical 只能由 `emphasis: critical` 显式指定。
    """
    if emphasis not in EMPHASIS:
        raise KeyError(f"未知 emphasis: {emphasis!r}；允许的取值：{sorted(EMPHASIS)}")
    if kind not in KINDS:
        raise KeyError(f"未知 kind: {kind!r}；允许的取值：{sorted(KINDS)}")
    if "level" in EMPHASIS[emphasis]:
        return EMPHASIS[emphasis]["level"]
    index = _LEVEL_ORDER[KINDS[kind]] + EMPHASIS[emphasis]["promote"]
    ceiling = _LEVEL_ORDER["secondary"]
    return VISUAL_LEVELS[max(0, min(index, ceiling))]


def stroke_for(kind: str, emphasis: str = DEFAULT_EMPHASIS) -> str:
    """取节点边框色。未知值直接抛错 —— 不 fallback。"""
    return LEVELS[level_for(kind, emphasis)]["stroke"]


def fill_for(kind: str, emphasis: str = DEFAULT_EMPHASIS) -> str:
    """取节点填充色。**唯一来源是主题的层级表**，没有第二张表。"""
    return LEVELS[level_for(kind, emphasis)]["fill"]


def emphasis_stroke_width(emphasis: str) -> float:
    """未知 emphasis 直接抛错 —— 与 kind / shape 同一条规矩。"""
    try:
        return EMPHASIS[emphasis]["stroke_width"]
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


def _rebind() -> None:
    """把当前主题装进 LEVELS / KINDS（角色→层级）/ EDGE_KINDS / CANVAS。

    morandi 现在和其他主题**同一套结构**，这里不再有特例分支
    （以前它的定义散在三个独立常量里，是封闭枚举里唯一的例外）。
    """
    global LEVELS, KINDS, EDGE_KINDS, CANVAS
    spec = THEMES[_active]
    LEVELS = {k: dict(v) for k, v in spec["levels"].items()}
    KINDS = dict(spec["kinds"])
    EDGE_KINDS = {k: dict(v) for k, v in spec["edges"].items()}
    CANVAS = {**spec["canvas"], **CANVAS_STYLE}


_rebind()


if __name__ == "__main__":
    # 人类可读的清单：python3 palette.py
    print(f"视觉层级（{len(VISUAL_LEVELS)} 档）")
    for name in VISUAL_LEVELS:
        v = LEVELS[name]
        print(f"  {name:<10} 描边 {v['stroke']}  填充 {v['fill']}")
    print(f"\n语义角色（{len(KINDS)} 类）—— 它们映射到上面的层级（角色数不设限，颜色只有 5 档）")
    for k, level in KINDS.items():
        v = LEVELS[level]
        print(f"  {k:<9} → {level:<9} 描边 {v['stroke']}  填充 {v['fill']}")
    print(f"\n边型（{len(EDGE_KINDS)} 类）—— 默认全部中性，只有线型表达语义")
    for k, v in EDGE_KINDS.items():
        print(f"  {k:<9} {v['zh']:<12} {v['style']:<7} {v['stroke']}")
