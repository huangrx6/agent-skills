#!/usr/bin/env python3
"""deck-spec.json → HTML。

两条硬规矩（都是量出来、并被脚本守着的）：
1. **渲染层不写死任何颜色/字号/字体** —— 全部来自 `styles/<style>/style.json`。
2. **同一份 spec + 同一个 seed = 完全一致的输出** —— 错位量/颗粒强度按 (seed, 元素)
   派生，不用全局 random（全局的话两次渲染就不一样，没法回归对比，也没法复现一版给别人）。

# 风格 seam：一种风格 = 一个目录

```
styles/<name>/
  style.json   token：色板 / 字号级数 / 字体 / 纹理 / 装饰 / 错位区间 / 对比度门槛
  skin.css     视觉层：颜色、字体、纹理、装饰观感
```

`render.py` 只出**语义骨架**：`section.slide` + `.title` / `.bullets` / `.col` / `.tl` / …
加几何。所有"长什么样"都在 `skin.css` 里。**加一种风格 = 加一个目录，不改这里。**

风格必须提供的 CSS 变量（契约，skin.css 与骨架都只认这几个）：
    --paper 底色    --text 正文色    --accent 主色    --accent-2 副色
    --display 标题字体    --body 正文字体    --viewer 浏览器外底色
（骨架里没有任何一处写死色值或字体名 —— 换风格就是换这几行变量 + 一张 skin.css。）
"""
from __future__ import annotations

import argparse
import html
import importlib.util
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_sibling(name: str):
    """动态加载同目录脚本（`scripts/` 不是包，同级 import 在静态层面无法解析）。

    把模块注册进 sys.modules 之后再 exec —— 写法沿用 `check_layout.py`。那一步是为
    `@dataclass` / 自引用 import 准备的（dataclasses._is_type 查
    sys.modules.get(cls.__module__)，拿到 None 会炸）。本 skill 的脚本都没有这两样，
    属防御性写法；它**不**负责“同一模块只加载一次”（实测：两次加载是两个对象）。
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{name}.py")
    mod_spec = importlib.util.spec_from_file_location(f"_deck_{name}", path)
    if mod_spec is None or mod_spec.loader is None:
        raise RuntimeError(f"加载不了同目录模块：{path}")
    module = importlib.util.module_from_spec(mod_spec)
    sys.modules[mod_spec.name] = module
    mod_spec.loader.exec_module(module)
    return module


deckio = _load_sibling("deckio")   # IO 收口：参数写错要报清楚，不甩 traceback

# 风格解析根（顺序即优先级）：用户自建 styles/ 在前；dev-tools/style-fixture/
# 是开发/测试夹具（demo、stress、测试套件用它跑通全链），**不是交付物**。
# 发布的 skill 不内置任何风格 —— 每份 deck 的风格按规则自建，
# 形状与自建指南见 references/style-architecture.md。
STYLE_ROOTS = (os.path.join(HERE, "..", "styles"),
               os.path.join(HERE, "..", "dev-tools", "style-fixture"))
DEFAULT_STYLE = "swiss-grid"
# content-image 的变体（Family × Variant，值封闭 —— validate_spec 同步）：
#   visual-right = 文 7 栅 + 图 5 栅（默认，历史上唯一的那一种）
#   visual-left  = 图先文后（镜像，宽度不动 —— 阅读从图开始/连续图页换侧换节奏）
#   even         = 6+6 均分（图与文等权，statement 用）
#   hero         = 图就是这一页的主角：满幅 12 栅 + 底部实心标题条
#                 （check 的全页图禁令对 hero role-aware 放行 —— 标题/条目
#                  仍是真 DOM 文本，"信息烤进图里"的禁止不适用）
IMAGE_VARIANTS = ("visual-right", "visual-left", "even", "hero")

# ── 版面几何：壳里那些数字的**唯一出处** ─────────────────────────────
# `SHELL_CSS` 里的 `.pad{padding:132px 84px}` 与 `.footrow{bottom:52px}` 是这几个值；
# check.py（判越界/死白）与 fit.py（试排）都读这里，不各自再拄一份。
# 拿两份几何常量去对同一张图，只会对出一个错的前提（本仓库已经踩过一次）。
grid_mod = _load_sibling("grid")   # 版面几何的唯一来源（网格 / 间距令牌 / 区域）

SLIDE_W, SLIDE_H = grid_mod.SLIDE_W, grid_mod.SLIDE_H
PAD_X, PAD_Y = grid_mod.PAD_X, grid_mod.PAD_Y
FOOT_BOTTOM, FOOT_H = grid_mod.FOOT_BOTTOM, grid_mod.FOOT_H
# 正文带：内容该待的竖向区间。下界是页脚之上 —— 内容压过它就是和页脚打架。
# 整数就是它们本来的样子（都是 px）：不做 float() 转一道，那只是给异常多一个入口。
CONTENT_TOP = PAD_Y
CONTENT_BOTTOM = SLIDE_H - FOOT_BOTTOM - FOOT_H

# 版式 → 用字号级数里的哪一档（级数本身在 style.json 的 type 里，是唯一来源）
TITLE_TIER = {"title": "cover", "content-text": "compact", "end": "end"}
DEFAULT_TITLE_TIER = "small"

# 条目根据**条数**选字号档：(上限, 档名)。
#
# 为什么按条数自适应：固定字号下，稀疏页（2 条）会留出半页死白，
# 密集页（7 条）又会撞出下缘 —— 同一档字号不可能同时服务两者。
# 这不是“好看一点”，是**构图问题**：留白必须是构图（有视觉锚点），不是内容缺席。
# （实测：瑞士栅格那版图文页只有 2 条、字号 32，页面下半 55% 是空的。）
BULLET_TIERS = ((3, "bulletLarge"), (5, "bullet"), (99, "bulletSmall"))

# `type` 级数里**渲染器与 skin 必读**的那些档位。
#
# 为什么要一个名单：新增风格时漏一档，渲染器不会报错 —— `tier["caption"]` 会
# KeyError（还算好），而 skin 里 `var(--t-something)` 拿不到值只会**静默地退回默认字号**，
# 那一页看着“就是有点怪”，查起来极贵。拿这份名单在 `style.py` 里当场报出来。
#
# 注意这是**下限**：skin 可以用 `--t-<任意键>` 再多拿几档（比如那张表里的 chartValue），
# 那些是自由的，不在名单里。
REQUIRED_TYPE_TIERS = frozenset({
    "cover", "compact", "small", "end",        # TITLE_TIER 的取值
    "subtitle", "caption", "foot",
    "bulletLarge", "bullet", "bulletSmall",    # BULLET_TIERS 的取值
    "colTitle", "nodeLabel", "nodeNote",
    "chartValue", "chartLabel",
})


def bullet_tier(n_items: int) -> str:
    for limit, tier in BULLET_TIERS:
        if n_items <= limit:
            return tier
    return "bulletSmall"


def _rng(seed, *parts) -> random.Random:
    return random.Random("|".join([str(seed)] + [str(p) for p in parts]))


def style_names() -> list[str]:
    """全部可用风格名（用户根在前，保持插入序去重）。"""
    names: list[str] = []
    for root in STYLE_ROOTS:
        for n in deckio.list_dirs(root):
            if n not in names:
                names.append(n)
    return names


def style_folder(name: str) -> str | None:
    """风格目录路径（含 style.json 的第一个根）；找不到返回 None。"""
    for root in STYLE_ROOTS:
        folder = os.path.join(root, name)
        if os.path.isfile(os.path.join(folder, "style.json")):
            return folder
    return None


def load_style(name: str = DEFAULT_STYLE) -> dict:
    """加载一个风格目录 → `{"name", "tokens", "skin"}`。

    两个文件都必须有：只有 token 没有 skin 会渲染出「有颜色没版式」的东西，
    只有 skin 没有 token 连色都没得填。缺一个就明确报出来，不猜。
    """
    for root in STYLE_ROOTS:
        folder = os.path.join(root, name)
        tokens_path = os.path.join(folder, "style.json")
        skin_path = os.path.join(folder, "skin.css")
        has_tokens = os.path.isfile(tokens_path)
        has_skin = os.path.isfile(skin_path)
        if has_tokens and has_skin:
            return {"name": name, "tokens": deckio.read_json(tokens_path),
                    "skin": deckio.read_text(skin_path)}
        if has_tokens or has_skin:
            raise SystemExit(f"✗ 风格 {name!r} 缺文件："
                             f"{'skin.css' if has_tokens else 'style.json'}\n"
                             f"  一个风格目录必须同时有 style.json + skin.css。")
    raise SystemExit(
        f"✗ 没有风格 {name!r}（现有：{style_names()}）\n"
        f"  自建：styles/<名>/ 里放 style.json + skin.css（形状见 "
        f"references/style-architecture.md）；\n"
        f"  dev-tools/style-fixture/swiss-grid 是开发夹具，可作参考拷改。")


def misregistration(tokens: dict, seed, *parts) -> tuple[float, float, float]:
    # misregistration 是**可选 effect**：风格没写就是"不错位"，不需要为
    # "没有这个效果"声明一坨零值区间（Swiss/Minimal 不该知道什么叫错位）。
    spec = tokens.get("misregistration") or {
        "offsetRangeX": (0.0, 0.0), "offsetRangeY": (0.0, 0.0),
        "rotationRange": (0.0, 0.0)}
    r = _rng(seed, "mis", *parts)
    return (round(r.uniform(*spec["offsetRangeX"]), 2),
            round(r.uniform(*spec["offsetRangeY"]), 2),
            round(r.uniform(*spec["rotationRange"]), 2))


def grain_opacity(tokens: dict, seed, *parts) -> float:
    # texture 同为可选 effect：没有纸纹层的风格返回 0（壳层据此也不发 .grain）。
    rng = (tokens.get("texture") or {}).get("grainOpacity")
    if not rng:
        return 0.0
    return round(_rng(seed, "grain", *parts).uniform(*rng), 3)


# ── 时间轴：t（秒）→ 每页的位置与时长 ────────────────────────────────────────
# 为什么时间轴算在 Python 里而不是 JS 里：**视频总长、帧数、每页切点都是它的下游产物**
# （animate.py 要拿总长去分配帧），而“同一份 spec 两次渲出同一段时间轴”是可测的。
# JS 只负责“给定 t 把 DOM 画成什么样”，不管时间轴本身。
def timeline(deck: dict, tokens: dict) -> list[dict]:
    """每页 [start, start+enter+hold)。

    `enter` = 入场编排跑完要多久；`hold` = 让人看完的**阅读时间**。

    hold 按内容量给，不是常数：5 条的页让观众读得比 2 条的久（“礼让观众”的量化）。
    入场编排里**标题先落、停一下、正文再上**（huashu 的“关键结果前停 0.5s”）——
    不停这一下，标题和条目一起涌上来，观众没有“看见”的动作。
    """
    mo = tokens["motion"]
    enter_s, hold_s = mo["enterMs"] / 1000, mo["holdMs"] / 1000
    stagger_s, title_hold_s = mo["staggerMs"] / 1000, mo["titleHoldMs"] / 1000
    read_per_item = mo["readPerItemMs"] / 1000
    out: list[dict] = []
    t = 0.0
    for i, slide in enumerate(deck["slides"], 1):
        n = max(len(slide.get("bullets") or slide.get("nodes") or slide.get("columns") or []), 1)
        # 首个非标题元素的延迟（与标题尾部重叠一点，避免中间出现空白段）
        first = enter_s * 0.55 + title_hold_s
        enter = first + (n - 1) * stagger_s + enter_s
        # §32 阅读时间按内容复杂度：图表页比纯文本页多停（看懂一组柱比读一句
        # 话慢）——每个数据项 +180ms，封顶 8 项；整页 hold 封 7s（clamp 上限）。
        chart_items = len(slide.get("data") or []) if slide.get("chart") else 0
        complexity_s = 0.18 * min(chart_items, 8)
        hold = min(hold_s + n * read_per_item + complexity_s, 7.0)
        out.append({"slide": i, "start": round(t, 3),
                    "enter": round(enter, 3), "hold": round(hold, 3)})
        t += enter + hold
    return out


def total_duration(deck: dict, tokens: dict) -> float:
    """整段时长（秒）。"""
    spans = timeline(deck, tokens)
    last = spans[-1]
    return round(last["start"] + last["enter"] + last["hold"], 3)


# ── 装饰墨块：由 style.json 的 decor.kind 分派 ────────────────────────────────
# 风格可以选一种装饰（或没有装饰）。加新装饰 = 在这里加一个分支 + 在 skin.css 里给样式。
def decor(tokens: dict, seed, index: int, kind_slide: str) -> str:
    """装饰元素。

    两重限制都在 token 里，不在代码里：
    - `types`：哪些版式放装饰（图文页/双栏/时间线的版心已被内容占满，再压一块是堆砌）
    - `zones`：放哪个角（孔版只用右侧两角 —— 左栏是文字栏）
    """
    spec = tokens.get("decor") or {}
    kind = spec.get("kind")
    if not kind or kind_slide not in spec.get("types", []):
        return ""                                   # 这个风格/这个版式不要装饰
    if kind == "halftone-circle":
        return _halftone_circle(spec, seed, index)
    if kind == "accent-block":
        # 大色块：给“数字当主角”那类风格补一块**色场**（左下或右下的底），
        # 它不抢字 —— 透明度很低，读起来是“这块版面归这一色管”。
        r = _rng(seed, "decor", index)
        size = r.choice(spec["sizes"])
        zone = r.choice(spec["zones"])
        css = {"tr": "right:-90px;top:-70px", "br": "right:-110px;bottom:-120px",
               "tl": "left:-90px;top:-70px"}[zone]
        return (f'<div class="decor-block" data-kind="accent-block" '
                f'data-zone="{zone}" data-size="{size}" '
                f'style="{css};width:{size}px;height:{round(size * 0.62)}px"></div>')
    raise SystemExit(f"✗ 认不出的装饰 kind={kind!r}")


def _halftone_circle(spec: dict, seed, index: int) -> str:
    """网点圆（叠印类风格用）。虚线描边画网点，不用 <pattern>：Chrome 导 PDF 会
    把 <pattern> 整块栅格化（实测 4 块半调 → 4 张位图）。"""
    r = _rng(seed, "decor", index)
    size = r.choice(spec["sizes"])
    zone = r.choice(spec["zones"])
    css = {"tr": "right:-60px;top:-40px", "br": "right:-130px;bottom:-140px"}[zone]
    step, half = 5, size / 2
    # 一行一条横虚线；dasharray 把每行切成方点。相位不重要（重复纹理）。
    dashes = "".join(f"M0 {y * step + step / 2:.1f}H{size}"
                     for y in range(size // step + 1))
    # 必须 clip 成圆 —— 虚线是**通栏**画的，不裁就是一块方底（视觉检查当场抓到 ✗）。
    cid = f"hc{index}"
    return (f'<svg class="halftone" data-kind="halftone-circle" data-zone="{zone}" '
            f'data-size="{size}" '
            f'style="{css};width:{size}px;height:{size}px" '
            f'viewBox="0 0 {size} {size}" aria-hidden="true">'
            f'<defs><clipPath id="{cid}">'
            f'<circle cx="{half}" cy="{half}" r="{half}"/></clipPath></defs>'
            f'<circle cx="{half}" cy="{half}" r="{half}" fill="var(--accent)"/>'
            f'<path clip-path="url(#{cid})" d="{dashes}" fill="none" '
            f'stroke="var(--paper)" stroke-width="2.5" stroke-dasharray="2.5 2.5"/></svg>')


# ── 骨架 CSS：**只有几何**，没有任何色值/字体名 ───────────────────────────────
# 判据：一条规则如果换个颜色/字体就变了，它属于 skin.css；只改位置/尺寸，才在这里。
SKELETON_CSS = """
:root{ __VARS__ }
html,body{margin:0;background:var(--viewer)}
.slide{position:relative;width:1600px;height:900px;background:var(--paper);
  overflow:hidden;margin:0 auto 36px}
.pad{padding:132px 84px}
/* 标题块：高度是版面几何（每种版式不同），字号由 --s-title 给（来自 type 级数） */
.titleblock{position:relative;display:block}
.tb-cover{height:158px}
.tb-compact{height:104px;margin-bottom:var(--sp-section)}
.tb-small{height:88px}
.sub{margin:0}
.two{display:flex;gap:var(--sp-item);align-items:flex-start;margin-top:var(--sp-group)}
.two .main{width:825.33px}
.imgwrap{margin:0;width:582.67px}
/* content-image 变体：v-even 6+6 均分（704px=span(6)，825.33+582.67+24=1432 不变）；
   v-left 只换 DOM 顺序（宽度不动），类名留给 skin 做侧别微调的钩子。 */
.two.v-even .main{width:704px}
.two.v-even .imgwrap{width:704px}
/* hero：图是这一页的主角 —— 满幅 12 栅 + 底部**实心**标题条。
   条用 --text 底 / --paper 字的反转色对：对比度与正文是同一个 token 保证
   （≥4.5 自动成立）。刻意不做半透明渐变 scrim —— 渐变透明端的文字对比度
   估不出来，实心条才可被门禁证明。 */
.herofig{position:relative;width:1432px;margin:0;overflow:hidden}
.herofig img{display:block;width:100%;height:100%;object-fit:cover}
.herofig .herobar{position:absolute;left:0;right:0;bottom:0;
  padding:18px 30px 18px 0;background:var(--text);color:var(--paper)}
.herofig .herobar .title{color:var(--paper);
  font-size:var(--s-colTitle,40px);line-height:1.3;white-space:normal}
.hero-bullets{margin-top:24px}
.imgwrap img{width:100%;display:block}
.cols{display:flex;gap:var(--sp-item);margin-top:var(--sp-item)}
.col{flex:1;min-width:0}
.tl{display:flex;gap:var(--sp-item);list-style:none;padding:0;margin:var(--sp-group) 0 0}
.tl li{flex:1;min-width:0;width:var(--tl-node,300px)}
.chartsrc{margin:calc(var(--sp-inner) * -0.5) 0 0;color:var(--text);opacity:.55;
  font:400 var(--s-caption,22px)/1.4 var(--body)}
.chartwrap{margin-top:var(--sp-item);width:1432px;padding:var(--sp-item);position:relative}
/* 图表的高度**由壳给死**（330px），宽度按 viewBox 比例自己算。
   为什么不能让它 width:100% 自己撑：那样高度会跟着容器宽度变 ——
   而各风格的 .chartwrap 内边距不同（34px vs 30px vs 0），于是同一张图表
   在不同风格里高 40~50px，页脚余量从 43 到 92 不等，有的发空有的贴边。
   钉死高度之后八套一致，余量稳定在 30~50px。 */
.chartwrap svg{position:relative;display:block;height:330px;width:auto;
  max-width:100%;margin:0 auto}
.end{position:absolute;left:84px;top:330px}
/* 页脚一行：页脚 + 品牌署名同在左下这一带。
   不用 space-between 把署名推到右边 —— 那样它会压在巨号页码上（三套风格都把右下
   给了页码）。所以是 flex-start + 间隔，页脚与署名并排。 */
.footrow{position:absolute;left:84px;right:84px;bottom:52px;display:flex;
  justify-content:flex-start;align-items:baseline;gap:28px}
.foot,.brandfoot{position:static}
/* 品牌 logo：位置在壳里给一个**能在四套风格都站住**的缺省（右上），某个风格需要
   另说就自己覆盖那一条 —— 与 .foot 同机制。
   约束**高度**而不是宽度：logo 多是横长条，锁高度才能让宽高比自然展开
   （给宽会有的被拉横、有的被压扁）。 */
.brandlogo{position:absolute;right:84px;top:58px;height:56px;width:auto}
.brandfoot{font:400 var(--s-foot, 20px)/1 var(--body);color:var(--text);opacity:0.42;
  letter-spacing:0.04em}
"""


def chart_svg(data: list[dict], unit: str = "", tag_attr: str = "") -> str:
    """柱状图：**几何全部由脚本算**，模型只出数据。

    方案里的规矩（第 2 层）：数据图表页的特色效果适用度低 —— 错位会毁掉可读性。
    所以这里只有**容器**做风格处理（半调底纹 + 描边框），柱与刻度保持干净、不带错位。
    柱高与数据成比例是硬要求，且由 check.py 独立复核（不是靠这里自觉）。
    """
    if not data:
        raise SystemExit("✗ chart 页需要 data: [{label, value}, …]")
    values: list[float] = []
    for k, d in enumerate(data):
        v = d.get("value")
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise SystemExit(f"✗ 第 {k} 条 chart 数据的 value 不是数字：{v!r}"
                             f"（图表页需要真数字，字符串会画不出比例）")
        # 上面已经确认是 int/float 且排除了 bool —— 不用再 float() 转一次
        values.append(v)
    peak = max(values) or 1.0
    # 图表自身的**比例**决定它在页面上占多高（SVG 是 width:100%，高度按比例来）。
    # 压测之前这里是 1100×460 —— 满宽渲染出 ~462px 高，加上标题块(152) + 容器上下
    # padding(68) + 图注(60) + 页边(132)，整页要 911px，**八套风格全部**把图注压进了
    # 页脚区，paper-ink 直接裁掉。demo 里根本没有图表页，所以从来没人看见。
    # 现在压到 1100×330：满宽渲染 ~331px，整页 ~787px，留 37px 余量。
    # 柱区占 250/330（比例与原来一致），上下给刻度标签留了头。
    w, h, base = 1100, 250, 286
    slot = w / len(data)
    bar_w = min(120.0, slot * 0.55)
    parts = [f'<svg viewBox="0 0 {w} {base + 44}" role="img" {tag_attr}>']
    for k, (d, v) in enumerate(zip(data, values)):
        bh = h * (v / peak)
        x = k * slot + (slot - bar_w) / 2
        y = base - bh
        parts.append(f'<rect class="bar" x="{x:.1f}" y="{y:.1f}" '
                     f'width="{bar_w:.1f}" height="{bh:.1f}"/>')
        parts.append(f'<text class="val" x="{x + bar_w / 2:.1f}" y="{y - 10:.1f}" '
                     f'text-anchor="middle">{d["value"]}{unit}</text>')
        parts.append(f'<text class="lbl" x="{x + bar_w / 2:.1f}" y="{base + 26:.1f}" '
                     f'text-anchor="middle">{html.escape(str(d["label"]))}</text>')
    parts.append(f'<line class="axis" x1="0" y1="{base}" x2="{w}" y2="{base}"/>')
    parts.append("</svg>")
    # 外层 chartwrap 是**结构**（图表容器 + 校验与测量的锚点），留在骨架里。
    # `.hf` 是**给 skin 留的钩子**（孔版在里面铺半调底纹）；不用它的 skin 拿到的
    # 是一个没有尺寸的空 div（skin 不写 .hf 样式就没任何视觉影响）。
    return f'<div class="chartwrap" {tag_attr}><div class="hf"></div>' + "".join(parts) + "</div>"


# ── deck 外壳：演示态（自动缩放 + letterbox + 键盘翻页 + 页码）──────────────
# 刻意做成**运行时的视图**，不是产物本身的版式。
#
# 产物文件永远是 1600×900、未缩放的竖向堆叠 —— 测量层（measure.py）用
# getBoundingClientRect 量真实像素，截图层（shots.py）按真实偏移滚屏，两者都依赖
# 这个几何。演示态只额外叠一层**整体相似变换**：等比缩放不会引入裁切，所以
# “量未缩放的原件”依然成立，不用为了演示能力推翻整个度量层。
SHELL_CSS = """
/* --k 由脚本按视口算；CSS 里算不出来 —— scale() 要的是无量纲数，
   而 min(100vw/1600, 100vh/900) 得到的是长度，两者不能互转。 */
html[data-view="present"] body{height:100%;overflow:hidden;display:grid;
  place-items:center;gap:0}
html[data-view="present"] .slide{display:none;margin:0;transform:scale(var(--k,1));
  transform-origin:center center}
html[data-view="present"] .slide.is-cur{display:block}
.hud,.hint{position:fixed;bottom:20px;font:400 20px/1 var(--body);color:var(--text);
  background:var(--paper);padding:10px 16px;letter-spacing:1px;opacity:0;
  transition:opacity .2s;pointer-events:none;z-index:9}
.hud{right:26px}
.hint{left:26px;font-size:18px}
html[data-view="present"] .hud{opacity:1}
html[data-view="present"] .hint{opacity:1}
/* 取帧态：只显当前页、**不缩放** —— 逐帧录制用。
   与演示态的区别：演示态要缩放到视口（给人看），取帧态要 1:1（给机器截）。
   壳隐藏：页码/快捷键提示是给人操作的，不该录进视频（huashu 坑 #9）。 */
html[data-view="frame"] body{height:auto;overflow:hidden;display:block}
html[data-view="frame"] .slide{display:none;margin:0}
html[data-view="frame"] .slide.is-cur{display:block}
html[data-view="frame"] .hud,html[data-view="frame"] .hint{display:none}
/* 打印/导 PDF：一页一张 1600×900，不缩放、不留阴影 —— 演示态是给屏幕的，
   纸面要的是原件本身（矢量 PDF 导出走这条路）。
   @page 必须显式给：不给的话 Chrome 用 Letter/A4，deck 会被缩小 + 四周留白
   （实测：6 页能出，但页尺寸是 Letter 的）。 */
@media print{
  @page{size:1600px 900px;margin:0}
  html,body{background:#fff;height:auto;display:block;overflow:visible}
  .slide{margin:0;transform:none;page-break-after:always;break-after:page;
    box-shadow:none;display:block !important}
  .hud,.hint{display:none !important}
  /* 纸面不留颗粒：颗粒是 feTurbulence，导 PDF 时整页会被栅格化成多张
     ~1366×769 位图（实测一页多 ~0.8MB），而它本身只有 0.08~0.15 不透明度、
     栅格化后还不到 1:1 —— 又大又糊。纸上本来就有纸纹。
     （这是**屏幕/纸面的有意差异**，不是漏了一句。屏幕上看得到颗粒。） */
  .grain{display:none !important}
}
"""

# 键盘翻页 + **时间轴引擎**。无依赖、不碰 DOM 结构（不包 wrapper）。
#
# 两套时钟共用同一个 `paint()`：
#   · 演示时走 rAF（墙钟）—— 翻到哪页就放哪页的入场
#   · 取帧时走 `__deck.seek(t)`（纯函数）—— 同一个 t 必出同一帧
# **同一段画代码**，所以“录出来”与“讲出来”不会跑偏。
#
# ⚠️ 这里绝不写 CSS transition：transition 走的是**墙钟**，逐帧 seek 渲染下每帧都是
# 独立截图，中间态取决于“截这一帧时真实过了多久”，完全不可复现（huashu 的坑 #18，
# 实测同一份动画三次能出两种结果）。动位移也用独立的 `translate`/`scale` 属性，
# 不用 `transform` —— 免得跟 skin 自己的 transform（歪一点、倾斜之类）互相覆盖。
SHELL_JS = """
(function(){
  var doc=document.documentElement;
  var slides=[].slice.call(document.querySelectorAll('section.slide'));
  if(!slides.length) return;
  var TL=window.__deck_timeline||[];
  var MO=window.__deck_motion||{};
  var hud=document.getElementById('__deck_page');
  var cur=0, raf=0;

  // 角色表从语义清单读（不另拄一份 —— 改了渲染层这里自动跟上）
  var ROLE={}; var manEl=document.getElementById('__deck_manifest');
  if(manEl){ try{ JSON.parse(manEl.textContent).forEach(function(e){ ROLE[e.id]=e.role; }); }catch(err){} }

  // 每页的编排表：DOM 顺序即编排顺序，角色决定**怎么上台**（§19 元素动画按
  // 类型设计，禁止所有元素统一 opacity 0→1）：
  //   title  → maskRevealY：遮罩从下揭开 + 落定（标题是视觉锚，要有重量）
  //   rule   → growX：段式线从左**画**出来（线是画的，不是浮的）
  //   image  → imageReveal：横向揭示（§20 左文右图 → 图在右侧揭开）+ 1.02→1 落定
  //   chart  → 容器先行（§31），柱从基线生长 growY/growX、折线 pathDraw、点弹出
  //   body   → fadeRise：淡入 + 小位移（不是纯 fade，也不是 0.4→1 —— 见 paint 里注）
  //   chrome → 页码/壳：跟标题走，不排进正文队列
  var PLAN=slides.map(function(sec, si){
    var span=TL[si]||{enter:1,hold:1};
    var body=0;
    return [].slice.call(sec.querySelectorAll('[data-m]')).map(function(el){
      var role=ROLE[el.getAttribute('data-m')]||'bullet';
      var kind = role==='title' ? 'title'
               : (role==='foot'||role==='brandfoot') ? 'chrome'
               : role==='image' ? 'image'
               : role==='chart' ? 'chart'
               : 'body';
      var delay = 0;
      if(kind==='body'||kind==='image'||kind==='chart'){
        delay = span.enter*0.55 + (MO.titleHoldMs||0)/1000 + (body++)*(MO.staggerMs||90)/1000;
      }
      var els=[el];
      var rules=[];
      if(kind==='title'){
        // 标题是**一组**：父块（swiss 的 2px 边框常画在它身上）一起遮罩；
        // .rule 不进组，单独 growX（否则线浮者出来，不是画的）。
        if(el.parentElement) els.push(el.parentElement);
        rules=[].slice.call(sec.querySelectorAll('.pad > .rule'));
      }
      // 图表的一次性准备在 PLAN 里算完（确定性）：柱的朝向看宽高比，
      // 折线长度 getTotalLength —— paint 每帧只做纯赋值。
      var parts=null;
      if(kind==='chart'){
        var bars=[].slice.call(el.querySelectorAll('.bar')).map(function(r){
          var w=parseFloat(r.getAttribute('width'))||1, h=parseFloat(r.getAttribute('height'))||1;
          return {el:r, horiz: w>h};
        });
        var lines=[].slice.call(el.querySelectorAll('.line')).map(function(p){
          var len=0; try{ len=p.getTotalLength(); }catch(err){ len=0; }
          if(len){ p.style.strokeDasharray=len; p.style.strokeDashoffset=len; }
          return {el:p, len:len};
        }).filter(function(x){ return x.len>0; });
        var dots=[].slice.call(el.querySelectorAll('.dot'));
        parts={bars:bars, lines:lines, dots:dots};
      }
      return {els:els, rules:rules, kind:kind, delay:delay, parts:parts};
    });
  });

  // 缓动。expoOut 是“起步快、刹车长”，给数字元素物理重量感；linear/ease 是 AI slop。
  function expoOut(p){ return p>=1?1:1-Math.pow(2,-10*p); }
  function overshoot(p){
    if(p>=1) return 1;
    var c=2.0, c3=c+1;
    return 1 + c3*Math.pow(p-1,3) + c*Math.pow(p-1,2);
  }
  function ease(p){ return (MO.easing==='overshoot') ? overshoot(p) : expoOut(p); }

  // 单页内 t（秒）→ DOM。**纯函数**：同一个 t 必出同一帧。
  function paint(si, t){
    var dur=(MO.enterMs||700)/1000;
    PLAN[si].forEach(function(it){
      var p=(t-it.delay)/dur; p = p<0?0:(p>1?1:p);
      var e=ease(p);
      // 段式线跟标题同拍，从左画出来（growX）
      it.rules.forEach(function(r){
        r.style.opacity='1';
        r.style.scale=e.toFixed(4)+' 1';
        r.style.transformOrigin='left center';
      });
      if(it.kind==='title'){
        // maskRevealY：遮罩从下揭开 + 26px 落定（视觉锚的重量）。
        // 正文不用 0.4→1 的 ghost 起点：第 0 帧必须是干净空态（抽帧 QA 钉着）。
        var m=(1-e)*100;
        it.els.forEach(function(el){
          el.style.opacity=e.toFixed(4);
          el.style.clipPath='inset('+m.toFixed(2)+'% 0 0 0)';
          el.style.translate='0 '+((1-e)*26).toFixed(2)+'px';
          el.style.scale=(1+(1-e)*0.012).toFixed(5);
        });
      } else if(it.kind==='image'){
        // imageReveal：从左向右揭开 + 1.02→1 萻定（§49 图片内容不得因动画变形，
        // 只允许这种近 1 的 settlescale）
        var w=(1-e)*100;
        it.els.forEach(function(el){
          el.style.opacity='1';
          el.style.clipPath='inset(0 '+w.toFixed(2)+'% 0 0)';
          el.style.scale=(1.02-0.02*e).toFixed(5);
        });
      } else if(it.kind==='chart'){
        // 容器先行（§31）：壳淡入微升；数据稍后 6% 起步
        it.els.forEach(function(el){
          el.style.opacity=e.toFixed(4);
          el.style.translate='0 '+((1-e)*10).toFixed(2)+'px';
        });
        var q=ease(Math.max(0,(p-0.06)/0.94));
        it.parts.bars.forEach(function(b){
          b.el.style.transformBox='fill-box';
          b.el.style.transformOrigin= b.horiz ? 'left center' : 'bottom center';
          b.el.style.scale= b.horiz ? q.toFixed(4)+' 1' : '1 '+q.toFixed(4);
        });
        it.parts.lines.forEach(function(l){
          l.el.style.strokeDashoffset=(l.len*(1-q)).toFixed(1);
        });
        it.parts.dots.forEach(function(d){
          d.style.transformBox='fill-box';
          d.style.transformOrigin='center';
          d.style.scale=q.toFixed(4);
        });
      } else {
        // body：fadeRise（标题落定后 stagger 上来）；chrome（页码）不动只淡
        var rise = it.kind==='chrome' ? 0 : 16;
        it.els.forEach(function(el){
          el.style.opacity=e.toFixed(4);
          el.style.translate='0 '+((1-e)*rise).toFixed(2)+'px';
          el.style.scale='1';
        });
      }
    });
  }
  function clearPaint(){
    PLAN.forEach(function(plan){ plan.forEach(function(it){
      it.els.forEach(function(el){ el.style.opacity=''; el.style.translate='';
        el.style.scale=''; el.style.clipPath=''; });
      it.rules.forEach(function(r){ r.style.opacity=''; r.style.scale='';
        r.style.transformOrigin=''; });
      if(it.parts){
        it.parts.bars.forEach(function(b){ b.el.style.scale=''; b.el.style.transformBox='';
          b.el.style.transformOrigin=''; });
        it.parts.lines.forEach(function(l){ l.el.style.strokeDashoffset=''; });
        it.parts.dots.forEach(function(d){ d.style.scale=''; d.style.transformBox='';
          d.style.transformOrigin=''; });
      }
    }); });
  }
  function span(si){ var s=TL[si]||{start:0,enter:1,hold:1}; return s; }
  function slideAt(t){
    for(var i=0;i<TL.length;i++){ if(t < TL[i].start+TL[i].enter+TL[i].hold) return i; }
    return Math.max(TL.length-1,0);
  }
  function onlyShow(si){
    slides.forEach(function(s,i){ s.classList.toggle('is-cur', i===si); });
    if(hud) hud.textContent=(si+1)+' / '+slides.length;
  }

  // ── 取帧接口（animate.py 用它）──────────────────────────────────
  function seek(t){
    t = t<0?0:t;
    var si=slideAt(t);
    if(doc.getAttribute('data-view')!=='frame') doc.setAttribute('data-view','frame');
    onlyShow(si);
    paint(si, t-span(si).start);
    cur=si;
    return si;
  }
  var lastT = TL.length ? TL[TL.length-1].start+TL[TL.length-1].enter+TL[TL.length-1].hold : 0;
  window.__deck = {duration: lastT, seek: seek};

  // ── 演示态 ──────────────────────────────────────────────────────
  function fit(){
    if(doc.getAttribute('data-view')!=='present') return;
    doc.style.setProperty('--k', Math.min(window.innerWidth/1600, window.innerHeight/900));
  }
  // 入场走 rAF（墙钟）—— 只放“入场”段，不放 hold
  function playEnter(si){
    var t0=performance.now();
    cancelAnimationFrame(raf);
    function step(now){
      var lt=(now-t0)/1000;
      if(lt < span(si).enter){ paint(si,lt); raf=requestAnimationFrame(step); }
      else { paint(si, span(si).enter); }
    }
    paint(si,0);
    raf=requestAnimationFrame(step);
  }
  function toScroll(){
    doc.setAttribute('data-view','scroll');
    cancelAnimationFrame(raf);
    clearPaint();                          // 清掉内联态，回到 CSS 的静态满态
    // `.is-cur` 在滚动态也留着：滚动态的 CSS 不用它（只有 present/frame 用），
    // 但它是“现在是第几页”的单一事实来源 —— 壳的页码与键盘导航都靠它对齐。
    onlyShow(cur);
    slides[cur].scrollIntoView({block:'center'});
  }
  function show(n,smooth){
    n=Math.max(0,Math.min(slides.length-1,n));
    cur=n;
    if(doc.getAttribute('data-view')==='present'){ onlyShow(n); fit(); playEnter(n); }
    else { toScroll(); }
    if(hud) hud.textContent=(n+1)+' / '+slides.length;
    try{ history.replaceState(null,'','#'+(n+1)); }catch(e){}
  }
  function setView(v){
    if(v==='present'){ doc.setAttribute('data-view','present'); onlyShow(cur); fit(); playEnter(cur); }
    else { toScroll(); }
  }
  function toggleFull(){
    if(document.fullscreenElement){ document.exitFullscreen(); }
    else if(doc.requestFullscreen){ doc.requestFullscreen(); }
  }
  document.addEventListener('keydown', function(e){
    var k=e.key, p=doc.getAttribute('data-view')==='present';
    if(k===' '||k==='Enter'||k==='PageDown'||k==='ArrowRight'||k==='ArrowDown'){
      if(p) e.preventDefault(); show(cur+1,true);
    } else if(k==='PageUp'||k==='ArrowLeft'||k==='ArrowUp'){
      if(p) e.preventDefault(); show(cur-1,true);
    } else if(k==='Home'){ if(p) e.preventDefault(); show(0,true); }
    else if(k==='End'){ if(p) e.preventDefault(); show(slides.length-1,true); }
    else if(k==='p'||k==='P'){ setView(p?'scroll':'present'); }
    else if(k==='f'||k==='F'){ toggleFull(); }
    else if(k==='Escape'){ if(p) setView('scroll'); }
  });
  window.addEventListener('resize', fit);

  // 开法：out.html?present 或 out.html#3；__recording 由录制/取帧端注入
  var start=0, m=/^#(\\d+)$/.exec(location.hash);
  if(m) start=parseInt(m[1],10)-1;
  if(window.__recording){
    doc.setAttribute('data-view','frame');      // 取帧态：1:1、只显当前页、隐壳
    seek(0);
    return;
  }
  if(/[?&]present\\b/.test(location.search)){ doc.setAttribute('data-view','present'); }
  show(start,false);
})();
"""


def _entry(mid: str, slide: int, role: str, text: str = "", size: float | None = None,
           **extra) -> dict:
    """语义清单的一条。几何不在里面 —— 几何由 measure.py 从真浏览器拿。

    这里只记“事实”：这个元素是什么、写了什么字、设计意图用多大字号。
    职责划得很清：**意图在渲染层，几何在测量层**。两者对不上就是 bug。

    额外键（目前只有图表数据）原样带走：导出层需要它，而它既不是几何、
    也不是“样式”，是这个元素的**内容**。
    """
    entry = {"id": mid, "slide": slide, "role": role, "text": text, "fontSize": size}
    entry.update(extra)
    return entry


def _head(title: str, style: dict, seed: int, color_set: str) -> str:
    """拼 `<head>`：骨架 + 风格 skin + 外壳，变量全部注入。"""
    tokens = style["tokens"]
    if color_set not in tokens["colorSets"]:
        raise SystemExit(f"✗ colorSet={color_set!r} 不在风格 {style['name']!r} 里"
                         f"（可用：{sorted(tokens['colorSets'])}）—— "
                         f"跑 validate_spec.py 能提前拦住这个")
    colors = tokens["colorSets"][color_set]
    text = ink_module.text_color(colors)
    tier = tokens["type"]
    vars_ = [
        # 间距令牌（grid.py 的 ramp + 语义档）：壳与 skin 里的 gap **只许**用这些，
        # 不许再写裸数字 —— 那是"间距无律"的来源（实测 10 个 gap 出现 7 种值）。
        *[f"{k}:{v}" for k, v in grid_mod.spacing_vars().items()],
        f"--paper:{colors['background']}", f"--accent:{colors['primary']}",
        f"--accent-2:{colors['secondary']}", f"--text:{text}",
        f"--display:{tokens['fonts']['display']}", f"--body:{tokens['fonts']['body']}",
        f"--viewer:{tokens['viewerBackground']}",
        f"--grain-op:{grain_opacity(tokens, seed, 'page')}",
    ]
    # 字号级数整份注入 --t-*：skin.css 与版式都用它，Python 侧也读同一份
    for key, value in tier.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            vars_.append(f"--t-{key}:{value}px")
    # 动画参数（时间轴本身另走 __deck_timeline，这里只给 JS 算单元素进度用）
    mo = tokens["motion"]
    vars_.append(f"--mo-enter:{mo['enterMs']}ms")
    vars_.append(f"--mo-ease:{mo['cssEase']}")
    head = ("<!doctype html><html lang=\"zh\"><head><meta charset=\"utf-8\">"
            f"<title>{html.escape(title)}</title><style>\n"
            + SKELETON_CSS.replace("__VARS__", ";".join(vars_))
            + "\n/* ── 风格 skin：" + style["name"] + " ── */\n"
            + style["skin"].replace("__GRAIN_SVG__", _grain_svg(tokens))
            + "\n" + SHELL_CSS + "\n"
            # 字体：样式栈里出现的清单字体，本地有就注入 @font-face。
            # 为什么不靠"装进系统"：实测 macOS 的字体缓存不会因为 cp 一个文件就刷新 ——
            # 字体装对了、名字也写对了，Chrome 仍然回退。@font-face 立刻生效，
            # 而且顺带让 Chrome 出 PDF 时把字形子集嵌进去（读者不需要装字体）。
            + fonts_module.face_css([tokens['fonts']['display'], tokens['fonts']['body']])
            + "\n</style></head><body>\n")
    return head


def _grain_svg(tokens: dict) -> str:
    """纸纹噪点（data URI）。skin.css 里用 `background-image:url("__GRAIN_SVG__")`。

    无 texture 的风格返回空串 —— 占位符必须被替换掉，哪怕替换成"什么都没有"。
    """
    freq = (tokens.get("texture") or {}).get("grainBaseFrequency")
    if freq is None:
        return ""
    return ("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' "
            "width='220' height='220'><filter id='n'><feTurbulence "
            f"type='fractalNoise' baseFrequency='{freq}' numOctaves='2'/>"
            "<feColorMatrix type='matrix' values='0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
            "0 0 0 1 0'/></filter><rect width='220' height='220' "
            "filter='url(%23n)'/></svg>")


ink_module = _load_sibling("ink")  # 叠印与对比度只有一处定义，不重抄
brand_module = _load_sibling("brand")
fonts_module = _load_sibling("fonts")  # 字体清单与 @font-face（清单是数据，不是硬编码）
chart_module = _load_sibling("chart")   # 图表引擎：DSL → 确定性 SVG（八类）
palette_module = _load_sibling("palette")  # 色彩语法与派生（auto 主题从这里出）
compile_module = _load_sibling("compile")  # 决策层：spec→resolved（render 只画）


def _apply_brand(style: dict, brand: dict) -> dict:
    """把品牌资产并进风格 token。

    在 `_head` 之前合并，后续全部环节（CSS 变量注入 / 语义清单 / 导出）自然看到
    品牌后的值 —— 不需要在十个地方各判断一次“是风格还是品牌”。

    优先级见 brand.py 模块头：**品牌赢在“是谁”（色板 / 字体 / logo），
    风格赢在“怎么表达”（版面 / 构图 / 运动）**。
    """
    if not brand:
        return style
    tokens = dict(style["tokens"])
    tokens["fonts"] = brand_module.merge_fonts(tokens["fonts"], brand)
    tokens["colorSets"] = brand_module.merge_color_sets(tokens["colorSets"], brand)
    merged = dict(style)
    merged["tokens"] = tokens
    return merged


def resolve_color_set(tokens: dict, deck: dict) -> str:
    """colorSet 名；省略 / "auto" → 语义决策方向（mood → 风格语法 → safe）。

    规则口径（总编排 §17 / 品牌协议 §5）：Style 出**语法与手调基准**，方向由
    spec 的 mood 或风格的 color_creativity 决定 —— seed 只管可复现，不做
    审美决策（"换 deck 换配色看 seed"是已修掉的老根因）。
    check.py 也用它，保证两边看到同一套色（几何唯一来源的同款纪律）。
    """
    name = deck.get("colorSet")
    if name in (None, "auto"):
        name, _ = palette_module.auto_set(tokens, deck.get("seed", 1),
                                          deck.get("mood"))
    return name


# ── 资产清单（§12 统一 Asset Pipeline 的入口，v1）───────────────────────
# schema 封闭：{"schemaVersion": 1, "assets": {id: {"file", "source", "note"}}}
# file 相对 assets/ 目录；解析后的最终 src = "assets/<file>"（相对 spec 目录
# = 相对产物 HTML）。没有 manifest 时 image 走旧的"相对路径"语义（全兼容）。
ASSET_MANIFEST_KEYS = frozenset({"schemaVersion", "assets"})
ASSET_ENTRY_KEYS = frozenset({"file", "source", "note"})


def load_assets_at(directory: str) -> dict | None:
    """读 <directory>/assets/manifest.json；没有 → None（旧路径语义）。

    schema 违规 = ERROR（封闭字段集，不静默猜意图）。
    """
    path = os.path.join(directory, "assets", "manifest.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"✗ 读不了资产清单 {path}：{exc}") from exc
    if not isinstance(data, dict) or set(data) != set(ASSET_MANIFEST_KEYS):
        raise SystemExit(f"✗ {path} 的顶层字段应为 {sorted(ASSET_MANIFEST_KEYS)}"
                         f"（封闭），实际 "
                         f"{sorted(data) if isinstance(data, dict) else type(data)}")
    if data.get("schemaVersion") != 1:
        raise SystemExit(f"✗ {path} 的 schemaVersion 只支持 1，"
                         f"实际 {data.get('schemaVersion')!r}")
    entries = data.get("assets")
    if not isinstance(entries, dict):
        raise SystemExit(f"✗ {path} 的 assets 应是 {{id: {{file, …}}}}")
    for aid, entry in entries.items():
        if not isinstance(entry, dict) or set(entry) - set(ASSET_ENTRY_KEYS):
            raise SystemExit(f"✗ {path} 的资产 {aid!r} 字段应为 "
                             f"{sorted(ASSET_ENTRY_KEYS)} 的子集（封闭）")
        if not isinstance(entry.get("file"), str) or not entry["file"]:
            raise SystemExit(f"✗ {path} 的资产 {aid!r} 缺必填 file")
    return data


def load_assets(spec_path: str) -> dict | None:
    return load_assets_at(os.path.dirname(os.path.abspath(spec_path)))


def resolve_asset(assets: dict | None, image_value: str) -> str | None:
    """assetId → "assets/<file>"；不是清单里的 id → None（按旧路径语义走）。

    §14 优先级链 v1：manifest 即选择（selected 的落点）；generated/provided
    的区分由 entry.source 记录。禁止缺图联网找图 —— 这里只做映射，不碰网络。
    """
    entry = ((assets or {}).get("assets") or {}).get(image_value)
    if entry is None:
        return None
    return f"assets/{entry['file']}"


def render(deck_spec: dict, style: dict | None = None,
           assets: dict | None = None) -> str:
    """渲染。输入两种都认（第三代链路：`Slide DSL → compile → resolved → Renderer 只画`）：

    - 语义 spec：先经 `compile.compile_spec` 决策（风格/品牌合并、色板、字号档、
      时间轴、assetId 解析都在那边定，带 trace），再面 `render_resolved`；
    - resolved.deck（`kind: "resolved.deck"`）：**直面，不做任何决策** ——
      不加载风格、不合并品牌、不算档位。

    assets：`load_assets` 的产物（spec 同目录 assets/manifest.json）——
    assetId → 文件的映射只发生在 compile（决策层），渲染器只见最终路径。
    """
    if compile_module.is_resolved(deck_spec):
        return render_resolved(deck_spec)
    return render_resolved(compile_module.compile_spec(deck_spec, style,
                                                       assets=assets))


def render_resolved(resolved: dict) -> str:
    """直渲 resolved.deck.json。**只画，不想**：所有输入都在 resolved 里。

    决策（色板/档位/错位/时间轴/logo 选版）由 compile.py 定并记 trace；
    本函数不加载风格、不合并品牌、不调用 bullet_tier/misregistration/timeline
    —— 渲染器里没有第二套决策，是"去决策化"的物理保证。
    """
    deck = resolved["deck"]
    style = resolved["style"]
    brand = resolved["brand"]
    tokens = style["tokens"]
    tier = tokens["type"]
    seed = resolved["seed"]
    out = [_head(resolved["title"], style, seed, resolved["colorSet"])]

    man: list[dict] = []          # 语义清单：元素身份 + 意图（几何由 measure.py 量）

    def tag(mid: str, slide_no: int, role: str, text: str = "", size: float | None = None,
            **extra) -> str:
        """登记一条并返回 `data-m` 属性串。"""
        man.append(_entry(mid, slide_no, role, text, size, **extra))
        return f'data-m="{mid}"'

    total = len(deck["slides"])
    # 尾页 = **end 版式那一页**，不是数组最后一页。常见 deck 里两者重合（谢谢页收尾），
    # 但附件页跟在后面也很常见 —— 那时该上 logo 的是谢谢页，不是附件页。
    # 没有 end 页的 deck 就退回最后一页（那才是它的“尾页”）。
    end_slide = total
    for k, s in enumerate(deck["slides"], 1):
        if s.get("type") == "end":
            end_slide = k
            break
    # 品牌 logo 选哪个文件由 compile 按纸色定好（resolved["logoFile"]）——
    # 这里只把文件变成内嵌 URI 与导出路径引用，不做选择。
    logo_file = resolved["logoFile"]
    colors = resolved["colors"]
    logo_uri = brand_module.logo_data_uri(brand, logo_file)
    logo_ref = brand_module.logo_ref(brand, logo_file)

    def title_html(text: str, mid_attr: str) -> str:
        """标题：**单层**。`data-text` 留给 skin 想做叠加装饰时用（attr() 取）。"""
        body = html.escape(text)
        return f'<h1 class="title" {mid_attr} data-text="{body}">{body}</h1>'

    for i, slide in enumerate(deck["slides"], 1):
        kind = slide.get("type")
        # 档位与错位是 compile 的决策（带 trace），这里只读 —— 渲染器不“想”。
        t_tier = slide["tTier"]
        tsize = slide["tSize"]
        # 两栏页永远是窄栏，不参与自适应（compile 已定，含理由）
        b_tier = slide["bTier"]
        bsize = slide["bSize"]
        # 错位是**整页一个值**（真实孔版一张纸过一次滚筒）；按 seed 派生，
        # 在 compile 里算好，这里只读。
        dx, dy, rot = slide["dx"], slide["dy"], slide["rot"]
        # data-idx：给 skin 一个**零成本的页码钩子**（.slide::after{content:attr(data-idx)}）。
        # 用属性而不是再加一个元素：安静派风格的构图需要一个字号锚点，但为此往每页
        # 塞一个 div、还得同步进清单和测量层，不值。
        out.append(f'<section class="slide" data-slide="{i}" data-idx="{i:02d}" '
                   f'style="--dx:{dx}px;--dy:{dy}px;--rot:{rot}deg">')
        out.append(decor(tokens, seed, i, kind))
        out.append('<div class="pad">')
        title_mid = f"s{i}.title"
        th = title_html(slide.get("title", ""), tag(title_mid, i, "title",
                                                    slide.get("title", ""), tsize))
        if kind == "title":
            out.append(f'<div class="titleblock tb-{t_tier}" '
                       f'style="--s-title:{tsize}px">{th}</div>')
            if slide.get("subtitle"):
                sub_attrs = tag(f"s{i}.subtitle", i, "subtitle", slide["subtitle"],
                                tier["subtitle"])
                out.append(f'<div class="sub subtitle" style="--s-subtitle:{tier["subtitle"]}px" '
                           f'{sub_attrs}>{html.escape(slide["subtitle"])}</div>')
            out.append('<div class="rule misreg"></div>')
        elif kind == "content-text":
            out.append(f'<div class="titleblock tb-{t_tier}" '
                       f'style="--s-title:{tsize}px">{th}</div>')
            items = "".join(
                f'<li {tag(f"s{i}.bullet.{bi}", i, "bullet", b, bsize)}>'
                f'<i>■</i>{html.escape(b)}</li>'
                for bi, b in enumerate(slide.get("bullets", [])))
            out.append(f'<ul class="bullets" style="--s-bullet:{bsize}px">{items}</ul>')
        elif kind == "content-image":
            # variant 判定要在 titleblock 之前：hero 的标题只住 herobar，
            # 顶部再立一个 titleblock 就是双标题（而且把 648px 的图顶出正文带）。
            variant = slide.get("variant") or "visual-right"
            if variant not in IMAGE_VARIANTS:
                raise SystemExit(
                    f"✗ 第 {i} 页（content-image）未知变体 {variant!r}；"
                    f"支持 {list(IMAGE_VARIANTS)}（validate_spec.py 会先拦住）。")
            if variant != "hero":
                out.append(f'<div class="titleblock tb-{t_tier}" '
                           f'style="--s-title:{tsize}px">{th}</div>')
            items = "".join(
                f'<li {tag(f"s{i}.bullet.{bi}", i, "bullet", b, bsize)}>'
                f'<i>■</i>{html.escape(b)}</li>'
                for bi, b in enumerate(slide.get("bullets", [])))
            # 干净报错，不要甩一个 KeyError 栈：validate_spec.py 本该先拦住
            # （它现在有 REQUIRED_SLIDE_FIELDS），但 render 也可能被别的入口直接调。
            src = slide.get("image")
            if not src:
                raise SystemExit(
                    f"✗ 第 {i} 页（content-image）没有 image —— 这个版式的全部内容"
                    f"就是那张图；请补上文件名，或把这一页换成 content-text。"
                    f"（validate_spec.py 会在渲染之前拦住这种 spec）")
            img_attrs = tag(f"s{i}.image", i, "image", src)
            # 图注放在 <figure> 里的 <figcaption>，不是另外挂一个 div：
            # 语义上它属于这张图（读屏器会念成图的一部分），样式上它跟着图的宽度
            # （640px）而不是跟着正文栏 —— 压测时才发现 content-image 之前
            # **根本不能带图注**，而给图配一行注是很自然的写法。
            cap = ""
            if slide.get("caption"):
                cap_attrs = tag(f"s{i}.caption", i, "caption", slide["caption"],
                                tier["caption"])
                cap = (f'<figcaption class="chartcap" {cap_attrs}>'
                       f'{html.escape(slide["caption"])}</figcaption>')
            # Family(content-image) × Variant：spec/compile 决定文图栅格分配，
            # 渲染只执行。默认 visual-right 必须**逐字节**等于旧输出（重构不改像素）。
            # （variant 已在 titleblock 之前判定 —— hero 不立独立标题块。）
            main_html = (f'<div class="main"><ul class="bullets" '
                         f'style="--s-bullet:{bsize}px">{items}</ul></div>')
            img_html = (f'<figure class="imgwrap" {img_attrs}>'
                        f'<img src="{html.escape(src)}" alt="">{cap}</figure>')
            if variant == "visual-left":       # 图先文后
                out.append(f'<div class="two v-left">{img_html}{main_html}</div>')
            elif variant == "even":            # 6+6 均分
                out.append(f'<div class="two v-even">{main_html}{img_html}</div>')
            elif variant == "hero":            # 图为主角：满幅 + 实心标题条
                # 无条目 648px（占整页 64% —— check 对 hero 放行，标题仍是
                # 真 DOM 文本）；带条目压到 520px 给正文留位。caption/条目
                # 跟在图后的普通流里（对比度走纸面，不走图上）。
                hero_h = 520 if items else 648
                bullets_html = (f'<ul class="bullets small hero-bullets" '
                                f'style="--s-bullet:{bsize}px">{items}</ul>'
                                ) if items else ""
                out.append(f'<figure class="herofig" {img_attrs} '
                           f'style="height:{hero_h}px">'
                           f'<img src="{html.escape(src)}" alt="">'
                           f'<div class="herobar">{th}</div></figure>'
                           f'{bullets_html}{cap}')
            else:                              # 默认：文 7 + 图 5，图在右
                out.append(f'<div class="two">{main_html}{img_html}</div>')
        elif kind == "two-column":
            out.append(f'<div class="titleblock tb-{t_tier}" '
                       f'style="--s-title:{tsize}px">{th}</div>')
            cols = []
            for ci, col in enumerate(slide.get("columns", [])[:2]):
                li = "".join(
                    f'<li {tag(f"s{i}.col{ci}.bullet.{bi}", i, "bullet", b, bsize)}>'
                    f'<i>■</i>{html.escape(b)}</li>'
                    for bi, b in enumerate(col.get("bullets", [])))
                band = "a" if ci == 0 else "b"
                coltitle = col.get("title", "")
                h3_attrs = tag(f"s{i}.col{ci}.title", i, "subtitle", coltitle,
                               tier["colTitle"])
                cols.append(f'<div class="col"><div class="band {band}"></div>'
                            f'<h3 {h3_attrs} style="--s-colTitle:{tier["colTitle"]}px">'
                            f'{html.escape(coltitle)}</h3>'
                            f'<ul class="bullets small">{li}</ul></div>')
            out.append('<div class="cols">' + "".join(cols) + "</div>")
        elif kind == "timeline":
            out.append(f'<div class="titleblock tb-{t_tier}" '
                       f'style="--s-title:{tsize}px">{th}</div>')
            nodes = []
            for ni, node in enumerate(slide.get("nodes", []), 1):
                label, note = node.get("label", ""), node.get("note", "")
                lab_attrs = tag(f"s{i}.node{ni}.label", i, "subtitle", label,
                                tier["nodeLabel"])
                note_attrs = tag(f"s{i}.node{ni}.note", i, "bullet", note,
                                 tier["nodeNote"])
                nodes.append('<li><span class="dot"></span>'
                             f'<b {lab_attrs}>{html.escape(label)}</b>'
                             f'<em {note_attrs}>{html.escape(note)}</em></li>')
            # 节点宽度由**网格**算，不写死：写死 300px 时 6 节点会到 1970px
            # （超出内容宽 538px，靠 flex 收缩硬扛 —— 那是"挤"的来源之一）。
            n_nodes = max(1, len(slide.get("nodes", [])))
            node_w = (grid_mod.CONTENT_W - (n_nodes - 1) * grid_mod.GUTTER) / n_nodes
            out.append('<ol class="tl" style="--s-nodeLabel:%dpx;--s-nodeNote:%dpx;'
                       '--tl-node:%.2fpx">%s</ol>'
                       % (tier["nodeLabel"], tier["nodeNote"], node_w, "".join(nodes)))
        elif kind == "end":
            out.append(f'<div class="end" style="--s-title:{tsize}px">{th}</div>')
        elif kind == "chart":
            # **结论先行**（规范第 5 条）：写了 message 就让它当大标题 —— 图表的
            # 标题该是"DeepSeek 调用量领先"，不是数据集名。原 title 降为小标签。
            message = str(slide.get("message", "")).strip()
            headline = message or th
            out.append(f'<div class="titleblock tb-{t_tier}" '
                       f'style="--s-title:{tsize}px">{html.escape(headline)}</div>')
            if message and str(slide.get("title", "")).strip():
                # ⚠️ 这里要用**原始标题文本**：th 是渲染好的 <h1> HTML，
                # 直接塞会把整串标签转义后印在页上（实测踩过）。
                out.append(f'<div class="chartsrc">'
                           f'{html.escape(str(slide.get("title", "")))}</div>')
            # 图表把**数据本身**也带进清单：导出层要拿它建原生图表（数据可改），
            # 而数据不是几何 —— 几何仍旧只从 measure.py 来。
            chart_attrs = tag(f"s{i}.chart", i, "chart", "", None,
                              data=slide.get("data", []),
                              series=slide.get("series", []),
                              chart=chart_module.infer_chart_type(slide)[0],
                              emphasis=slide.get("emphasis", {}),
                              unit=slide.get("unit", ""))
            # ⚠️ 外层 chartwrap 是**结构**：校验与测量的锚点（tag_attr 挂它身上），
            # `.hf` 是给 skin 的半调钩子。旧 chart_svg() 自己包这层，换引擎时丢过
            # 一次 —— check.py 两条图表检查都以它为锚，丢了就全部静默通过（实测）。
            out.append(f'<div class="chartwrap" {chart_attrs}><div class="hf"></div>'
                       + chart_module.svg(slide, colors) + "</div>")
            if slide.get("caption"):
                cap_attrs = tag(f"s{i}.caption", i, "bullet", slide["caption"],
                                tier["caption"])
                out.append(f'<div class="chartcap" {cap_attrs}>{html.escape(slide["caption"])}</div>')
        else:
            raise SystemExit(f"✗ 未知版式 type={kind!r}（支持 title / content-text / "
                             f"content-image / two-column / timeline / chart / end）")
        out.append("</div>")
        # 页脚一行：**页脚与品牌署名同处一个 flex 行**。
        #
        # 为什么不是各自绝对定位在左右两头：测完才发现的 —— 四套风格里有三套把
        # 右下角给了巨号页码（`.slide::after{content:attr(data-idx)}`），署名放右下
        # 就直接压在页码上（抽帧图里看得很清楚）。页脚那一带（左下）四套风格都是空的，
        # 而且“文档元信息”本来就该在一块儿。
        foot_text = f'{deck.get("title", "")} / {i:02d}'
        out.append('<div class="footrow">')
        out.append(f'<div class="foot" style="--s-foot:{tier["foot"]}px" '
                   f'{tag(f"s{i}.foot", i, "foot", foot_text, tier["foot"])}>'
                   f'{html.escape(foot_text)}</div>')
        if brand.get("footer"):
            bf = str(brand["footer"])
            out.append(f'<div class="brandfoot" style="--s-foot:{tier["foot"]}px" '
                       f'{tag(f"s{i}.brandfoot", i, "brandfoot", bf, tier["foot"])}>'
                       f'{html.escape(bf)}</div>')
        out.append('</div>')
        # 品牌 logo。**没品牌就不渲染这个元素** —— 不是渲染一个空占位。
        # src 是 base64 内嵌（产物自己完整，挪到哪都不裂）；清单里给的却是
        # **技能相对**路径（导出脚本据此找原图）—— 所以标了 src_base，让导出端知道
        # 该往哪儿解析（`image` 字段那种相对 HTML 的解析在这里是错的）。
        if logo_uri and brand_module.shows_logo(brand, kind, i, end_slide):
            out.append(f'<img class="brandlogo" src="{logo_uri}" alt="" '
                       f'{tag(f"s{i}.logo", i, "logo", logo_ref, None, src_base="skill")}>')
        # 纸纹层只在风格声明了 texture 时发射 —— 没有纸纹的风格**不该**有
        # 这个 DOM（不是"opacity:0 的隐形层"：看不见不等于不存在）。
        if tokens.get("texture"):
            out.append('<div class="grain"></div>')
        out.append("</section>")

    # 清单随产物一起走（不另写文件）：渲染、测量、导出读的是同一份事实。
    payload = json.dumps(man, ensure_ascii=True, separators=(",", ":")).replace("<", "\\u003c")
    out.append(f'<script type="application/json" id="__deck_manifest">{payload}</script>')
    # 时间轴与运动参数也随产物走：JS 引擎不自己算时间轴（那是 render.py 的职责，
    # animate.py 还要拿它去分配帧）。
    # ensure_ascii 只针对**这两个内嵌 JSON 载荷**（正文里的中文当然是 UTF-8 原文）——
    # 载荷走 \uXXXX 转义，是为了它在任何转存/重编码环节都不会被改坏。
    # （早先这里写成“保持产物是纯 ASCII”，不实：`<title>` 与正文本来就是 UTF-8。）
    spans = resolved["timeline"]            # compile 已定（Python 算，可测可回归）
    motion = {k: v for k, v in tokens["motion"].items() if k != "note"}
    out.append("<script>window.__deck_timeline="
               + json.dumps(spans, separators=(",", ":"))
               + ";window.__deck_motion="
               + json.dumps(motion, ensure_ascii=True, separators=(",", ":"))
               + ";</script>")
    # 壳：页码 / 快捷键提示 / 翻页脚本。**不给它们打 data-m** ——
    # 它们是壳不是内容，进了清单就会污染“清单条数 == 实测元素数”那条不变量。
    out.append(f'<div class="hud"><span id="__deck_page">1 / {total}</span></div>')
    out.append('<div class="hint">← → 翻页 · F 全屏 · P 演示/滚动</div>')
    out.append(f"<script>{SHELL_JS}</script>")
    out.append("</body></html>")
    return "\n".join(out)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="deck-spec.json → HTML")
    ap.add_argument("spec")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--style", default=None,
                    help=f"风格目录名（缺省读 spec 的 deck.style，再缺省 {DEFAULT_STYLE}）")
    args = ap.parse_args(argv[1:])
    deck_spec = deckio.read_json(args.spec)
    assets = load_assets(args.spec)      # assets/manifest.json（§12 管线入口）
    name = args.style or deck_spec["deck"].get("style", DEFAULT_STYLE)
    style = load_style(name)
    page = render(deck_spec, style, assets=assets)
    deckio.write_text(args.out, page)
    print(f"✓ 已写出 {args.out}（风格 {style['name']} / {len(page)} 字节 / "
          f"{len(deck_spec['deck']['slides'])} 页）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
