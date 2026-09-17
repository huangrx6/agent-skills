#!/usr/bin/env python3
"""out.html → 矢量 PDF（系统 Chrome 打印到 PDF）。

## 为什么这条路能出**矢量** PDF

页面里的东西全是 CSS/SVG 画的，而 Chrome 打印到 PDF 时把文字保留为**嵌入字体**、
把形状保留为**路径** —— 只有"合成器才能算"的东西（滤镜 / `<pattern>` / 大位图）
才会退化成位图。

所以这份 PDF：文字可选可搜、放大不糊、条纹与错位都是路径。实测 6 页 0.65MB、
零内嵌位图、7 个嵌入字体。

要维持这个性质有两条前提：

1. **`@page` 必须显式给尺寸**（`render.py` 的打印 CSS 里写了 `1600px 900px`）。
   不给的话 Chrome 用 Letter/A4，deck 会被缩小加留白 —— 尺寸悄悄变了，
   而页数还是对的，不查就发现不了。
2. **网点不能是 `<pattern>`**：Chrome 导 PDF 时会把 `<pattern>` 整块栅格化
   （实测 4 块半调 → 4 张 ~1035×1014 位图）。`render.py` 现在用虚线路径画网点。

## 这个脚本干的事

跑一次 Chrome，然后**验产物**并把话说明白：页数对不对、里面有没有位图、
字有没有嵌进去。一行 `--print-to-pdf` 谁都会写；会验的才算一层。

跑法：python3 pdf.py out.html -o deck.pdf
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_sibling(name: str):
    """动态加载同目录脚本（`scripts/` 不是包，同级 import 在静态层面无法解析）。

    写法和本目录其他脚本一致。
    """
    path = os.path.join(HERE, f"{name}.py")
    mod_spec = importlib.util.spec_from_file_location(f"_deck_{name}", path)
    if mod_spec is None or mod_spec.loader is None:
        raise RuntimeError(f"加载不了同目录模块：{path}")
    module = importlib.util.module_from_spec(mod_spec)
    sys.modules[mod_spec.name] = module
    mod_spec.loader.exec_module(module)
    return module


deckio = _load_sibling("deckio")   # IO 收口：读不到要报清楚，不甩 traceback


CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# CSS px → PDF pt 的换算（1px = 0.75pt）。
PX_TO_PT = 0.75


def inspect(pdf_path: str) -> dict:
    """读 PDF 说事实：页数 / 内嵌位图 / 嵌入字体 / 页尺寸。

    不引第三方库 —— 这些都是 PDF 里的字面标记，正则数一下就够；
    为了"验一下"去装一个 PDF 库不划算。
    """
    if not os.path.exists(pdf_path):
        return {"bytes": 0, "pages": 0, "images": 0, "fonts": 0, "mediaboxes": []}
    raw = deckio.read_bytes(pdf_path)
    page_count = len(re.findall(rb"/Type\s*/Page[^s]", raw))
    images = len(re.findall(rb"/Subtype\s*/Image", raw))
    fonts = len(re.findall(rb"/FontFile\d?", raw))
    boxes = {b.decode("ascii", "replace")
             for b in re.findall(rb"/MediaBox\s*\[([^\]]+)\]", raw)}
    return {"bytes": len(raw), "pages": page_count, "images": images,
            "fonts": fonts, "mediaboxes": sorted(boxes)}


def slide_count(html_path: str) -> int:
    """数产物里有几页 —— 拿 `<section class="slide">` 当事实来源。"""
    return len(re.findall(r'<section class="slide"', deckio.read_text(html_path)))


def export(html_path: str, out_path: str, timeout: int = 180) -> dict:
    """打印成 PDF，然后验一遍。验不过就抛清楚的话，不留给用户一个坏文件。"""
    if not os.path.isfile(CHROME):
        raise SystemExit(f"✗ 找不到 Chrome：{CHROME}\n"
                         f"  PDF 走的是 Chrome 的打印管线，没有替代品。")
    html_path = os.path.abspath(html_path)
    if not os.path.isfile(html_path):
        raise SystemExit(f"✗ 读不到产物：{html_path}")
    out_path = os.path.abspath(out_path)
    deckio.ensure_dir(os.path.dirname(out_path) or ".")

    proc = subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
         "--no-pdf-header-footer", f"--print-to-pdf={out_path}",
         "--virtual-time-budget=8000", f"file://{html_path}"],
        capture_output=True, text=True, timeout=timeout)
    if not os.path.exists(out_path):
        raise SystemExit(f"✗ Chrome 没出 PDF（退出码 {proc.returncode}）\n"
                         f"  stderr: {(proc.stderr or '').strip()[:400]}")

    info = inspect(out_path)
    info["expected_pages"] = slide_count(html_path)
    return info


def report(info: dict, out_path: str) -> int:
    """把验的结果说出来；有硬伤就返回 1。

    什么算硬伤：页数不对（有人会拿一份少了几页的 PDF 去讲）、PDF 空。
    位图**不算**硬伤 —— 它是质量指标，报出来让人自己判断（字体没嵌也一样）。
    """
    bad: list[str] = []
    if info["pages"] != info["expected_pages"]:
        bad.append(f"页数不对：PDF 有 {info['pages']} 页，产物里有 {info['expected_pages']} 页"
                   f" —— 打印分页被哪些元素推歪了（通常是某个元素撑破了 1600×900）")
    if info["bytes"] < 1024:
        bad.append(f"PDF 只有 {info['bytes']} 字节 —— 基本是空的")

    size_mb = info["bytes"] / 1048576
    print(f"{'✗' if bad else '✓'} {out_path}")
    print(f"  {info['pages']} 页 / {size_mb:.2f}MB / 内嵌位图 {info['images']} / "
          f"嵌入字体 {info['fonts']}")
    if info["mediaboxes"]:
        boxes = "、".join(info["mediaboxes"])
        print(f"  页尺寸 {boxes}（1600×900px = 1200×675pt）")
        if not any(abs(_box_w(b) - 1600 * PX_TO_PT) < 2 for b in info["mediaboxes"]):
            bad.append("页尺寸不是 1200×675pt —— 打印 CSS 的 @page 大概没生效，"
                       "deck 会被缩小加留白")
    if not bad and info["images"] == 0:
        print("  全矢量（零内嵌位图）：文字可选可搜、放大不糊")
    if not bad and info["fonts"] == 0:
        print("  ⚠ 没有嵌入字体 —— 对方机器缺字时文字会换字体（这条不阻塞，但交付前值得看一眼）")

    for b in bad:
        print(f"  ✗ {b}")
    return 1 if bad else 0


def _box_w(box: str) -> float:
    """从 MediaBox 字符串里取宽度。"""
    try:
        parts = [float(x) for x in box.split()]
    except ValueError:
        return -1.0
    return parts[2] - parts[0] if len(parts) == 4 else -1.0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="out.html → 矢量 PDF")
    ap.add_argument("html")
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args(argv[1:])
    info = export(args.html, args.out)
    return report(info, os.path.abspath(args.out))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
