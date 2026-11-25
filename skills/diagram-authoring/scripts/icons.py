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
import base64
import copy
import json
import math
import os
import re
import sys
import zlib
from xml.sax.saxutils import escape as _xml_escape

# 图标放进节点盒子里的默认高度（没有给具体节点时用）。
ICON_HEIGHT = 28.0
# 图标**统一描边宽度**。为什么要有这个数：素材库是不同作者做的，同一个库里
# 都能出现 strokeWidth 1 与 4 混用 —— 直接照抄进图里就成了"粗黑图标 + 细线图标"
# 混在一起（用户 2026-09-16 反馈："图标风格不一致"）。所以 place() 落笔时一律改写成它。
# 【待验证】2.0 是取了内置 sigil 那一档（两者必须看起来是一套），没有做过用户校准。
ICON_STROKE_WIDTH = 2.0
# 图标的粗糙度：与图纸的手绘调子一致（0 = 光滑，1 = 手绘）
ICON_ROUGHNESS = 1
# 图标里**允许保留的实心**上限：该元素面积 ≤ 图标整体包围盒的这个比例时算"细节"
# （点、箭头头部），保留其实心；超过就当"大块实心"转成空心。
# 为什么需要这条：素材里"整块填黑"的图形和"细线描边"的图形放在一张图上，
# 是两套视觉语言（用户 2026-09-16："图标风格不一致"）。我们自己的 sigil 里
# `_queue` 的三个点、`_plain` 的点也是实心，它们属于细节，必须留下。
ICON_SOLID_MAX_SHARE = 0.25
# 图标颜色在画布上的最低对比度。WCAG 对"非文本图形"的要求是 3:1 —— 照它来。
# 为什么需要这条：品牌色常常在我们这套浅画布上读不出来（实测 AWS 橙 #FF9900
# 对比度只有 2.04）。这时候**保留色相、往墨色压**，而不是丢掉颜色或让它糊掉。
ICON_MIN_CONTRAST = 3.0
# 图标颜色策略：auto（默认）/ ink（一律单色）/ native（原样保留）
ICON_COLOUR_MODES = ("auto", "ink", "native")
# 按**节点自身的高度**算图标高度，再夹到这个区间里。
#
# 为什么按比例而不是固定值：用户的原话是"让它更加适配每一个元素"——
# 固定高度在两层文字的大节点里显得小、在单行小节点里又显得挤。
# 为什么还要夹上限：节点高度会随内容变，不夹的话大节点的图标会大到失衡。
#
# 不构成循环：算的是**文字盒子**的高度（图标加进去之前那个），
# 所以"图标撑大节点 → 节点再撑大图标"这条回路不存在。
ICON_RATIO = 0.62
ICON_MIN = 22.0
ICON_MAX = 36.0


def height_for(text_box_height: float) -> float:
    """这个节点的图标该多高 —— 按节点自己的高度算，不搞一刀切。"""
    return max(ICON_MIN, min(ICON_MAX, text_box_height * ICON_RATIO))


def glyph_only(elements: list) -> list:
    """只留图形，丢掉素材自带的文字。

    ## 为什么默认这么做

    节点自己已经有标签了，素材项自带的文字是**冗余**的。实测（429 项里 317 项带文字）：
    那些文字缩到节点尺寸后只有 3~6px，既看不清又脏；而且它还占着地方，
    把真正的图形挤到中位只有 **70%** 的大小。

    丢掉之后：图形中位能占满 100%，而且"图标自带文字看不清"这个问题
    **从构造上消失**（不是靠报警，是靠不让它出现）。

    ## 什么时候不能丢

    整个素材项只有文字（那就是一个文字素材）—— 这时原样返回，
    不能返回空数组（空数组会让节点上什么也不显示，而且不报错）。
    """
    glyph = [el for el in elements if el.get("type") != "text"]
    return glyph if glyph else list(elements)
# 图标与文字之间留的空隙。**待验证**（没有真实数据校准过）。
ICON_GAP = 10.0


class LibraryError(ValueError):
    """素材库本身的问题（读不了 / 格式不认识 / 名字不存在）。"""


# 官方素材库的本地缓存目录（`scripts/icons_fetch.py` 往里下载）。
# 它是**唯一**说"缓存在哪"的地方；取库的工具从这里读，避免两处各写一份。
ICON_CACHE_ENV = "DIAGRAM_ICON_CACHE"


def _home() -> str:
    return os.path.expanduser(os.environ.get("AGENT_SKILLS_HOME", "~/.agent-skills"))


def legacy_cache_dir() -> str:
    return os.path.join(os.path.expanduser("~"), ".cache", "diagram-authoring", "libraries")


def default_cache_dir() -> str:
    root = os.environ.get("AGENT_SKILLS_DATA_DIR", "").strip()
    data = os.path.expanduser(root) if root else os.path.join(_home(), "data")
    new = os.path.join(data, "diagram-authoring", "libraries")
    if not os.path.isdir(new) and os.path.isdir(legacy_cache_dir()):
        return legacy_cache_dir()
    return new


def cache_dir(explicit: str | None = None) -> str:
    env = os.environ.get(ICON_CACHE_ENV, "").strip()
    base = explicit or env or default_cache_dir()
    return os.path.expanduser(base)


def library_config_paths() -> list[str]:
    """素材库路径配置：新位置优先，旧位置只读兼容。"""
    shared = os.environ.get("AGENT_SKILLS_CONFIG_DIR", "").strip()
    base = os.path.abspath(os.path.expanduser(shared)) if shared else os.path.join(_home(), "config")
    return [
        os.path.join(base, "excalidraw-library-path"),
        os.path.expanduser("~/.config/excalidraw-library-path"),
    ]


def cached_libraries(where: str | None = None) -> dict[str, str]:
    """缓存里有哪些库：`{slug: 路径}`。slug 就是文件名去掉后缀。"""
    got: dict[str, str] = {}
    try:
        entries = sorted(os.listdir(cache_dir(where)))
    except OSError:
        return got
    for name in entries:
        if name.endswith(".excalidrawlib"):
            got[name[: -len(".excalidrawlib")]] = os.path.join(cache_dir(where), name)
    return got


def library_path(explicit: str | None = None) -> tuple[str | None, str]:
    """素材库路径从哪来：命令行 > 环境变量 > 配置文件。与 vault 路径同一套优先级。

    为什么不做成仓库内的配置：素材库是**几 MB 的第三方文件**，
    放进仓库既有体积问题也有许可问题。所以路径可配、文件不入库。

    `--library` 还接受**缓存里的库名**（`scripts/icons_fetch.py --get` 下来的那些）：
    写 `--library it-icons` 与写全路径等价 —— 名字对不上时把缓存里有什么列出来。
    """
    env = os.environ.get("EXCALIDRAW_LIBRARY", "").strip()
    configs = library_config_paths()
    if explicit:
        if os.path.isfile(explicit):
            return explicit, "命令行参数"
        hit = cached_libraries().get(explicit.strip()) or cached_libraries().get(
            explicit.strip().lower())
        if hit:
            return hit, f"官方素材库缓存里的 {explicit!r}"
        have = "、".join(sorted(cached_libraries())) or "（缓存是空的）"
        return None, (f"命令行参数 {explicit!r} 既不是文件，本地缓存里也没有它；"
                      f"缓存里有：{have}。"
                      f"用 python3 scripts/icons_fetch.py --search <关键词> 从官方目录里找，"
                      f"--get <库名> 下载")
    if env:
        return env, "环境变量 EXCALIDRAW_LIBRARY"
    for config in configs:
        if not os.path.isfile(config):
            continue
        try:
            with open(config, encoding="utf-8") as fh:
                got = fh.read().strip()
        except OSError as exc:
            return None, f"配置文件读取失败：{exc}"
        if got:
            where = "配置文件" if config == configs[0] else "配置文件（旧位置）"
            return os.path.expanduser(got), f"{where} {config}"
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


_PALETTE = None


def _palette():
    """惰性加载同目录的 palette。

    本模块刻意**不在 import 期**依赖兄弟模块（方便单独测试、也避免循环）；
    但"把颜色压到可读"这件事必须只有一份实现，它住在 palette 里。
    """
    global _PALETTE
    if _PALETTE is None:
        import importlib.util
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "palette.py")
        spec = importlib.util.spec_from_file_location("_diagram_palette_for_icons", path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"加载不了 {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _PALETTE = module
    return _PALETTE


def _readable(colour: str, ink: str, canvas: str | None) -> str:
    """把一个颜色压到画布上可读（保留色相）—— 实现住在 `palette.readable_on`。"""
    if not canvas or not colour.startswith("#"):
        return colour
    return _palette().readable_on(colour, ink, canvas, ICON_MIN_CONTRAST)


def place(elements: list, left: float, top: float, *, key: str,
          target_height: float = ICON_HEIGHT,
          stroke: str | None = None,
          canvas: str | None = None,
          colours: str = "auto") -> list[dict]:
    """把一项素材复制进场景：缩放到目标高度、移到 (left, top)、换成全新的 id，
    并把**风格统一**（描边粗细 / 颜色 / 粗糙度 / 填充）。

    ## 为什么要统一风格（而不是"尊重素材原样"）

    素材是不同作者做的：同一个库里都能出现 `strokeWidth: 1` 与 `: 4` 混用，
    颜色有的是纯黑、有的是深灰，填充有的实心有的空。照抄进同一张图，结果就是
    **粗黑图标和细线图标混着**（用户原话："图标风格不一致啊"）。

    规矩：**描边粗细一律 `ICON_STROKE_WIDTH`；颜色一律用调用方给的墨色
    （＝所属节点自己的描边色，所以图标与它所在的框同色）；有填充的图形
    填充色也换成同一个墨色（保持"实心/空心"的设计，但不引入第二种颜色）。**

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

    # 图标整体包围盒 —— 用来判断某个实心元素是"细节"还是"大块"
    glyph_x = min(el["x"] for el in elements)
    glyph_y = min(el["y"] for el in elements)
    glyph_w = max(el["x"] + el.get("width", 0) for el in elements) - glyph_x
    glyph_h = max(el["y"] + el.get("height", 0) for el in elements) - glyph_y
    glyph_area = glyph_w * glyph_h

    # ── 颜色策略（见 ICON_MIN_CONTRAST / ICON_COLOUR_MODES）──
    # 多色素材（品牌 logo、彩色图标）是**作品**：保留它的配色，只把读不出来的颜色压一压；
    # 单色素材是**线描图形**：一律用墨色，跟图纸同一套语言。
    distinct = {c.lower() for c in visible_colours(elements)}
    multicolour = len(distinct) >= 2
    keep_native = colours == "native" or (colours == "auto" and multicolour)
    ink = stroke or elements[0].get("strokeColor") or "#000000"

    def _colour(original: str) -> str:
        if not keep_native:
            return ink
        if colours == "native":
            return original
        return _readable(original, ink, canvas)

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
        # ── 风格统一（见函数说明）──
        new["strokeWidth"] = ICON_STROKE_WIDTH
        new["roughness"] = ICON_ROUGHNESS
        new["opacity"] = 100
        new["strokeColor"] = _colour(original.get("strokeColor") or ink)
        # 实心处理：多色素材的实心**属于作品**（品牌 logo 的色块），保留；
        # 单色素材里小面积实心（点 / 箭头头部）也保留，大块实心转空心
        # —— 线描风格才是这一套图的统一语言。
        filled = (original.get("backgroundColor") or "transparent") != "transparent"
        area = (original.get("width") or 0) * (original.get("height") or 0)
        detail = glyph_area > 0 and area / glyph_area <= ICON_SOLID_MAX_SHARE
        if filled and (keep_native or detail):
            new["backgroundColor"] = _colour(original["backgroundColor"])
        else:
            new["backgroundColor"] = "transparent"
        new["fillStyle"] = "solid"
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
        # ⚠ 这里**刻意不**把 strokeWidth 按 scale 缩放。
        # 按比例缩放看着"更忠实素材"，但它会让同一张图里 22px 的小图标与 44px 的
        # 大图标描边粗细不同 —— 那正是用户说的"图标风格不一致"。
        # 统一粗细（ICON_STROKE_WIDTH）才是这套图的目标：所有图标视觉重量一致。
        out.append(new)
    return out


def visible_colours(elements: list) -> list[str]:
    """图标里**看得见**的颜色（描边 + 不透明的填充）。

    为什么要挑着算：素材元素区分"描边色"和"填充色"，而填充常常是 `transparent`
    （线框图标）。把 transparent 也拿去算对比度，会得到一堆无意义的结果。
    只算真正画出颜色的那些。
    """
    colours: list[str] = []
    for el in elements:
        stroke = el.get("strokeColor")
        if isinstance(stroke, str) and stroke.startswith("#"):
            colours.append(stroke)
        background = el.get("backgroundColor")
        if (isinstance(background, str) and background.startswith("#")
                and background not in ("transparent", "none")):
            colours.append(background)
    return colours


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


def _norm_token(text: str) -> str:
    """规范化图标名用于无损宽松匹配（忽略大小写、空格、横杠、下划线）。"""
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", text.strip().lower())


def resolve(library: dict, name: str) -> list:
    """按名字取一项：精确匹配 → 忽略大小写唯一匹配 → 规范化分隔符唯一匹配。

    找不到或出现多个重名歧义时抛错并列出候选项 —— 绝不静默错换。
    """
    items = library["items"]
    if name in items:
        return items[name]
    low = name.strip().lower()
    ci_hits = [k for k in items if k.strip().lower() == low]
    if len(ci_hits) == 1:
        return items[ci_hits[0]]
    norm = _norm_token(name)
    if norm:
        norm_hits = [k for k in items if _norm_token(k) == norm]
        if len(norm_hits) == 1:
            return items[norm_hits[0]]
        if len(norm_hits) > 1:
            raise LibraryError(
                f"素材库里 {name!r} 命中多个同名项：{sorted(norm_hits)[:8]}；请写完整名称")
    hint = "（这个库是 v1 格式，项没有名字，只能用 `#序号`）" if not library["named"] else ""
    near = [k for k in names(library) if low and low in k.lower()][:8]
    sample = near or names(library)[:12]
    raise LibraryError(
        f"素材库里没有 {name!r}；可用 {len(items)} 项里的：{sample}…{hint}")


def split_library_ref(name: str) -> tuple[str | None, str]:
    """解析跨库引用语法 `库名:图标名`。不带冒号时返回 `(None, name)`。"""
    if ":" in name:
        lib_ref, item_name = name.split(":", 1)
        if lib_ref.strip() and item_name.strip():
            return lib_ref.strip(), item_name.strip()
    return None, name


def resolve_across_libraries(name: str, explicit_library: str | None = None,
                             *, cache: str | None = None,
                             loaded: dict[str, dict] | None = None) -> tuple[list, str]:
    """从显式库、配置库或全部本地缓存 `.excalidrawlib` 中解析图标。

    支持：
    1. `"库名:图标名"` 跨库直连（同一张图可混用多个 `.excalidrawlib`）；
    2. 显式 `--library` 指定的库文件或缓存库名；
    3. 未传 `--library` 时自动扫描配置库与本地缓存目录内全部 `.excalidrawlib`。
    """
    store = loaded if loaded is not None else {}

    def _get_lib(path: str) -> dict:
        if path not in store:
            store[path] = load(path)
        return store[path]

    cached = cached_libraries(cache)
    lib_ref, item_name = split_library_ref(name)
    if lib_ref is not None:
        if os.path.isfile(lib_ref):
            return resolve(_get_lib(lib_ref), item_name), os.path.basename(lib_ref)
        hit = cached.get(lib_ref) or cached.get(lib_ref.lower())
        if hit:
            return resolve(_get_lib(hit), item_name), lib_ref
        have = "、".join(sorted(cached)) or "（本地缓存为空）"
        raise LibraryError(
            f"图标 {name!r} 指定的素材库 {lib_ref!r} 未找到；本地已缓存：{have}。"
            f"用 python3 scripts/icons_fetch.py --get {lib_ref!r} 下载")

    if explicit_library:
        path, source = library_path(explicit_library)
        if not path:
            raise LibraryError(f"找不到图标素材库（{source}）")
        return resolve(_get_lib(path), name), os.path.basename(path)

    # 先查环境变量 / 配置文件指定的默认库
    cfg_path, _cfg_src = library_path(None)
    if cfg_path and os.path.isfile(cfg_path):
        try:
            return resolve(_get_lib(cfg_path), name), os.path.basename(cfg_path)
        except LibraryError:
            if not cached:
                raise

    # 自动扫描全部本地缓存的 .excalidrawlib
    if not cached:
        raise LibraryError(
            f"找不到图标 {name!r}：未配置素材库且本地缓存为空。"
            f"运行 python3 scripts/icons_fetch.py --find <关键词> 查找并 --get <库名> 下载")

    exact_hits: list[tuple[str, list]] = []
    fuzzy_hits: list[tuple[str, str, list]] = []
    for slug_name, path in sorted(cached.items()):
        try:
            lib = _get_lib(path)
        except LibraryError:
            continue
        if name in lib["items"]:
            exact_hits.append((slug_name, lib["items"][name]))
            continue
        try:
            els = resolve(lib, name)
            # 找出匹配到的真实项名用于歧义提示
            norm = _norm_token(name)
            real = next((k for k in lib["items"] if k.lower() == name.lower()
                         or _norm_token(k) == norm), name)
            fuzzy_hits.append((slug_name, real, els))
        except LibraryError:
            continue

    if len(exact_hits) == 1:
        return exact_hits[0][1], exact_hits[0][0]
    if len(exact_hits) > 1:
        choices = [f"{s}:{name}" for s, _ in exact_hits]
        raise LibraryError(
            f"图标 {name!r} 在多个缓存库中均存在，请写成库名前缀消歧：{choices}")
    if len(fuzzy_hits) == 1:
        return fuzzy_hits[0][2], fuzzy_hits[0][0]
    if len(fuzzy_hits) > 1:
        choices = [f"{s}:{real}" for s, real, _ in fuzzy_hits]
        raise LibraryError(
            f"图标 {name!r} 在多个缓存库中匹配到候选项，请写成库名前缀消歧：{choices}")

    raise LibraryError(
        f"图标 {name!r} 在本地已缓存的 {len(cached)} 个素材库（{', '.join(sorted(cached))}）里都未找到。"
        f"用 python3 scripts/icons_fetch.py --find {name!r} 查找具体项名或下载新库")


def search_cached(keyword: str, *, cache: str | None = None) -> list[tuple[str, str, int]]:
    """离线在全部已缓存 `.excalidrawlib` 里搜索图标名，返回 `[(slug, item_name, element_count)]`。"""
    low = keyword.strip().lower()
    norm = _norm_token(keyword)
    hits: list[tuple[str, str, int]] = []
    for slug_name, path in sorted(cached_libraries(cache).items()):
        try:
            lib = load(path)
        except LibraryError:
            continue
        for item_name, elements in sorted(lib["items"].items()):
            if (not low or low in item_name.lower() or low in slug_name.lower()
                    or (norm and norm in _norm_token(item_name))):
                hits.append((slug_name, item_name, len(elements)))
    return hits


def _svg_stroke_dasharray(style: str | None) -> str:
    if style == "dashed":
        return ' stroke-dasharray="6 4"'
    if style == "dotted":
        return ' stroke-dasharray="2 3"'
    return ""


def to_svg(elements: list, *, target_height: float = ICON_HEIGHT,
           stroke: str | None = None, canvas: str | None = None,
           colours: str = "auto") -> str:
    """将任意 `.excalidrawlib` 或内置 sigil 元素列表渲染为独立 `<svg>` 字符串。

    复用 `place()` 的缩放、描边统一与 `auto/ink/native` 配色规则，
    让 draw.io 与 Excalidraw 使用同一套 `.excalidrawlib` 素材且观感一致。
    """
    placed = place(elements, 0.0, 0.0, key="svg", target_height=target_height,
                   stroke=stroke, canvas=canvas, colours=colours)
    if not placed:
        return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16"/>'

    xs: list[float] = []
    ys: list[float] = []
    for el in placed:
        ex, ey = float(el.get("x", 0.0)), float(el.get("y", 0.0))
        ew, eh = float(el.get("width", 0.0)), float(el.get("height", 0.0))
        pts = el.get("points")
        if isinstance(pts, list) and pts:
            for px, py in pts:
                xs.append(ex + float(px))
                ys.append(ey + float(py))
        else:
            xs.extend([ex, ex + ew])
            ys.extend([ey, ey + eh])

    pad = ICON_STROKE_WIDTH + 2.0
    min_x, max_x = min(xs) - pad, max(xs) + pad
    min_y, max_y = min(ys) - pad, max(ys) + pad
    vb_w = max(1.0, round(max_x - min_x, 2))
    vb_h = max(1.0, round(max_y - min_y, 2))

    parts: list[str] = []
    for el in placed:
        etype = el.get("type")
        ex, ey = float(el.get("x", 0.0)), float(el.get("y", 0.0))
        ew, eh = float(el.get("width", 0.0)), float(el.get("height", 0.0))
        sc = _xml_escape(str(el.get("strokeColor") or "#1f2937"))
        bg = str(el.get("backgroundColor") or "transparent")
        fill = "none" if bg in ("transparent", "none", "") else _xml_escape(bg)
        sw = round(float(el.get("strokeWidth", ICON_STROKE_WIDTH)), 2)
        dash = _svg_stroke_dasharray(el.get("strokeStyle"))
        angle = float(el.get("angle") or 0.0)
        transform = ""
        if abs(angle) > 1e-4:
            deg = round(math.degrees(angle), 2)
            cx, cy = round(ex + ew / 2.0, 2), round(ey + eh / 2.0, 2)
            transform = f' transform="rotate({deg} {cx} {cy})"'

        if etype == "rectangle":
            rx = ""
            if el.get("roundness"):
                r = round(min(ew, eh) * 0.16, 2)
                rx = f' rx="{r}" ry="{r}"'
            parts.append(
                f'<rect x="{ex:.2f}" y="{ey:.2f}" width="{ew:.2f}" height="{eh:.2f}"{rx}'
                f' fill="{fill}" stroke="{sc}" stroke-width="{sw}"{dash}{transform}/>'
            )
        elif etype == "ellipse":
            cx, cy = ex + ew / 2.0, ey + eh / 2.0
            rx, ry = max(0.5, ew / 2.0), max(0.5, eh / 2.0)
            parts.append(
                f'<ellipse cx="{cx:.2f}" cy="{cy:.2f}" rx="{rx:.2f}" ry="{ry:.2f}"'
                f' fill="{fill}" stroke="{sc}" stroke-width="{sw}"{dash}{transform}/>'
            )
        elif etype == "diamond":
            pts_str = (f"{ex + ew / 2.0:.2f},{ey:.2f} {ex + ew:.2f},{ey + eh / 2.0:.2f} "
                       f"{ex + ew / 2.0:.2f},{ey + eh:.2f} {ex:.2f},{ey + eh / 2.0:.2f}")
            parts.append(
                f'<polygon points="{pts_str}" fill="{fill}" stroke="{sc}"'
                f' stroke-width="{sw}" stroke-linejoin="round"{dash}{transform}/>'
            )
        elif etype in ("line", "arrow", "freedraw"):
            pts = el.get("points") or []
            if len(pts) < 2:
                continue
            abs_pts = [(ex + float(p[0]), ey + float(p[1])) for p in pts]
            pts_str = " ".join(f"{x:.2f},{y:.2f}" for x, y in abs_pts)
            closed = (math.dist(abs_pts[0], abs_pts[-1]) < 1.5 and len(abs_pts) >= 3)
            if closed:
                parts.append(
                    f'<polygon points="{pts_str}" fill="{fill}" stroke="{sc}"'
                    f' stroke-width="{sw}" stroke-linejoin="round"{dash}{transform}/>'
                )
            else:
                parts.append(
                    f'<polyline points="{pts_str}" fill="{fill}" stroke="{sc}"'
                    f' stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"{dash}{transform}/>'
                )
        elif etype == "text":
            txt = _xml_escape(str(el.get("text") or ""))
            fs = round(float(el.get("fontSize") or 12.0), 2)
            parts.append(
                f'<text x="{ex + ew / 2.0:.2f}" y="{ey + eh * 0.78:.2f}" text-anchor="middle"'
                f' font-family="sans-serif" font-size="{fs}" fill="{sc}"{transform}>{txt}</text>'
            )

    return (f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="{min_x:.2f} {min_y:.2f} {vb_w:.2f} {vb_h:.2f}" '
            f'width="{vb_w:.2f}" height="{vb_h:.2f}">'
            + "".join(parts) + "</svg>")


def to_svg_data_uri(elements: list, *, target_height: float = ICON_HEIGHT,
                    stroke: str | None = None, canvas: str | None = None,
                    colours: str = "auto") -> str:
    """生成 draw.io/mxGraph 兼容的 SVG data URI（逗号分隔、无 `;base64` 分号冲突）。"""
    svg = to_svg(elements, target_height=target_height, stroke=stroke,
                 canvas=canvas, colours=colours)
    payload = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml,{payload}"


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="查看 Excalidraw 素材库里有什么")
    ap.add_argument("library", nargs="?", help="*.excalidrawlib")
    ap.add_argument("--grep", help="只列名字里含这个词的")
    ap.add_argument("--size", metavar="NAME", help="看某一项的固有尺寸")
    args = ap.parse_args(argv)

    path, source = library_path(args.library)
    if not path:
        print(f"没找到素材库（{source}）。"
              f"用 --library 指定，或写一行路径到 {library_config_paths()[0]}")
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
