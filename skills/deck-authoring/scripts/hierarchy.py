#!/usr/bin/env python3
"""信息层级：文本预算、视觉焦点、密度。**全是提示级**，理由见下。

## 为什么这三条是提示而不是阻塞

用户给的规范里，这一块的核心是"用**意图**控制，不用坐标控制"。而本仓库早就是那样了：
spec 里根本没有 x/y（`validate_spec.py` 的 `COORD_FIELDS` 把 `x`/`y`/`dx`/`dy`/`rot`
/`width`/`height` 直接判错）—— 坐标、字号、间距全部由脚本派生。所以"不要让 LLM 决定
x=327"这条**不需要改**，已经成立。

真正缺的是**判断一页做得好不好**的那几把尺子。而"好不好"里能测的部分只有：
文字预算、焦点强弱、内容密度。**它们的阈值取决于语境**（封面就该空、Dashboard 就该满），
所以是提示；一旦做成阻塞，第一份正常的 deck 就会被挡住，然后所有人开始忽略检查。

客观的硬约束（越界 / 重叠 / 文字溢出 / 图被放大）继续由 `check.py` 阻塞，不在这里。

## 视觉权重怎么算（为什么不用面积）

实测发现：**文字元素的 `w` 是整栏宽，不是字面宽**。一个 128px 的标题量出来是
`w=1432`（整个正文栏），而它的实际墨迹只占很小一块 —— 拿面积当"视觉权重"会得出
"标题和一段正文一样重"的荒唐结论。

所以权重按**字号 × 角色权重**算（字号就是墨迹尺寸），非文字元素（图 / 图表 / 装饰）
才用面积 —— 它们的盒子**就是**墨迹。这是启发式，所以它只出提示。

跑法：
    python3 scripts/hierarchy.py your.spec.json out.html
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)


def _load_sibling(name: str):
    key = f"_deck_{name}"
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, os.path.join(HERE, f"{name}.py"))
    if spec is None or spec.loader is None:
        raise SystemExit(f"✗ 加载不了 scripts/{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


deckio = _load_sibling("deckio")
render = _load_sibling("render")
measure = _load_sibling("measure")

# ═══════════════════════════════════════════════════════════════════════════
# 1. 文本预算（规范第 12 条）
#
# 为什么这条重要：**没有预算，任何布局系统最后都会被文字撑爆**。而撑爆之后的
# 第一反应如果是"选小一档字号"，那正是规范点名「绝对不要第一步缩字号」的做法
# （v3 已把按条数自动降档整体退役：档位由作者声明）。预算的作用是**在缩字号
# 之前把话说清楚**：报错里直接给修复顺序。
# ═══════════════════════════════════════════════════════════════════════════

# 规范第 12 条给的数（中文字数）。左是我们 spec 里的角色，右是上限。
BUDGET = {
    "cover": 12,          # 封面主标题（hero）
    "title": 24,          # 内页标题
    "subtitle": 40,
    "colTitle": 14,       # 卡片 / 栏标题
    "nodeLabel": 14,
    "bullet": 60,         # 单条正文（卡片正文同档）
    "caption": 40,
    "end": 12,
}

# 修复顺序（规范第 22 条）—— **顺序本身就是知识**：先动内容，再动版式，
# 最后才动字号。写进报错里，因为报错是人唯一一定会读的那段字。
REPAIR_ORDER = (
    "1. 删掉非必要的字（先删修饰语，再删整句）",
    "2. 拆信息：一条里塞了两件事就分成两条",
    "3. 换版式：`content-text` 装不下就上 `two-column` / `content-image`",
    "4. 拆成两页（页数没有上限，挤在一页才是问题）",
    "5. 最后才允许缩小字号 —— 调 `style.json` 的 `type` 阶梯，别改这一页",
)


def visual_len(text: str) -> float:
    """"字"数：中日韩字符算 1，拉丁词算 1（而不是每个字母算 1）。

    为什么不是 `len()`：`len("LLM")` 是 3，但它在版面上是一个词的宽度；
    而 `len("模型")` 是 2、版面宽度也是 2。混排时按 `len()` 数会把英文标题
    当成三倍长，误报。

    **标点不数**（`，。！` 不是内容）：预算是"这话有多长"的度量，标点不承担内容。
    第一版把 CJK 标点区（U+3000~U+303F）也算进去了，于是 `"，。！"` 数出 1 个字
    （实测）。
    """
    chars = 0.0
    word = False
    for ch in text or "":
        if "\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf":
            chars += 1                      # 汉字（含扩展 A）
            word = False
        elif ch.isascii() and ch.isalnum():
            if not word:
                chars += 1                  # 拉丁词按 1 个算
            word = True
        else:
            word = False                    # 标点、空白、全角符号都不数
    return chars


def budget_issues(deck: dict) -> list[str]:
    """逐页查文本预算。**提示级**：超了要说清怎么修，不是只说"超了"。"""
    out: list[str] = []
    for i, slide in enumerate(deck.get("slides", []), 1):
        kind = slide.get("type", "")
        checks = []
        if kind == "title":
            checks.append(("标题", slide.get("title"), BUDGET["cover"]))
            checks.append(("副标题", slide.get("subtitle"), BUDGET["subtitle"]))
        elif kind == "end":
            checks.append(("收尾语", slide.get("title"), BUDGET["end"]))
        else:
            checks.append(("标题", slide.get("title"), BUDGET["title"]))
            checks.append(("图注", slide.get("caption"), BUDGET["caption"]))
            for title_key, items in (("columns", slide.get("columns")),
                                     ("nodes", slide.get("nodes"))):
                for item in items or []:
                    checks.append((f"{title_key} 栏标题", item.get("title")
                                   or item.get("label"), BUDGET["colTitle"]))
                    for b in item.get("bullets", []) or []:
                        checks.append((f"{title_key} 条目", b, BUDGET["bullet"]))
                    checks.append((f"{title_key} 说明", item.get("note"), BUDGET["bullet"]))
            for b in slide.get("bullets", []) or []:
                checks.append(("条目", b, BUDGET["bullet"]))
        for label, text, cap in checks:
            if not text:
                continue
            n = visual_len(str(text))
            if n > cap:
                out.append(f"第 {i} 页的{label}有 {n:.0f} 字（建议 ≤{cap}）："
                           f"{str(text)[:24]}… —— 修法**按顺序**来：\n     "
                           + "\n     ".join(REPAIR_ORDER))
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 2. 视觉焦点（规范第 7 / 8 条）
#
# 「一页只能有一个第一焦点」是能算的：给每个元素一个权重，然后要求
# **top1 明显大于 top2**。这条比"字号要有层级"有用得多 —— 后者经常满足，
# 而一页仍然全是重点。
# ═══════════════════════════════════════════════════════════════════════════

# 角色权重：这是**判断**，不是测量。依据是"这个角色在版面上承担多少注意力"。
ROLE_WEIGHT = {
    "chart": 1.00, "image": 1.00, "logo": 0.55,
    "title": 0.85, "chartValue": 0.60, "numeral": 0.55,
    "subtitle": 0.40, "colTitle": 0.35, "nodeLabel": 0.30,
    "bullet": 0.22, "nodeNote": 0.18, "caption": 0.15,
    "foot": 0.05, "brandfoot": 0.05,
}

# 第一焦点要比第二焦点重多少才算"明显"。**相对值**，不是绝对值。
#
# 为什么必须是相对值：实测权重落在 3~6 的量级（demo 第 1 页 title 5.29 对
# subtitle 0.45，第 3 页 image 6.81 对 title 3.17）。绝对阈值 0.25 在这种量级下
# 等于"几乎相等"，永远不会响 —— 换了几何都测不出问题。相对 0.25 的意思是
# **领先者至少比第二名重 33%**。
MIN_FOCAL_GAP = 0.25

# 「一页不能全是重点」（规范第 8 条）：权重达到首名这个比例的，算"重点"。
# 超过 MAX_FOCAL_POINTS 个就算失败 —— 直接实现"primary_focal_points <= 1,
# secondary <= 2"。
FOCAL_SHARE = 0.60
MAX_FOCAL_POINTS = 3


# 把"占整页面积的比例"放大到好读的量级（满幅图 ≈ 1.0）。
WEIGHT_SCALE = 10.0


def weights(measured: dict, slide_no: int) -> list[tuple[str, float, str]]:
    """这一页每个元素的视觉权重 → [(role, weight, 文本/来源)]。

    **两边都折算成"占整页面积的比例"**，这样文字与图形可比。

    文字用**墨迹面积**：`measure.py` 早就量了 `textW`（离屏 span 量的真实文字宽，
    不受容器 `overflow:hidden` 影响）—— 拿它乘元素高度。**不能拿元素的 `w`**：
    实测标题的 `w` 是整栏宽（1432px），而它的墨迹只占一小块，用它算会得出
    "标题与一段正文一样重"的荒唐结论。

    换行不止一行时 `textW` 会比容器宽，所以取 `min(textW, w)`（那部分面积确实是
    铺满容器的）。
    """
    slide_area = render.SLIDE_W * render.SLIDE_H
    if not slide_area:
        return []
    out: list[tuple[str, float, str]] = []
    for el in measured.get("elements", []):
        if el.get("slide") != slide_no:
            continue
        role = str(el.get("role") or "")
        base = ROLE_WEIGHT.get(role)
        if base is None:
            continue
        # 数字由 measure.py 写出来；拿到的不是数字就跳过，不抛 —— 与 check.py 里
        # `_check_full_page_image` 同一个写法（同一条理由：一次探测缺字段不该让
        # 整轮报告崩掉）。
        w, h = el.get("w"), el.get("h")
        if not isinstance(w, (int, float)) or not isinstance(h, (int, float)):
            continue
        ink_w = w
        text_w = el.get("textW")
        if isinstance(text_w, (int, float)) and text_w > 0:
            ink_w = min(text_w, w)
        weight = base * ((ink_w * h) / slide_area) * WEIGHT_SCALE
        out.append((role, round(weight, 4), str(el.get("intendedText") or role)[:20]))
    return sorted(out, key=lambda x: -x[1])


def ink_centers(measured: dict, slide_no: int) -> list[tuple[float, float]]:
    """(墨迹面积, 墨心 x) 列表 —— 供左右平衡类评分用。

    与 `weights` 同一套墨迹口径（textW 截断、数字缺失跳过、不抛）—— 平衡
    不要在别处再发明一遍"什么算墨"。
    """
    out: list[tuple[float, float]] = []
    for el in measured.get("elements", []):
        if el.get("slide") != slide_no:
            continue
        w, h = el.get("w"), el.get("h")
        x = el.get("x")
        if (not isinstance(w, (int, float)) or not isinstance(h, (int, float))
                or not isinstance(x, (int, float))):
            continue
        ink_w = w
        text_w = el.get("textW")
        if isinstance(text_w, (int, float)) and text_w > 0:
            ink_w = min(text_w, w)
        out.append((ink_w * h, x + w / 2))
    return out


def focal_issues(measured: dict, deck: dict) -> list[str]:
    """一页应当有**一个**明显的第一焦点（规范第 8 条）。提示级。"""
    out: list[str] = []
    for i, slide in enumerate(deck.get("slides", []), 1):
        if slide.get("type") in ("end",):
            continue
        ranked = weights(measured, i)
        if len(ranked) < 2:
            continue
        top_weight = ranked[0][1]
        if top_weight <= 0:
            continue
        gap = (top_weight - ranked[1][1]) / top_weight
        heavy = [r for r in ranked if r[1] >= top_weight * FOCAL_SHARE]
        if gap < MIN_FOCAL_GAP:
            top = "、".join(f"{r}（{w}）" for r, w, _ in ranked[:3])
            out.append(f"第 {i} 页没有明显的第一焦点：最强的三项是 {top}，"
                       f"领先第二名只有 {gap:.0%}（建议 ≥{MIN_FOCAL_GAP:.0%}）—— "
                       f"一页全是重点等于没有重点。要么把其中一项做大，"
                       f"要么把其余的降一档")
        if len(heavy) > MAX_FOCAL_POINTS:
            names = "、".join(f"{r}" for r, _w, _l in heavy)
            out.append(f"第 {i} 页有 {len(heavy)} 项都达到首名权重的 "
                       f"{FOCAL_SHARE:.0%}（{names}）—— 规范第 8 条：一页最多 "
                       f"{MAX_FOCAL_POINTS} 个重点（1 个主 + 2 个次）。"
                       f"把其中几项降级：缩小字号、去掉强调色、或挪到下一页")
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 3. 密度（规范第 11 条）—— 分档名来自规范，阈值是工程启发式
# ═══════════════════════════════════════════════════════════════════════════

DENSITY_BANDS = (
    (0.35, 0.50, "Minimal", "极简"),
    (0.45, 0.65, "Normal", "常规"),
    (0.55, 0.75, "Information", "信息型"),
    (0.65, 0.82, "Dashboard", "看板型"),
)


def density_share(measured: dict, slide_no: int) -> float | None:
    """这一页的内容占**正文带**多少（0~1）。`fit.py` 用的是同一个口径。"""
    box = measure.slide_content_span(measured, slide_no)
    if box is None:
        return None
    top, bottom = box
    band = render.CONTENT_BOTTOM - render.CONTENT_TOP
    if band <= 0:
        return None
    return max(0.0, min(1.0, (bottom - render.CONTENT_TOP) / band))


def density_issues(measured: dict, deck: dict, band: str | None = None) -> list[str]:
    """密度落在哪一档、是否偏离预期。提示级（阈值是启发式，不是行业标准）。"""
    out: list[str] = []
    want = next((b for b in DENSITY_BANDS if b[2] == band), None)
    for i, slide in enumerate(deck.get("slides", []), 1):
        if slide.get("type") in ("title", "end"):
            continue
        # hero 变体：图就是主角，墨面 90%+ 是设计不是"太满"—— 这把四档尺子
        # 是给文字主导页的（fit 对 hero 用 _hero_whitespace 那把，两处同一道理）。
        if slide.get("type") == "content-image" and slide.get("variant") == "hero":
            continue
        share = density_share(measured, i)
        if share is None:
            continue
        if want and not (want[0] <= share <= want[1]):
            out.append(f"第 {i} 页密度 {share:.0%}，不在 {want[2]} 档"
                       f"（{want[0]:.0%}~{want[1]:.0%}）—— {want[3]}页面"
                       f"该更满/更空；想看疏密怎么调去跑 `fit.py`")
        elif not want:
            for lo, hi, name, zh in DENSITY_BANDS:
                if lo <= share <= hi:
                    break
            else:
                out.append(f"第 {i} 页密度 {share:.0%} 落在四档之外"
                           f"（Minimal 35~50% / Normal 45~65% / Information 55~75% / "
                           f"Dashboard 65~82%）—— 太满就删内容，太空就加锚点")
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 4. 硬约束 / 软约束——**必须分开**（规范第 21 条）
# ═══════════════════════════════════════════════════════════════════════════

# 这是给文档与读者看的一张表：哪一类失败必须重排，哪一类只是打分。
# 本模块只管右边那一列（软约束）；左边那一列在 `check.py` 里，是阻塞的。
HARD_CONSTRAINTS = (
    "元素越界（超出画布 / 安全区）",
    "元素重叠（文字压文字）",
    "文字溢出容器",
    "字号低于最小可读",
    "图片被放大渲染（会糊）",
    "图表裁掉标签",
)

SOFT_CONSTRAINTS = (
    "视觉焦点是否明显（hierarchy.focal_issues）",
    "内容密度是否合适（hierarchy.density_issues）",
    "文字是否超出建议长度（hierarchy.budget_issues）",
    "对齐 / 平衡 / 层级 / 风格一致 —— 见 references/layout-system.md 的打分表",
)


def report(spec_path: str, html_path: str, band: str | None = None) -> int:
    """把三条提示打出来。**永远返回 0** —— 它们是提示，不是门。"""
    spec = deckio.read_json(spec_path)
    deck = spec.get("deck", {})
    measured = measure.measure(html_path)
    groups = (("文本预算", budget_issues(deck)),
              ("视觉焦点", focal_issues(measured, deck)),
              ("内容密度", density_issues(measured, deck, band)))
    total = sum(len(items) for _name, items in groups)
    print(f"信息层级（{total} 条提示；都是提示级 —— 阈值取决于语境）\n")
    for name, items in groups:
        if not items:
            print(f"✓ {name}：没有要说的")
            continue
        print(f"── {name}（{len(items)}）")
        for item in items:
            print("  ·", item)
        print()
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="信息层级：文本预算 / 视觉焦点 / 内容密度")
    ap.add_argument("spec", help="deck-spec.json")
    ap.add_argument("html", help="渲染产物 out.html")
    ap.add_argument("--band", default=None,
                    help="期望的密度档（Minimal / Normal / Information / Dashboard）")
    args = ap.parse_args(argv[1:])
    return report(args.spec, args.html, args.band)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
