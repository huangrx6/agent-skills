#!/usr/bin/env python3
"""内置语义 sigil —— 不依赖外部素材库的 16px 极简图形。

## 为什么要有这一层（模仿 archify 的 semantic sigil）

archify 每个节点左上角有一个 16×16 的语义小图形（浏览器窗 / 括号 / 圆柱 /
盾牌……），由渲染器自绘、随语义类型自动上色 —— **零外部依赖、宽度可控**。

本 skill 原有的 `icon` 字段指向外部 `.excalidrawlib` 素材库：库不在，图标就
用不了。这一层补上"常用语义图标不装库也能用"：`icon: "database"` 这类**内置名**
直接由本文件生成，宽度进尺寸链的方式与素材库图标完全一致（同一个
`icons.intrinsic_size` / `fit_scale` / `place` 管道）。

## 与素材库图标的关系

- 内置名优先级**高于**素材库：`icon: "database"` 永远是内置图形，不查库。
  两个来源同名时静默挑一个，等于"我写了 A 出来的是 B" —— 与未知 kind 不 fallback
  同一条规矩。
- 素材库仍然有效：不在内置目录里的名字照旧走库（品牌 logo 那类只有库里有）。

## 为什么颜色由调用方传入

`icons.place` 会整体复制元素，不做改色；生成时机在 emit、那时主题已定 ——
所以 `glyph(name, stroke)` 接受描边色，调用方传当前画布的墨色。
不在这里 import palette：本模块保持无兄弟依赖，方便单独测试。
"""

from __future__ import annotations

# 图形画在 0..16 的坐标框里；`icons.place` 会按目标高度等比缩放。
_STROKE_WIDTH = 2.0


def _line(x1: float, y1: float, x2: float, y2: float, stroke: str, i: int) -> dict:
    x, y = min(x1, x2), min(y1, y2)
    return {
        "id": f"sig-{i}", "type": "line",
        "x": x, "y": y,
        "width": abs(x2 - x1), "height": abs(y2 - y1),
        "points": [[x1 - x, y1 - y], [x2 - x, y2 - y]],
        "strokeColor": stroke, "backgroundColor": "transparent",
        "strokeWidth": _STROKE_WIDTH,
    }


def _ellipse(x: float, y: float, w: float, h: float, stroke: str, i: int,
             filled: bool = False) -> dict:
    return {
        "id": f"sig-{i}", "type": "ellipse",
        "x": x, "y": y, "width": w, "height": h,
        "strokeColor": stroke,
        "backgroundColor": stroke if filled else "transparent",
        "strokeWidth": _STROKE_WIDTH,
    }


def _rect(x: float, y: float, w: float, h: float, stroke: str, i: int) -> dict:
    return {
        "id": f"sig-{i}", "type": "rectangle",
        "x": x, "y": y, "width": w, "height": h,
        "strokeColor": stroke, "backgroundColor": "transparent",
        "strokeWidth": _STROKE_WIDTH,
    }


# ── 图形目录（每个都是 0..16 坐标框里的原始元素列表）─────────────
#
# 造型参考 archify 的 SIGIL_SHAPE，但用 Excalidraw 原语（线/椭圆/矩形）重画 ——
# 手绘抖动由渲染器的 roughness 提供，这里只给几何。
def _user(s: str) -> list[dict]:
    return [
        _ellipse(5.0, 1.0, 6.0, 6.0, s, 0),        # 头
        _rect(2.5, 9.0, 11.0, 6.0, s, 1),          # 肩与躯干
    ]


def _api(s: str) -> list[dict]:
    return [
        _line(5.5, 3.0, 1.5, 8.0, s, 0), _line(1.5, 8.0, 5.5, 13.0, s, 1),    # <
        _line(10.5, 3.0, 14.5, 8.0, s, 2), _line(14.5, 8.0, 10.5, 13.0, s, 3),  # >
        _line(9.5, 2.0, 6.5, 14.0, s, 4),          # 斜杠
    ]


def _database(s: str) -> list[dict]:
    return [
        _ellipse(1.0, 0.5, 14.0, 5.0, s, 0),       # 顶盖
        _line(1.0, 3.0, 1.0, 12.5, s, 1),          # 左壁
        _line(15.0, 3.0, 15.0, 12.5, s, 2),        # 右壁
        _ellipse(1.0, 10.5, 14.0, 5.0, s, 3),      # 底弧
    ]


def _queue(s: str) -> list[dict]:
    return [
        _line(1.0, 4.0, 15.0, 4.0, s, 0),
        _line(1.0, 8.0, 15.0, 8.0, s, 1),
        _line(1.0, 12.0, 15.0, 12.0, s, 2),
        _ellipse(3.4, 3.1, 2.0, 2.0, s, 3, filled=True),
        _ellipse(9.6, 7.1, 2.0, 2.0, s, 4, filled=True),
        _ellipse(6.0, 11.1, 2.0, 2.0, s, 5, filled=True),
    ]


def _shield(s: str) -> list[dict]:
    return [
        _line(8.0, 1.0, 13.0, 3.0, s, 0),
        _line(13.0, 3.0, 13.0, 7.5, s, 1),
        _line(13.0, 7.5, 8.0, 15.0, s, 2),
        _line(8.0, 15.0, 3.0, 7.5, s, 3),
        _line(3.0, 7.5, 3.0, 3.0, s, 4),
        _line(3.0, 3.0, 8.0, 1.0, s, 5),
        _line(5.8, 7.2, 7.4, 8.8, s, 6),           # 勾
        _line(7.4, 8.8, 10.4, 5.2, s, 7),
    ]


def _cloud(s: str) -> list[dict]:
    return [
        _ellipse(1.5, 6.0, 13.0, 7.5, s, 0),
        _ellipse(4.5, 2.0, 6.0, 6.0, s, 1),
    ]


def _external(s: str) -> list[dict]:
    return [
        _rect(1.5, 5.5, 9.0, 9.0, s, 0),
        _line(8.5, 2.5, 14.5, 2.5, s, 1),          # ↗ 箭头的两边
        _line(14.5, 2.5, 14.5, 8.5, s, 2),
        _line(14.5, 2.5, 8.0, 9.0, s, 3),
    ]


def _plain(s: str) -> list[dict]:
    return [
        _rect(3.0, 3.0, 10.0, 10.0, s, 0),
        _ellipse(7.0, 7.0, 2.2, 2.2, s, 1, filled=True),
    ]


_CANON: dict[str, object] = {
    "user": _user,
    "api": _api,
    "database": _database,
    "queue": _queue,
    "shield": _shield,
    "cloud": _cloud,
    "external": _external,
    "plain": _plain,
}

# 别名 → 规范名。别名大多对齐本 skill 的 kind 词汇，让 `icon` 写 kind 名也能用。
_ALIASES = {
    "client": "user", "person": "user",
    "service": "api", "backend": "api", "brackets": "api",
    "data": "database", "storage": "database", "db": "database",
    "async": "queue", "message": "queue", "event": "queue", "bus": "queue",
    "security": "shield", "lock": "shield",
    "node": "plain", "step": "plain",
}

NAMES = frozenset(_CANON) | frozenset(_ALIASES)


def is_builtin(name: str) -> bool:
    return name in NAMES


def glyph(name: str, stroke: str) -> list[dict]:
    """按名字生成一份 sigil 元素（0..16 坐标框，等 icons.place 缩放落位）。"""
    canonical = _ALIASES.get(name, name)
    if canonical not in _CANON:
        raise KeyError(f"{name!r} 不是内置 sigil；可用：{sorted(NAMES)}")
    return list(_CANON[canonical](stroke))  # type: ignore[operator]


def _main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="查看内置 sigil 目录")
    ap.add_argument("--name", help="看某个 sigil 的元素数与尺寸")
    args = ap.parse_args(argv)
    if args.name:
        try:
            els = glyph(args.name, "#1f2937")
        except KeyError as exc:
            print(f"✗ {exc}", file=sys.stderr)
            return 1
        xs = [e["x"] + e.get("width", 0) for e in els] + [e["x"] for e in els]
        ys = [e["y"] + e.get("height", 0) for e in els] + [e["y"] for e in els]
        print(f"{args.name}: {len(els)} 个元素，包围盒 "
              f"{max(xs) - min(xs):.0f}×{max(ys) - min(ys):.0f}")
        return 0
    print(f"内置 sigil（{len(_CANON)} 个规范名 + {len(_ALIASES)} 个别名）：")
    for name in sorted(_CANON):
        alias = ", ".join(sorted(a for a, c in _ALIASES.items() if c == name))
        print(f"  {name:<10}" + (f"（别名 {alias}）" if alias else ""))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_main())
