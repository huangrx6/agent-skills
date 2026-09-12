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
KINDS: dict[str, dict[str, str]] = {
    "client": {
        "zh": "用户 / 客户端 / 浏览器",
        "stroke": "#1e1e1e",
        "background": "#ffffff",
    },
    "service": {
        "zh": "服务 / API / 进程",
        "stroke": "#1971c2",
        "background": "#a5d8ff",
    },
    "data": {
        "zh": "数据库 / 持久化存储",
        "stroke": "#6741d9",
        "background": "#d0bfff",
    },
    "async": {
        "zh": "消息队列 / 缓存 / 事件通道",
        "stroke": "#e8590c",
        "background": "#ffd8a8",
    },
    "security": {
        "zh": "鉴权 / 网关 / 密钥",
        "stroke": "#c2255c",
        "background": "#ffdeeb",
    },
    "external": {
        "zh": "外部系统 / 第三方 / 不受控边界",
        "stroke": "#868e96",
        "background": "#f1f3f5",
    },
}

# 边（箭头）的样式：语义 → 线型。和前作一样保留"虚实表达同步/异步"的区分，
# 但**不给颜色自由度** —— 边一律用中性色，颜色只用于节点语义。
EDGE_KINDS: dict[str, dict[str, str]] = {
    "sync": {"zh": "同步调用", "style": "solid", "stroke": "#1e1e1e"},
    "data": {"zh": "数据读写", "style": "solid", "stroke": "#6741d9"},
    "async": {"zh": "异步 / 事件", "style": "dashed", "stroke": "#e8590c"},
    "optional": {"zh": "可选 / 条件分支", "style": "dashed", "stroke": "#868e96"},
}

MAX_KINDS = 6

# 画布与视觉风格（原本写在 PKB 的 resource-notes.md，已收拢到这里）。
CANVAS = {
    "background": "#ffffff",
    "grid": "#f1f3f5",
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
