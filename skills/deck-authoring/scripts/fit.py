#!/usr/bin/env python3
"""试排 —— 给定一页内容，实测**哪些版式装得下**。

## 它解决的是什么

写 spec 时最容易撞的墙是「猜版式」：6 条内容用 `content-text` 会不会溢出？
换 `two-column` 是不是就装得下？拆成两页每页几条？以前只能**写完 → 跑 check → 报溢出 →
改了再跑**，一轮一轮试。这个工具把那几轮压成一次。

## 它不估算 —— 它渲出来量

候选版式 + 各条目数的档位，全部摆进**同一份产物**渲染一次、开一次真浏览器量一次。
所以给出的数字（溢出多少 px、内容占正文带多少）就是真实几何，不是系数乘出来的。
这与 `measure.py` / `check.py` 是同一条路子：**不估，量**。

## 判据

正文带是 `[132, 824]`：上界是壳里 `.pad` 的 padding-top，下界是页脚（`bottom:52`
加一行字高）之上。三种判定：

| 判定 | 条件 | 意思 |
| --- | --- | --- |
| ✗ 溢出 | 内容底 > 824 | 装上会撞页脚或越出版面 |
| ⚠ 半页空 | 内容高度 < 正文带的 55% | 看着像"这页没做完"（安静风格最典型的死法） |
| ✓ 合适 | 其余 | |

「半页空」这条不是我编的：本仓库 swiss-grid 第一版就是"白底 + 左上标题 + 编号列表"，
渲出来下半页 55% 是死的，看着像页面没做完 —— 后来加了三个构图锚点才修好。
留白必须是**构图**，不是内容缺席。

跑法：
    python3 scripts/fit.py --from-spec deck.spec.json --slide 3
    python3 scripts/fit.py --title 核心结论 --bullet a --bullet b --bullet c
    python3 scripts/fit.py --json '{"title":"结论","bullets":["a","b","c","d","e"]}'
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_sibling(name: str):
    path = os.path.join(HERE, f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"_deck_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了同目录模块：{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


deckio = _load_sibling("deckio")
render = _load_sibling("render")
measure_mod = _load_sibling("measure")
hierarchy_mod = _load_sibling("hierarchy")   # 层级/焦点/平衡：同一份测量，不另立口径

# 正文带（与壳里的几何一致）—— 去 render.py 拿，不在这里重拄一份：
# 两份几何常量对同一张图，只会对出一个错的前提。
BAND_TOP = render.CONTENT_TOP
BAND_BOTTOM = render.CONTENT_BOTTOM
DEAD_SPACE = 0.55          # 内容高度不足正文带的这个比例 → 半页空

# ── CandidateScore：多目标，**不再"越满越好"** ──────────────────────────
# 规则侧完整公式：Fit .20 + Hierarchy .15 + Whitespace .15 + FocalClarity .15
#   + Balance .10 + SemanticFit .10 + StyleMatch .075 + DeckRhythm .075
#   − 惩罚（Overflow / SmallFont / Crowding / Repetition / FocalConflict / Cards）。
# 本工具量得到的维度：Fit / Whitespace / SemanticFit / **Hierarchy / Focal /
# Balance**（后三维从 hierarchy.weights 与 ink_centers 的实测来 —— Design
# Search 的评分器开始"会看"候选，不只是量密度）。StyleMatch / Rhythm 仍未
# 接入（要风格模型与跨页序列），report 里如实标注。
SCORE_WEIGHTS = {"fit": 0.20, "whitespace": 0.15, "semantic": 0.10,
                 "hierarchy": 0.15, "focal": 0.15, "balance": 0.10}
CROWDING_ABOVE = 0.85      # 占正文带超过这个比例 → 拥挤惩罚
CROWDING_PENALTY = 0.10
SMALLFONT_PENALTY = 0.10


def _whitespace_score(density: float) -> float:
    """留白分：舒适带 45%~75%（hierarchy 密度带的 Normal~Information）。

    带内 1.0；带外线性衰减 —— **稀不是满分也不是零分**（留白是构图），
    挤到 100% 是明确的坏（信息板化）。
    """
    if 0.45 <= density <= 0.75:
        return 1.0
    if density < 0.45:
        return max(0.0, density / 0.45)
    return max(0.0, 1.0 - (density - 0.75) / 0.25)


def _hero_whitespace(density: float) -> float:
    """hero 的留白维度：图为主角的页面，"呼吸感"来自图**完整占据**版面，
    不是文字密度。≥80% 满分，以下线性 —— 与 _whitespace_score 是两种
    同样诚实的主张：文字主导页要舒适带，图像主导页要完整。"""
    return min(1.0, max(0.0, density / 0.80))


def _semantic_score(kind: str, content: dict) -> float:
    """语义匹配：内容形状与版式的契合（不是"哪个装得多"）。"""
    n = len(content.get("bullets") or [])
    has_image = bool(content.get("image"))
    variant = kind.split(":")[1] if ":" in kind else None
    kind = kind.split(":")[0]          # "content-image:even" → 家族语义同默认
    if variant == "hero":
        # 图即陈述：条目越少越对（≥3 条就该用带正文的变体）
        return 1.0 if (has_image and n <= 2) else 0.2
    if kind == "content-image":
        return 1.0 if has_image else 0.0
    if kind == "two-column":
        return 1.0 if n >= 6 else (0.5 if n >= 4 else 0.2)
    # content-text：少条数大字页是它的主场（statement 的气质来源）
    return 1.0 if n <= 4 else (0.5 if n <= 5 else 0.2)


def _hierarchy_score(el_weights: list | None) -> float:
    """层级分（实测）：权重分布的尖度 = 1 − 归一化熵。

    标题主导的页面熵低 → 分高；"一页全是重点"熵顶满 → 分低（规范第 8 条：
    一页只允许一个主要 Takeaway 的可测代理）。
    """
    import math
    ws = [w for _r, w, _t in (el_weights or []) if w > 0]
    if len(ws) < 2:
        return 0.5                      # 没什么可排的：不给奖也不罚
    total = sum(ws)
    ps = [w / total for w in ws]
    entropy = -sum(p * math.log(p) for p in ps)
    concentration = max(0.0, min(1.0, 1.0 - entropy / math.log(len(ps))))
    # 熵尺对 3+ 个元素天然压缩（健康页 ≈0.19、极端主导 ≈0.64）—— sqrt 展宽
    # 量程（健康 ≈0.43、主导 ≈0.80、全平 0），顺序不变、区分力与其它维度相当。
    return round(concentration ** 0.5, 3)


def _focal_score(el_weights: list | None) -> float:
    """焦点分（实测）：第一名领先第二名多少 —— 复用 focal_issues 的判据
    （MIN_FOCAL_GAP 够阈值为 1.0），同一把尺子，只是从"报不报"变"打几分"。"""
    ws = sorted((w for _r, w, _t in (el_weights or []) if w > 0), reverse=True)
    if len(ws) < 2:
        return 0.5
    gap = (ws[0] - ws[1]) / ws[0]
    return round(min(1.0, gap / hierarchy_mod.MIN_FOCAL_GAP), 3)


def _balance_score(ink_cx: list | None) -> float:
    """平衡分（实测）：墨量加权的左右重心离版心中线的相对距离。"""
    pairs = ink_cx or []
    total = sum(w for w, _cx in pairs)
    if total <= 0:
        return 0.5
    center = render.SLIDE_W / 2
    cx = sum(w * x for w, x in pairs) / total
    return round(max(0.0, 1.0 - abs(cx - center) / center), 3)


def score_candidate(c: dict, content: dict) -> tuple[float, dict, list[str]]:
    """一个候选的多目标得分（0~0.45 满分基准）+ 分项 + 惩罚名。纯函数。"""
    is_hero = c["kind"].split(":")[-1] == "hero"
    parts = {"fit": 1.0 if c["fits"] else 0.0,
             "whitespace": round(
                 (_hero_whitespace if is_hero else _whitespace_score)(c["density"]), 3),
             "semantic": round(_semantic_score(c["kind"], content), 3),
             # 三维实测分：el_weights / ink_cx 由 analyze/recommend 从测量里带
             # 进候选；没有就 0.5（中性）—— 纯函数路径（合成候选）不崩。
             "hierarchy": _hierarchy_score(c.get("el_weights")),
             "focal": _focal_score(c.get("el_weights")),
             "balance": _balance_score(c.get("ink_cx"))}
    score = sum(parts[k] * SCORE_WEIGHTS[k] for k in SCORE_WEIGHTS)
    penalties: list[str] = []
    if not is_hero and c["density"] > CROWDING_ABOVE:
        score -= CROWDING_PENALTY
        penalties.append(f"拥挤（占带 {c['density']:.0%} > 85%）")
    n_total = len(content.get("bullets") or [])
    if c["kind"] == "content-text" and n_total > 5:
        score -= SMALLFONT_PENALTY
        penalties.append("最小字号档（缩字号是修复顺序第 13 位）")
    return round(score, 3), parts, penalties

# 试排哪些版式（只有能承载条目列表的才参与）
CANDIDATES = ("content-text", "two-column", "content-image")
MAX_SWEEP = 16             # 条目数上限的扫描范围（再多就是内容该拆页了）


def _split_even(items: list, parts: int) -> list[list]:
    """把条目尽量平均地分到 parts 栏（余数分给前面的栏）。"""
    out: list[list] = []
    per, extra = divmod(len(items), parts)
    at = 0
    for k in range(parts):
        take = per + (1 if k < extra else 0)
        out.append(items[at:at + take])
        at += take
    return out


def build_probe_deck(content: dict, columns: int = 2) -> tuple[dict, dict]:
    """摆出候选版式，返回 (deck_spec, 每页是什么)。

    全部塞进**一份**产物：渲一次、量一次，比逐版式各渲一次快得多，
    而且同一份产物里的几何可比（同样的壳、同样的字体回退结果）。
    """
    title = content.get("title", "")
    bullets = list(content.get("bullets") or [])
    image = content.get("image")
    slides: list[dict] = []
    labels: dict[int, dict] = {}
    n = len(slides)

    def add(slide: dict, kind: str, count: int | None = None) -> None:
        slides.append(slide)
        # 档位的**条目数当数据带着**，不从 detail 字符串里再 parse 回来 ——
        # 从展示文案反解数据是那种“改个措辞就静默坏掉”的写法。
        labels[len(slides)] = {"kind": kind, "count": count}

    for kind in CANDIDATES:
        if kind == "content-image" and not image:
            continue
        if kind == "two-column":
            if len(bullets) < 2:
                continue
            cols = _split_even(bullets, max(2, min(columns, len(bullets))))
            add({"type": "two-column", "title": title, "columns": [
                {"title": f"栏 {k}", "bullets": c} for k, c in enumerate(cols, 1)]},
                kind)
            continue
        if not bullets:
            continue
        s: dict = {"type": kind, "title": title, "bullets": bullets}
        if kind == "content-image":
            s["image"] = image
        add(s, kind)
        # 变体探针：content-image 不是一种版式，是一个**家族**。同一份产物里把
        # visual-left / even 也摆出来，CandidateScore 才有真候选可比 ——
        # compile 的"自动选变体"下一步就从这里取数（现在是显式才生效）。
        if kind == "content-image":
            for v in render.IMAGE_VARIANTS:
                if v == "visual-right":
                    continue                    # 默认就是它，上面已加
                add({"type": "content-image", "title": title, "bullets": bullets,
                     "image": image, "variant": v}, f"content-image:{v}")

    # 条目数扫描：找出 content-text / two-column 各自最多装几条。
    # 不能假设"越少越矮" —— 字号按条数分档（≤3 条用大字），所以 4 条可能比 3 条还矮。
    # 扫全部档位，报**能装下的最大条数**，与单调性无关。
    for kind in ("content-text", "two-column"):
        if len(bullets) < 2:
            continue
        for k in range(1, min(len(bullets) - 1, MAX_SWEEP) + 1):
            if kind == "content-text":
                add({"type": kind, "title": title, "bullets": bullets[:k]}, kind, k)
            else:
                cols = _split_even(bullets[:k], 2)
                add({"type": kind, "title": title, "columns": [
                    {"title": f"栏 {i}", "bullets": c} for i, c in enumerate(cols, 1)]},
                    kind, k)
    return ({"deck": {"title": title or "试排", "slides": slides}}, labels)


def _measure_row(measured: dict, no: int) -> tuple[float, float, float]:
    """一页的 (内容底, 溢出量, 占正文带比例)。溢出量为正就是撞出了正文带。

    内容占位走 `measure.slide_content_span` —— 与 check.py 的半页死白提示是**同一个**
    口径（自己再算一份的话，“fit 说装得下、check 说太稀”只是时间问题）。
    """
    span = BAND_BOTTOM - BAND_TOP
    box = measure_mod.slide_content_span(measured, no)
    if box is None:
        return (BAND_TOP, BAND_TOP - BAND_BOTTOM, 0.0)
    _top, bottom = box
    return (bottom, bottom - BAND_BOTTOM, (bottom - BAND_TOP) / span)


def analyze(measured: dict, labels: dict, content: dict) -> dict:
    """从测量结果里读出卖点。纯函数：给定同一份测量，结果恒定。

    ⚠️ “装得下”与“半页空”是**两件事**，不能合成一个判定：
      前者是硬对错（溢出=装不上），后者是质量信号（太稀）。
     ！第一版把它们合成一个 mark，于是“2 条内容、占了 46%”被当成“装不下”，
      给出“建议拆页 —— 拆成 1 页”这种废话。数字都对，**意思错了**。
    """
    candidates: list[dict] = []
    max_items: dict[str, int] = {}
    capped: set[str] = set()      # 扫到上限了 —— 那时只能说"至少 N 条"，不能说"最多"
    for no, meta in sorted(labels.items()):
        if no > len(measured.get("slides", [])):
            continue
        bottom, overflow, density = _measure_row(measured, no)
        count = meta.get("count")
        if count is not None:
            # 扫描档：只记“装得下”的最大条数（不依赖“越少越矮”——字号按条数分档）
            if overflow <= 0:
                prev = max_items.get(meta["kind"], 0)
                max_items[meta["kind"]] = count if count > prev else prev
                if count >= MAX_SWEEP:
                    capped.add(meta["kind"])
            continue
        candidates.append({"kind": meta["kind"], "bottom": round(bottom, 1),
                           # 实测三维的输入随候选走（同一份测量，report 保持纯函数）
                           "el_weights": hierarchy_mod.weights(measured, no),
                           "ink_cx": hierarchy_mod.ink_centers(measured, no),
                           "fits": overflow <= 0,
                           # `overflow` 是“**溢出**量”：装得下时是 0，不是负数。
                           # 有余多少是 `density` 的事 —— 一个名叫 overflow 的字段
                           # 报 −492 会把“还有余地”写成“溢出”，读的人得先想一下。
                           "overflow": round(overflow, 1) if overflow > 0 else 0.0,
                           "density": round(density, 3)})
    return {"candidates": candidates, "max_items": max_items, "capped": sorted(capped)}


def report(result: dict, content: dict, style: str, brand: str | None) -> str:
    bullets = content.get("bullets") or []
    out = [f"试排「{content.get('title', '')}」· {len(bullets)} 条 · 风格 {style}"
           + (f" / 品牌 {brand}" if brand else ""), ""]
    cands = result["candidates"]
    if not cands:
        out.append("  没有可试的版式（内容里没有条目？）")
        return "\n".join(out)
    out.append("  版式候选（真渲真量，不估算）")
    for c in cands:
        if c["fits"]:
            sparse = c["density"] < DEAD_SPACE
            mark = "⚠" if sparse else "✓"
            note = f"装得下，占正文带 {c['density']:.0%}" + ("（半页空）" if sparse else "")
        else:
            mark, note = "✗", f"撞出正文带 {c['overflow']:.0f}px"
        out.append(f"    {mark} {c['kind']:<15}{note}      内容底 {c['bottom']:.0f}px")

    fits = [c for c in cands if c["fits"]]
    out.append("")
    if fits:
        # 建议按**多目标评分**给（不再"越满越好"）：留白在舒适带、语义匹配、
        # 不触发拥挤/最小字号惩罚的候选赢。密度只是 Whitespace 维度的输入。
        scored = sorted(((*score_candidate(c, content), c) for c in fits),
                        key=lambda t: t[0], reverse=True)
        (score, parts, penalties, best) = scored[0]
        why = (f"留白 {parts['whitespace']:.2f} · 语义 {parts['semantic']:.2f} ·"
               f" 层级 {parts['hierarchy']:.2f} · 焦点 {parts['focal']:.2f} ·"
               f" 平衡 {parts['balance']:.2f}")
        extra = f"；惩罚：{'、'.join(penalties)}" if penalties else ""
        out.append(f"  建议：用 {best['kind']}（candidate score {score:.2f} ——"
                   f" {why}{extra}；占正文带 {best['density']:.0%}）。")
        out.append("  （已接入维度：Fit .20 + 留白 .15 + 语义 .10 + 层级 .15 +"
                   " 焦点 .15 + 平衡 .10（三维为 hierarchy 实测）− 拥挤/最小字号"
                   "惩罚；StyleMatch/Rhythm 未接入 —— 需风格模型与跨页序列）")
        if all(c["density"] < DEAD_SPACE for c in fits):
            out.append(f"  注意：所有版式都不到 {DEAD_SPACE:.0%}（都偏稀）。"
                       f"稀不是错误 —— 留白是构图，**不要为填满页面加内容**"
                       f"（反 slop：空洞口号/无证据数字/重复卡片都是这么来的）。"
                       f"要么接受留白，要么回内容层问：这页是否真有这么多可讲的"
                       f"（并页是内容决策，不是排版填空）。")
        return "\n".join(out)

    # 一个都装不下 —— 这时“最多几条”才有意义
    out.append("  条目数上限（装不下时才需要看）")
    if result["max_items"]:
        capped = set(result.get("capped") or ())
        for kind, n in sorted(result["max_items"].items()):
            # 扫到上限时只能说“至少 N 条” —— 说“最多”是把扫描边界当成了结论（写错过一次）
            word = f"至少 {n} 条（扫描上限就是 {MAX_SWEEP}）" if kind in capped else f"最多 {n} 条"
            out.append(f"    {kind:<15}{word}")
        room = sorted(result["max_items"].values())[-1]
        pages = (len(bullets) + room - 1) // room if room else 0
        out.append("")
        out.append(f"  建议：**拆页** —— 单页最多 {room} 条，这 {len(bullets)} 条要拆成 {pages} 页。")
    else:
        out.append("    （连 1 条都装不下 —— 先看看标题是不是太长了）")
        out.append("")
        out.append("  建议：**拆页 + 收短标题**。")
    return "\n".join(out)


def build_variant_probe(spec: dict, spec_dir: str | None = None) -> tuple[dict, dict]:
    """把 spec 里所有 content-image 页 × 三变体摆进**一份**探针产物。

    与 build_probe_deck 的分工：那个答"哪类版式装得下"（带条目扫描）；这个答
    "这一页用哪个变体"（只摆变体、带**真图** —— 图的高宽比是变体选择的真实
    输入，图裂了高度塌 0，量出来的就是错的）。

    图的相对路径按 spec 所在目录解析成绝对路径：探针 HTML 写在临时目录，
    相对 src 会指向不存在的位置。
    """
    deck = spec.get("deck", spec)
    base = spec_dir or "."
    probe_slides: list[dict] = []
    labels: dict[int, dict] = {}
    for page_no, s in enumerate(deck.get("slides", []), 1):
        if s.get("type") != "content-image" or not s.get("image"):
            continue
        img = str(s["image"])
        assets = render.load_assets_at(base)
        if assets and img in (assets.get("assets") or {}):
            img = render.resolve_asset(assets, img)   # assetId → assets/<file>
        if not os.path.isabs(img):
            cand = os.path.abspath(os.path.join(base, img))
            img = cand if os.path.exists(cand) else img
        for v in render.IMAGE_VARIANTS:
            probe_slides.append({"type": "content-image",
                                 "title": s.get("title", ""),
                                 "bullets": list(s.get("bullets") or []),
                                 "image": img, "variant": v})
            labels[len(probe_slides)] = {"kind": f"content-image:{v}", "page": page_no}
    probe = {"deck": {"title": deck.get("title", "变体实测"),
                      "style": deck.get("style") or render.DEFAULT_STYLE,
                      "colorSet": deck.get("colorSet"),
                      "seed": deck.get("seed", 1), "slides": probe_slides}}
    if deck.get("brand"):
        probe["deck"]["brand"] = deck["brand"]
    return probe, labels


def recommend(measured: dict, labels: dict, spec: dict) -> list[dict]:
    """从变体探针的实测里选每页最佳变体。纯函数（同测量 → 同结果）。

    打分复用 score_candidate；同分时按 render.IMAGE_VARIANTS 的默认序破平 ——
    平局偏向默认（visual-right），确定且保守。返回可直接落盘，
    compile --fit-variants 吃同一份结构。
    """
    deck = spec.get("deck", spec)
    slides = deck.get("slides", [])
    by_page: dict[int, list[tuple[str, dict]]] = {}
    for no, meta in sorted(labels.items()):
        if no > len(measured.get("slides", [])):
            continue
        _b, overflow, density = _measure_row(measured, no)
        variant = meta["kind"].split(":")[1]
        by_page.setdefault(meta["page"], []).append(
            (variant, {"fits": overflow <= 0, "density": round(density, 3),
                       "el_weights": hierarchy_mod.weights(measured, no),
                       "ink_cx": hierarchy_mod.ink_centers(measured, no)}))
    out: list[dict] = []
    for page_no, rows in sorted(by_page.items()):
        content = slides[page_no - 1] if page_no <= len(slides) else {}
        scored = []
        for variant, extra in rows:
            score, parts, pens = score_candidate(
                {**extra, "kind": f"content-image:{variant}"}, content)
            scored.append((score, variant, parts, pens, extra["density"]))
        scored.sort(key=lambda t: (-t[0], render.IMAGE_VARIANTS.index(t[1])))
        (score, variant, parts, pens, density) = scored[0]
        out.append({"page": page_no, "variant": variant, "score": score,
                    "density": density, "parts": parts, "penalties": pens,
                    "alternatives": [{"variant": v, "score": sc, "density": d}
                                     for sc, v, _p, _q, d in scored[1:]]})
    return out


def read_content(args) -> dict:
    if args.from_spec:
        spec = deckio.read_json(args.from_spec)
        slides = spec.get("deck", {}).get("slides", [])
        if not 1 <= args.slide <= len(slides):
            raise SystemExit(
                f"✗ --slide {args.slide} 越界：{args.from_spec} 只有 {len(slides)} 页")
        slide = dict(slides[args.slide - 1])
        if slide.get("columns"):                      # 两栏页：拍平成条目再试排
            flat: list[str] = []
            for col in slide["columns"]:
                flat.extend(col.get("bullets") or [])
            slide["bullets"] = flat
        if slide.get("nodes"):
            slide["bullets"] = [f"{n.get('label', '')} {n.get('note', '')}".strip()
                                for n in slide["nodes"]]
        return {"title": slide.get("title", ""), "bullets": slide.get("bullets") or [],
                "image": slide.get("image")}
    if args.json:
        try:
            data = json.loads(args.json)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"✗ --json 不是合法 JSON：{exc}") from exc
        if not isinstance(data, dict):
            raise SystemExit("✗ --json 的顶层应是对象")
        return {"title": data.get("title", ""), "bullets": data.get("bullets") or [],
                "image": data.get("image")}
    return {"title": args.title or "", "bullets": list(args.bullet or []), "image": None}


def _cli_recommend(args) -> int:
    """--recommend 的执行体：渲探针 → 量 → 选 → 输出（表 / JSON）。"""
    spec_path = os.path.abspath(args.from_spec)
    spec = deckio.read_json(spec_path)
    probe, labels = build_variant_probe(spec, os.path.dirname(spec_path))
    if not probe["deck"]["slides"]:
        print("（没有 content-image 页 —— 无变体可推荐）")
        return 0
    import tempfile
    with tempfile.TemporaryDirectory(prefix="deck-fitrec-") as tmp:
        html_path = os.path.join(tmp, "recommend.html")
        deckio.write_text(html_path, render.render(probe))
        measured = measure_mod.measure(html_path)
    recs = recommend(measured, labels, spec)
    if args.json_out:
        print(json.dumps(recs, ensure_ascii=False, indent=2))
    else:
        print(f"变体实测「{spec.get('deck', spec).get('title', '')}」·"
              f" {len(recs)} 个 content-image 页 · 风格 {probe['deck']['style']}")
        for rec in recs:
            alts = "、".join(f"{a['variant']} {a['score']:.2f}" for a in rec["alternatives"])
            print(f"  第 {rec['page']} 页 → {rec['variant']}"
                  f"（score {rec['score']:.2f}，占带 {rec['density']:.0%}；"
                  f"对手：{alts}）")
        print("  落盘：--json-out > variants.json，再 compile --fit-variants 喂入")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description="试排：给定一页内容，实测哪些版式装得下（渲一次、量一次）")
    ap.add_argument("--from-spec", default=None, help="从这份 spec 里取一页的内容")
    ap.add_argument("--slide", type=int, default=1, help="配合 --from-spec：第几页（从 1 数）")
    ap.add_argument("--json", default=None, help='直接给内容：{"title":…,"bullets":[…]}')
    ap.add_argument("--title", default=None, help="标题")
    ap.add_argument("--bullet", action="append", default=None, help="条目（可重复给多次）")
    ap.add_argument("--style", default=None, help="风格（缺省：spec 的，再缺省 swiss-grid）")
    ap.add_argument("--color-set", default=None, help="色板（缺省：spec 的，再缺省该风格的第一个）")
    ap.add_argument("--brand", default=None, help="品牌（缺省：spec 的）")
    ap.add_argument("--columns", type=int, default=2, help="two-column 试几栏（缺省 2）")
    ap.add_argument("--json-out", action="store_true", help="输出机读 JSON（给脚本用）")
    ap.add_argument("--recommend", action="store_true",
                    help="逐页实测 content-image 三变体并选最佳（配合 --from-spec；"
                         "--json-out 的产物喂给 compile --fit-variants）")
    args = ap.parse_args(argv[1:])

    if args.recommend:
        if not args.from_spec:
            raise SystemExit("✗ --recommend 需要 --from-spec（变体选择是对某一页内容+真图的）")
        return _cli_recommend(args)

    content = read_content(args)
    if not content["bullets"]:
        raise SystemExit("✗ 没有条目可试排 —— 用 --bullet / --json / --from-spec 给内容")

    style_name = args.style
    brand_name = args.brand
    color_set = args.color_set
    seed = 1
    if args.from_spec:
        deck = deckio.read_json(args.from_spec).get("deck", {})
        style_name = style_name or deck.get("style")
        brand_name = brand_name if args.brand else deck.get("brand")
        color_set = color_set or deck.get("colorSet")
        seed = deck.get("seed", 1)

    deck_spec, labels = build_probe_deck(content, args.columns)
    style_name = style_name or render.DEFAULT_STYLE
    deck_spec["deck"]["style"] = style_name
    deck_spec["deck"]["seed"] = seed
    # 色板必须合法：`_head` 会把它当事实（不在就报错退出）—— 缺省用该风格的第一个。
    if not color_set:
        color_set = next(iter(render.load_style(style_name)["tokens"]["colorSets"]), None)
    deck_spec["deck"]["colorSet"] = color_set
    if brand_name:
        deck_spec["deck"]["brand"] = brand_name
    # 试排的产物不该被当成交付物，写到临时目录（同目录写会让相对路径的图裂掉，
    # 但试排不带别的内容图 —— content-image 的图由 --image 决定，这里不涉及）。
    import tempfile

    tmp = tempfile.mkdtemp(prefix="deck-fit-")
    html_path = os.path.join(tmp, "fit.html")
    deckio.write_text(html_path, render.render(deck_spec))
    measured = measure_mod.measure(html_path)
    result = analyze(measured, labels, content)

    if args.json_out:
        print(json.dumps({"style": deck_spec["deck"]["style"], "brand": brand_name,
                          "content": content, **result}, ensure_ascii=False, indent=2))
    else:
        print(report(result, content, deck_spec["deck"]["style"], brand_name))
    # 一个都装不下 → 退出码 1：这是“必须拆页或减内容”的硬信号，不是建议。
    # 注意判据是 **fits**（硬对错），不是“满不满”—— 偏稀也是装得下的，不该退 1。
    return 0 if any(c["fits"] for c in result["candidates"]) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
