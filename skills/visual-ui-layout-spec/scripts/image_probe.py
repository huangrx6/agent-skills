#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow>=10.0.0"]
# ///
# -*- coding: utf-8 -*-
"""image_probe.py — UI 截图/大屏图的量化探测工具（visual-ui-layout-spec 技能内置）

只做一件事：把"看图猜"变成"读数写"。所有子命令输出人类可读文本 + 可选 JSON。

用 `uv run scripts/image_probe.py <cmd> <image> [opts]` 调用，
uv 会自动按上方 PEP 723 声明安装 Pillow，无需手动 pip install。

子命令：
  info      图片基本信息（尺寸/模式/DPI/推断设计基准宽与换算比例）
  quality   图片清晰度/对比度预检
  grid      叠加百分比坐标网格，另存标注图（供再次读图定位区域边界）
  bands     行/列投影法探测区块分隔线候选坐标（量出区域高度/宽度）
  runs      沿扫描线输出连续同色分段（精确量卡片宽、间距、内边距）
  crop      裁剪指定区域并放大另存（供分区下钻精读）
  palette   量化取主色（含占比），可限定区域与饱和度过滤
  pick      在指定坐标取样颜色（小邻域均值），输出 hex/rgb

示例：
  uv run scripts/image_probe.py info shot.png --json
  uv run scripts/image_probe.py grid shot.png --out /tmp/shot_grid.png
  uv run scripts/image_probe.py bands shot.png --axis both --top 12
  uv run scripts/image_probe.py runs shot.png --row 120 --tol 6
  uv run scripts/image_probe.py crop shot.png --box 0,140,420,340 --scale 3 --out /tmp/r3.png
  uv run scripts/image_probe.py crop shot.png --box 0,17,41,42 --unit pct --scale 3 --out /tmp/r3.png
  uv run scripts/image_probe.py palette shot.png --colors 14
  uv run scripts/image_probe.py pick shot.png --points 60,20;300,120 --radius 3
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from PIL import Image, ImageDraw, ImageStat, ImageFilter, ImageOps

# 常见设计基准宽（用于把截图像素换算回设计稿像素）
DESIGN_BASE_WIDTHS = (1920, 1600, 1440, 1366, 1280, 1024, 750, 390, 375)


# --------------------------------------------------------------------------- #
# 公共辅助
# --------------------------------------------------------------------------- #

def load_image(path):
    if not os.path.isfile(path):
        sys.stderr.write(f"[image_probe] 文件不存在：{path}\n")
        sys.exit(1)
    im = Image.open(path)
    im = ImageOps.exif_transpose(im)
    im.load()
    return im


def to_rgb(im):
    if im.mode in ("RGB",):
        return im
    if im.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        conv = im.convert("RGBA")
        bg.paste(conv, mask=conv.split()[-1])
        return bg
    return im.convert("RGB")


def hexcolor(rgb):
    r, g, b = (int(round(c)) for c in rgb[:3])
    return f"#{r:02x}{g:02x}{b:02x}"


def sat_light(rgb):
    """返回 (饱和度%, 亮度%)，HSV 口径。"""
    r, g, b = (float(c) for c in rgb[:3])
    mx, mn = max(r, g, b), min(r, g, b)
    sat = 0.0 if mx == 0 else (mx - mn) / mx * 100
    return round(sat, 1), round(mx / 255 * 100, 1)


def parse_box(box, size, unit):
    """解析 'x1,y1,x2,y2'，unit=px|pct，返回像素整数元组并裁剪到画布内。"""
    parts = [p.strip() for p in box.replace("，", ",").split(",")]
    if len(parts) != 4:
        sys.stderr.write("[image_probe] --box 需为 'x1,y1,x2,y2' 四个数值\n")
        sys.exit(1)
    vals = [float(p) for p in parts]
    w, h = size
    if unit == "pct":
        vals = [vals[0] / 100 * w, vals[1] / 100 * h, vals[2] / 100 * w, vals[3] / 100 * h]
    x1, y1, x2, y2 = (int(round(v)) for v in vals)
    x1, x2 = sorted((max(0, min(x1, w)), max(0, min(x2, w))))
    y1, y2 = sorted((max(0, min(y1, h)), max(0, min(y2, h))))
    return x1, y1, x2, y2


def gray_pixel(im, x, y):
    """取 (x,y) 的灰度值（浮点）。"""
    r, g, b = im.getpixel((x, y))[:3]
    return 0.299 * r + 0.587 * g + 0.114 * b


def emit(payload, lines, as_json):
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("\n".join(lines))


def _default_out(image, tag):
    tmp = os.environ.get("TMPDIR", "/tmp")
    base = os.path.splitext(os.path.basename(image))[0]
    return os.path.join(tmp, f"{base}__{tag}.png")


# --------------------------------------------------------------------------- #
# info
# --------------------------------------------------------------------------- #

def cmd_info(args):
    im = to_rgb(load_image(args.image))
    w, h = im.size
    design_base = min(DESIGN_BASE_WIDTHS, key=lambda b: abs(b - w))
    scale = w / design_base
    payload = {
        "path": os.path.abspath(args.image),
        "width": w, "height": h,
        "mode": im.mode,
        "dpi": im.info.get("dpi", (72, 72))[0],
        "design_base_width": design_base,
        "scale_factor": round(scale, 4),
        "megapixels": round(w * h / 1e6, 2),
    }
    lines = [
        f"图片：{payload['path']}",
        f"尺寸：{w} × {h}（{payload['megapixels']} MP）",
        f"模式：{im.mode}",
        f"推断设计基准宽：{design_base}（换算比例 ×{payload['scale_factor']}）",
    ]
    emit(payload, lines, args.json)


# --------------------------------------------------------------------------- #
# quality
# --------------------------------------------------------------------------- #

def cmd_quality(args):
    im = to_rgb(load_image(args.image))
    g = im.convert("L")
    stat = ImageStat.Stat(g)
    brightness = round(stat.mean[0], 2)
    contrast = round(stat.stddev[0], 2)
    edge = g.filter(ImageFilter.FIND_EDGES)
    edge_energy = round(ImageStat.Stat(edge).mean[0], 2)
    warnings = []
    if brightness < 35: warnings.append("整体较暗")
    if brightness > 235: warnings.append("整体较亮，浅色边界可能难测")
    if contrast < 20: warnings.append("整体对比度偏低")
    if edge_energy < 8: warnings.append("边缘能量较低，可能模糊或内容本身平滑")
    payload = {"brightness": brightness, "contrast_stddev": contrast,
               "edge_energy": edge_energy, "warnings": warnings}
    lines = [f"亮度：{brightness}", f"对比度（stddev）：{contrast}", f"边缘能量：{edge_energy}"]
    lines.extend(["注意："] + [f"  {x}" for x in warnings] if warnings else ["未发现明显质量风险。"])
    emit(payload, lines, args.json)


# --------------------------------------------------------------------------- #
# grid
# --------------------------------------------------------------------------- #

def cmd_grid(args):
    im = to_rgb(load_image(args.image))
    w, h = im.size
    ow, oh = round(w * args.scale), round(h * args.scale)
    overlay = Image.new("RGBA", (ow, oh), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for i in range(0, 101, args.step_x):
        x = round(i / 100 * ow)
        draw.line([(x, 0), (x, oh)], fill=(255, 0, 0, 80), width=1)
        draw.text((x + 2, 2), f"{i}%", fill=(255, 0, 0, 200))
    for i in range(0, 101, args.step_y):
        y = round(i / 100 * oh)
        draw.line([(0, y), (ow, y)], fill=(255, 0, 0, 80), width=1)
        draw.text((2, y + 2), f"{i}%", fill=(255, 0, 0, 200))
    base = im.resize((ow, oh), Image.LANCZOS).convert("RGBA")
    out_im = Image.alpha_composite(base, overlay).convert("RGB")
    out = args.out or _default_out(args.image, "grid")
    out_im.save(out)
    payload = {"out": os.path.abspath(out), "width": ow, "height": oh,
               "step_x": args.step_x, "step_y": args.step_y}
    emit(payload, [f"已生成网格标注图：{payload['out']}", f"网格步长：X {args.step_x}% / Y {args.step_y}%"], args.json)


# --------------------------------------------------------------------------- #
# bands
# --------------------------------------------------------------------------- #

def _row_means(im):
    w, h = im.size
    g = im.convert("L")
    return [ImageStat.Stat(g.crop((0, y, w, y + 1))).mean[0] for y in range(h)]


def _col_means(im):
    w, h = im.size
    g = im.convert("L")
    return [ImageStat.Stat(g.crop((x, 0, x + 1, h))).mean[0] for x in range(w)]


def _boundaries(means, min_gap, top):
    diffs = [abs(means[i + 1] - means[i]) for i in range(len(means) - 1)]
    ranked = sorted(range(len(diffs)), key=lambda i: diffs[i], reverse=True)
    picked = []
    for idx in ranked:
        if all(abs(idx + 1 - p) >= min_gap for p in picked):
            picked.append(idx + 1)
        if len(picked) >= top:
            break
    return sorted([(p, round(diffs[p - 1], 2)) for p in picked], key=lambda t: t[0])


def cmd_bands(args):
    im = to_rgb(load_image(args.image))
    if args.box:
        x1, y1, x2, y2 = parse_box(args.box, im.size, args.unit)
        im = im.crop((x1, y1, x2, y2))
    payload = {}
    lines = []
    if args.axis in ("h", "both"):
        picked = _boundaries(_row_means(im), args.min_gap, args.top)
        payload["horizontal"] = [{"y": y, "strength": s, "y_pct": round(y / im.height * 100, 2)} for y, s in picked]
        lines.append("")
        lines.append("水平分隔线候选（y 像素 / 占比 / 强度）—— 用于量区域高度：")
        for y, s in picked:
            lines.append(f"  y={y:<5} {y / im.height * 100:6.2f}%   强度 {s}")
        if len(picked) >= 2:
            segs = [picked[i + 1][0] - picked[i][0] for i in range(len(picked) - 1)]
            lines.append(f"  相邻带高：{segs}")
    if args.axis in ("v", "both"):
        picked = _boundaries(_col_means(im), args.min_gap, args.top)
        payload["vertical"] = [{"x": x, "strength": s, "x_pct": round(x / im.width * 100, 2)} for x, s in picked]
        lines.append("")
        lines.append("垂直分隔线候选（x 像素 / 占比 / 强度）—— 用于量列宽与栅格间距：")
        for x, s in picked:
            lines.append(f"  x={x:<5} {x / im.width * 100:6.2f}%   强度 {s}")
        if len(picked) >= 2:
            segs = [picked[i + 1][0] - picked[i][0] for i in range(len(picked) - 1)]
            lines.append(f"  相邻带宽：{segs}")
    lines.append("")
    lines.append("注意：候选点是「灰度突变位置」，需结合读图确认它是卡片边界、分割线还是内容边缘。")
    emit(payload, lines, args.json)


# --------------------------------------------------------------------------- #
# crop
# --------------------------------------------------------------------------- #

def cmd_crop(args):
    im = to_rgb(load_image(args.image))
    x1, y1, x2, y2 = parse_box(args.box, im.size, args.unit)
    sub = im.crop((x1, y1, x2, y2))
    w, h = sub.size
    if args.scale and args.scale != 1:
        sub = sub.resize((int(w * args.scale), int(h * args.scale)), Image.LANCZOS)
    out = args.out or _default_out(args.image, f"crop_{x1}_{y1}")
    sub.save(out)
    payload = {"out": os.path.abspath(out), "box_px": [x1, y1, x2, y2],
               "crop_size": [w, h], "scale": args.scale, "saved_size": list(sub.size)}
    emit(payload, [f"已裁剪：{payload['out']}",
                   f"原图区域：x {x1}~{x2}, y {y1}~{y2}（{w} x {h} px），放大 ×{args.scale}",
                   "下一步：读取该放大图，抄录区域内文案、组件与细节样式。"], args.json)


# --------------------------------------------------------------------------- #
# palette
# --------------------------------------------------------------------------- #

def cmd_palette(args):
    im = to_rgb(load_image(args.image))
    region = "整图"
    if args.box:
        x1, y1, x2, y2 = parse_box(args.box, im.size, args.unit)
        im = im.crop((x1, y1, x2, y2))
        region = f"x {x1}~{x2}, y {y1}~{y2}"
    small = im.copy()
    small.thumbnail((args.sample_size, args.sample_size), Image.LANCZOS)
    # 先按饱和度过滤像素，再量化 —— 否则小面积强调色会被大面积白/灰背景吞掉
    kept = list(small.getdata())
    if args.min_sat > 0:
        kept = [p for p in kept if sat_light(p)[0] >= args.min_sat]
    if not kept:
        emit({"region": region, "min_sat": args.min_sat, "colors": []},
             [f"取色区域：{region}", "（无符合饱和度阈值的像素，请降低 --min-sat）"], args.json)
        return
    flat = Image.new("RGB", (len(kept), 1))
    flat.putdata(kept)
    q = flat.quantize(colors=max(2, args.colors), method=Image.MEDIANCUT)
    pal = q.getpalette() or []
    counts = sorted(q.getcolors(maxcolors=1 << 20) or [], reverse=True)
    total = sum(c for c, _ in counts) or 1
    items = []
    for count, idx in counts:
        rgb = pal[idx * 3:idx * 3 + 3]
        if len(rgb) == 3:
            items.append({"hex": hexcolor(rgb), "share_pct": round(count / total * 100, 2)})
    emit({"region": region, "min_sat": args.min_sat, "colors": items},
         [f"取色区域：{region}"] + [f"  {c['hex']}  {c['share_pct']:>6}%  {c['hex']}" for c in items], args.json)


# --------------------------------------------------------------------------- #
# pick
# --------------------------------------------------------------------------- #

def cmd_pick(args):
    im = to_rgb(load_image(args.image))
    w, h = im.size
    results = []
    for raw in args.points.split(";"):
        rx, ry = [float(v) for v in raw.replace("，", ",").split(",")]
        if args.unit == "pct":
            rx, ry = rx / 100 * w, ry / 100 * h
        rx, ry = int(round(rx)), int(round(ry))
        r = max(0, args.radius)
        box = (max(0, rx - r), max(0, ry - r), min(w, rx + r + 1), min(h, ry + r + 1))
        rgb = tuple(round(v) for v in ImageStat.Stat(im.crop(box)).mean[:3])
        results.append({"x": rx, "y": ry, "rgb": rgb, "hex": hexcolor(rgb),
                        "hsv_sat_pct": sat_light(rgb)[0], "hsv_light_pct": sat_light(rgb)[1]})
    emit({"points": results},
         [f"({p['x']},{p['y']})  {p['hex']}  rgb{tuple(p['rgb'])}  饱和度 {p['hsv_sat_pct']}%  亮度 {p['hsv_light_pct']}%"
          for p in results], True)


# --------------------------------------------------------------------------- #
# runs
# --------------------------------------------------------------------------- #

def cmd_runs(args):
    im = to_rgb(load_image(args.image))
    w, h = im.size
    segments = []
    if args.row is not None:
        axis, pos = "horizontal", args.row
        y = max(0, min(args.row, h - 1))
        seg_start = 0
        prev = gray_pixel(im, 0, y)
        for x in range(1, w + 1):
            cur = gray_pixel(im, min(x, w - 1), y) if x < w else prev
            if abs(cur - prev) > args.tol or x == w:
                seg_len = x - seg_start
                if seg_len >= args.min_len:
                    rgb = im.getpixel((seg_start, y))[:3]
                    segments.append({"x_start": seg_start, "x_end": x, "length": seg_len, "hex": hexcolor(rgb)})
                seg_start = x
            prev = cur
    else:
        axis, pos = "vertical", args.col
        x = max(0, min(args.col, w - 1))
        seg_start = 0
        prev = gray_pixel(im, x, 0)
        for y in range(1, h + 1):
            cur = gray_pixel(im, x, min(y, h - 1)) if y < h else prev
            if abs(cur - prev) > args.tol or y == h:
                seg_len = y - seg_start
                if seg_len >= args.min_len:
                    rgb = im.getpixel((x, seg_start))[:3]
                    segments.append({"y_start": seg_start, "y_end": y, "length": seg_len, "hex": hexcolor(rgb)})
                seg_start = y
            prev = cur
    payload = {"axis": axis, "position": pos, "tol": args.tol, "min_len": args.min_len, "segments": segments}
    label = "行" if axis == "horizontal" else "列"
    lines = [f"{label} {pos}（容差 {args.tol}，最小段长 {args.min_len}）："]
    for s in segments:
        if axis == "horizontal":
            lines.append(f"  x {s['x_start']}~{s['x_end']}（{s['length']}px）{s['hex']}")
        else:
            lines.append(f"  y {s['y_start']}~{s['y_end']}（{s['length']}px）{s['hex']}")
    if not segments:
        lines.append("  无满足条件的色段。")
    emit(payload, lines, args.json)


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def build_parser():
    p = argparse.ArgumentParser(description="UI 截图量化探测工具")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("image")
        sp.add_argument("--json", action="store_true")

    sp = sub.add_parser("info", help="图片基本信息")
    common(sp)
    sp.set_defaults(fn=cmd_info)

    sp = sub.add_parser("quality", help="图片清晰度/对比度预检")
    common(sp)
    sp.set_defaults(fn=cmd_quality)

    sp = sub.add_parser("grid", help="叠加百分比坐标网格另存")
    common(sp)
    sp.add_argument("--step-x", type=int, default=5, help="X 网格步长（%%），默认 5")
    sp.add_argument("--step-y", type=int, default=5, help="Y 网格步长（%%），默认 5")
    sp.add_argument("--scale", type=float, default=1.0, help="输出缩放倍数")
    sp.add_argument("--out", help="输出路径，默认 $TMPDIR/<name>__grid.png")
    sp.set_defaults(fn=cmd_grid)

    sp = sub.add_parser("bands", help="行/列投影探测区块分隔线")
    common(sp)
    sp.add_argument("--axis", choices=["h", "v", "both"], default="both")
    sp.add_argument("--top", type=int, default=14, help="每轴保留候选数，默认 14")
    sp.add_argument("--min-gap", type=int, default=8, help="候选最小间距（px），默认 8")
    sp.add_argument("--box", help="限定分析区域 x1,y1,x2,y2")
    sp.add_argument("--unit", choices=["px", "pct"], default="px")
    sp.set_defaults(fn=cmd_bands)

    sp = sub.add_parser("crop", help="裁剪并放大另存")
    common(sp)
    sp.add_argument("--box", required=True, help="区域 x1,y1,x2,y2")
    sp.add_argument("--unit", choices=["px", "pct"], default="px")
    sp.add_argument("--scale", type=float, default=2.0, help="放大倍数，默认 2")
    sp.add_argument("--out", help="输出路径")
    sp.set_defaults(fn=cmd_crop)

    sp = sub.add_parser("palette", help="量化主色与占比")
    common(sp)
    sp.add_argument("--colors", type=int, default=12, help="量化色数，默认 12")
    sp.add_argument("--box", help="限定取色区域 x1,y1,x2,y2")
    sp.add_argument("--unit", choices=["px", "pct"], default="px")
    sp.add_argument("--sample-size", type=int, default=400, help="采样缩略最大边，默认 400")
    sp.add_argument("--min-sat", type=float, default=0.0, help="只保留饱和度 ≥ 此值（%%）的颜色")
    sp.set_defaults(fn=cmd_palette)

    sp = sub.add_parser("pick", help="坐标取样颜色")
    common(sp)
    sp.add_argument("--points", required=True, help="坐标串 'x,y;x,y'")
    sp.add_argument("--unit", choices=["px", "pct"], default="px")
    sp.add_argument("--radius", type=int, default=2, help="邻域半径（px），默认 2")
    sp.set_defaults(fn=cmd_pick)

    sp = sub.add_parser("runs", help="扫描线色块分段（量卡片宽/间距/内边距）")
    common(sp)
    g = sp.add_mutually_exclusive_group(required=True)
    g.add_argument("--row", type=int, help="水平扫描的 y 坐标")
    g.add_argument("--col", type=int, help="垂直扫描的 x 坐标")
    sp.add_argument("--tol", type=int, default=6, help="同色容差（单通道），默认 6")
    sp.add_argument("--min-len", type=int, default=3, help="最小段长（px），默认 3")
    sp.set_defaults(fn=cmd_runs)

    return p


def main():
    args = build_parser().parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
