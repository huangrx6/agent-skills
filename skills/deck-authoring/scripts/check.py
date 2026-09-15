#!/usr/bin/env python3
"""#76 产物校验 —— 只查能机械判定的东西，不承诺审美。

分两类（这个区分很重要，照仓库既有做法，同 `check_pointers.py` 的 broken / suspect）：

**阻塞**（`check()`）：
1. 对比度     文字色必须是两墨叠印色（主/副色天生 2.3~3.0，承载不了文字），且分档过门槛
2. 版面越界   **实测**：元素盒子越出**它所在那一页**的边界（`.slide` 是 overflow:hidden）
3. 容器裁切   **实测**：元素**自己会裁**（overflow 不是 visible）且 scroll 大于 client
4. 产物健康   **实测**：图片没加载 / 产物里的脚本报错
5. 错位区间   从**产物 HTML** 里读实际写进去的 --dx/--dy/--rot，比对 token 区间
6. 装饰不压文字 墨块必须落在安全区，不与文字栏相交
7. 图表成比例 柱高两两之间必须与数据成比例（基准取数据最大那条，不拿图形最高那根）
8. 图表区无错位 图表容器（逐层配对地扫完整个容器）里不许出现 riso 错位元素

**提示**（`advisories()`，不阻塞）：字体回退 —— 启发式，衬线撞衬线会误报。

2~4 条的数字来自 `measure.py`（真浏览器实测），**不是估算**：原先用
`text_width()` 估宽，对同一行汉字能差 2 倍多，而且偏差随字体/字距/折行变。

跑法：python3 check.py deck-spec.json out.html      # 全过退出 0，任一不过退出 1
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
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


ink = _load_sibling("ink")
deckio = _load_sibling("deckio")   # IO 收口：读不到产物要报清楚，不甩 traceback
measure_mod = _load_sibling("measure")   # 实测层：版面判断全部走它，不估算
render_mod = _load_sibling("render")   # 只为拿“同一个风格”的 token（单一来源）
brand_mod = _load_sibling("brand")     # 品牌资产（logo / 色板 / 字体）

TOKENS = os.path.join(HERE, "..", "styles", "swiss-grid", "style.json")

# **两个不同的框，别混用**（我自己第一版就混了 ✗，导致正常产物被误判"溢出"）：
#   内容区 = 版面减去内边距，量"放不放得下"（宽 1600-2×84 = 1432）
#   文字栏 = 文字实际占的窄带，只用来判"墨块进没进栏"（更保守）
CONTENT = (84.0, 132.0, 1516.0, 838.0)
TEXT_BAND = (84.0, 132.0, 1000.0, 770.0)
SLIDE_W, SLIDE_H = 1600.0, 900.0
# 内容只占正文带这么少 → 提示“这页几乎没有内容”。
#
# ⚠️ 这个阈值只能抓**近于空的页**，不能拿来判“太稀”。第一版写的是 0.55，
# 结果它在 demo 的 3 个正常页上全部开火（41% / 45% / 37%）—— 而那几页看着
# 一点都不像没做完（左轨 + 实线 + 巨号页码都在）。当初用户抱怨 swiss 第一版
# “下半页 55% 是死的”，真正原因不是内容少，而是**没有构图锚点**；修法也是加锚点，
# 不是加内容。所以：留白是不是问题，取决于风格有没有锚点，**像素密度算不出来**。
# 密度这个量该在 fit.py 里看（那里是选版式的场景，旁边还带着“可以合页”的建议），
# 不该在每次校验时拿一个不懂风格的阈值去喷人。
DEAD_SPACE_NOTE = 0.28

# **一张图覆盖整页** —— 禁止。
#
# 为什么是禁止而不是提示：一页的信息（标题 / 条目 / 数字 / 示意）一旦被画进图里，
# 它就同时失去了可编辑、可搜索、可翻译、可被读屏器读这四件事；而"对方要改字"
# 正是本 skill 出原生 PPTX 的理由。图在版面上的角色只有两种：**配图**（占一栏）
# 或**点缀**（更小），背景那种大图也不承载这一页的信息。
#
# 阈值离真实情况很远，所以不会误伤：唯一带图的 content-image 版式，实测配图占
# 整页 **17.0%**（607×404 / 1600×900）。取 0.60 是 3.5 倍余量。
FULL_PAGE_IMAGE = 0.60
CORNER = {  # zone → (右偏移, 下/上偏移, 靠上?)
    "tr": (60.0, 40.0, True), "br": (130.0, 140.0, False),
    "tl": (60.0, 40.0, True), "bl": (130.0, 140.0, False),
}


def _div_subtree(html: str, start: int) -> str:
    """从 `start` 处的 `<div` 开始，逐层配对，返回那个 div 的整段 HTML。

    为什么不用 `.*?</div>`：那是**非贪婪**的，遇到容器里第一个 `</div>` 就停。
    图表容器里有 `.hf` 那一层，于是正则实际只扫了最外面一层 —— 把 riso 塞到
    更深处（比如 svg 区域里）旧写法直接放行。这是真实漏报，不是杞人忧天。
    """
    depth = 0
    i = start
    while i < len(html):
        nxt_open = html.find("<div", i)
        nxt_close = html.find("</div>", i)
        if nxt_close == -1:
            return html[start:]
        if nxt_open != -1 and nxt_open < nxt_close:
            depth += 1
            i = nxt_open + 4
        else:
            depth -= 1
            i = nxt_close + 6
            if depth == 0:
                return html[start:i]
    return html[start:]


def _num(raw: str, where: str, problems: list[str]) -> float | None:
    """转 float；转不了就**报成问题**，不抛异常。

    `check()` 是库函数，契约是「返回问题清单」，不是「甩 traceback」。而且产物里
    的数字读不出来本身就是一种产物损坏 —— 应该被报出来，而不是静默跳过或炸掉。
    """
    try:
        return float(raw)
    except ValueError:
        problems.append(f"{where} 不是合法数字：{raw!r}（产物损坏？）")
        return None


def _check_layout(measured: dict) -> list[str]:
    """② 版面越界 / 容器裁切 —— 全部来自**真浏览器实测**，不是估算。

    为什么必须实测：原先靠 `text_width()` 估算（CJK 1em / ASCII 0.55em），对同一行
    12 个汉字标题，估算给 1032px、真渲出来是 2124px —— **低估 2 倍多**，于是
    end 页（180px 字号）越出版面 612px、被 `overflow:hidden` 静静裁掉，而校验说"全过"。

    两条判据（都是"已经发生的事"，不是推测）：
    甲・越出版面：`.slide` 是 overflow:hidden，元素盒子出去就是被裁。
    乙・容器内裁切：元素自己会裁（overflow 不是 visible）且 scrollW/H > clientW/H。

    ⚠️ 比的是**该元素所在那一页**的盒子，不是全局 1600×900 —— 产物是竖向堆叠的多页，
    第 2 页的元素 y 本来就在 900 以下；拿全局边界比会把后面每页都误报（实测踩过）。

    注意：装饰墨块**故意**溢出到版面外（right:-60px），但它们没有 `data-m`、
    不进这份清单，所以不会误报。
    """
    out: list[str] = []
    slides = measured.get("slides") or []
    for el in measured.get("elements", []):
        if not el.get("visible", True):
            continue
        mid = el.get("id", "?")
        role = el.get("role") or "元素"
        x, y, w, h = el["x"], el["y"], el["w"], el["h"]
        # 元素属于清单里的哪一页（1-based）→ 取那一页的盒子
        idx = el.get("slide")
        if isinstance(idx, int) and 1 <= idx <= len(slides):
            sl = slides[idx - 1]
            sx, sy, sw, sh = sl["x"], sl["y"], sl["w"], sl["h"]
        else:
            sx, sy, sw, sh = 0.0, 0.0, SLIDE_W, SLIDE_H
        right, bottom = x + w, y + h
        box_r, box_b = sx + sw, sy + sh
        overs = []
        if right - box_r > 1:
            overs.append(f"右缘 {right:.0f}px 越出该页右边界 {box_r:.0f}px（超出 {right - box_r:.0f}px）")
        if bottom - box_b > 1:
            overs.append(f"下缘 {bottom:.0f}px 越出该页下边界 {box_b:.0f}px（超出 {bottom - box_b:.0f}px）")
        if x < sx - 1:
            overs.append(f"左缘 {x:.0f}px 越出该页左边界 {sx:.0f}px")
        if y < sy - 1:
            overs.append(f"上缘 {y:.0f}px 越出该页上边界 {sy:.0f}px")
        if overs:
            out.append(f"{mid}（{role}）越出版面：" + "；".join(overs)
                       + " —— 该页是 overflow:hidden，会被裁掉")
            continue
        if el.get("text"):
            pass
        # 容器内裁切：**只有元素自己会裁**（overflow 不是 visible）时才算数。
        # `.foot` 这种 overflow:visible 的，scrollHeight 比 clientHeight 大 2px 是
        # 行高与字面度的正常差 —— 没被裁，报它就是误报（实测踩过）。
        clips = el.get("overflow") not in (None, "visible")
        if clips and (el["scrollW"] - el["clientW"] > 1 or el["scrollH"] - el["clientH"] > 1):
            out.append(f"{mid}（{role}）内容被容器裁切："
                       f"scroll {el['scrollW']}×{el['scrollH']} > client {el['clientW']}×{el['clientH']}")
    return out


def _check_full_page_image(measured: dict) -> list[str]:
    """一张图盖住整页 —— **阻塞**（见 FULL_PAGE_IMAGE 的注释）。

    为什么这条要有牙：它是"不要把所有东西都生成到一张图上、再让图片覆盖整页"这条
    硬规则的落点。今天是不可达的（没有整页图的版式），但**规则是被声明的**，
    所以它需要一个能失败的守卫 —— 否则哪天有人加了个全幅版式、或者手改 skin，
    这个禁止就会静默失效。
    """
    out: list[str] = []
    total = render_mod.SLIDE_W * render_mod.SLIDE_H
    if not total:
        return out
    for el in measured.get("elements", []):
        if el.get("role") not in ("logo", "image"):
            continue
        # 尺寸由 measure.py 写成数字；不是数字就跳过，不抛（check() 从不抛）。
        w = el.get("w")
        h = el.get("h")
        if not isinstance(w, (int, float)) or not isinstance(h, (int, float)):
            continue
        area = w * h
        if area / total >= FULL_PAGE_IMAGE:
            out.append(
                f"第 {el.get('slide')} 页的图盖住了整页的 {area / total:.0%}"
                f"（{w:.0f}×{h:.0f}px / "
                f"{render_mod.SLIDE_W}×{render_mod.SLIDE_H}）—— **一张图覆盖整页是不允许的**："
                f"这一页的信息（标题 / 条目 / 数字 / 示意）必须是版面里的**真文字**，"
                f"图只能是配图或点缀。要那种观感就换版式，别把内容画进图里")
    return out


def _check_measured_health(measured: dict) -> list[str]:
    """产物健康度：页面报错 / 图片没加载 —— 这两类以前根本没人看。"""
    out: list[str] = []
    for err in measured.get("errors", []):
        out.append(f"产物里的脚本报错：{err}")
    for im in measured.get("images", []):
        if not (im.get("complete") and im.get("naturalW")):
            out.append(f"图片没加载：{im.get('src')!r} —— "
                       f"相对路径的产物挪个目录就会全员裂图（交付前要么同目录交付，要么 base64 内嵌）")
    return out


def _check_font_fallback(measured: dict) -> list[str]:
    """字体回退**提示**（不判失败）—— 而且要说清楚**谁顶上了**。

    启发式：拿一个一定不存在的族当基准比宽度，宽度一样 = 那个族没生效。
    通用族（serif / monospace）排除 —— 它们不是字体而是**回退目标**，不排会误报“缺失”。
    即便如此仍可能误报（衬线撞衬线），所以只提示。

    只跟**有文字的元素**的栈算（探针已经滤掉无文字的，见 `measure.py`）。
    早先按全部元素统计，结果报了 `<figure>` 的 'PingFang SC' —— 那是 Chrome 给 CJK 的
     UA 默认值，而那个元素不渲染任何字形（实测踩过）。
    """
    fonts = measured.get("fonts", {})
    out: list[str] = []
    for stack in measured.get("stacks", []):
        first = stack[0] if stack else None
        if not first or fonts.get(first, {}).get("available"):
            continue                       # 首选能用，没有回退
        winner = next((f for f in stack if fonts.get(f, {}).get("available")), None)
        tail = (f"，实际用的是 {winner!r}" if winner
                else "，栈里没有一个可用 —— 会落到系统默认")
        out.append(f"字体回退（启发式提示）：声明的 {first!r} 在本机不可用{tail}"
                   f" —— 排版会随机器变，交付前确认一下")
    return out


def _check_brand(measured: dict, deck: dict, tokens: dict) -> tuple[list[str], list[str]]:
    """品牌资产：**logo 压文字（阻塞）** + 两条提示。

    为什么 logo 压文字要阻塞：它和“越出该页”是两回事 —— 两个盒子都在页内，
    `_check_layout` 看不出问题，但 logo 盖上标题就是废页。这条是确定性的
    （两个实测矩形相交），所以它够格阻塞。

    另两条是提示，因为它们的修法在品牌那边不在版面这边（补一个反白版 / 换更大的图）。
    """
    problems: list[str] = []
    notes: list[str] = []
    name = deck.get("brand")
    if not name:
        return problems, notes
    brand = brand_mod.load(name)
    els: list[dict] = measured.get("elements", [])
    logos = [e for e in els if e.get("role") == "logo"]
    if not logos:
        return problems, notes

    for lg in logos:
        for t in els:
            # 只跟**真带文字**的元素比。此处不能用“intendedText 非空”一句话打发：
            # logo / 内容图 / 图表的清单条目的 text 也是非空的（存的是文件路径或数据），
            # 拿那个当“有文字”会把 logo 报成“logo 压住了自己”（实写时就这么报了一次）。
            if t.get("slide") != lg.get("slide") or not t.get("intendedText"):
                continue
            if t.get("role") in ("logo", "image", "chart"):
                continue
            if _overlap(lg, t):
                problems.append(
                    f"logo 压住了文字（第 {lg.get('slide')} 页）："
                    f"logo x={lg['x']:.0f}..{lg['x'] + lg['w']:.0f} y={lg['y']:.0f}.."
                    f"{lg['y'] + lg['h']:.0f} 与 {t.get('id')} "
                    f"{t['x']:.0f}..{t['x'] + t['w']:.0f} 相交 —— "
                    f"logo 换小一点、或让风格把它放到另一个角")

    paper = tokens["colorSets"].get(deck.get("colorSet"), {}).get("background", "#FFFFFF")
    if brand_mod.is_dark_paper(paper) and not brand.get("logoInverse"):
        notes.append(
            f"品牌 {name!r} 只给了一个 logo，而这张纸是深底（{paper}）—— "
            f"实测过：白底用的 logo 放到纯黑底上，深色那块会**直接消失**（只剩零星浅色）。"
            f"建议在 brand.json 里补 logoInverse（与正版形状一致、只换明暗）")
    # 图被放大渲染 → 糊。logo 与**内容图**都查：判据一样（渲染宽 > 原始宽 5%），
    # 只是 logo 是品牌资产、内容图是每页那几张。SVG 不参与（放大不糊，它报的是
    # viewBox 尺寸）—— 素材里凡是 .svg 的跳过。
    for el in els:
        if el.get("role") not in ("logo", "image"):
            continue
        src = str(el.get("intendedText", ""))
        if src.lower().endswith(".svg"):
            continue
        nat = el.get("naturalW") or 0
        if nat and el.get("w", 0) > nat * 1.05:
            notes.append(
                f"第 {el.get('slide')} 页的图被放大渲染（原始 {nat:.0f}px 宽 → "
                f"实际 {el['w']:.0f}px）—— 会糊；换更大的位图，或者直接用 SVG")
    return problems, notes


def _check_deck_shape(measured: dict, deck: dict) -> tuple[list[str], list[str]]:
    """deck 级：**半页死白**（提示）+ 版式单一（提示）+ 没有封面（提示）。

    为什么“半页死白”必须在这里补：以前只有“装不下”那半边有牙（越界检查）。
    另半边一直是绿的 —— 一页内容只占正文带 40% 的话，渲染成功、校验全过，
    但人一眼就看出“这页没做完”。本仓库 swiss-grid 第一版正是这么死的：
    “白底 + 左上标题 + 编号列表”，下半页 55% 是死的。

    为什么是**提示**而不是阻塞：留白是风格的一部分（安静派就是靠留白），
    把“不够满”当硬错误会逼着人把每页塞满 —— 那是另一头错。
    """
    problems: list[str] = []
    notes: list[str] = []
    slides = deck.get("slides", [])
    kinds = [s.get("type") for s in slides]

    # 没有封面：不是硬错（有人就把第一页当正文页），但很难是个有意的选择。
    if slides and "title" not in kinds:
        notes.append("这份 deck 没有封面页（没有 type=title）—— 是漏了，还是有意？")

    # 版式单一：全是一种版式时，视线没有落点变化。
    content_kinds = [k for k in kinds if k not in ("title", "end")]
    if len(set(content_kinds)) == 1 and len(content_kinds) >= 3:
        notes.append(
            f"{len(content_kinds)} 页内容全是一种版式（{content_kinds[0]}）—— "
            f"构图没有变化。用 fit.py 试排一下别的版式，或把其中几页拆/并")

    # 图量：**全篇一张图都没有**时提示，并点名最该加图的那几页。
    #
    # 为什么要有这一条：用户明确要求「图片该要就要，别因为嫌麻烦就少要，多了也没事」。
    # 而在那之前，这条流水线对"少要"是完全沉默的 —— 一份 20 页全文字的 deck
    # 能一路绿灯到底。沉默就是默认，默认就是少要。
    #
    # 为什么仍是**提示**而不是阻塞："这份 deck 该有几张图"取决于内容（讲现场、
    # 讲对比、讲某个东西长什么样，就该有图；讲三条结论，就不必有），像素判不出来。
    # 所以这里只做一件事：在**一张图都没有**时开口，并指出位置。
    # 只在 0 张时响，避免对已有图的 deck 反复唠叨 —— 唠叨会让人整体忽略提示。
    if slides and not any(s.get("image") for s in slides):
        text_only = [(i, s) for i, s in enumerate(slides, 1)
                     if s.get("type") == "content-text" and len(s.get("bullets", [])) >= 4]
        notes.append(
            f"全篇 {len(slides)} 页**没有一张图** —— 一页在讲「某个东西长什么样 / "
            f"现场 / 对比」就该有图（用 content-image 版式）；讲「三条结论」不必有。"
            f"图多一点没坏处，少要才是问题")
        for i, s in text_only[:3]:
            notes.append(
                f"第 {i} 页「{s.get('title', '')}」是 {len(s.get('bullets', []))} 条纯文字 —— "
                f"想加图的话这一页最容易加")

    # 逐页密度：只对“承载内容”的版式判 —— 封面/收尾页本来就该稀疏。
    for i, slide in enumerate(slides, 1):
        if slide.get("type") in ("title", "end"):
            continue
        box = measure_mod.slide_content_span(measured, i)
        if box is None:
            continue
        top, bottom = box
        used = (bottom - render_mod.CONTENT_TOP) / (render_mod.CONTENT_BOTTOM
                                                    - render_mod.CONTENT_TOP)
        if used < DEAD_SPACE_NOTE:
            notes.append(
                f"第 {i} 页几乎没有内容（只占正文带 {used:.0%}）—— 内容底 "
                f"{bottom:.0f}px / 正文带底 {render_mod.CONTENT_BOTTOM:.0f}px。"
                f"一页只有标题没条目通常是漏了；确实要留白就删掉这页"
                f"（想看疏密去跑 fit.py）")
    return problems, notes


def _check_empty_content(deck: dict) -> list[str]:
    """空标题 / 空条目 —— **阻塞**。

    渲染器不会因为它空就不画那个盒子：空标题会画一条标题块的下划线，空条目会占
    一行高。结果是一页看着像渲染坏了。而它本来只是“内容没写”。
    """
    problems: list[str] = []
    for i, slide in enumerate(deck.get("slides", []), 1):
        if not str(slide.get("title", "")).strip():
            problems.append(f"第 {i} 页标题是空的 —— 标题块会画出一条线却什么都不写")
        for key in ("bullets",):
            for k, item in enumerate(slide.get(key) or []):
                if not str(item).strip():
                    problems.append(f"第 {i} 页 {key}[{k}] 是空的 —— 会占一行却是空白")
        for ci, col in enumerate(slide.get("columns") or []):
            for k, item in enumerate((col or {}).get("bullets") or []):
                if not str(item).strip():
                    problems.append(f"第 {i} 页 columns[{ci}].bullets[{k}] 是空的")
        for k, node in enumerate(slide.get("nodes") or []):
            if not str((node or {}).get("label", "")).strip():
                problems.append(f"第 {i} 页 nodes[{k}].label 是空的 —— 时间线上会是一个空节点")
        for k, d in enumerate(slide.get("data") or []):
            if not str((d or {}).get("label", "")).strip():
                problems.append(f"第 {i} 页 data[{k}].label 是空的 —— 图表会少一根柱的标签")
    return problems


def _overlap(a: dict, b: dict) -> bool:
    return not (a["x"] + a["w"] <= b["x"] or b["x"] + b["w"] <= a["x"]
                or a["y"] + a["h"] <= b["y"] or b["y"] + b["h"] <= a["y"])


def style_tokens(spec: dict, override: dict | None = None) -> dict:
    """解析 deck 用哪个风格，取它的 token。

    token 不再由调用方“带进来”：风格已经写在 spec 的 `deck.style` 里了
    （缺省 swiss-grid）。让校验层自己去读同一份，就不会出现“拿 A 风格的门槛
    去量 B 风格的产物”——那是多风格之后新增的错配面。
    """
    if override is not None:
        return override
    return render_mod.load_style(spec["deck"].get("style", render_mod.DEFAULT_STYLE))["tokens"]


def check(spec: dict, html_path: str, tokens: dict | None = None,
          measured: dict | None = None) -> list[str]:
    """跑全部阻塞检查，返回问题清单（空的 = 全过）。

    `tokens=None` 时按 spec 里的风格去加载 —— 调用方多数情况下不该手递 token。
    """
    tokens = style_tokens(spec, tokens)
    problems: list[str] = []
    page = deckio.read_text(html_path)      # 读一次就够（以前读了三次）
    deck = spec["deck"]
    colors = tokens["colorSets"][deck["colorSet"]]
    paper = colors["background"]
    ink_text = ink.text_color(colors)
    limits = tokens["contrast"]
    # 文字栏（判"墨块进没进栏"用；版面越界那一套已经改成实测了，不再靠推算）
    bx0, by0, bx1, by1 = TEXT_BAND

    # ① 对比度（解析式：叠印色相对纸色）—— 这条不需要测量，色值是推导出来的
    ratio = ink.contrast(ink_text, paper)
    if ratio < limits["minBody"]:
        problems.append(f"叠印墨对比度 {ratio:.2f} < {limits['minBody']}（文字色不达标）")

    # ② 版面越界 / 容器裁切 —— **实测**（不估）；同时看产物健康度
    data: dict = measure_mod.measure(html_path) if measured is None else measured
    problems.extend(_check_layout(data))
    problems.extend(_check_measured_health(data))
    problems.extend(_check_full_page_image(data))
    brand_problems, _ = _check_brand(data, deck, tokens)
    problems.extend(brand_problems)
    # 空内容与品牌无关，但它和越界一样是“一页看着坏了”—— 所以也走阻塞
    problems.extend(_check_empty_content(deck))

    for i, slide in enumerate(deck["slides"], 1):
        declared = slide.get("color")
        if declared and declared != "overprint":
            problems.append(f"第 {i} 页 声明 color={declared!r} —— 主/副色不能承载文字，只允许 overprint")

    # ④ 图表：柱高必须与数据成比例（独立复核，不看渲染器自觉），且图表区不许带错位
    #
    # 数柱高**必须限定在该页的 <section> 里**。压测之前这里扫的是整页 ——
    # 一页 deck 只有一张图时看不出问题，三张图时第一张会数到 6+2+3=11 根柱，
    # 报"柱子 11 根 ≠ 数据 6 条"。那种假报错比不报更坏：它会把一个正常的 deck 挡住。
    sections = page.split('<section class="slide"')[1:]
    for i, slide in enumerate(deck["slides"], 1):
        if slide.get("type") != "chart":
            continue
        block = sections[i - 1] if i - 1 < len(sections) else ""
        heights: list[float] = []
        for raw in re.findall(r'class="bar"[^>]*height="([^"]+)"', block):
            num = _num(raw, f"第 {i} 页图表柱高", problems)
            if num is not None:
                heights.append(num)
        values: list[float] = []
        for k, d in enumerate(slide.get("data", [])):
            num = _num(str(d.get("value")), f"第 {i} 页图表 data[{k}].value", problems)
            if num is not None:
                values.append(num)
        if len(heights) != len(values):
            problems.append(f"第 {i} 页图表：柱子 {len(heights)} 根 ≠ 数据 {len(values)} 条")
        elif values:
            # **两两比例**判据，不是"对峰值归一"：一旦有一根被改高，峰值基准就跟着错，
            # 于是六根全报（实测过 ✗）—— 那种输出等于没说清是谁错了。
            # 两两比例与基准无关，只会指向真的那一根。
            # 基准取**数据最大**的那条，不是图形最高的那根 —— 拿图形当基准的话，
            # 被篡改的那根一旦成为最高，它自己就被跳过、而无辜的柱子被报（实测过 ✗）。
            base = max(range(len(values)), key=lambda k: values[k])
            for k, (h, v) in enumerate(zip(heights, values)):
                if k == base or not values[base]:
                    continue
                want = heights[base] * v / values[base]
                if abs(h - want) > 1.5:
                    problems.append(f"第 {i} 页图表第 {k + 1} 根柱高 {h:.1f}px 与数据 {v} 不成比例"
                                    f"（按最高那根的长度换算应为 {want:.1f}px）")
    # ④ 图表区无错位：**逐层配对**扫整个容器，不是扫到第一个 </div> 就停。
    for hit in re.finditer(r'<div class="chartwrap"', page):
        block = _div_subtree(page, hit.start())
        if "riso" in block:
            problems.append("图表容器里出现了错位叠印元素（riso 只允许做容器与背景，不能进图表区）")

    # ③ 错位区间：读产物里真正写进去的值
    m = tokens["misregistration"]
    for dx, dy, rot in re.findall(r"--dx:([-\d.]+)px;--dy:([-\d.]+)px;--rot:([-\d.]+)deg", page):
        for raw, (lo, hi), name in ((dx, m["offsetRangeX"], "dx"),
                                    (dy, m["offsetRangeY"], "dy"),
                                    (rot, m["rotationRange"], "rot")):
            value = _num(raw, f"错位参数 {name}", problems)
            if value is None:
                continue
            if not (lo <= value <= hi):
                problems.append(f"错位参数 {name}={value} 越出 token 区间 [{lo}, {hi}]")

    # ④ 装饰不压文字
    for zone, raw_size in re.findall(r'data-zone="(\w+)" data-size="([^"]*)"', page):
        if zone not in CORNER:
            problems.append(f"未知装饰 zone={zone!r}")
            continue
        right_off, top_off, up = CORNER[zone]
        s = _num(raw_size, f"装饰墨块 zone={zone} 的 data-size", problems)
        if s is None:
            continue
        left = SLIDE_W + right_off - s if "r" in zone else -right_off
        top = -top_off if up else SLIDE_H + top_off - s
        rect = (left, top, left + s, top + s)
        if not (rect[2] <= bx0 or rect[0] >= bx1 or rect[3] <= by0 or rect[1] >= by1):
            problems.append(f"装饰墨块 zone={zone} 与文字栏相交 rect={tuple(round(v) for v in rect)}"
                            f"（安全区规则：只放右侧两角）")
    return problems


def advisories(measured: dict, spec: dict | None = None,
               tokens: dict | None = None) -> list[str]:
    """**不阻塞**的提示。

    与 `check()` 的分工照仓库既有做法（同 `check_pointers.py` 的 broken / suspect）：
    能确定性判定的才阻塞；启发式的只提示。字体那条是启发式 —— 拿一个一定不存在的
    族当基准比宽度，衬线撞衬线时可能误报，拿它挡交付会把人逼到忽略整个检查。
    """
    notes = _check_font_fallback(measured)
    if spec is not None and tokens is not None:
        _, brand_notes = _check_brand(measured, spec.get("deck", {}), tokens)
        notes.extend(brand_notes)
        _, shape_notes = _check_deck_shape(measured, spec.get("deck", {}))
        notes.extend(shape_notes)
    return notes


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="deck 产物校验（版面靠真浏览器实测）")
    ap.add_argument("spec")
    ap.add_argument("html")
    ap.add_argument("--tokens", default=None,
                    help="覆盖 token 文件（缺省按 spec 的 deck.style 去找）")
    args = ap.parse_args(argv[1:])
    spec = deckio.read_json(args.spec)
    tokens = deckio.read_json(args.tokens) if args.tokens else None
    measured = measure_mod.measure(args.html)      # 只量一次，校验与提示共用
    tokens = style_tokens(spec, tokens)
    problems = check(spec, args.html, tokens, measured=measured)
    if problems:
        print(f"✗ {len(problems)} 个问题：")
        for p in problems:
            print("  ·", p)
        for n in advisories(measured, spec, tokens):
            print("  ·", n)
        return 1
    print("✓ 校验全过（对比度 / 版面越界与裁切 / 错位区间 / 装饰不压文字 / "
          "图表成比例 / 图表区无错位 / 图片加载 / 页面报错 / logo 不压文字）")
    for n in advisories(measured, spec, tokens):
        print("  ·", n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
