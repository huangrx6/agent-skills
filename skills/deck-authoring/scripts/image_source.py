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


def _parse_size(raw: str) -> tuple[int, int]:
    """`WxH` → (w, h)。格式不对要说清楚哪里不对，不甩生成器报错。"""
    parts = raw.lower().split("x")
    if len(parts) != 2:
        raise SystemExit(f"✗ --size 要写成 WxH（如 640x400），收到 {raw!r}")
    return (round(deckio.as_number(parts[0], f"--size 的宽（{raw!r}）")),
            round(deckio.as_number(parts[1], f"--size 的高（{raw!r}）")))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="图片来源：缓存 / 生图 / 几何色块拼贴")
    ap.add_argument("--prompt", required=True)
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--tokens", default=os.path.join(HERE, "..", "styles", "swiss-grid", "style.json"))
    ap.add_argument("--color-set", default="vivid")
    ap.add_argument("--size", default="640x400")
    ap.add_argument("--provider-cmd", default=None,
                    help="可选的生图命令，用 {prompt} 与 {out} 占位；不填就用色块拼贴")
    args = ap.parse_args(argv[1:])
    tokens = deckio.read_json(args.tokens)
    colors = tokens["colorSets"][args.color_set]
    resolve(args.prompt, colors, _parse_size(args.size), args.out, args.provider_cmd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
