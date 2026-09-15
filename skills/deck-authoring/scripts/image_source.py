#!/usr/bin/env python3
"""图片来源：prompt 缓存 → 生图（可选，未配置则跳过）→ **几何色块拼贴**。

为什么默认是色块而不是生图：生图是全流程最慢、最贵、最容易失败的一环（方案第 5 层自己
写的），而方案第一条原则是"视觉效果优先用 CSS/SVG 原生能力，不靠生图模型硬画"。
所以几何色块拼贴在这里是**一等公民**，生图只是一个可选来源 —— 而且两件事必须做到：

1. **降级要说出来**：静默换成色块，用的人会以为图是模型画的 ✗
2. **缓存里的东西也要合规范**：缓存命中不等于可信 —— 上一次留下的可能根本不合规，
   所以命中后仍然要过"只在色板三角形内"这条不变量（实测能抓到：往里塞一张彩图就红）

跑法：python3 image_source.py --prompt "team photo, poster" -o pic.png [--provider-cmd "…"]
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import random
import shlex
import subprocess
import sys

from PIL import Image, ImageDraw

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
deckio = _load_sibling("deckio")   # IO 收口：本来就是本仓库的规矩，这个文件是最后一个没跟上的
# 文件名是 plate.py，但下游用法是 `treat_image.xxx` —— 绑定同名以最小化变更。
treat_image = _load_sibling("plate")

CACHE_DIR_VAR = "AGENT_SKILLS_CACHE_DIR"


def cache_dir() -> str:
    override = os.environ.get(CACHE_DIR_VAR, "").strip()
    if override:
        return os.path.abspath(os.path.expanduser(override))
    return os.path.expanduser(os.path.join("~", ".cache", "agent-skills", "riso-deck"))


def cache_key(prompt: str, colors: dict, size: tuple[int, int]) -> str:
    raw = f"{prompt}|{colors['primary']}|{colors['secondary']}|{colors['background']}|{size[0]}x{size[1]}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def collage(seed: int, colors: dict, size: tuple[int, int]) -> Image.Image:
    """几何色块拼贴（确定性）：圆 / 半圆 / 条纹 的专色组合。

    它本身就得是**有版式的**（方案 §5.2 原话：不能用无风格的灰色占位图）——
    哪怕是兜底图，也要看得出是这个 deck 的图，而不是“图待补”。
    """
    w, h = size
    image = Image.new("L", size, 255)
    draw = ImageDraw.Draw(image)
    r = random.Random(seed)
    lo, hi = round(min(w, h) * 0.18), round(min(w, h) * 0.42)   # 循环外算一次就够
    for _ in range(r.randint(3, 5)):
        radius = r.randint(lo, hi)
        x, y = r.randint(0, w), r.randint(0, h)
        kind = r.choice(["circle", "half", "band"])
        tone = r.choice([40, 90, 150, 200])
        if kind == "circle":
            draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=tone)
        elif kind == "half":
            draw.pieslice([x - radius, y - radius, x + radius, y + radius], start=180, end=360, fill=tone)
        else:
            draw.rectangle([x, y, x + radius, y + max(6, radius // 6)], fill=tone)
    return image.convert("RGB")


def in_palette(image: Image.Image, colors: dict, tol: float = 0.01) -> list[tuple[int, int, int]]:
    """不变量：图里任何颜色都必须落在「主色 / 叠印墨 / 纸色」三角形内。"""
    tri = (treat_image._rgb(colors["primary"]),
           treat_image._rgb(ink.overprint(colors["primary"], colors["secondary"])),
           treat_image._rgb(colors["background"]))
    entries = image.getcolors(maxcolors=1 << 20) or []
    stray: list[tuple[int, int, int]] = []
    for entry in entries:
        # getcolors 的第二项在类型上是 `int | tuple[int, ...]`（"L" 图给 int，RGB 给元组）。
        # 显式收窄并构造三元组，不用 `c for _, c in ...` —— 后者留下 int 分支。
        color = entry[1]
        if not isinstance(color, tuple) or len(color) != 3:
            continue
        rgb = (color[0], color[1], color[2])
        if not treat_image._in_triangle(rgb, *tri, tol=tol):
            stray.append(rgb)
    return stray


def _provider_argv(template: str, prompt: str, out: str) -> list[str]:
    """把 provider 命令模板变成 argv —— **不过 shell**。

    原来是 `subprocess.run(template.format(...), shell=True)`。prompt 是**用户内容**，
    直接拼进 shell 命令里就是一个命令注入点：prompt 里写个 `; rm -rf …` 就能执行
    （这是静态检查真报出来的，不是噪声）。

    改法：先用哨兵值 shlex 切好 argv，再把哨兵换成真值 —— prompt 永远只是
    **一个参数**，不再经过 shell 解析。引号写不写都行（占位处一般不写更清楚）。
    """
    sp, so = "\x00prompt\x00", "\x00out\x00"
    parts = shlex.split(template.format(prompt=sp, out=so))
    return [p.replace(sp, prompt).replace(so, out) for p in parts]


def resolve(prompt: str, colors: dict, size: tuple[int, int], out: str,
            provider_cmd: str | None = None) -> str:
    deckio.ensure_dir(cache_dir())
    path = os.path.join(cache_dir(), f"{cache_key(prompt, colors, size)}.png")
    if os.path.isfile(path):
        cached = Image.open(path).convert("RGB")
        stray = in_palette(cached, colors)
        if not stray:
            cached.save(out)
            print(f"✓ 命中缓存（{os.path.basename(path)}）→ {out}")
            return "cache"
        print(f"✗ 缓存里的图不合规范（{len(stray)} 种颜色在色板三角之外，例 {stray[:2]}）"
              f" —— 丢弃并重新走一遍，不拿不合规的图凑数")
    source = None
    if provider_cmd:
        try:
            subprocess.run(_provider_argv(provider_cmd, prompt, path), check=True)
            source = "generated"
        except subprocess.CalledProcessError as exc:
            print(f"✗ 生图失败（{exc.returncode}）→ 降级为几何色块拼贴")
    else:
        print("· 未配置生图（--provider-cmd）→ 用几何色块拼贴（它本身就是版画式的拼贴，不是灰占位图）")
    if source is None:
        image = collage(abs(hash(cache_key(prompt, colors, size))) % (10 ** 6), colors, size)
        treated = treat_image.duotone(image, colors["primary"], colors["secondary"],
                                      colors["background"], dots=3)
    else:
        treated = treat_image.duotone(Image.open(path).convert("RGB"), colors["primary"],
                                      colors["secondary"], colors["background"], dots=3)
    treated.save(path)
    treated.save(out)
    print(f"✓ 已写出 {out}（来源：{source or '几何色块拼贴'}，已缓存为 {os.path.basename(path)}）")
    return source or "collage"



# ═══════════════════════════════════════════════════════════════════════════
# 取图策略之三：**写清契约，交给人去生成**
#
# 为什么把它做成推荐路径：脚本擅长的是"知道每张图放进哪个槽位、那个槽位实测多少
# 像素、它会被制版管线怎么处理"—— 这些模型不会自己知道。而"出一张好看的图"这件事，
# 人在自己顺手的模型里做得比脚本去调一个陌生的 API 好。所以分工是：
#
#     **脚本写契约与提示词 → 人出图 → 脚本再验一遍**
#
# 与另两条策略（provider-cmd / 几何色块拼贴）并列，不是替代关系：
# provider-cmd 给有 API 的人，拼贴给"先跑起来看看"，brief 给真做设计的人。
# ═══════════════════════════════════════════════════════════════════════════

# 图片槽位的目标倍率：2x。与 shots.py 的 --force-device-scale-factor=2 同一个理由 ——
# 投影与打印都不糊。1x 在屏幕上勉强够，投到大屏就是糊的。
BRIEF_SCALE = 2

# 推荐的画面比例（照片类槽位）。选 3:2 而不是 16:9 或 1:1：
#   · `.imgwrap` 宽 640px，旁边是 820px 的文字栏 —— 太宽会让图显得像背景条
#   · 高度要能塞进正文带（页脚之上），1:1 的 640px 高会顶到页脚
#   · 3:2 是相机原生比例，出图的人最容易拿到
BRIEF_ASPECT = (3, 2)


def _slot_geometry(spec_path: str, style: str | None, out_dir: str,
                   place: bool = True) -> tuple[dict, str]:
    """渲一次、量一次，拿到**每个图片槽位的真实几何**。

    为什么非要量：槽位的宽是布局定的（`.imgwrap{width:640px}`），**高取决于图的
    比例** —— 图还没出的时候，只有真渲一遍才知道那个槽位有多高、装不装得下。
    先给一张占位图（比例就是 brief 推荐的那个），量出来的就是真值。
    这也是"不估算"原则用在写提示词上：给模型的尺寸数字必须是实测的。

    ⚠️ **`place=True` 会往 out_dir 里写占位图** —— 这是有副作用的。所以
    **`--check` 绝不能走这条路**：检查把它该验的东西自己造出来，就永远验不出
    "图还没出"（实测踩过：删掉图之后 `--check` 照样报"符合契约"）。
    检查只需要"文件名 + 契约里的尺寸/比例"，不需要测量 —— 它不该渲染任何东西。
    """
    render_mod = _load_sibling("render")
    measure_mod = _load_sibling("measure")
    spec = deckio.read_json(spec_path)
    deck = spec.get("deck", {})
    style_name = style or deck.get("style") or render_mod.DEFAULT_STYLE
    tokens = render_mod.load_style(style_name)["tokens"]
    color_set = deck.get("colorSet") or next(iter(tokens["colorSets"]), "")
    colors = tokens["colorSets"].get(color_set) or next(iter(tokens["colorSets"].values()))

    # 占位图（按推荐比例）——放好之后这次测量才量得到槽位高度
    slots = [s for s in deck.get("slides", []) if s.get("image")]
    if not slots:
        return ({}, style_name)
    width = 640 * BRIEF_SCALE
    height = round(width * BRIEF_ASPECT[1] / BRIEF_ASPECT[0])
    for slide in slots:
        target = os.path.join(out_dir, str(slide["image"]))
        if not os.path.isfile(target):
            collage(7, colors, (width, height)).save(target)

    html_path = os.path.join(out_dir, "_brief-probe.html")
    deckio.write_text(html_path, render_mod.render(spec))
    measured = measure_mod.measure(html_path)
    info: dict = {"style": style_name, "colors": colors, "slides": {}}
    for i, slide in enumerate(spec["deck"]["slides"], 1):
        if not slide.get("image"):
            continue
        box = [e for e in measured.get("elements", [])
               if e.get("slide") == i and e.get("role") == "image"]
        info["slides"][i] = {
            "title": slide.get("title", ""),
            "bullets": slide.get("bullets", []),
            "file": str(slide["image"]),
            "box": box[0] if box else None,
        }
    return (info, style_name)


def _aspect_box(w: int, h: int) -> str:
    return f"{w}:{h}（≈{w / h:.2f}:1）"


def build_brief(spec_path: str, out_dir: str, style: str | None = None) -> dict:
    """产出提示词契约（人读的 markdown + 机读的 JSON 一起给）。"""
    info, style_name = _slot_geometry(spec_path, style, out_dir)
    if not info:
        raise SystemExit("✗ 这份 spec 里没有任何 image 槽位 —— 没有要出图的地方")
    tokens = _load_sibling("render").load_style(style_name)["tokens"]
    label = tokens.get("label", style_name)
    temperature = tokens.get("temperature", "")
    reference = tokens.get("reference", "")

    w = 640 * BRIEF_SCALE
    h = round(w * BRIEF_ASPECT[1] / BRIEF_ASPECT[0])
    # 按**文件名**合并：同一个文件名用在多页是合法的（复用同一张图）。
    # 第一版按页列 —— 于是同一张图被列了三遍，人会出三张、互相覆盖（实测）。
    by_file: dict[str, dict] = {}
    for page, s in sorted(info["slides"].items()):
        box = s["box"] or {}
        entry = by_file.setdefault(s["file"], {
            "file": s["file"], "pages": [], "titles": [], "bullets": [],
            "target_px": [w, h], "aspect": _aspect_box(*BRIEF_ASPECT), "alpha": False,
            "measured": f"实测槽位 {box['w']:.0f}×{box['h']:.0f}px" if box else "",
            # ⚠️ 内容只是**草稿**：条目往往在讲这份 deck 的叙事，而不是在讲"照片里该有什么"。
            # 工具只能读到文字，读不到你脑子里的画面 —— 所以这一栏必须由人改写。
            "subject": s["title"], "subject_is_draft": True,
        })
        entry["pages"].append(page)
        entry["titles"].append(s["title"])
        entry["bullets"].extend(str(b) for b in s["bullets"][:3])
    slots = [by_file[k] for k in sorted(by_file, key=lambda k: by_file[k]["pages"][0])]
    brief = {
        "style": style_name, "style_label": label, "temperature": temperature,
        "reference": reference, "target_px": [w, h], "aspect": _aspect_box(*BRIEF_ASPECT),
        "slots": slots, "colors": info["colors"],
    }
    return brief


# 气质 → 该给模型的**视觉后果**。不写风格文献（Massimo Vignelli / 某本杂志那种）：
# 对读文档的人是背景，对生图模型是噪音 —— 它不知道该把"Vignelli"画成什么样。
# 这里只给能画出来的东西：光、对比、饱和、材质。
MOOD_CUES = {
    "大胆": "dramatic high-contrast lighting, bold simple forms, deep shadows, "
            "confident graphic silhouette",
    "安静": "even neutral daylight, restrained and calm, low drama, clean "
            "uncluttered composition, muted tones",
    "中性": "natural balanced light, everyday documentary feel, honest and plain",
}


# 同样三档的中文说法。中文提示里夹一句英文观感很出戏（实测：中文段里冒出
# "even neutral daylight, restrained and calm"），而且给中文模型看也没帮助。
MOOD_CUES_ZH = {
    "大胆": "戏剧性的高对比光、形体简洁有力、阴影深、轮廓像海报一样肯定",
    "安静": "均匀中性的日光、克制平静、不戏剧化、画面干净不杂、色调偏灰",
    "中性": "自然均衡的光、日常纪实感、朴素不修饰",
}


def _mood(temperature: str) -> str:
    return _pick(MOOD_CUES, temperature)


def _mood_zh(temperature: str) -> str:
    return _pick(MOOD_CUES_ZH, temperature)


def _pick(table: dict, temperature: str) -> str:
    for key, cue in table.items():
        if key in (temperature or ""):
            return cue
    return table["中性"]


def _prompt_en(slot: dict, brief: dict) -> str:
    """交给生图模型的那段。**按管线约束写**，不是通用套话。

    约束都来自这条流水线的事实：图会被压成两个墨色 + 半调网点（见 plate.py）。
    所以"细密纹理、细线、渐变、图里的文字"全都是坑 —— 它们在双色调里糊成一团。
    这类话不写进去，模型会给你一张很漂亮但制完版就废掉的图。
    """
    palette = brief["colors"]
    return (
        f"Editorial photograph for a slide deck, {brief['aspect']} aspect ratio, "
        f"{brief['target_px'][0]}x{brief['target_px'][1]}px.\n"
        f"Subject: {slot['subject']} — REPLACE THIS with what the photo should "
        f"actually show (auto-drafted from the slide title).\n"
        f"Look: {_mood(brief['temperature'])}.\n"
        # ⚠️ 不写"给文字留压字空间"：我们的版式里文字是**独立一栏**（左文右图），
        # 不是压在图上。写错了会让模型交一张主体偏到一边、空掉半张的图（第一版就写错了）。
        "Composition: ONE clear subject filling 60-70% of the frame, strong simple "
        "silhouette, clear separation between subject and background, shallow depth "
        "of field, clean uncluttered background. The photo stands on its own — "
        "text sits in a SEPARATE column beside it, never on top.\n"
        "Lighting: single directional light source, high contrast between light and "
        "shadow, deliberate shadows.\n"
        f"IMPORTANT — this image will be reduced to TWO INKS and printed as a "
        f"halftone (duotone {palette['primary']} / {palette['secondary']} on "
        f"{palette['background']}). It must still read clearly after that "
        f"reduction: rely on LARGE tonal masses and strong shapes, not on color "
        f"or fine detail.\n"
        "Avoid: text, letters, numbers, watermarks, logos, UI screenshots, thin "
        "lines, fine mesh or woven textures, busy repeating patterns, subtle "
        "gradients, low-contrast flat lighting, cluttered backgrounds, more than "
        "one focal subject."
    )


def _prompt_zh(slot: dict, brief: dict) -> str:
    return (
        f"给幻灯片用的纪实摄影，画面比例 {brief['aspect']}，目标 {brief['target_px'][0]}"
        f"×{brief['target_px'][1]} 像素。\n"
        f"内容：{slot['subject']}。← **这一句务必改成你真正要的画面**\n"
        f"观感：{_mood_zh(brief['temperature'])}。\n"
        f"构图：**一个**主体，占画面 60~70%；轮廓干净简单；主体与背景分离明确；"
        f"浅景深、背景干净不杂。"
        f"（图是**独立**的，文字在旁边的另一栏，不压在图上。）\n"
        f"光线：单一方向光源，明暗对比强，有明确的阴影。\n"
        f"⚠️ 这张图会被压成**两个墨色 + 半调网点**（{brief['colors']['primary']} / "
        f"{brief['colors']['secondary']} 印在 {brief['colors']['background']} 上）。"
        f"所以它必须靠**大块的明暗和强形状**立住，不能靠颜色或细节。\n"
        f"避免：文字/字母/数字/水印/logo、界面截图、细线、细密网格或织物纹理、"
        f"繁复重复的图案、柔和渐变、低对比的平光、杂乱的背景、多个并列主体。"
    )


def write_brief_md(brief: dict, out_path: str) -> str:
    lines = [
        "# 图片提示词契约",
        "",
        f"风格 **{brief['style_label']}**（{brief['temperature']}）· 参考 {brief['reference']}",
        "",
        f"**统一规格**：`{brief['target_px'][0]}×{brief['target_px'][1]}px`，"
        f"比例 {brief['aspect']}，**不需要透明通道**（会是整张不透明照片）。",
        f"倍率取 2x 是因为导出 PNG 时也是 2x（投影与打印都不糊）。",
        "",
        "**出完图存到哪**：与产物（`out.html`）**同一个目录**，文件名逐张见下。",
        "相对路径的产物挪个目录就会全员裂图（这是已知限制）—— 所以要同目录交付。",
        "",
        "> ⚠️ **这些图会被压成两个墨色 + 半调网点**（见 `plate.py`）。所以靠"
        "**大块明暗和强形状**立住的图能活下来，靠颜色/细密纹理/细线的图会糊成一团。"
        "下面的负面清单就是按这条写的，不是通用套话。",
        "",
        "---",
        "",
    ]
    for s in brief["slots"]:
        lines += [
            f"## {'、'.join('第 %d 页' % p for p in s['pages'])} · "
            f"{' / '.join(s['titles'])}",
            "",
            f"- **文件名**：`{s['file']}`（存到产物同目录，用在 "
            f"{'、'.join('第 %d 页' % p for p in s['pages'])}）"
            f"{'；' + s['measured'] if s['measured'] else ''}",
            f"- **尺寸**：{s['target_px'][0]}×{s['target_px'][1]}px，比例 {s['aspect']}",
            f"- **透明通道**：不需要（不透明照片即可）",
            f"- **会被制版处理**：双色调 + 半调网点 + 不引入色板外的色相",
            "",
            f"- **内容**：`{s['subject']}` —— ⚠️ **这是草稿**：从该页标题自动取的，"
            f"而条目的文字往往在讲这份 deck 的叙事、不是在讲照片里该有什么。"
            f"**请自己改写这一句** —— 工具读不到你脑子里的画面。",
            "",
            "**中文说明**",
            "",
            "```text",
            _prompt_zh(s, brief),
            "```",
            "",
            "**English prompt（多数模型对英文更稳）**",
            "",
            "```text",
            _prompt_en(s, brief),
            "```",
            "",
        ]
    lines += [
        "---",
        "",
        "出完图之后：",
        "",
        "```bash",
        "python3 scripts/image_source.py --check your.spec.json    # 验尺寸与比例对不对",
        "python3 scripts/deliver.py your.spec.json --pages 3      # 验它在版面里装得下",
        "```",
        "",
        "尺寸不对不是「将就一下」的事：**被放大渲染的图一定糊**，而交付前那条提示"
        "（`check.py` 的放大检查）就是为它准备的。",
    ]
    deckio.write_text(out_path, "\n".join(lines) + "\n")
    return out_path


def check_images(spec_path: str, out_dir: str, style: str | None = None) -> tuple[int, list[str]]:
    """验人交付的图：在不在、够不够大、比例对不对。

    为什么单独一步而不是并进 `check.py`：`check.py` 是在**渲染之后**看产物的
    （它只知道"有没有加载""有没有被放大"）；这一步是在**渲染之前**对着契约验 ——
    能在跑完整条流水线之前就告诉你"这张图你出小了/出窄了"。
    """
    spec = deckio.read_json(spec_path)
    # 逐页收（同一个文件名用在多页时，报第一个用到它的页号，且只验一次）
    wanted: dict[str, int] = {}
    for page, slide in enumerate(spec.get("deck", {}).get("slides", []), 1):
        name = slide.get("image")
        if name and str(name) not in wanted:
            wanted[str(name)] = page
    if not wanted:
        raise SystemExit("✗ 这份 spec 里没有任何 image 槽位")
    want_w = 640 * BRIEF_SCALE
    problems: list[str] = []
    for name, page in sorted(wanted.items(), key=lambda kv: kv[1]):
        path = os.path.join(out_dir, name)
        if not os.path.isfile(path):
            problems.append(f"第 {page} 页：`{name}` 不在 {out_dir} —— 还没出图")
            continue
        with Image.open(path) as im:
            w, h = im.size
        if w < want_w:
            problems.append(
                f"第 {page} 页：`{name}` 只有 {w}px 宽，契约要 {want_w}px —— "
                f"放进版面会被放大渲染（会糊）")
        ratio_want = BRIEF_ASPECT[0] / BRIEF_ASPECT[1]
        ratio_got = w / h
        if abs(ratio_got - ratio_want) > 0.12:
            problems.append(
                f"第 {page} 页：`{name}` 比例是 {ratio_got:.2f}:1，契约是 "
                f"{ratio_want:.2f}:1 —— 版面按宽度缩放，比例差太多会撑高或压扁"
                f"（撑高会撞页脚）")
    return (1 if problems else 0, problems)

def _parse_size(raw: str) -> tuple[int, int]:
    """`WxH` → (w, h)。格式不对要说清楚哪里不对，不甩生成器报错。"""
    parts = raw.lower().split("x")
    if len(parts) != 2:
        raise SystemExit(f"✗ --size 要写成 WxH（如 640x400），收到 {raw!r}")
    return (round(deckio.as_number(parts[0], f"--size 的宽（{raw!r}）")),
            round(deckio.as_number(parts[1], f"--size 的高（{raw!r}）")))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description="图片来源三条路：**写契约给人出图（--brief）** / 调生图命令 / 几何色块拼贴")
    # 三条路各自的入口：
    #   --brief 推荐（人出图）· --check 验人交付的图 · 其余是"先跑起来"的占位
    ap.add_argument("--brief", default=None, metavar="SPEC",
                    help="从这份 spec 生成**图片提示词契约**（人拿它去出图）")
    ap.add_argument("--check", default=None, metavar="SPEC",
                    help="验人交付的图：在不在 / 够不够大 / 比例对不对")
    ap.add_argument("--prompt", default=None, help="（占位路径）出图用的提示词")
    ap.add_argument("-o", "--out", default=None, help="输出文件（--brief 缺省写 spec 同目录）")
    ap.add_argument("--dir", default=None,
                    help="图片所在的目录（缺省：spec 所在目录）")
    ap.add_argument("--style", default=None, help="风格（缺省读 spec 的 deck.style）")
    ap.add_argument("--tokens", default=os.path.join(HERE, "..", "styles", "swiss-grid", "style.json"))
    # 色板名不写死：写死会在换风格 / 改色板名时**静默过期**——实测踩过两次
    # （plate.py 与这里都留着 riso 时代那个已经删掉的 'vivid'，于是默认路径直接崩）。
    ap.add_argument("--color-set", default=None, help="色板（缺省用该 token 的第一个）")
    ap.add_argument("--size", default="640x400")
    ap.add_argument("--json", action="store_true", help="--brief 时额外输出机读 JSON")
    ap.add_argument("--provider-cmd", default=None,
                    help="可选的生图命令，用 {prompt} 与 {out} 占位；不填就用色块拼贴")
    args = ap.parse_args(argv[1:])

    if args.brief:
        out_dir = args.dir or os.path.dirname(os.path.abspath(args.brief))
        brief = build_brief(args.brief, out_dir, args.style)
        target = args.out or os.path.join(out_dir, "image-brief.md")
        write_brief_md(brief, target)
        print(f"✓ 图片提示词契约 → {target}")
        print(f"  {len(brief['slots'])} 个槽位 · 统一规格 "
              f"{brief['target_px'][0]}×{brief['target_px'][1]}px · {brief['aspect']}")
        print(f"  出完图存到：{out_dir}（与产物同目录）")
        print(f"  存好后验一遍：image_source.py --check {args.brief}")
        if args.json:
            import json   # noqa: PLC0415

            print(json.dumps(brief, ensure_ascii=False, indent=2))
        return 0

    if args.check:
        out_dir = args.dir or os.path.dirname(os.path.abspath(args.check))
        code, problems = check_images(args.check, out_dir, args.style)
        if problems:
            print(f"✗ {len(problems)} 个问题：")
            for p in problems:
                print("  ·", p)
            print(f"\n  契约见 {os.path.join(out_dir, 'image-brief.md')}"
                  f"（没有就先生成：image_source.py --brief <spec>）")
            return code
        print("✓ 交付的图都符合契约（尺寸 / 比例 / 都在产物目录里）")
        return 0

    if not args.prompt or not args.out:
        raise SystemExit("✗ 要么给 --brief/--check（推荐），要么给 --prompt 与 -o（占位路径）")
    tokens = deckio.read_json(args.tokens)
    color_set = args.color_set or next(iter(tokens["colorSets"]), None)
    if color_set not in tokens["colorSets"]:
        raise SystemExit(f"✗ colorSet={color_set!r} 不在 {args.tokens} 里"
                         f"（可用：{sorted(tokens['colorSets'])}）")
    colors = tokens["colorSets"][color_set]
    resolve(args.prompt, colors, _parse_size(args.size), args.out, args.provider_cmd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
