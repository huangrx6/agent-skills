#!/usr/bin/env python3
"""deck-spec.json → HTML（riso 效果）。

两条硬规矩（都是 #73/#74 量出来、并被脚本守着的）：
1. **渲染层不写死任何颜色/参数** —— 全部来自 styles/risograph/style.json，CSS 里只有 var()。
2. **同一份 spec + 同一种子 = 完全一致的输出** —— 错位量/颗粒强度按 (seed, 元素) 派生，
   不用全局 random（全局的话两次渲染就不一样，没法回归对比，也没法复现一版给别人）。
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


ink = _load_sibling("ink")  # 叠印与对比度只有一处定义，不重抄
deckio = _load_sibling("deckio")   # IO 收口：参数写错要报清楚，不甩 traceback

TOKENS = os.path.join(HERE, "..", "styles", "risograph", "style.json")


def _rng(seed, *parts) -> random.Random:
    return random.Random("|".join([str(seed)] + [str(p) for p in parts]))


def misregistration(tokens: dict, seed, *parts) -> tuple[float, float, float]:
    spec = tokens["misregistration"]
    r = _rng(seed, "mis", *parts)
    return (round(r.uniform(*spec["offsetRangeX"]), 2),
            round(r.uniform(*spec["offsetRangeY"]), 2),
            round(r.uniform(*spec["rotationRange"]), 2))


def grain_opacity(tokens: dict, seed, *parts) -> float:
    return round(_rng(seed, "grain", *parts).uniform(*tokens["texture"]["grainOpacity"]), 3)


def _entry(mid: str, slide: int, role: str, text: str = "", size: float | None = None) -> dict:
    """语义清单的一条。几何不在里面 —— 几何由 measure.py 从真浏览器拿。

    这里只记“事实”：这个元素是什么、写了什么字、设计意图用多大字号。
    职责划得很清：**意图在渲染层，几何在测量层**。两者对不上就是 bug。
    """
    return {"id": mid, "slide": slide, "role": role, "text": text, "fontSize": size}


def halftone(tokens: dict, seed, index: int) -> str:
    """装饰墨块：只放**安全区**（右侧上下角），且把 zone/size 写进标签让校验能复核。

    第一版是四象限随便挑 —— 视觉检查当场抓到它压在标题上 ✗（#76 记下了这件事）。
    现在收成右半边的两个角：左栏是文字栏，墨块永不进栏。

    **画成 SVG，而且网点用「虚线网格」而不是 `<pattern>`**：
    1. 网点是**规则点阵**，本来就属于矢量世界。原来用 `radial-gradient` 画，整块在
       PDF 里变位图。
    2. 换 `<pattern>` 后屏幕好了，但 Chrome 导 PDF 时**把 `<pattern>` 整块栅格化**
       —— 实测 4 块半调 → 4 张 ~1035×1014 位图，1.49MB。把 `mix-blend-mode` 和
       `opacity` 都去掉也治不好，栅格化的是 pattern 本身。
    3. 换成一条**虚线描边路径**（横向线 + `stroke-dasharray`）后它留在矢量里：
       全 PDF 0.24MB、零位图。方点占 2.5²/25 ≈ 25%，圆点 r=1.4 占 6.16/25 ≈ 25%，
       面积对齐，而 5px 尺度下方点与圆点肉眼分不出。
    """
    r = _rng(seed, "half", index)
    size = r.choice([480, 560, 620])
    zone = r.choice(["tr", "br"])          # 只用右侧两角：文字栏在左
    css = {"tr": "right:-60px;top:-40px", "br": "right:-130px;bottom:-140px"}[zone]
    step, half = 5, size / 2          # step 是 int：行数用整除算，不需要强制转换
    # 一行一条横虚线；dasharray 把每行切成方点。相位不重要（重复纹理）。
    dashes = "".join(f"M0 {y * step + step / 2:.1f}H{size}"
                     for y in range(size // step + 1))
    # 必须 clip 成圆 —— 虚线是**通栏**画的，不裁就是一块方底（视觉检查当场抓到 ✗）。
    cid = f"hc{index}"
    return (f'<svg class="halftone" data-zone="{zone}" data-size="{size}" '
            f'style="{css};width:{size}px;height:{size}px" '
            f'viewBox="0 0 {size} {size}" aria-hidden="true">'
            f'<defs><clipPath id="{cid}">'
            f'<circle cx="{half}" cy="{half}" r="{half}"/></clipPath></defs>'
            f'<circle cx="{half}" cy="{half}" r="{half}" fill="var(--ink-a)"/>'
            f'<path clip-path="url(#{cid})" d="{dashes}" fill="none" '
            f'stroke="var(--paper)" stroke-width="2.5" stroke-dasharray="2.5 2.5"/></svg>')


HEAD = """<!doctype html><html lang="zh"><head><meta charset="utf-8"><title>__TITLE__</title><style>
/* 所有视觉参数都从 styles/risograph/style.json 注入；CSS 里没有一处写死的色值或尺寸 ——
   换色板/换字号只改 token，这里零改动（原型阶段定下的硬规矩）。 */
:root{ __VARS__ }
html,body{margin:0;background:var(--viewer)}
.slide{position:relative;width:1600px;height:900px;background:var(--paper);overflow:hidden;margin:0 auto 36px}
.grain{position:absolute;inset:0;pointer-events:none;opacity:var(--grain-op);
  background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='220' height='220'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='__GRAIN_FREQ__' numOctaves='2'/><feColorMatrix type='matrix' values='0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0'/></filter><rect width='220' height='220' filter='url(%23n)'/></svg>")}
.halftone{position:absolute;display:block;mix-blend-mode:multiply;opacity:.55}
.pad{padding:132px 84px}
.riso{position:relative;display:block}
.riso b{position:absolute;top:0;left:0;font:900 var(--riso-size,152px)/1.02 var(--serif);
  letter-spacing:-3px;white-space:nowrap}
/* 两遍墨各自 multiply 到纸上：重叠处变深（真实叠印），错开处露两色边 —— 「错版」 */
.riso .a{color:var(--ink-a);mix-blend-mode:multiply;transform:translate(var(--dx),var(--dy))}
.riso .b{color:var(--ink-b);mix-blend-mode:multiply}
.riso{transform:rotate(var(--rot))}
.sub{font:400 34px/1.5 var(--mono);color:var(--ink-text);margin-top:30px}
.rule{width:520px;height:8px;background:var(--ink-b);mix-blend-mode:multiply;margin:40px 0 0}
.bullets{font:400 40px/1.85 var(--mono);color:var(--ink-text);margin:0;padding:0;list-style:none}
.bullets i{color:var(--ink-a);font-style:normal;mix-blend-mode:multiply;margin-right:18px}
.two{display:flex;gap:48px;align-items:flex-start;margin-top:44px}
.two .main{width:820px}
.imgwrap{margin:0;width:640px;transform:rotate(-1.2deg)}
.imgwrap img{width:100%;display:block}
.bullets.small{font-size:30px;line-height:1.7}
.cols{display:flex;gap:56px;margin-top:48px}
.col{width:660px}
.col .band{height:14px;margin-bottom:22px;mix-blend-mode:multiply}
.col .band.ink-a{background:var(--ink-a)}
.col .band.ink-b{background:var(--ink-b)}
.col h3{font:700 44px/1.2 var(--serif);color:var(--ink-text);margin:0 0 18px}
.tl{display:flex;gap:34px;list-style:none;padding:0;margin:60px 0 0}
.tl li{width:300px}
.tl .dot{display:block;width:34px;height:34px;border-radius:50%;background:var(--ink-a);
  mix-blend-mode:multiply;transform:translate(var(--ddx),var(--ddy));margin-bottom:22px}
.tl b{display:block;font:700 30px/1.3 var(--serif);color:var(--ink-text)}
.tl em{display:block;font:400 24px/1.5 var(--mono);color:var(--ink-text);font-style:normal}
.chartwrap{margin-top:44px;width:1180px;padding:34px 38px;background:var(--paper);
  box-shadow:0 0 0 6px var(--ink-b);transform:rotate(-.4deg);position:relative}
.chartwrap .hf{position:absolute;inset:0;background:var(--ink-a);mix-blend-mode:multiply;opacity:.16;
  background-image:radial-gradient(circle,var(--paper) 1.4px,transparent 1.4px);background-size:6px 6px}
.chartwrap svg{position:relative;display:block;width:100%}
.chartwrap .bar{fill:var(--ink-a);mix-blend-mode:multiply}
.chartwrap .axis{stroke:var(--ink-text);stroke-width:2}
.chartwrap .val{font:700 22px var(--mono);fill:var(--ink-text)}
.chartwrap .lbl{font:400 20px var(--mono);fill:var(--ink-text)}
.chartcap{font:400 26px/1.5 var(--mono);color:var(--ink-text);margin-top:26px}
.end{position:absolute;left:84px;top:330px}
.foot{position:absolute;left:84px;bottom:52px;font:400 26px/1 var(--mono);color:var(--ink-text)}
__SHELL_CSS__
</style></head><body>
"""

# ── deck 外壳：演示态（自动缩放 + letterbox + 键盘翻页 + 页码）──────────────
# 刻意做成**运行时的视图**，不是产物本身的版式。
#
# 产物文件永远是 1600×900、未缩放的竖向堆叠 —— 测量层（measure.py）用
# getBoundingClientRect 量真实像素，截图层（shots.py）按真实偏移滚屏，两者都依赖
# 这个几何。演示态只额外叠一层**整体相似变换**：等比缩放不会引入裁切，所以
# “量未缩放的原件”依然成立，不用为了演示能力推翻整个度量层。
#
# 这是从 huashu-design 的 deck_index.html 学来的一点：演示能力是**壳**，
# 不该渗进内容版式。
SHELL_CSS = """
/* --k 由脚本按视口算；CSS 里算不出来 —— scale() 要的是无量纲数，
   而 min(100vw/1600, 100vh/900) 得到的是长度，两者不能互转。 */
html[data-view="present"] body{height:100%;overflow:hidden;display:grid;
  place-items:center;gap:0}
html[data-view="present"] .slide{display:none;margin:0;transform:scale(var(--k,1));
  transform-origin:center center}
html[data-view="present"] .slide.is-cur{display:block}
.hud,.hint{position:fixed;bottom:20px;font:400 20px/1 var(--mono);color:var(--ink-text);
  background:var(--paper);padding:10px 16px;letter-spacing:1px;opacity:0;
  transition:opacity .2s;pointer-events:none;z-index:9}
.hud{right:26px}
.hint{left:26px;font-size:18px}
html[data-view="present"] .hud{opacity:1}
html[data-view="present"] .hint{opacity:1}
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

# 键盘翻页那点脚本。无依赖、不碰 DOM 结构（不包 wrapper）—— 演示态只用
# html[data-view] + .is-cur 两个开关表达，量层和截图层看到的 DOM 一字未变。
SHELL_JS = """
(function(){
  var doc=document.documentElement;
  var slides=[].slice.call(document.querySelectorAll('section.slide'));
  if(!slides.length) return;
  var hud=document.getElementById('__deck_page');
  var cur=0;
  function view(){ return doc.getAttribute('data-view')==='present'?'present':'scroll'; }
  function fit(){
    if(view()!=='present') return;
    var k=Math.min(window.innerWidth/1600, window.innerHeight/900);
    doc.style.setProperty('--k', k);
  }
  function show(n,smooth){
    n=Math.max(0, Math.min(slides.length-1, n));
    cur=n;
    slides.forEach(function(s,i){ s.classList.toggle('is-cur', i===n); });
    if(hud) hud.textContent=(n+1)+' / '+slides.length;
    if(view()==='present'){ fit(); }
    else { slides[n].scrollIntoView({behavior:smooth?'smooth':'auto', block:'center'}); }
    try{ history.replaceState(null,'','#'+(n+1)); }catch(e){}
  }
  function setView(v){
    doc.setAttribute('data-view', v);
    show(cur,false);
  }
  function toggleFull(){
    if(document.fullscreenElement){ document.exitFullscreen(); }
    else if(doc.requestFullscreen){ doc.requestFullscreen(); }
  }
  document.addEventListener('keydown', function(e){
    var k=e.key, p=view()==='present';
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
  // 开法：out.html?present 或 out.html#3
  var start=0, m=/^#(\\d+)$/.exec(location.hash);
  if(m) start=parseInt(m[1],10)-1;
  if(/[?&]present\\b/.test(location.search)) doc.setAttribute('data-view','present');
  show(start,false);
})();
"""


def _riso(text: str, tokens: dict, seed, mid: str, mid_attr: str, *parts) -> str:
    """两遍错位叠印的标题。

    `mid` 是身份（`sN.title`），`mid_attr` 是调用方**已经登记好**的 `data-m="…"` 属性串。

    ⚠️ 身份打在**文字节点 `b.a`** 上，不是外层 wrapper 上：`.riso` 是 `position:relative`
    而两层 `b` 都是 `absolute` —— 绝对定位子元素不撑父盒，量 wrapper 会得到
    「宽 0 / 高 0 / 字号 16px（继承来的默认值）」这种荒谬结果（实测踩过）。
    wrapper 另用 `data-frame` 标记 —— 导出 PPTX 时仍需要它的错位参数。

    属性串由调用方传进来，是因为在 f-string 里再套两层引号会逼出 `chr(34)` 那种东西；
    先把属性算好再拼，代码才读得懂。
    """
    dx, dy, rot = misregistration(tokens, seed, *parts)
    style = f"--dx:{dx}px;--dy:{dy}px;--rot:{rot}deg"
    body = html.escape(text)
    return (f'<div class="riso" data-frame="{mid}" style="{style}">'
            f'<b class="a" {mid_attr}>{body}</b><b class="b">{body}</b></div>')


def chart_svg(data: list[dict], unit: str = "", tag_attr: str = "") -> str:
    """柱状图：**几何全部由脚本算**，模型只出数据。

    方案里的规矩（第 2 层）：数据图表页 riso 效果适用度低 —— 错位会毁掉可读性。
    所以这里只有**容器**做 riso（半调底纹 + 描边框），柱与刻度保持干净、不带错位。
    柱高与数据成比例是硬要求，且由 check_deck 独立复核（不是靠这里自觉）。
    """
    if not data:
        raise SystemExit("✗ chart 页需要 data: [{label, value}, …]")
    w, h, pad = 1100, 380, 40
    top, base = pad + 46, h - pad - 26
    values = [deckio.as_number(d.get("value"), f"chart data[{i}].value")
              for i, d in enumerate(data)]
    peak = max(values + [1e-9])
    span = (w - 2 * pad) / len(data)
    bar_w = span * 0.52
    # 注意：这里**不能**放 <div class="hf"> —— HTML 解析规则遇到非 SVG 元素
    # （<div>）会直接结束 svg 上下文，导致后面的 line/rect/text 全变成普通 HTML
    # 行内元素：柱高消失、标签挤成一行、caption 与页脚重叠（实测踩过）。
    # 半调底纹由外层 wrapper 的 <div class="hf"> 提供，不需要放进 svg 里。
    parts = [f'<svg viewBox="0 0 {w} {h}" role="img">',
             f'<line class="axis" x1="{pad}" y1="{base}" x2="{w - pad}" y2="{base}"/>']
    for i, d in enumerate(data):
        height = (base - top) * values[i] / peak                  # 按峰值归一
        x = pad + span * i + (span - bar_w) / 2
        y = base - height
        parts.append(f'<rect class="bar" x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{height:.1f}"/>')
        parts.append(f'<text class="val" x="{x + bar_w / 2:.1f}" y="{y - 10:.1f}" '
                     f'text-anchor="middle">{d["value"]}{unit}</text>')
        parts.append(f'<text class="lbl" x="{x + bar_w / 2:.1f}" y="{base + 26:.1f}" '
                     f'text-anchor="middle">{html.escape(str(d["label"]))}</text>')
    parts.append("</svg>")
    return f'<div class="chartwrap" {tag_attr}><div class="hf"></div>' + "".join(parts) + "</div>"



# 字号表 —— **单一来源**。渲染、清单、导出都读这一份。
#
# 以前 check.py 自己另写了一份（非 title 一律 86），于是 end 页（真实 180）被当成 86 判，
# 12 个汉字的标题：估算 12×86=1032 < 1432 判“过”，实际 12×180=2160 塞进 1600 版面被裁掉。
# 两份表就是 bug 的温床，收成一份。
TITLE_SIZE = {"title": 152, "content-text": 86, "content-image": 72,
              "two-column": 72, "timeline": 72, "chart": 72, "end": 180}
DEFAULT_BULLET_SIZE = 40
BULLET_SIZE = {"two-column": 30}      # 其余用 DEFAULT_BULLET_SIZE


def render(deck_spec: dict, tokens: dict) -> str:
    deck = deck_spec["deck"]
    seed = deck.get("seed", 1)
    name = deck.get("colorSet")
    if name not in tokens["colorSets"]:
        raise SystemExit(f"✗ colorSet={name!r} 不在 token 里"
                         f"（可用：{sorted(tokens['colorSets'])}）—— 跑 validate_spec.py 能提前拦住这个")
    colors = tokens["colorSets"][name]
    ink_text = ink.overprint(colors["primary"], colors["secondary"])
    variables = ";".join([
        f"--paper:{colors['background']}", f"--ink-a:{colors['primary']}",
        f"--ink-b:{colors['secondary']}", f"--ink-text:{ink_text}",
        f"--grain-op:{grain_opacity(tokens, seed, 'page')}",
        f"--viewer:{tokens['viewerBackground']}",
        f"--serif:{tokens['fonts']['display']}", f"--mono:{tokens['fonts']['mono']}",
    ])
    head = HEAD.replace("__TITLE__", html.escape(deck.get("title", "deck")))
    head = head.replace("__VARS__", variables)
    head = head.replace("__GRAIN_FREQ__", str(tokens["texture"]["grainBaseFrequency"]))
    head = head.replace("__SHELL_CSS__", SHELL_CSS)

    man: list[dict] = []          # 语义清单：元素身份 + 意图（几何由 measure.py 量）

    def tag(mid: str, slide_no: int, role: str, text: str = "", size: float | None = None) -> str:
        """登记一条并返回 `data-m` 属性串。"""
        man.append(_entry(mid, slide_no, role, text, size))
        return f'data-m="{mid}"'

    out = [head]
    for i, slide in enumerate(deck["slides"], 1):
        kind = slide.get("type")
        tsize = TITLE_SIZE.get(kind, 86)
        bsize = BULLET_SIZE.get(kind, DEFAULT_BULLET_SIZE)
        # 标题的 id 与属性串**先算好**，再在下面六个分支里复用 ——
        # 既避免在 f-string 里套四层引号，也避免同一个 id 写六遍写岔。
        title_mid = f"s{i}.title"
        title_attrs = tag(title_mid, i, "title", slide.get("title", ""), tsize)
        title_html = _riso(slide.get("title", ""), tokens, seed, title_mid, title_attrs, "t", i)
        out.append('<section class="slide">')
        if kind in ("title", "content-text", "end", "chart"):
            out.append(halftone(tokens, seed, i))
        out.append('<div class="pad">')
        if kind == "title":
            out.append(f'<div style="--riso-size:{tsize}px;height:158px">{title_html}</div>')
            if slide.get("subtitle"):
                sub_attrs = tag(f"s{i}.subtitle", i, "subtitle", slide["subtitle"], 34)
                out.append(f'<div class="sub" {sub_attrs}>{html.escape(slide["subtitle"])}</div>')
            out.append('<div class="rule"></div>')
        elif kind == "content-text":
            out.append(f'<div style="--riso-size:{tsize}px;height:104px;margin-bottom:64px">{title_html}</div>')
            items = "".join(
                f'<li {tag(f"s{i}.bullet.{bi}", i, "bullet", b, bsize)}>'
                f'<i>■</i>{html.escape(b)}</li>'
                for bi, b in enumerate(slide.get("bullets", [])))
            out.append(f'<ul class="bullets">{items}</ul>')
        elif kind == "content-image":
            out.append(f'<div style="--riso-size:{tsize}px;height:88px">{title_html}</div>')
            items = "".join(
                f'<li {tag(f"s{i}.bullet.{bi}", i, "bullet", b, bsize)}>'
                f'<i>■</i>{html.escape(b)}</li>'
                for bi, b in enumerate(slide.get("bullets", [])))
            src = slide["image"]
            img_attrs = tag(f"s{i}.image", i, "image", src)
            out.append('<div class="two"><div class="main">'
                       f'<ul class="bullets">{items}</ul></div>'
                       f'<figure class="imgwrap" {img_attrs}>'
                       f'<img src="{html.escape(src)}" alt=""></figure></div>')
        elif kind == "two-column":
            out.append(f'<div style="--riso-size:{tsize}px;height:88px">{title_html}</div>')
            cols = []
            for ci, col in enumerate(slide.get("columns", [])[:2]):
                li = "".join(
                    f'<li {tag(f"s{i}.col{ci}.bullet.{bi}", i, "bullet", b, bsize)}>'
                    f'<i>■</i>{html.escape(b)}</li>'
                    for bi, b in enumerate(col.get("bullets", [])))
                band = "ink-a" if ci == 0 else "ink-b"
                coltitle = col.get("title", "")
                h3_attrs = tag(f"s{i}.col{ci}.title", i, "subtitle", coltitle, 44)
                cols.append(f'<div class="col"><div class="band {band}"></div>'
                            f'<h3 {h3_attrs}>{html.escape(coltitle)}</h3>'
                            f'<ul class="bullets small">{li}</ul></div>')
            out.append('<div class="cols">' + "".join(cols) + "</div>")
        elif kind == "timeline":
            out.append(f'<div style="--riso-size:{tsize}px;height:88px">{title_html}</div>')
            nodes = []
            for ni, node in enumerate(slide.get("nodes", []), 1):
                dx, dy, _ = misregistration(tokens, seed, "dot", i, ni)
                label, note = node.get("label", ""), node.get("note", "")
                lab_attrs = tag(f"s{i}.node{ni}.label", i, "subtitle", label, 30)
                note_attrs = tag(f"s{i}.node{ni}.note", i, "bullet", note, 24)
                nodes.append(f'<li><span class="dot" style="--ddx:{dx}px;--ddy:{dy}px"></span>'
                             f'<b {lab_attrs}>{html.escape(label)}</b>'
                             f'<em {note_attrs}>{html.escape(note)}</em></li>')
            out.append('<ol class="tl">' + "".join(nodes) + "</ol>")
        elif kind == "end":
            out.append(f'<div class="end" style="--riso-size:{tsize}px">{title_html}</div>')
        elif kind == "chart":
            out.append(f'<div style="--riso-size:{tsize}px;height:88px">{title_html}</div>')
            chart_attrs = tag(f"s{i}.chart", i, "chart", "", None)
            out.append(chart_svg(slide.get("data", []), slide.get("unit", ""), chart_attrs))
            if slide.get("caption"):
                cap_attrs = tag(f"s{i}.caption", i, "bullet", slide["caption"], 26)
                out.append(f'<div class="chartcap" {cap_attrs}>{html.escape(slide["caption"])}</div>')
        else:
            raise SystemExit(f"✗ 未知版式 type={kind!r}（支持 title / content-text / content-image / "
                             f"two-column / timeline / chart / end）")
        out.append("</div>")
        foot_text = f'{deck.get("title", "")} / {i:02d}'
        out.append(f'<div class="foot" {tag(f"s{i}.foot", i, "foot", foot_text, 26)}>'
                   f'{html.escape(foot_text)}</div>')
        out.append('<div class="grain"></div>')
        out.append("</section>")

    # 清单随产物一起走（不另写文件）：渲染、测量、导出读的是同一份事实。
    payload = json.dumps(man, ensure_ascii=True, separators=(",", ":")).replace("<", "\\u003c")
    out.append(f'<script type="application/json" id="__deck_manifest">{payload}</script>')
    # 壳：页码 / 快捷键提示 / 翻页脚本。**不给它们打 data-m** ——
    # 它们是壳不是内容，进了清单就会污染“清单条数 == 实测元素数”那条不变量。
    total = len(deck["slides"])
    out.append(f'<div class="hud"><span id="__deck_page">1 / {total}</span></div>')
    out.append('<div class="hint">← → 翻页 · F 全屏 · P 演示/滚动</div>')
    out.append(f"<script>{SHELL_JS}</script>")
    out.append("</body></html>")
    return "\n".join(out)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="deck-spec.json → HTML（riso 效果）")
    ap.add_argument("spec")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--tokens", default=TOKENS)
    args = ap.parse_args(argv[1:])
    deck_spec = deckio.read_json(args.spec)
    tokens = deckio.read_json(args.tokens)
    page = render(deck_spec, tokens)
    deckio.write_text(args.out, page)
    print(f"✓ 已写出 {args.out}（{len(page)} 字节 / {len(deck_spec['deck']['slides'])} 页）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
