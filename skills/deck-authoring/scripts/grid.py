#!/usr/bin/env python3
"""网格与间距：版面几何的**唯一来源**。

## 为什么要有这个模块

建它之前，几何散在三处且已经打架：`render.py` 推导 `CONTENT_BOTTOM = 824`，
`check.py` 手写 `CONTENT = (…, 838)` —— 同一条"内容下边界"两个数字差 14px。
两个"唯一来源"就是没有唯一来源。

规范给的结构是 **Grid + Region + Constraint**（Fluent 2 的 Grid/Regions、
Figma Auto Layout 的父子参数、Design Tokens 的 spacing ramp），这里一次落地：

  · **画布与安全区** —— 1600×900，边距 x=84 / y=132，页脚占 52+24；
  · **12 列网格** —— 边距 84、列距 24，任何版式宽度只取整列跨度
    （2 / 3 / 4 / 5 / 6 / 7 / 8 / 12 列），不允许 5.37 列；
  · **间距令牌** —— 8 档 ramp（8/12/16/24/32/48/64/96），任何 gap 只从 ramp 取；
  · **关系规则** —— 组间距 ≥ 1.5 × 条目距（Gestalt 接近性：越近越相关）。

`render.py` / `check.py` / `fit.py` / `hierarchy.py` / `deliver.py` 全部从这里取值；
谁再手写一个 838，就是回到两个真相的老路上去。

跑法：
    python3 scripts/grid.py            # 打印网格与令牌
    python3 scripts/grid.py --json     # 机读
"""

from __future__ import annotations

import argparse
import json
import sys

# ═══════════════════════════════════════════════════════════════════════════
# 画布与安全区（规范第 3 条）
# ═══════════════════════════════════════════════════════════════════════════

SLIDE_W, SLIDE_H = 1600, 900

# 水平边距 84 = 1600 × 5.25%，在 4px 基准上（84 = 4×21）。
# 垂直边距 132 更大：顶部要放下标题块的空气，这是 PPT 与文档的差异 ——
# 页面顶部需要更多留白才不显得"贴着边"。
PAD_X = 84
PAD_Y = 132

# 页脚区：底 52 起、高 24。内容不得进入这个带。
FOOT_BOTTOM = 52
FOOT_H = 24

# 内容带（正文允许出现的竖直区间）。**这是"内容下边界"的唯一数字** ——
# check.py 从前手写过 838，与 render.py 的 824 差 14px（发现时已经漂了）。
CONTENT_TOP = PAD_Y
CONTENT_BOTTOM = SLIDE_H - FOOT_BOTTOM - FOOT_H      # 824
CONTENT_W = SLIDE_W - 2 * PAD_X                       # 1432

# ═══════════════════════════════════════════════════════════════════════════
# 12 列网格（规范第 4 条）
#
# 列宽不是整数（(1432 − 11×24)/12 = 97.33px）—— CSS 吃小数像素，检查按
# 容差 1.5px 判吸附。刻意不为了整数去动边距：边距 84 是既有的左缘，
# 改它会连带页脚、logo、装饰全部重排。
# ═══════════════════════════════════════════════════════════════════════════

COLUMNS = 12
GUTTER = 24
COL_W = (CONTENT_W - (COLUMNS - 1) * GUTTER) / COLUMNS     # ≈ 97.33

# 版式允许的跨度（整列）。**没有 5.37 列这种东西** —— 那是"看着差不多"的来源之一。
ALLOWED_SPANS = (2, 3, 4, 5, 6, 7, 8, 12)


def col(k: int) -> float:
    """第 k 列（1 起）的左缘 x。"""
    if not 1 <= k <= COLUMNS:
        raise SystemExit(f"✗ 列号 {k} 越界（1~{COLUMNS}）")
    return PAD_X + (k - 1) * (COL_W + GUTTER)


def span(n: int, start: int = 1) -> tuple[float, float]:
    """从 start 列起、跨 n 列的 (x, 宽)。宽度含中间的列距。"""
    if n not in ALLOWED_SPANS:
        raise SystemExit(f"✗ 跨度 {n} 列不在允许集 {ALLOWED_SPANS} 里"
                         f"（版面宽度只取整列跨度）")
    end = start + n - 1
    if end > COLUMNS:
        raise SystemExit(f"✗ 第 {start} 列起跨 {n} 列超出 {COLUMNS} 列")
    return col(start), n * COL_W + (n - 1) * GUTTER


def column_starts() -> list[float]:
    """全部 12 个列起点（对齐检查用：元素左缘应吸附于这些值之一）。"""
    return [col(k) for k in range(1, COLUMNS + 1)]


def snap(x: float, tol: float = 1.5) -> int | None:
    """x 吸附到第几列（容差内）；吸不上返回 None。0 = 左边距。"""
    if abs(x - PAD_X) <= tol:
        return 0
    for k, cx in enumerate(column_starts(), 1):
        if abs(x - cx) <= tol:
            return k
    return None


# ═══════════════════════════════════════════════════════════════════════════
# 间距令牌（规范第 9 / 10 条）
#
# ramp 是 4px 体系（8/12/16/24/32/48/64/96）。语义档从 ramp 取值，
# 并满足关系规则：组间距 ≥ 1.5 × 条目距（48 ≥ 1.5×24 ✓）、
# 区块距 ≥ 1.33 × 组距（64 ≥ 64 ✓）。
# ═══════════════════════════════════════════════════════════════════════════

SPACING = {
    "space-1": 8,    # hairline：行内微调
    "space-2": 12,   # tight：标签与它的值
    "space-3": 16,   # inner：条目内部（一行拆两行的间隙）
    "space-4": 24,   # item：条目之间 / 图与图注
    "space-5": 32,   # group：小模块之间
    "space-6": 48,   # group2：标题块与正文块
    "space-7": 64,   # section：区块之间
    "space-8": 96,   # hero：封面级留白
}

# 语义档（layout 用这些，不直接用 ramp —— ramp 是底座，语义才是意图）。
SEMANTIC = {
    "inner": 16,      # 条目内部
    "item": 24,       # 条目之间
    "group": 48,      # 模块之间（标题块 → 正文块）
    "section": 64,    # 区块之间
}

# 关系规则（规范第 10 条）。**成文**而不是靠感觉：group ≥ 1.5 × inner。
GROUP_RATIO = 1.5
SECTION_RATIO = 1.33


def spacing_vars() -> dict[str, str]:
    """语义档 + ramp → CSS 自定义属性（render.py 注进产物）。"""
    out = {f"--sp-{k}": f"{v}px" for k, v in SEMANTIC.items()}
    out.update({f"--sp-{k}": f"{v}px" for k, v in SPACING.items()})
    return out


def check_relationships() -> list[str]:
    """关系规则自检 —— ramp 违反时立刻知道，而不是靠人眼发现节奏散了。"""
    problems = []
    if SEMANTIC["group"] < GROUP_RATIO * SEMANTIC["inner"]:
        problems.append(f"group({SEMANTIC['group']}) < {GROUP_RATIO}×inner({SEMANTIC['inner']})")
    if SEMANTIC["section"] < SECTION_RATIO * SEMANTIC["group"]:
        problems.append(f"section({SEMANTIC['section']}) < "
                        f"{SECTION_RATIO}×group({SEMANTIC['group']})")
    ramp = sorted(SPACING.values())
    if ramp != sorted(set(ramp)):
        problems.append("ramp 里有重复值")
    for name, value in SEMANTIC.items():
        if value not in SPACING.values():
            problems.append(f"{name}={value} 不在 ramp 里（gap 只许从 ramp 取）")
    return problems


# ═══════════════════════════════════════════════════════════════════════════
# 区域（规范第 5 条）：AI 不输出坐标，只输出"谁进哪个区"；坐标由这里算。
# ═══════════════════════════════════════════════════════════════════════════

REGIONS = {
    "header": (PAD_X, PAD_Y, CONTENT_W, 104),            # 标题块
    "body":   (PAD_X, CONTENT_TOP + 104 + SEMANTIC["group"],
               CONTENT_W, CONTENT_BOTTOM - CONTENT_TOP - 104 - SEMANTIC["group"]),
    "aside":  (col(8), CONTENT_TOP, span(5, 8)[1], CONTENT_BOTTOM - CONTENT_TOP),
    "footer": (PAD_X, SLIDE_H - FOOT_BOTTOM - FOOT_H, CONTENT_W, FOOT_H + FOOT_BOTTOM),
}


# ═══════════════════════════════════════════════════════════════════════════
# 视觉优先级（规范第 7 条）：priority 映射到字号/字重/明度/面积，
# 而不是"重要 = 字变大"。角色 → 档位在这里只有一处定义。
# ═══════════════════════════════════════════════════════════════════════════

PRIORITY = {
    "title": 2, "subtitle": 3, "image": 1, "chart": 1, "logo": 3,
    "colTitle": 3, "nodeLabel": 3, "bullet": 4, "nodeNote": 4,
    "caption": 5, "foot": 5, "brandfoot": 5,
    "chartValue": 3, "chartLabel": 5,
}

PRIORITY_RULES = {
    1: "页面唯一核心视觉：面积最大、周围留白最大、允许 Accent",
    2: "标题 / 核心结论：较大字号 + Bold",
    3: "重要支撑：Medium、允许 Accent",
    4: "正文：Regular、中性色",
    5: "辅助：小字号、Muted",
}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="网格与间距（版面几何唯一来源）")
    ap.add_argument("--json", action="store_true", help="机读输出")
    args = ap.parse_args(argv[1:])
    problems = check_relationships()
    if args.json:
        print(json.dumps({
            "canvas": [SLIDE_W, SLIDE_H], "pad": [PAD_X, PAD_Y],
            "columns": COLUMNS, "gutter": GUTTER, "col_w": round(COL_W, 3),
            "spans": {n: [round(span(n)[0], 1), round(span(n)[1], 1)] for n in ALLOWED_SPANS},
            "spacing": SPACING, "semantic": SEMANTIC,
            "regions": {k: [round(v, 1) for v in box] for k, box in REGIONS.items()},
            "relationship_problems": problems,
        }, ensure_ascii=False, indent=2))
        return 1 if problems else 0
    print(f"画布 {SLIDE_W}×{SLIDE_H} · 边距 {PAD_X}/{PAD_Y} · "
          f"{COLUMNS} 列 / 列距 {GUTTER} / 列宽 {COL_W:.2f}")
    print(f"内容带 y {CONTENT_TOP}→{CONTENT_BOTTOM}（高 {CONTENT_BOTTOM - CONTENT_TOP}），宽 {CONTENT_W}")
    print(f"间距 ramp：{SPACING}")
    print(f"语义档：{SEMANTIC}（关系规则 group≥{GROUP_RATIO}×inner、"
          f"section≥{SECTION_RATIO}×group）")
    for n in ALLOWED_SPANS:
        x, w = span(n)
        print(f"  span {n:2} 列  x={x:7.2f}  w={w:7.2f}")
    if problems:
        print("✗ 关系规则不满足：")
        for p in problems:
            print("   ·", p)
        return 1
    print("✓ 关系规则全部满足")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
