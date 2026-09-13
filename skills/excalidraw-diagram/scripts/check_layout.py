#!/usr/bin/env python3
"""十项校验 + 自动调参循环 + 报告生成。

## 为什么校验和调参在同一个文件里

调参循环**完全由校验结果驱动** —— "哪项失败动哪个参数"是一张表的两半。
拆成两个文件，那张表就会裂开：改了一边的阈值，另一边未必跟着改。
所以 `validation.md` 也是把这两件事写在同一节里的。

## 前作栽在哪（本模块存在的全部理由）

前作 `draw-excalidraw` 的 `lint.mjs` **只有 1474 字节**。要的四项校验里**只有"重叠"一项存在**
（阈值 4px、只 warn）。连线长度 / 文字溢出 / 色板越界三项完全不存在。
而且全部结果是 `warn` / `info` —— **没有一条能挡住输出**。报了什么也不影响结果。

## 关于 #1 和 #3：它们是"后置断言"，不是"内容体检"

坐标是从间距参数算出来的（`layout.py` 的 `assign_coordinates`），字号与容器宽度是同一份
`text_metrics` 量出来的。所以：

- **#1 元素间隙**：同层节点恰好相距一个节点间距，跨层恰好相距一个层间距 ——
  在今天的坐标推导下**构造上不可能失败**。
- **#3 文字溢出**：容器宽度由断行宽度反推 —— 同样构造上不可能失败。

它们一旦报，报的是**脚本内部不一致**（推导与实际落笔不符），不是你的内容有问题。
留着的意义是：以后加了分组折叠、或换掉坐标推导方式时，这两条会立刻变成真实的门。
**别把"它从来不报"当成"它没用"** —— 但也不要因为它在就以为间隙真的被量过了。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import sys
from dataclasses import dataclass, field
from typing import Any


def _load_sibling(name: str):
    """动态加载同目录脚本（`scripts/` 不是包，同级 import 在静态层面无法解析）。

    沿用 `validate_spec.py` 里那一个的写法与理由：必须把模块注册进 sys.modules
    之后再 exec，否则被加载模块里的 `@dataclass` 会炸 —— dataclasses._is_type 会查
    sys.modules.get(cls.__module__) 并拿到 None，报 "'NoneType' object has no
    attribute '__dict__'"。
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{name}.py")
    mod_spec = importlib.util.spec_from_file_location(f"_diagram_{name}", path)
    if mod_spec is None or mod_spec.loader is None:
        raise RuntimeError(f"加载不了同目录模块：{path}")
    module = importlib.util.module_from_spec(mod_spec)
    sys.modules[mod_spec.name] = module
    mod_spec.loader.exec_module(module)
    return module


L = _load_sibling("layout")
palette = _load_sibling("palette")
tm = _load_sibling("text_metrics")

# 同目录模块是运行期动态加载的（理由见 `_load_sibling`），静态层面拿不到它们的类型。
# 所以跨模块的参数标成 Any，并在各自 docstring 里写真实类型 —— 不写假类型，
# 也不为了过检查而把注解注掉。
BoxT = Any          # layout.Box
PlacedT = Any       # layout.Placed
ResultT = Any       # layout.LayoutResult

# ── 阈值。全部写死在脚本里，不进规格（规格里没有旋钮，见 diagram-spec.md）──
# 【待验证】这几个阈值是“依据前作数值与常识设的起点”，不是实测出来的 ——
# 它们等的是 validation.md 里那张校准表（用够 5 张图做一次复盘）。
# 信任状态总表见 references/diagram-spec.md（“数值的信任状态”一节）。
GAP_MIN = 12.0            # #1 相邻元素最小间隙（前作容忍 4px **重叠**，本版检查间隙）
# #2 连线最短可见长度。数值来自 layout.py（那边是唯一定义）—— 两边各写一个数
# 迟早会漂，而漂的时候“生成”和“检查”会对同一张图给出相反结论。
EDGE_MIN = L.EDGE_MIN
CROSSING_RATIO = 0.5      # #5 交叉数软阈值 = 边数 × 0.5
MAX_TUNE_ROUNDS = 4       # 调参轮数上限
TOLERANCE = 0.5           # 浮点比较容差（#3 断言用）

# 命中这几类就别调参了 —— 改参数没用，那是脚本 bug 或内容错误
STOP_ON = frozenset({"text", "palette", "region_label"})
# 可以靠调参解决的项。注意 #5（交叉数）是**软**项 —— 它不阻塞输出，但仍然是可调的。
# 只看“阻不阻塞”会让它永远调不动，而 validation.md 明写着它可自动修。
TUNABLE = frozenset({"gap", "edge", "crossing", "through", "overlap", "slant"})
# `_step` 真的会为它动参数的检查项。
#
# 这个集合与 `_step` 的映射表**必须一致**，由 tests/test_check_layout.py 里的
# 一条用例钉住：放进 TUNABLE 却调不动 = 调参循环对它形同虚设。
# 这个坑踩过两次（`crossing` 一次、`through` 又一次），所以改成机械检查。
STEPPABLE = frozenset({"gap", "edge", "crossing", "through", "overlap", "slant"})

CHECK_LABEL = {
    "gap": "元素间隙",
    "edge": "连线长度",
    "text": "文字溢出",
    "palette": "颜色越界",
    "crossing": "边交叉数",
    # 加这条检查的时候漏了这张表 —— 结果**报告里一出现"穿节点"就崩**（KeyError）。
    # 平时看不见，因为报告只在有问题时打印。现在由用例钉住两张表一致
    # （TestEveryCheckHasALabel），加检查时忘不了。
    "through": "连线穿节点",
    "region": "区域重叠",
    # 加这两项的时候两张表都得跟着加 —— 由 TestEveryCheckHasALabel 钉住，
    # 而报告里漏了标签就会 KeyError（建表时就踩过一次）。
    "overlap": "连线重合",
    "slant": "连线斜段",
    "region_label": "区域标题溢出",
}
# 报告里用的中文说法。**参数名不许出现在报告里** —— 一旦报告写"建议调大某某"，
# 参数选择权就又回到模型手上了（validation.md 第二节）。
PARAM_SPOKEN = {
    "nodeSeparation": "节点间距",
    "rankSeparation": "层间距",
    "barycenterRounds": "排序轮数",
}


@dataclass(frozen=True)
class Issue:
    check: str
    blocking: bool
    where: str
    detail: str
    # 能动的只有内容的建议。**None = 这不是内容问题**，比如文字溢出属于脚本内部不一致。
    # 把建议随 issue 一起带上，而不是事后从 `check` 反推 —— 反推一定会漏掉
    # “同一类 check 里有两种性质不同的失败”这种情况（文字溢出就是）。
    advice: str | None = None

    def line(self) -> str:
        mark = "✗" if self.blocking else "·"
        return f"{mark} {CHECK_LABEL[self.check]}：{self.where} —— {self.detail}"


@dataclass
class Outcome:
    issues: list[Issue] = field(default_factory=list)

    @property
    def blocking(self) -> list[Issue]:
        return [i for i in self.issues if i.blocking]

    @property
    def soft(self) -> list[Issue]:
        return [i for i in self.issues if not i.blocking]

    def checks_hit(self) -> set[str]:
        return {i.check for i in self.blocking}

    def tunable_hits(self) -> set[str]:
        """能通过调参改善的项（阻塞的 + 交叉那条软的）。"""
        return {i.check for i in self.issues if i.check in TUNABLE}

    def converged(self) -> bool:
        """没有阻塞项，也没有**调得动**的可调项 → 可以出图了。

        这里曾经是硬编码的 `and "crossing" not in self.tunable_hits()` ——
        于是每新加一个可调项都要记得回来改这一行，而“记得”正是这个项目
        反复证明不可靠的东西（加 `through` 时就又踩了一次：它一出现就直接
        出报告，调参循环对它等于不存在）。

        现在改成问“有没有 STEPPABLE 里的项”，而 STEPPABLE 与 `_step` 的映射表
        由一条用例钉住一致 —— 关系机械化，不靠记性。
        """
        return not self.blocking and not (self.tunable_hits() & STEPPABLE)


@dataclass
class Attempt:
    round_no: int
    params: dict[str, float]
    outcome: Outcome


# ── #1 元素间隙 ─────────────────────────────────────────────
def _aabb_gap(a: PlacedT, b: PlacedT) -> float:
    """两个包围盒之间的最短距离。重叠时返回 0。

    用**间隙**而不是前作那种"容忍 4px 重叠"：两个框相距 2px 在视觉上就已经糊在一起，
    而重叠检测不会报。

    实现只有一份，在 `layout.aabb_gap` —— 径向布局的半径外推也要量同一个间隙。
    两处各写一份的话就是第二个漂移点：径向按 A 松开、校验按 B 报错，会来回打架。
    """
    return L.aabb_gap(a, b)


def check_gaps(result: ResultT) -> list[Issue]:
    real = sorted(result.real_nodes().items())     # 虚节点尺寸为 0，不是视觉元素
    out: list[Issue] = []
    for i in range(len(real)):
        for j in range(i + 1, len(real)):
            (ia, a), (ib, b) = real[i], real[j]
            gap = _aabb_gap(a, b)
            if gap < GAP_MIN:
                out.append(Issue("gap", True, f"{ia} ↔ {ib}",
                                 f"间隙 {gap:.0f}px，下限 {GAP_MIN:.0f}px",
                                 advice="元素挨得过近：拆节点，或把相关节点归入同一主题分开画。"))
    return out


# ── #2 连线长度 ─────────────────────────────────────────────
def check_edge_lengths(result: ResultT) -> list[Issue]:
    out: list[Issue] = []
    for e in result.edges:
        pts = e["points"]
        seg = [math.dist(pts[k], pts[k + 1]) for k in range(len(pts) - 1)]
        if not seg:
            continue
        shortest = min(seg)
        if shortest < EDGE_MIN:
            out.append(Issue("edge", True, f"{e['from']} → {e['to']}",
                             f"最短一段 {shortest:.0f}px，下限 {EDGE_MIN:.0f}px",
                             advice="连线过短：拆节点或减少层级。"))
    return out


# ── #3 文字溢出（一致性断言，不是内容问题）──────────────────
def check_text_fit(spec: dict, result: ResultT,
                   boxes: dict[str, BoxT]) -> list[Issue]:
    """重新量一遍文字，和落笔时用的尺寸比对。

    按 `diagram-spec.md` 定的耦合方向（容器宽度由断行宽度反推），文字在构造上不可能溢出。
    所以这条报出来只有一个意思：**测量与落笔之间有不一致** —— 脚本 bug，不是内容问题。
    报告必须这么说，否则模型会去干"缩短标签"这件没用的事。
    """
    out: list[Issue] = []
    for node in spec.get("nodes", []):
        nid = node["id"]
        if nid not in boxes:
            continue
        # 盒子现在是 NodeBox：形状包围盒 + 里面的文字。断言比的是**文字那一半** ——
        # 形状多出来的余量是从文字算出来的，拿包围盒去比文字尺寸会必然不等。
        # 比文字本身反而更强：形状算错了会从 layout.boxes_from_spec 那条路被发现。
        used = getattr(boxes[nid], "text", boxes[nid])
        # **用盒子自己的字号重新量。** 强调档会让字号大一步（§14），按默认字号量
        # 出来的尺寸当然对不上 —— 那会把它误报成「文字溢出」，而其实落笔是对的。
        # 这里仍然卡"恰好相等"，没有放宽：字号不一致照样会被抓住。
        fresh = tm.measure(node.get("label", ""), node.get("detail", ""),
                           font_size=getattr(used, "font_size", tm.FONT_NODE))
        if abs(fresh.width - used.width) > TOLERANCE or abs(fresh.height - used.height) > TOLERANCE:
            out.append(Issue("text", True, nid,
                             f"落笔尺寸 {used.width:.0f}×{used.height:.0f}，"
                             f"重新量得 {fresh.width:.0f}×{fresh.height:.0f}。"
                             f"这是生成脚本的内部不一致（测量与落笔不符），不是你内容的问题。"))
        elif tm.too_long_for_largest(node.get("label", "")):
            # 真正的"内容"问题只有这一种：标签长到最大档也放不下，只能换写法。
            out.append(Issue("text", True, nid, "标签超过了最大断行档位，无法成图",
                             advice="标签太长：换更短的说法，或把内容拆成两个节点。"))
    return out


# ── #4 kind / 颜色越界 ──────────────────────────────────────
def _palette_colors() -> set[str]:
    """“在板内”的完整取值集合。

    强调层级的派生色**也从色板算出来**（`palette.fill_for` / `stroke_for`），
    不是手写第二张表 —— 手写就会漂移，而漂移了这张校验就变成假的。
    """
    colors: set[str] = set()
    for entry in list(palette.LEVELS.values()) + list(palette.EDGE_KINDS.values()):
        colors.update(v for k, v in entry.items() if k in ("stroke", "background"))
    colors.update(v for k, v in palette.CANVAS.items() if k in ("background", "grid", "text"))
    for kind in palette.KINDS:
        for emphasis in palette.EMPHASIS:
            colors.add(palette.fill_for(kind, emphasis))
            colors.add(palette.stroke_for(kind, emphasis))
    return colors


def check_palette(spec: dict) -> list[Issue]:
    """未知 kind 或颜色不在板内 —— 规格写错了，调参数没用。

    注意：这条**不 fallback**。`palette.stroke_for` 对未知 kind 抛 KeyError（设计如此），
    所以这里接住它并转成 issue，而不是给个默认色放过去 —— 静默 fallback 会让
    "颜色必须在板内"这条校验自己绕过自己。
    """
    allowed = _palette_colors()
    out: list[Issue] = []
    for node in spec.get("nodes", []):
        kind = node.get("kind")
        emphasis = node.get("emphasis", palette.DEFAULT_EMPHASIS)
        # 两种病因分开判、分开报。混成一句会让修的人照着一个错的提示越修越偏
        # （实测踩过：kind 写错时报出的是“未知 shape: None”）。
        # 两条都是**硬判**，不 fallback —— fallback 会让“颜色必须在板内”这条校验绕过自己。
        if kind not in palette.KINDS:
            out.append(Issue("palette", True, node["id"],
                             f"未知 kind：{kind!r}；允许值 {sorted(palette.KINDS)}",
                             advice="有 kind 不在允许集合里：改用上面列出的允许值。"))
            continue
        if emphasis not in palette.EMPHASIS:
            out.append(Issue("palette", True, node["id"],
                             f"未知 emphasis：{emphasis!r}；"
                             f"允许值 {sorted(palette.EMPHASIS)}",
                             advice="有强调档位不在允许集合里：改用上面列出的允许值。"))
            continue
        stroke = palette.stroke_for(kind, emphasis)
        background = palette.fill_for(kind, emphasis)
        for got, what in ((stroke, "描边"), (background, "填充")):
            if got not in allowed:
                out.append(Issue("palette", True, node["id"],
                                 f"{what}色 {got} 不在板内",
                                 advice="有颜色不在色板里：改用色板允许的取值。"))
    for e in spec.get("edges") or []:
        kind = e.get("kind")
        if kind is None:
            continue
        try:
            # 注意 `edge_style_for()` 返回的是**线型**（"solid"/"dashed"），不是整份样式。
            # 要颜色得直接读 EDGE_KINDS。
            got = palette.EDGE_KINDS[kind]["stroke"]
        except KeyError:
            out.append(Issue("palette", True, f"{e['from']} → {e['to']}",
                             f"未知边型：{kind!r}；允许值 {sorted(palette.EDGE_KINDS)}",
                             advice="有边型不在允许集合里：改用上面列出的允许值。"))
            continue
        if got not in allowed:
            out.append(Issue("palette", True, f"{e['from']} → {e['to']}",
                             f"线色 {got} 不在板内",
                             advice="有颜色不在色板里：改用色板允许的取值。"))
    return out


# ── #5 边交叉数（软阈值）────────────────────────────────────
def check_crossings(spec: dict, result: ResultT) -> list[Issue]:
    """超过 边数 × 0.5 就报。

    软阈值而不是硬门：**零交叉不是总能达到**。把它当硬门会导致"为了过门把节点排成
    不可读的形状"或者干脆卡死。它的真正作用是仪表盘 —— 前作没有这个指标，
    所以层内排序质量差只能靠人眼发现（"这几根线绕得很奇怪"）。

    报告必须给出**交叉的是哪几条边**：只有计数的话，人没法定位问题。
    这就是 `layout.crossing_pairs` 与 `count_crossings` 共用一份实现的原因。
    """
    edges = spec.get("edges") or []
    limit = len(edges) * CROSSING_RATIO
    if result.crossings <= limit:
        return []
    pairs = []
    for a, b in result.crossing_origins:
        ea = edges[a] if 0 <= a < len(edges) else None
        eb = edges[b] if 0 <= b < len(edges) else None
        if ea and eb:
            pairs.append(f"{ea['from']}→{ea['to']} ✕ {eb['from']}→{eb['to']}")
    detail = f"{result.crossings} 处，软阈值 {limit:.1f}（边数 {len(edges)} × {CROSSING_RATIO}）"
    return [Issue("crossing", False, "；".join(pairs) or "（无法归因）", detail,
                  advice="连线交叉偏多：考虑拆节点、减少 detail、或调换两个节点的先后位置。")]


# ── 汇总 ────────────────────────────────────────────────────
def check_edges_through_nodes(spec: dict, result: ResultT) -> list[Issue]:
    """连线穿过**别的**节点。

    为什么要单独一条：“看起来有线压在框上”这件事，当时五条校验里**没有一条在管**，
    只能靠人看图发现。而它是纯几何判断（线段与矩形相交），完全可以机械检。

    定为**可调项**而不是硬门：布局已经会自己试着绕行（`layout.avoid_nodes`），
    绕不过去说明图本身密 —— 这时候应该多给点间距重跑，而不是卡死不出图。
    报告给的是**内容级建议**，不是“再推一推”。
    """
    out: list[Issue] = []
    for edge in result.edges:
        exclude = {edge["from"], edge["to"]}
        hit = L.nodes_hit_by_polyline(edge["points"], result.placed, exclude)
        if hit:
            out.append(Issue(
                "through", False, f"{edge['from']}→{edge['to']}",
                f"这条连线穿过了 {len(hit)} 个别的节点（{', '.join(hit)}）",
                advice="连线穿过节点：把中间那个节点换个层或换个位置，或把这条边拆成两段。"))
    return out


# ── #8 / #9 连线形状（可调项）────────────────────────────
# 两项紧挨着放：一个管“两根线画成一根”，一个管“画歪了”。
# 编号按加进表的顺序，区域（#7）的定义在下面。
#
# #8 连线重合：共线重合约 1px 就报 —— 图上那就是“一根线”，看不出是两根。
# 数值来自 layout.py（那边是唯一定义，车道分配避开重合用的也是它）——
# 两边各写一个数迟早会漂，而漂的时候生成与检查会对同一张图给出相反结论。
EDGE_OVERLAP_MIN = L.EDGE_OVERLAP_MIN


def check_edge_overlap(result: ResultT) -> list[Issue]:
    """两根连线画在**同一条线上**（共线 + 区间重叠）—— 可调项。

    为什么它必须存在：这一项以前**根本不在检查表里**，于是“报告全绿”与
    “看着是一根线”可以同时成立 —— 实测 7 张自带图里有 5 张存在重合
    （01-architecture 里 `order→user` 与 `order→cache` 在 x=966 上重合 225px）。
    生成侧现在有 `layout._spread_lanes` 主动错开车道，但那是**尽力而为**
    （挪进节点就回退），所以还需要这一项把剩下的如实报出来。

    为什么是可调项而不是硬门：空档太窄时确实可能分不开 —— 那是空间不够，
    不是内容错了。调参循环会先去试更宽的间距（见 `_step`）。

    只查**横平竖直**的段：分层图的连线全部是这样，而这个病就活在那里。
    径向 / 力导向的斜线是两节点之间的辐条，两条辐条重合意味着两个节点在同一个
    方向上 —— 那已经被「元素间隙」管住了，不在这里重复一套几何判据。
    """
    segs: list[tuple[int, float, float, float, str]] = []
    for edge in result.edges:
        pts = edge["points"]
        name = f"{edge['from']}→{edge['to']}"
        for a, b in zip(pts, pts[1:]):
            if abs(a[0] - b[0]) <= 0.5:
                segs.append((0, a[0], min(a[1], b[1]), max(a[1], b[1]), name))
            elif abs(a[1] - b[1]) <= 0.5:
                segs.append((1, a[1], min(a[0], b[0]), max(a[0], b[0]), name))
    out: list[Issue] = []
    reported: set[tuple[str, str]] = set()
    for i in range(len(segs)):
        for j in range(i + 1, len(segs)):
            first, second = segs[i], segs[j]
            if first[0] != second[0] or first[4] == second[4]:
                continue
            if abs(first[1] - second[1]) > 0.75:
                continue                        # 不在同一条线上
            overlap = min(first[3], second[3]) - max(first[2], second[2])
            if overlap <= EDGE_OVERLAP_MIN:
                continue
            key = ((first[4], second[4]) if first[4] < second[4]
                   else (second[4], first[4]))
            if key in reported:
                continue                        # 一对边只报一次
            reported.add(key)
            out.append(Issue(
                "overlap", False, f"{key[0]} 与 {key[1]}",
                f"两根线在同一条线上重合约 {overlap:.0f}px，看上去是一根线",
                advice="连线重合：把其中一条的目标节点换个层或换个位置，或减少同一对节点之间的重复连线。"))
    return out


# ── #9 连线斜段（可调项）──────────────────────────────────
def check_edge_slant(result: ResultT) -> list[Issue]:
    """连线上出现了**斜段**（既不水平也不竖直）—— 可调项。

    用户对这件事的原话是「就是那种 90 度拐弯的线不行吗」。分层图里每一条边
    都有正交候选（`layout._orthogonal_path`），只有当**全部候选都不可用**时
    才会退回到两点直弦 —— 所以一条斜段出现，就意味着“这一段路真的过不去”，
    应当在报告里说清楚，而不是让它悄悄地出图。

    为什么从前没报：斜段以前**不在检查表里** —— 生成侧把一条 1475px 的斜线当作“避开
    3px 毛刺”的选择，而校验对两者都无话可说。现在两边都管上了。

    只查**分层图**（LR / TB）：径向与力导向的连线**就该是**两点直辐条，
    那是它们的画法，不是缺陷。
    """
    if str(getattr(result, "direction", "")) not in ("LR", "TB"):
        return []
    out: list[Issue] = []
    for edge in result.edges:
        pts = edge["points"]
        for a, b in zip(pts, pts[1:]):
            if abs(b[0] - a[0]) > 0.5 and abs(b[1] - a[1]) > 0.5:
                out.append(Issue(
                    "slant", False, f"{edge['from']}→{edge['to']}",
                    "这条连线里有一段是斜的",
                    advice="斜段是“正交路线全都走不通”的兜底：把跨层的边拆成两段、"
                           "减少层级，或换一个方向重画。"))
                break
    return out


# ── #10 区域标题（后置断言 + 一条内容级上限）─────────────
def check_region_labels(spec: dict, result: ResultT,
                        boxes: dict[str, BoxT]) -> list[Issue]:
    """区域标题必须装在标题带里。

    **两条性质不同的失败共用一个 check**（`Issue` 的 docstring 里就写了这种情况）：
      - 断行与尺寸对不上 / 标题比区域宽 / 标题块压到成员 → **脚本内部不一致**，
        不给内容建议（否则模型会去干“缩短标签”这件没用的事）
      - 标题被断成太多行 → **内容问题**，建议缩短标题或拆区域

    为什么加这一条：这个溢出**真实发生过**。用户拿截图来问“这种块的 title 会溢出”，
    而当时九项校验里**没有一项在量区域标题** —— 标题宽度压根没进过任何尺寸链，
    报告全绿而图上两头各冒出去 22px。

    现在尺寸链是“区域宽度（由成员定）→ 断行 → 行数 → 标题带高度”，
    所以前一类构造上不该失败 —— 它一旦报就是脚本 bug。留着的意义：
    下次改断行或改标题带时，它会立刻变成真实的门（和 #1 / #3 那两条后置断言同理）。
    """
    out: list[Issue] = []
    for region in L.region_boxes(spec, result.placed, boxes):
        lines = list(region.get("label_lines") or ())
        if not lines:
            continue
        expect, expect_width = L.region_label_lines(region["label"], region["width"])
        if list(expect) != lines or abs(expect_width - region["label_width"]) > TOLERANCE:
            out.append(Issue(
                "region_label", True, region["id"],
                "标题断行与区域尺寸对不上。这是生成脚本的内部不一致"
                "（测量与落笔不符），不是你内容的问题。"))
            continue
        inner = region["width"] - 2 * L.REGION_LABEL_MARGIN
        if region["label_width"] > inner + TOLERANCE:
            out.append(Issue(
                "region_label", True, region["id"],
                f"标题宽 {region['label_width']:.0f}px，而区域只有 {inner:.0f}px 可用 —— "
                f"这是生成脚本的内部不一致，不是你内容的问题。"))
            continue
        members = [result.placed[nid] for nid in region.get("members", ())
                   if nid in result.placed]
        if members and region["label_y"] + region["label_height"] > \
                min(node.y for node in members) - L.REGION_PAD + TOLERANCE:
            out.append(Issue(
                "region_label", True, region["id"],
                "标题块压到了成员节点上 —— 这是生成脚本的内部不一致。"))
            continue
        if len(lines) > L.REGION_TITLE_MAX_LINES:
            out.append(Issue(
                "region_label", True, region["id"],
                f"区域标题被断成 {len(lines)} 行"
                f"（超过 {L.REGION_TITLE_MAX_LINES} 行，标题带要占 "
                f"{region['label_height'] + L.REGION_LABEL_TOP + L.REGION_LABEL_GAP:.0f}px 高）",
                advice="区域标题太长：换更短的说法，或把这一区拆成两块。"))
    return out


# ── #7 区域 ────────────────────────────────────────────────
def check_regions(spec: dict, result: ResultT, boxes: dict[str, BoxT]) -> list[Issue]:
    """区域之间**要么分开、要么一个完全包住另一个** —— 不许部分重叠。

    实测踩过：一个 group 的节点在空间上被另一个 group 的节点夹在中间时，两个区域框
    会叠成一块 —— 图上看不出"谁包着谁"，区域就不再表达任何东西了。

    为什么判失败而不是自动缩框：缩框要么盖住自己的成员、要么把自己的成员排除在外，
    两种都是在**骗**。正解是改分组或改布局，那得让作者知道。

    为什么允许完全包含：分区里面再圈一块（"这一段属于异常路径"）是正当用法。
    """
    regions = L.region_boxes(spec, result.placed, boxes)
    out: list[Issue] = []
    for i in range(len(regions)):
        for j in range(i + 1, len(regions)):
            a, b = regions[i], regions[j]
            overlap_x = (min(a["x"] + a["width"], b["x"] + b["width"])
                         - max(a["x"], b["x"]))
            overlap_y = (min(a["y"] + a["height"], b["y"] + b["height"])
                         - max(a["y"], b["y"]))
            if overlap_x <= 0 or overlap_y <= 0:
                continue
            inside = ((a["x"] >= b["x"] and a["y"] >= b["y"]
                       and a["x"] + a["width"] <= b["x"] + b["width"]
                       and a["y"] + a["height"] <= b["y"] + b["height"])
                      or (b["x"] >= a["x"] and b["y"] >= a["y"]
                          and b["x"] + b["width"] <= a["x"] + a["width"]
                          and b["y"] + b["height"] <= a["y"] + a["height"]))
            if inside:
                continue
            out.append(Issue(
                "region", True, f"{a['id']} ↔ {b['id']}",
                f"两个区域部分重叠 {overlap_x:.0f}×{overlap_y:.0f}px",
                advice="区域要么分开、要么一个完全包住另一个。把其中一组的节点挪到一起，"
                       "或者把这几个节点重新归组 —— 不要靠缩框，缩完就盖住成员了。"))

    # 框里**夹着非成员节点** —— 这比重叠更严重：图上看那个节点"属于这一区"，
    # 是**语义错误**，不是排版问题。部分压线也算（边框从它身上切过去）。
    real = result.real_nodes()
    for region in regions:
        members = set(region.get("members", ()))
        for nid, node in real.items():
            if nid in members:
                continue
            if (node.x < region["x"] + region["width"] and node.x + node.width > region["x"]
                    and node.y < region["y"] + region["height"]
                    and node.y + node.height > region["y"]):
                out.append(Issue(
                    "region", True, f"{region['id']} ⊃ {nid}",
                    f"区域 {region['id']!r} 的框里夹着非成员节点 {nid!r}",
                    advice="它在图上看起来属于这一区。要么把它也写进这个 group，"
                           "要么把这一区拆成两块 —— 框不能靠缩，缩了就会盖住自己的成员。"))
    return out


def check(spec: dict, result: ResultT,
          boxes: dict[str, BoxT]) -> Outcome:
    return Outcome(issues=[
        *check_gaps(result),
        *check_edge_lengths(result),
        *check_text_fit(spec, result, boxes),
        *check_palette(spec),
        *check_crossings(spec, result),
        *check_edges_through_nodes(spec, result),
        *check_edge_overlap(result),
        *check_edge_slant(result),
        *check_regions(spec, result, boxes),
        *check_region_labels(spec, result, boxes),
    ])


# ── 自动调参 ────────────────────────────────────────────────
def _step(params: dict[str, float], outcome: Outcome) -> dict[str, float]:
    """按固定步长递增。**这是查表，不是判断** —— 见 validation.md 第二节。"""
    out = dict(params)
    hit = outcome.tunable_hits()
    if "gap" in hit:
        out["nodeSeparation"] = min(params["nodeSeparation"] + L.PARAM_STEP["nodeSeparation"],
                                    L.PARAM_LIMIT["nodeSeparation"])
    if "edge" in hit:
        out["rankSeparation"] = min(params["rankSeparation"] + L.PARAM_STEP["rankSeparation"],
                                    L.PARAM_LIMIT["rankSeparation"])
    if "crossing" in hit:
        out["barycenterRounds"] = min(params["barycenterRounds"] + L.PARAM_STEP["barycenterRounds"],
                                      L.PARAM_LIMIT["barycenterRounds"])
    if "through" in hit:
        # 连线穿过节点时先给更多间距 —— 空间富余了绕行才推得开。
        # 两个方向一起加：穿节点往往横竖都有，分不清该加哪一边。
        out["nodeSeparation"] = min(params["nodeSeparation"] + L.PARAM_STEP["nodeSeparation"],
                                    L.PARAM_LIMIT["nodeSeparation"])
        out["rankSeparation"] = min(params["rankSeparation"] + L.PARAM_STEP["rankSeparation"],
                                    L.PARAM_LIMIT["rankSeparation"])
    if "overlap" in hit or "slant" in hit:
        # 重合与斜段都是**空间不够**的表现：空档宽了，车道才分得开
        # （`_spread_lanes` 的步长上限就是空档宽度）；正交候选也才有地方落脚。
        # 和穿节点同一套加法，理由相同 —— 分不清该加横还是竖，就一起加。
        out["nodeSeparation"] = min(params["nodeSeparation"] + L.PARAM_STEP["nodeSeparation"],
                                    L.PARAM_LIMIT["nodeSeparation"])
        out["rankSeparation"] = min(params["rankSeparation"] + L.PARAM_STEP["rankSeparation"],
                                    L.PARAM_LIMIT["rankSeparation"])
    return out


def _extremeness(result: Any) -> float:
    """图的长宽比有多极端：1.0 = 正方，越大越细长。"""
    placed = list(result.placed.values())
    if not placed:
        return 1.0
    width = max(p.x + p.width for p in placed) - min(p.x for p in placed)
    height = max(p.y + p.height for p in placed) - min(p.y for p in placed)
    if width <= 0 or height <= 0:
        return 1.0
    ratio = width / height
    return max(ratio, 1.0 / ratio)


def layout_with_retry(spec: dict, boxes: dict[str, BoxT],
                      params: dict[str, float] | None = None
                      ) -> tuple[Any, Outcome, list[Attempt]]:
    """算 → 校验 → 失败就调参重跑，最多 MAX_TUNE_ROUNDS 轮。

    调参**由脚本自己做，中间不经过模型**。让模型读报告再判断"我该把间距调到多少"，
    和前作的病根是同一件事 —— 只是把"模型猜坐标"换成"模型猜间距"，
    换了个变量名，风险小很多但没有归零。
    """
    current = dict(L.DEFAULT_PARAMS)
    current.update(params or {})
    attempts: list[Attempt] = []
    result = L.layout(spec, boxes, current)
    outcome = check(spec, result, boxes)

    for round_no in range(MAX_TUNE_ROUNDS + 1):
        attempts.append(Attempt(round_no=round_no, params=dict(current), outcome=outcome))
        if outcome.converged():
            break
        if any(i.check in STOP_ON for i in outcome.blocking):
            break                       # 改参数没用，别浪费轮次
        stepped = _step(current, outcome)
        if stepped == current:
            break                       # 已到上限；再跑只会得到同一个结果
        candidate = L.layout(spec, boxes, stepped)
        candidate_outcome = check(spec, candidate, boxes)
        # 护栏：调参器只盯它自己那几项检查，对**长宽比完全无感**。实测它会为了修
        # 折段带出来的 2 处穿节点，把层间距从 120 一路顶到 270 —— 图又变回细长条，
        # 折段刚省下来的高度全被吃回去。所以明确规定：**让图变得更极端的一步不采纳**。
        if _extremeness(candidate) > _extremeness(result):
            break
        current, result, outcome = stepped, candidate, candidate_outcome

    return result, outcome, attempts


# ── 报告 ────────────────────────────────────────────────────
def _assert_no_param_names(text: str) -> None:
    """报告里不许出现参数名。写成断言，而不是靠下次记得 ——
    一条措辞规则如果没人检查，就会在第一次图省事时消失。"""
    leaked = sorted(k for k in PARAM_SPOKEN if k in text)
    if leaked:
        raise AssertionError(f"报告里出现了参数名 {leaked}；只能用中文说法 {sorted(PARAM_SPOKEN.values())}")


def format_report(spec: dict, attempts: list[Attempt], outcome: Outcome) -> str:
    """三段式。**第 1 段是重点**：证明参数空间已经走过。

    不加第 1 段的话，模型或人会立刻去建议"调一下间距" —— 而那段存在的意义
    就是证明那条路已经走过了。这是措辞层面的约束，但它决定了整个循环会不会退化回前作。
    """
    lines: list[str] = []

    lines.append("### 已尝试过的排布（参数空间已经走过，不必重试）")
    seen: dict[str, list[float]] = {}
    for a in attempts:
        for key, spoken in PARAM_SPOKEN.items():
            seen.setdefault(spoken, []).append(a.params[key])
    for spoken, values in seen.items():
        uniq: list[float] = []
        for v in values:
            if not uniq or uniq[-1] != v:
                uniq.append(v)
        if len(uniq) > 1:
            chain = " → ".join(f"{v:g}" for v in uniq)
            lines.append(f"- {spoken}：{chain}（共 {len(attempts)} 轮）")
    if len(lines) == 1:
        lines.append("- 首轮即通过，没有调整过任何排布参数。")

    lines.append("")
    lines.append("### 仍然失败的项")
    if not outcome.issues:
        lines.append("- 无。")
    for issue in outcome.blocking + outcome.soft:
        lines.append(f"- {issue.line()}")

    lines.append("")
    lines.append("### 能动的只有内容")
    # 建议随 issue 带来，不从 check 类型反推 —— 反推会漏掉
    # “同一类 check 里有两种性质不同的失败”那种情况。
    seen_advice: list[str] = []
    for issue in outcome.blocking + outcome.soft:
        if issue.advice and issue.advice not in seen_advice:
            seen_advice.append(issue.advice)
    if seen_advice:
        lines.extend(f"- {a}" for a in seen_advice)
    else:
        lines.append("- 无需改动。")

    text = "\n".join(lines)
    _assert_no_param_names(text)
    return text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="十项校验 + 自动调参（报告里不出现参数名）")
    ap.add_argument("spec", help="*.diagram.json")
    ap.add_argument("--json", action="store_true", help="附带机器可读结果")
    args = ap.parse_args(argv)

    try:
        with open(args.spec, encoding="utf-8") as fh:
            spec = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"读不到规格：{exc}", file=sys.stderr)
        return 2

    boxes = L.boxes_from_spec(spec)
    try:
        result, outcome, attempts = layout_with_retry(spec, boxes)
    except ValueError as exc:
        print(f"布局失败：{exc}", file=sys.stderr)
        return 1

    print(format_report(spec, attempts, outcome))
    if args.json:
        print(json.dumps({
            "rounds": len(attempts),
            "crossings": result.crossings,
            "blocking": len(outcome.blocking),
            "soft": len(outcome.soft),
        }, ensure_ascii=False, indent=2))
    return 0 if not outcome.blocking else 1


if __name__ == "__main__":
    sys.exit(main())
