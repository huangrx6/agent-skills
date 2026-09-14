#!/usr/bin/env python3
"""deck-spec.json → HTML（riso 效果）。

两条硬规矩（都是 #73/#74 量出来、并被脚本守着的）：
1. **渲染层不写死任何颜色/参数** —— 全部来自 design-tokens.json，CSS 里只有 var()。
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

    沿用 `check_layout.py` 里那一个的写法与理由：必须把模块注册进 sys.modules
    之后再 exec，否则被加载模块里的 `@dataclass` 会炸 —— dataclasses._is_type 会查
    sys.modules.get(cls.__module__) 并拿到 None，报 "'NoneType' object has no
    attribute '__dict__'"。
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


def halftone(tokens: dict, seed, index: int) -> str:
    """装饰墨块：只放**安全区**（右侧上下角），且把 zone/size 写进标签让校验能复核。

    第一版是四象限随便挑 —— 视觉检查当场抓到它压在标题上 ✗（#76 记下了这件事）。
    现在收成右半边的两个角：左栏是文字栏，墨块永不进栏。
    """
    r = _rng(seed, "half", index)
    size = r.choice([480, 560, 620])
    zone = r.choice(["tr", "br"])          # 只用右侧两角：文字栏在左
    css = {"tr": "right:-60px;top:-40px", "br": "right:-130px;bottom:-140px"}[zone]
    return (f'<div class="halftone" data-zone="{zone}" data-size="{size}" '
            f'style="{css};width:{size}px;height:{size}px;border-radius:50%"></div>')


HEAD = """<!doctype html><html lang="zh"><head><meta charset="utf-8"><title>__TITLE__</title><style>
/* 所有视觉参数都从 design-tokens.json 注入；CSS 里没有一处写死的色值或尺寸 ——
   换色板/换字号只改 token，这里零改动（原型阶段定下的硬规矩）。 */
:root{ __VARS__ }
html,body{margin:0;background:var(--viewer)}
.slide{position:relative;width:1600px;height:900px;background:var(--paper);overflow:hidden;margin:0 auto 36px}
.grain{position:absolute;inset:0;pointer-events:none;opacity:var(--grain-op);
  background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='220' height='220'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='__GRAIN_FREQ__' numOctaves='2'/><feColorMatrix type='matrix' values='0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0'/></filter><rect width='220' height='220' filter='url(%23n)'/></svg>")}
.halftone{position:absolute;background:var(--ink-a);mix-blend-mode:multiply;opacity:.55;
  background-image:radial-gradient(circle,var(--paper) 1.4px,transparent 1.4px);background-size:5px 5px}
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
</style></head><body>
"""


def _riso(text: str, tokens: dict, seed, *parts) -> str:
    dx, dy, rot = misregistration(tokens, seed, *parts)
    style = f"--dx:{dx}px;--dy:{dy}px;--rot:{rot}deg"
    body = html.escape(text)
    return (f'<div class="riso" style="{style}">'
            f'<b class="a">{body}</b><b class="b">{body}</b></div>')


def chart_svg(data: list[dict], unit: str = "") -> str:
    """柱状图：**几何全部由脚本算**，模型只出数据。

    方案里的规矩（第 2 层）：数据图表页 riso 效果适用度低 —— 错位会毁掉可读性。
    所以这里只有**容器**做 riso（半调底纹 + 描边框），柱与刻度保持干净、不带错位。
    柱高与数据成比例是硬要求，且由 check_deck 独立复核（不是靠这里自觉）。
    """
    if not data:
        raise SystemExit("✗ chart 页需要 data: [{label, value}, …]")
    w, h, pad = 1100, 380, 40
    top, base = pad + 46, h - pad - 26
    values = [float(d["value"]) for d in data]
    peak = max(values + [1e-9])
    span = (w - 2 * pad) / len(data)
    bar_w = span * 0.52
    parts = [f'<svg viewBox="0 0 {w} {h}" role="img">',
             f'<div class="hf"></div>',
             f'<line class="axis" x1="{pad}" y1="{base}" x2="{w - pad}" y2="{base}"/>']
    for i, d in enumerate(data):
        height = (base - top) * float(d["value"]) / peak           # 按峰值归一
        x = pad + span * i + (span - bar_w) / 2
        y = base - height
        parts.append(f'<rect class="bar" x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{height:.1f}"/>')
        parts.append(f'<text class="val" x="{x + bar_w / 2:.1f}" y="{y - 10:.1f}" '
                     f'text-anchor="middle">{d["value"]}{unit}</text>')
        parts.append(f'<text class="lbl" x="{x + bar_w / 2:.1f}" y="{base + 26:.1f}" '
                     f'text-anchor="middle">{html.escape(str(d["label"]))}</text>')
    parts.append("</svg>")
    return '<div class="chartwrap"><div class="hf"></div>' + "".join(parts) + "</div>"



def render(deck_spec: dict, tokens: dict) -> str:
    deck = deck_spec["deck"]
    seed = deck.get("seed", 1)
    colors = tokens["colorSets"][deck["colorSet"]]
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

    out = [head]
    for i, slide in enumerate(deck["slides"], 1):
        kind = slide.get("type")
        out.append('<section class="slide">')
        if kind in ("title", "content-text", "end", "chart"):   # 图文/双栏/时间线页自带色彩，不加装饰墨块
            out.append(halftone(tokens, seed, i))
        out.append('<div class="pad">')
        if kind == "title":
            out.append(f'<div style="--riso-size:152px;height:158px">{_riso(slide["title"], tokens, seed, "t", i)}</div>')
            if slide.get("subtitle"):
                out.append(f'<div class="sub">{html.escape(slide["subtitle"])}</div>')
            out.append('<div class="rule"></div>')
        elif kind == "content-text":
            out.append(f'<div style="--riso-size:86px;height:104px;margin-bottom:64px">'
                       f'{_riso(slide["title"], tokens, seed, "t", i)}</div>')
            items = "".join(f'<li><i>■</i>{html.escape(b)}</li>' for b in slide.get("bullets", []))
            out.append(f'<ul class="bullets">{items}</ul>')
        elif kind == "content-image":
            out.append(f'<div style="--riso-size:72px;height:88px">{_riso(slide["title"], tokens, seed, "t", i)}</div>')
            items = "".join(f'<li><i>■</i>{html.escape(b)}</li>' for b in slide.get("bullets", []))
            out.append('<div class="two"><div class="main">'
                       f'<ul class="bullets">{items}</ul></div>'
                       f'<figure class="imgwrap"><img src="{html.escape(slide["image"])}" alt=""></figure></div>')
        elif kind == "two-column":
            out.append(f'<div style="--riso-size:72px;height:88px">{_riso(slide["title"], tokens, seed, "t", i)}</div>')
            cols = []
            for ci, col in enumerate(slide.get("columns", [])[:2]):
                li = "".join(f'<li><i>■</i>{html.escape(b)}</li>' for b in col.get("bullets", []))
                band = "ink-a" if ci == 0 else "ink-b"   # 两专色只做栏标色带；正文仍用叠印墨（荧光色载不住文字）
                cols.append(f'<div class="col"><div class="band {band}"></div>'
                            f'<h3>{html.escape(col.get("title", ""))}</h3>'
                            f'<ul class="bullets small">{li}</ul></div>')
            out.append('<div class="cols">' + "".join(cols) + "</div>")
        elif kind == "timeline":
            out.append(f'<div style="--riso-size:72px;height:88px">{_riso(slide["title"], tokens, seed, "t", i)}</div>')
            nodes = []
            for ni, node in enumerate(slide.get("nodes", []), 1):
                dx, dy, _ = misregistration(tokens, seed, "dot", i, ni)   # 每个时间点独立错位
                nodes.append(f'<li><span class="dot" style="--ddx:{dx}px;--ddy:{dy}px"></span>'
                             f'<b>{html.escape(node.get("label", ""))}</b>'
                             f'<em>{html.escape(node.get("note", ""))}</em></li>')
            out.append('<ol class="tl">' + "".join(nodes) + "</ol>")
        elif kind == "end":
            out.append(f'<div class="end" style="--riso-size:180px">'
                       f'{_riso(slide["title"], tokens, seed, "t", i)}</div>')
        elif kind == "chart":
            out.append(f'<div style="--riso-size:72px;height:88px">{_riso(slide["title"], tokens, seed, "t", i)}</div>')
            out.append(chart_svg(slide.get("data", []), slide.get("unit", "")))
            if slide.get("caption"):
                out.append(f'<div class="chartcap">{html.escape(slide["caption"])}</div>')
        else:
            raise SystemExit(f"✗ 未知版式 type={kind!r}（支持 title / content-text / content-image / "
                             f"two-column / timeline / chart / end）")
        out.append("</div>")
        out.append(f'<div class="foot">{html.escape(deck.get("title", ""))} / {i:02d}</div>')
        out.append('<div class="grain"></div>')
        out.append("</section>")
    out.append("</body></html>")
    return "\n".join(out)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="deck-spec.json → HTML（riso 效果）")
    ap.add_argument("spec")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--tokens", default=TOKENS)
    args = ap.parse_args(argv[1:])
    with open(args.spec, encoding="utf-8") as fh:
        deck_spec = json.load(fh)
    with open(args.tokens, encoding="utf-8") as fh:
        tokens = json.load(fh)
    page = render(deck_spec, tokens)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(page)
    print(f"✓ 已写出 {args.out}（{len(page)} 字节 / {len(deck_spec['deck']['slides'])} 页）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
