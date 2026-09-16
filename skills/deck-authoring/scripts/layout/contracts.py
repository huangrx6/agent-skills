"""页面契约：这一页**能装多少** —— 写内容前先读它，别写完再缩字号。

**为什么要有它**：修复梯里"缩字号"排在最后（第 13 位），而"装不下"这个数字
如果只在渲染后才知道，人就会倾向"压一压字号算了"。契约把它提前：**照预算写**。

**预算怎么来**（估算是估算，不装成精确）：

- 区域宽度：`grid.span(n)`（跨度的唯一来源）—— 双栏页按栏跨度，图页按文字栏跨度；
- 每行字数：按 CJK 全角估（1 个字 ≈ 1 个字号）；拉丁文实际更宽裕，所以这是**保守**估计；
- 可用高度：正文带 `CONTENT_BOTTOM − CONTENT_TOP`（692px，`grid.py` 的单一来源）；
- 条目标签缩进：默认 80px（常见皮肤的悬挂缩进量级；皮肤可以更宽，所以再保守一档）。

契约给出的是**软预算**：`check.py` 只在超预算超过 `TOLERANCE` 时开口，而且提示
里第一句是"改文案 / 换版式"，不是"缩字号"。渲染后的实测（越界 / 碰撞 / 死白）
仍是硬门 —— 预算是**提前量**，不是替代品。
"""
from __future__ import annotations

import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _up(name: str):
    path = os.path.join(os.path.dirname(HERE), f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"_deck_ct_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sibling(name: str):
    path = os.path.join(HERE, f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"_deck_ct_s_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 layout/{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_grid = _up("grid")
_fp = _sibling("fingerprint")

# 估算参数（改这里就是改"预算有多保守"）
ITEM_INDENT = 80.0        # 条目的悬挂缩进（含标记位）
LINE_HEIGHT = 1.55        # 行高倍数（与壳 / 皮肤的正文行高同量级）
ITEM_GAP = 28.0           # 条目之间的垂直间隙（估值；皮肤可更松）
TOLERANCE = 0.15          # 超出这个比例才开口 —— 估算是估算
TITLE_MAX_LINES = 3       # 标题块最多几行（再长就该改写标题）

BAND_H = _grid.CONTENT_BOTTOM - _grid.CONTENT_TOP
CONTENT_W = _grid.CONTENT_W


def _as_number(value, default: float) -> float:
    """数字→ float，其余（含 bool / NaN / 字符串）→ default。

    预算表宁可给一个保守的默认值，也不能让一个坏值把整张表变成 NaN
    （NaN 参与比较全假，预算等于静默失效）。
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    try:
        num = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return default if num != num else num


def _floor(value: float) -> int:
    """向下取整；坏值 → 0（调用方自己兜底至少 1）。"""
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return 0


def _lines(height: float, size: float) -> int:
    if size <= 0:
        return 1
    return max(1, _floor(height // (size * LINE_HEIGHT)))


def _chars(width: float, size: float) -> int:
    """一行能排几个 CJK 全角字（保守：拉丁实际更宽裕）。"""
    if size <= 0:
        return 0
    return max(1, _floor(width // size))


def _tier_size(tiers: dict, key: str, default: float) -> float:
    size = _as_number((tiers or {}).get(key), default)
    return size if size > 0 else default


def budgets(page_type: str, layout: str | None, tiers: dict,
            indent: float = ITEM_INDENT) -> dict:
    """这一页的预算表（按页型 + 结构 + 风格的 type 级数算）。

    `tiers` 是风格 token 的 `type` 块（`validate_spec`/`check` 都拿得到）。
    不认识的页型 → `{}`（不猜）。
    """
    if not isinstance(page_type, str) or not page_type:
        return {}                       # 不认识的页型不猜
    if layout is not None and not isinstance(layout, str):
        layout = None
    title_size = _tier_size(tiers, "compact", 84.0)
    bullet_size = _tier_size(tiers, "bullet", 32.0)
    col_title_size = _tier_size(tiers, "colTitle", 40.0)
    node_label = _tier_size(tiers, "nodeLabel", 28.0)
    node_note = _tier_size(tiers, "nodeNote", 22.0)
    out: dict = {"pageType": page_type, "layout": layout}

    if page_type in ("title", "end"):
        size = _tier_size(tiers, "cover" if page_type == "title" else "end", 128.0)
        out["title"] = {"maxChars": _chars(CONTENT_W, size),
                        "maxLines": TITLE_MAX_LINES}
        return out
    if page_type == "content-text":
        out["title"] = {"maxChars": _chars(CONTENT_W, title_size),
                        "maxLines": TITLE_MAX_LINES}
        out["bullets"] = _item_budget(CONTENT_W, BAND_H, bullet_size, indent)
        return out
    if page_type == "content-image":
        st = _fp.structure(page_type, layout or "visual-right")
        text_span = 7
        if st:
            text_span = next((r["span"] for r in st["regions"]
                              if r["role"] == "text"), 7)
        if layout == "hero":
            # 满幅图的文字只住在底部标题条 + 图下的说明/条目里
            out["title"] = {"maxChars": _chars(CONTENT_W, col_title_size),
                            "maxLines": 2}
            out["bullets"] = _item_budget(CONTENT_W, BAND_H, bullet_size, indent)
            return out
        text_w = _grid.span(text_span)[1]
        out["title"] = {"maxChars": _chars(CONTENT_W, title_size),
                        "maxLines": TITLE_MAX_LINES}
        out["bullets"] = _item_budget(text_w, BAND_H, bullet_size, indent)
        return out
    if page_type == "two-column":
        st = _fp.structure(page_type, layout or "even")
        spans = [r["span"] for r in (st or {}).get("regions", ())] or [6, 6]
        narrow = min(spans)
        out["title"] = {"maxChars": _chars(CONTENT_W, title_size),
                        "maxLines": TITLE_MAX_LINES}
        # 栏内**条目**按条目字号算；栏题是另一回事（它自己一行，用 colTitle 档）
        out["columns"] = _item_budget(_grid.span(narrow)[1], BAND_H,
                                      bullet_size, indent)
        out["columns"]["perColumn"] = True
        out["columns"]["titleChars"] = _chars(_grid.span(narrow)[1],
                                              col_title_size)
        out["columns"]["titleSize"] = col_title_size
        return out
    if page_type == "timeline":
        nodes = 7
        out["title"] = {"maxChars": _chars(CONTENT_W, title_size),
                        "maxLines": TITLE_MAX_LINES}
        out["nodes"] = {"maxItems": nodes,
                        "labelChars": _chars(CONTENT_W / nodes - 24, node_label),
                        "noteChars": _chars(CONTENT_W / nodes - 24, node_note)}
        return out
    if page_type == "chart":
        out["title"] = {"maxChars": _chars(CONTENT_W, title_size),
                        "maxLines": TITLE_MAX_LINES}
        out["data"] = {"maxPoints": 12}      # 再多的点在 1600px 宽上也读不出来
        return out
    return out


def _item_budget(width: float, height: float, size: float,
                 indent: float) -> dict:
    text_w = max(1.0, width - indent)
    per_item = size * LINE_HEIGHT + ITEM_GAP
    return {"maxItems": max(1, _floor(height // per_item)),
            "maxChars": _chars(text_w, size),
            "size": size}


def contract_for_slides(slides: list, tiers: dict) -> list:
    """逐页预算（给 `render --contract` 用）。"""
    out = []
    for i, s in enumerate(slides, 1):
        if not isinstance(s, dict):
            continue
        page_type = s.get("type")
        if not isinstance(page_type, str) or not page_type:
            continue
        layout = s.get("layout")
        out.append({"page": i, "role": s.get("role"), "title": s.get("title"),
                    **budgets(page_type,
                              layout if isinstance(layout, str) else None, tiers)})
    return out


__all__ = ["budgets", "contract_for_slides", "TOLERANCE", "BAND_H", "CONTENT_W"]
