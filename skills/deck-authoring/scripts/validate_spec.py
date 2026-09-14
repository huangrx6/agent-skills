#!/usr/bin/env python3
"""规格校验 —— 检查模型写出来的 `deck-spec.json`。

这是**输入层**的校验（spec 写对没有），不是产物校验（那是 `check.py` 的六项）。
两者分开，因为修复动作不同：spec 错了改内容，产物不对改版式 / 色板。

## 字段集是**封闭**的（这条是核心设计）

`check.py` 只主动拦 `color` 一个字段，其余未知键它是**静默忽略**的。静默的后果是：

> 模型顺手写个 `fontSize: 120` 或 `x: 40` → 没报错 → 它以为生效了 → 出的图却没变
> → 它开始怀疑整条链路，去改别的没用的地方。

本 skill 的整个立论就是"坐标 / 字号 / 色值由脚本算，模型只写内容"。所以这里把字段集
写死、未知项直接判失败 —— 让"顺手加一个"**当场撞墙**，而不是静默失效。

和 `check.py` 的分工：那边查"产物长成什么样"，这边查"你让我画什么"。

用法：
    python3 validate_spec.py deck-spec.json
    python3 validate_spec.py deck-spec.json --json

退出码：0 = 通过，1 = 有 error，2 = 读不到 / 不是合法 JSON。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TOKENS = os.path.join(HERE, "..", "styles", "risograph", "style.json")

# 封闭字段集。加字段要同时改这里与 `references/style-architecture.md` ——
# 这正是设计意图：让"顺手加一个"变得有摩擦。
DECK_FIELDS = {"colorSet", "seed", "title", "slides"}
SLIDE_FIELDS = {
    "title":         {"type", "title", "subtitle", "color"},
    "content-text":  {"type", "title", "bullets", "color"},
    "content-image": {"type", "title", "bullets", "image", "color"},
    "two-column":    {"type", "title", "columns", "color"},
    "timeline":      {"type", "title", "nodes", "color"},
    "chart":         {"type", "title", "data", "unit", "caption", "color"},
    "end":           {"type", "title", "color"},
}
# 嵌套列表的元素字段（两栏 / 时间点 / 柱子）
ITEM_FIELDS = {
    "columns": {"title", "bullets"},
    "nodes":   {"label", "note"},
    "data":    {"label", "value"},
}

# 刻意的空缺 —— 报错时给**专门**说明，而不是只说"未知字段"。这三个集合对应
# 本 skill 立论里明确不许模型碰的三类东西。
SIZE_FIELDS = {"fontSize", "font_size", "fontSizePx", "textSize", "size", "font"}
COORD_FIELDS = {"x", "y", "dx", "dy", "rot", "rotation", "offset", "left", "top",
                "width", "height", "w", "h"}
COLOR_FIELDS = {"primary", "secondary", "background", "ink", "inkText", "paper",
                "fg", "bg", "fill", "stroke"}

HINTS = {
    "fontSize": "字号不在规格里：它由 render.py 派生，对比度分档由 token.contrast.largeTextPx 判定。",
    "font_size": "同上 —— 字号由脚本派生，不是写进来的。",
    "fontSizePx": "同上 —— 字号由脚本派生，不是写进来的。",
    "textSize": "同上 —— 字号由脚本派生，不是写进来的。",
    "size": "同上 —— 字号 / 尺寸由脚本派生。",
    "font": "字体族在 token.fonts 里，不在规格里。",
    "x": "坐标是刻意不存在的字段。一旦 schema 里有 x/y，模型就会开始填数字 —— 而版式计算正是交给脚本的那部分。",
    "y": "同上 —— 用 type 表达版式，不要给坐标。",
    "dx": "错位量由 (seed, 元素) 派生，规格里没有它。",
    "dy": "同上 —— 错位量由脚本派生。",
    "rot": "旋转角由 (seed, 元素) 派生，规格里没有它。",
    "rotation": "同上 —— 旋转角由脚本派生。",
    "width": "尺寸由版式决定，规格里没有它。",
    "height": "同上 —— 尺寸由版式决定。",
    "primary": "色值不在规格里：换色板请改 styles/risograph/style.json 的 colorSets。",
    "secondary": "同上 —— 色值只在 token 里。",
    "background": "同上 —— 纸色只在 token 里。",
    "ink": "同上 —— 叠印墨是推导出来的，不是写进来的。",
    "inkText": "同上 —— 文字色 = overprint(primary, secondary)，由 ink.py 推导。",
}


class Issues:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def error(self, code: str, where: str, message: str) -> None:
        self.items.append({"level": "error", "code": code, "where": where, "message": message})

    def warn(self, code: str, where: str, message: str) -> None:
        self.items.append({"level": "warn", "code": code, "where": where, "message": message})

    @property
    def errors(self) -> list[dict]:
        return [i for i in self.items if i["level"] == "error"]


def _check_fields(obj: dict, allowed: set[str], where: str, issues: Issues) -> None:
    """未知键判错，并按字段类别给专门说明。"""
    for key in obj:
        if key in allowed:
            continue
        hint = HINTS.get(key)
        if key in SIZE_FIELDS:
            issues.error("SIZE_FIELD", f"{where}.{key}", hint or "规格里没有字号字段。")
        elif key in COORD_FIELDS:
            issues.error("COORD_FIELD", f"{where}.{key}", hint or "规格里没有坐标 / 尺寸字段。")
        elif key in COLOR_FIELDS:
            issues.error("COLOR_FIELD", f"{where}.{key}", hint or "规格里没有色值字段。")
        else:
            issues.error("UNKNOWN_FIELD", f"{where}.{key}",
                         f"未知字段 {key!r}；这里的允许集是 {sorted(allowed)}")


def _check_items(slide: dict, key: str, where: str, issues: Issues) -> None:
    """校验嵌套列表（columns / nodes / data）的元素字段。"""
    items = slide.get(key)
    if items is None:
        return
    if not isinstance(items, list):
        issues.error("BAD_ITEMS", f"{where}.{key}", f"{key} 必须是数组")
        return
    allowed = ITEM_FIELDS[key]
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            issues.error("BAD_ITEM", f"{where}.{key}[{i}]", "每一项都必须是对象")
            continue
        _check_fields(item, allowed, f"{where}.{key}[{i}]", issues)


def validate(spec: dict, color_sets: set[str] | None = None) -> Issues:
    issues = Issues()
    if not isinstance(spec, dict):
        issues.error("BAD_ROOT", "$", "顶层必须是对象")
        return issues
    _check_fields(spec, {"deck"}, "$", issues)

    deck = spec.get("deck")
    if not isinstance(deck, dict):
        issues.error("BAD_DECK", "deck", "缺少 deck 对象")
        return issues
    _check_fields(deck, DECK_FIELDS, "deck", issues)

    if color_sets is not None:
        chosen = deck.get("colorSet")
        if isinstance(chosen, str) and chosen not in color_sets:
            issues.error("BAD_COLOR_SET", "deck.colorSet",
                         f"{chosen!r} 不在 token 的 colorSets 里，可用 {sorted(color_sets)}")

    slides = deck.get("slides")
    if not isinstance(slides, list) or not slides:
        issues.error("BAD_SLIDES", "deck.slides", "slides 必须是非空数组")
        return issues

    for i, slide in enumerate(slides):
        where = f"deck.slides[{i}]"
        if not isinstance(slide, dict):
            issues.error("BAD_SLIDE", where, "每一页都必须是对象")
            continue
        kind = slide.get("type")
        if kind not in SLIDE_FIELDS:
            issues.error("BAD_TYPE", f"{where}.type",
                         f"未知版式 {kind!r}；支持 {sorted(SLIDE_FIELDS)}")
            continue
        _check_fields(slide, SLIDE_FIELDS[kind], where, issues)
        # color 只允许 "overprint"（主/副色载不住正文 —— 见 ink.py）
        declared = slide.get("color")
        if declared is not None and declared != "overprint":
            issues.error("BAD_COLOR", f"{where}.color",
                         f"只接受 \"overprint\"（两墨叠印色），收到 {declared!r} —— "
                         f"主/副色单独当文字色对比度天生不达标")
        for key in ITEM_FIELDS:
            if key in slide:
                _check_items(slide, key, where, issues)

    return issues


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="校验 deck-spec.json 规格（字段集封闭）")
    ap.add_argument("spec", help="规格文件路径")
    ap.add_argument("--tokens", default=DEFAULT_TOKENS,
                    help="token 文件（只为把 colorSet 的名字对一遍）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    try:
        with open(args.spec, encoding="utf-8") as fh:
            spec = json.load(fh)
    except OSError as exc:
        print(f"读不到规格文件：{exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"不是合法 JSON：{exc}", file=sys.stderr)
        return 2

    # token 读不到**不算** spec 的错（可能只是没带对路径）—— 那就跳过 colorSet 存在性校验，
    # 而不是把一件读不到的事报成"规格有问题"。
    color_sets: set[str] | None = None
    try:
        with open(args.tokens, encoding="utf-8") as fh:
            color_sets = set(json.load(fh)["colorSets"])
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        color_sets = None

    issues = validate(spec, color_sets)

    if args.json:
        print(json.dumps({"spec": args.spec, "error_count": len(issues.errors),
                          "issues": issues.items}, ensure_ascii=False, indent=2))
        return 1 if issues.errors else 0

    if not issues.items:
        print("✓ 规格通过（字段集封闭、版式与 colorSet 都认得）")
        return 0

    for it in issues.items:
        mark = "✗" if it["level"] == "error" else "·"
        print(f"  {mark} [{it['code']}] {it['where']}")
        print(f"      {it['message']}")

    print(f"\n{len(issues.errors)} 个 error，{len(issues.items) - len(issues.errors)} 个 warn")
    return 1 if issues.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
