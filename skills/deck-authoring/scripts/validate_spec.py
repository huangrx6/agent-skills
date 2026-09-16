#!/usr/bin/env python3
"""规格校验 —— 检查模型写出来的 `deck-spec.json`。

这是**输入层**的校验（spec 写对没有），不是产物校验（那是 `check.py` 的六项）。
两者分开，因为修复动作不同：spec 错了改内容，产物不对改版式 / 色板。

## 字段集是**封闭**的（这条是核心设计）

`check.py` 只主动拦 `color` 一个字段，其余未知键它是**静默忽略**的。静默的后果是：

> 模型顺手写个 `fontSize: 120` 或 `x: 40` → 没报错 → 它以为生效了 → 出的图却没变
> → 它开始怀疑整条链路，去改别的没用的地方。

本 skill 的整个立论就是"坐标 / 字号 / 色值由脚本算，模型只写内容"。所以这里把字段集
写死、未知项直接判失败 —— 让"顺手加一个"**当场撞墙**，而不是静默失效。

和 `check.py` 的分工：那边查"产物长成什么样"，这边查"你让我画什么"。

用法：
    python3 validate_spec.py deck-spec.json
    python3 validate_spec.py deck-spec.json --json

退出码：0 = 通过，1 = 有 error，2 = 读不到 / 不是合法 JSON。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STYLES_DIR = os.path.join(HERE, "..", "styles")

# 封闭字段集。加字段要同时改这里与 `references/style-architecture.md` ——
# 这正是设计意图：让"顺手加一个"变得有摩擦。
DECK_FIELDS = {"colorSet", "seed", "title", "slides", "style", "brand", "note"}
# colorSet **必填具名**（配色由作者定：先看候选，选定后写名字；
# 对比度由 ink.py/check.py 验收）。门里没有"自动配色"这条路。
CHART_TYPES = ("bar", "bar-horizontal", "line", "area", "bar-stacked",
               "donut", "scatter", "combo")
# 视觉载体：每页**显式决定**这页靠什么立住。不写下来就等于没决定 ——
# 实测的后果是全篇靠文字撑、图与元素一直没人提。四个档就是这条流水线能交付的
# 四种载体（其余"元素"靠版式与条目形状表达，不另设档）：见 references/images.md。
# 页面角色（这一页"在干什么"）：**语义**，不是结构枚举 —— 页型说结构（双栏/
# 图页/图表），角色说意图。配版式、看重复、写内容都先看它。
# 词表是封闭的：拼错的角色名会让它静默失效（和拼错 layout 名一个性质）。
# 类型映射（哪几个页型承载得了哪个角色）在 layout/roles.py —— 两份的**名字**
# 由测试钉住一致（validate_spec 零依赖，不导入 layout/）。
ROLES = ("cover", "transition", "statement", "breakdown", "evidence", "metric", "trend", "composition",
         "comparison", "process", "capabilities", "architecture", "flow", "topology", "hero_visual", "context_image",
         "risks", "actions", "result", "observation", "team", "closing")
VISUAL_KINDS = ("none", "evidence_image", "diagram", "data")
VISUAL_KEYS = {"kind", "intent", "note", "ratio"}
# 比例的合理区间（宽/高）。超出就是写错了（把像素当比例、或写了 1:0 这种）。
RATIO_RANGE = (0.4, 2.6)
VISUAL_IMAGE_KINDS = ("evidence_image", "diagram")

# `notes`（讲稿）**每一种版式都能写** —— 它是给人看的，不影响排版：
# 它不发任何元素（所以不进清单、不进测量），只随产物走一份 JSON，由演示台读。
SLIDE_FIELDS = {
    "title":         {"type", "title", "subtitle", "color", "titleTier", "visual",
                      "role", "notes"},
    "content-text":  {"type", "title", "bullets", "color", "titleTier", "bulletTier",
                      "visual", "role", "notes"},
    "content-image": {"type", "title", "bullets", "image", "caption", "color",
                   "layout", "titleTier", "bulletTier", "visual", "role", "notes"},
    "two-column":    {"type", "title", "columns", "color", "layout", "titleTier",
                   "bulletTier", "visual", "role", "notes"},
    "timeline":      {"type", "title", "nodes", "color", "titleTier", "visual",
                      "role", "notes"},
    # 图表的 DSL：几何/样式/动画都不在 spec 里，AI 只写语义。
    # `chart`（图形类型）**必填** —— 只认 CHART_TYPES 里的八个值，没有推断。
    "chart":         {"type", "title", "data", "unit", "caption", "color",
                      "chart", "intent", "message", "series", "emphasis",
                      "annotations", "visual", "role", "notes"},
    "end":           {"type", "title", "color", "titleTier", "visual", "role",
                      "notes"},
}
# **条件必填**：这个版式的全部内容就是那个字段，缺了它这一页不成立。
#
# 字段集是"封闭"的（只查允许哪些键），不是"必填"的 —— 所以 `content-image`
# 不给 `image` 会一路放行到渲染器，然后 `KeyError: 'image'` 崩栈。实测撞到过。
# 与"图片该要就要，别为了省事少要"是同一条：这一页的版式已经说了要图，
# 就不该把它省掉。
# 布局：**自由字符串**（v3）。
# 渲染器认识的结构布局（能力，非枚举禁令）：content-image 的
# visual-right/visual-left/even/hero，two-column 的 even/lean-left/lean-right。
# 其它字符串 = 作者/风格自造的布局名 —— 渲染套缺省结构 + data-layout 钩子，
# 排法由 skin.css 写。validate 不封值集（"auto" 除外 —— 那是"让脚本替你选"，
# 而选布局是内容决策）。
# 拼写检查在 check.py：风格在 style.json 声明 `layouts` 词表时按词表验。
STRUCTURAL_LAYOUTS = ("visual-right", "visual-left", "even", "hero",
                      "lean-left", "lean-right")

REQUIRED_SLIDE_FIELDS = {
    "content-image": {"image"},
}

# 嵌套列表的元素字段（两栏 / 时间点 / 柱子）
ITEM_FIELDS = {
    "columns": {"title", "bullets"},
    "nodes":   {"label", "note"},
    "data":    {"label", "value"},
    # 散点要两个连续量：x/y（value 视同 y，向后兼容）
    "series":      {"name", "data"},
    "annotations": {"type", "target", "text", "value"},
}

# 刻意的空缺 —— 报错时给**专门**说明，而不是只说"未知字段"。这三个集合对应
# 本 skill 立论里明确不许模型碰的三类东西。
SIZE_FIELDS = {"fontSize", "font_size", "fontSizePx", "textSize", "size", "font"}
COORD_FIELDS = {"x", "y", "dx", "dy", "rot", "rotation", "offset", "left", "top",
                "width", "height", "w", "h"}
COLOR_FIELDS = {"primary", "secondary", "background", "ink", "inkText", "paper",
                "fg", "bg", "fill", "stroke"}

HINTS = {
    "fontSize": "字号档在风格的 type 块里（作者数据）；spec 只能选档名（titleTier/bulletTier），不写数字。",
    "font_size": "同上 —— 字号由脚本派生，不是写进来的。",
    "fontSizePx": "同上 —— 字号由脚本派生，不是写进来的。",
    "textSize": "同上 —— 字号由脚本派生，不是写进来的。",
    "size": "同上 —— 字号 / 尺寸由脚本派生。",
    "font": "字体族在 token.fonts 里，不在规格里。",
    "x": "坐标是刻意不存在的字段。一旦 schema 里有 x/y，模型就会开始填数字 —— 而版式计算正是交给脚本的那部分。",
    "variant": "字段名是 layout（自由字符串）。结构布局：content-image 的 "
               "visual-right/visual-left/even/hero；two-column 的 even/lean-left/"
               "lean-right；其它名字由 skin.css 排。",
    "mood": "不是字段 —— 配色方向直接写 colorSet 名字，没有语义推导这一步。",
    "titleTier": "标题档名（风格 type 块里的键）：风格 titleTiers 定缺省映射，"
                 "这里逐页覆盖。",
    "bulletTier": "条目档名；v3 无按条数自动升降档，缺省取风格 bulletDefault。",
    "y": "同上 —— 用 type 表达版式，不要给坐标。",
    "dx": "错位量由 (seed, 元素) 派生，规格里没有它。",
    "dy": "同上 —— 错位量由脚本派生。",
    "rot": "旋转角由 (seed, 元素) 派生，规格里没有它。",
    "rotation": "同上 —— 旋转角由脚本派生。",
    "width": "尺寸由版式决定，规格里没有它。",
    "height": "同上 —— 尺寸由版式决定。",
    "primary": "色值不在规格里：换色板请改 styles/swiss-grid/style.json 的 colorSets。",
    "secondary": "同上 —— 色值只在 token 里。",
    "background": "同上 —— 纸色只在 token 里。",
    "ink": "同上 —— 叠印墨是推导出来的，不是写进来的。",
    "inkText": "同上 —— 文字色 = overprint(primary, secondary)，由 ink.py 推导。",
}


class Issues:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def error(self, code: str, where: str, message: str) -> None:
        self.items.append({"level": "error", "code": code, "where": where, "message": message})

    def warn(self, code: str, where: str, message: str) -> None:
        self.items.append({"level": "warn", "code": code, "where": where, "message": message})

    @property
    def errors(self) -> list[dict]:
        return [i for i in self.items if i["level"] == "error"]


def _check_fields(obj: dict, allowed: set[str], where: str, issues: Issues) -> None:
    """未知键判错，并按字段类别给专门说明。"""
    for key in obj:
        if key in allowed:
            continue
        hint = HINTS.get(key)
        if key in SIZE_FIELDS:
            issues.error("SIZE_FIELD", f"{where}.{key}", hint or "规格里没有字号字段。")
        elif key in COORD_FIELDS:
            issues.error("COORD_FIELD", f"{where}.{key}", hint or "规格里没有坐标 / 尺寸字段。")
        elif key in COLOR_FIELDS:
            issues.error("COLOR_FIELD", f"{where}.{key}", hint or "规格里没有色值字段。")
        else:
            issues.error("UNKNOWN_FIELD", f"{where}.{key}",
                         f"未知字段 {key!r}；这里的允许集是 {sorted(allowed)}")


def _check_items(slide: dict, key: str, where: str, issues: Issues) -> None:
    """校验嵌套列表（columns / nodes / data / series / annotations）的元素字段。"""
    items = slide.get(key)
    if items is None:
        return
    if not isinstance(items, list):
        issues.error("BAD_ITEMS", f"{where}.{key}", f"{key} 必须是数组")
        return
    allowed = set(ITEM_FIELDS[key])
    # **限定豁免**：散点图的 x/y 是**数据**（两个连续量），不是版式坐标。
    # COORD_FIELDS 的禁令管的是"模型不许填版式坐标"；散点的 x/y 与 value 同类。
    # 只在 chart 页的 data 项上豁免 —— 禁令在其他所有地方原样有效。
    if (slide.get("type") == "chart" and key == "data"
            and (slide.get("chart") == "scatter" or slide.get("intent") == "correlation")):
        allowed |= {"x", "y"}
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            issues.error("BAD_ITEM", f"{where}.{key}[{i}]", "每一项都必须是对象")
            continue
        _check_fields(item, allowed, f"{where}.{key}[{i}]", issues)


def _ratio_ok(raw) -> bool:
    """`"3:2"` → True；非字符串 / 不是 W:H / 超出 RATIO_RANGE 都 False。"""
    if not isinstance(raw, str) or raw.count(":") != 1:
        return False
    a, b = raw.split(":")
    if not (a.isdigit() and b.isdigit()):
        return False
    w, h = int(a), int(b)
    if w <= 0 or h <= 0 or w > 64 or h > 64:
        return False
    lo, hi = RATIO_RANGE
    return lo <= (w / h) <= hi


def validate(spec: dict, color_sets: set[str] | None = None) -> Issues:
    issues = Issues()
    if not isinstance(spec, dict):
        issues.error("BAD_ROOT", "$", "顶层必须是对象")
        return issues
    _check_fields(spec, {"deck"}, "$", issues)

    deck = spec.get("deck")
    if not isinstance(deck, dict):
        issues.error("BAD_DECK", "deck", "缺少 deck 对象")
        return issues
    _check_fields(deck, DECK_FIELDS, "deck", issues)

    # 风格必填（工具链不内置任何风格 —— 见 references/style-architecture.md）
    if not deck.get("style"):
        issues.error("MISSING_STYLE", "deck.style",
                     "deck.style 必填 —— 工具链不内置任何风格，也没有可拷的"
                     "参考实现：在 deck 项目的 styles/<名>/ 里放 style.json + skin.css，"
                     "spec 写 \"style\": \"<名>\"（形状见 references/style-architecture.md）")

    # 配色必填具名（auto/mood 不是字段）
    if deck.get("colorSet") in (None, "auto"):
        issues.error("MISSING_COLOR_SET", "deck.colorSet",
                     "colorSet 必填具名 —— 配色由作者定：先看候选（门 ③），"
                     "选定后写名字；对比度由 ink.py 验收")

    if color_sets is not None:
        chosen = deck.get("colorSet")
        if isinstance(chosen, str) and chosen not in color_sets:
            issues.error("BAD_COLOR_SET", "deck.colorSet",
                         f"{chosen!r} 不在 token 的 colorSets 里，可用 "
                         f"{sorted(color_sets)}")

    slides = deck.get("slides")
    if not isinstance(slides, list) or not slides:
        issues.error("BAD_SLIDES", "deck.slides", "slides 必须是非空数组")
        return issues

    for i, slide in enumerate(slides):
        where = f"deck.slides[{i}]"
        if not isinstance(slide, dict):
            issues.error("BAD_SLIDE", where, "每一页都必须是对象")
            continue
        kind = slide.get("type")
        if kind not in SLIDE_FIELDS:
            issues.error("BAD_TYPE", f"{where}.type",
                         f"未知版式 {kind!r}；支持 {sorted(SLIDE_FIELDS)}")
            continue
        _check_fields(slide, SLIDE_FIELDS[kind], where, issues)
        # 视觉载体：声明什么载体，就得是能装下它的版式（自相矛盾当场拦）。
        visual = slide.get("visual")
        if visual is not None:
            vwhere = f"{where}.visual"
            if not isinstance(visual, dict):
                issues.error("BAD_VISUAL", vwhere,
                             f"visual 要是对象（{{\"kind\": ...}}），收到 {visual!r}；"
                             f"四种载体见 references/images.md")
            else:
                _check_fields(visual, VISUAL_KEYS, vwhere, issues)
                vkind = visual.get("kind")
                if vkind is None:
                    issues.error("BAD_VISUAL", vwhere, "visual 必须写 kind")
                elif vkind not in VISUAL_KINDS:
                    issues.error("BAD_VISUAL", vwhere,
                                 f"未知载体 {vkind!r}；支持 {list(VISUAL_KINDS)}")
                elif vkind in VISUAL_IMAGE_KINDS and kind != "content-image":
                    issues.error("BAD_VISUAL", vwhere,
                                 f"声明 visual.kind={vkind} 要用图，版式却是 {kind!r} —— "
                                 f"图没有槽位。改成 content-image（图占一栏）或去掉声明")
                elif vkind == "data" and kind != "chart":
                    issues.error("BAD_VISUAL", vwhere,
                                 f"声明 visual.kind=data 要用图表，版式却是 {kind!r} —— "
                                 f"改成 chart 版式（chart 字段写图形类型）")
                elif vkind == "none" and kind == "content-image":
                    issues.error("BAD_VISUAL", vwhere,
                                 f"content-image 版式声明 visual.kind=none —— "
                                 f"这一页的版式就是图：给 image，或换成 content-text")
                # 要图 → **必须写清比例**。出图工具的默认比例各家不同（Midjourney 默认
                # 1:1、SD 看 sampler、DALL·E 只认 prompt），不写下来就等于没定，
                # 出回来再改成本高得多；槽位高度也按它算。
                if vkind in VISUAL_IMAGE_KINDS:
                    ratio = visual.get("ratio")
                    if ratio is None:
                        issues.error("MISSING_RATIO", vwhere,
                                     "要图就得写清比例：visual.ratio（如 \"3:2\" / "
                                     "\"4:3\" / \"1:1\" / \"16:9\"）—— 出图工具的默认"
                                     "比例各家不同，不写下来等于没定；槽位高度按它算。"
                                     "不带 live 空位的图页（没有 visual 声明）不受这条约束")
                    elif not _ratio_ok(ratio):
                        issues.error("BAD_RATIO", vwhere,
                                     f"ratio 要写成 \"宽:高\"（整数，如 \"3:2\"），"
                                     f"收到 {ratio!r}")
        # 角色：封闭词表（拼错的角色名 = 静默失效，与 layout 同名一个性质）
        role = slide.get("role")
        if role is not None:
            if not isinstance(role, str) or not role:
                issues.error("BAD_ROLE", f"{where}.role",
                             f"role 要是非空字符串，得到 {role!r}")
            elif role not in ROLES:
                issues.error("BAD_ROLE", f"{where}.role",
                             f"未知角色 {role!r}；支持 {list(ROLES)} —— "
                             f"角色说这一页在干什么（配版式、看重复都靠它）")
        # 布局：自由字符串，只拦 "auto"（"让脚本替你选"）与非字符串
        layout = slide.get("layout")
        if layout is not None:
            if not isinstance(layout, str) or not layout:
                issues.error("BAD_LAYOUT", where,
                             f"layout 要是非空字符串，得到 {layout!r}")
            elif layout == "auto":
                issues.error("BAD_LAYOUT", where,
                             "layout 不支持 auto —— 选布局是内容决策，直接写"
                             "布局名；自造名由 skin.css 排（缺省结构 + "
                             "data-layout 钩子）")
        # 图形类型必填且封闭八类（没有任何推断路径）
        if kind == "chart":
            ctype = slide.get("chart")
            if not ctype:
                issues.error("MISSING_CHART_TYPE", where,
                             f"图表页必须写 chart —— 图形类型由作者声明"
                             f"（八类：{list(CHART_TYPES)}）；intent 仍是可选语义标注")
            elif ctype not in CHART_TYPES:
                issues.error("UNKNOWN_CHART_TYPE", f"{where}.chart",
                             f"未知图形 {ctype!r}；支持 {list(CHART_TYPES)}")
        for need in REQUIRED_SLIDE_FIELDS.get(kind, ()):
            if not slide.get(need):
                issues.error("MISSING_FIELD", f"{where}.{need}",
                             f"{kind} 版式必须有 {need!r} —— 这一页的全部内容就是它。"
                             f"缺了不是「少一张图」，是渲染器会直接崩；"
                             f"这一页不需要图就换成 content-text 版式")
        # color 只允许 "overprint"（主/副色载不住正文 —— 见 ink.py）
        declared = slide.get("color")
        if declared is not None and declared != "overprint":
            issues.error("BAD_COLOR", f"{where}.color",
                         f"只接受 \"overprint\"（两墨叠印色），收到 {declared!r} —— "
                         f"主/副色单独当文字色对比度天生不达标")
        for key in ITEM_FIELDS:
            if key in slide:
                _check_items(slide, key, where, issues)

    return issues


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="校验 deck-spec.json 规格（字段集封闭）")
    ap.add_argument("spec", help="规格文件路径")
    ap.add_argument("--tokens", default=None,
                    help="覆盖 token 文件（缺省按 deck.style 解析：deck 项目 styles/ 优先，--style 也吃路径）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    try:
        with open(args.spec, encoding="utf-8") as fh:
            spec = json.load(fh)
    except OSError as exc:
        print(f"读不到规格文件：{exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"不是合法 JSON：{exc}", file=sys.stderr)
        return 2

    # token 读不到**不算** spec 的错（可能只是没带对路径）—— 那就跳过 colorSet 存在性校验，
    # 而不是把一件读不到的事报成"规格有问题"。
    # 风格从 spec 的 deck.style 解析（必填，无内置风格）：色板名单必须
    # 按**这一份 deck 选的风格**去查，拿别的风格的名单去核会误报。
    tokens_path = args.tokens
    if tokens_path is None:
        deck = spec.get("deck") if isinstance(spec, dict) else None
        style_name = deck.get("style") if isinstance(deck, dict) else None
        if isinstance(style_name, str) and style_name:
            tokens_path = os.path.join(STYLES_DIR, style_name, "style.json")
    color_sets: set[str] | None = None
    if tokens_path is None:
        # 没声明风格（或声明了但找不到 token 文件）—— 不在这里报错：
        # MISSING_STYLE / 风格缺失由 validate() 与 check.py 各自负责，
        # 这里只把"查不了色板名单"的降级写在脸上（跳过名单存在性校验）。
        issues = validate(spec, None)
    else:
        try:
            with open(tokens_path, encoding="utf-8") as fh:
                color_sets = set(json.load(fh)["colorSets"])
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            color_sets = None
        issues = validate(spec, color_sets)

    if args.json:
        print(json.dumps({"spec": args.spec, "error_count": len(issues.errors),
                          "issues": issues.items}, ensure_ascii=False, indent=2))
        return 1 if issues.errors else 0

    if not issues.items:
        print("✓ 规格通过（字段集封闭、版式与 colorSet 都认得）")
        return 0

    for it in issues.items:
        mark = "✗" if it["level"] == "error" else "·"
        print(f"  {mark} [{it['code']}] {it['where']}")
        print(f"      {it['message']}")

    print(f"\n{len(issues.errors)} 个 error，{len(issues.items) - len(issues.errors)} 个 warn")
    return 1 if issues.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
