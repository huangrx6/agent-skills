#!/usr/bin/env python3
"""图片 → riso 可用的图：duotone（只映射到两个专色）+ 半调网点。

为什么必须有这一层：随手一张彩照贴进 riso 版式里会**立刻露馅**（方案 §2 图文页那条）。
真实孔版印刷的图是网点密度表现灰度、只有两个专色的 —— 所以这里是"重新制版"，
不是"加个滤镜"：先把图变灰度，再把灰度映射到 两墨叠印 的色阶上，最后叠半调网点。

跑法：python3 plate.py in.jpg -o out.png --tokens styles/swiss-grid/style.json --color-set vivid
     python3 plate.py --sample -o sample.png            # 没有真图时生成一张测试卡
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys

from PIL import Image, ImageDraw, ImageOps

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
deckio = _load_sibling("deckio")   # IO 收口：读不到 token 要报清楚，不甩 traceback


def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def duotone(image: Image.Image, primary: str, secondary: str, paper: str,
            dots: int = 4) -> Image.Image:
    """灰度 → 两墨色阶（暗处=叠印，亮处=纸），再叠一层半调网点。"""
    gray = ImageOps.grayscale(image)
    dark = _rgb(ink.overprint(primary, secondary))
    paper_rgb = _rgb(paper)
    # 色阶：白 → 纸色，黑 → 叠印墨色（中间线性过渡 = 网点密度的连续近似）
    # 色阶：白 → 纸色，黑 → 叠印墨色（中间线性过渡 = 网点密度的连续近似）
    # 用 256 项 LUT 而不是 lambda：point() 的 callable 形式每个像素都要回转进 Python，
    # 而且类型上也说不清；LUT 一次算好、之后走 C 层。
    lut = [[round(dark[i] + (paper_rgb[i] - dark[i]) * t / 255) for t in range(256)]
           for i in range(3)]
    out = Image.merge("RGB", [gray.point(lut[i]) for i in range(3)])
    # 半调：**有序抖动**（Bayer 4×4）。
    # 我第一版写成 `if v < 128: 每个像素都打点 else 棋盘格` ✗ —— 结果是"暗处实心、
    # 128 以上密度全都一样"，等于没有连续调（实测：光/中调区域平滑无网点 ✗）。
    # 真网点要让**密度随灰度连续变化**：用阈值矩阵逐子像素比较，16 级密度。
    matrix = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]
    if dots > 0:
        # 在**输出分辨率**上直接打点：单元 `dots`×`dots`，阈值取自 Bayer 4×4 矩阵 ——
        # 于是"点的大小"由 dots 定、"点的密度"随灰度连续变。
        # 前一版把 dots 倍放大的 mask 又 LANCZOS 缩回原尺寸 ✗ → 网点被平均成平滑色块
        # （实测光/中调区域 100px 内只有 1~3 段颜色 ✓ 平滑 ✗）—— 那才是"看不见网点"的真因。
        w, h = gray.size
        mask = Image.new("L", (w, h), 255)
        load = mask.load()
        source = gray.load()
        if load is None or source is None:
            raise SystemExit("✗ 拿不到像素访问器（Pillow 返回 None）")
        for y in range(h):
            by = (y // dots) % 4
            for x in range(w):
                v = source[x, y]
                # 灰度图（"L"）的像素一定是标量；这里收窄类型，不是运行时分支。
                if not isinstance(v, (int, float)):
                    continue
                if v < (matrix[by][(x // dots) % 4] + 0.5) / 16 * 255:
                    load[x, y] = 0
        out = Image.composite(out, Image.new("RGB", (w, h), _rgb(primary)), mask)
    return out


def _in_triangle(point: tuple[int, int, int], a, b, c, tol: float = 1e-6) -> bool:
    """点是否落在三角形内 —— **三维**重心坐标，不是二维投影。

    我第一版拿 x/y 两个坐标做二维叉积 ✗，而三角形长在 RGB 三维空间里：投影出去
    会把"空间内但在 R–G 平面外"的点误判成越界（实测 3 个紫色 ✗）。
    正确做法：解 p = a + u(b−a) + v(c−a)，要求 u, v ≥ 0、u+v ≤ 1，且残差≈0。
    """
    v1 = [b[i] - a[i] for i in range(3)]
    v2 = [c[i] - a[i] for i in range(3)]
    w = [point[i] - a[i] for i in range(3)]
    vv1, vv2, v12 = sum(x * x for x in v1), sum(x * x for x in v2), sum(v1[i] * v2[i] for i in range(3))
    wv1, wv2 = sum(w[i] * v1[i] for i in range(3)), sum(w[i] * v2[i] for i in range(3))
    det = vv1 * vv2 - v12 * v12
    if abs(det) < 1e-9:
        return False
    u = (wv1 * vv2 - wv2 * v12) / det
    v = (vv1 * wv2 - v12 * wv1) / det
    residual = [w[i] - u * v1[i] - v * v2[i] for i in range(3)]
    if max(abs(x) for x in residual) > 1.5:
        return False
    # **整数化容差**：逐通道 int() 取整会让"数学上恰在边界上"的点落到边界外一丝
    # （实测 muted/vivid 各有 3 个紫色点 v ≈ −0.002 ✗）。这个容差是明文的，
    # 不是为了让它变绿而调出来的 —— 残差那一关仍然卡着颜色真的跑偏的情况。
    return (u >= -0.01) and (v >= -0.01) and (u + v <= 1.01)


def sample(size: tuple[int, int] = (640, 400)) -> Image.Image:
    """没有真图时生成一张测试卡（渐变 + 几何块），用来验证处理链路。"""
    image = Image.new("L", size, 255)
    draw = ImageDraw.Draw(image)
    width, height = size
    for x in range(width):
        draw.line([(x, 0), (x, height)], fill=round(255 * x / width))
    draw.ellipse([width * 0.1, height * 0.15, width * 0.45, height * 0.75], fill=60)
    draw.rectangle([width * 0.55, height * 0.2, width * 0.9, height * 0.8], fill=180)
    return image.convert("RGB")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="图片 → duotone + 半调（riso 制版）")
    ap.add_argument("src", nargs="?")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--tokens", default=os.path.join(HERE, "..", "styles", "swiss-grid", "style.json"))
    ap.add_argument("--color-set", default="vivid")
    ap.add_argument("--dots", type=int, default=3)
    ap.add_argument("--sample", action="store_true", help="不读真图，生成测试卡")
    args = ap.parse_args(argv[1:])
    tokens = deckio.read_json(args.tokens)
    colors = tokens["colorSets"][args.color_set]
    source = sample() if args.sample else Image.open(args.src)
    treated = duotone(source, colors["primary"], colors["secondary"], colors["background"], args.dots)
    treated.save(args.out)
    # 自查（判据写成几何，才机械可判）：
    # duotone 的过渡色落在「叠印墨 ↔ 纸」连线上，半调边缘又落在「主色 ↔ 该点」之间 ——
    # 所以可达颜色集正好是 **主色 / 叠印墨 / 纸色** 三点构成的三角形。
    # 我第一版写成"离三个色值都不许超过 90"，把中间过渡色全判成越界 ✗（240 种"违规"全是它）。
    hues: set[tuple[int, int, int]] = set()
    for entry in treated.getcolors(maxcolors=1 << 24) or []:
        color = entry[1]
        # getcolors 的第二项在类型上是 `int | tuple[int, ...]`（"L" 图给 int，RGB 给元组）。
        # duotone 的产物是 RGB，所以只收三元组 —— 显式构造而不是 tuple(c)，
        # 后者会被推断成 tuple[int, ...] 而不是长度写死的三元组。
        if isinstance(color, tuple) and len(color) == 3:
            hues.add((color[0], color[1], color[2]))
    tri = (_rgb(colors["primary"]), _rgb(ink.overprint(colors["primary"], colors["secondary"])),
           _rgb(colors["background"]))
    stray = [c for c in hues if not _in_triangle(c, *tri)]
    print(f"✓ 已写出 {args.out}（{treated.size[0]}×{treated.size[1]}，{len(hues)} 种颜色）")
    print(f"  三角（主色/叠印墨/纸色）之外的颜色：{len(stray)} 种"
          + ("  ✓ 制版产物没有引入色板外的色相" if not stray else f"  ✗ 例：{stray[:3]}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
