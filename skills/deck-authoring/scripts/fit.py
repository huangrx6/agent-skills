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

# 正文带（与壳里的几何一致）—— 去 render.py 拿，不在这里重拄一份：
# 两份几何常量对同一张图，只会对出一个错的前提。
BAND_TOP = render.CONTENT_TOP
BAND_BOTTOM = render.CONTENT_BOTTOM
DEAD_SPACE = 0.55          # 内容高度不足正文带的这个比例 → 半页空

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
        # 建议给**最满**的那个：留白是构图，但能装满却不满 = 这页没做完
        best = sorted(fits, key=lambda c: c["density"])[-1]
        out.append(f"  建议：用 {best['kind']}（占 {best['density']:.0%}）——"
                   f" 它把正文带用得最满。")
        if all(c["density"] < DEAD_SPACE for c in fits):
            out.append(f"  注意：所有版式都不到 {DEAD_SPACE:.0%}（都偏稀）——"
                       f"内容太少了。考虑：把两页合成一页、每个条目写长一点"
                       f"（把“结论”展开成一句完整判断），或者换更满的版式。")
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
    args = ap.parse_args(argv[1:])

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
