#!/usr/bin/env python3
"""比对 source.html 与 deck.html 的逐页骨架，防止"源码改了、产物没变"。

编译器的 HTML 解析器会"修复"未闭合标签，结果可能把新内容丢掉却不报错。
本脚本按 data-slide 对比两边的骨架标记（svg/table/notes/verdict/list/finale），
任何一页不一致就返回 1。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SECTION = re.compile(r'<section class="slide"[^>]*data-slide="(\d+)"[^>]*>(.*?)</section>', re.S)


def skeleton(body: str) -> str:
    if re.search(r'class="[^"]*\bfinale\b', body):
        return "finale"
    parts = []
    if "<table" in body:
        parts.append("table")
    if re.search(r'<svg[^>]*class="[^"]*\bdgm\b', body):
        parts.append("svg")
    if re.search(r'class="[^"]*\bed\b', body):
        parts.append("list")
    if re.search(r'class="[^"]*\bnotes-row\b', body):
        parts.append(f"row{body.count('class=\"note ')}")
    elif "class=\"note " in body:
        parts.append(f"notes{body.count('class=\"note ')}")
    if "verdict" in body:
        parts.append("verdict")
    return "+".join(parts) or "text"


def scan(path: Path) -> dict[int, str]:
    text = path.read_text(encoding="utf-8")
    return {int(n): skeleton(b) for n, b in SECTION.findall(text)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="比对源码与产物的逐页骨架")
    ap.add_argument("source", type=Path)
    ap.add_argument("deck", type=Path)
    args = ap.parse_args(argv)

    src, out = scan(args.source), scan(args.deck)
    if len(src) != len(out):
        print(f"✗ 页数不一致：source {len(src)} 页，deck {len(out)} 页")
        return 1

    bad = [(n, src[n], out[n]) for n in src if src.get(n) != out.get(n)]
    if bad:
        print("✗ 源码与产物不一致：")
        for n, a, b in bad:
            print(f"  第 {n} 页：源码 {a} / 产物 {b}")
        print("\n多半是标签未闭合，编译器在修复时换了内容。回到生成器重出，不要手改 HTML。")
        return 1

    print(f"✓ {len(src)} 页骨架逐页一致（源码 = 产物）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
