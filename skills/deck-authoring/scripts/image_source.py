#!/usr/bin/env python3
"""图片：**先写契约，再由用户出图**。

两条路径，同一份提示词：

1. `--brief` → 契约（`image-brief.md` + `assets/requests/*.json`）—— 用户拿它出图；
2. `--check` → 验用户回填的图：在不在 / 够不够大 / 比例合不合（比例只说明，不阴塞）。

图只从**用户的模型**来：脚本不画图（没有拼贴、没有占位图兜底），也不调用任何生图
后端或读取密钥 —— 代用户出图会让交付里混进一张分工不清的图。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import random
import re
import sys
import tempfile
from typing import cast

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


deckio = _load_sibling("deckio")   # IO 收口：本来就是本仓库的规矩，这个文件是最后一个没跟上的


def collage(seed: int, colors: dict, size: tuple[int, int]) -> Image.Image:
    """一把**量尺寸的尺子**：几何色块拼贴，尺寸对、确定性（同一 seed 同一张）。

    它只活在临时目录里（见 `_slot_geometry`），用途只有一个 —— 让 `.imgwrap`
    按目标比例撑开，从而量到槽位真实的几何。**它不是这个 deck 的资产**，
    也不出现在产物目录里：交付图一律是人拿 `--brief` 的提示词出的。
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


def _has_transparency(path: str) -> bool:
    try:
        with Image.open(path) as image:
            extrema = image.convert("RGBA").getchannel("A").getextrema()
            if isinstance(extrema, tuple):
                return cast(tuple[int, int], extrema)[0] < 255
            return float(extrema) < 255
    except (OSError, ValueError):
        return False


def _is_fully_transparent(path: str) -> bool:
    try:
        with Image.open(path) as image:
            return image.convert("RGBA").getchannel("A").getextrema()[1] == 0
    except (OSError, ValueError):
        return False


# ═══════════════════════════════════════════════════════════════════════════
# 取图策略：**写清契约，再由用户出图**
#
# 为什么契约放在第一位：脚本擅长的不是画图，是"知道每张图放进哪个槽位、那个槽位实测
# 多少像素、它会被版式怎么裁"—— 这些模型不会自己知道。所以主路径是：
#
#     **脚本写契约与提示词 → 用户出图 → 脚本再验一遍**
#
# 脚本不提供任何出图后端，也不读取任何生成服务密钥：那一步属于用户。
# 这样交付里的每张图都有明确来源，不会混进一张没人认领的生成图。
# ═══════════════════════════════════════════════════════════════════════════

# 图片槽位的目标倍率：2x。与 shots.py 的 --force-device-scale-factor=2 同一个理由 ——
# 投影与打印都不糊。1x 在屏幕上勉强够，投到大屏就是糊的。
BRIEF_SCALE = 2

# 宽度差这么一点点不算问题。为什么要有这个容差：生图服务每个比例给的是**固定像素**，
# 未必正好够我们要的宽度；而把这种本来能用的图判成"会糊"，整条链就卡在一张没毛病的图上。
# 差得多的（> 5%）仍然是阻塞项：那道门的本意是"别拿缩略图当大图"。
SIZE_TOLERANCE = 0.05

# 提示词里没填的模板占位（中文 〈…〉、英文 <…>）：brief 交出去前应被作者填掉。
# 保留它是为了在验收与测试里识别"还没写完整"的提示词，而不是发给任何模型。
PLACEHOLDER_RE = re.compile(r"〈[^〉]*〉|<[^<>]*>")

# Legacy renderer fallback. Actual contracts use measured slot geometry.
BRIEF_ASPECT = (3, 2)


def _slot_geometry(spec_path: str, style: str | None) -> tuple[dict, str]:
    """渲一次、量一次，拿到**每个图片槽位的真实几何**。

    为什么非要量：槽位的宽是布局定的（`.imgwrap` 那一列），**高取决于图的
    比例** —— 图还没出的时候，只有真渲一遍才知道那个槽位有多高、装不装得下。
    先放一把"尺子"（比例就是 brief 推荐的那个），量出来的就是真值。
    这也是"不估算"原则用在写提示词上：给模型的尺寸数字必须是实测的。

    **尺子只活在临时目录里**（只有本次渲染用的 spec 副本指向它）—— 产物目录里的
    图永远只有人出的那一份。写进产物目录就等于把一张脚本拼的图混进交付（
    `--brief` 跑完，图片目录里躺着几张拼贴，没人替换它们就跟着交付了）。
    `--check` 先检查真实文件是否存在，再用临时尺子测布局所需尺寸；尺子不会写进
    图片目录，也不能代替被验收的真实文件。
    """
    render_mod = _load_sibling("render")
    measure_mod = _load_sibling("measure")
    spec = deckio.read_json(spec_path)
    deck = spec.get("deck", {})
    # 解析根与渲染层同一套：deck 项目 = spec 所在目录（不是 cwd）
    project_dir = os.path.dirname(os.path.abspath(spec_path))
    style_name = style or deck.get("style")
    tokens = render_mod.load_style(style_name, project_dir)["tokens"]
    colors = _pick_colors(deck, tokens)

    # 尺子（按推荐比例）+ 探针 HTML 都进临时目录，产物目录一个字节都不写
    slots = [s for s in deck.get("slides", []) if s.get("image")]
    if not slots:
        return ({}, style_name)
    width = 640 * BRIEF_SCALE
    height = round(width * BRIEF_ASPECT[1] / BRIEF_ASPECT[0])
    # 原路径先抄下来：探针副本要用尺子替掉 image，而契约里必须还是**用户那个路径**
    original = {i: str(s.get("image", "")) for i, s in enumerate(spec["deck"]["slides"], 1)}
    with tempfile.TemporaryDirectory(prefix="deck-brief-") as probe_dir:
        collage(7, colors, (width, height)).save(os.path.join(probe_dir, "ruler.png"))
        for slide in spec["deck"]["slides"]:
            if slide.get("image"):
                slide["image"] = "ruler.png"   # 只改这份探针副本，不动用户那份 spec
        html_path = os.path.join(probe_dir, "probe.html")
        deckio.write_text(html_path, render_mod.render(spec, project_dir=project_dir))
        measured = measure_mod.measure(html_path)
    info: dict = {"style": style_name, "colors": colors, "slides": {}}
    for i, slide in enumerate(spec["deck"]["slides"], 1):
        if not slide.get("image"):
            continue
        box = [e for e in measured.get("elements", [])
               if e.get("slide") == i and e.get("role") == "image"]
        image_box = box[0] if box else None
        hero_overlay = False
        if slide.get("layout") == "hero" and image_box:
            for element in measured.get("elements", []):
                if (element.get("slide") != i or element.get("role") != "title"
                        or element.get("hiddenBy") or element.get("opacity", 1) == 0):
                    continue
                left = max(element.get("x", 0), image_box.get("x", 0))
                top = max(element.get("y", 0), image_box.get("y", 0))
                right = min(element.get("x", 0) + element.get("w", 0),
                            image_box.get("x", 0) + image_box.get("w", 0))
                bottom = min(element.get("y", 0) + element.get("h", 0),
                             image_box.get("y", 0) + image_box.get("h", 0))
                hero_overlay = hero_overlay or (right > left and bottom > top)
        visual = slide.get("visual") if isinstance(slide.get("visual"), dict) else {}
        info["slides"][i] = {
            "title": slide.get("title", ""),
            "bullets": slide.get("bullets", []),
            "file": original.get(i, str(slide.get("image", ""))),
            "box": image_box,
            # 说明文字与版式类型：提示词的「文字」那一栏要用它们说清
            # "画面里不要有字，字由版面排"——这比笼统的负面词有用。
            "caption": slide.get("caption", ""),
            "type": slide.get("type", ""),
            "layout": slide.get("layout", ""),
            "visual_note": visual.get("note", ""),
            "imageBrief": visual.get("imageBrief", {}),
            # This describes only the legacy renderer's hero contract, not a universal layout.
            "hero_title_overlay": hero_overlay,
        }
    return (info, style_name)


# 哪些版式**天生带视觉锚点**（图表 / 时间线 / 两栏对比）—— 不缺图也立得住。
# 反过来，`content-text` 是纯文字页：它是**最可能该加图**的地方。
# 这只是一条按版式猜的启发式，所以它只用来**提示**，最终判断在人。
VISUAL_LAYOUTS = ("content-image", "chart", "timeline")


def suggest_image_slots(spec_path: str) -> list[str]:
    """一份 spec 一张图都没有时，指出哪几页该考虑加图。

    为什么不是直接报"没有要出图的地方"：那是把"少要"做成了默认。用户明确要的是
    **图片该要就要，别因为嫌麻烦就少要，多了也没事**。所以工具在这里的角色是
    提醒 + 指出位置，不是拒绝服务。
    """
    deck = deckio.read_json(spec_path).get("deck", {})
    slides = deck.get("slides", [])
    out = []
    for i, slide in enumerate(slides, 1):
        kind = slide.get("type", "")
        # 只有纯文字页会被列出来：图表 / 时间线本身就带视觉锚点，不缺图也立得住
        # （它们由 `VISUAL_LAYOUTS` 声明，见那里的注释）。
        if kind == "content-text":
            bullets = slide.get("bullets", [])
            if len(bullets) >= 3:
                out.append(f"第 {i} 页「{slide.get('title', '')}」是纯文字页、"
                           f"{len(bullets)} 条 —— 全篇最容易加图的地方")
    # 封面：主视觉通常在这里，但 title 版式**没有** image 字段
    for i, slide in enumerate(slides, 1):
        if slide.get("type") == "title":
            out.append(f"第 {i} 页是封面 —— `title` 版式不带 image 字段；要主视觉得"
                       f"用整幅色块或换版式（这一条是版式的限制，不是没要图）")
            break
    return out


def _pick_colors(deck: dict, tokens: dict) -> dict:
    """spec 指定的色板（缺省第一套）。

    `--brief` 与 `--check` 都按同一套色板解释契约，避免提示词与验收各说各的。
    """
    color_set = deck.get("colorSet") or next(iter(tokens["colorSets"]), "")
    return tokens["colorSets"].get(color_set) or next(iter(tokens["colorSets"].values()))


def _aspect_box(w: int, h: int) -> str:
    return f"{w}:{h}（≈{w / h:.2f}:1）"


def build_brief(spec_path: str, out_dir: str, style: str | None = None,
                contract_dir: str | None = None) -> dict:
    """产出提示词契约（人读的 markdown + 机读的 JSON 一起给；后者写进
    contract_dir/assets/requests/，md 由 main() 调 write_brief_md 写）。

    `out_dir` = **图片在哪**（人出的图存这儿；`--check` 也只看这里）；
    `contract_dir` = **合同在哪**
    （缺省同 out_dir）。分开是因为 `--dir` 的本意只是前者 —— 一份
    17 页 deck 的提示词合同被 `--dir` 一起搬进 /tmp，用户拿不到那份要他执行的东西。"""
    info, style_name = _slot_geometry(spec_path, style)
    if not info:
        # 不直接失败：先说清"你这份 spec 一张图都没有"，再指出哪几页可能该有 ——
        # 工具按版式只能猜到这一步，要不要加由内容定。
        lines = ["✗ 这份 spec 里没有任何 image 槽位 —— 没有要出图的地方。", ""]
        hints = suggest_image_slots(spec_path)
        if hints:
            lines.append("  要不要加图由内容定（工具只能按版式猜）：")
            lines += [f"    · {h}" for h in hints]
            lines += ["", "  一页在讲「某个东西长什么样 / 现场 / 对比」，就该有图；",
                      "  在讲「三条结论」，就不必有。加图用 `content-image` 版式"]
        else:
            lines.append("  这份 spec 里也没有明显该加图的位置（页数少 / 都是短页）。")
        raise SystemExit("\n".join(lines))
    tokens = _load_sibling("render").load_style(
        style_name, os.path.dirname(os.path.abspath(spec_path)))["tokens"]
    label = tokens.get("label", style_name)
    temperature = tokens.get("temperature", "")
    reference = tokens.get("reference", "")

    # 按**文件名**合并：同一个文件名用在多页是合法的（复用同一张图）。
    # 按**文件**列，不按页列：同一张图被多页共用时，按页列会列三遍，
    # 人会出三张互相覆盖（实测）。
    by_file: dict[str, dict] = {}
    # 槽位 id → 实测槽位 (w, h)。机读合同（assets/requests/）要用数字的宽高比，
    # 不能从 entry["measured"] 那句**给人看的**话里倒着解析 —— 量的时候顺手存。
    measured_px: dict[str, tuple[float, float] | None] = {}
    for page, s in sorted(info["slides"].items()):
        box = s["box"] or {}
        if not box or box.get("w", 0) <= 0 or box.get("h", 0) <= 0:
            raise SystemExit(f"✗ 第 {page} 页没有测到有效图片槽位，不能生成尺寸合同")
        w, h = math.ceil(box["w"] * BRIEF_SCALE), math.ceil(box["h"] * BRIEF_SCALE)
        entry = by_file.setdefault(s["file"], {
            "file": s["file"], "pages": [], "titles": [], "bullets": [],
            "target_px": [w, h], "aspect": _aspect_box(w, h),
            "requirements": [], "imageBrief": {}, "visual_notes": [],
            "hero_overlay_pages": [],
            "measured": f"实测槽位 {box['w']:.0f}×{box['h']:.0f}px" if box else "",
            # Page copy is context. Only imageBrief describes what to generate.
            "caption": s.get("caption", ""), "layout": s.get("type", ""),
        })
        # 与 entry["measured"] 同一条规则：取**首次出现**那页的实测值
        if s["file"] not in measured_px:
            measured_px[s["file"]] = (box["w"], box["h"]) if box else None
        entry["requirements"].append({"page": page, "width": box["w"], "height": box["h"],
                                      "fit": box.get("objectFit") or "cover"})
        direction = s.get("imageBrief") or {}
        for key, value in direction.items():
            if key in entry["imageBrief"] and entry["imageBrief"][key] != value:
                raise SystemExit(f"✗ 复用图片 {s['file']} 的 imageBrief.{key} 不一致；"
                                 "请统一同一素材的要求，或为不同构图使用不同文件名")
            entry["imageBrief"][key] = value
        if s.get("visual_note"):
            entry["visual_notes"].append(str(s["visual_note"]))
        if s.get("hero_title_overlay"):
            entry["hero_overlay_pages"].append(page)
        entry["target_px"] = [max(entry["target_px"][0], w), max(entry["target_px"][1], h)]
        entry["aspect"] = _aspect_box(*entry["target_px"])
        entry["pages"].append(page)
        entry["titles"].append(s["title"])
        entry["bullets"].extend(str(b) for b in s["bullets"][:3])
    slots = [by_file[k] for k in sorted(by_file, key=lambda k: by_file[k]["pages"][0])]
    brief = {
        "style": style_name, "style_label": label, "temperature": temperature,
        "reference": reference, "target_px": slots[0]["target_px"], "aspect": slots[0]["aspect"],
        "slots": slots, "colors": info["colors"],
    }
    # 机读的那一半落盘（人读的 md 由 main() 调 write_brief_md 写）。缺省与图片同目录；
    # `--dir` 指到别处时仍跟着 spec 走 —— 合同与 manifest（render.load_assets）同根。
    _write_asset_requests(brief, measured_px,
                          os.path.join(contract_dir or out_dir, "assets", "requests"))
    return brief


# Image direction is authored in visual.imageBrief. Geometry is measured separately;
# neither the palette name nor the renderer's layout name selects an artistic medium.
PROMPT_ORDER = ("用途", "主体", "构图", "主体位置", "文字安全区", "风格", "背景", "限制")
OPTIONAL_FIELDS = ("用途", "主体位置", "文字安全区", "风格", "背景", "限制")


def _composition_text(slot: dict | str, zh: bool) -> str:
    # Accept the former string argument for callers; a layout label alone proves no geometry.
    if not isinstance(slot, dict):
        slot = {}
    direction = slot.get("imageBrief") or {}
    parts = [direction.get("composition", "")]
    fits = {r.get("fit", "cover") for r in slot.get("requirements", [])}
    if "cover" in fits:
        parts.append("图片将按实测图位 cover 裁切，关键主体应保留在可见范围；按声明的主体位置安排构图。"
                     if zh else "The measured slot uses cover cropping. Keep essential subjects visible at the specified focal position.")
    if fits & {"contain", "scale-down"}:
        parts.append("图位采用 contain/scale-down，保留完整画面；不要为并不存在的裁切强行居中主体。"
                     if zh else "The slot uses contain/scale-down and retains the complete image.")
    if slot.get("hero_overlay_pages"):
        parts.append("此素材有一处使用旧结构化 hero 图位，底部标题带会覆盖图片；该区域不要放关键主体，实际覆盖高度以页面渲染为准。"
                     if zh else "A legacy structured hero slot overlays a title band at the bottom. Keep essential subjects clear of that band; its actual height comes from the rendered slide.")
    return " ".join(p for p in parts if p) or (
        "按本次图像用途组织画面；主体位置与文字留白遵循已声明的要求。" if zh else
        "Compose for this image's purpose and any specified focal position or text-safe area.")


def _negative_space_text(slot: dict | str) -> str:
    if not isinstance(slot, dict):
        return ""
    return (slot.get("imageBrief") or {}).get("negativeSpace", "")


def _field_values(slot: dict, brief: dict, lang: str) -> list[tuple[str, str]]:
    zh = lang == "zh"
    direction = slot.get("imageBrief") or {}
    subject = direction.get("subject") or (
        "〈描述要生成的主体及必要特征；缺少真实证据时请提供原始素材，不编造证据〉" if zh else
        "<describe the subject and essential features; provide original assets when factual evidence is required>")
    fields = [("用途", direction.get("purpose", "")), ("主体", subject),
              ("构图", _composition_text(slot, zh))]
    focal = direction.get("focal")
    if focal is not None:
        fields.append(("主体位置", f"焦点位于画面横向 {focal[0]}%、纵向 {focal[1]}%。" if zh else
                       f"Place the focal subject at {focal[0]}% horizontally and {focal[1]}% vertically."))
    fields += [("文字安全区", _negative_space_text(slot)), ("风格", direction.get("style", ""))]
    if "transparent" in direction:
        if direction["transparent"]:
            fields.append(("背景", "输出带真实透明通道的素材，不绘制棋盘格或实心底。" if zh else
                           "Use a real transparent background, not a drawn checkerboard or solid backdrop."))
        else:
            fields.append(("背景", "输出不透明背景；背景内容按本次主体与构图要求。" if zh else
                           "Use an opaque background appropriate to the specified subject and composition."))
    if direction.get("avoid"):
        fields.append(("限制", "；".join(direction["avoid"])))
    return [(name, value) for name, value in fields if value]


def render_prompt(slot: dict, brief: dict, lang: str = "zh") -> str:
    """Preserve authored direction verbatim; translate only generated field guidance."""
    return "\n".join(f"【{name}】{value}" for name, value in _field_values(slot, brief, lang))


def api_params(brief: dict) -> list[str]:
    w, h = brief["target_px"]
    direction = brief.get("imageBrief") or {}
    transparent = direction.get("transparent")
    alpha_note = ("需要真实透明通道；选择支持透明输出的工具和 PNG/WebP 格式" if transparent is True else
                  "不透明背景" if transparent is False else
                  "透明通道未指定；不预设图片媒介或背景")
    return [f"尺寸 {w}×{h}px（按所有实测图位 ×{BRIEF_SCALE}）",
            f"比例 {brief['aspect']}（来自实测尺寸）", "数量 1 张", alpha_note,
            "质量 / seed 按本次工具与复现需要设置"]


def _write_asset_requests(brief: dict, measured_px: dict, requests_dir: str) -> None:
    """Request v2 remains compatible; authored direction fields are optional additions."""
    for slot in brief["slots"]:
        direction = slot.get("imageBrief") or {}
        note = slot["measured"]
        if slot["caption"]:
            note += f"；版面说明文字：{slot['caption']}"
        request = {
            "schemaVersion": 2, "slide": slot["pages"], "role": slot["layout"],
            "aspect": round(slot["target_px"][0] / slot["target_px"][1], 3),
            "target_px": slot["target_px"], "requirements": slot["requirements"],
            "focal": direction.get("focal", ""),
            "negative_space": _negative_space_text(slot),
            "prompt": render_prompt(slot, brief, "zh"), "required": True, "note": note,
        }
        for key in ("purpose", "transparent", "avoid"):
            if key in direction:
                request[key] = direction[key]
        deckio.write_json(os.path.join(requests_dir, f"{slot['file']}.json"), request)


def write_brief_md(brief: dict, out_path: str) -> str:
    lines = ["# 图片提示词契约", "",
             "这份契约交给用户出图：用你自己的模型按提示词生成，文件名与目录见下方；skill 不代生图。", "",
             f"项目风格：{brief['style_label']}。风格参考：{brief['reference'] or '未提供'}。", "",
             f"页面色板参考：{json.dumps(brief['colors'], ensure_ascii=False)}。"
             "这是页面上下文，不限定照片、插画或证据素材的颜色数量。", "",
             "用途、主体、构图、风格、焦点、文字安全区与透明要求来自可选的 visual.imageBrief。"
             "只填写本次需要的项；没有声明的媒介、光线、色彩和背景不自动补成固定风格。", "",
             "〈…〉或 <…> 是尚未明确的主体，生成前需要填写。页面标题、条目和图注仅作为参考材料，"
             "不会自动画进图中；确实需要图内文字时，在主体或构图中给出准确文案。"
             "需要真实截图或事实证据时使用原始素材。", "",
             "尺寸、比例、数量优先作为生成工具的参数传递，不要写进 prompt 造成冲突；"
             "工具只接收提示词时应将参数一并提供。焦点和安全区是生图指导，不会自动改写页面 CSS。", ""]
    for slot in brief["slots"]:
        direction = slot.get("imageBrief") or {}
        used = "、".join(f"第 {p} 页" for p in slot["pages"])
        lines += [f"## {used} · {' / '.join(slot['titles'])}", "",
                  f"- 文件名：`{slot['file']}`（相对产物目录；{slot['measured']}）",
                  f"- 用途：{direction.get('purpose') or '未指定；根据本页内容决定图片任务'}",
                  f"- 内容参考：{'；'.join(slot['bullets']) or '无条目'}",
                  f"- 标题与图注参考：{' / '.join(slot['titles'])}；{slot.get('caption') or '无图注'}"]
        if slot.get("visual_notes"):
            lines.append(f"- 视觉说明参考：{'；'.join(slot['visual_notes'])}")
        lines += ["", "**中文提示词**", "", "```text", render_prompt(slot, brief, "zh"), "```", "",
                  "**English prompt**（已填写的主体与风格保持原文；英文说明不等于自动翻译）", "",
                  "```text", render_prompt(slot, brief, "en"), "```", "", "**参数**", ""]
        lines += [f"- {item}" for item in api_params({**brief, **slot})]
        lines += ["", "复用图位："]
        lines += [f"- 第 {r['page']} 页：{r['width']}×{r['height']}px，{r['fit']}"
                  for r in slot["requirements"]]
        lines.append("")
    lines += ["回填后运行 `image_source.py --check <spec>`，再检查实际页面与最终导出。", "",
              "尺寸和透明通道通过不代表画面内容合格。逐图检查：主体及关键细节是否保留；"
              "文字与结构是否准确；实际裁切、文字安全区和透明边缘是否符合当前页。", ""]
    deckio.write_text(out_path, "\n".join(lines))
    return out_path


def image_size(path: str) -> tuple[int, int] | None:
    """像素尺寸。SVG 读 viewBox / width-height —— PIL 打不开矢量图（实测会抛）。

    SVG 是**矢量**：没有"分辨率"这回事。版面按宽度缩放，所以宽度取 viewBox 的宽，
    `--check` 那条"够不够大"对矢量图不适用（放多大都不糊），由调用方跳过。
    """
    if not os.path.isfile(path):
        # 缺文件由调用方报（"还没出图"），检查器自己不能因为读不到就退出进程 ——
        # `deckio.read_text` 读不到时抛 SystemExit（它的约定），在这里必须拦住。
        return None
    if path.lower().endswith(".svg"):
        try:
            raw = deckio.read_text(path)
        except (OSError, UnicodeDecodeError):
            return None
        box = re.search(r'viewBox\s*=\s*"([-\d.\s,]+)"', raw)
        if box:
            parts = [x for x in re.split(r"[\s,]+", box.group(1).strip()) if x]
            if len(parts) == 4:
                try:
                    return (round(float(parts[2])), round(float(parts[3])))
                except ValueError:
                    return None
        wh = re.search(r'width\s*=\s*"(\d+)"[^>]*height\s*=\s*"(\d+)"', raw)
        if wh:
            try:
                return (int(wh.group(1)), int(wh.group(2)))
            except ValueError:
                return None
        return None
    try:
        with Image.open(path) as im:
            return tuple(im.size)          # type: ignore[return-value]
    except (OSError, ValueError):
        return None


def check_images(spec_path: str, out_dir: str, style: str | None = None,
                 ) -> tuple[int, list[str], list[str]]:
    """验人交付的图：在不在（阻塞）、够不够大（阻塞）、比例合不合（**只说明**）。

    比例**不阻塞**：生图工具出成 1:1 / 4:3 / 2:1 是常态（提示词按不住比例，各家默认
    都不同），而渲染层按**槽位**处理 —— 高度由槽位比例定，多出来的部分按 `visual.kind`
    裁切（照片）或留边（结构图）。所以"比例不对"不是错，为比例重出图纯属浪费。

    为什么单独一步而不是并进 `check.py`：`check.py` 是在**渲染之后**看产物的
    （它只知道"有没有加载""有没有被放大"）；这一步是在**渲染之前**对着契约验 ——
    能在跑完整条流水线之前就告诉你"这张图你出小了/出窄了"。
    """
    spec = deckio.read_json(spec_path)
    # 逐页收（同一个文件名用在多页时，报第一个用到它的页号，且只验一次）
    wanted: dict[str, int] = {}
    want_ratio: dict[str, float] = {}
    transparency: dict[str, bool] = {}
    for page, slide in enumerate(spec.get("deck", {}).get("slides", []), 1):
        name = slide.get("image")
        visual = slide.get("visual") if isinstance(slide.get("visual"), dict) else {}
        direction = visual.get("imageBrief") or {}
        if name and isinstance(direction.get("transparent"), bool):
            if str(name) in transparency and transparency[str(name)] != direction["transparent"]:
                return (1, [f"复用图片 {name} 的透明要求不一致"], [])
            transparency[str(name)] = direction["transparent"]
        if not name or str(name) in wanted:
            continue
        wanted[str(name)] = page
        # 比例以 spec 声明的 `visual.ratio` 为准（缺省才是 brief 推荐值）——
        # 出图的人按它出，验收当然也按它验。
        visual = slide.get("visual") if isinstance(slide.get("visual"), dict) else {}
        # 比例解析：写坏了不在这里报（`validate_spec.py` 的 BAD_RATIO 才是那一道门），
        # 这里退回 brief 的推荐值 —— 检查器自己不能因为一个坏字段就炸。
        try:
            a, b = (int(x) for x in str(visual.get("ratio")).split(":"))
        except (TypeError, ValueError):
            continue                     # 坏比例由 validate_spec 的 BAD_RATIO 报
        if b:
            want_ratio[str(name)] = a / b
    if not wanted:
        raise SystemExit("✗ 这份 spec 里没有任何 image 槽位")
    # 只量布局，不生产或替换用户图片；缺图仍由下方真实路径检查拦住。
    has_images = any(os.path.isfile(os.path.join(out_dir, name)) for name in wanted)
    geometry, _ = _slot_geometry(spec_path, style) if has_images else ({}, None)
    slots_by_file: dict[str, list[dict]] = {}
    for page, slot in geometry.get("slides", {}).items():
        box = slot.get("box") or {}
        if box.get("w", 0) > 0 and box.get("h", 0) > 0:
            slots_by_file.setdefault(slot["file"], []).append({**box, "page": page})
    problems: list[str] = []
    notes: list[str] = []
    for name, page in sorted(wanted.items(), key=lambda kv: kv[1]):
        path = os.path.join(out_dir, name)
        if not os.path.isfile(path):
            problems.append(f"第 {page} 页：`{name}` 不在 {out_dir} —— 还没出图")
            continue
        size = image_size(path)
        if size is None:
            problems.append(f"第 {page} 页：`{name}` 读不出有效尺寸，无法验收")
            continue
        w, h = size
        if w <= 0 or h <= 0:
            problems.append(f"第 {page} 页：`{name}` 尺寸必须为正数")
            continue
        slots = slots_by_file.get(name, [])
        if not slots:
            problems.append(f"第 {page} 页：`{name}` 没测到图位尺寸，无法验收清晰度")
            continue
        if path.lower().endswith(".svg"):
            notes.append(f"第 {page} 页：`{name}` 是**矢量图**（SVG）—— 不做放大检查"
                         f"（放多大都不糊）；比例按 viewBox {w}×{h} 算")
            if name in transparency:
                problems.append(f"第 {page} 页：`{name}` 的 SVG 透明效果需渲染确认，当前栅格透明检查不能认证")
        else:
            if _is_fully_transparent(path):
                problems.append(f"第 {page} 页：`{name}` 完全透明，没有可见内容")
                continue
            request_path = os.path.join(os.path.dirname(os.path.abspath(spec_path)),
                                        "assets", "requests", f"{name}.json")
            if name not in transparency and os.path.isfile(request_path):
                requirement = deckio.read_json(request_path).get("transparent")
                if isinstance(requirement, bool):
                    transparency[name] = requirement
            if name in transparency and _has_transparency(path) != transparency[name]:
                requirement = "真实透明通道" if transparency[name] else "不透明背景"
                problems.append(f"第 {page} 页：`{name}` 不满足声明的{requirement}")
            requirements = []
            for slot in slots:
                fit = slot.get("objectFit") or "cover"
                scales = (w / slot["w"], h / slot["h"])
                effective = max(scales) if fit in ("contain", "scale-down") else min(scales)
                requirements.append((effective / BRIEF_SCALE, slot))
            quality, limiting = min(requirements, key=lambda item: item[0])
            want_w = math.ceil(limiting["w"] * BRIEF_SCALE)
            want_h = math.ceil(limiting["h"] * BRIEF_SCALE)
            if quality < 1 - SIZE_TOLERANCE:
                problems.append(
                    f"第 {limiting['page']} 页：`{name}` 只有 {w}px 宽、{h}px 高，"
                    f"图位契约要 {want_w}px × {want_h}px（{limiting.get('objectFit') or 'cover'}）；"
                    f"有效清晰度仅目标的 {quality:.1%}，放大后会糊")
            elif quality < 1:
                notes.append(f"第 {page} 页：`{name}` {w}px 宽、{h}px 高，"
                             f"有效清晰度比目标少 {(1 - quality) * 100:.1f}%（5%容差内）")
        ratio_want = want_ratio.get(name, BRIEF_ASPECT[0] / BRIEF_ASPECT[1])
        ratio_got = w / h
        if abs(ratio_got - ratio_want) > 0.12:
            notes.append(
                f"第 {page} 页：`{name}` 是 {ratio_got:.2f}:1，槽位要 {ratio_want:.2f}:1"
                f" —— 清晰度通过时不用为比例重出图；请预览实际 cover 裁切或 contain 留边，"
                f"确认主体和文字完整保留")
    return (1 if problems else 0, problems, notes)

def _temp_dir_note(path: str) -> str | None:
    """deck 建在临时目录里 → 说一声（不阻塞）。

    为什么必须开口：提示词合同是**要交给用户去执行**的东西（他拿它去出图），
    落在 /tmp 里重启就没了。一份 17 页 deck 的 spec / 风格 / 提示词
    全在 /tmp/dir-*，用户手上只有一段对话，那份合同等于没产出。
    """
    real = os.path.realpath(path).rstrip(os.sep) + os.sep
    temp_root = os.path.realpath(tempfile.gettempdir()).rstrip(os.sep) + os.sep
    if real.startswith((temp_root, "/private/tmp/")):
        return (f"⚠️ deck 项目在临时目录里：{path}\n"
                f"   spec / 风格 / 素材 / 提示词合同都该在**项目目录**（随项目交付）——\n"
                f"   临时目录重启即失，用户也就拿不到这份要他执行的提示词。")
    return None


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description="图片来源：写契约交给用户出图，再验收回填文件；"
                    "脚本不生图，也不调用任何生图后端")
    ap.add_argument("--brief", default=None, metavar="SPEC",
                    help="从这份 spec 生成**图片提示词契约**（用户拿它去出图）")
    ap.add_argument("--check", default=None, metavar="SPEC",
                    help="验用户回填的图：在不在 / 够不够大 / 比例对不对")
    ap.add_argument("-o", "--out", default=None, help="输出文件（--brief 缺省写 spec 同目录）")
    ap.add_argument("--dir", default=None,
                    help="**图片**所在的目录（缺省：spec 所在目录）—— 只管图片："
                         "提示词合同与 requests 始终写在 spec 同目录")
    ap.add_argument("--style", default=None, help="风格（缺省读 spec 的 deck.style）")
    ap.add_argument("--json", action="store_true", help="--brief 时额外输出机读 JSON")
    args = ap.parse_args(argv[1:])

    if args.brief:
        # 合同（md + requests）落 **spec 所在目录**；`--dir` 只管图片在哪（
        # 提示词被 --dir 搬进 /tmp，用户拿不到）。
        spec_dir = os.path.dirname(os.path.abspath(args.brief))
        out_dir = args.dir or spec_dir
        brief = build_brief(args.brief, out_dir, args.style, contract_dir=spec_dir)
        target = args.out or os.path.join(spec_dir, "image-brief.md")
        write_brief_md(brief, target)
        print(f"✓ 图片提示词契约 → {target}")
        print(f"  {len(brief['slots'])} 个素材 · 尺寸按实际图位分别列在合同中")
        print(f"  出完图存到：{out_dir}（按上面的文件名）")
        print(f"  存好后验一遍：image_source.py --check {args.brief}")
        note = _temp_dir_note(spec_dir)
        if note:
            print(note)
        if args.json:
            import json  # noqa: PLC0415

            print(json.dumps(brief, ensure_ascii=False, indent=2))
        return 0

    if args.check:
        out_dir = args.dir or os.path.dirname(os.path.abspath(args.check))
        code, problems, notes = check_images(args.check, out_dir, args.style)
        if problems:
            print(f"✗ {len(problems)} 个问题：")
            for p in problems:
                print("  ·", p)
            for nt in notes:
                print("  ·", nt)
            print(f"\n  契约见 {os.path.join(out_dir, 'image-brief.md')}"
                  f"（没有就先生成：image_source.py --brief <spec>）")
            return code
        print("✓ 交付的图够用（都在产物目录里、尺寸够）")
        for nt in notes:
            print("  ·", nt)
        return 0

    raise SystemExit("✗ 要么给 --brief，要么给 --check；本脚本不提供生图命令。\n"
                     "  需要图时先 --brief 交 image-brief.md，由用户生成后回填，再 --check。")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
