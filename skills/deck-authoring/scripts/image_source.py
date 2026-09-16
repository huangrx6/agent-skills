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
import re
import tempfile
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


deckio = _load_sibling("deckio")   # IO 收口：本来就是本仓库的规矩，这个文件是最后一个没跟上的

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
        # 缓存命中即可信：key 里已经含 prompt + 色板 + 尺寸，同一把 key 就是同一张图。
        # 照片本来就有千百种颜色，拿"只在色板三角形内"去量它只会把好图判死
        # （v4 删掉制版后处理时这道判据就该一起删）—— 色彩约束由 --brief 的提示词承担。
        cached = Image.open(path).convert("RGB")
        cached.save(out)
        print(f"✓ 命中缓存（{os.path.basename(path)}）→ {out}")
        return "cache"
    if not provider_cmd:
        raise SystemExit(
            "✗ 没有生图命令（--provider-cmd），也没有 --brief。\n"
            "  这个工具不自己画图。拿 `--brief` 出提示词 → 用你自己的模型出图 →\n"
            "  存到 spec 同目录（或 --dir 指的目录）→ `--check` 验一遍。\n"
            "  有生图 API：--prompt '…' -o out.png --provider-cmd '你的命令 --prompt {prompt} --out {out}'")
    try:
        subprocess.run(_provider_argv(provider_cmd, prompt, path), check=True)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"✗ 生图失败（返回码 {exc.returncode}）—— 没有降级产物："
                         f"图只从你的模型来，脚本不兜底")
    # 没有制版处理这一层（双色调 / 半调网点都不做）—— 图片按原样使用。
    # 想要版画质感就在出图提示词里要（`--brief` 的构图/负空间字段），而不是
    # 在交付链里做一道后处理：后处理会让"check 说合规、交付图却不一样"。
    image = Image.open(path).convert("RGB")
    image.save(path)
    image.save(out)
    print(f"✓ 已写出 {out}（来源：{provider_cmd.split()[0]}，已缓存为 {os.path.basename(path)}）")
    return "generated"



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


def _slot_geometry(spec_path: str, style: str | None) -> tuple[dict, str]:
    """渲一次、量一次，拿到**每个图片槽位的真实几何**。

    为什么非要量：槽位的宽是布局定的（`.imgwrap` 那一列），**高取决于图的
    比例** —— 图还没出的时候，只有真渲一遍才知道那个槽位有多高、装不装得下。
    先放一把"尺子"（比例就是 brief 推荐的那个），量出来的就是真值。
    这也是"不估算"原则用在写提示词上：给模型的尺寸数字必须是实测的。

    **尺子只活在临时目录里**（只有本次渲染用的 spec 副本指向它）—— 产物目录里的
    图永远只有人出的那一份。写进产物目录就等于把一张脚本拼的图混进交付（实测踩过：
    `--brief` 跑完，图片目录里躺着几张拼贴，没人替换它们就跟着交付了）。
    **`--check` 也不走这条路**：检查把它该验的东西自己造出来，就永远验不出
    "图还没出"（实测踩过：删掉图之后 `--check` 照样报"符合契约"）——
    检查只需要"文件名 + 契约里的尺寸/比例"，不该渲染任何东西。
    """
    render_mod = _load_sibling("render")
    measure_mod = _load_sibling("measure")
    spec = deckio.read_json(spec_path)
    deck = spec.get("deck", {})
    style_name = style or deck.get("style")
    tokens = render_mod.load_style(style_name)["tokens"]
    color_set = deck.get("colorSet") or next(iter(tokens["colorSets"]), "")
    colors = tokens["colorSets"].get(color_set) or next(iter(tokens["colorSets"].values()))

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
            "file": original.get(i, str(slide.get("image", ""))),
            "box": box[0] if box else None,
            # 说明文字与版式类型：提示词的「文字」那一栏要用它们说清
            # "画面里不要有字，字由版面排"——这比笼统的负面词有用。
            "caption": slide.get("caption", ""),
            "type": slide.get("type", ""),
            "variant": slide.get("variant", ""),
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


def _aspect_box(w: int, h: int) -> str:
    return f"{w}:{h}（≈{w / h:.2f}:1）"


def build_brief(spec_path: str, out_dir: str, style: str | None = None,
                contract_dir: str | None = None) -> dict:
    """产出提示词契约（人读的 markdown + 机读的 JSON 一起给；后者写进
    contract_dir/assets/requests/，md 由 main() 调 write_brief_md 写）。

    `out_dir` = **图片在哪**（人出的图存这儿；`--check` 也只看这里）；
    `contract_dir` = **合同在哪**
    （缺省同 out_dir）。分开是因为 `--dir` 的本意只是前者 —— 实测踩过：一份
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
    tokens = _load_sibling("render").load_style(style_name)["tokens"]
    label = tokens.get("label", style_name)
    temperature = tokens.get("temperature", "")
    reference = tokens.get("reference", "")

    w = 640 * BRIEF_SCALE
    h = round(w * BRIEF_ASPECT[1] / BRIEF_ASPECT[0])
    # 按**文件名**合并：同一个文件名用在多页是合法的（复用同一张图）。
    # 按**文件**列，不按页列：同一张图被多页共用时，按页列会列三遍，
    # 人会出三张互相覆盖（实测）。
    by_file: dict[str, dict] = {}
    # 槽位 id → 实测槽位 (w, h)。机读合同（assets/requests/）要用数字的宽高比，
    # 不能从 entry["measured"] 那句**给人看的**话里倒着解析 —— 量的时候顺手存。
    measured_px: dict[str, tuple[float, float] | None] = {}
    for page, s in sorted(info["slides"].items()):
        box = s["box"] or {}
        entry = by_file.setdefault(s["file"], {
            "file": s["file"], "pages": [], "titles": [], "bullets": [],
            "target_px": [w, h], "aspect": _aspect_box(*BRIEF_ASPECT), "alpha": False,
            "measured": f"实测槽位 {box['w']:.0f}×{box['h']:.0f}px" if box else "",
            # 「主体 / 场景 / 细节」三栏**故意留空**，交给填的人。
            # 该页标题**不进**提示词（那是擅自补充事实）：
            # 条目往往在讲这份 deck 的叙事（"把现场图处理成两色…"），不是在讲画什么。
            # 规则是"用户未提供且会影响事实准确性的内容不得擅自补充"，所以这里只给
            # **参考材料**（标题/条目/说明文字），不进提示词。
            "caption": s.get("caption", ""), "layout": s.get("type", ""),
        })
        # 与 entry["measured"] 同一条规则：取**首次出现**那页的实测值
        if s["file"] not in measured_px:
            measured_px[s["file"]] = (box["w"], box["h"]) if box else None
        entry["pages"].append(page)
        entry["titles"].append(s["title"])
        entry["bullets"].extend(str(b) for b in s["bullets"][:3])
    slots = [by_file[k] for k in sorted(by_file, key=lambda k: by_file[k]["pages"][0])]
    brief = {
        "style": style_name, "style_label": label, "temperature": temperature,
        "reference": reference, "target_px": [w, h], "aspect": _aspect_box(*BRIEF_ASPECT),
        "slots": slots, "colors": info["colors"],
    }
    # 机读的那一半落盘（人读的 md 由 main() 调 write_brief_md 写）。缺省与图片同目录；
    # `--dir` 指到别处时仍跟着 spec 走 —— 合同与 manifest（render.load_assets）同根。
    _write_asset_requests(brief, measured_px,
                          os.path.join(contract_dir or out_dir, "assets", "requests"))
    return brief


# ═══════════════════════════════════════════════════════════════════════════
# 提示词：按**固定字段顺序**组装，不是把属性堆成一段
#
#        主体 → 场景 → 构图 → 镜头 → 光线 → 色彩 → 风格 → 细节 → 文字 → 限制
#
# 顺序本身就是信息：先让模型明白「画什么」（主体 / 场景），再明白「怎么画」
# （构图 / 镜头 / 光线 / 色彩 / 风格），最后是「绝对不能错」（文字 / 限制）。
# 堆成一段会让"不要细密纹理"这类约束把"主体是什么"淹没 —— 而主体最优先。
#
# 据此定下的三条（每一条都对应一类错法）：
#   · 把"气质"写成一句"观感" → 光和风格混在同一行。现在**拆进各自字段**：
#     光线只讲光源/方向/质感，风格只讲可执行的视觉语言（规则 8 / 10）。
#   · 把尺寸与比例写进 prompt 正文 → API 有独立参数的东西写进去只会打架。
#     现在它们只出现在「参数」栏，明写"不要写进 prompt"（规则 14）。
#   · 负面词是一堆通用 boilerplate（水印 / 界面截图 / 不要额外人物）→ 限制项
#     必须与任务相关。现在只留**与这条管线有关**的：色彩与构图要可用的那些
#     （规则 13）。
#
# 冲突时的优先级（规则 12）：用户明确要求 > 主体准确性 > 文字与品牌准确性 >
# 构图 > 场景 > 光线 > 风格 > 装饰细节。**低优先级的不得破坏高优先级的** ——
# 这条在本流水线里真的有冲突点：风格的强色相（低优先级）不许破坏
# "照片本身要能直接用"（构图 / 色彩级），见「风格」那一栏的写法。
# ═══════════════════════════════════════════════════════════════════════════

# 字段顺序就是优先级顺序，不要调换。
PROMPT_ORDER = ("主体", "场景", "构图", "镜头", "光线", "色彩", "风格", "细节", "文字", "限制")

# **默认不发**的可选字段。规则 6：镜头参数"只有当镜头信息能明显改善画面时才加入"。
# 而"这张图需不需要镜头感"是工具判断不了的 —— 给了默认值，它就永远躺在那儿，
# 等于把"每次都加"当了默认，正好违反规则。所以默认**整行不出现**，需要的人自己插。
OPTIONAL_FIELDS = ("镜头",)
LENS_HINT = {
    "zh": "**要镜头感就自己插一行**，位置在【构图】和【光线】之间，例如："
          "「平视、85mm、浅景深、对焦主体」/「俯拍、广角、大景深、透视强」/「特写、微距」。"
          "不写不等于没有镜头，只是这个判断留给看图的人 —— 工具不知道你这张图需不需要它。",
    "en": "Add a lens line yourself only if it improves the image, between "
          "Composition and Lighting — e.g. 'eye-level, 85mm, shallow depth of field, "
          "focus on the subject'.",
}

# 工具**不知道**、必须由人填的三栏。留空比编一个更负责 —— 规则 7：
# "用户未提供且会影响事实准确性的内容，不得擅自补充"。
FILL = {
    "主体": {
        "zh": "〈写：是什么、几个、主要特征。别写「好看 / 高级 / 漂亮」这类词〉",
        "en": "<what it is / how many / key features. No vague words like "
              "'beautiful', 'premium', 'stunning'>",
    },
    "场景": {
        "zh": "〈写：地点 + 环境氛围（室内/室外、时间、天气）。背景元素要服务于主体〉",
        "en": "<where + atmosphere (indoor/outdoor, time of day, weather). "
              "Background elements must serve the subject>",
    },
    "细节": {
        "zh": "〈可选：材质与质感。产品写金属/玻璃/皮革，场景写地面/墙面/环境细节〉",
        "en": "<optional: materials and texture — metal / glass / leather for "
              "products, ground / wall / environment detail for scenes>",
    },
}

# 气质 → **拆进三个不同字段**。不写风格文献（Massimo Vignelli 那种）：对读文档的人
# 是背景，对生图模型是噪音 —— 它不知道该把"Vignelli"画成什么样。
MOOD = {
    "大胆": {
        "光线": ("戏剧性高对比、方向明确的**单**光源，阴影深而实",
                 "dramatic high-contrast single directional light, deep solid shadows"),
        "色彩": ("高饱和、以深色为主，明暗反差大",
                 "highly saturated, dark-dominant, strong tonal contrast"),
        "风格": ("海报式的强对比，形体简洁有力",
                 "poster-like high contrast, bold simple forms"),
    },
    "安静": {
        "光线": ("均匀柔和的中性日光，没有强烈方向性",
                 "even soft neutral daylight, no strong directionality"),
        "色彩": ("低饱和、色调偏灰，近似单色",
                 "desaturated, greyish, near-monochrome"),
        "风格": ("克制平静、画面干净不杂",
                 "restrained, calm, clean and uncluttered"),
    },
    "中性": {
        "光线": ("自然均衡、方向柔和的日常光",
                 "natural balanced everyday light with soft direction"),
        "色彩": ("自然中性色，不额外引入色相",
                 "natural neutral tones, no added hue"),
        "风格": ("诚实朴素", "plain and honest"),
    },
}


def _mood_row(temperature: str) -> dict:
    for key, row in MOOD.items():
        if key in (temperature or ""):
            return row
    return MOOD["中性"]


def _field_values(slot: dict, brief: dict, lang: str) -> list[tuple[str, str]]:
    """按 PROMPT_ORDER 逐栏给出内容 —— 工具知道的事实，或留给人的空。

    每一栏只讲它该讲的事：构图不谈光线、光线不谈风格。这是"描述顺序统一"能成立的
    前提；混着写的话顺序就名存实亡了。
    """
    zh = lang == "zh"
    palette = brief["colors"]
    mood = _mood_row(brief["temperature"])
    primary = palette["primary"]
    secondary = palette["secondary"]
    paper = palette["background"]
    caption = slot.get("caption") or ""

    composition = _composition_text(slot.get("variant") or "", zh=zh)
    if zh:
        colour = (f"主色 {primary}、辅色 {secondary}、纸色 {paper}；{mood['色彩'][0]}。"
                  f"色系控制在 1~3 个；**靠明暗层次而不靠色相**"
                  f"（图片按原样进产物，不引入色板外的色相）")
        # 风格那一栏只留"可执行的视觉语言"本身："（可执行的视觉语言）"
        # 和"优先于任何装饰性的色彩偏好"是**给读者的规则说明**，
        # 模型会把它当成画面要求 —— 两个读者不能混在一行里。
        style = (f"纪实摄影；{mood['风格'][0]}；靠**大块明暗和强形状**立住"
                 f"（照片会被直接用进版式，只有这些能活下来）")
        # 用户明确禁掉的那件事写在这里：**这一页的信息不许被画进图里**。
        # 一页的信息（标题/条目/数字/示意）一旦烘进图里，它就同时失去可编辑、
        # 可搜索、可翻译、可被读屏器读 —— 而"对方要改字"正是本 skill 出原生
        # PPTX 的理由。图只负责观感。
        text = ("画面里**不要出现任何文字、字母或数字**，也**不要把这一页的信息画进去**"
                "（标题、条目、数字、流程示意、界面截图都不算画面内容）—— "
                "这一页的信息由版面用**真文字**排，图只负责观感；也不要画任何 logo —— "
                "品牌标识由版面另行叠")
        if caption:
            text += f"（这一页的说明文字是「{caption}」，它是**排出来的**，不是画出来的）"
        limits = ("不要：细线、细密网格或织物纹理、柔和渐变、低对比平光"
                  "（这四样塞进版式会糊成一团）；不要多个并列主体或重复主体；"
                  "不要结构变形、过曝、裁切主体；"
                  "**主体收在画面中心 80% 的区域里**（四周各留出 ≥10% 余量）—— "
                  "版面会按槽位比例裁切或留边，贴到边上的主体一定会被切掉")
    else:
        composition = _composition_text(slot.get("variant") or "", zh=False)
        colour = (f"primary {primary}, secondary {secondary}, paper {paper}; "
                  f"{mood['色彩'][1]}. Keep to 1-3 colour families. It ends up as two "
                  f"families; it must read by TONAL RANGE, not by hue "
                  f"(the image goes into the deck as-is, so stay inside the palette)")
        style = (f"documentary photography; {mood['风格'][1]}; it must hold on large "
                 f"tonal masses and strong shapes (fine texture and thin lines do "
                 f"not survive being placed in a slide)")
        text = ("No text, letters or numbers inside the image, and do NOT draw this "
                "page's information into it (no titles, bullet text, numbers, flow "
                "diagrams or UI screenshots) — the layout composes the page's "
                "information as real text; the image only carries look and feel. Do "
                "not draw any logo either — brand marks are placed by the layout")
        if caption:
            text += f" (this page's caption is \u300c{caption}\u300d \u2014 it is composed, " \
                    f"not drawn)"
        limits = ("Avoid: thin lines, fine mesh or woven texture, subtle gradients, "
                  "low-contrast flat light (all four mud up once in the slide); "
                  "multiple competing or duplicated subjects; structural distortion, "
                  "blown highlights, a cropped-off subject; "
                  "keep the subject inside the CENTRAL 80% of the frame (leave a "
                  "margin of at least 10% on every side) \u2014 the layout crops or "
                  "letterboxes to the slot, so anything touching the edge gets cut")

    return [
        ("主体", FILL["主体"][lang]),
        ("场景", FILL["场景"][lang]),
        ("构图", composition),
        ("光线", mood["光线"][0 if zh else 1]),
        ("色彩", colour),
        ("风格", style),
        ("细节", FILL["细节"][lang]),
        ("文字", text),
        ("限制", limits),
    ]


def _composition_text(variant: str, zh: bool) -> str:
    """构图指示按**版式变体**分支（审计发现：写死"只占一栏"对 hero 满幅
    是反指示 —— md:86 的例外在代码里落空）。"""
    if variant == "hero":
        if zh:
            return ("**满幅主角图**：这张图占满整页版面 —— 它是这一页的主角，不是配图。"
                    "**页面下方有实心标题条压图**：视觉重心与关键内容放在**上 2/3**，"
                    "下方留出可被条幅从容覆盖的区域；不需要在图内为文字留白"
                    "（条是实心底，字排在这上面）。")
        return ("FULL-BLEED HERO: this image fills the entire page — it IS this "
                "page's protagonist, not a supporting figure. A solid title bar "
                "overlays the bottom: keep the visual center of gravity in the "
                "UPPER two-thirds and leave the lower third calm enough to be "
                "covered. No text space needed inside the frame (the bar is solid).")
    if zh:
        return ("**一个**主体，占画面 60~70%；轮廓干净、主体与背景分离明确；背景干净不杂。"
                "这张图在版面上**只占一栏** —— 它是配图 / 点缀，**不是整页背景**；"
                "说明文字排在它旁边的另一栏、**不压在图上**，所以不要在图内为文字留白。")
    return ("ONE subject filling 60-70% of the frame; clean silhouette, clear "
            "subject/background separation, uncluttered background. On the slide it "
            "occupies ONE COLUMN only — it is a supporting image, NOT a full-page "
            "background. Its caption sits in a SEPARATE column beside it, never "
            "overlaid, so do NOT reserve space inside the frame for text.")


def _negative_space_text(variant: str) -> str:
    if variant == "hero":
        return ("满幅图：下方实心标题条压图，关键内容放上 2/3；"
                "图内不必为文字留白（条是实心底）")
    return "背景干净不杂；说明文字排在旁边的另一栏、不压在图上，图内不必为文字留白"


def render_prompt(slot: dict, brief: dict, lang: str = "zh") -> str:
    """带字段名的提示词。字段名本身携带顺序与优先级信息，模型读得懂 ——
    比把同样的内容写成一段不分层的话更可控。"""
    lines = []
    for name, value in _field_values(slot, brief, lang):
        lines.append(f"【{name}】{value}")
    return "\n".join(lines)


def api_params(brief: dict) -> list[str]:
    """**不进提示词**的那些 —— API 有独立参数，写进 prompt 只会和参数打架。

    规则 14。这里把它们单列出来，并明写"不要写进 prompt"，否则填的人会顺手
    把尺寸抄回正文里，然后模型既收到参数又收到文字描述，两者冲突时就是随机结果。
    """
    w, h = brief["target_px"]
    return [
        f"尺寸 {w}×{h}px（槽宽 ×2）",
        f"比例 {brief['aspect']}（按页面上声明的 visual.ratio；没写就是槽位缺省 3:2）",
        "数量 1 张",
        "不需要透明通道（整张不透明照片）",
        "质量 / seed 随意 —— 这张图是外部素材，不参与 deck 的确定性渲染",
    ]


def _write_asset_requests(brief: dict, measured_px: dict, requests_dir: str) -> None:
    """写机读的资产请求：`assets/requests/<槽位id>.json`（槽位 id = spec 里的 image 值）。

    manifest（`render.load_assets`，见 references/images.md）是"图已到位"的登记册；
    requests 是它的**上游合同**：`--brief` 自动写，人按 prompt 出图，再把选中的文件
    登记进 manifest —— assetId 就是这里的槽位 id，闭环。schema 封闭 v1，封闭集外的
    字段不许写：{schemaVersion, slide, role, aspect, focal, negative_space, prompt,
    required, note}。
    """
    for slot in brief["slots"]:
        box = measured_px.get(slot["file"])
        note = slot["measured"]
        if slot["caption"]:
            cap = f"说明文字「{slot['caption']}」由版面排"
            note = f"{note}；{cap}" if note else cap
        request = {
            "schemaVersion": 1,
            "slide": slot["pages"],      # 该槽位用到的页（同图复用多页时全列）
            "role": slot["layout"],      # 版式 —— 这个槽位在页里的角色
            "aspect": round(box[0] / box[1], 3) if box else None,   # 实测槽位宽高比
            # focal 留空：画面主体是什么工具不知道 —— 与契约 md 的〈…〉同一条规则，
            # 不许自己编（"用户未提供且会影响事实准确性的内容，不得擅自补充"）。
            "focal": "",
            # negative_space 是工具**知道**的那一半：文字不压在图上，图内不必为文字留白。
            "negative_space": _negative_space_text(slot.get("variant") or ""),
            "prompt": render_prompt(slot, brief, "zh"),
            "required": True,            # 版式要图就必须给图（check 的输入门是阻塞级）
            "note": note,
        }
        deckio.write_json(os.path.join(requests_dir, f"{slot['file']}.json"), request)


def write_brief_md(brief: dict, out_path: str) -> str:
    """契约文档：工具知道的事实 + 给模型的提示词 + 参数栏 + 由人填的空。"""
    lines = [
        "# 图片提示词契约",
        "",
        f"风格 **{brief['style_label']}**（{brief['temperature']}）· 参考 {brief['reference']}",
        "",
        "## 提示词怎么读",
        "",
        "每条提示词按**固定字段顺序**给，这个顺序就是优先级：",
        "",
        "```text",
        "主体 → 场景 → 构图 → 镜头 → 光线 → 色彩 → 风格 → 细节 → 文字 → 限制",
        "```",
        "",
        "先「画什么」（主体 / 场景），再「怎么画」（构图 / 光线 / 色彩 / 风格），",
        "最后是「绝对不能错」（文字 / 限制）。**别把顺序打乱**——堆成一段会让"
        "「不要细密纹理」这种约束把「主体是什么」淹掉，而主体最优先。",
        "",
        "**「镜头」默认不出现**：镜头参数只有在能明显改善画面时才该加，而工具判断不了"
        "你这张图需不需要它 —— 给了默认值就等于每次都加。要加就自己插一行，位置在"
        "【构图】与【光线】之间。",
        "",
        "打架的时候按这个优先级裁决（左边赢）：",
        "",
        "```text",
        "你的明确要求 > 主体准确 > 文字与品牌准确 > 构图 > 场景 > 光线 > 风格 > 装饰细节",
        "```",
        "",
        "**工具能填的已经填好，剩下的 〈…〉 得你来填**：「主体 / 场景 / 细节」这三栏"
        "工具读不到（它只看得见 spec 里的文字）——你写什么就是什么，它不会替你编。"
        "填完把 〈…〉 换掉、按需删掉标了（可选）的行，就是一条可直接发送的完整提示词。",
        "",
        "**尺寸 / 比例 / 数量这些不要写进提示词**：生图 API 有独立参数，"
        "prompt 里再写一遍只会和参数打架。它们单列在每张图的「参数」栏。",
        "",
        "**图在版面上只有两种角色**：**配图**（占一栏）或**点缀**（更小）；连背景那种"
        "大图也不承载这一页的信息。**一页的信息（标题 / 条目 / 数字 / 示意）永远由版面用"
        "真文字排**，不许烘进图里 —— 烘进去就同时失去可编辑、可搜索、可翻译、可被读屏器"
        "读这四件事，而「对方要改字」正是这个 skill 能出原生 PPTX 的理由。"
        "所以**一张图盖住整页是不允许的**（`check.py` 会拦）。",
        "",
        "**这些图会进版式与验收链**（色彩要落在风格色板里）——这是为什么提示词里"
        "反复强调「靠大块明暗和强形状」：靠颜色、细密纹理、细线立住的图会糊成一团。"
        "「限制」栏里只列与这条管线相关的项，没有通用负面词堆砌。",
        "",
        "**出完图存到哪**：与产物（`out.html`）**同一个目录**，文件名逐张见下"
        "（相对路径的产物挪个目录就会全员裂图，所以要同目录交付）。",
        "",
        "---",
        "",
    ]
    for s in brief["slots"]:
        used = "、".join("第 %d 页" % p for p in s["pages"])
        lines += [
            f"## {used} · {' / '.join(s['titles'])}",
            "",
            f"- **文件名**：`{s['file']}`（存到产物同目录，用在 {used}）"
            f"{'；' + s['measured'] if s['measured'] else ''}",
            f"- **用途**：配图（版式 `{s['layout'] or 'content-image'}`）"
            f"{'；说明文字「' + s['caption'] + '」由版面排，**别画进图里**' if s['caption'] else ''}",
            "- **色彩要落在色板内**：不引入色板外的色相（图片按原样进产物，不再做制版处理）",
            "",
            "**工具读得到的参考材料**（是**文字**，不是画面 —— 只帮你回忆这一页在讲什么；"
            "「主体 / 场景 / 细节」仍然要你填）",
            "",
            f"- 标题：{s['titles'][0]}",
            f"- 条目：{'；'.join(s['bullets'][:4]) or '（这一页没有条目）'}"
            if s["bullets"] else "- 条目：（无）",
            "",
            "**中文提示词** —— 把 〈…〉 换成你的内容，可直接发送",
            "",
            "```text",
            render_prompt(s, brief, "zh"),
            "```",
            "",
            "**English prompt**（多数模型对英文更稳）",
            "",
            "```text",
            render_prompt(s, brief, "en"),
            "```",
            "",
            f"📷 {LENS_HINT['zh']}",
            "",
            "**参数**（用 API 参数传，**不要写进 prompt**）",
            "",
        ]
        for item in api_params(brief):
            lines.append(f"- {item}")
        lines.append("")
    lines += [
        "---",
        "",
        "出完图之后：",
        "",
        "```bash",
        "python3 scripts/image_source.py --check your.spec.json    # 验尺寸与比例对不对",
        "python3 scripts/check.py your.spec.json out.html          # 渲完再过校验门",
        "```",
        "",
        "尺寸不对不是「将就一下」的事：**被放大渲染的图一定糊**，而交付前那条提示"
        "（`check.py` 的放大检查）就是为它准备的。",
        "",
        "**还要人眼看三条**（脚本查不出画面内容，只有你能看）：",
        "",
        "1. **主体在不在中心 80% 区域内** —— 版面按槽位裁切（照片）或留边（结构图），"
        "贴边的主体一定被切；",
        "2. **画面里有没有文字 / 数字** —— 有就重出（这一页的字由版面排）；",
        "3. **结构图有没有被压扁** —— 结构图的比例写进 `visual.ratio`（如 `4:3`），"
        "写了就按它留边，别硬塞进 3:2。",
    ]
    deckio.write_text(out_path, "\n".join(lines) + "\n")
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
    for page, slide in enumerate(spec.get("deck", {}).get("slides", []), 1):
        name = slide.get("image")
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
    want_w = 640 * BRIEF_SCALE
    problems: list[str] = []
    notes: list[str] = []
    for name, page in sorted(wanted.items(), key=lambda kv: kv[1]):
        path = os.path.join(out_dir, name)
        if not os.path.isfile(path):
            problems.append(f"第 {page} 页：`{name}` 不在 {out_dir} —— 还没出图")
            continue
        size = image_size(path)
        if size is None:
            notes.append(f"第 {page} 页：`{name}` 读不出尺寸（不是常见图片格式？）"
                         f" —— 尺寸与比例都没法验")
            continue
        w, h = size
        if path.lower().endswith(".svg"):
            notes.append(f"第 {page} 页：`{name}` 是**矢量图**（SVG）—— 不做放大检查"
                         f"（放多大都不糊）；比例按 viewBox {w}×{h} 算")
        elif w < want_w:
            problems.append(
                f"第 {page} 页：`{name}` 只有 {w}px 宽，契约要 {want_w}px —— "
                f"放进版面会被放大渲染（会糊）")
        ratio_want = want_ratio.get(name, BRIEF_ASPECT[0] / BRIEF_ASPECT[1])
        ratio_got = w / h
        if abs(ratio_got - ratio_want) > 0.12:
            notes.append(
                f"第 {page} 页：`{name}` 是 {ratio_got:.2f}:1，槽位要 {ratio_want:.2f}:1"
                f" —— **不用为比例重出图**：渲染按槽位比例定高度，照片按中心裁切"
                f"（cover）、结构图留边不裁（contain，按 spec 的 visual.kind 选）。"
                f"只要主体不贴边、画面里没有文字，裁切看不出来")
    return (1 if problems else 0, problems, notes)

def _parse_size(raw: str) -> tuple[int, int]:
    """`WxH` → (w, h)。格式不对要说清楚哪里不对，不甩生成器报错。"""
    parts = raw.lower().split("x")
    if len(parts) != 2:
        raise SystemExit(f"✗ --size 要写成 WxH（如 640x400），收到 {raw!r}")
    return (round(deckio.as_number(parts[0], f"--size 的宽（{raw!r}）")),
            round(deckio.as_number(parts[1], f"--size 的高（{raw!r}）")))


def _temp_dir_note(path: str) -> str | None:
    """deck 建在临时目录里 → 说一声（不阻塞）。

    为什么必须开口：提示词合同是**要交给用户去执行**的东西（他拿它去出图），
    落在 /tmp 里重启就没了。实测踩过：一份 17 页 deck 的 spec / 风格 / 提示词
    全在 /tmp/dir-*，用户手上只有一段对话，那份合同等于没产出。
    """
    real = os.path.realpath(path).rstrip(os.sep) + os.sep
    temp_root = os.path.realpath(tempfile.gettempdir()).rstrip(os.sep) + os.sep
    if real.startswith(temp_root) or real.startswith("/private/tmp/"):
        return (f"⚠️ deck 项目在临时目录里：{path}\n"
                f"   spec / 风格 / 素材 / 提示词合同都该在**项目目录**（随项目交付）——\n"
                f"   临时目录重启即失，用户也就拿不到这份要他执行的提示词。")
    return None


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description="图片来源两条路：**写契约给人出图（--brief，默认）** / 调你的生图命令（--provider-cmd）")
    # 两条路各自的入口：
    #   --brief 推荐（人出图）· --check 验人交付的图 · --prompt+--provider-cmd 给有 API 的人
    ap.add_argument("--brief", default=None, metavar="SPEC",
                    help="从这份 spec 生成**图片提示词契约**（人拿它去出图）")
    ap.add_argument("--check", default=None, metavar="SPEC",
                    help="验人交付的图：在不在 / 够不够大 / 比例对不对")
    ap.add_argument("--prompt", default=None, help="出图用的提示词（配合 --provider-cmd）")
    ap.add_argument("-o", "--out", default=None, help="输出文件（--brief 缺省写 spec 同目录）")
    ap.add_argument("--dir", default=None,
                    help="**图片**所在的目录（缺省：spec 所在目录）—— 只管图片："
                         "提示词合同与 requests 始终写在 spec 同目录")
    ap.add_argument("--style", default=None, help="风格（缺省读 spec 的 deck.style）")
    ap.add_argument("--tokens", default=None,
                    help="风格 tokens 路径（缺省按 spec 的 deck.style 解析）")
    # 色板名不写死：写死会在换风格 / 改色板名时**静默过期**——实测踩过两次
    # （plate.py 与这里都留着 riso 时代那个已经删掉的 'vivid'，于是默认路径直接崩）。
    ap.add_argument("--color-set", default=None, help="色板（缺省用该 token 的第一个）")
    ap.add_argument("--size", default="640x400")
    ap.add_argument("--json", action="store_true", help="--brief 时额外输出机读 JSON")
    ap.add_argument("--provider-cmd", default=None,
                    help="生图命令，用 {prompt} 与 {out} 占位；不给就拒绝："
                         "脚本不自己画图，改用 --brief 拿提示词")
    args = ap.parse_args(argv[1:])

    if args.brief:
        # 合同（md + requests）落 **spec 所在目录**；`--dir` 只管图片在哪（实测踩过：
        # 提示词被 --dir 搬进 /tmp，用户拿不到）。
        spec_dir = os.path.dirname(os.path.abspath(args.brief))
        out_dir = args.dir or spec_dir
        brief = build_brief(args.brief, out_dir, args.style, contract_dir=spec_dir)
        target = args.out or os.path.join(spec_dir, "image-brief.md")
        write_brief_md(brief, target)
        print(f"✓ 图片提示词契约 → {target}")
        print(f"  {len(brief['slots'])} 个槽位 · 统一规格 "
              f"{brief['target_px'][0]}×{brief['target_px'][1]}px · {brief['aspect']}")
        print(f"  出完图存到：{out_dir}（按上面的文件名）")
        print(f"  存好后验一遍：image_source.py --check {args.brief}")
        note = _temp_dir_note(spec_dir)
        if note:
            print(note)
        if args.json:
            import json   # noqa: PLC0415

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

    if not args.prompt or not args.out:
        raise SystemExit("✗ 要么给 --brief/--check（推荐），要么给 --prompt 与 -o（需要 --provider-cmd）")
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
