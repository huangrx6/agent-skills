"""结构指纹：判断两个候选"是不是同一个结构"。

**为什么需要它**：页级要给作者 3 个候选，但"换了个渲染变体"不等于换了结构。
镜像（图在左 / 图在右）、只改 DOM 顺序、只换一档栏宽 —— 这些在观感上是同一个
构图，摆三个近亲候选等于没给选择。判据要能*算*出来，而不是靠名字看起来不同。

**判据**（`composition`）：

    family + 区域跨度的**排序后**多重集

镜像只换顺序、不换跨度集合 → 同一个 composition（这正是"镜像不算新结构"）。
跨度不同（6+6 vs 7+5）→ 不同 composition；family 不同（split vs hero）→ 不同。

**一处声明**：`STRUCTURES` 同时是"结构指纹"和"页面契约（各区域文案预算）"的
来源 —— 区域跨度决定这一栏能放多少字，两份表各写一份必然写岔。

边界：这里只描述**渲染器真会发出的结构**（`render.IMAGE_LAYOUTS` /
`TWO_COL_LAYOUTS` 是能力清单）。指纹不认识的名字 → `None`，不猜。
"""
from __future__ import annotations

# 区域：名字 + 栅格跨度（12 栅制）。`role` 是语义角色，给契约与门共用。
_MAIN = "main"
_IMAGE = "image"
_HERO = "hero"

# 渲染器能力清单 ↔ 结构声明。key 是 spec 里写的 layout 名。
STRUCTURES: dict[str, dict[str, dict]] = {
    "content-image": {
        "visual-right": {
            "family": "split",
            "direction": "row",
            "regions": ({"name": _MAIN, "role": "text", "span": 7},
                        {"name": _IMAGE, "role": "image", "span": 5}),
        },
        "visual-left": {
            # 与 visual-right **同构图**（镜像）：跨度集合一样，只换顺序。
            "family": "split",
            "direction": "row",
            "regions": ({"name": _IMAGE, "role": "image", "span": 5},
                        {"name": _MAIN, "role": "text", "span": 7}),
        },
        "even": {
            "family": "split",
            "direction": "row",
            "regions": ({"name": _MAIN, "role": "text", "span": 6},
                        {"name": _IMAGE, "role": "image", "span": 6}),
        },
        "visual-wide": {
            # 4+8：与 6+6 / 7+5 是**不同构图**（跨度集合不同）。
            "family": "split",
            "direction": "row",
            "regions": ({"name": _MAIN, "role": "text", "span": 4},
                        {"name": _IMAGE, "role": "image", "span": 8}),
        },
        "hero": {
            "family": "hero",
            "direction": "column",
            "regions": ({"name": _HERO, "role": "image", "span": 12},
                        {"name": _MAIN, "role": "text", "span": 12}),
        },
    },
    "two-column": {
        "even": {
            "family": "columns",
            "direction": "columns",
            "regions": ({"name": "col0", "role": "text", "span": 6},
                        {"name": "col1", "role": "text", "span": 6}),
        },
        "lean-left": {
            "family": "columns",
            "direction": "columns",
            "regions": ({"name": "col0", "role": "text", "span": 7},
                        {"name": "col1", "role": "text", "span": 5}),
        },
        "lean-right": {
            # 与 lean-left 同构图（跨度集合相同）。
            "family": "columns",
            "direction": "columns",
            "regions": ({"name": "col0", "role": "text", "span": 5},
                        {"name": "col1", "role": "text", "span": 7}),
        },
        "lean-hard-left": {
            "family": "columns",
            "direction": "columns",
            "regions": ({"name": "col0", "role": "text", "span": 4},
                        {"name": "col1", "role": "text", "span": 8}),
        },
        "lean-hard-right": {
            # 与 lean-hard-left 同构图（镜像）。
            "family": "columns",
            "direction": "columns",
            "regions": ({"name": "col0", "role": "text", "span": 8},
                        {"name": "col1", "role": "text", "span": 4}),
        },
    },
}


def structure(page_type: str, layout: str) -> dict | None:
    """这个 (页型, layout) 的结构声明；不认识 → None（不猜）。"""
    table = STRUCTURES.get(page_type)
    if not table or not isinstance(layout, str):
        return None
    return table.get(layout)


def composition(page_type: str, layout: str) -> str | None:
    """结构指纹：`family|span,span,…`（跨度排序 → 镜像折叠成同一个）。

    不认识的 (页型, layout) → None：调用方自己决定是报错还是跳过。
    """
    st = structure(page_type, layout)
    if st is None:
        return None
    spans = ",".join(str(r["span"]) for r in sorted(st["regions"],
                                                     key=lambda r: r["span"]))
    return f"{st['family']}|{spans}"


def fingerprint(page_type: str, layout: str) -> dict | None:
    """给报告/诊断用的完整指纹（含区域顺序，便于人读"怎么镜像的"）。"""
    st = structure(page_type, layout)
    comp = composition(page_type, layout)
    if st is None or comp is None:
        return None
    return {
        "pageType": page_type,
        "layout": layout,
        "family": st["family"],
        "direction": st["direction"],
        "regions": [f"{r['name']}:{r['span']}" for r in st["regions"]],
        "composition": comp,
    }


def distinct(page_type: str, layouts: list) -> list:
    """按 composition 去重（保序，每个构图留第一个）。

    镜像折叠在这里生效：`visual-right` 先出现时，`visual-left` 不会再占一个候选位。
    不认识的名字**保留**（宁可多给一个候选，也不要静默吞掉渲染器真支持的东西）。
    """
    seen: set[str] = set()
    out: list = []
    for name in layouts:
        comp = composition(page_type, name) or f"unknown|{name}"
        if comp in seen:
            continue
        seen.add(comp)
        out.append(name)
    return out


def mirror_of(page_type: str, layout: str) -> str | None:
    """同构图里的另一个名字（镜像），没有就 None。"""
    target = composition(page_type, layout)
    if target is None:
        return None
    table = STRUCTURES.get(page_type) or {}
    for name in table:
        if name != layout and composition(page_type, name) == target:
            return name
    return None


def region_budget_key(page_type: str, layout: str) -> dict:
    """区域跨度表：`{区域名: {role, span}}`（契约按跨度定文案预算时读它）。"""
    st = structure(page_type, layout)
    if st is None:
        return {}
    return {r["name"]: {"role": r["role"], "span": r["span"]} for r in st["regions"]}


__all__ = ["STRUCTURES", "structure", "composition", "fingerprint",
           "distinct", "mirror_of", "region_budget_key"]
