#!/usr/bin/env python3
"""检查整套页面的结构节奏：同一种版面骨架是否用得太滥、是否相邻重复。

只读 HTML 源，按每页顶层区块给一个"骨架签名"，例如 `svg+notes3`、`table+verdict`。
它不判断美丑，只回答两个问题：
  1. 有没有某一种**非图像**骨架占了半本以上？
  2. 有没有连续三页以上同一种**非图像**骨架？

图像/整幅页由内容决定多少，不设上限：图集、步骤、前后对比可以连续多页，检查器只提示
构图是否在变，不按张数判失败。
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
                    help="非图像主角最多占全本的多少（默认 0.45；图像页不设上限）")
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

    image_leads = {"img", "bleed", "svg"}
    text_sigs = [sig for sig in sigs if sig.split("+")[0] not in image_leads]
    image_count = total - len(text_sigs)
    image_share = image_count / total

    problems: list[str] = []
    if text_sigs:
        top_text, top_text_n = collections.Counter(text_sigs).most_common(1)[0]
        if top_text_n / total > args.max_share:
            problems.append(
                f"非图像主角 `{top_text}` 占 {top_text_n}/{total}（{top_text_n/total:.0%}），"
                f"超过 {args.max_share:.0%}——页面太像同一套文档排版。")

    runs = []
    start = 0
    for i in range(1, len(sigs) + 1):
        if i == len(sigs) or sigs[i] != sigs[start]:
            if i - start >= 3:
                runs.append((start + 1, i))
            start = i

    text_runs = [run for run in runs if sigs[run[0] - 1].split("+")[0] not in image_leads]
    image_runs = [run for run in runs if sigs[run[0] - 1].split("+")[0] in image_leads]
    if text_runs:
        spans = "、".join(f"{first}–{last}" if last > first else str(first) for first, last in text_runs)
        problems.append(f"连续三页以上非图像主角相同，出现在第 {spans} 页；"
                        "相邻两页同构可以留给信息比较，连成排才说明版面在偷懒。")

    text_leads = {sig.split("+")[0] for sig in text_sigs} - {"finale"}
    if total >= 8 and image_share < 0.5 and len(text_leads) < 3:
        problems.append(
            f"非图像视觉主角只有 {len(text_leads)} 种（{'、'.join(sorted(text_leads)) or '无'}），"
            "至少需要 3 种——正文页正在重复同一套排版。")

    if problems:
        for problem in problems:
            print("  ✗ " + problem)
        print("\n改法：换视觉主角（全幅图/出血材质/整幅色域/大数字/引文/大表/剖面/拼贴/停顿页）、"
              "换分栏、换底部收束；同一主角成对出现可以，但不要连续三页，也不要 A/B/A/B 交替。")
        return 1

    if image_count:
        print(f"  · 图像 / 整幅主角 {image_count}/{total}（{image_share:.0%}）——不设上限，按内容决定多少。")
    if image_share >= 0.6 or image_runs:
        print("    确认每页的构图/裁切/角色在变（整幅、框景、网格、拼贴、局部放大）；"
              "图集式重复可以保留，不看数量看是否成立。")
    if image_share >= 0.5:
        print("  ✓ 节奏检查通过：图像主导的稿子不按张数判失败；构图变化仍要目检。")
    else:
        print("  ✓ 版面节奏正常：非图像主角没有过半，没有连续三页同构，主角种类充足。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
