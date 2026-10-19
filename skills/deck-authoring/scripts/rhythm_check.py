#!/usr/bin/env python3
"""检查整套页面的结构节奏：同一种版面骨架是否用得太滥、是否相邻重复。

只读 HTML 源，按每页顶层区块给一个"骨架签名"，例如 `svg+notes3`、`table+verdict`。
它不判断美丑，只回答两个问题：
  1. 有没有某一种骨架占了半本以上？
  2. 有没有连续两页骨架完全一样？
"""
from __future__ import annotations

import argparse
import collections
import re
import sys
from pathlib import Path

SECTION = re.compile(r'<section[^>]*class="[^"]*\bslide\b[^"]*"[^>]*>.*?</section>', re.S)


def signature(section: str) -> str:
    """按**视觉主角**分类：一页只有一种主角，附属说明块只记有无、不记数量。

    把 notes 的数量算进签名会让 `svg+notes3` 和 `svg+notes1` 变成两种骨架，
    而它们在版面感知上是同一页型；这种细分会掩盖真正的同质化。
    """
    if re.search(r'class="[^"]*\bfinale\b', section):
        return "finale"
    if re.search(r'\bfull-bleed\b|\bdeck-bleed\b|\bedge-to-edge\b', section):
        lead = "bleed"
    elif re.search(r'<svg[^>]*class="[^"]*\bdgm\b', section):
        lead = "svg"
    elif re.search(r'<img\b', section):
        lead = "img"
    elif re.search(r'<table\b', section):
        lead = "table"
    elif re.search(r'class="[^"]*\b(stat|stats|bignum|big-number)\b', section):
        lead = "stat"
    elif re.search(r'<blockquote\b|class="[^"]*\bquote\b', section):
        lead = "quote"
    elif re.search(r'class="[^"]*\bed\b', section):
        lead = "list"
    else:
        lead = "text"
    if re.search(r'class="[^"]*\b(note|verdict)\b', section):
        lead += "+cap"
    return lead


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="检查页面结构节奏（骨架重复与相邻同构）")
    ap.add_argument("html", type=Path, help="source.html 或 deck.html")
    ap.add_argument("--max-share", type=float, default=0.45,
                    help="单一骨架最多占全本的多少（默认 0.45）")
    args = ap.parse_args(argv)

    text = args.html.read_text(encoding="utf-8")
    sections = SECTION.findall(text)
    if not sections:
        print(f"没找到 slide：{args.html}", file=sys.stderr)
        return 2

    sigs = [signature(s) for s in sections]
    counts = collections.Counter(sigs)
    total = len(sigs)

    print(f"共 {total} 页，{len(counts)} 种视觉主角\n")
    for sig, n in counts.most_common():
        bar = "█" * n
        print(f"  {n:2d}  {sig:<18} {bar}")
    print()

    problems: list[str] = []
    top_sig, top_n = counts.most_common(1)[0]
    if top_n / total > args.max_share:
        problems.append(
            f"主角 `{top_sig}` 占 {top_n}/{total}（{top_n/total:.0%}），超过 {args.max_share:.0%}——页面太像同一套排版。")

    runs = []
    for i in range(1, len(sigs)):
        if sigs[i] == sigs[i - 1]:
            runs.append(i + 1)
    if runs:
        problems.append("连续两页主角相同，出现在第 " + "、".join(map(str, runs)) + " 页。")

    leads = {s.split("+")[0] for s in sigs} - {"finale"}
    if total >= 8 and len(leads) < 4:
        problems.append(
            f"视觉主角只有 {len(leads)} 种（{'、'.join(sorted(leads))}），至少需要 4 种"
            "——正文页正在重复同一套排版。")

    if problems:
        for p in problems:
            print("  ✗ " + p)
        print("\n改法：换视觉主角（全幅图/出血材质/大数字/引文/大表/剖面/拼贴/停顿页）、"
              "换分栏、换底部收束；同一主角最多隔两页再出现一次，不要 A/B/A/B 交替。")
        return 1

    print("  ✓ 版面节奏正常：没有单一主角过半，没有相邻同构，主角种类充足。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
