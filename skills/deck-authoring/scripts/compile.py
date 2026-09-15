#!/usr/bin/env python3
"""compile —— 把语义 spec 编译成 resolved deck（决策层，渲染的上游）。

## 为什么要有它

第三代规则（总编排 §25）：`Slide DSL → Compile/Resolve → resolved → Renderer 只画`。
此前 render.py 同时做决策（风格/品牌合并、色板解析、字号档、时间轴）和绘制——
上游 AI 越来越聪明，下游却把一切压回 7 个模具，且决策不可见（缩字号悄悄发生）。

compile 把决策搬出来：

- **Theme**：风格加载（双根）→ 品牌合并 → colorSet 解析（显式/auto 派生）
- **Typography**：每页标题档 / 条目档（bullet_tier 在这里有 trace，不再是静默缩字）
- **Geometry 种子**：每页错位（misregistration，按 seed 派生）
- **Asset**：logo 正/反白按纸色选
- **Motion**：时间轴（`timeline()`）

每个关键决策进 `trace`（§26 Decision Trace）：`{stage, slide?, decision, reason[]}`
—— 系统能解释"为什么这样设计"，而不是一锅端。

## resolved.deck.json（v1）

```jsonc
{"schemaVersion": 1, "kind": "resolved.deck",
 "style": {"name": "...", "tokens": {...}, "skin": "..."},   // 已含品牌合并
 "brand": {...}, "colorSet": "auto:creative", "colors": {...},
 "logoFile": "logo-inverse.svg",
 "title": "...", "seed": 1,
 "slides": [{"index": 1, "kind": "content-text", "tTier": "compact",
             "tSize": 96, "bTier": "bullet", "bSize": 32,
             "dx": 0.4, "dy": -0.3, "rot": 0.2}],
 "timeline": [{"slide": 1, "start": 0.0, "enter": 1.1, "hold": 3.4}],
 "trace": [{...}]}
```

render_resolved(resolved) **只消费这份**：不再加载风格、不再合并品牌、不再算档位
—— 渲染器不"想"。`render(spec)` = compile + draw（字节级不变，416 条测试钉着）。

跑法：
    python3 scripts/compile.py deck.spec.json -o resolved.deck.json
    python3 scripts/compile.py deck.spec.json --trace          # 只看决策
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_sibling(name: str):
    """同目录模块加载（仓库约定：importlib + sys.modules，不碰 sys.path）。

    render 惰性加载：render 模块级加载 palette/ink/brand 等，这里若顶层互导
    会拿到半成品模块。
    """
    key = f"_deck_compile_{name}"
    if key in sys.modules:
        return sys.modules[key]
    path = os.path.join(HERE, f"{name}.py")
    spec = importlib.util.spec_from_file_location(key, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了同目录模块：{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


_render_mod: Any = None       # 惰性加载的 render 句柄（Any：其契约由测试钉）


def _render() -> Any:
    """惰性拿 render：render 模块级加载 palette/ink/brand 等，顶层互导会拿到半成品。"""
    global _render_mod
    if _render_mod is None:
        _render_mod = _load_sibling("render")
    return _render_mod


SCHEMA_VERSION = 1
RESOLVED_KIND = "resolved.deck"

# 降档的理由文案 —— 缩字号是修复顺序的**第 13 位**（layout-system §28），
# 发生时必须可见：trace 里说清，check 里再提示一遍。
_TIER_REASON = "条目数超过 5 条档上限 → 降为 {tier}。缩字号是修复顺序第 13 位：" \
               "先删条目 / 拆页 / 换变体，别把降档当第一手段"


def compile_spec(deck_spec: dict, style: dict | None = None,
                 fit_variants: dict | list | None = None) -> dict:
    """spec → resolved（决策层）。纯函数：同 spec + 同 seed（+ 同实测数据）恒等。

    fit_variants：`fit --recommend` 的产物（list 或 {页码: rec}），只喂给
    variant:"auto" 的页 —— 显式 variant 永远赢，实测数据不越权改内容决策。
    """
    r = _render()
    brand_mod = r.brand_module
    deck = deck_spec["deck"]
    trace: list[dict] = []
    # 归一化：键统一转 str（JSON 落盘是 list，喂进来 list / dict 都得认；
    # str() 不会抛，脏条目静默丢弃后走"auto 无数据 → 默认"兜底，好过抛栈）。
    recs: dict[str, dict] = {}
    if isinstance(fit_variants, list):
        for rec in fit_variants:
            if isinstance(rec, dict) and "page" in rec:
                recs[str(rec["page"])] = rec
    elif isinstance(fit_variants, dict):
        for k, v in fit_variants.items():
            recs[str(k)] = v

    # ── Theme：风格（双根）→ 品牌合并 → colorSet ─────────────────────────
    resolved_style: dict = (style if style is not None
                            else r.load_style(deck.get("style", r.DEFAULT_STYLE)))
    brand = brand_mod.load(deck.get("brand"))
    if brand:
        trace.append({"stage": "theme", "decision": f"brand:{deck.get('brand')}",
                      "reason": [f"字体并入（{list(brand.get('fonts', {}))} 或整体替换）",
                                 "色板并入（同名键品牌赢，风格原有不删）"]})
    resolved_style = r._apply_brand(resolved_style, brand)
    tokens: dict = resolved_style["tokens"]
    seed = deck.get("seed", 1)

    color_set = r.resolve_color_set(tokens, deck)
    if deck.get("colorSet") in (None, "auto"):
        # 方向决策的理由进 trace（与 auto_set 同一决策链，纯函数可重放）
        palette_mod = _load_sibling("palette")
        _pick, dir_reasons = palette_mod.choose_direction(tokens, deck.get("mood"))
        trace.append({"stage": "theme", "decision": color_set,
                      "reason": ["spec 未指定 colorSet（auto）", *dir_reasons,
                                 "只动 primary/secondary，纸色文字不动（对比度保住）"]})
    else:
        trace.append({"stage": "theme", "decision": color_set,
                      "reason": ["spec 显式指定（手调基准）"]})
    colors = tokens["colorSets"][color_set]
    paper = colors.get("background", "#FFFFFF")

    # ── Asset：logo 正/反白按纸色 ─────────────────────────────────────────
    logo_file = brand_mod.logo_file(brand, paper)
    if brand:
        trace.append({"stage": "asset", "decision": f"logo:{logo_file or '（无品牌）'}",
                      "reason": [f"纸色 {paper} 相对亮度"
                                 f"{' < 0.45 → 反白版' if logo_file and 'inverse' in str(logo_file) else ' ≥ 0.45 → 正版'}"]})

    # ── Typography + 几何种子：逐页档位与错位 ─────────────────────────────
    tier = tokens["type"]
    slides_out: list[dict] = []
    for i, slide in enumerate(deck["slides"], 1):
        kind = slide.get("type")
        t_tier = r.TITLE_TIER.get(kind, r.DEFAULT_TITLE_TIER)
        n_bullets = len(slide.get("bullets", []))
        if kind == "two-column":
            b_tier = "bulletSmall"          # 两栏永远窄栏，不参与自适应
            reason = "两栏版式的栏宽固定为窄栏（不参与自适应）"
        else:
            b_tier = r.bullet_tier(n_bullets)
            if b_tier == "bulletLarge":
                # 升档是**好事**（内容少字就该大），不是修复信号 —— 但也要留痕：
                # 大字档是这页气质的一部分（statement 页靠它）。
                reason = f"条目 ≤3 → 大字档：内容少字就该大（statement 页的气质来源）"
            else:
                reason = _TIER_REASON.format(tier=b_tier)
        if b_tier != "bullet":
            trace.append({"stage": "typography", "slide": i,
                          "decision": f"{kind}:{b_tier}",
                          "reason": [reason]})
        # ── Layout：Family × Variant（第一片：content-image 三变体）────────
        # variant 本身在 spec 里，{**slide} 合并页对象时自动带进 resolved ——
        # compile 的职责是**留痕**：谁选的变体、为什么。自动选变体（按内容形状
        # 派生）要等 fit 的候选实测给数据，现在是显式才记、默认静默。
        variant = slide.get("variant")
        if variant == "auto":
            # auto：吃 fit --recommend 的实测分数（同内容同图，可复现）。
            # 没数据就回退默认并留痕 —— 无实测的选择是另一个拍脑袋。
            rec = recs.get(str(i))
            if rec and rec.get("variant") in r.IMAGE_VARIANTS:
                alts = "、".join(f"{a['variant']} {a['score']:.2f}"
                                 for a in rec.get("alternatives", []))
                trace.append({"stage": "layout", "slide": i,
                              "decision": f"{kind}:{rec['variant']}（auto→实测最佳）",
                              "reason": [f"fit 实测：{rec['variant']} score "
                                         f"{rec['score']:.2f}"
                                         + (f"（对手：{alts}）" if alts else ""),
                                         "数据来自 fit --recommend 的同内容同图实测，"
                                         "可复现；显式 variant 永远优先于 auto"]})
                variant = rec["variant"]
            else:
                trace.append({"stage": "layout", "slide": i,
                              "decision": f"{kind}:visual-right（auto 无数据 → 默认）",
                              "reason": ["spec 要 auto 但没喂实测数据："
                                         "fit --from-spec … --recommend --json-out "
                                         "> variants.json 落盘，compile --fit-variants 喂入",
                                         "回退默认而不是猜"]})
                variant = "visual-right"
        elif variant:
            trace.append({"stage": "layout", "slide": i,
                          "decision": f"{kind}:{variant}",
                          "reason": ["spec 显式指定 —— 变体是内容决策（图在哪侧/"
                                     "文图几几开），写 spec 的人定，compile 只执行与留痕"]})
        dx, dy, rot = r.misregistration(tokens, seed, "page", i)
        # 决策与内容**合并进同一页对象**：resolved 自足 —— 渲染器只吃这一份，
        # 不需要回头读 spec（"resolved = read_json(...); html = render(resolved)"）。
        page = {**slide, "index": i, "kind": kind,
                "tTier": t_tier, "tSize": tier[t_tier],
                "bTier": b_tier, "bSize": tier[b_tier],
                "dx": dx, "dy": dy, "rot": rot}
        if kind == "content-image":
            # resolved 里的 variant 必须是具体值（"auto" 是意图不是几何）——
            # 渲染器的封闭值集没有 auto，漏进去就是 SystemExit。
            page["variant"] = variant or "visual-right"
        slides_out.append(page)

    # ── Motion：时间轴 ────────────────────────────────────────────────────
    timeline = r.timeline(deck, tokens)

    return {
        "schemaVersion": SCHEMA_VERSION, "kind": RESOLVED_KIND,
        "style": {"name": resolved_style["name"], "tokens": tokens,
                  "skin": resolved_style["skin"]},
        "brand": brand, "colorSet": color_set, "colors": colors,
        "logoFile": logo_file,
        "title": deck.get("title", "deck"), "seed": seed,
        "deck": {"title": deck.get("title", "deck"), "slides": slides_out},
        "timeline": timeline, "trace": trace,
    }


def is_resolved(obj: dict) -> bool:
    """认得出 resolved（渲染入口据此分流：resolved 直渲，spec 先编译）。"""
    return obj.get("kind") == RESOLVED_KIND and "style" in obj


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description="把语义 spec 编译成 resolved.deck.json（决策出渲染，带 trace）")
    ap.add_argument("spec", help="deck.spec.json（语义层输入）")
    ap.add_argument("-o", "--out", default=None,
                    help="写出 resolved.deck.json（不给则只打印摘要）")
    ap.add_argument("--trace", action="store_true",
                    help="打印决策 trace（每条：阶段/决定/理由）")
    ap.add_argument("--fit-variants", default=None,
                    help="fit --recommend --json-out 的落盘产物：variant 为 auto 的页"
                         "按实测分数选（没喂的 auto 回退默认并留痕）")
    args = ap.parse_args(argv[1:])

    deckio = _load_sibling("deckio")
    spec = deckio.read_json(args.spec)
    fit_variants = None
    if args.fit_variants:
        # 变体产物顶层是 **list**（fit --json-out 落盘形态），deckio 按 spec
        # 校验会拒 —— json 直读，compile_spec 里已有类型归一化与兜底。
        import json as _json
        try:
            with open(args.fit_variants, encoding="utf-8") as fh:
                fit_variants = _json.load(fh)
        except (OSError, _json.JSONDecodeError) as exc:
            raise SystemExit(
                f"✗ 读不了变体实测产物 {args.fit_variants}：{exc}\n"
                f"  先跑：fit.py --from-spec <spec> --recommend --json-out "
                f"> {args.fit_variants}") from exc
    resolved = compile_spec(spec, fit_variants=fit_variants)

    if args.out:
        deckio.write_json(args.out, resolved)
        print(f"✓ {args.out}（{len(resolved['slides'])} 页决策 · "
              f"{len(resolved['trace'])} 条 trace · colorSet={resolved['colorSet']}）")
    if args.trace or not args.out:
        if not args.out:
            print(f"colorSet={resolved['colorSet']} · logo={resolved['logoFile'] or '—'} · "
                  f"{len(resolved['trace'])} 条决策")
        for t in resolved["trace"]:
            at = f"（第 {t['slide']} 页）" if "slide" in t else ""
            print(f"  [{t['stage']}]{at} {t['decision']}")
            for why in t["reason"]:
                print(f"      · {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
