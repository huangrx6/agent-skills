#!/usr/bin/env python3
"""图片来源：prompt 缓存 → 生图（可选，未配置则跳过）→ **几何色块拼贴**。

为什么默认是色块而不是生图：生图是全流程最慢、最贵、最容易失败的一环（方案第 5 层自己
写的），而方案第一条原则是"视觉效果优先用 CSS/SVG 原生能力，不靠生图模型硬画"。
所以几何色块拼贴在这里是**一等公民**，生图只是一个可选来源 —— 而且两件事必须做到：

1. **降级要说出来**：静默换成色块，用的人会以为图是模型画的 ✗
2. **缓存里的东西也要合规范**：缓存命中不等于可信 —— 上一次留下的可能根本不合规，
   所以命中后仍然要过"只在色板三角形内"这条不变量（实测能抓到：往里塞一张彩图就红）

跑法：python3 image_source.py --prompt "team photo, riso" -o pic.png [--provider-cmd "…"]
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import random
import subprocess
import sys

from PIL import Image, ImageDraw

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


ink = _load_sibling("ink")
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

    它自己也必须是 riso 的（方案 §5.2 原话：不能用无风格的灰色占位图）。
    """
    w, h = size
    image = Image.new("L", size, 255)
    draw = ImageDraw.Draw(image)
    r = random.Random(seed)
    for _ in range(r.randint(3, 5)):
        radius = r.randint(int(min(w, h) * 0.18), int(min(w, h) * 0.42))
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
    hues = {c for _, c in (image.getcolors(maxcolors=1 << 20) or [])}
    return [c for c in hues if not treat_image._in_triangle(c, *tri, tol=tol)]


def resolve(prompt: str, colors: dict, size: tuple[int, int], out: str,
            provider_cmd: str | None = None) -> str:
    os.makedirs(cache_dir(), exist_ok=True)
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
            subprocess.run(provider_cmd.format(prompt=prompt, out=path), shell=True, check=True)
            source = "generated"
        except subprocess.CalledProcessError as exc:
            print(f"✗ 生图失败（{exc.returncode}）→ 降级为几何色块拼贴")
    else:
        print("· 未配置生图（--provider-cmd）→ 用几何色块拼贴（它本身就是 riso 的，不是灰占位图）")
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


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="图片来源：缓存 / 生图 / 几何色块拼贴")
    ap.add_argument("--prompt", required=True)
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--tokens", default=os.path.join(HERE, "..", "styles", "risograph", "style.json"))
    ap.add_argument("--color-set", default="vivid")
    ap.add_argument("--size", default="640x400")
    ap.add_argument("--provider-cmd", default=None,
                    help="可选的生图命令，用 {prompt} 与 {out} 占位；不填就用色块拼贴")
    args = ap.parse_args(argv[1:])
    tokens = json.load(open(args.tokens, encoding="utf-8"))
    colors = tokens["colorSets"][args.color_set]
    w, h = (int(x) for x in args.size.lower().split("x"))
    resolve(args.prompt, colors, (w, h), args.out, args.provider_cmd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
