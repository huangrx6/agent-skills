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


def compile_spec(deck_spec: dict, style: dict | None = None,
                 assets: dict | None = None) -> dict:
    """spec → resolved（决策层）。纯函数：同 spec + 同 seed（+ 同资产清单）恒等。

    v3：档位 / 布局 / 配色 / 图形类型都是**作者声明**（spec 或风格数据），
    这里只做合并、解析与留痕 —— 不再有自动推断与枚举选择。
    assets：`render.load_assets` 的产物 —— assetId → "assets/<file>" 的映射
    只在这里发生（§14 Asset Resolver v1：manifest 即选择），页对象携带
    解析后的最终路径，渲染器不见 assetId。
    """
    r = _render()
    brand_mod = r.brand_module
    deck = deck_spec["deck"]
    trace: list[dict] = []

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
    trace.append({"stage": "theme", "decision": color_set,
                  "reason": ["spec 显式声明 colorSet（v3：配色由作者定，"
                             "对比度由 ink/check 验收）"]})
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
    # 标题档映射：风格数据 titleTiers 覆盖缺省映射；spec 可逐页写 titleTier。
    # v3：映射不是脚本法条 —— 它是风格可以改的数据（值域仍锁在字号档名里）。
    title_tiers = {**r.TITLE_TIER, **(tokens.get("titleTiers") or {})}
    # 条目默认档：风格 bulletDefault，缺省 "bullet"；两栏页固定窄档（结构事实）。
    bullet_default = tokens.get("bulletDefault") or r.DEFAULT_BULLET_TIER
    slides_out: list[dict] = []
    for i, slide in enumerate(deck["slides"], 1):
        kind = slide.get("type")
        t_tier = slide.get("titleTier") or title_tiers.get(kind, r.DEFAULT_TITLE_TIER)
        if slide.get("titleTier"):
            trace.append({"stage": "typography", "slide": i,
                          "decision": f"titleTier:{t_tier}",
                          "reason": ["spec 逐页声明标题档"]})
        if kind == "two-column":
            b_tier = slide.get("bulletTier") or "bulletSmall"
        else:
            b_tier = slide.get("bulletTier") or bullet_default
        if slide.get("bulletTier"):
            trace.append({"stage": "typography", "slide": i,
                          "decision": f"bulletTier:{b_tier}",
                          "reason": ["spec 逐页声明条目档（v3 无按条数自动升降档）"]})
        # v3：档名是作者/风格数据 —— 拼错必须当场报，不能掉进 tier[...] 的 KeyError
        for role, tier_name in (("标题", t_tier), ("条目", b_tier)):
            if tier_name not in tier:
                raise SystemExit(
                    f"✗ 第 {i} 页的{role}档 {tier_name!r} 不在风格的 type 块里"
                    f"（可用 {sorted(tier)}）—— 检查 spec 的 titleTier/bulletTier "
                    f"或风格的 titleTiers/bulletDefault")
        # ── Layout：Family × Variant（第一片：content-image 三变体）────────
        # variant 本身在 spec 里，{**slide} 合并页对象时自动带进 resolved ——
        # compile 的职责是**留痕**：谁选的变体、为什么。自动选变体（按内容形状
        # 派生）要等 fit 的候选实测给数据，现在是显式才记、默认静默。
        # ── Asset：assetId → 最终路径（§14 优先级链 v1：manifest 即选择）────
        # spec 里的 image 写 assetId（语义引用）；清单里的 id → "assets/<file>"，
        # 不在清单里 → 原样（旧路径语义，demo/stress 全兼容）。
        image_val = slide.get("image")
        if image_val and assets:
            resolved_img = r.resolve_asset(assets, str(image_val))
            if resolved_img is not None:
                slide = {**slide, "image": resolved_img}
                entry = assets["assets"][str(image_val)]
                trace.append({"stage": "asset", "slide": i,
                              "decision": f"{image_val} → {resolved_img}",
                              "reason": [f"manifest 选中（source="
                                         f"{entry.get('source', '未标')}）",
                                         "assetId 是语义引用，路径只在 resolved 里出现；"
                                         "缺文件由 check 的「图片加载」门实测拦"]})
        # ── Chart：图形类型是作者声明（v3）—— 显式值已在页对象里，不再推断

        # ── Layout：作者声明的布局（v3：结构布局是渲染器能力，其余是 skin 自由层）
        layout = slide.get("layout")
        if layout:
            known = layout in r.IMAGE_LAYOUTS or layout in r.TWO_COL_LAYOUTS
            trace.append({"stage": "layout", "slide": i,
                          "decision": f"{kind}:{layout}",
                          "reason": ["spec 显式声明布局（图在哪侧/文图几几开是内容决策，"
                                     "写 spec 的人定，compile 只执行与留痕）",
                                     "渲染器结构布局" if known else
                                     "作者自造布局名 → 缺省结构 + data-layout，"
                                     "排法由 skin.css 写"]})
        dx, dy, rot = r.misregistration(tokens, seed, "page", i)
        # 决策与内容**合并进同一页对象**：resolved 自足 —— 渲染器只吃这一份，
        # 不需要回头读 spec（"resolved = read_json(...); html = render(resolved)"）。
        page = {**slide, "index": i, "kind": kind,
                "tTier": t_tier, "tSize": tier[t_tier],
                "bTier": b_tier, "bSize": tier[b_tier],
                "dx": dx, "dy": dy, "rot": rot}
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
    args = ap.parse_args(argv[1:])

    deckio = _load_sibling("deckio")
    spec = deckio.read_json(args.spec)
    resolved = compile_spec(spec, assets=_render().load_assets(args.spec))

    if args.out:
        deckio.write_json(args.out, resolved)
        print(f"✓ {args.out}（{len(resolved['deck']['slides'])} 页决策 · "
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
