#!/usr/bin/env python3
"""图片：**先把提示词写成契约，再用它出图**。

三条路径，同一条提示词：

1. `--brief` → 契约（`image-brief.md` + `assets/requests/*.json`）—— 不花钱；
2. `--generate` → 按契约逐槽位出图。**配了就直连**：给了 `--provider-cmd` 用你的命令，
   没给但设了 `MINIMAX_API_KEY`（或 `MINIMAX_CN_API_KEY`）就用内置 MiniMax；
   两边都没有就明确告诉你手动出图、放到哪个目录；
3. `--check` → 验图：在不在 / 够不够大 / 比例合不合（比例只说明，不阴塞）。

图只从**你的模型**来：这个脚本不画图（没有拼贴、没有占位图兜底），生图失败也不降级
—— 否则交付里会混进一张没人认领的图。
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import importlib.util
import io
import json
import math
import os
import random
import re
import shlex
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

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
    return os.path.expanduser(os.path.join("~", ".cache", "agent-skills", "deck-images"))


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


# ── 生图后端：内置 MiniMax ────────────────────────────────────────────────
# 接口事实（与本机 `minimax-mcp` 自己发的请求一致）：
#   POST {host}/v1/image_generation
#   Authorization: Bearer <key>
#   {model, prompt, aspect_ratio, n, prompt_optimizer, response_format}
#   → {"data": {"image_urls": [...]}}（另有 base_resp.status_code 报错用）
# 只读环境变量，不写任何配置文件：密钥不落盘、不进仓库。
MINIMAX_HOST_DEFAULT = "https://api.minimaxi.com"
MINIMAX_MODEL_DEFAULT = "image-01"
# 官方只认这八档；我们的比例是**实测槽位**算出来的，不一定正好命中 —— 所以取最近一档
# （比例本来就不阻塞交付：渲染层按槽位裁切/留边，见 check_images 的说明）。
MINIMAX_RATIOS = ((1, 1), (16, 9), (4, 3), (3, 2), (2, 3), (3, 4), (9, 16), (21, 9))
MINIMAX_TIMEOUT = 180
# 提示词里没填的主体：中文用 〈…〉、英文用 <…> —— 两种都要拦，
# 否则"没填的模板"会原样发给模型（发出去就是花真钱买一张模板画）。
PLACEHOLDER_RE = re.compile(r"〈[^〉]*〉|<[^<>]*>")


def minimax_key() -> str | None:
    """配了就用。两个名字都认：`MINIMAX_API_KEY` 是 MCP 自己用的，
    `MINIMAX_CN_API_KEY` 是本机把它套进 MCP 时用的那个（同一把密钥）。"""
    for name in ("MINIMAX_API_KEY", "MINIMAX_CN_API_KEY"):
        value = os.environ.get(name)
        if value:
            return value
    return None


def _http_url(url: str) -> str:
    """只允许 http/https。两个 URL 都不是我们能控制的东西 —— `MINIMAX_API_HOST` 来自
    环境变量、图片 URL 来自远端响应 —— 不校验 scheme 的话，`file:` 这类会去读本机文件。
    """
    if not url.startswith(("http://", "https://")):
        raise SystemExit(f"✗ 只接受 http/https 的 URL：{url[:80]}")
    return url


def minimax_ratio(aspect: float | None) -> str:
    """槽位比例 → 官方八档里最近的一档（按对数距离，因为比例是乘性的）。"""
    if not aspect or aspect <= 0:
        aspect = BRIEF_ASPECT[0] / BRIEF_ASPECT[1]
    best = min(MINIMAX_RATIOS,
               key=lambda r: abs(math.log((r[0] / r[1]) / aspect)))
    return f"{best[0]}:{best[1]}"


def minimax_generate(prompt: str, aspect: float | None, out: str) -> None:
    """调 MiniMax 出一张图，写成 `out`。失败直接抛（**没有降级产物**）。"""
    key = minimax_key()
    if not key:
        raise SystemExit(
            "✗ 没配 MiniMax 密钥 —— 不知道拿谁出图。\n"
            "  要么给 --provider-cmd，要么设 MINIMAX_API_KEY（或 MINIMAX_CN_API_KEY）。")
    host = (os.environ.get("MINIMAX_API_HOST") or MINIMAX_HOST_DEFAULT).rstrip("/")
    model = os.environ.get("MINIMAX_IMAGE_MODEL") or MINIMAX_MODEL_DEFAULT
    payload = {
        "model": model,
        "prompt": prompt,
        "aspect_ratio": minimax_ratio(aspect),
        "n": 1,
        "prompt_optimizer": True,
        "response_format": "url",
    }
    req = urllib.request.Request(  # noqa: S310 (scheme 已由 _http_url 校验)
        _http_url(f"{host}/v1/image_generation"),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=MINIMAX_TIMEOUT) as resp:  # noqa: S310 (scheme 已校验)
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:200]
        raise SystemExit(f"✗ MiniMax 生图失败（HTTP {exc.code}）：{detail}\n"
                         f"  {_no_fallback_hint()}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise SystemExit(f"✗ MiniMax 生图失败（{exc}）：{host}\n"
                         f"  {_no_fallback_hint()}") from exc
    # MiniMax 的错误通常走 base_resp（HTTP 200 但业务码非 0，例如密钥错 2049）
    base = body.get("base_resp") or {}
    if base.get("status_code"):
        raise SystemExit(f"✗ MiniMax 生图失败（{base.get('status_code')}）："
                         f"{base.get('status_msg')}\n  {_no_fallback_hint()}")
    urls = ((body.get("data") or {}).get("image_urls") or [])
    if not urls:
        raise SystemExit(f"✗ MiniMax 没返回图（响应里没有 data.image_urls）："
                         f"{json.dumps(body)[:200]}\n  {_no_fallback_hint()}")
    try:
        with urllib.request.urlopen(_http_url(urls[0]), timeout=MINIMAX_TIMEOUT) as resp:  # noqa: S310
            blob = resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        raise SystemExit(f"✗ 图生成了但下载失败：{exc}\n  {_no_fallback_hint()}") from exc
    # 先解一遍再落盘：写不出来的字节留在那里，下游只会说"图片没加载"
    try:
        with Image.open(io.BytesIO(blob)) as probe:
            probe.verify()
    except OSError as exc:
        raise SystemExit(f"✗ 下回来的不是能解码的图（{exc}）\n  {_no_fallback_hint()}") from exc
    deckio.ensure_dir(os.path.dirname(os.path.abspath(out)) or ".")
    try:
        with open(out, "wb") as fh:
            fh.write(blob)
    except OSError as exc:
        raise SystemExit(f"✗ 写不了 {out}：{exc}") from exc
    print(f"✓ MiniMax 出图（{payload['aspect_ratio']}）")


def _no_fallback_hint() -> str:
    """生图失败时固定给的那句：不兜底，但告诉你下一步走哪条路。"""
    return ("没有降级产物：图只从你的模型来。手动出的路：按 image-brief.md 的提示词"
            "出图 → 存到 spec 同目录 → image_source.py --check <spec>")


def resolve(prompt: str, colors: dict, size: tuple[int, int], out: str,
            provider_cmd: str | None = None, aspect: float | None = None) -> str:
    """拿到一张图写到 `out`，返回来源（`cache` / `generated`）。

    三条路，按优先级：缓存 → `--provider-cmd`（你的命令）→ 内置 MiniMax（配了密钥时）。
    都没有就**拒绝**并说清手动怎么走 —— 这个工具不自己画图，也没有降级产物：
    一张脚本拼的图混进交付，比交付里缺一张图更坏（没人认领它）。
    """
    deckio.ensure_dir(cache_dir())
    path = os.path.join(cache_dir(), f"{cache_key(prompt, colors, size)}.png")
    if os.path.isfile(path):
        # 缓存命中即可信：key 里已经含 prompt + 色板 + 尺寸，同一把 key 就是同一张图。
        # 照片本来就有千百种颜色，拿"只在色板三角形内"去量它只会把好图判死
        # （v4 删掉制版后处理时这道判据就该一起删）—— 色彩约束由 --brief 的提示词承担。
        _save_image_copy(path, out)
        print(f"✓ 命中缓存（{os.path.basename(path)}）→ {out}")
        return "cache"
    if provider_cmd:
        try:
            subprocess.run(_provider_argv(provider_cmd, prompt, path), check=True)
        except subprocess.CalledProcessError as exc:
            raise SystemExit(f"✗ 生图失败（返回码 {exc.returncode}）—— 没有降级产物："
                             f"图只从你的模型来，脚本不兜底") from exc
    elif minimax_key():
        # 配了就直连：密钥在环境变量里（不落盘、不进仓库）
        minimax_generate(prompt, aspect, path)
    else:
        raise SystemExit(
            "✗ 没配生图后端，这一步出不了图。两条路：\n"
            "  1. 手动：拿 `--brief` 的提示词出图 → 存到 spec 同目录 → `--check` 验一遍；\n"
            "  2. 直连：--provider-cmd '你的命令 --prompt {prompt} --out {out}'，"
            "或设 MINIMAX_API_KEY / MINIMAX_CN_API_KEY 用内置 MiniMax。")
    # 没有制版处理这一层（双色调 / 半调网点都不做）—— 图片按原样使用。
    # 想要版画质感就在出图提示词里要（`--brief` 的构图/负空间字段），而不是
    # 在交付链里做一道后处理：后处理会让"check 说合规、交付图却不一样"。
    _save_image_copy(path, out)
    print(f"✓ 已写出 {out}（来源：{_provider_label(provider_cmd)}，已缓存为 "
          f"{os.path.basename(path)}）")
    return "generated"


def _save_image_copy(source: str, target: str) -> None:
    """Keep provider pixels, including transparency, when copying a cached image."""
    with Image.open(source) as image:
        has_alpha = image.mode in ("RGBA", "LA") or "transparency" in image.info
        converted = image.convert("RGBA" if has_alpha else "RGB")
        if has_alpha and converted.getchannel("A").getextrema()[1] == 0:
            raise SystemExit("✗ 图片完全透明，没有可见内容，不能作为完成素材")
        if has_alpha and os.path.splitext(target)[1].lower() in (".jpg", ".jpeg"):
            if converted.getchannel("A").getextrema()[0] < 255:
                raise SystemExit("✗ 透明图片不能写成 JPEG；请将图片文件名改为 PNG 或 WebP")
            converted = converted.convert("RGB")
        converted.save(target)


def _has_transparency(path: str) -> bool:
    try:
        with Image.open(path) as image:
            return image.convert("RGBA").getchannel("A").getextrema()[0] < 255
    except (OSError, ValueError):
        return False


def _is_fully_transparent(path: str) -> bool:
    try:
        with Image.open(path) as image:
            return image.convert("RGBA").getchannel("A").getextrema()[1] == 0
    except (OSError, ValueError):
        return False



# ═══════════════════════════════════════════════════════════════════════════
# 取图策略：**写清契约，再由人（或配好的后端）出图**
#
# 为什么契约放在第一位：脚本擅长的不是画图，是"知道每张图放进哪个槽位、那个槽位实测
# 多少像素、它会被版式怎么裁"—— 这些模型不会自己知道。所以主路径是：
#
#     **脚本写契约与提示词 → 出图（人或配好的后端）→ 脚本再验一遍**
#
# 出图的两条路（`--generate`）：`--provider-cmd` 给有生图命令的人；没给就用内置
# MiniMax（配了 MINIMAX_API_KEY / MINIMAX_CN_API_KEY 时）。都没配时**不装作能做**：
# 说清手动路径与要放的目录，而不是产一张脚本拼的图混进交付。
# ═══════════════════════════════════════════════════════════════════════════

# 图片槽位的目标倍率：2x。与 shots.py 的 --force-device-scale-factor=2 同一个理由 ——
# 投影与打印都不糊。1x 在屏幕上勉强够，投到大屏就是糊的。
BRIEF_SCALE = 2

# 宽度差这么一点点不算问题。为什么要有这个容差：生图服务每个比例给的是**固定像素**，
# 未必正好够我们要的宽度 —— 官方 MiniMax 的 3:2 是 1248×832，比 1280 少 2.5%；
# 而把这种本来能用的图判成"会糊"，整条链就卡在一张没毛病的图上。
# 差得多的（> 5%）仍然是阻塞项：那道门的本意是"别拿缩略图当大图"。
SIZE_TOLERANCE = 0.05

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

    单独抽出来是因为缓存 key 含色板：`--brief` 与 `--generate` 必须算出**同一把**
    key，否则同一张图会被重复付费生成一遍。
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
    alpha_note = ("需要真实透明通道；选择支持透明输出的后端和 PNG/WebP 格式" if transparent is True else
                  "不透明背景" if transparent is False else
                  "透明通道未指定；不预设图片媒介或背景")
    return [f"尺寸 {w}×{h}px（按所有实测图位 ×{BRIEF_SCALE}）",
            f"比例 {brief['aspect']}（来自实测尺寸）", "数量 1 张", alpha_note,
            "质量 / seed 按本次后端与复现需要设置"]


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
             f"项目风格：{brief['style_label']}。风格参考：{brief['reference'] or '未提供'}。", "",
             f"页面色板参考：{json.dumps(brief['colors'], ensure_ascii=False)}。"
             "这是页面上下文，不限定照片、插画或证据素材的颜色数量。", "",
             "用途、主体、构图、风格、焦点、文字安全区与透明要求来自可选的 visual.imageBrief。"
             "只填写本次需要的项；没有声明的媒介、光线、色彩和背景不自动补成固定风格。", "",
             "〈…〉或 <…> 是尚未明确的主体，生成前需要填写。页面标题、条目和图注仅作为参考材料，"
             "不会自动画进图中；确实需要图内文字时，在主体或构图中给出准确文案。"
             "需要真实截图或事实证据时使用原始素材。", "",
             "尺寸、比例、数量优先作为后端参数传递，不要写进 prompt 造成冲突；"
             "后端只接收提示词时应将参数一并提供。焦点和安全区是生图指导，不会自动改写页面 CSS。", ""]
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
    lines += ["生成后运行 `image_source.py --check <spec>`，再检查实际页面与最终导出。", "",
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

def _provider_label(provider_cmd: str | None) -> str:
    """说清这一轮**拿谁**出图 —— 生图是花钱的一步，用哪个后端要写明白。"""
    if provider_cmd:
        return "你的命令（--provider-cmd）"
    if minimax_key():
        model = os.environ.get("MINIMAX_IMAGE_MODEL") or MINIMAX_MODEL_DEFAULT
        return f"内置 MiniMax（{model}）"
    return "没配"


def generate_images(spec_path: str, out_dir: str, style: str | None = None,
                    provider_cmd: str | None = None,
                    contract_dir: str | None = None) -> tuple[int, list[str], list[str]]:
    """按契约里**填好的**提示词逐槽位出图。返回 `(退出码, 已出, 说明)`。

    提示词从 `assets/requests/<文件名>.json` 的 `prompt` 读 —— 那是契约，也是人
    填完的版本。**这一步只读契约、只写图**：不重新生成模板（那会把填好的内容
    覆盖回占位符），也不重新渲一遍量一遍（契约里的 `aspect` 就是实测槽位比例）。

    “还没填”不是错误而是**阻塞**：把模板（或带 〈…〉/<…> 的文本）发给模型，
    只会得到一张模板画，钱是真花了。所以报错要指明**填哪个文件**。

    没配后端时**动手前一次说清两条路**（手动 / 直连），不在循环里每张抛一次。
    已存在的文件不覆盖（可能是人手出的好图，也可能是上次已付过费的图）——
    要重出就把它删掉。
    """
    if not provider_cmd and not minimax_key():
        contract = os.path.join(contract_dir or out_dir, "image-brief.md")
        raise SystemExit(
            f"✗ 没配生图后端，一步都没跑。两条路：\n"
            f"  1. 手动：按 {contract} 的提示词出图 → 存到 {out_dir}/<契约里的文件名>"
            f" → `--check` 验一遍；\n"
            f"  2. 直连：--provider-cmd '你的命令 --prompt {{prompt}} --out {{out}}'，"
            f"或设 MINIMAX_API_KEY / MINIMAX_CN_API_KEY（内置 MiniMax，"
            f"{MINIMAX_MODEL_DEFAULT}）")
    req_dir = os.path.join(contract_dir or os.path.dirname(os.path.abspath(spec_path)),
                           "assets", "requests")
    reqs = sorted(glob.glob(os.path.join(req_dir, "*.json")))
    if not reqs:
        raise SystemExit(f"✗ {req_dir} 里没有契约 —— 先跑 `--brief "
                         f"{os.path.basename(spec_path)}` 生成契约与提示词")
    # 与 --brief 同一把缓存 key（色板 + 尺寸都取同一套），重跑不重复付费
    spec_deck = deckio.read_json(spec_path).get("deck", {})
    tokens = _load_sibling("render").load_style(
        style or spec_deck.get("style"),
        os.path.dirname(os.path.abspath(spec_path)))["tokens"]
    colors = _pick_colors(spec_deck, tokens)
    print(f"· {_provider_label(provider_cmd)}：{len(reqs)} 个槽位 · 每槽 1 张")
    done: list[str] = []
    blocked: list[str] = []
    notes: list[str] = []
    for req_path in reqs:
        name = os.path.basename(req_path)[: -len(".json")]
        target = os.path.join(out_dir, name)
        request = deckio.read_json(req_path)
        transparent = request.get("transparent")
        if "transparent" in request and not isinstance(transparent, bool):
            blocked.append(f"{name}：transparent 必须是布尔值")
            continue
        if os.path.isfile(target):
            if _is_fully_transparent(target):
                blocked.append(f"{name}：已有文件完全透明，没有可见内容，保留文件供检查")
                continue
            if transparent is not None and _has_transparency(target) != transparent:
                blocked.append(f"{name}：已有文件不满足透明要求，保留文件供检查；请替换合格素材")
                continue
            notes.append(f"{name}：已存在，跳过（要重出就删掉它）")
            continue
        target_px = request.get("target_px")
        if not (isinstance(target_px, list) and len(target_px) == 2
                and all(isinstance(v, (int, float)) and v > 0 for v in target_px)):
            # 兼容旧合同；新 --brief 总是携带真实尺寸。
            width = 640 * BRIEF_SCALE
            target_px = [width, round(width / (request.get("aspect") or 1.5))]
        size = tuple(math.ceil(v) for v in target_px)
        prompt = str(request.get("prompt") or "").strip()
        blanks = PLACEHOLDER_RE.findall(prompt)
        if not prompt or blanks:
            blocked.append(
                f"{name}：提示词还没填（{blanks[0] if blanks else '空'}）—— 把 "
                f"{os.path.relpath(req_path)} 的 prompt 里 〈…〉/ <…> 换成内容")
            continue
        aspect = request.get("aspect")
        how = resolve(prompt, colors, size, target, provider_cmd,
                      aspect=aspect if isinstance(aspect, (int, float)) else None)
        if transparent is not None and _has_transparency(target) != transparent:
            blocked.append(f"{name}：生成图片不满足透明要求；请换用支持所需背景的后端或提供合格素材")
            continue
        done.append(f"{name}（{how} → {minimax_ratio(aspect)}）")
    return (1 if blocked else 0, done, notes + blocked)


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
        description="图片来源：写契约→出图（人，或配好的后端走 --generate）；"
                    "脚本不手画图，也没有降级产物")
    # 两条路各自的入口：
    #   --brief 推荐（人出图）· --check 验人交付的图 · --prompt+--provider-cmd 给有 API 的人
    ap.add_argument("--generate", default=None, metavar="SPEC",
                    help="按契约里的提示词出图（**要花钱**，只有显式给这个参数才会调）："
                         "给了 --provider-cmd 用它；否则用内置 MiniMax（需 "
                         "MINIMAX_API_KEY / MINIMAX_CN_API_KEY）；都没配就说清手动怎么走")
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
    # 色板名不写死：写死会在换风格 / 改色板名时**静默过期**。
    # 缺省取该 token 的第一套。
    ap.add_argument("--color-set", default=None, help="色板（缺省用该 token 的第一个）")
    ap.add_argument("--size", default="640x400")
    ap.add_argument("--json", action="store_true", help="--brief 时额外输出机读 JSON")
    ap.add_argument("--provider-cmd", default=None,
                    help="生图命令，用 {prompt} 与 {out} 占位（不过 shell）；"
                         "不给就用内置 MiniMax（配了密钥时），都没配就拒绝")
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

    if args.generate:
        # 与 --brief 同一套口径：图片在 `--dir` 或 spec 同目录；契约始终在 spec 同目录
        spec_dir = os.path.dirname(os.path.abspath(args.generate))
        out_dir = args.dir or spec_dir
        code, done, notes = generate_images(args.generate, out_dir, args.style,
                                           provider_cmd=args.provider_cmd,
                                           contract_dir=spec_dir)
        for line in done:
            print(f"  ✓ {line}")
        for line in notes:
            print(f"  · {line}")
        if done:
            print(f"\n✓ 出了 {len(done)} 张 → {out_dir}")
            print(f"  验一遍：image_source.py --check {args.generate}")
        return code

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
        raise SystemExit("✗ 要么给 --brief/--generate/--check（推荐），"
                         "要么给 --prompt 与 -o")
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
