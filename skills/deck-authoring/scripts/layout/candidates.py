"""Candidate Search：未声明布局的页，把结构候选都渲一遍、实测、打分。

**边界（不可违反）**：

- 只搜**未声明** `layout` 的页：作者写了就是钉死（主权），搜索不越权。
- 目标函数**不含「最满优先」**：密度是**区间满意度**（normal 45~65%，
  两头都扣分），不是最大化 —— 越满越好的选法会奖励拥挤。
- 任何硬违规（竖向溢出 / 标题写出列 / 安全盒碰撞）= 候选**作废**，
  不进排序。
- 可测的才打分（密度 / 换行 / 视觉占比 / 平衡）；语义契合、风格契合、
  deck 节奏是**作者判断** —— 打分表摆出来，决定权在人（`--pick` 才落盘）。

结构候选来自渲染器能力清单（`render.IMAGE_LAYOUTS` /
`TWO_COL_LAYOUTS`），以参数注入（避免 render ⇄ layout 循环加载）。
"""
from __future__ import annotations

import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _up(name: str):
    path = os.path.join(os.path.dirname(HERE), f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"_deck_cand_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


grid = _up("grid")
_repair = None      # 懒加载缓存（修复梯的硬信号）


def _sibling(name: str):
    path = os.path.join(HERE, f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"_deck_cand_s_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 layout/{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_col = _sibling("collision")

# ── 区间满意度（§28：两端都扣分，65% 不自动优于 50%）──────────────────
DENSITY_BAND = {"content-image": (0.40, 0.68), "two-column": (0.45, 0.72)}
# 视觉占比（§19：min 40% / preferred 55%；hero 满幅是作者声明的设计，
# 自动选优不奖励它）
VISUAL_BAND = (0.35, 0.60)

# 可测维度的权重（§27 的可测子集；语义/风格/节奏留给作者看表判断）
WEIGHTS = {"density": 0.30, "readability": 0.25, "focal": 0.25, "balance": 0.20}


def searchable(slide: dict, image_layouts, two_col_layouts) -> list:
    """这一页可搜的结构候选。声明过 layout / 页型无结构布局 → 空表（不搜）。"""
    if not isinstance(slide, dict) or slide.get("layout"):
        return []
    kind = slide.get("type")
    if kind == "content-image":
        return list(image_layouts)
    if kind == "two-column":
        return list(two_col_layouts)
    return []


def _interval_score(value: float, lo: float, hi: float,
                    falloff: float = 0.25) -> float:
    """区间内 1.0，两端线性衰减到 0（越出 falloff 宽度就归零）。"""
    if lo <= value <= hi:
        return 1.0
    if value < lo:
        return max(0.0, 1 - (lo - value) / falloff)
    return max(0.0, 1 - (value - hi) / falloff)


def _bullet_lines(el: dict) -> int:
    """条目行数（h / 字号×1.55，四舍五入；字号缺失按 1 行）。"""
    size, h = el.get("fontSize"), el.get("h")
    if not isinstance(size, (int, float)) or size <= 0 or not isinstance(h, (int, float)):
        return 1
    return max(1, round(h / (size * 1.55)))


def score_page(page_type: str, elements: list, slide_top: float,
               layout_name: str = "") -> dict:
    """一页一个候选的实测评分。

    返回 ``{valid, invalid_reason, density(原始占比), scores{...}, total}`` ——
    原始值与得分分开：44% 落在区间内得分 1.0，是两件事，混在一个键里
    会把「区间满意」读成「塞满」。

    ``elements`` 是该页的实测元素（measure 口径，绝对坐标）；
    ``slide_top`` 是该页在产物里的 y 起点（页内坐标 = 绝对 − 起点）；
    ``layout_name`` 是**正在试的这个候选**——试 hero 时标题条压图按
    intentional 豁免（试用即声明）。
    """
    invalid = []
    tops = [{"x": 0, "y": slide_top, "w": grid.SLIDE_W, "h": grid.SLIDE_H}]
    # 硬门三件：溢出（竖/横）+ 安全盒碰撞 —— 任一命中即作废
    els = [dict(e, slide=1) for e in elements]
    issues = _up_repair_signals({"slides": tops, "elements": els})
    invalid.extend(f"{i['kind']}:{i['el']}" for i in issues)
    hero = frozenset({1}) if layout_name == "hero" else frozenset()
    viol = _col.violations(_col.build_boxes(els), hero)
    invalid.extend(f"clearance:{v['a']}×{v['b']}" for v in viol)
    if invalid:
        return {"valid": False, "invalid_reason": invalid,
                "density": None, "scores": {}, "total": -1.0}

    band = grid.CONTENT_BOTTOM - grid.CONTENT_TOP
    content = [e for e in elements
               if e.get("role") not in ("foot", "brandfoot", "logo")]
    bottoms = [e["y"] + e["h"] - slide_top for e in content
               if isinstance(e.get("y"), (int, float))
               and isinstance(e.get("h"), (int, float))]
    density = ((max(bottoms) - grid.CONTENT_TOP) / band) if bottoms else 0.0
    d_lo, d_hi = DENSITY_BAND.get(page_type, (0.45, 0.68))
    s_density = _interval_score(density, d_lo, d_hi)

    bullets = [e for e in content if str(e.get("id", "")).split(".", 1)[-1]
               .split(".")[0].startswith("bullet")]
    wrapped = sum(_bullet_lines(b) - 1 for b in bullets)
    s_read = max(0.0, 1 - 0.18 * wrapped)

    s_focal = None
    images = [e for e in content if e.get("role") == "image"]
    if page_type == "content-image" and images:
        share = max(i["w"] for i in images) / grid.CONTENT_W
        s_focal = _interval_score(share, *VISUAL_BAND)

    mass = [(e["x"] + e["w"] / 2, e["w"] * e["h"] * (0.5 if e.get("role") == "image" else 0.3))
            for e in content
            if isinstance(e.get("x"), (int, float)) and isinstance(e.get("w"), (int, float))]
    s_balance = None
    if mass:
        # 图片按面积折半计质量：视觉块天生比文字墨量大，全按面积会让
        # 所有图主导页一起得零分（那不是平衡信号，是惩罚信号）
        total = sum(m for _, m in mass)
        cx = sum(c * m for c, m in mass) / total if total else 0
        center = grid.PAD_X + grid.CONTENT_W / 2
        s_balance = max(0.0, 1 - abs(cx - center) / 400)

    scores = {"density": round(s_density, 3), "readability": round(s_read, 3)}
    if s_focal is not None:
        scores["focal"] = round(s_focal, 3)
    if s_balance is not None:
        scores["balance"] = round(s_balance, 3)
    weights = {k: WEIGHTS[k] for k in scores}
    wsum = sum(weights.values()) or 1.0
    total = sum(scores[k] * weights[k] for k in scores) / wsum
    return {"valid": True, "invalid_reason": [],
            "density": round(density, 3),      # 原始占比（不是得分）
            "scores": scores, "total": round(total, 3)}


def _up_repair_signals(measured: dict) -> list:
    """复用修复梯的硬信号（竖向溢出 / 标题写出列）。"""
    global _repair
    if _repair is None:
        _repair = _sibling("repair")
    return _repair.signals(measured)


__all__ = ["searchable", "score_page", "DENSITY_BAND", "VISUAL_BAND", "WEIGHTS"]
