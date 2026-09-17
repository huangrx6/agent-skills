#!/usr/bin/env python3
"""deck-spec.json → HTML。

两条硬规矩（都是量出来、并被脚本守着的）：
1. **渲染层不写死任何颜色/字号/字体** —— 全部来自风格目录的 style.json
   （deck 项目的 styles/<name>/；--style 也接受路径）。
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
import re
import sys
import copy
import tempfile

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

# 风格解析根（顺序即优先级），**只有两根**：
#   1. <deck 项目>/styles/   —— 风格跟着 deck 项目走（随项目交付、可移植）；
#     工具链只写这里。
#   2. skill 的 styles/      —— 用户**显式托管**的全局风格；工具链永不写入。
#
# 没有第三根、也没有内置参考风格：夹具时代结束了。那份夹具被拷来拷去的结果是
# 每份 deck 长得一样（用户实测："无论换什么主题，产物永远一个样式"）——
# 一个可拷贝的模板必然会变成默认答案。风格按规则现写，形状见
# references/style-architecture.md。
def style_roots() -> tuple[str, ...]:
    """风格解析根（**每次调用时算**，不是 import 时冻结）。

    顺序即优先级：
      1. 环境变量 DECK_STYLES 指的根（`:` 分隔）—— 测试夹具、预览草稿、
         或风格放在 deck 项目之外时的显式入口；
      2. <当前目录>/styles —— 风格跟着 deck 项目走（工具链只写这里）；
      3. skill 的 styles/ —— 用户显式托管的全局风格（工具链永不写入）。

    为什么是函数而不是常量：常量会在 import 时把 cwd 冻住 —— 调用方（尤其测试）
    之后改 cwd 或设环境变量都无效，于是"为什么找不到风格"变成谜。
    """
    roots: list[str] = []
    extra = os.environ.get("DECK_STYLES")
    if extra:
        roots.extend(p for p in extra.split(os.pathsep) if p)
    roots.append(os.path.join(os.getcwd(), "styles"))
    roots.append(os.path.join(HERE, "..", "styles"))
    return tuple(roots)
# content-image 的**结构布局**（渲染器能力 —— 像图表的八类图形，不是审美枚举）：
#   visual-right = 文 7 栅 + 图 5 栅（缺省结构）
#   visual-left  = 图先文后（镜像）
#   even         = 6+6 均分
#   hero         = 图为主角：满幅 12 栅 + 底部实心标题条
# 另外两类自由，渲染**不拦**：
#   · two-column 的结构布局见 TWO_COL_LAYOUTS；
#   · 任何其它字符串 = 作者/风格自造的布局名 —— 渲染套缺省结构并加
#     `data-layout="<名>"`，怎么排由 skin.css 写（布局语言是作者的自由，
#     脚本只提供结构与验收）。
# 自动选择这条路不存在：
# 名字改为布局；spec 字段 `layout`，`variant` 不再接受。
IMAGE_LAYOUTS = ("visual-right", "visual-left", "even", "visual-wide", "hero")

# two-column 的结构布局（同上：渲染器能力，非审美枚举）：
#   even = 6+6 均分（缺省） / lean-left = 左 7 栅右 5 栅 / lean-right = 镜像
TWO_COL_LAYOUTS = ("even", "lean-left", "lean-right",
                   "lean-hard-left", "lean-hard-right")

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

# ── hero 的图高：**按这一页要装什么算**，不是一个固定值 ─────────────────
# 正文带 = CONTENT_BOTTOM − CONTENT_TOP（692px，页脚是 absolute，已在 824 之下
# 留好，不占这里）。图之后还要放条目与图注 —— 这两样都是普通流，所以图必须
# **先把它们的位置让出来**。旧写法按"有没有条目"在两个固定值（520/648）里挑：
# 条目多到 6 条时就溢出正文带、压到页脚上，而图还占着 520px 不让。
#
# 估算法与 `layout/contracts.py` 同一套（行高 1.55 / 条目间隙 28）——
# 同一个数字只该有一个出处。HERO_MIN_H 是"图还是主角"的下限：低于它就该
# 换版式/拆页，而不是把图压成一条（那种页由 check 的越界门接着报）。
HERO_BAND = CONTENT_BOTTOM - CONTENT_TOP    # 两个常量都是 int，不需要转
HERO_MAX_H = 648
HERO_MIN_H = 320
HERO_LINE = 1.55
HERO_ITEM_GAP = 28.0
HERO_ITEM_MARGIN = 24.0        # .hero-bullets 的 margin-top（= --sp-item）
HERO_CAPTION_MARGIN = 32.0     # = --sp-block：见下方 hero 流里的图注规则
# 页脚是 absolute（bottom:52），所以流内容的**净距**要自己留出来 ——
# 安全盒表：body 下 16 + foot 上 24 = 40（有图注时 caption 下 12 + foot 上 24 = 36，
# 40 更严，取它一个值就够，省掉"按情况分叉"）。
HERO_FOOT_CLEARANCE = 40.0


def hero_height(items_n: int, bsize: float, caption_px: float | None) -> int:
    """hero 这一页的图该多高：正文带减去条目/图注/页脚净距，夹在上下限之间。"""
    used = 0.0
    if items_n:
        used += HERO_ITEM_MARGIN + items_n * (bsize * HERO_LINE + HERO_ITEM_GAP)
    if caption_px:
        used += HERO_CAPTION_MARGIN + caption_px * HERO_LINE
    room = HERO_BAND - used - HERO_FOOT_CLEARANCE
    # round 而不是 int()：CSS 要的是整 px，而 round 对负数/边界也不会抛
    return round(max(HERO_MIN_H, min(HERO_MAX_H, room)))

# 版式 → 用字号级数里的哪一档（级数本身在 style.json 的 type 里，是唯一来源）
TITLE_TIER = {"title": "cover", "content-text": "compact", "end": "end"}
DEFAULT_TITLE_TIER = "small"

# `type` 级数里**渲染器与 skin 必读**的那些档位。
#
# 为什么要一个名单：新增风格时漏一档，渲染器不会报错 —— `tier["caption"]` 会
# KeyError（还算好），而 skin 里 `var(--t-something)` 拿不到值只会**静默地退回默认字号**，
# 那一页看着"就是有点怪"，查起来极贵。拿这份名单在 `style.py` 里当场报出来。
#
# 注意这是**下限**：skin 可以用 `--t-<任意键>` 再多拿几档（比如那张表里的 chartValue），
# 那些是自由的，不在名单里。
REQUIRED_TYPE_TIERS = frozenset({
    "cover", "compact", "small", "end",        # TITLE_TIER 的取值
    "subtitle", "caption", "foot",
    "bulletLarge", "bullet", "bulletSmall",    # 条目档（含风格 bulletDefault 的取值）
    "colTitle", "nodeLabel", "nodeNote",
    "chartValue", "chartLabel",
})

# 条目默认档：**作者/风格声明**，不按条数自动升降档。
# slide 可写 `bulletTier` 覆盖；风格可写 `bulletDefault`；都没有 → "bullet"。
# 内容多就拆页 / 收短 —— 不靠脚本把字悄悄缩小。
DEFAULT_BULLET_TIER = "bullet"
DEFAULT_BULLET_TIER = "bullet"

def _rng(seed, *parts) -> random.Random:
    return random.Random("|".join([str(seed)] + [str(p) for p in parts]))


def style_names() -> list[str]:
    """全部可用风格名（用户根在前，保持插入序去重）。

    只认**含 style.json 的目录**：styles/ 是用户目录，会攒实验草稿和无关
    文件夹（实测：一个手滑的 `__probe/t.txt` 就把整个工具链拖红）—— 没有
    清单的目录是"还没成风格的文件夹"，不是坏风格，不该出现在任何列表里。
    """
    names: list[str] = []
    for root in style_roots():
        for n in deckio.list_dirs(root):
            if n in names:
                continue
            if not os.path.isfile(os.path.join(root, n, "style.json")):
                continue
            names.append(n)
    return names


def style_folder(name: str) -> str | None:
    """风格目录路径（含 style.json 的第一个根）；找不到返回 None。

    `name` 也可以是**显式目录路径**（含 style.json）—— 三方向预览草稿在
    /tmp 里也能直接渲，全程不碰任何 styles 根。
    """
    if os.path.isdir(name) and os.path.isfile(os.path.join(name, "style.json")):
        return os.path.abspath(name)
    for root in style_roots():
        folder = os.path.join(root, name)
        if os.path.isfile(os.path.join(folder, "style.json")):
            return folder
    return None


def style_location_note(folder: str | None, spec_path: str) -> str | None:
    """风格目录 / spec 的位置有问题 → 说一声（不阻塞）。

    为什么必须开口：风格是 deck 的**表达层，随项目交付**。放在 /tmp 里，重启或被
    清理就没了 —— 实测发生过：一份 17 页 deck 的风格目录被清掉，spec 里的
    `deck.style` 成了死链，整套版式再也复现不出来。

    四情形分开说，因为**要挪的东西不同**（早期版本一律劝"把风格挪到 spec 旁边"，
    spec 自己就在 /tmp 时这句是反的）：
      · 两个都在临时目录 → 整个 deck 项目都要挪；
      · 只有风格在临时目录 → 挪风格；
      · 只有 spec 在临时目录 → 挪 spec（风格在项目里也一样交付不了）；
      · 风格在 deck 项目之外 → 挪风格进去。
    """
    if not folder or not os.path.isabs(folder):
        return None
    spec_dir = os.path.dirname(os.path.abspath(spec_path))
    temp_root = os.path.realpath(tempfile.gettempdir()).rstrip(os.sep) + os.sep

    def is_temp(path: str) -> bool:
        real = os.path.realpath(path).rstrip(os.sep) + os.sep
        return real.startswith(temp_root) or real.startswith("/private/tmp/")

    in_spec = os.path.realpath(folder).rstrip(os.sep).startswith(
        os.path.realpath(spec_dir).rstrip(os.sep) + os.sep)
    style_temp, spec_temp = is_temp(folder), is_temp(spec_dir)
    if style_temp and spec_temp:
        return (f"⚠️ **整个 deck 项目都在临时目录里**：spec={spec_dir} / 风格={folder}\n"
                f"   重启或被清理就全没了（实测发生过：风格被清掉，spec 的 deck.style "
                f"成了死链）—— 把 spec + styles/ + assets/ 一起挪进**项目目录**")
    if style_temp:
        return (f"⚠️ 风格在临时目录里：{folder}\n"
                f"   风格随 deck 项目交付 —— 挪进 {spec_dir}/styles/<名>/，"
                f"再把 spec 的 deck.style 改成那个名字；临时目录重启即失")
    if spec_temp:
        return (f"⚠️ **spec 在临时目录里**：{spec_dir}\n"
                f"   风格在项目里也没用 —— deck 项目（spec + styles/ + assets/）该建在"
                f"**项目目录**：交付 / 换台机器要能一起带走")
    if not in_spec:
        return (f"⚠️ 风格在 deck 项目之外：{folder}\n"
                f"   交付 / 换台机器就找不到它 —— 建议挪进 {spec_dir}/styles/<名>/")
    return None


def load_style(name: str | None = None) -> dict:
    """加载一个风格目录 → `{"name", "tokens", "skin"}`。

    `name` 既可以是**风格名**（在两根里找），也可以是**显式目录路径** ——
    预览草稿放 /tmp 里也能直接渲。两个文件都必须有：只有 token 没 skin 会渲出
    「有颜色没版式」的东西，只有 skin 没 token 连色都没得填；缺一个就明确报出来。
    """
    if not name:
        raise SystemExit(
            "✗ 这份 deck 没写 deck.style —— 风格必须由 deck 自己带"
            "（工具链不内置任何风格，也没有可拷的参考实现）。\n"
            "  做法：在 deck 项目的 styles/<名>/ 里放 style.json + skin.css，"
            "spec 里写 \"style\": \"<名>\"；\n"
            "  style.json 的契约（顶层键 / 字号档 / 色板 / motion / 可选 effect）"
            "见 references/style-architecture.md。")
    folder = style_folder(name)
    if folder is None:
        raise SystemExit(
            f"✗ 没有风格 {name!r}（现有：{style_names()}）\n"
            f"  风格按规则现写：deck 项目的 styles/<名>/ 里放 style.json + skin.css"
            f"（形状见 references/style-architecture.md）。")
    tokens_path = os.path.join(folder, "style.json")
    skin_path = os.path.join(folder, "skin.css")
    has_tokens = os.path.isfile(tokens_path)
    has_skin = os.path.isfile(skin_path)
    if not (has_tokens and has_skin):
        raise SystemExit(
            f"✗ 风格 {name!r} 缺文件：{'skin.css' if has_tokens else 'style.json'}\n"
            f"  一个风格目录必须同时有 style.json + skin.css。")
    return {"name": os.path.basename(folder),
            "tokens": deckio.read_json(tokens_path),
            "skin": deckio.read_text(skin_path)}


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
  overflow:hidden;margin:0 auto 36px;
  /* 页盒必须**永远**是 1600×900：border-box 下皮肤加边框/内边距都往内吃，
     不会把盒子掉大。没有这句的后果实测过：皮肤给 .slide 加了 1px 上边框
     （一个极其自然的设计动作）→ 页盒 901px → 导 PDF 每页多溢出一张，
     17 页的 deck 变 34 页；HTML 屏上一点看不出来（overflow 剪掉）。 */
  box-sizing:border-box;
  /* 基准字体族：skin 没写到的选择器就从这里继承 —— 否则会静默掉到浏览器
     UA 默认族（CJK 在 macOS 上是 PingFang SC）：同一页里一半宋体一半系统 UI 族，
     而且换台机器字形全变。皮肤的显式规则照旧覆盖它。 */
  font-family:var(--body)}
.pad{padding:132px 84px}
/* 标题块：高度是版面几何（每种版式不同），字号由 --s-title 给（来自 type 级数） */
.titleblock{position:relative;display:block}
.tb-cover{min-height:158px}
.tb-compact{min-height:104px}
.tb-small{min-height:88px}
.sub{margin:0}
/* 间距治理：块与块的间距全部由 .pad（父容器）的邻接规则给；组件自身零外距。 */
.pad > .titleblock.tb-compact,
.pad > .titleblock.tb-small{margin-bottom:var(--sp-section)}
.two{display:flex;gap:var(--sp-item);align-items:flex-start}
.two .main{width:825.33px}
.imgwrap{margin:0;width:582.67px}
/* content-image 变体：v-even 6+6 均分（704px=span(6)，825.33+582.67+24=1432 不变）；
   v-left 只换 DOM 顺序（宽度不动），类名留给 skin 做侧别微调的钩子。 */
.two.v-even .main{width:704px}
.two.v-even .imgwrap{width:704px}
/* 4+8：图拉到 8 栅（946.67px=span(8)）、正文压到 4 栅（461.33px=span(4)）。
   为什么要它：6+6 / 7+5 / 满幅只给得出三个**真构图**，给了三个候选也只有一个组合。
   版式候选要有得挑，结构词表先得够大（461.33+946.67+24=1432 不变）。
   max-height 必须有：槽宽 946 时 3:2 的图高 631px，正文带只剩 524 —— 会直接
   竖向溢出（实测：这个候选一开始全页作废）。aspect-ratio 遇 max-height 会
   等比缩（不裁不变形），图比槽窄一截，但构图仍然真的不同。 */
.two.v-visual-wide .main{width:461.33px}
.two.v-visual-wide .imgwrap{width:946.67px}
.two.v-visual-wide .imgwrap img{max-height:470px}
/* hero：图是这一页的主角 —— 满幅 12 栅 + 底部**实心**标题条。
   条用 --text 底 / --paper 字的反转色对：对比度与正文是同一个 token 保证
   （≥4.5 自动成立）。刻意不做半透明渐变 scrim —— 渐变透明端的文字对比度
   估不出来，实心条才可被门禁证明。 */
.herofig{position:relative;width:1432px;margin:0;overflow:hidden}
.herofig img{display:block;width:100%;height:100%;object-fit:cover}
.herofig .herobar{position:absolute;left:0;right:0;bottom:0;
  padding:18px 30px 18px 0;background:var(--text);color:var(--paper)}
.herofig .herobar .title{color:var(--paper);
  font-size:var(--s-colTitle,26px);line-height:1.3;white-space:normal}
.hero-bullets{margin-top:var(--sp-item)}
/* hero 流里的图注是**顶层元素**（不在 figure 里，所以拿不到"figure 成员"那条豁免），
   它必须自己满足安全盒：body 下 16 + caption 上 12 = 28 —— --sp-inner(16) 不达标，
   用 --sp-block(32)。普通图文页的图注在 <figure> 里，不受这条影响。 */
.herofig + .chartcap, .hero-bullets + .chartcap{margin-top:var(--sp-block)}
/* 内容图：**展示比例由槽位定，不由图片自身比例定**。
   生图工具出成 1:1 / 4:3 / 2:1 是常态（提示词按不住比例，各家默认都不同）——
   只写 width 的话高度会跟着图片比例走：1:1 撑出页底（实测溢出 109px）、
   2:1 留出一个空洞。现在高度由槽位比例定，多出来的部分按内容类型处理：
     · 照片 / 插画 / 截图 → 一律 cover（按中心裁切）
     · 提示词里因此写死两件事：主体收在中间、画面里不要有文字
   皮肤想让图留边不裁（"每一笔都是信息"那种结构图）就覆盖
   `.imgwrap img{object-fit:contain}`；想改槽位比例就覆盖 aspect-ratio。 */
.imgwrap img{width:100%;display:block;aspect-ratio:var(--img-ratio,3/2);
  object-fit:cover}
.cols{display:flex;gap:var(--sp-item)}
.col{flex:1;min-width:0}
/* two-column 变体：lean-left 左栏 7 栅（825.33px=span(7)），右栏由 flex:1 补齐
   （582.67px=span(5)，825.33+582.67+24=1432 不变）；lean-right 镜像。
   默认 even 不加类 —— 上面的 flex:1 等分就是 (1432−24)/2=704px=span(6)，
   默认路径逐字节不变（test_compile 的黄金对照钉着）。 */
.cols.v-lean-left .col:first-child{flex:none;width:825.33px}
.cols.v-lean-right .col:last-child{flex:none;width:825.33px}
/* 4+8 / 8+4：强弱更分明的一对栏（461.33px=span(4) / 946.67px=span(8)）。
   侧别靠 :first-child / :last-child —— flex 会自己分配剩下的宽度，
   所以与 7+5 同属于一个度量集（跨度集合），不是新的家族。 */
.cols.v-lean-hard-left .col:first-child{flex:none;width:461.33px}
.cols.v-lean-hard-right .col:last-child{flex:none;width:461.33px}
.tl{display:flex;gap:var(--sp-item);list-style:none;padding:0;margin:0}
/* 条目列表：壳只管**结构**（无默认圆点、无浏览器缩进）——标记是装饰，归皮肤
   （`.bullets li::before`）。壳**不发**条目标记：
   自己的短横时就成了两个标记，而那个方块没有间距、直接贴住正文（实测截图）。 */
.bullets{list-style:none;padding:0;margin:0}
.tl li{flex:1;min-width:0;width:var(--tl-node,300px)}
/* 图注 / 图表注：壳给一个站得住的缺省 —— 与图之间留一个间距 token，颜色压到
   muted（注解不是正文）。皮肤要另说就覆盖这两条（皮肤 CSS 在壳之后，同级即胜）。 */
.chartcap{margin-top:var(--sp-inner);color:var(--text);opacity:.62;
  font:400 var(--s-caption,16px)/1.5 var(--body)}
/* 行内强调（模型写的 `**x**`）：用 span 而不是 b —— 皮肤的 .tl b 会命中裸 b */
.em{font-weight:700}
.chartsrc{margin:calc(var(--sp-inner) * -0.5) 0 0;color:var(--text);opacity:.55;
  font:400 var(--s-caption,16px)/1.4 var(--body)}
.chartwrap{margin-top:var(--sp-item);width:1432px;padding:var(--sp-item);
  position:relative;box-sizing:border-box}
/* box-sizing:border-box 必须有：1432 是**含内边距**的栅格宽。content-box 下
   总宽 = 1432+48 = 1480，右缘冲出内容界 48px —— 皮肤一留横向 padding 就现形
   （不留的皮肤恰好把它掩盖了）。 */
/* 图表容器高度**由壳给死**（330px）—— 图表是 G2（默认 canvas 渲染器），
   而 G2 的 autoFit 从容器取尺寸：容器没有高度就会在渲染时抛错（实测）。
   高度钉在 .g2 上而不是 .chartwrap svg 上：canvas/svg 都由 G2 自己塞进去。
   为什么不让它 width:100% 自己撑：那样高度会跟着容器宽度变 —— 而各风格的
   .chartwrap 内边距不同，同一张图表在不同风格里会差 40~50px。 */
.chartwrap .g2{position:relative;display:block;height:330px;width:100%}
.chartwrap .g2 canvas,.chartwrap .g2 svg{display:block;max-width:100%}
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
.brandfoot{font:400 var(--s-foot, 14px)/1 var(--body);color:var(--text);opacity:0.42;
  letter-spacing:0.04em}
"""


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
/* ── 演示台（讲稿层）──────────────────────────────────
   台上的人要看的是：现在第几页 / 下一页是什么 / 这页要说什么 / 讲了多久。
   它盖在幻灯片上，但**不进清单、不进测量、不进导出**（没有 data-m；打印与
   取帧态一律隐藏）—— 演示台是工具，不是内容。 */
#__deck_console{position:fixed;left:0;right:0;bottom:0;z-index:20;
  background:#0C0E10;color:#F2F4F6;font:400 19px/1.5 var(--body);
  padding:18px 24px 14px;display:none;gap:10px;flex-direction:column;max-height:56vh}
#__deck_console[data-open]{display:flex}
/* 讲稿层打开时，壳自己的页码条与快捷键条退场：一份屏上两个计数器是噪音，
   而讲稿层已经有更准的那个（它还知道"下一页是什么"）。 */
html[data-console] .hud,html[data-console] .hint{opacity:0}
.pc-head{display:flex;gap:22px;align-items:baseline;font-variant-numeric:tabular-nums;
  font-size:17px;opacity:.85}
#__deck_console_clock{font-weight:600;font-size:20px;opacity:1}
#__deck_console_timer{color:#8FD3A7}
#__deck_console_step{margin-left:auto}
#__deck_console_notes{white-space:pre-wrap;font-size:21px;line-height:1.62;
  max-height:34vh;overflow:auto}
.pc-next{opacity:.7;font-size:17px;border-top:1px solid rgba(255,255,255,.14);
  padding-top:8px}
.pc-btns{display:flex;gap:10px;flex-wrap:wrap}
.pc-btns button{font:inherit;font-size:16px;padding:6px 14px;border-radius:2px;
  border:1px solid rgba(255,255,255,.28);background:transparent;color:inherit;
  cursor:pointer}
.pc-btns button:hover{background:rgba(255,255,255,.12)}
/* 黑屏：只盖页面，不盖讲稿层 —— 对着观众黑，对着自己还能看讲稿 */
#__deck_blackout{position:fixed;inset:0;z-index:15;background:#000}
#__deck_blackout[hidden],#__deck_console[hidden]{display:none}
@media print{#__deck_console,#__deck_blackout{display:none !important}}
html[data-view="frame"] #__deck_console,html[data-view="frame"] #__deck_blackout{
  display:none !important}
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
    notify(n);
    try{ history.replaceState(null,'','#'+(n+1)); }catch(e){}
  }
  // ── 演示台接口（窄：三个动作 + 一个订阅）──────────────────────
  // 讲稿层是**另一个脚本**，它不能摸这里的内部变量（cur/slides/show 都是闭包私有）。
  // 所以只开一个门：谁知道“现在第几页”，谁能翻页，谁就能做演示台 ——
  // 而且这个门是可校验的（check 的演示台合同门钉这几个名字）。
  var subs=[];
  function notify(n){ for(var i=0;i<subs.length;i++){ try{ subs[i](n); }catch(e){} } }
  window.__deck_ui={cur:function(){return cur;}, total:slides.length,
    next:function(){show(cur+1,true);}, prev:function(){show(cur-1,true);},
    onShow:function(cb){ subs.push(cb); cb(cur); }};
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
    else if(k==='s'||k==='S'){ if(typeof presenterToggle==='function') presenterToggle(); }
    else if(k==='b'||k==='B'){ if(typeof blackoutToggle==='function') blackoutToggle(); }
    else if(k==='r'||k==='R'){ if(typeof presenterReset==='function') presenterReset(); }
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

# ── 演示台（讲稿层）─────────────────────────────────────────────
# 台上的人需要四样东西：现在第几页 / 下一页是什么 / 这一页要说什么 / 讲了多久。
# 四样都在同一屏内，**不切窗口** —— 现场演出时“切窗口”就是出错的那一步。
#
# 它与翻页壳的接口只有 `window.__deck_ui`（四个名字）：壳不知道讲稿层存在，
# 讲稿层也不摸壳的内部变量。这条窄接口 + 下面这串 id 就是合同，check 钉的就是它。
#
# 为什么不做“观众屏 / 第二窗口”：那需要两个窗口、一套跨窗口同步、一套断开恢复
# 状态机（实测最容易在现场出问题的正是它）。一个 HTML、一个窗口、讲稿盖在上面
# —— 少一层同步就少一处现场事故。
CONSOLE_HTML = """
<div id="__deck_blackout" hidden></div>
<aside id="__deck_console" hidden>
  <div class="pc-head">
    <span id="__deck_console_clock">--:--</span>
    <span id="__deck_console_timer">00:00</span>
    <span id="__deck_console_step">1 / 1</span>
  </div>
  <div id="__deck_console_notes"></div>
  <div class="pc-next">下一页 · <span id="__deck_console_next">—</span></div>
  <div class="pc-btns">
    <button type="button" data-pc="prev">上一页 ←</button>
    <button type="button" data-pc="next">下一页 →</button>
    <button type="button" data-pc="reset">计时归零 (R)</button>
    <button type="button" data-pc="black">黑屏 (B)</button>
    <button type="button" data-pc="close">收起 (S)</button>
  </div>
</aside>
"""

CONSOLE_JS = """
(function(){
  var box=document.getElementById('__deck_console');
  var ui=window.__deck_ui;
  if(!box||!ui) return;
  var blackout=document.getElementById('__deck_blackout');
  var elClock=document.getElementById('__deck_console_clock');
  var elTimer=document.getElementById('__deck_console_timer');
  var elStep=document.getElementById('__deck_console_step');
  var elNotes=document.getElementById('__deck_console_notes');
  var elNext=document.getElementById('__deck_console_next');
  function read(id,fallback){
    var el=document.getElementById(id); if(!el) return fallback;
    try{ return JSON.parse(el.textContent)||fallback; }catch(e){ return fallback; }
  }
  var NOTES=read('__deck_notes',{}), OUTLINE=read('__deck_outline',[]);
  var t0=null;
  function pad(n){ return (n<10?'0':'')+n; }
  function fmt(ms){
    var s=Math.floor(ms/1000);
    if(s<3600) return pad(Math.floor(s/60))+':'+pad(s%60);
    return Math.floor(s/3600)+':'+pad(Math.floor(s/60)%60)+':'+pad(s%60);
  }
  function tick(){
    var now=new Date();
    elClock.textContent=pad(now.getHours())+':'+pad(now.getMinutes());
    if(t0!==null) elTimer.textContent=fmt(now.getTime()-t0);
  }
  // 没写讲稿的页也显示一行字（不是空白）—— 空白看不出“是没写还是没加载”
  function paint(i){
    elStep.textContent=(i+1)+' / '+ui.total;
    var text=NOTES[String(i+1)];
    elNotes.textContent=(typeof text==='string'&&text)?text:'（这一页没写讲稿）';
    var nx=OUTLINE[i+1];
    elNext.textContent=nx?((nx.t||'（无标题）')+(nx.k?' · '+nx.k:'')):'— 最后一页';
  }
  function startTimer(){ if(t0===null){ t0=Date.now(); tick(); } }
  function mark(on){
    var root=document.documentElement;
    if(on) root.setAttribute('data-console',''); else root.removeAttribute('data-console');
  }
  window.presenterToggle=function(){
    if(box.hasAttribute('data-open')){ box.removeAttribute('data-open'); box.hidden=true; mark(0); }
    else { box.hidden=false; box.setAttribute('data-open',''); mark(1); startTimer(); paint(ui.cur()); }
  };
  window.presenterReset=function(){ t0=Date.now(); elTimer.textContent='00:00'; };
  window.blackoutToggle=function(){ if(blackout) blackout.hidden=!blackout.hidden; };
  box.addEventListener('click',function(e){
    var b=e.target.closest?e.target.closest('button[data-pc]'):null; if(!b) return;
    var act=b.getAttribute('data-pc');
    if(act==='prev') ui.prev();
    else if(act==='next') ui.next();
    else if(act==='reset') window.presenterReset();
    else if(act==='black') window.blackoutToggle();
    else if(act==='close') window.presenterToggle();
  });
  ui.onShow(paint);
  tick(); setInterval(tick,1000);
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
deck_mod = _load_sibling("deck")    # 品牌并入 + spec→resolved 编译（原 brand/compile）
fonts_module = _load_sibling("fonts")  # 字体清单与 @font-face（清单是数据，不是硬编码）


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
    tokens["fonts"] = deck_mod.merge_fonts(tokens["fonts"], brand)
    tokens["colorSets"] = deck_mod.merge_color_sets(tokens["colorSets"], brand)
    merged = dict(style)
    merged["tokens"] = tokens
    return merged


# ═══════════════════════════════════════════════════════════════════════════
# 图表：**AntV G2**（v4 —— 手写 SVG 渲染器已整体删除）
#
# 为什么换掉手写 SVG：那一版只有圆角/网格线/单字重的极简骨架，用户实测的评语是
# "可丑的原生感"。G2 是成熟的声明式图形语法：编码、坐标轴、标注、堆叠都由它做，
# 我们只出 spec（数据 → 编码），不手绘几何。
#
# 确定性（§41/42）：`animation: false` 关死；G2 的 SVG 输出是同步的纯函数，
# 同 spec 同输出 —— measure/check 才有稳定 DOM 可量。
# ═══════════════════════════════════════════════════════════════════════════
CHART_TYPES = ("bar", "bar-horizontal", "line", "area", "bar-stacked",
               "donut", "scatter", "combo")


def chart_declared_type(slide: dict) -> str:
    """图形类型 —— **spec 显式声明**，没有推断。"""
    declared = slide.get("chart")
    if not declared:
        raise SystemExit(
            "✗ 图表页缺 `chart` —— 图形类型由作者显式声明（八类："
            f"{list(CHART_TYPES)}）。validate_spec.py 会先拦住这种 spec。")
    if declared not in CHART_TYPES:
        raise SystemExit(f"✗ chart={declared!r} 不在八类里（{list(CHART_TYPES)}）")
    return declared


def chart_data(slide: dict) -> list[dict]:
    """单系列数据（[{label, value}]）；多系列见 series。"""
    return list(slide.get("data", []))


def _hex_mix(a: str, b: str, t: float) -> str:
    """线性混两个 HEX（t=0 是 a，t=1 是 b）。"""
    pa, pb = a.lstrip("#"), b.lstrip("#")
    ea = [int(pa[i:i + 2], 16) for i in (0, 2, 4)]
    eb = [int(pb[i:i + 2], 16) for i in (0, 2, 4)]
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(ea, eb))


def chart_muted(primary: str, background: str) -> str:
    """muted = 主色向纸色褪 55% —— 有色相但退到背景里，让 accent 独占注意力。"""
    return _hex_mix(primary, background, 0.55)


def chart_series_colors(primary: str, background: str, n: int) -> list[str]:
    """多系列用主色的深浅阶（不是彩虹）：向纸色分档褪色。"""
    if n <= 1:
        return [primary]
    return [_hex_mix(primary, background, 0.62 * i / max(1, n - 1)) for i in range(n)]


def chart_emphasis_set(slide: dict) -> set:
    """被强调的标签集合（`emphasis.values`）。"""
    em = slide.get("emphasis") or {}
    return {str(v) for v in em.get("values", [])}


# 柱宽：G2 的 band 默认把柱子撑到几乎相接。实测（PNG 量柱宽）：4 类目下柱子
# 187px、横向覆盖 82.9% —— 四根几乎连成一片。`scale.x.padding` 是**相对 band** 的
# 留白（实测 0.4 → 柱宽 116px / 覆盖 51.6%；`insetLeft/Right` 也能收窄，但它是绝对
# 像素：类目一多（8 类）会把柱子挤成细线）。取 0.45 落在 45~52% 区间。
_BAND_PAD = {"x": {"padding": 0.45}}


# 行内强调：模型常把 Markdown 的 `**x**` 写进条目/标题（实测第 3 页条目原样显示了
# `**6 因素** 硬尺标统一口径`）。解释成**加粗**（本意就是强调），用 `span.em`
# 而不是 `<b>` —— 皮肤的 `.tl b`（时间线节点标签）会命中裸 `<b>`，把行内强调
# 变成块级大字号。所有**可见文本**都走 rich()，不要再直接 html.escape。
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")


def rich(text) -> str:
    return _MD_BOLD.sub(r'<span class="em">\1</span>', html.escape(str(text)))


def _chart_norm_series(slide: dict) -> list[dict]:
    """统一成 [{name, data:[{label,value}]}]（单系列 data 与多系列 series 都收）。"""
    series = slide.get("series")
    if series:
        return [{"name": str(s.get("name", "")), "data": list(s.get("data", []))}
                for s in series]
    return [{"name": "", "data": list(slide.get("data", []))}]


def chart_g2_spec(slide: dict, colors: dict, emphasis: set | None = None,
                  tier: dict | None = None, fonts_body: str = "") -> dict:
    """Chart Resolver 的 G2 产物（§19：链路不绑技术——HTML 路径用 AntV G2）。

    输出 G2 5 的 chart spec（renderer 由壳层指定 svg + animation off——
    确定性 §41：同输入同输出，measure/check 才有稳定的 DOM 可量）。
    配色守规矩：muted + 1 accent（emphasis 命中的数据用主色，其余灰化）。
    """
    data = _chart_norm_series(slide)[0]["data"]
    emphasis = emphasis or set()
    primary = colors.get("primary", "#0033CC")
    muted_c = chart_muted(primary, colors.get("background", "#FFFFFF"))
    text = colors.get("text", "#0A0A0A")
    # 坐标轴配色：G2 主题的轴标签/轴名是**theme 自带的深色**，不跟 paper 走。
    # 实测后果：深底反白风格里轴标签与轴名直接看不见（柱在、刻度没了）。
    # 轴是图的一部分，颜色同样从 token 取 —— 这里只覆盖已实测生效的两项。
    # 排印注入：G2 默认主题的字体/字号/轴样式**不跟 deck 走**（默认轴字一族、
    # 默认尺寸，深底风格里轴名直接看不见）。字体栈与字号全部从风格 token 来：
    # 图表是版面的一部分，不是一块飞地。
    label_px = (tier or {}).get("chartLabel", 14)
    value_px = (tier or {}).get("chartValue", 16)
    typo_axis = {
        "labelFill": text, "labelFontFamily": fonts_body,
        "labelFontSize": label_px,
        "titleFill": text, "titleFontFamily": fonts_body,
        "titleFontSize": label_px,
        "tickStroke": muted_c, "lineStroke": muted_c,
        "gridStroke": muted_c, "gridLineWidth": 1, "gridLineDash": [3, 3],
    }
    typo_label = {"fill": text, "fontSize": value_px, "fontFamily": fonts_body}

    def enc_color(d):
        return primary if (not emphasis or str(d.get("label")) in emphasis) else muted_c

    kind = chart_declared_type(slide)
    spec: dict = {
        "animation": False,                      # 确定性：动画关死（§41/42）
        # autoFit **不写在这里**：它是 chart 实例选项，写在 spec 里会覆盖构造函数的
        # autoFit:true（见文末实例化代码与 :952 的注释「autoFit 跟容器走」）——
        # 实测后果：canvas 退到 G2 默认 640×480，撑出 .g2 的 330px 容器、
        # 压住图注，而且只占满左侧不到一半宽度。
        "padding": "auto",
        # 轴**标题**一律关掉：不关就是数据集名（"label" / "value"）印在轴上 ——
        # 最典型的图表 slop，人话标题由页面 message / 图注承担。
        "axis": {"x": {**typo_axis, "grid": False, "title": False},
                 "y": {**typo_axis, "title": False}},
        # tooltip 关掉：交互产物会落进截图/录屏/PDF（实测截图里就飘着一个
        # "重大 / value / 3" 浮层），也让同一份产物两次截图不一致。
        "interaction": {"tooltip": False},
    }
    if kind in ("bar", "bar-horizontal"):
        rows = sorted(data, key=lambda d: -d.get("value", 0)) \
            if kind == "bar-horizontal" else data
        rows = [{**d, "c": enc_color(d)} for d in rows]
        spec.update({
            "type": "interval",
            "data": rows,
            "encode": {"x": "label", "y": "value", "color": "c"},
            "scale": {"color": {"type": "identity"}, **_BAND_PAD},
            "style": {"lineWidth": 0},
            "labels": [{"text": "value", "style": {**typo_label,
                                                   "fontWeight": 600,
                                                   "position": "outside"}}],
        })
        if kind == "bar-horizontal":
            spec["coordinate"] = {"transform": [{"type": "transpose"}]}
    elif kind == "donut":
        rows = [{**d, "c": enc_color(d)} for d in data]
        spec.update({
            "type": "interval",
            "data": rows,
            "coordinate": {"transform": [{"type": "transpose"},
                                         {"type": "theta", "innerRadius": 0.62}]},
            "encode": {"y": "value", "color": "label"},
            "scale": {"color": {"range": [d["c"] for d in rows]}},
            "axis": False,
            "legend": {"color": {"position": "right",
                                 "itemLabelFill": text,
                                 "itemLabelFontFamily": fonts_body,
                                 "itemLabelFontSize": label_px}},
        })
    elif kind in ("line", "area"):
        spec.update({
            "type": "area" if kind == "area" else "line",
            "data": data,
            "encode": {"x": "label", "y": "value"},
            "style": {"stroke": primary, "lineWidth": 2.5},
            "labels": [{"text": "value", "style": {**typo_label,
                                                   "selector": "last"}}],
            "axis": {"x": {**typo_axis, "title": False, "grid": False},
                     "y": {**typo_axis, "title": False}},
        })
    elif kind == "scatter":
        spec.update({
            "type": "point",
            "data": data,
            "encode": {"x": "label", "y": "value", "size": 4},
            "style": {"fill": primary, "stroke": muted_c},
            "axis": {"x": {**typo_axis, "title": False, "grid": False},
                     "y": {**typo_axis, "title": False}},
        })
    elif kind in ("bar-stacked", "combo"):
        series = slide.get("series") or []
        rows = []
        for si, srow in enumerate(series):
            for d in srow.get("data", []):
                rows.append({"label": d.get("label"), "value": d.get("value", 0),
                             "series": srow.get("name", f"系列{si+1}")})
        spec.update({
            "type": "interval" if kind == "bar-stacked" else "line",
            "data": rows,
            "encode": {"x": "label", "y": "value", "color": "series"},
            "transform": [{"type": "stackY"}] if kind == "bar-stacked" else [],
            "scale": {"color": {"range": chart_series_colors(primary, colors.get(
                "background", "#FFFFFF"), max(1, len(series)))}, **_BAND_PAD},
            "axis": {"x": {**typo_axis, "title": False, "grid": False},
                     "y": {**typo_axis, "title": False}},
        })
    return spec




# G2 vendor（版本锁死，保确定性）：内联进产物，离线可用、无 CDN 依赖。
G2_VENDOR = os.path.join(HERE, "vendor", "g2-5.2.10.min.js")

# 实例化：把每页的 data-g2 spec 交给 G2（animation 关死，确定性）。
# G2 5 的 API 是 chart.options(spec) + chart.render()；不写 width/height ——
# autoFit 跟容器走，容器尺寸由壳的 CSS 定（几何 SSOT 在 grid.py）。
# ⚠️ 不要传 `renderer:` 字符串：这份 UMD bundle 只带默认 canvas 渲染器，
# 字符串会在运行时抛 `registerPlugin is not a function`（实测）。
G2_INIT_JS = """
(function(){
  var nodes=[].slice.call(document.querySelectorAll('.g2[data-g2]'));
  if(!nodes.length) return;
  if(!window.G2){ nodes.forEach(function(n){ n.setAttribute('data-chart-error','no-g2'); }); return; }
  nodes.forEach(function(n){
    var spec; try{ spec=JSON.parse(n.getAttribute('data-g2')); }catch(e){
      n.setAttribute('data-chart-error','bad-spec'); return; }
    try{
      // 不要传 renderer: 这份 UMD bundle 只带默认（canvas）渲染器 —— 传字符串
      // 会在运行时抛 registerPlugin is not a function（实测踩过）。
      // devicePixelRatio 2：位图在两倍像素下渲染，进 PDF 时够锐。
      var chart=new G2.Chart({container:n, autoFit:true, devicePixelRatio:2,
                              animation:false, padding:'auto'});
      chart.options(spec);
      chart.render();
      n.setAttribute('data-chart-ready','1');
    }catch(e){ n.setAttribute('data-chart-error','render'); }
  });
})();
"""

def resolve_color_set(tokens: dict, deck: dict) -> str:
    """colorSet 名 —— **spec 显式声明**（配色由作者定，脚本只验收）。

    这里没有 auto 路径：选色是审美
    决策（门 ③ 给候选，作者定）。validate_spec 会先拦住缺失；这里也拦一道，
    给直调入口干净报错。check.py 也用它 —— 两边看到同一套色。
    """
    name = deck.get("colorSet")
    if not name or name == "auto":
        raise SystemExit(
            "✗ 这份 deck 没写 colorSet —— 配色由作者显式声明，没有自动配色；"
            "对比度由 ink.py/check.py 验收，选哪套是你的决定。")
    if name not in tokens.get("colorSets", {}):
        raise SystemExit(
            f"✗ colorSet={name!r} 不在风格的 colorSets 里"
            f"（{sorted(tokens.get('colorSets', {}))}）")
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

    §14 优先级链：manifest 即选择（selected 的落点）；generated/provided
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
    if deck_mod.is_resolved(deck_spec):
        return render_resolved(deck_spec)
    return render_resolved(deck_mod.compile_spec(deck_spec, style,
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
    g2_specs: list[str] = []      # 图表页的 G2 spec（文档末尾统一实例化）

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
    logo_uri = deck_mod.logo_data_uri(brand, logo_file)
    logo_ref = deck_mod.logo_ref(brand, logo_file)

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
                f'{rich(b)}</li>'
                for bi, b in enumerate(slide.get("bullets", [])))
            out.append(f'<ul class="bullets" style="--s-bullet:{bsize}px">{items}</ul>')
        elif kind == "content-image":
            # 布局判定要在 titleblock 之前：hero 的标题只住 herobar，
            # 顶部再立一个 titleblock 就是双标题（而且把 648px 的图顶出正文带）。
            # IMAGE_LAYOUTS 是渲染器**结构能力**（像图表的八类图形）；
            # 其它字符串 = 作者自造的布局名 —— 套缺省结构 + `data-layout` 钩子，
            # 具体怎么排由 skin.css 写（脚本不枚举审美）。
            layout = slide.get("layout")
            if layout is not None and not isinstance(layout, str):
                raise SystemExit(
                    f"✗ 第 {i} 页 layout 要是字符串，得到 {type(layout).__name__}")
            custom_layout = layout is not None and layout not in IMAGE_LAYOUTS
            layout = layout or "visual-right"
            if layout != "hero":
                out.append(f'<div class="titleblock tb-{t_tier}" '
                           f'style="--s-title:{tsize}px">{th}</div>')
            items = "".join(
                f'<li {tag(f"s{i}.bullet.{bi}", i, "bullet", b, bsize)}>'
                f'{rich(b)}</li>'
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
                       f'{rich(slide["caption"])}</figcaption>')
            # Family(content-image) × Variant：spec/compile 决定文图栅格分配，
            # 渲染只执行。默认 visual-right 必须**逐字节**等于旧输出（重构不改像素）。
            # （variant 已在 titleblock 之前判定 —— hero 不立独立标题块。）
            main_html = (f'<div class="main"><ul class="bullets" '
                         f'style="--s-bullet:{bsize}px">{items}</ul></div>')
            # 比例由 spec 的 visual.ratio 给（未声明则壳缺省 3:2）—— 出图提示词里写的就是
            # 这个比例，所以图按槽位铺满即可（裁切看不出来）。
            visual = slide.get("visual") if isinstance(slide.get("visual"), dict) else {}
            ratio = visual.get("ratio")
            style_attr = ""
            if isinstance(ratio, str) and ratio.count(":") == 1:
                style_attr = f' style="--img-ratio:{ratio.replace(":", "/")}"'
            img_html = (f'<figure class="imgwrap" {img_attrs}{style_attr}>'
                        f'<img src="{html.escape(src)}" alt="">{cap}</figure>')
            if layout == "visual-left":       # 图先文后
                # 类名 = layout 名（皮肤按名字就能选到，不用猜）；`v-left` 是历史短名，
                # 保留不撤 —— 已经写在皮肤里的选择器不能因为改名默默失效。
                out.append(f'<div class="two v-visual-left v-left">{img_html}{main_html}</div>')
            elif layout == "even":            # 6+6 均分
                out.append(f'<div class="two v-even">{main_html}{img_html}</div>')
            elif layout == "visual-wide":     # 4+8：图当主角、正文收窄
                out.append(f'<div class="two v-visual-wide">{main_html}{img_html}</div>')
            elif layout == "hero":            # 图为主角：满幅 + 实心标题条
                # 图高按这一页实际要装的条目/图注算（hero_height）——
                # 固定值会在"条目多"时把后面的字顶到页脚上（实测 6 条溢出 113px）。
                # 下限 HERO_MIN_H：真装不下时就该换版式/拆页，不是把图压成一条。
                hero_h = hero_height(
                    len(slide.get("bullets") or []), bsize,
                    tier.get("caption") if slide.get("caption") else None)
                bullets_html = (f'<ul class="bullets small hero-bullets" '
                                f'style="--s-bullet:{bsize}px">{items}</ul>'
                                ) if items else ""
                out.append(f'<figure class="herofig" {img_attrs} '
                           f'style="height:{hero_h}px">'
                           f'<img src="{html.escape(src)}" alt="">'
                           f'<div class="herobar">{th}</div></figure>'
                           f'{bullets_html}{cap}')
            else:                              # 缺省：文 7 + 图 5，图在右
                hook = f' data-layout="{html.escape(layout)}"' if custom_layout else ""
                out.append(f'<div class="two"{hook}>{main_html}{img_html}</div>')
        elif kind == "two-column":
            # 与 content-image 同一模式：TWO_COL_LAYOUTS 是渲染器结构能力；
            # 其它字符串 = 作者自造布局名（缺省结构 + data-layout 钩子）。
            layout = slide.get("layout")
            if layout is not None and not isinstance(layout, str):
                raise SystemExit(
                    f"✗ 第 {i} 页 layout 要是字符串，得到 {type(layout).__name__}")
            custom_layout = layout is not None and layout not in TWO_COL_LAYOUTS
            layout = layout or "even"
            out.append(f'<div class="titleblock tb-{t_tier}" '
                       f'style="--s-title:{tsize}px">{th}</div>')
            cols = []
            for ci, col in enumerate(slide.get("columns", [])[:2]):
                li = "".join(
                    f'<li {tag(f"s{i}.col{ci}.bullet.{bi}", i, "bullet", b, bsize)}>'
                    f'{rich(b)}</li>'
                    for bi, b in enumerate(col.get("bullets", [])))
                band = "a" if ci == 0 else "b"
                coltitle = col.get("title", "")
                h3_attrs = tag(f"s{i}.col{ci}.title", i, "subtitle", coltitle,
                               tier["colTitle"])
                # 类名 `colTitle` 是给皮肤的钩子（与 type 阶梯同名）—— 没有它，
                # 皮肤只能猜标签名，猜错就掉回 UA 的 <h3> 样式（实测 18.7px/700 而非
                # 阶梯里的 26px）。`--s-bullet` 同理：顶层列表一直发，这里漏发过一次，
                # 皮肤那句 `font: 400 var(--s-bullet)/…` 因变量不存在**整条失效**，
                # 连字体族一起丢（掉到 UA 默认）。同一个角色，发的东西必须一致。
                cols.append(f'<div class="col"><div class="band {band}"></div>'
                            f'<h3 class="colTitle" {h3_attrs} '
                            f'style="--s-colTitle:{tier["colTitle"]}px">'
                            f'{rich(coltitle)}</h3>'
                            f'<ul class="bullets small" style="--s-bullet:{bsize}px">'
                            f'{li}</ul></div>')
            # 非默认结构布局加 v-<layout> 类（宽度规则在骨架 CSS）；even 是缺省，
            # 不加类 —— 旧输出（flex 等分 6+6）一个字节都不动。自造布局名则加
            # data-layout 钩子（结构仍是缺省，排法交给 skin）。
            if custom_layout:
                vclass, hook = "", f' data-layout="{html.escape(layout)}"'
            else:
                vclass = "" if layout == "even" else f" v-{layout}"
                hook = ""
            out.append(f'<div class="cols{vclass}"{hook}>' + "".join(cols) + "</div>")
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
                              chart=chart_declared_type(slide),
                              emphasis=slide.get("emphasis", {}),
                              unit=slide.get("unit", ""))
            # ⚠️ 外层 chartwrap 是**结构**：校验与测量的锚点（tag_attr 挂它身上）。
            # 里层 .g2 拿 data-g2（G2 spec JSON）—— 文档末尾统一实例化：
            # 声明式图形语法只出 spec，几何由 G2 算。
            g2_json = json.dumps(
                chart_g2_spec(slide, colors, chart_emphasis_set(slide),
                              tier=tier, fonts_body=tokens["fonts"]["body"]),
                ensure_ascii=True, separators=(",", ":")).replace("'", "&#39;")
            g2_specs.append(g2_json)
            out.append(f'<div class="chartwrap" {chart_attrs}>'
                       f'<div class="g2" data-g2=\'{g2_json}\'></div></div>')
            if slide.get("caption"):
                cap_attrs = tag(f"s{i}.caption", i, "caption", slide["caption"],
                                tier["caption"])
                out.append(f'<div class="chartcap" {cap_attrs}>{rich(slide["caption"])}</div>')
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
        if logo_uri and deck_mod.shows_logo(brand, kind, i, end_slide):
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
    # （`<title>` 与正文是 UTF-8；转义的只是这两个内嵌 JSON 载荷。）
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
    out.append('<div class="hint">← → 翻页 · S 讲稿 · B 黑屏 · F 全屏 · P 演示/滚动</div>')
    # 讲稿与目录随产物走（跟清单同一个模式）。演示台是**纯前端**的：打开一个 HTML
    # 文件就能用，不需要服务器、不需要第二个文件 —— 现场演出时少一个依赖就少一处出错。
    # 载荷跟清单一样走 \uXXXX 转义（转存/重编码都不会改坏它）。
    notes = {str(i): s["notes"] for i, s in enumerate(deck["slides"], 1)
             if isinstance(s.get("notes"), str) and s["notes"].strip()}
    outline = [{"t": s.get("title", ""), "k": s.get("kind") or s.get("type", "")}
               for s in deck["slides"]]
    for tag_id, payload_obj in (("__deck_notes", notes), ("__deck_outline", outline)):
        blob = json.dumps(payload_obj, ensure_ascii=True,
                          separators=(",", ":")).replace("<", "\\u003c")
        out.append(f'<script type="application/json" id="{tag_id}">{blob}</script>')
    out.append(CONSOLE_HTML)
    # 图表：先内联 G2 vendor（锁版本、离线可用），再实例化每页的 spec。
    # renderer: svg + animation: false —— 确定性（§41：同输入同输出）；
    # 渲染完打 data-chart-ready，测量端据此知道图表 DOM 已就绪。
    if g2_specs:
        try:
            with open(G2_VENDOR, encoding="utf-8") as fh:
                out.append(f"<script>{fh.read()}</script>")
        except OSError as exc:
            raise SystemExit(f"✗ 读不了 G2 vendor（{G2_VENDOR}）：{exc}") from exc
        out.append("<script>\n" + G2_INIT_JS + "\n</script>")
    out.append(f"<script>{SHELL_JS}</script>")
    out.append(f"<script>{CONSOLE_JS}</script>")
    out.append("</body></html>")
    return "\n".join(out)


measure_mod = _load_sibling("measure")   # 实测层（repair 循环里量产物）


_ROOT_VARS_RE = None  # 惰性编译（模块级 re 已 import）


def _root_vars(page: str) -> dict:
    """从产物文本抠 `:root{--k:v}` —— 与 pptx_native.parse_root_vars 同一份契约。

    resolved 契约要带颜色变量，导出器就不必再解析 HTML（HTML 只剩给人看）。
    """
    import re as _re
    global _ROOT_VARS_RE
    if _ROOT_VARS_RE is None:
        _ROOT_VARS_RE = _re.compile(r":root\s*\{(.*?)\}", _re.S)
    m = _ROOT_VARS_RE.search(page)
    out: dict = {}
    if not m:
        return out
    for chunk in m.group(1).split(";"):
        if ":" in chunk:
            k, _, v = chunk.partition(":")
            out[k.strip()] = v.strip()
    return out


def _load_layout():
    """加载 layout/ 包（模型 + 碰撞 + 修复梯）。机制同 _load_sibling。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "layout", "__init__.py")
    pkg_spec = importlib.util.spec_from_file_location("_deck_render_layout", path)
    if pkg_spec is None or pkg_spec.loader is None:
        raise RuntimeError(f"加载不了 layout 包：{path}")
    module = importlib.util.module_from_spec(pkg_spec)
    sys.modules[pkg_spec.name] = module
    pkg_spec.loader.exec_module(module)
    return module


def _repair_loop(deck_spec: dict, style: dict, assets: dict | None,
                 out_path: str, max_iter: int = 4) -> int:
    """渲 → 实测 → 修复梯 → 再渲（≤ max_iter 轮）。

    每轮把当前产物写到 out_path（最后一轮即交付物）；补丁与诊断写
    ``<out>.repair.json``，有补丁时另出 ``<out>.repaired.spec.json``
    （可采纳 / 可拒绝 —— 修复只动 spec 可表达的字段）。
    """
    repair_mod = _load_layout().repair
    patches: list = []
    diagnostics: list = []
    iterations = 0
    for i in range(max_iter):
        iterations = i + 1
        resolved = deck_mod.compile_spec(deck_spec, style, assets=assets)
        deckio.write_text(out_path, render_resolved(resolved))
        measured = measure_mod.measure(out_path)
        issues = repair_mod.signals(measured)
        if not issues:
            break
        actions, diags = repair_mod.plan(deck_spec, resolved, issues)
        # 同一页同一问题跨轮只记一次（声明类的诊断每轮都会重报，重复没有信息量）
        seen = {(d["slide"], d["issue"], d["why"]) for d in diagnostics}
        diagnostics.extend(
            {**d, "iteration": iterations} for d in diags
            if (d["slide"], d["issue"], d["why"]) not in seen)
        if not actions:
            break                       # 梯子走完（声明过 / 已到最小档）
        repair_mod.apply(deck_spec, actions)
        patches.extend({**a, "iteration": iterations} for a in actions)
    report = {"iterations": iterations,
              "fixed": not diagnostics and not repair_mod.signals(
                  measure_mod.measure(out_path)),
              "patches": patches, "diagnostics": diagnostics}
    deckio.write_json(out_path + ".repair.json", report)
    if patches:
        deckio.write_json(out_path.replace(".html", ".repaired.spec.json"),
                          deck_spec)
    for p in patches:
        print(f"  · 第 {p['slide']} 页 {p['field']}: {p['from']} → {p['to']}"
              f"（{p['why']}）")
    for d in diagnostics:
        print(f"  ✗ 第 {d['slide']} 页 {d['issue']} 超出 {d['over']:.0f}px —— "
              f"{d['why']}；建议：{d['suggest']}")
    state = "✓ 修复完成" if report["fixed"] else "✗ 未能完全修复（见 repair.json）"
    print(f"{state}（{iterations} 轮 / {len(patches)} 个补丁 / "
          f"{len(diagnostics)} 条诊断）")
    return 0 if report["fixed"] else 1


def _contract_main(deck_spec: dict, style: dict, as_json: bool = False) -> int:
    """把"这一页能装多少"打出来 —— **写内容前**先读预算。

    为什么要有这一步：修复梯里"缩字号"排最后（第 13 位），而人一旦写多了，
    最省事的动作就是压字号。把预算提前，写的时候就知道该收在多少字以内、
    这一页最多几条 —— 比"渲完再发现装不下"便宜得多。

    预算按 `grid` 跨度 + 风格 type 级数算（见 layout/contracts.py）；
    `--json` 给程序读，默认给人读。
    """
    tiers = (style.get("tokens") or {}).get("type") or {}
    rows = _load_layout().contracts.contract_for_slides(
        deck_spec["deck"].get("slides") or [], tiers)
    if as_json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        return 0
    if not rows:
        print("spec 里没有可算的页（需要 type）")
        return 0
    print(f"风格 {style['name']} 的 type 级数下的**每页容量**（估算：按 CJK 全角、"
          f"常见条目缩进；渲染后的实测才是硬门）")
    for r in rows:
        bits = [f"第 {r['page']} 页", r["pageType"],
                f"layout={r.get('layout') or '缺省'}"]
        if r.get("role"):
            bits.append(f"role={r['role']}")
        print("  " + " · ".join(bits))
        if r.get("title"):
            t = r["title"]
            print(f"      标题 ≤ {t['maxChars']} 字/行 × {t.get('maxLines', 1)} 行")
        for key, name in (("bullets", "条目"), ("columns", "栏"), ("nodes", "节点")):
            spec = r.get(key)
            if not spec:
                continue
            if key == "nodes":
                print(f"      {name} ≤ {spec['maxItems']} 个"
                      f"（标签 ≤ {spec.get('labelChars')} 字 / 说明 ≤ {spec.get('noteChars')} 字）")
            elif key == "columns":
                print(f"      {name}题 ≤ {spec.get('titleChars')} 字；"
                      f"每栏 {name}目 ≤ {spec['maxItems']} 条 × {spec['maxChars']} 字")
            else:
                print(f"      {name} ≤ {spec['maxItems']} 条 × {spec['maxChars']} 字")
    return 0


def _cmp_panel_css() -> str:
    """对比页选择面板的样式（只在对比产物里注入）。"""
    return ("<style>\n"
            ".cmp{position:fixed;left:20px;bottom:20px;z-index:50;"
            "font:400 15px/1.5 var(--body);background:var(--paper);color:var(--text);"
            "border:1px solid color-mix(in srgb,var(--text) 30%,transparent);"
            "padding:14px 16px;max-width:min(620px,86vw)}\n"
            ".cmp button{font:inherit;padding:4px 10px;cursor:pointer;"
            "background:transparent;color:inherit;margin-left:6px;"
            "border:1px solid color-mix(in srgb,var(--text) 35%,transparent)}\n"
            ".cmp button[aria-pressed=\"true\"]{background:var(--text);color:var(--paper)}\n"
            ".cmp .row{display:flex;flex-wrap:wrap;gap:8px;align-items:center;"
            "margin-top:8px}\n"
            ".cmp .row button{margin-left:0}\n"
            ".cmp textarea{width:100%;height:56px;margin-top:8px;display:none;"
            "font:12px/1.4 monospace;box-sizing:border-box}\n"
            ".cmp.min .body{display:none}\n"
            "</style>\n")


def _cmp_panel_html(plan: list, seed) -> str:
    """对比页的选择面板。

    **为什么要有它**：候选表摆出来只能给会看表的人；"版式该长什么样"这个决定
    应该能在页面上点出来。静态文件、零服务器：选择存内存 + localStorage，
    "复制选择"吐出一段 JSON，交给 `--picks` 回写 spec。

    `plan`：`[{"page": 3, "variants": ["even", null]}]`（`null` = 缺省/当前）。
    """
    return (_cmp_panel_css()
            + '<div class="cmp" id="cmp"><div><b>候选选择</b>'
              '<button id="cmp-toggle">收起</button></div>'
              '<div class="body"><div class="row">'
              '<button id="cmp-prev">上一组</button>'
              '<span id="cmp-pos"></span>'
              '<button id="cmp-next">下一组</button>'
              '<button id="cmp-copy">复制选择</button>'
              '<button id="cmp-reset">全部用缺省</button></div>'
              '<div class="row" id="cmp-vars"></div>'
              '<textarea id="cmp-out" readonly spellcheck="false"></textarea>'
              '<div class="row" id="cmp-hint" style="opacity:.62"></div></div></div>\n'
            + "<script>\n" + _cmp_panel_js(plan, seed) + "\n</script>\n")


def _cmp_panel_js(plan: list, seed) -> str:
    """面板行为：按 DOM 顺序把页分回组；选择存 localStorage；导出 JSON。"""
    return ("(function(){\n"
            f"  var PLAN={json.dumps(plan, ensure_ascii=False)};\n"
            f"  var KEY='deck-cmp-{html.escape(str(seed))}';\n"
            "  var slides=[].slice.call(document.querySelectorAll('section.slide'));\n"
            "  var groups=[],k=0;\n"
            "  PLAN.forEach(function(p){groups.push({page:p.page,"
            "variants:p.variants.map(function(v){return {name:v,index:k++};})});});\n"
            "  if(!groups.length) return;\n"
            "  var pick={};\n"
            "  try{ pick=JSON.parse(localStorage.getItem(KEY)||'{}')||{}; }"
            "catch(err){ pick={}; }\n"
            "  var at=0;\n"
            "  function label(v){ return v===null ? '缺省（当前渲染）' : v; }\n"
            "  function save(){ try{ localStorage.setItem(KEY,JSON.stringify(pick)); }"
            "catch(err){} }\n"
            "  function go(i){\n"
            "    at=Math.max(0,Math.min(groups.length-1,i));\n"
            "    var g=groups[at];\n"
            "    document.getElementById('cmp-pos').textContent=\n"
            "      '第 '+g.page+' 页 · 第 '+(at+1)+'/'+groups.length+' 组';\n"
            "    var box=document.getElementById('cmp-vars'); box.innerHTML='';\n"
            "    g.variants.forEach(function(v,vi){\n"
            "      var b=document.createElement('button');\n"
            "      b.textContent=(vi+1)+'. '+label(v.name);\n"
            "      b.setAttribute('aria-pressed',"
            " String(pick[g.page]===v.name || (v.name===null && !(g.page in pick))));\n"
            "      b.onclick=function(){ pick[g.page]=v.name; save(); go(at);\n"
            "        slides[v.index].scrollIntoView({block:'center'}); };\n"
            "      box.appendChild(b);\n"
            "    });\n"
            "  }\n"
            "  document.getElementById('cmp-prev').onclick=function(){ go(at-1); };\n"
            "  document.getElementById('cmp-next').onclick=function(){ go(at+1); };\n"
            "  document.getElementById('cmp-reset').onclick=function(){\n"
            "    pick={}; save(); go(at); };\n"
            "  document.getElementById('cmp-toggle').onclick=function(){\n"
            "    var p=document.getElementById('cmp'); p.classList.toggle('min');\n"
            "    this.textContent=p.classList.contains('min')?'展开':'收起'; };\n"
            "  document.getElementById('cmp-copy').onclick=function(){\n"
            "    var out=document.getElementById('cmp-out');\n"
            "    out.style.display='block'; out.value=JSON.stringify(pick); out.select();\n"
            "    try{ document.execCommand('copy'); }catch(err){}\n"
            "    document.getElementById('cmp-hint').textContent=\n"
            "      '已选 '+Object.keys(pick).length+' 页 —— 存成 picks.json 后： '\n"
            "      + 'render.py <spec> --candidates --picks picks.json'; };\n"
            "  go(0);\n"
            "})();")


def _default_layout(page_type: str) -> str | None:
    """不声明 layout 时渲染器用的缺省结构名（用于对比页标出"当前"）。"""
    return {"content-image": "visual-right", "two-column": "even"}.get(page_type)


def _apply_picks(deck_spec: dict, picks: dict) -> tuple[dict, list[str], list[str]]:
    """把 `{页码: 候选名}` 写回 spec。

    候选名可以是 `null` / `""` / `"缺省"` —— 表示**撤掉 layout**、回到渲染缺省。
    坏的键（不是数字、页码越界）不静默吞：写进 `problems` 让调用方开口。
    """
    picked = copy.deepcopy(deck_spec)
    slides = picked.get("deck", {}).get("slides") or []
    applied: list[str] = []
    problems: list[str] = []
    for key, name in (picks or {}).items():
        try:
            idx = int(key)
        except (TypeError, ValueError):
            problems.append(f"picks 的键 {key!r} 不是页码")
            continue
        if idx < 1 or idx > len(slides):
            problems.append(f"picks 里的第 {idx} 页不存在（共 {len(slides)} 页）")
            continue
        if name in (None, "", "缺省"):
            slides[idx - 1].pop("layout", None)
            applied.append(f"第 {idx} 页 → 缺省")
            continue
        if not isinstance(name, str):
            problems.append(f"第 {idx} 页的候选名 {name!r} 不是字符串")
            continue
        slides[idx - 1]["layout"] = name
        applied.append(f"第 {idx} 页 → {name}")
    return picked, applied, problems


def _candidates_main(deck_spec: dict, style: dict, assets, out_path: str,
                     pick: bool, seed=None, picks_path: str | None = None,
                     compare_path: str | None = None) -> int:
    """页级候选：每页 3 个**结构不同**的候选 + 1 个"当前/缺省"，整份 deck 联合择优。

    与旧版的区别（旧版逐页各挑各的最优）：

    - 候选先按**结构指纹**去重（镜像折叠成同一个构图）—— 三个候选不能是同一个
      构图的三件衣服；
    - 选择由 `layout/allocation.py` **整份 deck 一起**做（重复惩罚 + 拟合带 +
      seed 决定平局）：逐页最优会得到"每页都还行、整份一个版式用五遍"；
    - 产物是**对比页**（N 组 × 最多 4 页，同内容不同结构）+ 选择面板：
      决定权在作者，面板把选择吐成 JSON，`--picks` 回写 spec。

    `--pick`（自动采用最优）保留兼容：不带 `--picks` 时仍可用。
    """
    fp_mod = _load_layout().fingerprint
    alloc_mod = _load_layout().allocation
    cand_mod = _load_layout().candidates
    slides = deck_spec["deck"]["slides"]
    seed = seed if seed is not None else deck_spec["deck"].get("seed", 1)

    groups: dict[int, list] = {}
    for i, s in enumerate(slides, 1):
        vocab = cand_mod.searchable(s, IMAGE_LAYOUTS, TWO_COL_LAYOUTS)
        if vocab:
            groups[i] = fp_mod.distinct(s.get("type"), vocab)
    if not groups:
        print("没有可搜索的页（layout 已声明，或页型无结构布局）")
        return 0

    # 每个候选各渲一遍、实测、打分。同一轮里所有页试同一个候选序号 —— 一次
    # 渲染量完所有页，比"每页每候选渲染一次"少一个数量级的启动开销。
    results: dict[int, dict] = {i: {} for i in groups}
    for k in range(max(len(v) for v in groups.values())):
        trial = copy.deepcopy(deck_spec)
        touched = False
        for i, cands in groups.items():
            if k < len(cands):
                trial["deck"]["slides"][i - 1]["layout"] = cands[k]
                touched = True
        if not touched:
            break
        html = render_resolved(deck_mod.compile_spec(trial, style, assets=assets))
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as tf:
            tf.write(html)
            trial_path = tf.name
        try:
            measured = measure_mod.measure(trial_path)
        finally:
            os.unlink(trial_path)
        rects = measured.get("slides") or []
        for i, cands in groups.items():
            if k >= len(cands):
                continue
            els = [e for e in measured.get("elements", []) if e.get("slide") == i]
            top = rects[i - 1].get("y", 0) if i <= len(rects) else 0
            results[i][cands[k]] = cand_mod.score_page(
                slides[i - 1].get("type"), els, top, layout_name=cands[k])

    # 联合择优：候选的"拟合分"就是实测总分（密度是其中的区间满意度，
    # 不是最满优先）；重复与跨页节奏由 allocation 的惩罚项管。
    pages = []
    for i, cands in groups.items():
        page_type = slides[i - 1].get("type")
        pages.append({"key": i, "pageType": page_type,
                      "candidates": [
                          {"layout": n, "fit": results[i][n]["total"],
                           "fingerprint": fp_mod.fingerprint(page_type, n)}
                          for n in cands if results[i][n]["valid"]]})
    plan = alloc_mod.allocate(pages, seed=seed)
    chosen = plan["assignments"]

    for i, cands in groups.items():
        print(f"第 {i} 页（{slides[i - 1].get('type')}）:")
        keep = set(chosen.get(i) or [])
        for name in cands:
            sc = results[i][name]
            if not sc["valid"]:
                why = "、".join(sc["invalid_reason"][:2])
                print(f"  ✗ {name:13s} 作废（{why}）")
                continue
            so = sc["scores"]
            mark = "★" if name in keep else " "
            print(f"  {mark} {name:13s} 总分 {sc['total']:.2f}"
                  f"（占带 {sc['density']:.0%}"
                  f"{'，密度分 ' + format(so['density'], '.2f') if 'density' in so else ''}"
                  f"{'，可读 ' + format(so['readability'], '.2f')}"
                  f"{'，视觉 ' + format(so['focal'], '.2f') if 'focal' in so else ''}"
                  f"{'，平衡 ' + format(so['balance'], '.2f') if 'balance' in so else ''}）")
    for note in plan["diagnostics"]:
        print(f"  ⚠️ {note}")

    report = {"seed": seed, "searched": {str(i): t for i, t in results.items()},
              "assignments": {str(i): n for i, n in chosen.items()},
              "penalties": plan["penalties"], "score": plan["score"],
              "diagnostics": plan["diagnostics"]}
    deckio.write_json(os.path.splitext(out_path)[0] + ".candidates.json",
                      report)

    # ── 对比页：同内容、不同结构 ─────────────────────────────────────
    compare_path = compare_path or (os.path.splitext(out_path)[0] + ".compare.html")
    compare_spec = copy.deepcopy(deck_spec)
    panel_plan: list = []
    cursor = 0
    for i, s in enumerate(compare_spec["deck"]["slides"], 1):
        cands = chosen.get(i) or []
        if not cands:
            continue
        current = s.get("layout")
        variants: list = list(cands)
        if current is None:
            default = _default_layout(s.get("type"))
            if default not in variants:
                variants.append(None)          # 缺省（撤掉 layout 的那种渲法）
        elif current not in variants:
            variants.append(current)
        # 展开成连续多页：同内容、只换 layout
        expanded = []
        for name in variants:
            page = copy.deepcopy(s)
            if name is None:
                page.pop("layout", None)
            else:
                page["layout"] = name
            expanded.append(page)
        compare_spec["deck"]["slides"][cursor:cursor + 1] = expanded
        cursor += len(expanded)
        panel_plan.append({"page": i, "variants": variants})
    # 页码引用会失效（页数变了）—— 对比产物是**给人挑的**，不是交付物，
    # 所以只把原始页号写在面板里，产物内部不再依赖页码。
    compare_html = render_resolved(
        deck_mod.compile_spec(compare_spec, style, assets=assets))
    compare_html = compare_html.replace(
        "</body>", _cmp_panel_html(panel_plan, seed) + "</body>")
    deckio.write_text(compare_path, compare_html)
    print(f"✓ 对比页已写出 {compare_path}（{len(panel_plan)} 组 · "
          f"每组最多 {max(len(p['variants']) for p in panel_plan)} 页）"
          f"—— 在页面上挑，点「复制选择」得到 picks JSON")

    # ── 回写 ──────────────────────────────────────────────────────────
    if picks_path:
        picks = deckio.read_json(picks_path)
        picked, applied, problems = _apply_picks(deck_spec, picks)
        for p in problems:
            print(f"✗ {p}")
        if not applied:
            print("✗ picks 里没有可应用的选择")
            return 1
        picked_path = os.path.splitext(out_path)[0] + ".picked.spec.json"
        deckio.write_json(picked_path, picked)
        deckio.write_text(out_path, render_resolved(
            deck_mod.compile_spec(picked, style, assets=assets)))
        print(f"✓ 已按选择渲染 {out_path}（{'、'.join(applied)}）")
        print(f"  采纳后的 spec：{picked_path}")
        return 0
    if pick:
        if not chosen:
            print("✗ 没有可用候选，未改动")
            return 1
        picked_spec = copy.deepcopy(deck_spec)
        for i, name in chosen.items():
            picked_spec["deck"]["slides"][i - 1]["layout"] = name
        deckio.write_json(os.path.splitext(out_path)[0] + ".candidates.spec.json",
                          picked_spec)
        deckio.write_text(out_path, render_resolved(
            deck_mod.compile_spec(picked_spec, style, assets=assets)))
        where = "、".join(f"第 {i} 页 → {n}" for i, n in sorted(chosen.items()))
        print(f"✓ 已自动采用最优并渲染：{where}")
        return 0
    print(f"（未回写：在对比页上挑好，点「复制选择」存成 picks.json，再跑 "
          f"--candidates --picks picks.json；或加 --pick 直接采用最优）")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="deck-spec.json → HTML（可选：导出 resolved）")
    ap.add_argument("spec")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--style", default=None,
                    help="风格目录名（缺省读 spec 的 deck.style；spec 必须写它）")
    ap.add_argument("--resolved", default=None, metavar="PATH",
                    help="额外导出 resolved.deck.json（渲染器的唯一输入，含决策 trace）")
    ap.add_argument("--trace", action="store_true",
                    help="打印决策 trace（每条：阶段 / 决定 / 理由）")
    ap.add_argument("--repair", action="store_true",
                    help="渲→实测→修复梯→再渲（≤4 轮；只动 spec 可表达字段，"
                         "作者声明过的不碰，产出 *.repaired.spec.json）")
    ap.add_argument("--candidates", action="store_true",
                    help="页级候选：每页 3 个结构不同的候选 + 缺省，整份 deck 联合择优，"
                         "并写出对比页（同内容不同结构，页面上挑；复制选择得 picks JSON）")
    ap.add_argument("--pick", action="store_true",
                    help="配合 --candidates：不问作者，直接采用最优候选并渲染")
    ap.add_argument("--contract", action="store_true",
                    help="打出每页容量（标题/条目/栏目/节点的字数与条数预算）——"
                         "写内容前先读，别写完再缩字号")
    ap.add_argument("--json", action="store_true",
                    help="配合 --contract：输出 JSON（给程序读）")
    ap.add_argument("--picks", default=None, metavar="PATH",
                    help="配合 --candidates：按对比页导出的 picks.json（{页码: 候选名}）"
                         "回写 spec 并渲染，产出 *.picked.spec.json")
    ap.add_argument("--seed", default=None,
                    help="候选择优的随机种子（缺省读 spec 的 deck.seed）——"
                         "同 seed 同输入必得同结果")
    args = ap.parse_args(argv[1:])
    deck_spec = deckio.read_json(args.spec)
    assets = load_assets(args.spec)      # assets/manifest.json（§12 管线入口）
    name = args.style or deck_spec["deck"].get("style")
    style = load_style(name)
    if args.contract:
        return _contract_main(deck_spec, style, args.json)
    if args.repair:
        return _repair_loop(deck_spec, style, assets, args.out)
    if args.candidates or args.pick or args.picks:
        return _candidates_main(deck_spec, style, assets, args.out, args.pick,
                               seed=args.seed, picks_path=args.picks)
    resolved = deck_mod.compile_spec(deck_spec, style, assets=assets)
    page = render_resolved(resolved)
    deckio.write_text(args.out, page)
    print(f"✓ 已写出 {args.out}（风格 {style['name']} / {len(page)} 字节 / "
          f"{len(deck_spec['deck']['slides'])} 页）")
    loc_note = style_location_note(style_folder(name), args.spec)
    if loc_note:
        print(loc_note)
    if args.resolved:
        # 完整契约：语义（manifest）+ 真实几何（measure 实测，一次成型）+
        # 颜色变量 + 资产基准目录。导出器（pptx_native --resolved）只吃这一份，
        # 不再自己解析 HTML —— HTML 与 PPTX 同源，几何只在渲染时定一次。
        measured = measure_mod.measure(args.out)
        resolved["manifest"] = measure_mod.read_manifest(page)
        resolved["geometry"] = {
            "slides": measured.get("slides") or [],
            "elements": measured.get("elements") or [],
            "decor": measured.get("decor") or [],
        }
        resolved["vars"] = _root_vars(page)
        resolved["baseDir"] = os.path.dirname(os.path.abspath(args.out))
        deckio.write_json(args.resolved, resolved)
        n_geo = len(resolved["geometry"]["elements"])
        print(f"✓ 已写出 {args.resolved}（{len(resolved['trace'])} 条 trace · "
              f"colorSet={resolved['colorSet']} · {n_geo} 个实测元素）")
    if args.trace:
        for t in resolved["trace"]:
            slide = f" 第 {t['slide']} 页" if t.get("slide") else ""
            print(f"  [{t['stage']}]{slide} {t['decision']}")
            for r in t.get("reason", []):
                print(f"      · {r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
