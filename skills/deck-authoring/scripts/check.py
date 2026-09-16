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
7. 图表就绪 数据形状对（label 非空 / value 是数字）+ G2 真渲染出来了（实测）
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
deck_mod = _load_sibling("deck")       # 品牌资产 + 编译（原 brand/compile）
grid_mod = _load_sibling("grid")     # 网格与间距（版面几何唯一来源）


def _load_layout():
    """加载 ``layout/`` 包（模型 + 碰撞政策）。加载法与 _load_sibling 同源；
    包的 ``__init__`` 自己设 ``__path__``，子模块由它动态拉起。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "layout", "__init__.py")
    pkg_spec = importlib.util.spec_from_file_location("_deck_layout", path)
    if pkg_spec is None or pkg_spec.loader is None:
        raise RuntimeError(f"加载不了 layout 包：{path}")
    module = importlib.util.module_from_spec(pkg_spec)
    sys.modules[pkg_spec.name] = module
    pkg_spec.loader.exec_module(module)
    return module


layout_mod = _load_layout()  # 安全盒碰撞（几何模型 + 政策 + 验收）



# **两个不同的框，别混用**（我自己第一版就混了 ✗，导致正常产物被误判"溢出"）：
#   内容区 = 版面减去内边距，量"放不放得下"（宽 1600-2×84 = 1432）
#   文字栏 = 文字实际占的窄带，只用来判"墨块进没进栏"（更保守）
# 几何从 grid.py 取（**唯一来源**）。这里曾手写过 (…, 838) —— 与 render.py
# 推导的 824 差 14px：两个"唯一来源"已经漂了才发现（这就是 grid.py 存在的理由）。
CONTENT = (render_mod.PAD_X, render_mod.CONTENT_TOP,
           render_mod.SLIDE_W - render_mod.PAD_X, render_mod.CONTENT_BOTTOM)
TEXT_BAND = (render_mod.PAD_X, render_mod.CONTENT_TOP,
             render_mod.PAD_X + 1000.0, render_mod.CONTENT_BOTTOM - 54.0)
SLIDE_W, SLIDE_H = 1600.0, 900.0
# 内容只占正文带这么少 → 提示“这页几乎没有内容”。
#
# ⚠️ 这个阈值只能抓**近于空的页**，不能拿来判“太稀”。第一版写的是 0.55，
# 结果它在 demo 的 3 个正常页上全部开火（41% / 45% / 37%）—— 而那几页看着
# 一点都不像没做完（左轨 + 实线 + 巨号页码都在）。当初用户抱怨 swiss 第一版
# “下半页 55% 是死的”，真正原因不是内容少，而是**没有构图锚点**；修法也是加锚点，
# 不是加内容。所以：留白是不是问题，取决于风格有没有锚点，**像素密度算不出来**。
# 密度这个量不该在每次校验时拿一个不懂风格的阈值去喷人。
#
# 但仍然要分两层开口（都是提示，不阻塞）：
#   < DEAD_SPACE_NOTE —— 一页几乎什么都没排（通常是漏了条目）
#   < SPARSE_NOTE     —— 下半页空着。这一条是**字号调正之后才看得见**的问题：
#     大字（海报尺度）会把正文带填满，所以“字太大”一直同时意味着“内容不够”；
#     字降下来后，同一页只剩 33~46% 就会现形。实测：把夹具字号从 96/46 降到
#     48/24，第 2~5 页占带量落到 33~46%，下半页整块是死的。
DEAD_SPACE_NOTE = 0.28
SPARSE_NOTE = 0.5

# **一张图覆盖整页** —— 禁止。
#
# 为什么是禁止而不是提示：一页的信息（标题 / 条目 / 数字 / 示意）一旦被画进图里，
# 它就同时失去了可编辑、可搜索、可翻译、可被读屏器读这四件事；而"对方要改字"
# 正是本 skill 出原生 PPTX 的理由。图在版面上的角色有三种：**配图**（占一栏）、
# **点缀**（更小）、**主角**（hero 变体：满幅图 + 标题/条目仍是真 DOM 文本 ——
# "信息烤进图里"的禁止不适用，见 _check_full_page_image 的 role-aware 分支）。
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


def _check_full_page_image(measured: dict, deck: dict) -> list[str]:
    """一张图盖住整页 —— **阻塞**，但对 hero 布局 role-aware（见注释）。

    为什么这条要有牙：它是"不要把所有东西都生成到一张图上、再让图片覆盖整页"这条
    硬规则的落点。**role-aware 之后它可达了**：hero 布局的无条目形态图占整页 64%
    —— 那一页图就是主角，且标题/条目仍是真 DOM 文本，四失禁止不适用。但守卫
    对其余一切照旧：手改 skin 把配图撑到全页、或者哪个新变式忘了声明角色，
    这条会失败。logo 永远不放行（品牌标盖满整页没有合法场景）。
    """
    out: list[str] = []
    total = render_mod.SLIDE_W * render_mod.SLIDE_H
    if not total:
        return out
    hero_pages = {
        i for i, s in enumerate(deck.get("slides", []), 1)
        if s.get("type") == "content-image" and s.get("layout") == "hero"}
    for el in measured.get("elements", []):
        if el.get("role") not in ("logo", "image"):
            continue
        if el.get("role") == "image" and el.get("slide") in hero_pages:
            continue          # hero：图是主角，信息没烤进图里
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


def _check_grid_alignment(measured: dict) -> list[str]:
    """**锚点元素必须吸附到网格列**（提示级）。

    只查结构锚点（标题 / 副标题 / 栏题 / 图 / 图表）：它们的左缘应当在边距或某个
    列起点上。列表条目不查 —— 有的风格给条目做悬挂缩进（paper-ink 的破折号缩进
    68/82px），那是版式语言不是失对齐。logo 也不查：位置是各风格自己定的。

    为什么是提示：skin 可以有正当理由偏移（比如装饰性出血），拿它挡交付会把
    有意的偏移当成错误。但它得开口 —— 网格是"整齐"的地基，吸没吸上要看得见。

    实测改网格前：左缘出现 7 个任意值（418/752/800/909/1086/1281/84）；
    改后全部落在列上（84 / 448=col4 / 812=col7 / 933=col8 / 1176=col10）。
    """
    anchors = ("title", "subtitle", "image", "chart")
    starts = [round(v, 1) for v in grid_mod.column_starts()]
    off: list[tuple[int, float, str]] = []
    for el in measured.get("elements", []):
        if el.get("role") not in anchors:
            continue
        slide_no = el.get("slide")
        x = el.get("x")
        # 数字由 measure.py 写出来；不是数字就跳过，不抛 —— check() 从不抛
        # （与 _check_full_page_image / hierarchy.weights 同一个写法）。
        if not isinstance(slide_no, int) or not isinstance(x, (int, float)):
            continue
        if grid_mod.snap(x) is None:
            off.append((slide_no, x, str(el.get("role"))))
    if not off:
        return []
    head = "、".join(f"第{s}页 {r}（x={x:.0f}）" for s, x, r in off[:4])
    return [f"有 {len(off)} 个锚点元素的左缘没吸附到网格列：{head}"
            f" —— 列起点是 {starts[:6]}…（见 grid.py）。网格对齐是「整齐」的地基；"
            f"若是风格有意的偏移（悬挂缩进/出血），可以忽略这条"]


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


# ── 字号体检的四条线 ────────────────────────────────────────────────
# 依据是画布几何本身，不是审美偏好：1600×900，正文带 = 900−132(上边)−52(下边距)
# −24(页脚) = 692px（grid.py）。四条线各自对应一类实测过的失败：
#
#   TITLE_POSTER_PX —— 内页标题用了**封面尺度**。128/96 那种数是给一页一句话的
#     封面/宣言页准备的；内页照抄它，每页都像标题页：读起来累、信息密度反而低。
#     内页标题的合理区是 40~56。
#   BODY_DENSE_PX —— **一页 4 条以上还用宣言档正文**。大字配 1~2 条是气质，
#     配 4~6 条是挤：行距被压、目光没有落点，观众不知道该先看哪条。
#   BODY_MEDIAN_PX —— 内页正文档的推荐区间（观众距离 = 笔记本/一臂之内；
#     投影到 3m 外才需要整体加 6~8px）。上限管“整体偏大”，下限管“整体偏小
#     到看不清”—— 两头都会出现，所以两头都报。
TITLE_POSTER_PX = 72
BODY_DENSE_PX = 30
BODY_MEDIAN_PX = (20, 28)

# 封面 / 封底用大字号是**对的**，不体检这两类版式的标题。
TITLE_SIZE_EXEMPT = frozenset({"title", "end"})


def _tier_of(tokens: dict | None, px: float) -> str:
    """这个像素值来自哪一档（给修法用）。改字号要去 style 的 type 里改，
    所以提示里必须点名是哪一档 —— 只报“96px 太大”，作者得自己反查。"""
    if not isinstance(tokens, dict):
        return ""
    tiers = tokens.get("type")
    if not isinstance(tiers, dict):
        return ""
    hits = [k for k, v in tiers.items() if isinstance(v, (int, float)) and v == px]
    return f"（= type.{hits[0]}）" if hits else ""


def _check_type_size(measured: dict, deck: dict, tokens: dict | None) -> list[str]:
    """字号体检（**提示**，不阻塞）。

    为什么提示而不是阻塞：字号是设计决定，大字放在宣言页上完全正确；脚本只该把
    “这页的字号跟你这页的内容量明显不搭”说出来，不该替作者拍板。但**必须开口** ——
    这正是“每份 deck 字号都偏大”能长期存在的原因：装得下就没人报错。

    判据全部来自实测（`measure.py` 的 fontSize / role / slide），不读 style 的意图值：
    意图和实际渲染对不上时，要看的是观众看到的那一个。
    """
    # 位置与键名照 spec 的真实形状：slides 在 deck 下，版式键是 type（不是 layout）。
    # 第一版写成 spec["slides"]，取不到就直接返回空 —— 整个体检静默失效。这正是
    # 本仓库反复踩的坑：**取不到数据时不报错就等于没做**。
    slides = deck.get("slides")
    if not isinstance(slides, list):
        return []
    layouts: dict[int, str] = {}
    for i, sl in enumerate(slides, start=1):
        if isinstance(sl, dict):
            layouts[i] = str(sl.get("type") or "content-text")
    # 按页收：标题字号 / 条目字号 / 条目数
    titles: dict[int, float] = {}
    bodies: dict[int, list[float]] = {}
    for el in measured.get("elements", []):
        slide_no, role, px = el.get("slide"), el.get("role"), el.get("fontSize")
        if not isinstance(slide_no, int) or not isinstance(px, (int, float)) or px <= 0:
            continue
        if role == "title":
            titles[slide_no] = max(titles.get(slide_no, 0.0), px)
        elif role == "bullet":
            bodies.setdefault(slide_no, []).append(px)
    notes: list[str] = []
    # ① 内页标题用了封面尺度
    big_titles = [
        (n, px) for n, px in sorted(titles.items())
        if px >= TITLE_POSTER_PX and layouts.get(n) not in TITLE_SIZE_EXEMPT
    ]
    if big_titles:
        head = "、".join(f"第{n}页 {px:.0f}px{_tier_of(tokens, px)}" for n, px in big_titles[:4])
        notes.append(
            f"内页标题是封面尺度：{head}（共 {len(big_titles)} 页超过 {TITLE_POSTER_PX}px）—— "
            f"内页标题的合理区是 40~56px。层级靠**标题与正文的倍数**（2~3 倍）立住，"
            f"不靠绝对值堆大；改 style 的 type.compact / type.small")
    # ② 条目多还用宣言档
    dense = [
        (n, max(pxs), len(pxs)) for n, pxs in sorted(bodies.items())
        if len(pxs) >= 4 and max(pxs) > BODY_DENSE_PX
    ]
    if dense:
        head = "、".join(f"第{n}页 {cnt}条×{px:.0f}px" for n, px, cnt in dense[:4])
        notes.append(
            f"条目多但用的是宣言档字号：{head} —— 大字配 1~2 条是气质，配 4 条以上就挤"
            f"（行距被压、目光没落点）。这一页要么降档（type.bullet / type.bulletSmall），"
            f"要么拆页")
    # ③ 整体偏大 / 偏小：按**条目**取中位数（不是每页取最大值再取中位）——
    # 宣言页是少数派：一页 2 条×46px 不该把整体结论顶成“偏大”。中位数按条目数
    # 加权后，
    # 只有“大多数条目都大”才会报，那才是真的整体偏大。
    per_bullet = sorted(px for pxs in bodies.values() for px in pxs)
    if per_bullet:
        mid = per_bullet[len(per_bullet) // 2]
        lo, hi = BODY_MEDIAN_PX
        if mid > hi:
            notes.append(
                f"内页正文整体偏大：中位数 {mid:.0f}px{_tier_of(tokens, mid)}（推荐 {lo}~{hi}px）"
                f"—— 1600×900 上正文超过 {hi}px，一页就装不下几句话，密度会掉。"
                f"想保留大字就减少每页内容，否则把 type.bullet 降下来")
        elif mid < lo:
            notes.append(
                f"内页正文整体偏小：中位数 {mid:.0f}px{_tier_of(tokens, mid)}（推荐 {lo}~{hi}px）"
                f"—— 一臂之内都得费劲看。改 type.bullet / type.bulletSmall")
    return notes


def _check_font_fallback(measured: dict) -> list[str]:
    """字体回退**提示**（不判失败）—— 而且要说清楚**谁顶上了**。"

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
    brand = deck_mod.load(name)
    # v5：不再有"演示品牌"提示 —— 仓库里已经没有任何示例品牌可被误用
    # （那份 example/ACME 被真用进过交付，所以连示例一起删了）。
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

    paper = tokens["colorSets"].get(
        render_mod.resolve_color_set(tokens, deck), {}).get("background", "#FFFFFF")
    if deck_mod.is_dark_paper(paper) and not brand.get("logoInverse"):
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


# 有结构布局的版式（提示轮换用；布局词表由作者/风格定，渲染器只认结构能力）
LAYOUT_TYPES = ("content-image", "two-column")


def _layout_rotation_notes(deck: dict) -> list[str]:
    """同型页连排且布局一个不换 → 提示轮换（构图节奏的可测代理）。

    反 slop 清单第一条就是"每页同构图"。同 type 连排本身合法（对比页天然
    成对），但布局全相同是把同一张构图复印几遍 —— hero/镜像/均分这些零成本
    换法都不用，多半是写 spec 时不知道布局存在（提示里直接指路 SKILL.md）。
    纯函数：只看 spec。
    """
    out: list[str] = []
    slides = deck.get("slides", [])
    start = 0
    for i in range(1, len(slides) + 1):
        # 段尾判定：i 越界，或 (type, layout) 对不同 → 收一段
        if i < len(slides):
            a, b = slides[i - 1], slides[i]
            if (a.get("type") == b.get("type")
                    and a.get("layout") == b.get("layout")):
                continue
        kind = slides[start].get("type")
        n = i - start
        if n >= 2 and kind in LAYOUT_TYPES:
            out.append(f"第 {start + 1}~{i} 页连排 {n} 个 {kind} 且布局全相同"
                       f"（{slides[start].get('layout') or '缺省'}）—— 连排同型页"
                       f"请换布局换构图节奏（结构布局与自造布局见 SKILL.md 版式表）")
        start = i
    return out


def _layout_vocab_problems(deck: dict, tokens: dict, slides: list) -> list[str]:
    """布局词表验收：风格在 style.json 声明 layouts 时，spec.layout 必须落在词表里。

    v3 的纪律：**作者自己封闭自己的词表**（风格声明它认哪些布局名）——
    脚本不再有一张全局枚举，但拼写错误仍然当场拦（自造名写错一个字母，
    skin 里那条规则就永远不生效，最难查的那种静默）。
    """
    vocab = tokens.get("layouts")
    if not isinstance(vocab, list) or not vocab:
        return []
    allowed = set(vocab) | set(render_mod.IMAGE_LAYOUTS) | set(render_mod.TWO_COL_LAYOUTS)
    out: list[str] = []
    for i, s in enumerate(slides, 1):
        lay = s.get("layout")
        if isinstance(lay, str) and lay and lay not in allowed:
            out.append(f"第 {i} 页 layout={lay!r} 不在风格的 layouts 词表里"
                       f"（{vocab}）—— 拼写错误会让 skin 里那条规则永远不生效")
    return out


def _tier_notes(deck: dict) -> list[str]:
    """字号档提示：条目多的 content-text 页在缺省档下会偏挤。

    v3 起**没有按条数自动降档** —— 档位由作者声明（slide.bulletTier 或
    风格 bulletDefault）。这里只在"条目多 + 没显式声明档位"时提示一声：
    内容多就拆页 / 收短，或显式写一个小档，别让字自己变小。
    纯函数：只看 spec，不碰测量。
    """
    out: list[str] = []
    for i, s in enumerate(deck.get("slides", []), 1):
        if s.get("type") != "content-text" or s.get("bulletTier"):
            continue
        n = len(s.get("bullets") or [])
        if n > 5:
            out.append(f"第 {i} 页 {n} 条且未声明 bulletTier —— 缺省档下会偏挤。"
                       f"先考虑拆页 / 收短（缩字号是修复顺序第 13 位）；"
                       f"确实要小字就显式写 bulletTier: \"bulletSmall\"")
    return out


def _check_deck_shape(measured: dict, deck: dict,
                      tokens: dict | None = None) -> tuple[list[str], list[str]]:
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

    # 档位提示（纯函数抽出，便于单测）：风格/作者声明档位，脚本不再自动升降。
    notes.extend(_tier_notes(deck))
    notes.extend(_layout_rotation_notes(deck))
    problems.extend(_layout_vocab_problems(deck, tokens or {},
                                           deck.get("slides", [])))

    # 版式单一：全是一种版式时，视线没有落点变化。
    content_kinds = [k for k in kinds if k not in ("title", "end")]
    if len(set(content_kinds)) == 1 and len(content_kinds) >= 3:
        notes.append(
            f"{len(content_kinds)} 页内容全是一种版式（{content_kinds[0]}）—— "
            f"构图没有变化。换一页的 layout（结构布局或自造布局），或把其中几页拆/并")

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
    sparse: list[tuple[int, float]] = []
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
                f"一页只有标题没条目通常是漏了；确实要留白就删掉这页")
        elif used < SPARSE_NOTE:
            sparse.append((i, used))
    # 汇总成一条：一页一条会变成唠叨，唠叨会让人整体忽略提示
    if sparse:
        where = "、".join(f"第{i}页 {u:.0%}" for i, u in sparse[:5])
        more = "" if len(sparse) <= 5 else f" 等 {len(sparse)} 页"
        notes.append(
            f"下半页空着：{where}{more}（占正文带不到 {SPARSE_NOTE:.0%}）—— "
            f"这是把字号降下来之后才看得见的问题：大字在填满正文带，所以“字太大”"
            f"常常同时意味着“内容不够”。补内容 / 换更饱满的版式（双栏、图、大数字）"
            f"／确实要留白就接受，但别让它成为默认")
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
    return render_mod.load_style(spec["deck"].get("style"))["tokens"]


def check(spec: dict, html_path: str, tokens: dict | None = None,
          measured: dict | None = None) -> list[str]:
    """跑全部阻塞检查，返回问题清单（空的 = 全过）。

    `tokens=None` 时按 spec 里的风格去加载 —— 调用方多数情况下不该手递 token。
    """
    tokens = style_tokens(spec, tokens)
    problems: list[str] = []
    page = deckio.read_text(html_path)      # 读一次就够（以前读了三次）
    deck = spec["deck"]
    colors = tokens["colorSets"][render_mod.resolve_color_set(tokens, deck)]
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
    problems.extend(_check_full_page_image(data, deck))
    brand_problems, _ = _check_brand(data, deck, tokens)
    problems.extend(brand_problems)
    # 空内容与品牌无关，但它和越界一样是“一页看着坏了”—— 所以也走阻塞
    problems.extend(_check_empty_content(deck))
    # ⑥ 安全盒碰撞：不同视觉组之间，安全盒相交即违规（deny 默认）。
    # 判据全来自实测元素盒 + layout 包的安全距离表；「图表本体没撞、
    # 标签撞了」「图片没撞、caption 撞了」这两类以前全是沉默的。
    hero_pages = frozenset(
        i for i, s in enumerate(deck.get("slides", []), 1)
        if isinstance(s, dict) and s.get("layout") == "hero")
    for v in layout_mod.collision.violations(
            layout_mod.collision.build_boxes(data.get("elements", [])), hero_pages):
        problems.append(
            f"第 {v['slide']} 页 {v['a']} 与 {v['b']} 太近"
            f"（{v['group']}：需要 ≥{v['required']:.0f}px，实际 {v['actual']:.0f}px）—— "
            f"安全盒相交按重叠处理；要么拉开间距（父容器 gap 档），要么这页内容该拆")
    # 布局词表：风格声明了 layouts 时，spec 里拼错的布局名当场拦（v3 起布局是
    # 自由字符串，拼错会让 skin 里那条规则永远不生效 —— 最难查的那种静默）。
    problems.extend(_layout_vocab_problems(deck, tokens, deck.get("slides", [])))

    for i, slide in enumerate(deck["slides"], 1):
        declared = slide.get("color")
        if declared and declared != "overprint":
            problems.append(f"第 {i} 页 声明 color={declared!r} —— 主/副色不能承载文字，只允许 overprint")

    # ④ 图表：**G2 就绪 + 数据形状**（v4 —— 图表改由 AntV G2 渲染）
    #
    # 为什么不检查"柱高与数据成比例"了：那条门是为**手写 SVG 渲染器**设的
    # （我们自己算柱高，就得自己复核）。v4 起几何由 G2 的编码算 —— 再量它的
    # 像素等于用手量尺子。换成的两件事：
    #   a) G2 真的渲染出来了（容器里有 canvas/svg，且没有 data-chart-error）；
    #   b) 数据本身是对的（label 非空、value 是数字）—— 数据错才是真错。
    sections = page.split('<section class="slide"')[1:]
    for i, slide in enumerate(deck["slides"], 1):
        if slide.get("type") != "chart":
            continue
        block = sections[i - 1] if i - 1 < len(sections) else ""
        for k, d in enumerate(slide.get("data", [])):
            if not str(d.get("label", "")).strip():
                problems.append(f"第 {i} 页图表 data[{k}].label 是空的 —— 轴上会缺一个标签")
            _num(str(d.get("value")), f"第 {i} 页图表 data[{k}].value", problems)
        # 就绪看**实测**（静态 HTML 里只有容器与 spec，判断不出来）
        measured_chart = next((e for e in data.get("elements", [])
                               if e.get("slide") == i and e.get("id") == f"s{i}.chart"), None)
        state = (measured_chart or {}).get("chartReady")
        if state and state.startswith("error"):
            problems.append(f"第 {i} 页图表：G2 渲染失败（{state.split(':', 1)[1]}）"
                            f" —— 产物里那一页是空的")
    # ④ 图表区无错位：**逐层配对**扫整个容器，不是扫到第一个 </div> 就停。
    for hit in re.finditer(r'<div class="chartwrap"', page):
        block = _div_subtree(page, hit.start())
        if "riso" in block:
            problems.append("图表容器里出现了错位叠印元素（riso 只允许做容器与背景，不能进图表区）")

    # ③ 错位区间：读产物里真正写进去的值（misregistration 是可选 effect ——
    # 没声明的风格 dx/dy/rot 全 0，区间无从对起，跳过不查）
    m = tokens.get("misregistration") or {}
    hits = re.findall(r"--dx:([-\d.]+)px;--dy:([-\d.]+)px;--rot:([-\d.]+)deg", page) if m else []
    for dx, dy, rot in hits:
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
    notes.extend(_check_grid_alignment(measured))
    if spec is not None and tokens is not None:
        _, brand_notes = _check_brand(measured, spec.get("deck", {}), tokens)
        notes.extend(brand_notes)
        _, shape_notes = _check_deck_shape(measured, spec.get("deck", {}), tokens)
        notes.extend(shape_notes)
        # 字号体检：这是“每份 deck 字号都偏大”唯一能被当场看见的地方 ——
        # 装得下就不报错，所以以前没有任何一条会开口。
        notes.extend(_check_type_size(measured, spec.get("deck", {}), tokens))
        # 信息层级（文本预算 / 焦点 / 密度）那三条曾由 hierarchy.py 提供，v4 随
        # 该模块一起退役：阈值取决于语境（封面就该空、看板就该满），做成阻塞会
        # 把第一份正常的 deck 挡住；而**装不装得下**这件事已由 measure 实测那两道
        # （越界 / 裁切）定死。腾出的「构图节奏」类提示保留在 _layout_rotation_notes。
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
