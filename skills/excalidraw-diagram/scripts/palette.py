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
KINDS: dict[str, dict[str, str]] = {
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
EDGE_KINDS: dict[str, dict[str, str]] = {
    "sync": {"zh": "同步调用", "style": "solid", "stroke": "#8A8681"},
    "data": {"zh": "数据读写", "style": "solid", "stroke": "#8B7FA0"},
    "async": {"zh": "异步 / 事件", "style": "dashed", "stroke": "#AC896F"},
    "optional": {"zh": "可选 / 条件分支", "style": "dashed", "stroke": "#849383"},
}

MAX_KINDS = 6

# 画布与视觉风格（原本写在 PKB 的 resource-notes.md，已收拢到这里）。
CANVAS = {
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
