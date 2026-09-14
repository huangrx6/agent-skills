#!/usr/bin/env python3
"""把五套 drawio 配色方案做成一页一套的 **预览文件** —— 给用户**挑风格用**的。

## 为什么需要它（和 `direction_preview.py` 同一个理由）

方案名（`classic` / `engineering` / `print` …）说明不了什么 —— 用户要看了才知道喜不喜欢。
由模型替用户选一个然后出图，经常是出完才发现"不是我想要的那个专业感"，改一次的成本
比先看一眼高得多。

**用法**：用户**没指定风格**时，出图之前跑一次，把生成的文件给他，他在**底部页签**上
一页页切着挑；挑完再照他选的那套出正式图。

    python3 scripts/scheme_preview.py -o /tmp/schemes.drawio
    # 然后在 draw.io / app.diagrams.net 里打开，切页签看

**为什么用"多页"而不是像 Excalidraw 那样并排几块**：draw.io 的页签是原生能力，
而**每页可以有自己的底色** —— Excalidraw 那边只能整个文件一个底色，所以它得给深色
面板手工铺一块底矩形（见 `direction_preview.py` 文档里那个坑）。多页顺手绕开了它，
而且页签名直接就是方案名。

五页用的是**同一张样例图**（同一组节点、同一种布局，只有配色不同）—— 不然"哪个更好看"
会被内容和版式的差异盖住。
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_sibling(name: str):
    """动态加载同目录脚本（`scripts/` 不是包）。同一个模块只加载一次。"""
    key = f"_scheme_preview_{name}"
    loaded = sys.modules.get(key)
    if loaded is not None:
        return loaded
    path = os.path.join(HERE, f"{name}.py")
    spec = importlib.util.spec_from_file_location(key, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


emitter = _load_sibling("emit_drawio")
palette = emitter.palette

# 样例图：故意把 4 个层级、两种边型、区域都放进去 —— 一页就能看出整套色阶，
# 而不是只看"一个框是什么颜色"。内容刻意平庸：它只是背景板，别抢配色的戏。
SAMPLE: dict = {
    "type": "flow",
    "direction": "LR",
    "title": "配色对照",
    "groups": [{"id": "g", "label": "服务区", "level": "tint"}],
    "nodes": [
        {"id": "start", "kind": "client", "label": "入口", "group": "g"},
        {"id": "plain", "kind": "plain", "label": "普通步骤", "group": "g",
         "detail": "次要说明那一行"},
        {"id": "hot", "kind": "service", "label": "重点服务", "emphasis": "primary"},
        {"id": "store", "kind": "data", "label": "存储", "shape": "cylinder"},
        {"id": "bad", "kind": "service", "label": "异常兜底", "emphasis": "critical"},
    ],
    "edges": [
        {"from": "start", "to": "plain"},
        {"from": "plain", "to": "hot"},
        {"from": "hot", "to": "store", "kind": "data", "label": "读写"},
        {"from": "hot", "to": "bad", "kind": "async", "label": "异步"},
    ],
}


def build(spec: dict | None = None, schemes: list[str] | None = None) -> str:
    """把 N 套方案做成 N 页（同一张样例图）。**纯函数，不写文件。**"""
    diagram = dict(spec or SAMPLE)
    names = schemes or palette.available_schemes()
    pages = []
    for name in names:
        scheme = palette.DRAWIO_SCHEMES[name]
        # 每页的标题 = 方案（中文名 + 机器名）—— 切页签时一眼知道这是哪套
        page_spec = {**diagram, "title": f"{scheme['zh']}（{name}）"}
        page, _result, outcome, _attempts = emitter.emit_page(page_spec, scheme=name)
        if outcome.blocking:
            raise emitter.SpecError(
                f"方案 {name} 的预览出不来：{[i.line() for i in outcome.blocking]}")
        pages.append(page)
    return emitter.build_file(pages)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="五套 drawio 配色做成一页一套的预览（给用户挑风格用）")
    parser.add_argument("-o", "--out", default="scheme-preview.drawio")
    parser.add_argument("--schemes", nargs="*", default=None,
                        help=f"只预览这几套（默认全部：{'、'.join(palette.available_schemes())}）")
    args = parser.parse_args(argv)

    try:
        xml = build(schemes=args.schemes)
    except (KeyError, emitter.SpecError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    problems = emitter._load_sibling("check_drawio").check_text(xml)
    if problems:
        print("✗ 预览文件没过结构自检（这是 bug，请报出来）：", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    try:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(xml)
    except OSError as exc:
        print(f"写不了 {args.out}：{exc}", file=sys.stderr)
        return 1
    page_list = "、".join(args.schemes or palette.available_schemes())
    print(f"✓ 已写出 {args.out}（{len(args.schemes or palette.available_schemes())} 页："
          f"{page_list}）")
    print("  在 draw.io 里打开，**切底部页签**挑一套；挑完告诉我就照那套出正式图。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
