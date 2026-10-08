#!/usr/bin/env python3
"""HTML → PDF：等待资源就绪后打印，并验证逐页尺寸。

文字和部分形状可保留矢量；照片、Canvas 图表与部分合成效果会栅格化。
通过 Poppler pdfinfo 检查每页 MediaBox，位图/字体标记统计仅作诊断。
跑法：python3 pdf.py out.html -o deck.pdf
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import os
import re
import shutil
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

    页数与逐页尺寸由 Poppler 解析，不能靠正则猜压缩对象或继承的 MediaBox。
    位图/字体仍是字面标记统计，仅供诊断，不据此证明整个 PDF 全矢量。
    """
    if not os.path.exists(pdf_path):
        return {"bytes": 0, "pages": 0, "images": 0, "fonts": 0, "mediaboxes": []}
    raw = deckio.read_bytes(pdf_path)
    pdfinfo = os.environ.get("DECK_PDFINFO") or shutil.which("pdfinfo")
    if not pdfinfo:
        raise SystemExit("✗ 找不到 pdfinfo；请安装 Poppler（macOS: brew install poppler；"
                         "Linux: apt install poppler-utils），或设置 DECK_PDFINFO 为可执行文件路径")
    try:
        summary = subprocess.run([pdfinfo, pdf_path], capture_output=True, text=True,
                                 timeout=30, env={**os.environ, "LC_ALL": "C"})
        count = re.search(r"^Pages:\s*(\d+)\s*$", summary.stdout, re.M)
        if summary.returncode or count is None:
            raise SystemExit(f"✗ pdfinfo 读不动 PDF：{summary.stderr.strip()[:300]}")
        page_count = int(count.group(1))
        detail = subprocess.run([pdfinfo, "-box", "-f", "1", "-l", str(page_count), pdf_path],
                                capture_output=True, text=True, timeout=30,
                                env={**os.environ, "LC_ALL": "C"})
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(f"✗ pdfinfo 检查失败：{exc}") from exc
    if detail.returncode:
        raise SystemExit(f"✗ pdfinfo 读取逐页尺寸失败：{detail.stderr.strip()[:300]}")
    images = len(re.findall(rb"/Subtype\s*/Image", raw))
    fonts = len(re.findall(rb"/FontFile\d?", raw))
    boxes = re.findall(r"^(?:Page\s+\d+\s+)?MediaBox:\s*(.+)$", detail.stdout, re.M)
    return {"bytes": len(raw), "pages": page_count, "images": images,
            "fonts": fonts, "mediaboxes": [b.strip() for b in boxes]}


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

    animate = _load_sibling("animate")
    async def print_ready():
        return await asyncio.wait_for(
            animate._capture_async(html_path, "", [], 1, pdf_out=out_path), timeout)
    try:
        asyncio.run(print_ready())
    except RuntimeError as exc:
        if "no-websockets" not in str(exc):
            raise
        raise SystemExit("✗ PDF 导出需要 websockets 等待字体、图片和图表就绪：pip install websockets") from exc
    except TimeoutError as exc:
        raise SystemExit(f"✗ PDF 导出超过 {timeout} 秒，未交付旧文件") from exc

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
    if len(info["mediaboxes"]) != info["pages"]:
        bad.append("缺少逐页 MediaBox，无法验证每页尺寸")
    for index, box in enumerate(info["mediaboxes"], 1):
        width, height = _box_size(box)
        if not (abs(width - 1600 * PX_TO_PT) < 2
                and abs(height - 900 * PX_TO_PT) < 2):
            bad.append(f"第 {index} 页尺寸不是 1200×675pt（{width:g}×{height:g}）"
                       " —— 请检查打印 CSS 的 @page")

    size_mb = info["bytes"] / 1048576
    print(f"{'✗' if bad else '✓'} {out_path}")
    print(f"  {info['pages']} 页 / {size_mb:.2f}MB / 内嵌位图 {info['images']} / "
          f"嵌入字体 {info['fonts']}")
    if info["mediaboxes"]:
        boxes = "、".join(info["mediaboxes"])
        print(f"  页尺寸 {boxes}（1600×900px = 1200×675pt）")
    if not bad and info["images"] == 0:
        print("  未检测到内嵌位图标记（诊断统计，不替代逐页视觉验收）")
    if not bad and info["fonts"] == 0:
        print("  ⚠ 未检测到 FontFile 标记，可能是 Type3 字形或未嵌入字体，请检查实际 PDF")

    for b in bad:
        print(f"  ✗ {b}")
    return 1 if bad else 0


def _box_w(box: str) -> float:
    """从 MediaBox 字符串里取宽度。"""
    return _box_size(box)[0]


def _box_size(box: str) -> tuple[float, float]:
    try:
        parts = [float(x) for x in box.split()]
    except ValueError:
        return (-1.0, -1.0)
    return (parts[2] - parts[0], parts[3] - parts[1]) if len(parts) == 4 else (-1.0, -1.0)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="out.html → PDF（逐页尺寸验证）")
    ap.add_argument("html")
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args(argv[1:])
    info = export(args.html, args.out)
    return report(info, os.path.abspath(args.out))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
