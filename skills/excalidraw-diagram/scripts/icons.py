#!/usr/bin/env python3
"""图标 —— 从 Excalidraw 素材库（`.excalidrawlib`）取图形，放进生成的场景里。

## 为什么是"复制元素"而不是"让用户拖进去"

素材库文件里存的就是**原始元素**（带自己的 x/y/width/height/points）。所以完全可以把
选中的那一项原样复制进我们生成的场景 —— 不需要网络、不需要在 Excalidraw 里手拖，
而且结果是可复现的（同一个库、同一个名字 → 同一张图）。

## 为什么图标是"第二个尺寸来源"

文字尺寸是我们自己量的（`text_metrics`），而图标的**固有宽高来自外部文件**。
这是第一次有外部数据直接决定画出来的东西有多大 —— 所以：

- 它必须被**算进节点的盒子**（否则图标会盖住文字或溢出）
- `references/validation.md` 第六节那条"尺寸只有一个来源"的前提**从这一版起不再成立**，
  已经按约定回去改过了（先改文档，再改 `TestSizeSourcePremise`）

## 格式

两种都支持（官方从 v1 换到 v2 时没有保留兼容层）：

- v1：`{"type": "excalidrawlib", "version": 1, "library": [[元素...], ...]}`，项**没有名字**
- v2：`{"type": "excalidrawlib", "version": 2, "libraryItems": [{"id", "name", "elements"}, ...]}`

v1 没有名字，只能按序号索引 —— 这种项一律用 `#<序号>` 当名字，并且**明确标注**
"这个库没有名字"，而不是造一个看起来像名字的东西。

## 未知名字判失败，不 fallback

与 `kind` / `shape` / `emphasis` 同一条规矩：报错并列出可用的名字。
静默换一个图标，看图的人根本不知道原本想要的是什么。
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import sys
import zlib

# 图标放进节点盒子里的目标高度。宽高按原始比例缩放到这个高度 ——
# 之所以只定高度：素材库里的图标宽高比五花八门，按宽度缩放会让高的图标压到文字。
ICON_HEIGHT = 22.0
# 图标与文字之间留的空隙。**待验证**（没有真实数据校准过）。
ICON_GAP = 10.0


class LibraryError(ValueError):
    """素材库本身的问题（读不了 / 格式不认识 / 名字不存在）。"""


def library_path(explicit: str | None = None) -> tuple[str | None, str]:
    """素材库路径从哪来：命令行 > 环境变量 > 配置文件。与 vault 路径同一套优先级。

    为什么不做成仓库内的配置：素材库是**几 MB 的第三方文件**，
    放进仓库既有体积问题也有许可问题。所以路径可配、文件不入库。
    """
    env = os.environ.get("EXCALIDRAW_LIBRARY", "").strip()
    config = os.path.expanduser("~/.config/excalidraw-library-path")
    if explicit:
        return explicit, "命令行参数"
    if env:
        return env, "环境变量 EXCALIDRAW_LIBRARY"
    if os.path.isfile(config):
        try:
            with open(config, encoding="utf-8") as fh:
                got = fh.read().strip()
        except OSError as exc:
            return None, f"配置文件读取失败：{exc}"
        if got:
            return os.path.expanduser(got), f"配置文件 {config}"
    return None, "未配置"


def load(path: str) -> dict:
    """读素材库，返回 `{名字: 元素数组}`，外加 `source` 与 `named` 两个元信息。"""
    if not os.path.isfile(path):
        raise LibraryError(f"素材库读不到：{path}")
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise LibraryError(f"素材库解析失败：{exc}") from None

    if not isinstance(raw, dict) or raw.get("type") != "excalidrawlib":
        raise LibraryError("这不是 Excalidraw 素材库（顶层 type 不是 excalidrawlib）")

    items: dict[str, list] = {}
    named = True
    if isinstance(raw.get("libraryItems"), list):        # v2
        for index, item in enumerate(raw["libraryItems"]):
            if not isinstance(item, dict) or not isinstance(item.get("elements"), list):
                continue
            name = item.get("name") or item.get("id") or f"#{index}"
            items[str(name)] = item["elements"]
    elif isinstance(raw.get("library"), list):           # v1：没有名字
        named = False
        for index, elements in enumerate(raw["library"]):
            if isinstance(elements, list):
                items[f"#{index}"] = elements
    else:
        raise LibraryError("素材库既没有 libraryItems（v2）也没有 library（v1）")

    return {"source": path, "named": named, "items": items}


def names(library: dict) -> list[str]:
    return sorted(library["items"])


def intrinsic_size(elements: list) -> tuple[float, float]:
    """这一项占多大 —— **外部数据**，不是我们算出来的。"""
    xs: list[float] = []
    ys: list[float] = []
    for el in elements:
        xs += [el["x"], el["x"] + el.get("width", 0)]
        ys += [el["y"], el["y"] + el.get("height", 0)]
    if not xs:
        return 0.0, 0.0
    return max(xs) - min(xs), max(ys) - min(ys)


def fit_scale(elements: list, target_height: float = ICON_HEIGHT) -> float:
    """等比缩放到目标高度。高度为 0 时不缩放（有些库项是纯线条，没有高度）。"""
    _w, h = intrinsic_size(elements)
    if h <= 0 or target_height <= 0:
        return 1.0
    return target_height / h


def _seed(element_id: str) -> int:
    """由新 id 派生 seed —— 同一张图重复生成要得到一模一样的文件。"""
    return zlib.crc32(element_id.encode("utf-8")) & 0x7FFFFFFF


def _scale_points(points: list, scale: float) -> list:
    return [[round(p[0] * scale, 2), round(p[1] * scale, 2)] for p in points]


def place(elements: list, left: float, top: float, *, key: str,
          target_height: float = ICON_HEIGHT) -> list[dict]:
    """把一项素材复制进场景：缩放到目标高度、移到 (left, top)、换成全新的 id。

    ## 为什么必须重映射 id 与引用

    素材库里的元素带着自己的 id，以及指向别的元素的引用（`containerId`、
    `boundElements`、`startBinding`/`endBinding`、`groupIds`）。直接把两份素材
    放进同一个场景，或者复用一个节点的两次图标，id 就会撞 —— 撞了之后
    Excalidraw 里拖动一个会连带动另一个。所以这里**整体重映射**。

    ## 为什么统一挂一个 groupId

    图标常常是"图形 + 文字"好几个元素。挂同一个 groupId：
      ① 用户在 Excalidraw 里拖动时它们一起动；
      ② 本项目的"没有 groupId 的才是节点"这条判定（见 emit 的说明）
         会**自动**把图标当装饰、不参与穿透检查与标签搜索 —— 这正是想要的行为。
    """
    if not elements:
        return []
    scale = fit_scale(elements, target_height)
    min_x = min(el["x"] for el in elements)
    min_y = min(el["y"] for el in elements)
    dx = left - min_x * scale
    dy = top - min_y * scale

    group_id = f"{key}-group"
    id_map = {el["id"]: f"{key}-{i}" for i, el in enumerate(elements)}

    out: list[dict] = []
    for el, original in zip(elements, elements):
        new = copy.deepcopy(original)                   # 不动调用方的东西
        new["id"] = id_map[original["id"]]
        new["x"] = round(original["x"] * scale + dx, 2)
        new["y"] = round(original["y"] * scale + dy, 2)
        new["width"] = round(original.get("width", 0) * scale, 2)
        new["height"] = round(original.get("height", 0) * scale, 2)
        new["groupIds"] = [group_id]
        new["frameId"] = None
        new["seed"] = _seed(new["id"])
        new["versionNonce"] = _seed(new["id"] + "nonce")
        new["isDeleted"] = False
        new["locked"] = False
        # 引用整体改指向新 id；引不到的一律清空（不能留一个指向别的图标的悬空引用）
        new["containerId"] = id_map.get(original.get("containerId"))
        bound = original.get("boundElements")
        if isinstance(bound, list):
            new["boundElements"] = [{"type": b.get("type"), "id": id_map[b["id"]]}
                                    for b in bound if b.get("id") in id_map] or None
        for field in ("startBinding", "endBinding"):
            binding = original.get(field)
            if isinstance(binding, dict):
                target = binding.get("elementId")
                new[field] = ({**binding, "elementId": id_map[target]}
                              if target in id_map else None)
        if isinstance(original.get("points"), list):
            new["points"] = _scale_points(original["points"], scale)
        if original.get("fontSize"):
            new["fontSize"] = round(original["fontSize"] * scale, 2)
        if original.get("strokeWidth"):
            new["strokeWidth"] = round(original["strokeWidth"] * scale, 2)
        out.append(new)
    return out


def background_elements(elements: list) -> set[str]:
    """图标里哪些元素是"图形/背景"（用来判断图标是否与底色冲突）。

    只看 `backgroundColor` 不为透明 —— 素材库里透明背景的线条图标很常见。
    """
    return {el["id"] for el in elements if el.get("backgroundColor") not in (None, "transparent")}


# 缩到这个字号以下就看不清了。**待验证**：按常见可读下限拍的，没有实测校准。
MIN_LEGIBLE_PT = 9.0


def scaled_font_sizes(elements: list, target_height: float = ICON_HEIGHT) -> list[float]:
    """这一项缩到目标高度后，它自带的文字会变成多大。"""
    scale = fit_scale(elements, target_height)
    return [round(el["fontSize"] * scale, 2)
            for el in elements if el.get("fontSize")]


def readability(elements: list, target_height: float = ICON_HEIGHT
                ) -> tuple[float, float] | None:
    """返回 `(最小字号, 缩放比)`；没有文字元素时返回 None。

    ## 为什么需要这条

    实测过一件事：vault 里那个素材库是**厂商示意图**集合，不是图标集 ——
    每一项是"图形 + 自带文字标签"的小示意图。缩到节点里当图标用，自带的文字
    会变成 2px 的噪点，既看不清又脏。图长得没错，是**素材选错了**。

    这是纯机械判断（外部文件里的字号 × 缩放比），所以做成检查而不是在文档里写一句提醒。
    """
    sizes = scaled_font_sizes(elements, target_height)
    if not sizes:
        return None
    return min(sizes), fit_scale(elements, target_height)


def resolve(library: dict, name: str) -> list:
    """按名字取一项。找不到就抛错并**列出可用的名字** —— 不 fallback。"""
    items = library["items"]
    if name not in items:
        hint = "（这个库是 v1 格式，项没有名字，只能用 `#序号`）" if not library["named"] else ""
        raise LibraryError(
            f"素材库里没有 {name!r}；可用 {len(items)} 项里的：{names(library)[:12]}…{hint}")
    return items[name]


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="查看 Excalidraw 素材库里有什么")
    ap.add_argument("library", nargs="?", help="*.excalidrawlib")
    ap.add_argument("--grep", help="只列名字里含这个词的")
    ap.add_argument("--size", metavar="NAME", help="看某一项的固有尺寸")
    args = ap.parse_args(argv)

    path, source = library_path(args.library)
    if not path:
        print(f"没找到素材库（{source}）。"
              f"用 --library 指定，或写一行路径到 ~/.config/excalidraw-library-path")
        return 2
    try:
        lib = load(path)
    except LibraryError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1

    got = names(lib)
    if args.grep:
        got = [n for n in got if args.grep.lower() in n.lower()]
    print(f"素材库 {path}（{len(lib['items'])} 项，"
          f"{'有名字' if lib['named'] else '无名字（v1）'}）")
    for name in got[:200]:
        elements = lib["items"][name]
        w, h = intrinsic_size(elements)
        print(f"  {name:<34} {len(elements)} 个元素  {w:.0f}×{h:.0f}")
    if len(got) > 200:
        print(f"  …… 还有 {len(got) - 200} 项")
    if args.size:
        try:
            w, h = intrinsic_size(resolve(lib, args.size))
        except LibraryError as exc:
            print(f"✗ {exc}", file=sys.stderr)
            return 1
        print(f"\n{args.size}: {w:.1f}×{h:.1f}，放进节点会缩放到高 {ICON_HEIGHT}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
