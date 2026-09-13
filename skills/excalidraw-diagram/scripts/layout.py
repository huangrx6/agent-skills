#!/usr/bin/env python3
"""分层布局 —— 分层 → 层内排序 → 坐标分配。纯 Python，零依赖。

## 为什么坐标由这里算，不由模型写

配色、大小、字号、排版、连线长度、遮挡 —— 全部是空间计算。让模型直接吐坐标，
本质是让它做一件它没有可靠能力的事。所以规格里没有坐标字段（见 `validate_spec.py`
的封闭字段集），坐标只从这里出。

## 前作栽在哪，本模块怎么防

前作 `draw-excalidraw` 把布局交给了 Dagre / ELK，只暴露一个 `layout.engine` 开关。
后果是：**布局不好时，唯一的动作是"换个引擎"或"改内容"，永远不是"调间距重跑"** ——
修复闭环从一开始就不存在。

本模块把布局参数收在**自己内部**（不放进规格），并把参数做成可调的，
好让 `check_layout.py` 的自动调参循环能失败 → 调参 → 重跑。

## 三个阶段的难度差别（诚实说明）

- **分层**（最长路径）与**坐标分配**：直白。
- **层内排序**（交叉最小化）：Sugiyama 里唯一不 trivial 的部分。本模块用
  barycenter 启发式 + 多轮来回扫描，**每一轮后数一次交叉数并保留最优排列** ——
  不是跑完就算。所以交叉数是这个模块唯一的客观质量指标。

## 环的处理

`architecture` / `dependency` 近似无环，但 `flow` / `state` 可能真的有环。
按标准做法：DFS 找出回边 → 反转它们得到一个 DAG 用于分层与排序 →
出坐标时再把回边的路径反过来（否则箭头方向就错了）。规格与边语义不变。

## 长边

跨越多层的边（rank 差 > 1）要插虚节点（dummy），否则：
① 交叉数算不准（相邻层之间才有定义）；② 边的路径会穿过中间层。

虚节点段带 `origin` 标记，标明它属于哪条原始边 —— 少了这个，从同一节点出发的
多条长边会互相"串线"，走成对方的分支。

用法（一般经 `check_layout.layout_with_retry` 调用，不直接用）：
    python3 layout.py spec.diagram.json --explain
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import sys
from dataclasses import dataclass, replace
from typing import Any

# **图类型这个枚举只有这一份。** `validate_spec.py` 的类型白名单直接从这里取 ——
# 以前它自己抄了一份，两份已经漂移过：`component` / `sequence` 在这个表里有方向，
# 但白名单不接受它们，所以永远走不到（校验先挡掉）。是死条目，已删。
DIRECTION_FOR_TYPE = {
    "architecture": "LR",
    "dependency": "TB",
    "flow": "TB",
    "state": "LR",
    # 这两个类型**没有专用布局**，目前按分层排（SKILL.md 的类型表里写明了）。
    # 以前它们不在这里，靠 `.get(type, "LR")` 的默认值兜着 —— 那是**静默 fallback**，
    # 而"封闭枚举未知值判失败不 fallback"是这个项目自己的规矩。
    # 写出来之后至少是"明说的降级"，不是"悄悄换了个算法"。
    "mindmap": "LR",
    "network": "LR",
}

# ── 布局参数：只在脚本内部，不进规格 ────────────────────────
# 【已实测】rankSeparation 120 沿用前作 Dagre 默认值，实测这些指标对它不敏感；
# **nodeSeparation 从 70 提到 120** —— 70 是继承来的、没验过的值，量出来是这样：
#   同一份五层架构规格（19 节点 / 25 边，含正交路由）：
#     nodeSep 70  → 斜段占 3.9%、2 个标签被挤到压在节点框上、画布高 687
#     nodeSep 90~105 → 仍有 1 个标签压节点，斜段 9~10%（挤到连正交都排不下）
#     nodeSep 115 → 标签清干净，斜段 9.3%
#     nodeSep 120 → **标签 0、斜段 0%**，画布高 912   ← 拐点
#     nodeSep 145 → 同样干净，只是白占地方（高 1024）
# 所以取 120 —— 和 rankSeparation 同值，两个方向的呼吸空间一样大。
# 这一条的来历：先按参数扫描量，再取“再小就开始坏”的那个值，不凭手感定。
# 原则：别人失败经验里的**具体数值**值得复用；他们的**架构决策**不值得复用。
# 但注意——“前作用过、没被推翻”≠“已经验证过”。这两个数我们没量过，所以标待验证。
# 信任状态总表见 references/diagram-spec.md（“数值的信任状态”一节）。
DEFAULT_PARAMS: dict[str, float] = {
    "nodeSeparation": 120.0,
    "rankSeparation": 120.0,
    "barycenterRounds": 4.0,
}
# 自动调参的固定步长与上限（见 check_layout.py 的循环）
PARAM_STEP: dict[str, float] = {
    "nodeSeparation": 20.0,
    "rankSeparation": 30.0,
    "barycenterRounds": 4.0,
}
PARAM_LIMIT: dict[str, float] = {
    "nodeSeparation": 200.0,
    "rankSeparation": 400.0,
    "barycenterRounds": 12.0,
}
DUMMY_PREFIX = "__dummy_"
# ── 图标占位（有 `icon` 字段的节点）────────────────────────
# 图标缩放到 `icons.ICON_HEIGHT` 高，宽度随素材比例变。这两个数是当**尺寸拿不到时**
# 的保守占位（宁可多留白，也不能让图标盖住文字），以及上下留的空隙。
ICON_RESERVE = 30.0
ICON_GAP = 10.0
ICON_VERTICAL_PAD = 6.0

# ── 绕行：连线不许穿过别的节点（P2 / P10）────────────────────
#
# 这几个数都是**待验证**的（没有真实数据校准，见 diagram-spec.md 的信任状态总表）：
# 间隙沿用“元素最小间隙”那一个数，不另起一套。
NODE_CLEARANCE = 12.0
EDGE_MIN = 24.0             # 一条连线上最短的可见段。**唯一定义在这里** ——
                            # check_layout 的判据也从它取：两边各写一个数，迟早会漂。
SMALL_DODGE = 40.0          # 让开这么多像素以内算「小动作」；再多就该换贴车道的画法
                            # （实测：把单点推到 424px 的 V 形，比贴着障碍走更乱）
# 把挡路的线段推开时，偏移量试探的步长与上限。
# 上限就是“推不出去就算了”的那条线 —— 病态图里无限推比不推更糟。
DETOUR_STEP = 28.0
DETOUR_MAX_OFFSET = 280.0
# 最多几轮。一轮解决一处，多轮是给“推完之后又撞上别的”留的余地。
DETOUR_ROUNDS = 6

# ── 径向布局：思维导图（#94）──────────────────────────────────
#
# 思维导图要的是**同心环**（根在中心、按深度铺在环上），不是把分层布局转 90° ——
# 后者出来是一棵树被压扁，而不是"中心辐射"。
#
# 三件事要算对，缺一个就不像：
#   1. **扇区**：每个子树占一段连续角度，按**叶子数**分配 —— 否则一边挤一边空
#   2. **半径**：逐环外推，且必须让**同环相邻节点**不重叠（角度间距 × 半径 ≥ 两者半宽 + 间隙）
#   3. **端点**：连线是朝外的辐条，走两个节点中心之间的直线并裁到盒子边上 ——
#      分层那套"按四个边贴点"的规则在这里不成立
RING_GAP = 46.0            # 环与环之间的净空
RADIAL_REFINE_STEPS = 60   # 半径外推的迭代上界：正常 2~4 轮收敛；这是护栏不是预算
RADIAL_MIN_PUSH = 2.0      # 每轮至少往外让这么多，保证迭代一定在推进
RING_ORDER_ROUNDS = 4      # 环内重排的交换轮数上界：一轮全试一遍，没改进就停
RADIAL_GAP = 34.0          # 同环相邻节点之间的净空

# ── 折段：主轴太长时把它折成几段并排（P7）─────────────────────
#
# 为什么需要：`02-flow` 是一条 13 节点的链，主轴必然很长、交叉轴必然很空 ——
# 实测 114×380（0.30:1），缩到一屏就是一条竖线。**这不是间距能解决的**：
# 间距调小只会更窄、调大只会更长，因为层数不变。唯一能改的是层的排布方式。
#
# 判据用与可读区间同一组数（0.45~4.5），不另立一套。
WRAP_MIN_ASPECT = 0.45
WRAP_MAX_ASPECT = 4.5
# 段与段之间的空档。与 rankSeparation 同量级（120）但它们是两件事：
# 段内是"层与层的距离"，段间是"两块图之间的空白"，后者要更明显才看得出是折过来的。
WRAP_SEGMENT_GAP = 220.0
# 跨栏车道之间的间距。实测踩过：两条跨栏边（`disposable→finishRefresh` 与
# `disposable→failure`）拿到同一个空档 x，**精确重叠**画成了同一条线 ——
# 看上去是"一根线"，其实是两根。现在按用过的次数依次错开。
WRAP_LANE_STEP = 34.0
# 通用车道分配（`_spread_lanes`）：同一条车道线上重叠的段要错开时用这两个数。
# 步长沿用折段那套（34px）；空档放不下就压密，但不再低于 LANE_STEP_MIN ——
# 再密就分不出是两条线了，宁可夹在空档边上。
LANE_STEP_MIN = 14.0
LANE_EDGE_MARGIN = 10.0      # 车道离空档边界（节点外缘）至少留这么多
# 两条线共线重合约 1px 就算“画成一根线” —— 车道分配要避开的正是它。
# **唯一定义在这里**：`check_layout` 的「连线重合」检查也从这里取，
# 两边各写一个数迟早会漂（`EDGE_MIN` 那条注释说的就是这件事）。
EDGE_OVERLAP_MIN = 1.0
# 主轴超过这么长才考虑折。**比例分不出"三个节点排一行"和"十三个节点排一行"** ——
# 两者都是 13:1，但前者是一张小图（一屏放得下），后者才是真长条。
# 少了这条，几张测试用的小图都会被折，几何也跟着变得莫名其妙。
#
# 两个方向的阈值不同，这是**判断**不是推导 —— 因为实测证明没有任何纯几何判据
# 能分开这两种情况：`04-state` 的自然主轴（2090）比 `02-flow`（1734）还长，
# 长短和比例都说"更该折"，但折完 `04-state` 反而更难读。
# 真正的差别在阅读方式：
#   TB 的细长条 = 一条竖线，**任何屏幕都放不下**（屏幕是横的）→ 早折
#   LR 的长条 = 本来就是这个方向该有的样子，横着读是自然的 → 长到两屏以上才折
WRAP_MIN_MAIN = {"TB": 1600.0, "LR": 2400.0}


# 每层最多几个节点还算"链式"。链式图折段是有意义的：主轴长是因为**层数多**，
# 交叉轴空是因为**每层没几个节点**。密集图不一样 —— 它宽高比本来就在区间内，
# 折它只会把段间的连线拉长、横穿过去（实测：05-network 穿节点 1 → 4）。
WRAP_MAX_LAYER_SIZE = 2


def segments_needed(main_total: float, cross_total: float,
                    max_layer: int = 1, direction: str = "TB") -> int:
    """要把主轴折成几段。返回 1 表示**不折**。

    两个条件都要满足才折：

    三个条件都要满足才折：

    1. **真的长**（`WRAP_MIN_MAIN`，按方向取值）—— 比例不够，得看绝对长度。
    2. **比例出区间**（`WRAP_MIN/MAX_ASPECT`，和可读区间同一组数）。
    3. **是链式图**（`WRAP_MAX_LAYER_SIZE`）—— 折段的收益是消掉长条，代价是
       段间连线要绕路；密集图本来就不是长条，付这个代价是净亏。
    """
    if cross_total <= 0 or main_total <= 0:
        return 1
    if max_layer > WRAP_MAX_LAYER_SIZE:
        return 1
    if main_total < WRAP_MIN_MAIN.get(direction, 2400.0):
        return 1
    aspect = (cross_total / main_total) if direction == "TB" else (main_total / cross_total)
    if WRAP_MIN_ASPECT <= aspect <= WRAP_MAX_ASPECT:
        return 1
    return max(1, round((main_total / cross_total) ** 0.5))


# ── 枢纽节点：扇出大的节点在**交叉轴**上长一点（P12）──────────
#
# 为什么：边的落点是沿节点边缘均分的，节点太小就摊不开。实测 order 有 7 条边、
# 节点只有 64px 高 → 7 个锚点挤在 46px 里，相邻只差 6.6px，远处看还是一束。
#
# 为什么只长交叉轴：主轴方向长大会把层间距顶开、整张图被拉长；交叉轴长一点
# 只是在那一列/那一行里多占一点，代价小得多。
#
# 代价（实测过）：节点变高 → 那一层变高变宽 → 整图长宽比跟着动。
# 对 04-state（9.7:1 太宽）和 02-flow（0.3:1 太高）这两种极端反倒是**改善**。
HUB_MIN_FANOUT = 3          # 低于这个数不算枢纽，长它没意义
HUB_GROWTH_PER_EDGE = 14.0  # 每多一条边长这么多
HUB_GROWTH_MAX = 60.0       # 最多长这么多（不封顶的话大枢纽会失衡）


def hub_extra(fanout: int) -> float:
    """这个扇出数该让交叉轴多长。"""
    if fanout < HUB_MIN_FANOUT:
        return 0.0
    return min(HUB_GROWTH_MAX, (fanout - HUB_MIN_FANOUT + 1) * HUB_GROWTH_PER_EDGE)


def fanout_of(spec: dict) -> dict:
    """每个节点连了几条边（进出都算）—— 落点是沿边缘摊开的，两边都占地方。"""
    counts: dict[str, int] = {}
    for edge in spec.get("edges") or []:
        for end in ("from", "to"):
            if edge.get(end):
                counts[edge[end]] = counts.get(edge[end], 0) + 1
    return counts


def main_axis(spec: dict) -> str:
    """这张图的主轴方向 —— 决定“交叉轴”是宽还是高。"""
    return spec.get("direction") or DIRECTION_FOR_TYPE.get(spec.get("type", ""), "LR")
# 同一侧挂多条边时，贴点沿这侧铺开的跨度占边长多少。
#
# 为什么留边距：贴点贴到角上，线与节点的邻边会“粘”在一起；
# 而 0.72 是**待验证**值（没有真实数据校准过，见 diagram-spec.md 的信任状态总表）。
# 只有一条边时**不铺开**，贴点就是边中点 —— 与改之前完全一致（零回归）。
ATTACH_SPAN = 0.72
# 虚节点在交叉轴上的间距。不复用 nodeSeparation（70）—— 虚节点高度为 0，
# 给它一整个节点间距会把层横向撑得很空；但也不能是 0，否则自同一节点出发的
# 平行长边会完全重叠、看上去是一条线。20 取自 Dagre 的 edgesep 默认值。
DUMMY_SEPARATION = 20.0


@dataclass(frozen=True)
class Box:
    """节点的视觉尺寸。由 `text_metrics.measure` 按文字反推，不由模型给。"""

    width: float
    height: float


@dataclass(frozen=True)
class Placed:
    id: str
    x: float
    y: float
    width: float
    height: float
    rank: int


@dataclass
class LayoutResult:
    direction: str
    params: dict[str, float]
    ranks: dict[str, int]
    order: dict[int, list[str]]
    placed: dict[str, Placed]
    edges: list[dict]
    crossings: int
    crossing_origins: list[list[int]]
    dummy_count: int
    reversed_edges: list[tuple[str, str]]
    pin_conflicts: list[str]

    def real_nodes(self) -> dict[str, Placed]:
        return {k: v for k, v in self.placed.items() if not k.startswith(DUMMY_PREFIX)}

    def as_dict(self) -> dict:
        return {
            "direction": self.direction,
            "params": self.params,
            "ranks": {k: v for k, v in self.ranks.items()
                      if not k.startswith(DUMMY_PREFIX)},
            "order": {str(k): v for k, v in self.order.items()},
            "crossings": self.crossings,
            "crossing_origins": self.crossing_origins,
            "dummy_count": self.dummy_count,
            "reversed_edges": [list(e) for e in self.reversed_edges],
            "pin_conflicts": self.pin_conflicts,
            "nodes": {k: {"x": v.x, "y": v.y, "width": v.width, "height": v.height,
                          "rank": v.rank} for k, v in self.real_nodes().items()},
            "edges": self.edges,
        }


# ── 图基础 ──────────────────────────────────────────────────
def _adjacency(node_ids: list[str], edges: list[dict], forward: bool) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {n: [] for n in node_ids}
    for e in edges:
        if forward:
            a, b = e["from"], e["to"]
        else:
            a, b = e["to"], e["from"]
        if a in out and b in out:
            out[a].append(b)
    return out


def break_cycles(node_ids: list[str], edges: list[dict]
                 ) -> tuple[list[dict], list[tuple[str, str]]]:
    """DFS 找出回边并反转，返回 (无环边表, 被反转的边列表)。

    反转的边在出坐标时要再反回来，否则箭头方向就错了。
    """
    color: dict[str, int] = {n: 0 for n in node_ids}   # 0 白 1 灰 2 黑
    succ = _adjacency(node_ids, edges, forward=True)
    reversed_set: set[tuple[str, str]] = set()

    for root in node_ids:
        if color[root] != 0:
            continue
        stack: list[tuple[str, int]] = [(root, 0)]
        color[root] = 1
        while stack:
            node, i = stack[-1]
            if i < len(succ[node]):
                nxt = succ[node][i]
                stack[-1] = (node, i + 1)
                if color.get(nxt, 2) == 1:          # 指向还在栈上的节点 = 回边
                    reversed_set.add((node, nxt))
                elif color.get(nxt, 2) == 0:
                    color[nxt] = 1
                    stack.append((nxt, 0))
            else:
                color[node] = 2
                stack.pop()

    dag: list[dict] = []
    for e in edges:
        key = (e["from"], e["to"])
        if key in reversed_set:
            dag.append({**e, "from": e["to"], "to": e["from"]})
        else:
            dag.append(dict(e))
    return dag, sorted(reversed_set)


def _topological(node_ids: list[str], edges: list[dict]) -> list[str]:
    indeg = {n: 0 for n in node_ids}
    for e in edges:
        if e["from"] in indeg and e["to"] in indeg:
            indeg[e["to"]] += 1
    queue = [n for n in node_ids if indeg[n] == 0]
    out: list[str] = []
    while queue:
        n = queue.pop(0)
        out.append(n)
        for m in _adjacency([n], edges, forward=True)[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                queue.append(m)
    # break_cycles 之后理论上不会有剩余环；留个退路而不是静默丢节点
    for n in node_ids:
        if n not in out:
            out.append(n)
    return out


def _rank_conflicts(ranks: dict[str, int], edges: list[dict]) -> list[tuple[str, str, int, int]]:
    return [(e["from"], e["to"], ranks[e["from"]], ranks[e["to"]])
            for e in edges
            if e["from"] in ranks and e["to"] in ranks
            and ranks[e["to"]] <= ranks[e["from"]]]


def _raise_conflicts(bad: list[tuple[str, str, int, int]], why: str) -> None:
    detail = "；".join(f"{a}(rank {ra}) → {b}(rank {rb})" for a, b, ra, rb in bad)
    raise ValueError(f"{why}，无法排出合法的层：{detail}")


# ── 阶段一：分层 ────────────────────────────────────────────
def assign_ranks(node_ids: list[str], dag: list[dict],
                 explicit: dict[str, int] | None = None) -> dict[str, int]:
    """最长路径分层，然后应用规格里的 `rank` 约束。

    显式 `rank` 当**硬约束**：设完之后向前推后继（至少 r+1）。若因此违反 rank
    关系，抛错而不是悄悄放宽 —— 那是规格写错了，该让用户知道。
    """
    order = _topological(node_ids, dag)
    preds = _adjacency(node_ids, dag, forward=False)
    ranks = {n: 0 for n in node_ids}
    for n in order:
        if preds[n]:
            ranks[n] = max(ranks[p] + 1 for p in preds[n] if p in ranks)

    overridden: list[tuple[str, int, int]] = []
    for n in order:
        if explicit and n in explicit:
            ranks[n] = explicit[n]
        if preds[n]:
            pushed = max(ranks[n], max(ranks[p] + 1 for p in preds[n]))
            if explicit and n in explicit and pushed != explicit[n]:
                overridden.append((n, explicit[n], pushed))
            ranks[n] = pushed

    if overridden:
        detail = "；".join(f"{n} 写了 rank {want}，但它的前驱要求 ≥{got}"
                          for n, want, got in overridden)
        raise ValueError(
            f"rank 约束与边方向矛盾：{detail}。"
            f"要么改 rank，要么把边的方向反过来。"
        )

    bad = _rank_conflicts(ranks, dag)
    if bad:
        _raise_conflicts(bad, "rank 约束相互冲突")
    return ranks


def apply_axis_pins(ranks: dict[str, int], pins: dict[str, str], direction: str,
                    dag: list[dict]) -> tuple[dict[str, int], list[str]]:
    """主轴方向的 pin（LR 的 left/right、TB 的 top/bottom）→ 强制取该轴两端。

    这里**必须复核一次边约束**：把一个有前驱的节点钉到 rank 0，等于要求它和
    前驱同层，那是排不出合法分层的。发现冲突就退回原 rank 并记下来 ——
    悄悄放宽会让 pin 变成一个有时管用有时不管用的东西。
    """
    if not ranks:
        return ranks, []
    low_pin, high_pin = ("left", "right") if direction == "LR" else ("top", "bottom")
    out = dict(ranks)
    conflicts: list[str] = []
    lo, hi = min(ranks.values()), max(ranks.values())
    for node, pin in pins.items():
        if node not in out or pin not in (low_pin, high_pin):
            continue
        original = out[node]
        out[node] = lo if pin == low_pin else hi
        bad = _rank_conflicts(out, dag)
        if bad:
            out[node] = original
            first = bad[0]
            conflicts.append(
                f"{node} 的 pin: {pin} 与图结构冲突"
                f"（{first[0]} → {first[1]} 会变成同层或逆序），已退回 rank {original}"
            )
    return out, conflicts


def insert_dummies(ranks: dict[str, int], dag: list[dict]
                   ) -> tuple[dict[str, int], list[dict], list[dict], list[str]]:
    """给跨多层的边插虚节点。

    返回 (含虚节点的 ranks, 展开后的边段, 原始边表, 虚节点 id 列表)。
    虚节点宽度按 0 处理（只占排序槽位，不占视觉空间）。

    每个边段带 `origin` —— 原始边的**下标**，而不是 (from, to) 对：
    ① 少了这个标记，拆出来的段无法归因；
    ② 用 `from` 匹配也不行，一个节点可以同时是好几条长边的起点，
       那样它们会全部走成同一条链；
    ③ 用 (from, to) 也不够，重复边（同一对节点之间两条边）会被合并成一条。
    下标是唯一且不会撞的。
    """
    all_ranks = dict(ranks)
    segments: list[dict] = []
    origins: list[dict] = []
    dummy_ids: list[str] = []
    counter = 0

    for idx, e in enumerate(dag):
        a, b = e["from"], e["to"]
        origins.append({**e, "origin": idx})
        if ranks[b] - ranks[a] <= 1:
            segments.append({**e, "origin": idx})
            continue
        prev = a
        for r in range(ranks[a] + 1, ranks[b]):
            did = f"{DUMMY_PREFIX}{counter}"
            counter += 1
            all_ranks[did] = r
            dummy_ids.append(did)
            segments.append({**e, "from": prev, "to": did, "origin": idx})
            prev = did
        segments.append({**e, "from": prev, "to": b, "origin": idx})
    return all_ranks, segments, origins, dummy_ids


# ── 阶段二：层内排序 ────────────────────────────────────────
def crossing_pairs(order: dict[int, list[str]], segments: list[dict]
                   ) -> list[tuple[dict, dict]]:
    """逐对找出真正交叉的边段。

    `count_crossings` 就是本函数的长度 —— 计数与定位**共用同一份实现**。
    分成两份写的话，“报了几处”和“报的是哪几处”迟早会对不上，
    而那种不一致比没有指标更糟：人会先怀疑自己的图。

    只算相邻层：跨层边已经被虚节点拆成逐层的段，所以定义是完整的。
    O(E²) —— 本 skill 的规模（6~14 节点）下清晰比快更重要。
    """
    pos: dict[str, int] = {}
    rank_of: dict[str, int] = {}
    for r, layer in order.items():
        for i, n in enumerate(layer):
            pos[n] = i
            rank_of[n] = r

    by_pair: dict[tuple[int, int], list[dict]] = {}
    for s in segments:
        a, b = s["from"], s["to"]
        if a not in pos or b not in pos or rank_of[b] != rank_of[a] + 1:
            continue
        by_pair.setdefault((rank_of[a], rank_of[b]), []).append(s)

    out: list[tuple[dict, dict]] = []
    for group in by_pair.values():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                u1, v1 = pos[group[i]["from"]], pos[group[i]["to"]]
                u2, v2 = pos[group[j]["from"]], pos[group[j]["to"]]
                if (u1 < u2 and v1 > v2) or (u1 > u2 and v1 < v2):
                    out.append((group[i], group[j]))
    return out


def count_crossings(order: dict[int, list[str]], segments: list[dict]) -> int:
    return len(crossing_pairs(order, segments))


def _barycenter(node: str, neighbors: dict[str, list[str]],
                pos: dict[str, int]) -> float | None:
    vals = [pos[n] for n in neighbors.get(node, []) if n in pos]
    return sum(vals) / len(vals) if vals else None


def _seed_order(ranks: dict[str, int], seed: list[str]) -> dict[int, list[str]]:
    layers: dict[int, list[str]] = {}
    for n in seed:
        if n in ranks:
            layers.setdefault(ranks[n], []).append(n)
    return layers


def order_layers(ranks: dict[str, int], segments: list[dict], seed: list[str],
                 rounds: float) -> tuple[dict[int, list[str]], int]:
    """barycenter 多轮扫描，**每轮后数交叉并保留最优**。

    保留最优这一点是关键：barycenter 不是单调改进的启发式，跑更多轮不保证更好。
    只保留链尾那次，等于把最好的排列丢掉 —— 这也正是"多跑几轮"看起来没用的原因。
    """
    current = _seed_order(ranks, seed)
    if not current:
        return {}, 0
    best = {r: list(v) for r, v in current.items()}
    best_cross = count_crossings(best, segments)

    nodes = list(ranks)
    preds = _adjacency(nodes, segments, forward=False)
    succ = _adjacency(nodes, segments, forward=True)
    max_rank = max(current)

    # 轮数用 while 递增，而不是 `range(int(rounds))`：rounds 来自浮点参数表，
    # 那个整数转换没有真实的失败可能，但 lint 规则 unchecked-throwing-call-python
    # 会把**任何**裸 int()/float() 当错误报。与其加一个永远不会触发的 try 去哄它，
    # 不如换个不需要转换的写法。附带好处：轮数不会被静默截断。
    sweep = 0
    while sweep < rounds:
        sweep += 1
        for r in range(1, max_rank + 1):
            # 空层是合法的：显式 rank 把节点抬到高处后，中间会留下一整段没有节点的层。
            # 不跳过就会拿着不存在的键去取列表。
            if not current.get(r):
                continue
            pos = {n: i for layer in current.values() for i, n in enumerate(layer)}
            keys = {n: _barycenter(n, preds, pos) for n in current[r]}
            current[r] = sorted(current[r], key=lambda n: (keys[n] is None, keys[n] or 0.0))
        c = count_crossings(current, segments)
        if c < best_cross:
            best, best_cross = {r: list(v) for r, v in current.items()}, c

        for r in range(max_rank - 1, -1, -1):
            if not current.get(r):
                continue
            pos = {n: i for layer in current.values() for i, n in enumerate(layer)}
            keys = {n: _barycenter(n, succ, pos) for n in current[r]}
            current[r] = sorted(current[r], key=lambda n: (keys[n] is None, keys[n] or 0.0))
        c = count_crossings(current, segments)
        if c < best_cross:
            best, best_cross = {r: list(v) for r, v in current.items()}, c

    return best, best_cross


def apply_cross_axis_pins(order: dict[int, list[str]], ranks: dict[str, int],
                          pins: dict[str, str], direction: str) -> dict[int, list[str]]:
    """交叉轴方向的 pin（LR 的 top/bottom、TB 的 left/right）→ 该层排最前 / 最后。"""
    cross_low, cross_high = ("top", "bottom") if direction == "LR" else ("left", "right")
    out = {r: list(layer) for r, layer in order.items()}
    for node, pin in pins.items():
        if pin not in (cross_low, cross_high):
            continue
        r = ranks.get(node)
        if r is None or r not in out:
            continue
        layer = [n for n in out[r] if n != node]
        out[r] = ([node] + layer) if pin == cross_low else (layer + [node])
    return out


# ── 阶段三：坐标分配 ────────────────────────────────────────
def aabb_gap(a: Any, b: Any) -> float:
    """两个包围盒之间的最短距离（重叠时为 0）。

    **间隙的唯一实现**：check_layout 的间隙校验和径向布局的自动外推都用它。
    两处各写一份的话就是第二个漂移点 —— 这个项目已经吃过几次这个亏。
    """
    gap_x = max(b.x - (a.x + a.width), a.x - (b.x + b.width), 0.0)
    gap_y = max(b.y - (a.y + a.height), a.y - (b.y + b.height), 0.0)
    return math.hypot(gap_x, gap_y)


def _aabb_deficit(a: Any, b: Any, want: float) -> float:
    """离 want 还差多少；**重叠时连渗入深度一起算**。

    这样外推一次就够，而不是每轮只挪 12px（上界只有 60 轮，慢慢挪会用完）。
    """
    dx = max(b.x - (a.x + a.width), a.x - (b.x + b.width))
    dy = max(b.y - (a.y + a.height), a.y - (b.y + b.height))
    if dx >= 0 and dy >= 0:
        return max(0.0, want - math.hypot(dx, dy))
    if dx < 0 and dy < 0:
        return want + min(-dx, -dy)      # 两轴都相交：最短分离平移
    return want - max(dx, dy, 0.0)


def support_extent(box: Any, ux: float, uy: float) -> float:
    """轴对齐盒子在**方向 (ux, uy)** 上的半宽。

    **唯一实现**：径向的半径外推、力导向的碰撞感知斥力都用它 —— 两处各写一份的话
    就是第二个漂移点（这个项目已经吃过几次这个亏）。
    单位方向不需要归一化也会错得很自然，所以这里显式归一化。
    """
    length = math.hypot(ux, uy) or 1.0
    return ((box.width / 2.0) * abs(ux / length)
            + (box.height / 2.0) * abs(uy / length))


def _radial_extent(box: Any, theta: float) -> float:
    """盒子在**半径方向**（角度 theta）上的半宽 = 支撑值在径向的分量。"""
    return support_extent(box, math.cos(theta), math.sin(theta))


def _tangential_extent(box: Any, theta: float) -> float:
    """盒子在**切向**上的半宽。"""
    return support_extent(box, -math.sin(theta), math.cos(theta))


def _angular_distance(first: float, second: float) -> float:
    delta = abs(first - second) % (2 * math.pi)
    return min(delta, 2 * math.pi - delta)


def _nearest_by_angle(node: str, members: list[str], angle: dict[str, float],
                      count: int = 2) -> list[str]:
    """角度上离 node 最近的若干个（跨环比较用）。

    不取全局最大：内环节点一多，"最宽的那个"会把整圈撑得毫无必要地大。
    取最近的几个（通常是它的父节点）才是有意义的那对。
    """
    return sorted(members, key=lambda m: _angular_distance(
        angle.get(m, 0.0), angle.get(node, 0.0)))[:count]


def _seed_radii(rings: dict[int, list[str]], angle: dict[str, float],
                boxes: dict[str, Any]) -> dict[int, float]:
    """半径初值：按**方向感知**的支撑值，不是 height/2。

    第一版拿 height/2 当"半径方向的半宽"，于是 150×50 的盒子在 -150° 方向上
    真实半宽 77px、公式只算 25px —— 两环的框直接叠上（实测间隙 0px）。
    轴对齐的盒子在半径方向上的半宽是 (w/2)|cosθ| + (h/2)|sinθ|。
    """
    radius: dict[int, float] = {}
    for index in sorted(rings):
        members = rings[index]
        if index == 0:
            radius[0] = 0.0
            continue
        inner_radius = radius.get(index - 1, 0.0)
        inner = rings.get(index - 1, [])
        need = inner_radius + RING_GAP
        for n in members:
            theta = angle.get(n, 0.0)
            extent = _radial_extent(boxes[n], theta)
            for m in _nearest_by_angle(n, inner, angle):
                need = max(need, inner_radius
                           + _radial_extent(boxes[m], angle.get(m, 0.0))
                           + extent + RING_GAP)
        if len(members) == 1:
            need = max(need, _tangential_extent(
                boxes[members[0]], angle.get(members[0], 0.0)) + RADIAL_GAP)
        else:
            # 同环相邻：角度差 × 半径 ≥ 切向半宽和 + 间隙
            for i, n in enumerate(members):
                other = members[(i + 1) % len(members)]
                delta = _angular_distance(angle.get(n, 0.0), angle.get(other, 0.0))
                delta = delta if delta > 1e-9 else 2 * math.pi
                span = (_tangential_extent(boxes[n], angle.get(n, 0.0))
                        + _tangential_extent(boxes[other], angle.get(other, 0.0)))
                need = max(need, (span + RADIAL_GAP) / delta)
        radius[index] = need
    return radius


def _place_rings(rings: dict[int, list[str]], angle: dict[str, float],
                 radius: dict[int, float], boxes: dict[str, Any]) -> dict[str, Any]:
    """把每环的节点摆到自己的圆上（位置是**中心**在 (r cosθ, r sinθ)）。"""
    placed: dict[str, Any] = {}
    for index in sorted(rings):
        r = radius.get(index, 0.0)
        for n in rings[index]:
            theta = angle.get(n, 0.0)
            box = boxes[n]
            placed[n] = Placed(id=n,
                               x=round(r * math.cos(theta) - box.width / 2.0, 2),
                               y=round(r * math.sin(theta) - box.height / 2.0, 2),
                               width=box.width, height=box.height, rank=index)
    return placed


def _ring_deficit(placed: dict[str, Any], ring_of: dict[str, int],
                  want: float) -> tuple[int | None, float, str, str]:
    """所有节点对里最严重的一处"离 want 还差多少"。"""
    worst_ring, worst_missing, worst_pair = None, 0.0, ("", "")
    ids = sorted(placed)
    for position, a_id in enumerate(ids):
        for b_id in ids[position + 1:]:
            missing = _aabb_deficit(placed[a_id], placed[b_id], want)
            if missing > worst_missing:
                worst_missing = missing
                worst_ring = max(ring_of[a_id], ring_of[b_id])
                worst_pair = (a_id, b_id)
    return worst_ring, worst_missing, worst_pair[0], worst_pair[1]


def _refine_radii(rings: dict[int, list[str]], angle: dict[str, float],
                  boxes: dict[str, Any]) -> tuple[dict[str, Any], dict[int, float]]:
    """半径定稿：**摆出来量真实间隙，不够就往外推**。

    初值公式再怎么修都是近似（盒子的占位随角度变、同环两个宽盒子彼此挤压），
    所以最终值由"量"决定，不由公式决定 —— 和折段那次"空档位置从摆好的坐标实测"
    是同一条原则。推的是**这一环连同它外面的所有环**，相对间距保持不变。

    60 轮还没收敛就不收敛了：交出去的图会带着真实的间隙问题，由间隙校验报阻塞项、
    进而拒绝出图 —— 布局层不替校验层兜底，也不假装成功。
    """
    radius = _seed_radii(rings, angle, boxes)
    ring_of = {n: index for index, members in rings.items() for n in members}
    want = NODE_CLEARANCE + 1.0
    placed = _place_rings(rings, angle, radius, boxes)
    for _ in range(RADIAL_REFINE_STEPS):
        hit, missing, first, second = _ring_deficit(placed, ring_of, want)
        if hit is None:
            return placed, radius
        if ring_of[first] == ring_of[second]:
            # 同环：往外推能拉开弧长，但增益是角度差倍数 → 按角度差放大
            delta = max(_angular_distance(angle.get(first, 0.0),
                                          angle.get(second, 0.0)), 0.05)
            push = max(missing / delta, RADIAL_MIN_PUSH)
        else:
            push = max(missing, RADIAL_MIN_PUSH)
        for index in list(radius):
            if index >= hit:
                radius[index] += push
        placed = _place_rings(rings, angle, radius, boxes)
    return placed, radius


def radial_tree(node_ids: list[str], edges: list[dict]) -> tuple[str, dict[str, int], dict[str, list[str]]]:
    """把图取成一棵树：返回 (根, 深度, 孩子表)。

    取根的顺序：**入度为 0 → 扇出最大 → 输入顺序**。都在输入里出现过并列的情况，
    所以三级都要有，结果才是确定的（同一份规格永远出同一张图）。
    有多条入边的节点按 BFS 先到先得，多余的边**仍然会被画出来**（只是不参与定位）——
    思维导图本来就可能有交叉引用。
    """
    children: dict[str, list[str]] = {n: [] for n in node_ids}
    indegree = {n: 0 for n in node_ids}
    outdegree = {n: 0 for n in node_ids}
    for edge in edges:
        a, b = edge["from"], edge["to"]
        if a in children and b in indegree and a != b:
            outdegree[a] += 1
            indegree[b] += 1
    roots = [n for n in node_ids if indegree[n] == 0] or list(node_ids)
    root = max(roots, key=lambda n: (outdegree[n], -node_ids.index(n)))

    depth = {root: 0}
    queue = [root]
    seen = {root}
    while queue:
        current = queue.pop(0)
        for edge in edges:
            if edge["from"] != current:
                continue
            child = edge["to"]
            if child in seen or child not in children:
                continue
            seen.add(child)
            children[current].append(child)
            depth[child] = depth[current] + 1
            queue.append(child)
    # 断开的节点（不在任何边里）挂在根下面，深度 1 —— 丢了它们等于丢内容
    for n in node_ids:
        if n not in depth:
            depth[n] = 1
            children[root].append(n)
    return root, depth, children


def _leaf_count(node: str, children: dict[str, list[str]],
                cache: dict[str, int]) -> int:
    if node not in cache:
        kids = children.get(node, [])
        cache[node] = 1 if not kids else sum(
            _leaf_count(k, children, cache) for k in kids)
    return cache[node]


# ── 力导向：网状图（#94）────────────────────────────────────────
#
# 网状图没有天然层级，分层会把它拉成一条长条（05-network 实测 4.3:1）。
# 力导向不假设层级：边当弹簧、节点当互相排斥的盒子，结构自己显形。
#
# **确定性是硬要求**：同一份规格永远出同一张图（否则"改一个标签，整张图重排"）。
# 所以初始位置用**确定的圆**（按输入顺序），不用随机数、不做多次重启取最优。
FORCE_ITERATIONS = 320        # 迭代轮数
FORCE_COOLING = 0.94          # 每轮温度衰减 = 每步位移的上界
FORCE_INITIAL_SPREAD = 0.62   # 初始圆半径 = 这个系数 × 理想间距 × √n
FORCE_OVERLAP_PUSH = 0.8      # 重叠时额外的分离力度（相对重叠深度）
FORCE_SEPARATION_ROUNDS = 80  # 收尾分离的轮数上界
# 下面两个系数是**扫出来的**（改源文件 + 子进程跑 emit 完整流水线，12 组各量一次；
# 之所以要子进程：emit 的布局是经 check_layout 的调参器调的，而 check_layout 每次被
# `load_sibling` 重新 exec 一份 —— 进程内 monkeypatch 挂不到它用的那份上，量不出差别）。
#
#   系数/份额     画布         比例   穿  软项
#   0.5 / 0.35   907×755      1.2    0    0
#   0.5 / 0.7    922×755      1.2    0    0   ← 选它
#   0.8 / 0.7   1070×949      1.1    0    0
#   1.4 / 0.7   1161×1596     1.4    0    0
#
# 12 组**都没有**穿节点、没有软项，所以差别只有"多紧"。选偏紧的那个不只是因为好看：
# **调参器只会加大间距（单向）** —— 默认偏松就永远不会被收紧，默认偏紧时该松的场合
# 调参器会自己补上。面积因此降到默认松值的 1/2.2。
FORCE_IDEAL_EXTRA = 0.5       # 理想中心距 = rankSeparation + 这个系数 × 节点平均长边
FORCE_CLEARANCE_SHARE = 0.7   # 最小间隙取 nodeSeparation 的多少（下限仍是 NODE_CLEARANCE）


def _force_centres(live: list[str], boxes: dict[str, Any],
                   edges: list[dict], params: dict[str, float]) -> dict[str, list[float]]:
    """力学迭代，返回每个节点的**中心**坐标。

    两个参数**真的连着**（不然调参那几轮对着它空转 —— 前作就是"有旋钮没人拧"）：
    - `rankSeparation` → 理想中心距（把连线拉长，对付"连线过短"）
    - `nodeSeparation` → 盒子之间至少留多少（对付"挨得过近"和"连线穿节点"）
    """
    typical = sum(max(boxes[n].width, boxes[n].height) for n in live) / len(live)
    ideal = (params.get("rankSeparation", DEFAULT_PARAMS["rankSeparation"])
             + FORCE_IDEAL_EXTRA * typical)
    clearance = max(NODE_CLEARANCE, FORCE_CLEARANCE_SHARE * params.get(
        "nodeSeparation", DEFAULT_PARAMS["nodeSeparation"]))

    radius = ideal * math.sqrt(len(live)) * FORCE_INITIAL_SPREAD
    centre: dict[str, list[float]] = {}
    for index, node in enumerate(live):
        theta = 2.0 * math.pi * index / len(live)
        centre[node] = [radius * math.cos(theta), radius * math.sin(theta)]
    temperature = radius * 0.35

    for _ in range(FORCE_ITERATIONS):
        disp = {node: [0.0, 0.0] for node in live}
        for i in range(len(live)):
            for j in range(i + 1, len(live)):
                first, second = live[i], live[j]
                dx = centre[first][0] - centre[second][0]
                dy = centre[first][1] - centre[second][1]
                distance = math.hypot(dx, dy)
                if distance < 1e-6:
                    # 完全重合：给一个**确定的**小偏移（按输入顺序），不能靠随机
                    dx, dy = 0.0, 1e-3 * (i + 1)
                    distance = math.hypot(dx, dy)
                ux, uy = dx / distance, dy / distance
                push = ideal * ideal / distance
                need = max(clearance, support_extent(boxes[first], ux, uy)
                           + support_extent(boxes[second], ux, uy))
                if distance < need:
                    push += (need - distance) * FORCE_OVERLAP_PUSH
                disp[first][0] += ux * push
                disp[first][1] += uy * push
                disp[second][0] -= ux * push
                disp[second][1] -= uy * push
        for edge in edges:
            a, b = edge.get("from"), edge.get("to")
            if a not in centre or b not in centre or a == b:
                continue
            dx = centre[a][0] - centre[b][0]
            dy = centre[a][1] - centre[b][1]
            distance = math.hypot(dx, dy) or 1e-6
            ux, uy = dx / distance, dy / distance
            pull = distance * distance / ideal
            disp[a][0] -= ux * pull
            disp[a][1] -= uy * pull
            disp[b][0] += ux * pull
            disp[b][1] += uy * pull
        for node in live:
            dx, dy = disp[node]
            length = math.hypot(dx, dy)
            if length < 1e-9:
                continue
            step = min(length, temperature)     # 步长上界 = 当前温度
            centre[node][0] += dx / length * step
            centre[node][1] += dy / length * step
        temperature *= FORCE_COOLING
    return centre


def _separate_boxes(placed: dict[str, Any], want: float) -> dict[str, Any]:
    """收尾分离：**摆出来量，不够就推开**（不指望力学一定收敛到不重叠）。

    用的是同一个 `_aabb_deficit`（径向的半径外推也用它）—— 同一件几何一份实现。
    推的方向是两个盒心的连线方向，各让一半。轮数有上界；到顶还没分开就如实交出去，
    由间隙校验报出来（布局层不替校验层兜底，也不假装成功）。
    """
    out = dict(placed)
    ids = sorted(out)
    for _ in range(FORCE_SEPARATION_ROUNDS):
        worst = 0.0
        for position, first in enumerate(ids):
            for second in ids[position + 1:]:
                a, b = out[first], out[second]
                deficit = _aabb_deficit(a, b, want)
                if deficit <= 0:
                    continue
                worst = max(worst, deficit)
                ax, ay = a.x + a.width / 2.0, a.y + a.height / 2.0
                bx, by = b.x + b.width / 2.0, b.y + b.height / 2.0
                dx, dy = ax - bx, ay - by
                length = math.hypot(dx, dy) or 1.0
                shift = deficit / 2.0 + 0.5
                out[first] = _shift(a, dx / length * shift, dy / length * shift)
                out[second] = _shift(b, -dx / length * shift, -dy / length * shift)
        if worst <= 0.0:
            break
    return out


def _shift(box: Any, dx: float, dy: float) -> Any:
    return Placed(id=box.id, x=round(box.x + dx, 2), y=round(box.y + dy, 2),
                  width=box.width, height=box.height, rank=box.rank)


def force_layout(node_ids: list[str], boxes: dict[str, Any], edges: list[dict],
                 params: dict[str, float]) -> tuple[dict[str, Any], dict[str, int],
                                                    dict[int, list[str]], list[dict]]:
    """力导向布局（网状图）。返回 (placed, depth, order, routed)。

    `depth` 与 `order` 对力导向没有意义（没有层）。给的是**统一的 0** ——
    没有任何东西消费它们（校验与落笔都只看坐标），但签名与径向保持一致，
    免得调用方要为两种布局写两套分支。
    """
    live = [n for n in node_ids if n in boxes]
    if not live:
        return {}, {}, {}, []
    centre = _force_centres(live, boxes, edges, params)
    placed = {}
    for node in live:
        box = boxes[node]
        # 力学算的是**中心**；Placed 存左上角
        placed[node] = Placed(id=node,
                              x=round(centre[node][0] - box.width / 2.0, 2),
                              y=round(centre[node][1] - box.height / 2.0, 2),
                              width=box.width, height=box.height, rank=0)
    want = max(NODE_CLEARANCE, FORCE_CLEARANCE_SHARE * params.get(
        "nodeSeparation", DEFAULT_PARAMS["nodeSeparation"]))
    placed = _separate_boxes(placed, want)
    return placed, {n: 0 for n in live}, {0: list(live)}, straight_edges(edges, placed)


def _assign_sectors(root: str, order: dict[str, list[str]],
                    leaves: dict[str, int]) -> dict[str, tuple[float, float]]:
    """扇区：根占整圆，每个父节点的孩子按**叶子数**切分它的扇区。

    切分顺序由 `order` 决定 —— 重排就是换这个顺序（见 _search_sibling_order）。
    """
    sector: dict[str, tuple[float, float]] = {root: (-math.pi, math.pi)}
    for node in _breadth_first(root, order):
        kids = [k for k in order.get(node, []) if k in leaves]
        if not kids:
            continue
        low, high = sector[node]
        total = sum(leaves[k] for k in kids) or 1
        cursor = low
        for kid in kids:
            share = (high - low) * leaves[kid] / total
            sector[kid] = (cursor, cursor + share)
            cursor += share
    return sector


def _rings_of(live: list[str], depth: dict[str, int],
              angle: dict[str, float]) -> dict[int, list[str]]:
    """按深度分环，环内按角度排序（角度是从扇区切出来的，所以这就是环上顺序）。"""
    rings: dict[int, list[str]] = {}
    for node in live:
        rings.setdefault(depth.get(node, 0), []).append(node)
    for members in rings.values():
        members.sort(key=lambda node: angle.get(node, 0.0))
    return rings


def _edge_cost(placed: dict[str, Any], routed: list[dict]) -> tuple[int, int]:
    """真指标：(穿节点数, 交叉数)。

    穿节点用的是 `check_layout` 那条检查**同一个原语**（`nodes_hit_by_polyline`，
    排除自己的两端），所以这里量的和报告里写的、以及 fixture 基线记的是同一个数。

    交叉用的是**几何定义** —— 径向报的就是它。分层报的是组合定义（相邻层顺序倒置），
    两者是不同的量（见 `geometric_crossing_pairs` 的说明），所以这个函数只用来做
    径向的取舍，不拿去和分层的交叉数比。
    """
    through = 0
    for edge in routed:
        through += len(nodes_hit_by_polyline(
            edge["points"], placed, {edge["from"], edge["to"]}))
    return through, len(geometric_crossing_pairs(routed))


def _search_sibling_order(root: str, children: dict[str, list[str]],
                          leaves: dict[str, int], boxes: dict[str, Any],
                          depth: dict[str, int], live: list[str],
                          edges: list[dict]) -> tuple[dict[str, list[str]], tuple[int, int]]:
    """在**扇区槽位**之间重排兄弟节点，降低穿节点/交叉。返回 (顺序, 代理代价)。

    对齐分层的 `order_layers`：那边在层内重排（barycenter + 保留最优），这边在
    扇区槽位之间重排。差别在**粒度** —— 分层的节点彼此独立；径向的槽位属于**子树**，
    排一个兄弟会把它的整棵子树带着走（后代的角度是从父节点的扇区递归切出来的），
    所以重排的单位是子树，不是单个节点。

    目标按**字典序**：(穿节点数, 交叉数)。不混成加权和 —— 穿节点是遮挡（内容被压住
    读不出来），交叉只是多一根线，两者不是一回事，加权和会把取舍藏进系数里。

    用**便宜代理**（初值半径 + 直裁线，实测 0.06ms）而不是完整摆放（35ms，几乎全花在
    `avoid_nodes` 上）—— 几十个候选就是几秒。代理会**高估**穿节点（它没有绕行能力），
    所以它只负责提名；采纳前用真指标复核，见 `radial_layout`。
    """
    order = {node: list(kids) for node, kids in children.items()}

    def cost(candidate: dict[str, list[str]]) -> tuple[int, int]:
        sector = _assign_sectors(root, candidate, leaves)
        angle = {node: sum(bounds) / 2.0 for node, bounds in sector.items()}
        rings = _rings_of(live, depth, angle)
        placed = _place_rings(rings, angle, _seed_radii(rings, angle, boxes), boxes)
        lines: list[dict] = []
        for index, edge in enumerate(edges):
            a, b = edge.get("from"), edge.get("to")
            if a not in placed or b not in placed:
                continue
            lines.append({"from": a, "to": b, "origin": index,
                          "points": list(_clip_to_boxes(placed[a], placed[b]))})
        return _edge_cost(placed, lines)

    best = cost(order)
    for _ in range(RING_ORDER_ROUNDS):
        improved = False
        for node in _breadth_first(root, children):
            siblings = order.get(node, [])
            for i in range(len(siblings)):
                for j in range(i + 1, len(siblings)):
                    trial = {key: list(value) for key, value in order.items()}
                    trial[node][i], trial[node][j] = trial[node][j], trial[node][i]
                    candidate = cost(trial)
                    if candidate < best:
                        best, order, improved = candidate, trial, True
        if not improved:
            break
    return order, best


def _radial_pipeline(order: dict[str, list[str]], root: str,
                     leaves: dict[str, int], boxes: dict[str, Any],
                     depth: dict[str, int], live: list[str],
                     edges: list[dict]) -> tuple[dict[str, Any], dict[int, list[str]], list[dict]]:
    """一套完整摆放：扇区 → 环 → 半径外推 → 连线绕行。返回 (placed, rings, routed)。"""
    sector = _assign_sectors(root, order, leaves)
    angle = {node: sum(bounds) / 2.0 for node, bounds in sector.items()}
    rings = _rings_of(live, depth, angle)
    placed, _radius = _refine_radii(rings, angle, boxes)
    return placed, rings, straight_edges(edges, placed)


def radial_layout(node_ids: list[str], boxes: dict[str, Any],
                  edges: list[dict]) -> tuple[dict[str, Any], dict[str, int],
                                             dict[int, list[str]], list[dict]]:
    """同心环布局。返回 (placed, depth, 环上的顺序, 已绕行的连线)。

    连线一起返回，是因为**绕行（`avoid_nodes`）占了整个函数 99% 的时间**（35ms 里
    几乎全是它），而它对外面没有意义 —— 让调用方再绕一遍就是白花一倍。
    """
    root, depth, children = radial_tree(node_ids, edges)
    live = [n for n in node_ids if n in boxes]
    if not live:
        return {}, {}, {}, []

    leaves: dict[str, int] = {}
    for n in live:
        _leaf_count(n, children, leaves)

    # ── 环上顺序：默认**用作者写的顺序**；只有真的被遮挡了才去搜别的排法 ──
    #
    # 环上的顺序同时也是**阅读顺序**（人按什么次序写节点，图上就按什么次序读）。
    # 所以重排是有代价的，代价换来的必须是"遮挡变少" —— 只少一根交叉不值得把作者的
    # 顺序打乱。这条还带来一个好处：**没遮挡的图根本不跑搜索**，快路径的成本和
    # 没有环内排序时完全一样。
    placed, rings, routed = _radial_pipeline(children, root, leaves, boxes,
                                             depth, live, edges)
    occlusions = _edge_cost(placed, routed)
    if occlusions[0]:
        searched, _proxy = _search_sibling_order(root, children, leaves, boxes,
                                                 depth, live, edges)
        if searched != children:
            trial = _radial_pipeline(searched, root, leaves, boxes,
                                     depth, live, edges)
            # 代理只负责**提名**；采纳与否看真指标，而且只看主键（穿节点数）
            if _edge_cost(trial[0], trial[2])[0] < occlusions[0]:
                placed, rings, routed = trial

    order = {index: list(members) for index, members in rings.items()}
    return placed, depth, order, routed


def _breadth_first(root: str, children: dict[str, list[str]]) -> list[str]:
    """自根向下逐层访问（父一定排在子前面）。"""
    out: list[str] = []
    queue = [root]
    seen = {root}
    while queue:
        node = queue.pop(0)
        out.append(node)
        for child in children.get(node, []):
            if child not in seen:
                seen.add(child)
                queue.append(child)
    return out


def straight_edges(edges: list[dict], placed: dict[str, Any]) -> list[dict]:
    """连线 = 两个盒心之间的直线，裁到各自的盒子边上。

    **不分层的图共用这一份**（径向的辐条、力导向的弹簧线）。分层那套"按 LR/TB 的
    四个边贴点"在这里不成立 —— 这类图的线的方向取决于两个节点的相对位置，
    不是固定的上下左右。

    **试过又退掉的方案**：交叉引用（非树边）绕外圈走弧。当时理由是长弦会穿过圆心
    附近的节点；实测确实如此（3 条边各穿 2 个节点），但那是**软项、不阻塞出图** ——
    而绕外圈付出的代价更大：所有交叉引用被推到最外环之外，几条弧合并成一圈看起来
    像"容器边界"的多边形，读者会以为画里有个框；从同一节点收进来的几条还会长距离
    收敛成一个尖。**穿节点是软项，围栏是结构误读** —— 后者更糟。退回直线，穿节点
    如实报在软项里，由人决定要不要改内容。
    """
    out: list[dict] = []
    for index, edge in enumerate(edges):
        a, b = edge.get("from"), edge.get("to")
        if a not in placed or b not in placed:
            continue
        start, end = _clip_to_boxes(placed[a], placed[b])
        points = avoid_nodes([start, end], placed, {a, b})
        out.append({"from": a, "to": b, "points": points, "reversed": False,
                    "label": edge.get("label"), "kind": edge.get("kind"),
                    "origin": index})
    return out


def _clip_to_boxes(a: Any, b: Any) -> tuple[list[float], list[float]]:
    """把中心连线裁到两个盒子的边界上（各取中心出发、朝对方那一侧的交点）。"""
    ax, ay = a.x + a.width / 2.0, a.y + a.height / 2.0
    bx, by = b.x + b.width / 2.0, b.y + b.height / 2.0
    return (_edge_point(a, ax, ay, bx, by), _edge_point(b, bx, by, ax, ay))


def _edge_point(box: Any, cx: float, cy: float, tx: float, ty: float) -> list[float]:
    """从盒心朝 (tx, ty) 射线，与盒子边界的交点。"""
    dx, dy = tx - cx, ty - cy
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return [round(cx, 2), round(cy, 2)]
    scale = math.inf
    if abs(dx) > 1e-9:
        scale = min(scale, (box.width / 2.0) / abs(dx))
    if abs(dy) > 1e-9:
        scale = min(scale, (box.height / 2.0) / abs(dy))
    return [round(cx + dx * scale, 2), round(cy + dy * scale, 2)]


def geometric_crossing_pairs(edges: list[dict]) -> list[list[int]]:
    """**几何**交叉：哪些边对真的穿过了彼此（返回规格里的边序号）。

    分层布局用的是组合定义（相邻层之间顺序倒置），那个定义要求"有层"；
    径向没有层，所以这里换几何定义 —— 两者是两个不同的量，各自在各自的路径上
    是有意义的那个。报的是同一栏数字，但定义写在各自的 docstring 里，不混用。

    第一版按**线段对**计数，一条弧被折成 18 段就把它自己那一对边算成十几次，
    于是"7 处交叉"变成"31 处"：同一对边最多记 1 次才对得上分层那个定义的口径。

    与 `crossing_pairs` / `count_crossings` 保持同构：**定位与计数共用一份实现**，
    这样报告里那句"必须给出交叉的是哪几条边"在径向的图上同样成立。
    """
    polylines: list[list] = []
    origins: list[int] = []
    for edge in edges:
        origin = edge.get("origin")
        if not isinstance(origin, int):
            continue          # 没有来源序号的边不参与定位（两条路径都会填上）
        polylines.append(edge.get("points") or [])
        origins.append(origin)   # 与 polylines 同步追加，下标才对得上
    pairs: list[list[int]] = []
    for i in range(len(polylines)):
        for j in range(i + 1, len(polylines)):
            if _polylines_cross(polylines[i], polylines[j]):
                pairs.append([origins[i], origins[j]])
    return pairs



def _polylines_cross(first: list, second: list) -> bool:
    """两条折线是否**真正穿过**彼此（端点相碰不算）。"""
    for a, b in zip(first, first[1:]):
        for c, d in zip(second, second[1:]):
            if _segments_intersect(a, b, c, d):
                return True
    return False


def _segments_intersect(p1, p2, p3, p4) -> bool:
    """严格相交：四条叉积**同号反转**才算。

    用"严格"，是为了让**端点相碰不算交叉** —— 从同一个节点出发的两条弧会共享
    同一个外侧出发点（坐标完全一样），宽松判据会把它们记成交叉。
    """
    def cross(o, a, b) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    d1, d2 = cross(p3, p4, p1), cross(p3, p4, p2)
    d3, d4 = cross(p1, p2, p3), cross(p1, p2, p4)
    return d1 * d2 < 0 and d3 * d4 < 0


@dataclass(frozen=True)
class Coords:
    """坐标 + **折段的划分**。

    段信息必须跟着坐标一起出来：跨段的那条连线要走两栏之间的空档绕过去，
    它得知道"段在哪、空档在哪"。在别处再算一遍就是两份实现，两份必然漂移。
    """

    placed: dict[str, Placed]
    segments: dict[int, int]          # 层号 → 段号（不折时全是 0）
    bands: tuple[float, ...]          # 段间空档的中心（交叉轴坐标）


def assign_coordinates(order: dict[int, list[str]], boxes: dict[str, Box],
                       direction: str, node_sep: float, rank_sep: float,
                       groups_of: dict[str, str] | None = None) -> Coords:
    """`groups_of` 是**节点 → 区域**的映射（可选），只用来决定折点位置 —— 见下面那段。"""
    live = {r: [n for n in layer if n in boxes] for r, layer in order.items()}
    live = {r: layer for r, layer in live.items() if layer}
    if not live:
        return Coords(placed={}, segments={}, bands=())

    def main_size(n: str) -> float:
        b = boxes[n]
        return b.width if direction == "LR" else b.height

    def cross_size(n: str) -> float:
        b = boxes[n]
        return b.height if direction == "LR" else b.width

    def gap_for(node: str, node_sep_value: float) -> float:
        return DUMMY_SEPARATION if node.startswith(DUMMY_PREFIX) else node_sep_value

    main_extent = {r: max(main_size(n) for n in layer) for r, layer in live.items()}
    cross_total = {
        r: sum(cross_size(n) for n in layer)
        + sum(gap_for(layer[i], node_sep) for i in range(len(layer) - 1))
        for r, layer in live.items()
    }
    cross_max = max(cross_total.values())

    main_start: dict[int, float] = {}
    cursor = 0.0
    for r in sorted(live):                 # 空层不占主轴空间，只跳过
        main_start[r] = cursor
        cursor += main_extent[r] + rank_sep

    placed: dict[str, Placed] = {}
    for r, layer in live.items():
        offset = (cross_max - cross_total[r]) / 2.0
        for n in layer:
            b = boxes[n]
            # 主轴方向在层内居中，让跨层长边更直
            main_pos = main_start[r] + (main_extent[r] - main_size(n)) / 2.0
            if direction == "LR":
                x, y = main_pos, offset
            else:
                x, y = offset, main_pos
            placed[n] = Placed(id=n, x=round(x, 2), y=round(y, 2), width=b.width,
                               height=b.height, rank=r)
            offset += cross_size(n) + gap_for(n, node_sep)

    # ── 折段（P7）────────────────────────────────────────────
    # 主轴太长时把层切成几段并排 —— "链式图缩到一屏是一条线"的唯一解法。
    # 放在坐标算完之后：只是一次平移，不碰分层与层内排序的任何逻辑。
    main_total = cursor - rank_sep if len(live) > 1 else cursor
    count = segments_needed(main_total, cross_max,
                            max(len(layer) for layer in live.values()), direction)
    segments: dict[int, int] = {}
    if count > 1:
        ranks = sorted(live)
        per_segment = -(-len(ranks) // count)          # 向上取整
        # ⚠️ **折点不许切进一个区域**。区域是"一块连续的东西"，被折成两栏就不是一块了 ——
        # 而且区域的包围盒会横跨两栏，把两栏之间的节点全包进去（实测：一张 29 层、
        # 8 个区域的图，按等差折点会把 3 个区域劈开，报出 20 条"框里夹着非成员"）。
        # 判据：相邻两层若共享同一个 group，就必须留在同一段。
        rank_groups: dict[int, set[str]] = {}
        if groups_of:
            for r, layer in live.items():
                rank_groups[r] = {groups_of[n] for n in layer if n in groups_of}
        # 切点只能落在**区域边界**上（相邻两层不共享 group）；没有区域时处处可切。
        allowed = [j for j in range(1, len(ranks))
                   if not (rank_groups.get(ranks[j], set())
                           & rank_groups.get(ranks[j - 1], set()))]

        def partition(limit: int) -> list[int] | None:
            """在允许的位置切，让每段不超过 limit 层；做不到就返回 None。

            贪心**尽量晚切**（每段塞满再切）—— 这样段数最少，也就是"用最少的栏数
            把最长的那一栏压到 limit 以内"。
            """
            cuts: list[int] = []
            start = 0
            while len(ranks) - start > limit:
                candidates = [c for c in allowed if start < c <= start + limit]
                if not candidates:
                    return None
                cut = max(candidates)
                cuts.append(cut)
                start = cut
                if len(cuts) >= count:
                    return None          # 段数超了：这个 limit 不可行
            return cuts

        # 目标不是"每段尽量一样长"，而是**把最长的那一段压下来** ——
        # 折段本来就是为了别让画布拉成一条长条，所以约束在**最长段**上。
        # 旧的写法是"够长了就切"，被区域边界一挡就睡得很不均（实测 Spring 那张
        # 折成 9 / 16 / 5：中间一栏是旁边的三倍高）。
        best_cuts: list[int] | None = None
        low_limit, high_limit = -(-len(ranks) // count), len(ranks)
        while low_limit <= high_limit:
            middle = (low_limit + high_limit) // 2
            got = partition(middle)
            if got is None:
                low_limit = middle + 1
            else:
                best_cuts = got
                high_limit = middle - 1
        cuts = sorted(best_cuts or [])
        segments = {}
        current = 0
        for index, r in enumerate(ranks):
            if current < len(cuts) and index >= cuts[current]:
                current += 1
            segments[r] = current
        segment_first: dict[int, int] = {}
        for r in ranks:
            segment_first.setdefault(segments[r], r)
        # 平移：**每段都当作独立的一栏**摆在交叉轴上，主轴各自从 0 重新开始。
        for r in ranks:
            segment = segments[r]
            # 交叉轴：每段往右让开一个"段宽 + 段间空档"。第 0 段不让。
            cross_shift = segment * (cross_max + WRAP_SEGMENT_GAP)
            # 主轴：**每段都从 0 重新开始**。
            # 少了这一步就不是"折"，而是"斜着错开的楼梯" —— 高度一点没降，只多了宽度，
            # 长宽比数字会变好看但图反而更大。第一版就漏了这一步。
            main_shift = main_start[segment_first[segment]] if segment else 0.0
            if not cross_shift and not main_shift:
                continue
            for n in live[r]:
                p = placed[n]
                if direction == "TB":
                    placed[n] = Placed(id=p.id, x=round(p.x + cross_shift, 2),
                                       y=round(p.y - main_shift, 2), width=p.width,
                                       height=p.height, rank=p.rank)
                else:
                    placed[n] = Placed(id=p.id, x=round(p.x - main_shift, 2),
                                       y=round(p.y + cross_shift, 2), width=p.width,
                                       height=p.height, rank=p.rank)
    if not segments:
        segments = {r: 0 for r in live}
    # 空档位置**从摆好的坐标实测**，不按 `cross_max + gap/2` 解析推算 ——
    # 两者会差：第一版按理论值算，跨段那条连线横走的那一段正好落在别的节点上。
    extent: dict[int, list[float]] = {}
    for nid, p in placed.items():
        lo, hi = ((p.x, p.x + p.width) if direction == "TB" else (p.y, p.y + p.height))
        slot = extent.setdefault(segments[p.rank], [lo, hi])
        slot[0], slot[1] = min(slot[0], lo), max(slot[1], hi)
    bands = []
    for k in range(1, max(segments.values()) + 1):
        if (k - 1) in extent and k in extent:
            bands.append(round((extent[k - 1][1] + extent[k][0]) / 2.0, 2))
    return Coords(placed=placed, segments=segments, bands=tuple(bands))


# ── 边路径 ──────────────────────────────────────────────────
def route_edges(origins: list[dict], segments: list[dict],
                placed: dict[str, Placed], direction: str,
                reversed_set: set[tuple[str, str]], align: bool = True) -> list[dict]:
    """把（可能经过虚节点的）原始边连成折线。

    遍历的是**原始边**而不是边段 —— 拆出来的首段也带虚节点，按段遍历会把
    跨层边整条漏掉（首段被当成虚节点段跳过）。
    被反转过的边在绘制时要再反回来 —— 否则箭头方向就错了。
    """
    out: list[dict] = []
    # 先把所有链解出来 —— 贴点要**跨边**协调（同一个节点上的几条边得均分），
    # 逐条遍历时看不到别人。注意链的方向是 DAG 方向，可能与原始边的 from/to 相反。
    resolved = []
    for idx, e in enumerate(origins):
        chain = _follow(idx, e, segments, placed)
        if len(chain) >= 2:
            resolved.append((idx, chain))
    # 主轴链拉直（只动交叉轴，且先量间隙）。放在锚点分配**之前** ——
    # 贴点要按最终位置算，先分锚点再挪节点等于白算。
    if align:
        _align_spine(placed, origins, direction)
    gaps = _rank_gaps(placed, direction)
    starts, ends = _anchor_slots(resolved, placed, direction)

    for idx, chain in resolved:
        e = origins[idx]
        pts = _points(chain, placed, direction, starts[idx], ends[idx])
        # 推开挡路的节点。排除自己的两端 —— 它们本来就贴着线。
        pts = avoid_nodes(pts, placed, {chain[0], chain[-1]})
        # 最后一道：能直就直。上一步只保证「不穿节点」，不保证「不绕远」——
        # 虚节点车道会把跨层边牵着在每一层横移一次（实测偏离直线 324px）。
        waypoints = [[placed[n].x + placed[n].width / 2,
                      placed[n].y + placed[n].height / 2] for n in chain[1:-1]]
        start_rank, end_rank = placed[chain[0]].rank, placed[chain[-1]].rank
        # 第二条候选：**丢掉落在首尾跨度之外的虚节点行**，剩下的按行进方向排好 ——
        # 这样纵向移动是单调的（0 次来回）。实测 3 条来回边都是被“绕出去的行”拖的：
        # 目标行 547，而某个虚节点行在 572，于是必须先下去再回来。
        # 实测这几条边的来回是**同一个病**：路由要经过的虚节点行/列落在首尾跨度之外，
        # 路径就只能先出去再回来。虚节点的位置是分层布局给的（它给长边留的空位），跟这条
        # 边要往哪走没关系。所以给两条把它拉回跨度内的候选：
        #   ① 丢掉跨度外的那些站；② 保留站、但把**横轴坐标夹进跨度**。
        #
        # ⚠️ 横轴是 x 还是 y **由方向决定** —— 这里曾经写死用 y，于是 TB 图那边等于没做
        # （TB 的横轴是 x）。是量 03-dependency 时发现「过滤前后结果一样」抓出来的。
        cross = 1 if direction == "LR" else 0
        low, high = sorted((pts[0][cross], pts[-1][cross]))
        backwards = pts[0][cross] > pts[-1][cross]
        ordered = sorted(waypoints, key=lambda w: w[cross], reverse=backwards)
        inside = [w for w in ordered if low - 1 <= w[cross] <= high + 1]
        clamped = []
        for w in ordered:
            pulled = list(w)
            pulled[cross] = min(max(w[cross], low), high)
            if not clamped or pulled != clamped[-1]:
                clamped.append(pulled)
        variants = [_orthogonal_path(pts[0], pts[-1], waypoints, direction, gaps,
                                     start_rank, end_rank)]
        for alternative in (inside, clamped):
            if alternative and alternative != waypoints:
                variants.append(_orthogonal_path(pts[0], pts[-1], alternative, direction,
                                                 gaps, start_rank, end_rank))
        pts = straighten(pts, placed, {chain[0], chain[-1]}, orthogonals=variants,
                         endpoints=(chain[0], chain[-1]))
        a, b = e["from"], e["to"]
        was_reversed = (b, a) in reversed_set
        if was_reversed:
            # 回到原始方向。只翻折线点不动 from/to 的话，报告里的两端与点的走向相反 ——
            # 下游照着 from→to 画箭头就会画反。
            a, b = b, a
            pts = list(reversed(pts))
        out.append({"from": a, "to": b, "points": pts, "reversed": was_reversed,
                    "label": e.get("label"), "kind": e.get("kind")})
    return out


def _follow(origin_idx: int, origin_edge: dict, segments: list[dict],
            placed: dict[str, Placed]) -> list[str]:
    """沿**同一条 origin** 的虚节点链走到下一个真实节点。

    起点必须是该 origin 的**首个边段**，不能直接用原始边：拆过的边其 `to` 已经是
    终点，直接跟会立刻退出循环，整条虚节点链被跳过（跨层边于是画成一条直连的线）。
    """
    first = next((s for s in segments if s.get("origin") == origin_idx), None)
    if first is None:
        return [c for c in (origin_edge["from"], origin_edge["to"]) if c in placed]

    chain = [first["from"]]
    cur = first
    for _ in range(1000):
        if not cur["to"].startswith(DUMMY_PREFIX):
            break
        chain.append(cur["to"])
        nxt = [s for s in segments
               if s["from"] == cur["to"] and s.get("origin") == origin_idx]
        if not nxt:
            break
        cur = nxt[0]
    chain.append(cur["to"])
    return [c for c in chain if c in placed]


def _corridors(placed: dict[str, Placed], direction: str) -> dict[int, tuple[float, float]]:
    """相邻两层之间的空档区间 `{下层 rank: (低, 高)}`（LR 是 x，TB 是 y）。

    与 `_rank_gaps` 同一件事的**区间版**：那个只给中线（车道默认坐标），
    这里还要给出这条带子的**边界** —— 车道在带子里左右挪才不会挪进节点。
    """
    by_rank: dict[int, list] = {}
    for nid, node in placed.items():
        if nid.startswith(DUMMY_PREFIX):
            continue
        by_rank.setdefault(node.rank, []).append(node)
    out: dict[int, tuple[float, float]] = {}
    ranks = sorted(by_rank)
    for lower, upper in zip(ranks, ranks[1:]):
        if direction == "LR":
            low = max(n.x + n.width for n in by_rank[lower])
            high = min(n.x for n in by_rank[upper])
        else:
            low = max(n.y + n.height for n in by_rank[lower])
            high = min(n.y for n in by_rank[upper])
        out[lower] = (low, high)
    return out


def _shift_limits(pts: list, si: int, axis: int) -> tuple[float, float]:
    """这一段沿 `axis` 平移 δ 时，δ 被什么夹住 —— 由**相邻两段**的长度下限决定。

    为什么不能只靠事后复核：把车道往源节点那一侧挪时，第一段（贴点引出线）
    会被压短 —— 实测 01-architecture 里 10px，`_path_is_sane` 于是把整条边退掉，
    重叠又回来了。**事先算清楚能挪多少**，比“挪完发现不行再退回来”稳得多。

    相邻段与这一段的**方向相反**（横平竖直的折线是交替的），所以平移 δ 会让
    前一段长 δ、后一段短 δ；两边都要求 ≥ EDGE_MIN，而且**不许反向**
    （反向就是在图上多了个回勾）。返回 `(-inf, inf)` 表示没有约束。
    """
    low, high = -math.inf, math.inf
    a, b = pts[si], pts[si + 1]
    if si > 0:
        span = a[axis] - pts[si - 1][axis]
        if abs(span) > 0.5:
            if span > 0:
                low = max(low, EDGE_MIN - span)
            else:
                high = min(high, -EDGE_MIN - span)
    if si + 2 < len(pts):
        span = pts[si + 2][axis] - b[axis]
        if abs(span) > 0.5:
            if span > 0:
                high = min(high, span - EDGE_MIN)
            else:
                low = max(low, span + EDGE_MIN)
    return low, high


def _lane_window(item: list, placed: dict[str, Placed],
                 direction: str, corridors: dict) -> tuple[float, float] | None:
    """这一条段可以挪到哪个坐标区间 —— `None` = 没有位置约束。

    两种来源，取交集：
    - **端口段**：挪的是贴点，它必须留在**那一面**上（离角留 `PORT_SNAP_MARGIN`）。
    - **空档里的段**：只能在同一空档内挪。注意空档的坐标轴是主轴
      （LR 是 x、TB 是 y），所以只有固定轴正好等于主轴的那些段才用得上它 ——
      横穿某一层的那种段（LR 的横段、TB 的竖段）不靠空档定位，没这个约束。
    再叠上 `_shift_limits`：相邻两段不许被压到可见下限以下、也不许反向。
    """
    fixed_axis, coord, port = item[2], item[3], item[7]
    low, high = coord + item[8], coord + item[9]
    bounds = None
    if port is not None:
        box = placed.get(port)
        if box is None:
            return None
        if fixed_axis == 0:
            bounds = (box.x + PORT_SNAP_MARGIN, box.x + box.width - PORT_SNAP_MARGIN)
        else:
            bounds = (box.y + PORT_SNAP_MARGIN, box.y + box.height - PORT_SNAP_MARGIN)
    elif fixed_axis == (0 if direction == "LR" else 1):
        for span_low, span_high in corridors.values():
            if span_low - 1.0 <= coord <= span_high + 1.0:
                bounds = (span_low + LANE_EDGE_MARGIN, span_high - LANE_EDGE_MARGIN)
                break
    if bounds is not None:
        low, high = max(low, bounds[0]), min(high, bounds[1])
    if low > high:
        return None                              # 无处可挪
    return (low, high)


def _pick_lane(center: float, lane_no: int, step: float,
               window: tuple[float, float] | None, ok) -> float:
    """给一条车道选个落脚点。

    候选顺序沿用折段那套“对称往两边散”，但每一步都要过 `ok` —— 那个判据里既有
    窗口（不能挪到节点里去），也有**全局占用**（不能挪到另一条线头上）。
    实测踩过：只比同组内的坐标，`a2→b1` 被挪到了 `a1→b1` 所在的那一行 ——
    重合换了一对而已。

    实在找不到合适的就退到“夹在窗口里、离已占用的点最远”的候选：空档确实放不下时
    如实把重合留给 `check_layout` 去报，而不是直接把这条段丢掉不管。
    """
    def clamp(value: float) -> float:
        if window is None:
            return value
        return min(max(value, window[0]), window[1])

    side = -1.0 if lane_no % 2 else 1.0
    magnitude = ((lane_no + 1) // 2) * step
    fallback = None
    fallback_gap = -1.0
    for k in range(1, 6):
        span = magnitude + (k - 1) * step
        for candidate in (center + side * span, center - side * span):
            target = clamp(candidate)
            accepted, gap = ok(target)
            if accepted:
                return target
            if gap > fallback_gap:
                fallback, fallback_gap = target, gap
    return fallback if fallback is not None else center


def _spread_lanes(routed: list[dict], placed: dict[str, Placed],
                  direction: str) -> int:
    """把**共线且区间重叠**的段错开 —— 治「线与线重合」。

    病根：`_orthogonal_path` 里所有跨层段用的都是**同一个**车道坐标
    （`_rank_gaps` 给的空档中线）。于是同一个空档里，只要两条边的交叉轴区间
    有重叠，它们就精确画在同一条线上 —— 看上去是一根线，其实是两根。
    实测：01-architecture 里 `order→user` 与 `order→cache` 在 x=966 上
    重合 225px；7 张自带图里有 5 张存在重合（最长 225px）。
    去重逻辑本来只写在折段布局（`coords.bands`）那一个分支里，普通分层一条都没有。

    做法，**先量再挪**：
      1. 收集**所有**段（含端口引出线），按「固定轴 + 该轴坐标」分组 ——
         同组就是共线的。斜段不参与（它不与任何段共线）。
         端口段也收：实测 02-flow 的重合就是两条端口引出线
         （一条进 `scan` 的顶面、一条从同一个面出来）画在同一条 x 上。
         但**端口段只有当它垂直于所在那一面时**才允许挪 —— 否则一挪就把
         贴点推离了那一面。
      2. 组内按交叉轴区间做**区间着色**（first-fit）：区间重叠的段拿不同车道号。
      3. 车道坐标 = 原坐标 ± 对称步长（沿用折段那套写法）；
         空档放不下就压密，压到 `LANE_STEP_MIN` 为止，再不行就夹在空档/那一面里。
      4. 逐段平移（只改固定轴分量）—— 相邻段方向不变，仍然横平竖直。
      5. 挪完**逐边复核**：不穿节点 / 不穿自己 / 不留过短段 / 不新增主轴来回；
         任一不满足就这条边整条回退。不硬拗：宁可留一处重合（校验会报它），
         也不能为它把线推进节点里。

    返回实际挪动的段数（给用例与调试看）。
    """
    items: list[list] = []   # [ei, si, 固定轴, 坐标, 区间低, 区间高, 车道号, 端口节点, δ下限, δ上限]
    for ei, edge in enumerate(routed):
        pts = edge["points"]
        for si in range(len(pts) - 1):
            a, b = pts[si], pts[si + 1]
            if math.dist(a, b) < 0.5:
                continue
            if abs(a[0] - b[0]) <= 0.5:
                fixed_axis, cross = 0, 1
            elif abs(a[1] - b[1]) <= 0.5:
                fixed_axis, cross = 1, 0
            else:
                continue                        # 斜段不与任何段共线
            port = None
            normal = None
            if si == 0 or si == len(pts) - 2:
                if si == 0:
                    port, anchor = edge["from"], a
                else:
                    port, anchor = edge["to"], b
                box = placed.get(port)
                if box is not None:
                    normal = _outward_normal(anchor, box)
            if port is not None:
                if normal is None:
                    continue
                # 这一段必须**垂直于那一面**（走出去/进来的方向）才挪得动：
                # 固定轴 0 = 竖段，只能贴在上下两面；固定轴 1 = 横段，只能贴在左右两面。
                if (fixed_axis == 0 and normal[0] != 0) or \
                        (fixed_axis == 1 and normal[1] != 0):
                    continue
            items.append([ei, si, fixed_axis, a[fixed_axis],
                          min(a[cross], b[cross]), max(a[cross], b[cross]),
                          None, port, *_shift_limits(pts, si, fixed_axis)])
    if not items:
        return 0

    # 按「固定轴 + 坐标」分组（同一条直线上的段）。带容差 —— 坐标都是算出来的，
    # 回舍误差会造出两条本该当成一条的组。
    groups: list[list] = []
    for item in sorted(items, key=lambda it: (it[2], it[3])):
        if groups and groups[-1][0][2] == item[2] \
                and abs(groups[-1][0][3] - item[3]) <= 1.0:
            groups[-1].append(item)
        else:
            groups.append([item])

    corridors = _corridors(placed, direction)
    # 全部段的当前占位，按轴分。挪一段就更新它 —— “别把线挪到另一条线头上”
    # 靠的就是这张全图（而不是单个组）的表。
    occupancy: dict[tuple[int, int], tuple[int, float, float, float]] = {
        (item[0], item[1]): (item[2], item[3], item[4], item[5]) for item in items}
    shifts: dict[tuple[int, int], tuple[int, float]] = {}
    for group in groups:
        lanes: list[list[tuple[float, float]]] = []
        for item in sorted(group, key=lambda it: (it[4], it[5], it[0])):
            for lane_no, taken in enumerate(lanes):
                # 只是**端点相接**不算重叠（共用拐点的两段本来就这样）。
                if all(item[5] <= low + 0.5 or item[4] >= high - 0.5
                       for low, high in taken):
                    taken.append((item[4], item[5]))
                    item[6] = lane_no
                    break
            else:
                item[6] = len(lanes)
                lanes.append([(item[4], item[5])])
        if len(lanes) < 2:
            continue                             # 这一条线上没有要错开的
        center = group[0][3]
        window = _lane_window(group[0], placed, direction, corridors)
        step = WRAP_LANE_STEP
        if window is not None:
            room = window[1] - window[0]
            if room != math.inf:
                step = max(LANE_STEP_MIN, min(step, room / (len(lanes) + 1)))
        placed_here: list[float] = [center]
        for item in group:
            lane_no = item[6]
            if lane_no == 0:
                continue                         # 第 0 道留在原地
            own = _lane_window(item, placed, direction, corridors)
            if own is None:
                continue                         # 自己没地方挪（不是“没有约束”）
            room = own[1] - own[0]
            step_here = step if room == math.inf else max(
                LANE_STEP_MIN, min(step, room / (len(lanes) + 1)))

            def ok(target, _item=item):
                """`(可用?, 离本组其它落点多远)` —— 窗口在外面已经夹过了。
                两件事：离**本组**已定的落点够远；不压在**别的边**的某段上。"""
                gap = min((abs(target - other) for other in placed_here), default=math.inf)
                if gap < LANE_STEP_MIN:
                    return False, gap
                axis, low, high = _item[2], _item[4], _item[5]
                for (other_ei, _si), spot in occupancy.items():
                    if other_ei == _item[0] or spot[0] != axis:
                        continue
                    if abs(spot[1] - target) > 0.75:
                        continue
                    if min(high, spot[3]) - max(low, spot[2]) > EDGE_OVERLAP_MIN:
                        return False, gap
                return True, gap

            target = _pick_lane(center, lane_no, step_here, own, ok)
            placed_here.append(target)
            occupancy[(item[0], item[1])] = (item[2], target, item[4], item[5])
            shifts[(item[0], item[1])] = (item[2], round(target - center, 2))

    if not shifts:
        return 0

    # 一个拐点可能同时是「要挪的竖段」和「要挪的横段」的端点 —— 两条轴互不干扰，
    # 所以这里按**轴**记冲突，而不是按点。（只按点记会把这种合法的两个方向当成冲突，
    # 02-flow 的收尾就是因此没挪成。）
    touched: dict[int, dict[int, dict[int, float]]] = {}
    for (ei, si), (axis, delta) in sorted(shifts.items()):
        edge_points = touched.setdefault(ei, {})
        conflict = False
        for known, per_axis in edge_points.items():
            if axis in per_axis and (known in (si, si + 1) or known + 1 in (si, si + 1)):
                conflict = True
                break
        if conflict:
            continue                             # 共用拐点且同为这一根轴：跳过这一段
        edge_points.setdefault(si, {})[axis] = delta

    moved = 0
    for ei, deltas in touched.items():
        edge = routed[ei]
        before = [list(p) for p in edge["points"]]
        trial = [list(p) for p in before]
        for si, per_axis in deltas.items():
            for point in (trial[si], trial[si + 1]):
                for axis, delta in per_axis.items():
                    point[axis] = round(point[axis] + delta, 2)
        if _path_is_sane(trial, before, placed, edge["from"], edge["to"]):
            edge["points"] = trial
            moved += len(deltas)
    return moved


def _path_is_sane(trial: list, before: list, placed: dict[str, Placed],
                  head_id: str, tail_id: str) -> bool:
    """挪过车道的路径还成不成立 —— 车道分配后唯一的复核口。

    四件事：不能穿节点、不能穿自己两端节点的盒子、不能留下过短的段、
    不能新增主轴来回（挪过头时相邻段会反向，看上去是个回勾）。
    斜段不可能被造出来（挪的是轴对齐坐标），但检查很便宜，还是查一下。
    """
    if nodes_hit_by_polyline(trial, placed, {head_id, tail_id}):
        return False
    if _crosses_own_nodes(trial, placed, head_id, tail_id):
        return False
    if _is_slanted(trial):
        return False
    if any(math.dist(a, b) < EDGE_MIN for a, b in zip(trial, trial[1:])):
        return False
    return _reversals(trial) <= _reversals(before)


def _anchor_slots(resolved: list, placed: dict[str, Placed],
                  direction: str) -> tuple[dict, dict]:
    """给每个节点两侧的贴点分配位置 —— **治 P1（喷泉）**。

    以前所有边都连到节点的同一个边中点：实测一个节点同时喷出 6 条线，
    三种图型（架构 / 思维导图 / 状态机）上都是目视最刺眼的一处。

    两件事：
      1. **排序**：按另一端的横向坐标排 —— 往上的目标配上面的贴点。
         这不只是为了好看，它会直接减少交叉（可以从交叉数上量出来）。
      2. **均分**：k 条边就把跨度均分 k 份，每条取每份的中夹（单条 = 中点）。

    返回 `(起点偏移, 终点偏移)`，两个都是 `{origin_idx: 偏移像素}`。
    偏移参照节点在交叉轴上的中心，沿贴点所在边量。
    """
    starts: dict[str, list] = {}
    ends: dict[str, list] = {}
    for idx, chain in resolved:
        starts.setdefault(chain[0], []).append((idx, chain[-1]))
        ends.setdefault(chain[-1], []).append((idx, chain[0]))
    return (_slots(starts, placed, direction), _slots(ends, placed, direction))


def _slots(groups: dict[str, list], placed: dict[str, Placed],
           direction: str) -> dict:
    """一张贴点表：同一节点上的多条边沿这一侧均分。"""
    out: dict[int, float] = {}
    for nid, items in groups.items():
        p = placed[nid]
        if direction == "LR":
            span = p.height * ATTACH_SPAN
        else:
            span = p.width * ATTACH_SPAN

        def other_axis(item, _p=p):
            """另一端在交叉轴上的坐标（LR 的交叉轴是 y，TB 是 x）。"""
            q = placed[item[1]]
            return (q.y + q.height / 2) if direction == "LR" else (q.x + q.width / 2)

        # idx 参与排序键：位置相同时仍然稳定，不会因遍历顺序不同而抖动
        ordered = sorted(items, key=lambda it: (other_axis(it), it[0]))
        count = len(ordered)
        for j, (idx, _other) in enumerate(ordered):
            if count == 1:
                out[idx] = 0.0
            else:
                out[idx] = ((j + 0.5) / count - 0.5) * span
    return out


def _port_faces(here: Placed, neighbour: Placed, direction: str) -> tuple[float, float]:
    """这个节点的端口该开在哪一面 —— **朝着下一站**，而不是照着布局方向的假设。

    踩过的坑：TB 图一向「从底边出去」（假设 rank 往下长），可 02-flow 的 rank 轴
    是反的（rank 6 的画布 y 反而更小）—— 于是 `scan→stage` 从 scan 的**底边**出去，
    接着却要往上走，整条线从自己的盒子里穿了过去（图上看就是线从框里冒出来），
    而 `nodes_hit_by_polyline` 一向排除两端节点，这种路一直没人拦。

    判据只看**下一站的中心在哪边**，跟布局方向、跟 rank 大小都无关：
    - LR：下一站在左边就开左边，否则右边
    - TB：下一站在上边就开上边，否则下边
    回边（往左上走的）因此自动拿到"对着目标"的那一面，不需要额外的分支。
    """
    hx, hy = here.x + here.width / 2, here.y + here.height / 2
    nx, ny = neighbour.x + neighbour.width / 2, neighbour.y + neighbour.height / 2
    if direction == "LR":
        return (here.x, hy) if nx < hx else (here.x + here.width, hy)
    return (hx, here.y) if ny < hy else (hx, here.y + here.height)


def _points(chain: list[str], placed: dict[str, Placed], direction: str,
            start_off: float = 0.0, end_off: float = 0.0) -> list[list[float]]:
    """链上的折点（链是 **DAG 方向**；反向边由调用方把点表反过来）。

    两端的端口**朝着链上的相邻站**开（见 `_port_faces`）。试过一次"给反向边换端口"
    就撤掉，结论是"几何本来就落在该落的那一侧" —— **那个结论错了**：当时量的是
    斜段和拐点，而真正的症状是**穿自己两端节点的盒子**，度量里根本没有这一项。
    改回按相邻站定方向之后，02-flow 的穿自己从 1 条降到 0。
    """
    pts: list[list[float]] = []
    last = len(chain) - 1
    for i, nid in enumerate(chain):
        p = placed[nid]
        cx, cy = p.x + p.width / 2, p.y + p.height / 2
        if i == 0:
            px, py = _port_faces(p, placed[chain[1]], direction) if last else (cx, cy)
            # 偏移量沿**所在的那条边**铺开（LR 的端口在左右面上 → 沿 y），
            # 不跟着面走的话，同一侧的边会全叠在中心线上。
            pts.append([px, py + start_off] if direction == "LR" else [px + start_off, py])
        elif i == last:
            px, py = _port_faces(p, placed[chain[-2]], direction) if last else (cx, cy)
            pts.append([px, py + end_off] if direction == "LR" else [px + end_off, py])
        else:
            pts.append([cx, cy])                    # 中间站（虚节点）取自身中心
    pts = [[round(x, 2), round(y, 2)] for x, y in pts]
    return _snap_ports(pts, chain, placed, direction)


PORT_SNAP_MARGIN = 8.0       # 端口对齐之后，落点离节点角至少留这么多（别贴到圆角上）


def _snap_ports(pts: list, chain: list[str], placed: dict[str, Placed],
                direction: str) -> list[list[float]]:
    """两端端口只差一点点时，把它们**并到同一列/行**上 —— 治「明明该直着下来却是歪的」。

    病根在 `_slots`：贴点偏移是**各自按自己节点的跨度**摊开的
    （LR 用 `height × ATTACH_SPAN`，TB 用 `width × ATTACH_SPAN`）。两端节点尺寸不同时，
    同一条边的离开点与到达点天然错开 —— 实测一份 TB 图里错开 23px。

    错开本身不是病（那是正常的一小折），要命的是它**刚好短于 EDGE_MIN**：
    正交候选里于是多出一段「毛刺」，而排序键当年把毛刺排在斜段**前面**，
    整条正交路径就这样输给一条两点斜线（实测 1475px，横穿整张图）。
    用户的原话：「不能像我一样，直接直直的下来吗」。

    所以这里只做一件事：`|错开| < EDGE_MIN` 时把到达点并到离开点那一列/行上，
    并保证它仍落在目标那一面内、离角至少 `PORT_SNAP_MARGIN`。并上之后
    正交路径里那段毛刺自然消失 —— 直的就真的直。

    **错开得多的（正常折线）一律不动**：那是画法，不是缺陷。
    """
    if len(pts) < 2:
        return pts
    axis = 1 if direction == "LR" else 0        # 交叉轴：LR 是 y，TB 是 x
    start, end = pts[0], pts[-1]
    if abs(end[axis] - start[axis]) >= EDGE_MIN:
        return pts                              # 本来就差得远或本来就齐：不动
    target = placed.get(chain[-1])
    if target is None:
        return pts
    if direction == "LR":
        low = target.y + PORT_SNAP_MARGIN
        high = target.y + target.height - PORT_SNAP_MARGIN
    else:
        low = target.x + PORT_SNAP_MARGIN
        high = target.x + target.width - PORT_SNAP_MARGIN
    if low > high:                              # 那一面比两个边距还窄：不硬对齐
        return pts
    aligned = round(min(max(start[axis], low), high), 2)
    if abs(aligned - start[axis]) >= EDGE_MIN:
        return pts                              # 对齐要求把落点挪出去太远：不做
    out = [list(p) for p in pts]
    out[-1][axis] = aligned
    return out



def _sample_points(a: list[float], b: list[float], step: float = 2.0):
    """线段上的采样点。间距取 2px —— 远小于最小间隙（12px），不会漏掉擦边的相交。"""
    span = math.dist(a, b)
    count = math.ceil(span / step) + 1
    return [(a[0] + (b[0] - a[0]) * i / count, a[1] + (b[1] - a[1]) * i / count)
            for i in range(count + 1)]


def _segment_hits_box(a: list[float], b: list[float], p: Placed,
                      pad: float = 0.0) -> bool:
    if not _segment_may_hit_box(a, b, p, pad):
        return False            # 精确否定：这一步不改结果，只省掉几百个采样点
    left, top = p.x - pad, p.y - pad
    right, bottom = p.x + p.width + pad, p.y + p.height + pad
    return any(left <= x <= right and top <= y <= bottom
               for x, y in _sample_points(a, b))


def _segment_may_hit_box(a: list[float], b: list[float], p: Placed,
                         pad: float = 0.0) -> bool:
    """纯加速用的**精确**排除测试（slab 法），不是第二个判据。

    它只做"提前否定"：说"不可能相交"时，采样版也一定找不到落进盒子的点
    （线段与矩形不相交 ⇒ 线段上的任何点都不在矩形内），所以 `_segment_hits_box`
    的结果一个字都不会变。说"可能"时仍旧走采样 —— **采样是权威口径**，
    绕行、校验、测试都用它，这里绝不另立一套几何判据（同一件几何算两遍必然漂移）。

    为什么要它：采样间距 2px，一条 900px 的弦会采出 452 个点，再对每个节点
    逐点做包含判断 —— 环内排序要跑几十个候选，光这一项就把搜索拖到 100ms。
    """
    left, top = p.x - pad, p.y - pad
    right, bottom = p.x + p.width + pad, p.y + p.height + pad
    low, high = 0.0, 1.0
    for delta, start, lo_bound, hi_bound in (
            (b[0] - a[0], a[0], left, right),
            (b[1] - a[1], a[1], top, bottom)):
        if abs(delta) < 1e-12:
            if start < lo_bound or start > hi_bound:
                return False        # 与这条板平行，且落在板外
            continue
        enter = (lo_bound - start) / delta
        leave = (hi_bound - start) / delta
        if enter > leave:
            enter, leave = leave, enter
        low = max(low, enter)
        high = min(high, leave)
        if low > high:
            return False
    return True


def _visible_nodes(placed: dict, exclude: set[str]):
    """图上真正看得见的节点。排除自己的两端与虚节点（虚节点只是路径上的拐点）。"""
    for nid, p in placed.items():
        if nid in exclude or nid.startswith(DUMMY_PREFIX):
            continue
        if p.width <= 0 or p.height <= 0:
            continue
        yield nid, p


def _blocking_nodes(pts: list, placed: dict, exclude: set[str],
                    pad: float = 0.0) -> list[tuple[int, str]]:
    """折线里“第几段穿过了哪个节点”，按段序返回。"""
    out: list[tuple[int, str]] = []
    for i, (a, b) in enumerate(zip(pts, pts[1:])):
        for nid, p in _visible_nodes(placed, exclude):
            if _segment_hits_box(a, b, p, pad):
                out.append((i, nid))
    return out


def nodes_hit_by_polyline(pts: list, placed: dict, exclude: set[str]) -> list[str]:
    """这条折线穿过了哪些**别的**节点（去重，按首次出现排序）。

    这是“连线是否穿过节点”的**唯一实现** —— 绕行逻辑、校验、测试都调它。
    同一件几何算两遍必然漂移，而漂移的那一份会让两边给出不同结论（这个坑踩过）。
    """
    seen: list[str] = []
    for _i, nid in _blocking_nodes(pts, placed, exclude):
        if nid not in seen:
            seen.append(nid)
    return seen


def _corner_routes(a: list[float], b: list[float], n: Placed,
                   clearance: float):
    """绕过节点 n 的候选路径，每次产出一对拐点。

    第一版写的是“把线段中点沿法线推开”，**不够**：推开的那条线会撞上邻居
    （实测 root→m5 的第一处试探就被 m1 挡住）。原因很直白 —— 单点偏移只是
    把线挪了一点，并没有让它“绕过这个盒子”。

    所以改成绕着盒子走：横向为主的线从盒子的上面或下面过，纵向为主的从左边或右边过。
    每侧给出两个拐点（进盒子前、出盒子后），四个候选按顺序试。
    """
    horizontal = abs(b[0] - a[0]) >= abs(b[1] - a[1])
    if horizontal:
        lanes = (n.y - clearance, n.y + n.height + clearance)
        for lane in lanes:
            first = [n.x - clearance, lane]
            second = [n.x + n.width + clearance, lane]
            yield (first, second) if a[0] <= b[0] else (second, first)
    else:
        lanes = (n.x - clearance, n.x + n.width + clearance)
        for lane in lanes:
            first = [lane, n.y - clearance]
            second = [lane, n.y + n.height + clearance]
            yield (first, second) if a[1] <= b[1] else (second, first)


def _try_detour(pts: list, i: int, blocked: str, placed: dict,
                exclude: set[str]) -> list[list[float]] | None:
    """让第 i 段绕过 `blocked`。四个候选都不行就返回 None（不硬拗）。

    判据用**带间隙**的版本（`NODE_CLEARANCE`）而不是“刚好不碰”：
    擦着节点 1px 过去虽然不算“穿过”，看起来一样难看。
    """
    a, b = pts[i], pts[i + 1]

    # 候选顺序是有实测依据的：先试“小幅推开”，再试“绕着盒子走”。
    # 反过来试过：大绕行会占掉别的边本来能用的空间，整体反而更差
    # （实测穿节点数 3/1 → 4/2）。所以**小动作优先**。
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length, dx / length
    mid = [(a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0]
    offset = DETOUR_STEP
    while offset <= DETOUR_MAX_OFFSET:
        for sign in (1.0, -1.0):
            trial = pts[:i] + [a, [mid[0] + nx * offset * sign,
                                   mid[1] + ny * offset * sign], b] + pts[i + 2:]
            if not _blocking_nodes(trial, placed, exclude, NODE_CLEARANCE):
                return trial
        offset += DETOUR_STEP

    for first, second in _corner_routes(a, b, placed[blocked], NODE_CLEARANCE):
        trial = pts[:i] + [a, first, second, b] + pts[i + 2:]
        if not _blocking_nodes(trial, placed, exclude, NODE_CLEARANCE):
            return trial
    return None


def _collinear(a: list, b: list, c: list, tolerance: float = 0.5) -> bool:
    """b 是不是落在 a→c 这条直线上（垂距 ≤ tolerance）。"""
    base = math.dist(a, c)
    if base < 1e-9:
        return True
    cross = abs((c[0] - a[0]) * (b[1] - a[1]) - (c[1] - a[1]) * (b[0] - a[0]))
    return cross / base <= tolerance


def _close_short_legs(pts: list, min_segment: float) -> list:
    """把过短的段**就地并掉** —— 不是删拐点（删拐点会把正交路径拉成斜线）。

    一段短的竖段（横段同理）连接的是两条**高度差几像素的水平走线**
    （实测：两个虚节点保留的行只差 3px）。把这两条走线并到同一条高度上，
    短段长度归零、两条走线共线并被合并 —— 路径全程仍然横平竖直。

    端点保护：只有在走线**确实包含端口**时才让端口参与位移，而且
    哪一侧包含端口就把新高度取成**另一侧的值**（端口因此一动不动）；
    两侧都是端口时取中点（位移 < EDGE_MIN/2，且 `_snap_ports` 已先处理过一遍）。

    为什么必须在这里做：排序键现在把斜段排在毛刺前面（斜段不可修复），
    于是带毛刺的正交路径会被选中 —— 毛刺就必须真的被消掉，不能靠「别选它」躲。
    消不掉（形状不是横平竖直）时**原样返回**：宁可让 `check_layout` 报一条
    「连线过短」，也不要为了一根 3px 的毛刺把整条线画成斜线。

    收敛：每轮要么删掉一个重点、要么把一段的长度归零（下一轮删掉它），
    所以点数单调下降；预算用完就放弃，不会死循环。
    """
    work = [list(p) for p in pts]
    budget = len(work) + 4
    while budget > 0:
        budget -= 1
        found = None
        for i, (a, b) in enumerate(zip(work, work[1:])):
            if math.dist(a, b) < min_segment:
                found = i
                break
        if found is None:
            return work
        a, b = work[found], work[found + 1]
        if math.dist(a, b) < 0.5:               # 已经完全重合：并点
            work.pop(found + 1)
            continue
        if abs(a[0] - b[0]) < 0.5:
            axis = 1                            # 竖段：动 y
        elif abs(a[1] - b[1]) < 0.5:
            axis = 0                            # 横段：动 x
        else:
            return [list(p) for p in pts]       # 斜的短段：不在这里处理
        # 两侧的走线：共享同一个坐标的连续点（含端点本身）
        left = found
        while left > 0 and abs(work[left - 1][axis] - a[axis]) < 0.5:
            left -= 1
        right = found + 1
        while right < len(work) - 1 and abs(work[right + 1][axis] - b[axis]) < 0.5:
            right += 1
        left_has_port = left == 0                # 走线里带着起点
        right_has_port = right == len(work) - 1  # 走线里带着终点
        if left_has_port and not right_has_port:
            target = a[axis]                     # 起点不动：另一侧并过来
        elif right_has_port and not left_has_port:
            target = b[axis]                     # 终点不动
        else:
            target = (a[axis] + b[axis]) / 2.0   # 两侧都是端口：各让一半
        for k in range(left, right + 1):
            work[k][axis] = target
    return [list(p) for p in pts]


def _simplify_path(pts: list, min_segment: float = EDGE_MIN) -> list:
    """去掉共线的中间点和过短的段。

    为什么必须有：车道候选会生出「横移 11px」这种几乎为零的拐角 —— 画出来是个
    小毛刺，而 `check_layout` 有可见长度下限（24px），一条这样的段会把整张图判红。
    短线不是几何错误，是视觉噪声：与其让检查去报它，不如生成时就不要它。

    两步，顺序不能反：
    1. `_close_short_legs` 先**并掉**短的段 —— 并是平移走线，路径仍然横平竖直。
    2. 再按下面的循环去共线点 / 去掉还剩的短拐点。

    只做第 2 步是不行的：它靠**删拐点**消短段，而删掉一个拐点就把正交路径
    拉成了斜线，于是函数末尾那条「不许引入斜段」的守卫又会把原本带毛刺的
    路径退回 —— 毛刺就这样留了下来，再被排序键罚成一条斜线（当时的排序键）。
    """
    if len(pts) <= 2:
        return [list(p) for p in pts]
    pts = _close_short_legs([list(p) for p in pts], min_segment)
    kept = [list(pts[0])]
    for point in pts[1:-1]:
        if math.dist(kept[-1], point) < min_segment:
            continue                        # 这一段太短：连这个拐点一起跳过
        if len(kept) >= 2 and _collinear(kept[-2], kept[-1], point):
            kept.pop()                      # 只是多了一个「结」，去掉它
        kept.append(list(point))
    tail = list(pts[-1])
    while len(kept) >= 2 and math.dist(kept[-1], tail) < min_segment:
        kept.pop()                          # 末段太短：把最后一个内点也去掉
    kept.append(tail)
    # **简化不许引入斜段**：正交路径的拐点被合并掉之后会变回一条斜线，
    # 而它仍然带着正交的档位标签 —— 实测这就是斜段占 20% 的来源
    # （两点路径的“偏离”恒为 0，度量也看不出来）。宁可不简化。
    if _is_slanted(kept) and not _is_slanted(pts):
        return [list(p) for p in pts]
    return kept


def _max_deviation(pts: list) -> float:
    """折点离「首尾直线」最远有多少像素。0 = 就是直线。"""
    a, b = pts[0], pts[-1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    span = math.hypot(dx, dy) or 1e-9
    return max((abs((q[0] - a[0]) * dy - (q[1] - a[1]) * dx) / span
                for q in pts[1:-1]), default=0.0)


ATTACH_STUB = 28.0        # 贴点先往外走这么长，再转向（必须 > EDGE_MIN，它是一段真线）


def _outward_normal(anchor: list, box) -> tuple[float, float] | None:
    """锚点贴在盒子的哪条边上 → 朝外的单位法线。认不出来就返回 None。"""
    if abs(anchor[0] - (box.x + box.width)) <= 1.5:
        return (1.0, 0.0)
    if abs(anchor[0] - box.x) <= 1.5:
        return (-1.0, 0.0)
    if abs(anchor[1] - (box.y + box.height)) <= 1.5:
        return (0.0, 1.0)
    if abs(anchor[1] - box.y) <= 1.5:
        return (0.0, -1.0)
    return None


def _crosses_own_nodes(pts: list, placed: dict, head_id: str, tail_id: str) -> bool:
    """路径是不是穿过了**它自己两端节点**的内部。

    `nodes_hit_by_polyline` 一向把两端节点排除掉（端点在边界上，贴着边不算撞），
    结果「从底边出来却往上走、整个人从盒子里穿过去」这种路一直是合法的。
    实测 scan→stage 就是这样：出口锚点在 scan 的**底边**，接着却往上走 74px
    穿回盒子里 —— 图上就是一条线从框里冒出来。

    判据：把两端盒子**往里收** 1px（免得把贴在边上的端点算成"在里面"），
    再看路径上的取样点有没有落在里面。
    """
    for node_id in (head_id, tail_id):
        box = placed.get(node_id)
        if box is None:
            continue
        x0, y0 = box.x + 1.0, box.y + 1.0
        x1, y1 = box.x + box.width - 1.0, box.y + box.height - 1.0
        for a, b in zip(pts, pts[1:]):
            for step in range(1, 9):
                t = step / 8.0
                x, y = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
                if x0 < x < x1 and y0 < y < y1:
                    return True
    return False


def _with_port_stubs(pts: list, placed: dict, head_id: str, tail_id: str) -> list:
    """**先往外走一点，再转向** —— 让连线不要顺着节点边框滑出去。

    用户的原话：「连线不要直接顺着节点的边框出去，先往外走一点，在向着原来的方向
    出去，不然会和边框融合，看着也难受」。

    做法：看第一段是不是**平行于锚点所在的那条边**（从底边出来却横着走 = 顺着边框）。
    是的话，沿法线插一段短出头（垂直于那条边），并把原第二点也推到同一条线上，
    保证插完每一段仍然是横或竖。入口端对称处理。

    两端各自用**自己那个节点**的盒子判（`head_id` / `tail_id` 由调用方给，
    不去从集合里猜 —— 集合没有顺序）。

    插完要**复核不穿节点**：出头是朝外的，正常会进空档，但密集图里可能擦到旁边的
    兄弟节点 —— 那种情况就不插（宁可贴着边框，也不能穿节点）。
    """
    out = [list(p) for p in pts]
    if len(out) < 2:
        return out
    for head, node_id in ((True, head_id), (False, tail_id)):
        box = placed.get(node_id)
        if box is None:
            continue
        anchor = out[0] if head else out[-1]
        neighbour = out[1] if head else out[-2]
        normal = _outward_normal(anchor, box)
        if normal is None:
            continue
        dx, dy = neighbour[0] - anchor[0], neighbour[1] - anchor[1]
        parallel = (abs(dx) < 0.5) if normal[0] != 0 else (abs(dy) < 0.5)
        if not parallel:
            continue
        stub = [anchor[0] + normal[0] * ATTACH_STUB, anchor[1] + normal[1] * ATTACH_STUB]
        moved = [neighbour[0], stub[1]] if normal[1] != 0 else [stub[0], neighbour[1]]
        trial = list(out)
        if head:
            trial[1] = moved
            trial.insert(1, stub)
        else:
            trial[-2] = moved
            trial.insert(len(trial) - 1, stub)
        if not nodes_hit_by_polyline(trial, placed, {head_id, tail_id}) \
                and not _crosses_own_nodes(trial, placed, head_id, tail_id):
            out = trial
    return _simplify_path(out)


def _is_slanted(pts: list) -> bool:
    """这条路径里有没有**斜段**（既不水平也不竖直）。"""
    for first, second in zip(pts, pts[1:]):
        if abs(second[0] - first[0]) > 0.5 and abs(second[1] - first[1]) > 0.5:
            return True
    return False


def _reversals(pts: list) -> int:
    """路径在两条轴上各“改了几次方向”。

    一条干净的路线（直线 / Z / 贴着车道绕）在两个轴上都**单调** —— 0 次。
    出去又回来的路（在图上就是绕着节点画了一个矩形框）会有 1~2 次。
    实测踩过：新路由在往回走的边上走出大矩形回路，看着像“容器边界” ——
    结构误读，比斜线糟糕得多；而当时的度量只数了 y 方向的往返，没抓到它。
    """
    total = 0
    for axis in (0, 1):
        values = [p[axis] for p in pts]
        signs = [1 if b > a + 1e-6 else (-1 if b < a - 1e-6 else 0)
                 for a, b in zip(values, values[1:])]
        signs = [s for s in signs if s]
        total += sum(1 for a, b in zip(signs, signs[1:]) if a != b)
    return total


def _path_rank(pts: list, tier: int) -> tuple:
    """候选路径的排序键。

    顺序：**斜段 → 主轴来回 → 毛刺段 → 形状档位 → 折点数 → 偏离 → 绕路比**。

    - 斜段是**用户明确不要的东西**（原话：“就是那种 90 度拐弯的线不行吗”）。
      它必须排在这里，而不是靠档位 —— 因为「简化」会把正交折线的拐点合并掉，
      让它变回一条两点斜线，而它仍然带着正交的档位标签。实测踩过：斜段因此
      占了全部连线长度的 20%，而两点路径的“偏离”恒为 0，用度量根本看不出来。
    - 主轴来回（走出去再走回来）也排在前面：它同样属于「结构上不该出现」，
      而且比多几个拐点难看得多 —— 看上去像给一组节点画了个框。
    - 毛刺段（短于可见下限）排第三。

    **为什么斜段必须排在毛刺前面**（这一条曾经写反，代价很大）：
    斜段**不可修复** —— 一条 1475px 的对角线只能重画；毛刺**可以就地修掉** ——
    十几像素的错位，`_close_short_legs` 一并就没了（端口错位那一路则由
    `_snap_ports` 提前消掉）。写反的后果是：正交路径里只要出现一段 3px
    （虚节点保留的两行只差 3px、或两端贴点差 23px），整条正交路径就被
    一条横穿全图的斜线压掉 —— 实测一份五层架构里有 7 条边这样变成斜线、
    合计 5886px，而且**校验全绿**（斜段当时不在检查项里）。
    用户的话：「为什么这么直着过去，这不对吧」。

    这三项都是「结构上不该出现」，所以排在审美档位前面；档位只在同类型之间分高下。
    """
    a, b = pts[0], pts[-1]
    span = math.hypot(b[0] - a[0], b[1] - a[1]) or 1e-9
    length = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    stub = 0 if all(math.dist(first, second) >= EDGE_MIN
                    for first, second in zip(pts, pts[1:])) else 1
    slanted = 1 if _is_slanted(pts) else 0
    # 主轴来回（走出去再走回来）也排在最前 —— 它同样属于「结构上不该出现」，
    # 而且比多几个拐点难看得多：看上去像给一组节点画了个框。
    zigzag = _reversals(pts)
    corners = max(0, len(pts) - 2)
    deviation = max((abs((q[0] - a[0]) * (b[1] - a[1]) - (q[1] - a[1]) * (b[0] - a[0])) / span
                     for q in pts[1:-1]), default=0.0)
    return (slanted, zigzag, stub, tier, corners, round(deviation, 2),
            round(length / span, 3))


def _align_spine(placed: dict, edges: list, direction: str) -> int:
    """把主轴上的链**拉直** —— 治「竖着那半段中心点对不上」。

    实测（一份竖版流程，13 节点）：主轴中心从 `build` 的 422 漂到 `profile` 的 362，
    之后的 `forbid / probe / req / degraded` 全继承了这 60px 偏移。原因很直白：
    `profile` 有**两个**父节点（mem / prod 分叉），它的位置取的是两者的平均 ——
    而不是**分叉点自己的正下方**。

    两条规则，都是从结构上看得出来的：

    1. **菱形汇合点对齐分叉点**：一个节点的全部父节点如果只有同一个父节点（那就是分叉），
       它就站到分叉点的中心线下 —— 主流程直着往下，分支挂在两侧。
    2. **单入单出的节点对齐邻居**：链上的节点站到上下游中心的中点。

    只动**交叉轴**（TB 动 x、LR 动 y），而且**先量再挪**：挪完若与同层邻居的间隙
    小于 NODE_CLEARANCE 就放弃这次对齐（宁可歪，不要叠）。返回实际挪动的节点数。
    """
    parents: dict[str, list[str]] = {}
    children: dict[str, list[str]] = {}
    for e in edges:
        parents.setdefault(e["to"], []).append(e["from"])
        children.setdefault(e["from"], []).append(e["to"])

    def centre(nid: str) -> float:
        q = placed[nid]
        return (q.x + q.width / 2) if direction == "TB" else (q.y + q.height / 2)

    def cross_size(nid: str) -> float:
        q = placed[nid]
        return q.width if direction == "TB" else q.height

    def sibling_gap(nid: str, target: float) -> float:
        """把这个节点挪到 target 之后，它和同层邻居的最小间隙。"""
        me = placed[nid]
        half = cross_size(nid) / 2
        best = math.inf
        for other, q in placed.items():
            if other == nid or q.rank != me.rank or other.startswith(DUMMY_PREFIX):
                continue
            other_centre = (q.x + q.width / 2) if direction == "TB" else (q.y + q.height / 2)
            best = min(best, abs(target - other_centre) - half - cross_size(other) / 2)
        return best

    # 走到每个节点可达的节点数 —— 分叉时用它认「主线」是哪一支：
    # 父节点有多个孩子时，只把子树最大的那支拉直，其余当分支挂在侧面
    # （这正是人画流程图的习惯：主流程直着往下，错误分支甩到一边）。
    def subtree_size(start: str) -> int:
        seen: set[str] = set()
        stack = [start]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(children.get(cur, []))
        return len(seen)

    main_child: dict[str, str] = {}
    for parent, kids in children.items():
        if len(kids) == 1:
            main_child[parent] = kids[0]
        else:
            main_child[parent] = max(kids, key=lambda k: (subtree_size(k), -kids.index(k)))

    def rank_gaps_ok(rank: int) -> bool:
        """这一层里任意两个真节点的间隙都不小于 NODE_CLEARANCE。"""
        items = [p for n, p in placed.items()
                 if p.rank == rank and not n.startswith(DUMMY_PREFIX)]
        for i, a in enumerate(items):
            for b in items[i + 1:]:
                gap = (abs((a.x + a.width / 2) - (b.x + b.width / 2)) - a.width / 2 - b.width / 2
                       if direction == "TB" else
                       abs((a.y + a.height / 2) - (b.y + b.height / 2)) - a.height / 2 - b.height / 2)
                if gap < NODE_CLEARANCE - 0.01:
                    return False
        return True

    def push_aside(nid: str, target: float, touched: dict) -> bool:
        """把挡住 nid 归位的同层邻居沿交叉轴往外推，腾出 NODE_CLEARANCE 的间隙。

        推的是**位置**，不改任何结构；推完立刻用同一个 `sibling_gap` 复核被推的那个
        节点 —— 它自己要是因此挤到第三个节点，这次推就作废（返回 False）。
        """
        me = placed[nid]
        half = cross_size(nid) / 2
        for other, q in placed.items():
            if other == nid or q.rank != me.rank or other.startswith(DUMMY_PREFIX):
                continue
            other_centre = (q.x + q.width / 2) if direction == "TB" else (q.y + q.height / 2)
            gap = abs(target - other_centre) - half - cross_size(other) / 2
            if gap >= NODE_CLEARANCE:
                continue
            away = 1.0 if other_centre >= target else -1.0
            new_centre = other_centre + away * (NODE_CLEARANCE - gap + 1.0)
            if sibling_gap(other, new_centre) < NODE_CLEARANCE:
                return False                    # 推它会挤到第三个 —— 那就不推
            touched.setdefault(other, q)
            if direction == "TB":
                placed[other] = replace(q, x=new_centre - q.width / 2)
            else:
                placed[other] = replace(q, y=new_centre - q.height / 2)
        return True

    moved = 0
    for _round in range(6):                     # 让对齐沿着链往下传
        changed = 0
        for nid in list(placed):
            if nid.startswith(DUMMY_PREFIX):
                continue
            ins, outs = parents.get(nid, []), children.get(nid, [])
            target = None
            if len(ins) >= 2:
                # 菱形汇合：全部父节点共用一个祖父 → 站到分叉点的中心线下
                grandparents = {g for parent in ins for g in parents.get(parent, [])}
                if len(grandparents) == 1:
                    target = centre(next(iter(grandparents)))
            elif len(ins) == 1 and main_child.get(ins[0]) == nid:
                # 主线的一环：站到**父节点**的正下方（不是和邻居取平均 ——
                # 要的是「继承主线」，不是「把弯抹平」）。
                target = centre(ins[0])
            if target is None or abs(target - centre(nid)) < 1.0:
                continue
            # 记下这次要动的对象（含可能被推开的分支）—— 动完复核整层，不行就整体回滚。
            # 第一版只检查了“被推的那个”与**当时**的位置，nid 还没过去 —— 于是推完
            # 再挪过去就叠在一起了（实测：四对节点间隙 0px，整张图判红）。
            touched: dict[str, "Placed"] = {}
            if sibling_gap(nid, target) < NODE_CLEARANCE:
                # 会挤到邻居。但这个邻居**本来就是分支** —— 主线归位时把它往外推一次
                # （只推一次、不级联）。实测：竖版流程里 `opt` 是 412px 宽的菱形，
                # 它要归位就被右边的 `stop` 挡住，而 `stop` 正是那条“是 → 拒绝启动”
                # 的分支，本来就该往外站。
                if not push_aside(nid, target, touched):
                    continue                    # 推不动 —— 宁可歪着
            node = placed[nid]
            touched[nid] = node
            # `Placed` 是 frozen 的 —— 换一个对象写回字典（字典本身是共享的可变对象，
            # 所以 route_edges 之外的布局结果也能看到新位置）。
            placed[nid] = (replace(node, x=target - node.width / 2) if direction == "TB"
                           else replace(node, y=target - node.height / 2))
            if not rank_gaps_ok(placed[nid].rank):
                for key, old_value in touched.items():
                    placed[key] = old_value     # 回滚：宁可歪着，不要叠
                continue
            changed += 1
            moved += 1
        if not changed:
            break
    return moved


def _rank_gaps(placed: dict, direction: str) -> dict[int, float]:
    """相邻两层之间的**空档**坐标（LR 是 x，TB 是 y）。

    为什么必须有它：虚节点坐的是**层内的列**，不是层与层之间的空档 —— 沿虚节点的 x
    走竖段，就会穿过它所在的那一列。实测（04-state）：`paid→refunding` 的所有正交候选
    都被挡住，退回一条 1128px 的斜线，一条边就占了整张图斜段的一半。

    空档的性质正好相反：两列之间那 120px（rankSeparation）里，**整条高度**都是空的。
    所以规矩是：**竖段走空档，横段走虚节点保留的行**。
    键是空档**下面/左侧**那一层的 rank；两层之间没有更高的层时不出现在表里。
    """
    by_rank: dict[int, list] = {}
    for nid, node in placed.items():
        if nid.startswith(DUMMY_PREFIX):
            continue
        by_rank.setdefault(node.rank, []).append(node)
    gaps: dict[int, float] = {}
    ranks = sorted(by_rank)
    for lower, upper in zip(ranks, ranks[1:]):
        if direction == "LR":
            right = max(node.x + node.width for node in by_rank[lower])
            left = min(node.x for node in by_rank[upper])
            gaps[lower] = (right + left) / 2
        else:
            bottom = max(node.y + node.height for node in by_rank[lower])
            top = min(node.y for node in by_rank[upper])
            gaps[lower] = (bottom + top) / 2
    return gaps


def _orthogonal_path(a: list, b: list, waypoints: list, direction: str,
                     gaps: dict[int, float], start_rank: int, end_rank: int) -> list[list[float]]:
    """走出只含**横段与竖段**的路径。

    规矩（都是从实测的“钩子”和“斜段”里总结的）：

    1. **竖段走层间空档**（LR）/ **横段走层间空档**（TB）—— 空档里整条高度都是空的，
       走在里面不可能撞到节点。**不要走虚节点那一列**：虚节点坐的是层内的列，
       沿它走等于横穿那一层（实测就是这么退回斜线的）。
    2. **另一条腿走虚节点保留的行** —— 虚节点是分层布局为长边留的空位，
       它所在的行在它穿过的列里是空的。
    3. **先沿主轴走**：LR 先横、TB 先竖 —— 反过来等于一出来就横穿自己那一层。

    背景：斜段曾占全部连线长度的 49.5%；用户的原话是「就是那种 90 度拐弯的线不行吗」。
    """
    lanes = [gaps[r] for r in sorted(gaps) if start_rank <= r < end_rank]
    pts: list[list[float]] = [list(a)]
    if direction == "LR":
        row = a[1]
        for index, (x, y) in enumerate(waypoints):
            lane = lanes[min(index, len(lanes) - 1)] if lanes else (a[0] + b[0]) / 2
            pts.append([lane, row])            # 横段：走到这一站前面的空档
            pts.append([lane, y])              # 竖段：在空档里换到它的行
            pts.append([x, y])                 # 横段：沿它保留的行穿过那一层
            row = y
        lane = lanes[-1] if lanes else (a[0] + b[0]) / 2
        pts.append([lane, row])                # 横段：回到空档
        pts.append([lane, b[1]])               # 竖段：在空档里换到目标的行
        pts.append(list(b))                    # 横段：从空档进目标
    else:
        column = a[0]
        for index, (x, y) in enumerate(waypoints):
            lane = lanes[min(index, len(lanes) - 1)] if lanes else (a[1] + b[1]) / 2
            pts.append([column, lane])         # 竖段：走到这一站前面的空档
            pts.append([x, lane])              # 横段：在空档里换到它的列
            pts.append([x, y])                 # 竖段：沿它保留的列穿过那一层
            column = x
        lane = lanes[-1] if lanes else (a[1] + b[1]) / 2
        pts.append([column, lane])             # 竖段：回到空档
        pts.append([b[0], lane])               # 横段：在空档里换到目标的列
        pts.append(list(b))                    # 竖段：从空档进目标
    # **去掉连续重复点**：拐点正好落在空档上时会出现零长度的段（实测 order→db 就有
    # `(1304,296) → (1304,296)`）。它不只是难看 —— 排序键的第一项"毛刺数"会把这种
    # 段算进去，于是一条**来回 0** 的候选被一条来回 1 的压住，修好的路永远选不上。
    # `wrap_route` 早就因为同一件事手工去过重复点，这里也得做。
    deduped = [pts[0]]
    for point in pts[1:]:
        if point != deduped[-1]:
            deduped.append(point)
    return _simplify_path(deduped)


def _lane_candidates(a: list[float], b: list[float], placed: dict,
                     exclude: set[str]) -> list[list[list[float]]]:
    """绕过**一整列节点**的候选：让开、贴着走、再回来。

    单个中间点推不开一整列节点（实测：跨 7 层的边被 6 个节点排成一列挡住，
    偏移梯度扫到上限也过不去），绕盒子那四个候选也只管一个盒子。人画这种线的方式
    就是“先横着让开一条车道，直着走到位置，最后再横回来”。

    给两种画法，都贴在障碍整体包围盒的外侧（贴着障碍走，不是跑到画布边缘）：

    - **4 点**：横移段就走在 a/b 的高度上。最省，但那条横移线常常穿过别的节点
      （实测过：一列节点打横排开时它一定过不去）。
    - **6 点**：横移段挪到障碍上下两侧的走廊（包围盒外），中间那段沿车道直走。
      多一点折点，但连接段不会横穿障碍 —— 这是真绕得过去的那种。

    两种都交给调用方按档位比，不在这里替它选。
    """
    blockers = [p for nid, p in _visible_nodes(placed, exclude)
                if _segment_hits_box(a, b, p, NODE_CLEARANCE)]
    if not blockers:
        return []
    left = min(p.x for p in blockers) - NODE_CLEARANCE
    right = max(p.x + p.width for p in blockers) + NODE_CLEARANCE
    top = min(p.y for p in blockers) - NODE_CLEARANCE
    bottom = max(p.y + p.height for p in blockers) + NODE_CLEARANCE
    out: list[list[list[float]]] = []
    if abs(b[1] - a[1]) >= abs(b[0] - a[0]):        # 竖向为主：左右让车道
        for lane in (left, right):
            out.append([list(a), [lane, a[1]], [lane, b[1]], list(b)])
        for lane in (left, right):
            out.append([list(a), [a[0], top], [lane, top],
                        [lane, bottom], [b[0], bottom], list(b)])
    else:                                            # 横向为主：上下让车道
        for lane in (top, bottom):
            out.append([list(a), [a[0], lane], [b[0], lane], list(b)])
        for lane in (top, bottom):
            out.append([list(a), [left, a[1]], [left, lane],
                        [right, lane], [right, b[1]], list(b)])
    return out


def straighten(pts: list, placed: dict, exclude: set[str],
               orthogonals: list | None = None,
               endpoints: tuple[str, str] = ("", "")) -> list[list[float]]:
    """把一条边**能直就直、要弯就最小弯**。

    为什么必须有这一遍：跨层的边在分层算法里是被**虚节点**牵着走的 —— 虚节点的 x
    由「层内排序（减少交叉）」决定，它不管这条边离首尾两点的直线差多远。于是一条
    跨 7 层的边会在每一层的车道上各横移一次：实测偏离直线 **324px**、六个折点；
    而它真正需要做的，只是让开、直着走、再回来（三个折点）。

    候选四类（各自带档位，见 `_path_rank`）：
      ① 首尾直线（两点）
      ② 把直线交给 `avoid_nodes`：小幅推开 / 绕盒子走 —— 推得太远就不算「小动作」，
         直接降到第 3 档（那种 V 形实测比贴着走更乱）
      ③ 贴车道：绕过挡路的**整列**节点
      ④ 原路径（虚节点车道）
    先用「不许穿节点」过滤，再按档位与折点数挑。**不会让任何一条边新穿过节点**：
    穿节点的候选直接出局，而那条判据只有一份实现（`nodes_hit_by_polyline`）。
    """
    if len(pts) < 2:
        return [[round(x, 2), round(y, 2)] for x, y in pts]
    straight = [list(pts[0]), list(pts[-1])]
    pushed = avoid_nodes(straight, placed, exclude)
    candidates: list[tuple[int, list]] = []
    # 档 0：**轴向**直线（同一行的两点）—— 既直又正交，最好
    if abs(straight[0][1] - straight[1][1]) < 0.5 or abs(straight[0][0] - straight[1][0]) < 0.5:
        candidates.append((0, straight))
    # 档 1：正交路径（只走横竖段，拐点落在虚节点预留的行/列上）。
    # 可以给多条（比如“原样”和“丢掉跨度外的行”两条），交给排序键挑。
    for orthogonal in (orthogonals or []):
        candidates.append((1, orthogonal))
    # 档 2：小动作推开 / 贴着障碍走车道（两者都是轴对齐的）
    candidates.append((2 if _max_deviation(pushed) <= SMALL_DODGE else 4, pushed))
    candidates += [(3, lane) for lane in _lane_candidates(straight[0], straight[1],
                                                          placed, exclude)]
    # 档 4：斜的直线弦，档 5：原来的虚节点车道 —— 只在正交都不可行时才用
    candidates.append((4, straight))
    candidates.append((5, pts))
    viable = []
    for tier, path in candidates:
        if nodes_hit_by_polyline(path, placed, exclude):
            continue
        # **每个**候选都先简化一遍 —— 只简化最后选中的那个是不够的：
        # 简化会挪动拐点，可能挪进节点，于是那一份不可用，而「不可用就退回未简化的」
        # 会把带毛刺的原样留下（实测 A→D 就留了一段 3px，用例抓到的）。
        simple = _simplify_path(path)
        candidate = simple if not nodes_hit_by_polyline(simple, placed, exclude) else path
        # 穿过自己两端节点的内部 → 直接不用这个候选（见 _crosses_own_nodes）
        if _crosses_own_nodes(candidate, placed, *endpoints):
            continue
        viable.append((tier, candidate))
    if not viable:
        return [[round(x, 2), round(y, 2)] for x, y in pts]

    _tier, best = min(viable, key=lambda item: _path_rank(item[1], item[0]))
    best = _with_port_stubs(best, placed, *endpoints)
    return [[round(x, 2), round(y, 2)] for x, y in best]


def avoid_nodes(pts: list, placed: dict, exclude: set[str]) -> list[list[float]]:
    """把挡路的线段推开 —— 连线不该穿过别的节点（P2 / P10）。

    做法跟标签定位同一套思路：**不靠一个魔法偏移量，而是试探一个偏移阶梯，
    取第一个真的把障碍绕开的**。区别是这里改的是线本身。

    为什么必须由脚本做：这是纯几何判断（线段与矩形是否相交），而模型看不到坐标 ——
    让它“注意别穿过节点”只能靠猜，正是这个 skill 一开始要避免的事。

    推不出去（试完阶梯还是撞）就**原样返回**，不硬拗：病态图里无限推比不推更糟。
    剩下的那几处由 `check_layout` 报出来，报告给内容级的建议（拆节点 / 换方向）。

    只在**段中点**插一个拐点。这不是通用寻路（不会绕三个节点），但对
    “一条边恰好压过中间某个节点”这种实际形态够用 —— 也正因为够用，
    它不需要引入一个真正的路由引擎。
    """
    pts = [list(p) for p in pts]
    for _round in range(DETOUR_ROUNDS):
        blocked = _blocking_nodes(pts, placed, exclude)
        if not blocked:
            break
        seg_index, blocked_node = blocked[0]
        moved = _try_detour(pts, seg_index, blocked_node, placed, exclude)
        if moved is None:
            break
        pts = moved
    return [[round(x, 2), round(y, 2)] for x, y in pts]


# ── 主入口 ──────────────────────────────────────────────────
def wrap_route(a: Placed, b: Placed, band: float, lane: float,
               direction: str) -> list[list[float]]:
    """跨段连线的走法：出源节点 → **先沿主轴绕到本层外缘之外** → 沿交叉轴进空档 →
    沿主轴走到目标那一层 → 进目标。

    五个坑，全是实测踩出来的：

    1. **不能直连**。直连是从一栏的末尾斜拉到另一栏的开头，横穿两栏 ——
       实测 `02-flow` 的 `scan → stage` 撞掉 2 个节点（`cache`、`gate`）。
    2. **也不能顺着"出源节点后直接走交叉轴"**。TB 下这招碰巧能用（层是横排，
       从源节点下方走出去天然是空的），**LR 下必撞** —— 层是竖列，源节点正下方
       往往就站着同列的下一个节点。实测 `04-state` 的 `paid → refunding`
       就这么撞上了 `cancelled`。
    3. 所以第一步必须是**沿主轴**绕到本层外缘之外那条通道（`lane`），再拐。
    4. 出入口的**面**不能写死。原先写死"底边中点进、上边中点出"，只在
       "rank 一路往下"时才成立；02-flow 的 rank 轴是反的，于是出口开在背对通道的
       那一面 —— 线从源节点的**盒子里面**穿了出去（图上就是线从框里冒出来）。
       现在按**通道在节点的哪一侧**定面（和 `_port_faces` 一个道理）。
    5. 入口那一面要**对着通道（band）**，不能对着上/下边 —— 否则最后一段是横着
       **贴着目标的上边框**滑进去的（用户原话："会和边框融合，看着也难受"）。

    `lane` 由调用方按源节点所在层的实际外缘算出（主轴方向）。
    """
    if direction == "TB":
        # 出口朝着通道那一侧（通道在节点上方就从顶边出）
        start = ([a.x + a.width / 2.0, a.y] if lane < a.y
                 else [a.x + a.width / 2.0, a.y + a.height])
        # 入口朝着 band 那一侧 —— 最后一段是**横**着进去，垂直于左右边
        end = ([b.x, b.y + b.height / 2.0] if band < b.x + b.width / 2.0
               else [b.x + b.width, b.y + b.height / 2.0])
        pts = [start, [start[0], lane], [band, lane], [band, end[1]], end]
    else:
        start = ([a.x, a.y + a.height / 2.0] if lane < a.x
                 else [a.x + a.width, a.y + a.height / 2.0])
        end = ([b.x + b.width / 2.0, b.y] if band < b.y + b.height / 2.0
               else [b.x + b.width / 2.0, b.y + b.height])
        pts = [start, [lane, start[1]], [lane, band], [end[0], band], end]
    # 各段宽度相同时，中间两个拐点会落在同一个位置 —— 那一段长度是 0，
    # 会被"最短连线"校验判成 0px。去掉重复点（保留首尾）。
    out = [pts[0]]
    for point in pts[1:]:
        if point != out[-1]:
            out.append(point)
    return out



def layout(spec: dict, boxes: dict[str, Box],
           params: dict[str, float] | None = None) -> LayoutResult:
    p = dict(DEFAULT_PARAMS)
    p.update(params or {})
    # spec 是外部 JSON，字段可能缺、可能是 null；先收成 str 再当 dict 的键。
    declared = spec.get("direction")
    spec_type = spec.get("type")
    direction = (str(declared) if declared
                 else DIRECTION_FOR_TYPE.get(str(spec_type or ""), "LR"))

    nodes = spec.get("nodes", [])
    node_ids = [n["id"] for n in nodes]
    edges = [{"from": e["from"], "to": e["to"], "label": e.get("label"),
              "kind": e.get("kind")} for e in (spec.get("edges") or [])]
    pins = {n["id"]: n["pin"] for n in nodes if n.get("pin")}
    explicit = {n["id"]: n["rank"] for n in nodes if n.get("rank") is not None}

    # ── 策略分发：思维导图走**径向**（中心辐射），其余走分层 ──
    # 放在这里、在任何分层计算之前：径向不需要 rank / dummy / 层内排序那一整套，
    # 但**共用**边路径的绕行与所有几何校验（它们只看坐标，与布局方式无关）。
    if str(spec_type or "") == "mindmap" and len(node_ids) >= 2:
        placed, depth, order, routed = radial_layout(node_ids, boxes, edges)
        if placed:
            crossings = geometric_crossing_pairs(routed)
            return LayoutResult(
                direction="RADIAL", params=p, ranks=depth, order=order,
                placed=placed, edges=routed,
                crossings=len(crossings), crossing_origins=crossings,
                dummy_count=0, reversed_edges=[], pin_conflicts=[])

    # 网状图走**力导向**（没有天然层级，分层会把它拉成一条长条）
    if str(spec_type or "") == "network" and len(node_ids) >= 2:
        placed, depth, order, routed = force_layout(node_ids, boxes, edges, p)
        if placed:
            crossings = geometric_crossing_pairs(routed)
            return LayoutResult(
                direction="FORCE", params=p, ranks=depth, order=order,
                placed=placed, edges=routed,
                crossings=len(crossings), crossing_origins=crossings,
                dummy_count=0, reversed_edges=[], pin_conflicts=[])

    dag, reversed_edges = break_cycles(node_ids, edges)
    ranks = assign_ranks(node_ids, dag, explicit)
    ranks, pin_conflicts = apply_axis_pins(ranks, pins, direction, dag)
    ranks, segments, origins, dummy_ids = insert_dummies(ranks, dag)

    order, _ = order_layers(ranks, segments, node_ids + dummy_ids,
                            p["barycenterRounds"])
    order = apply_cross_axis_pins(order, ranks, pins, direction)
    # pin 会改动层内顺序，所以交叉数必须**在 pin 之后**重算 ——
    # 报一个 pin 之前的数，等于报告里的指标和实际的图对不上。
    pairs = crossing_pairs(order, segments)
    crossings = len(pairs)

    all_boxes = dict(boxes)
    for n in dummy_ids:
        all_boxes.setdefault(n, Box(0.0, 0.0))

    # 节点 → 区域（只喂给折段：折点要避开区域边界，见 assign_coordinates）
    groups_of = {node["id"]: node["group"] for node in spec.get("nodes", [])
                 if isinstance(node, dict) and node.get("group")}
    coords = assign_coordinates(order, all_boxes, direction,
                                p["nodeSeparation"], p["rankSeparation"],
                                groups_of=groups_of)
    placed = coords.placed
    # 主轴拉直是一把双刃剑：它让主流程直着走，但也可能把某条边推到别的节点上。
    # **两种都算，挑更干净的** —— 判据是「连线穿节点的处数」，同分时留着拉直版
    # （那是用户明确要的直）。这跟径向那次「只在遮挡真的变少时才换顺序」是同一套路：
    # 用一个能量出来的指标决定要不要接受一次“看起来更好”的调整。
    def quality(routed_edges: list, table: dict) -> tuple:
        """评价一次路由：穿节点 → 穿自己 → 贴边滑 → 斜段占比。

        只卡穿节点是不够的 —— 对齐之后有些边的正交候选会被节点挡住，于是退回斜的直线弦。
        实测：五层架构那张在“只卡穿节点”时选了拉直版，斜段从 0% 涨到 20.6%。
        斜段是用户明确不要的东西，所以它也得进判据（同分时留拉直版 —— 那是要的直）。
        """
        hit = sum(len(nodes_hit_by_polyline(e["points"], table, {e["from"], e["to"]}))
                  for e in routed_edges)
        # 「穿自己」和「贴边滑」以前**不在判据里**，所以拉直版把它们带出来也没人管：
        # 02-flow 就是这样 —— 一条边从源的底边出去却往上走，整条线穿过自己的盒子
        # （图上就是线从框里冒出来），入口还贴着上边框滑进去（用户说"会和边框融合"）。
        # 这两项现在参与挑版，和斜段一样属于"结构上不该出现"。
        own = sum(1 for e in routed_edges
                  if _crosses_own_nodes(e["points"], table, e["from"], e["to"]))
        slide = 0
        for e in routed_edges:
            pts = e["points"]
            if len(pts) < 2:
                continue
            for anchor, neighbour, nid in ((pts[0], pts[1], e["from"]),
                                           (pts[-1], pts[-2], e["to"])):
                box = table.get(nid)
                normal = _outward_normal(anchor, box) if box is not None else None
                if normal is None:
                    continue
                dx, dy = neighbour[0] - anchor[0], neighbour[1] - anchor[1]
                if (abs(dx) < 0.5) if normal[0] != 0 else (abs(dy) < 0.5):
                    slide += 1
        diagonal = total = 0.0
        for e in routed_edges:
            for a, b in zip(e["points"], e["points"][1:]):
                dx, dy = abs(b[0] - a[0]), abs(b[1] - a[1])
                length = math.hypot(dx, dy)
                total += length
                if dx > 0.5 and dy > 0.5:
                    diagonal += length
        return (hit, own, slide, round(diagonal / total, 3) if total else 0.0)

    plain_table = dict(placed)
    plain_routed = route_edges(origins, segments, plain_table, direction,
                               set(reversed_edges), align=False)
    aligned_table = dict(placed)
    aligned_routed = route_edges(origins, segments, aligned_table, direction,
                                 set(reversed_edges), align=True)
    if quality(aligned_routed, aligned_table) <= quality(plain_routed, plain_table):
        placed, routed = aligned_table, aligned_routed
    else:
        placed, routed = plain_table, plain_routed
    # 折段之后，两端落在不同段的连线改走空档 —— 直连会横穿两栏。
    if coords.bands:
        lane_uses: dict[float, int] = {}
        for e in routed:
            sa = coords.segments.get(placed[e["from"]].rank) if e["from"] in placed else None
            sb = coords.segments.get(placed[e["to"]].rank) if e["to"] in placed else None
            if sa is None or sb is None or sa == sb:
                continue
            pa = placed[e["from"]]
            pb = placed[e["to"]]
            # 通道放在**源节点那一层的外缘之外**（主轴方向），不是源节点自己的中线 ——
            # 同层里源节点旁边/下面可能还站着别的节点。留 30px 余量。
            peers = [q for q in placed.values() if q.rank == pa.rank]
            # 目标在哪一侧就往哪一侧绕，别绕反了。
            if direction == "TB":
                far = max(q.y + q.height for q in peers) + 30.0
                near = min(q.y for q in peers) - 30.0
                lane = far if pb.y >= pa.y else near
            else:
                far = max(q.x + q.width for q in peers) + 30.0
                near = min(q.x for q in peers) - 30.0
                lane = far if pb.x >= pa.x else near
            band = coords.bands[min(sa, sb)]
            # **分车道**：同一个空档里已经走过 n 条边，就往外让 n 个步长 ——
            # 否则两条边会精确重叠，图上看起来是一根线（实测踩过）。
            used = lane_uses.get(band, 0)
            lane_uses[band] = used + 1
            # **对称往两边散**（-1、+1、-2、+2…），不是一路往右挤 ——
            # 空档本来就夹在左右两块之间，只往一边让会把后面那条挤到右边那块身上去。
            offset = WRAP_LANE_STEP * (used // 2 + 1) * (-1 if used % 2 == 0 else 1)
            e["points"] = wrap_route(pa, placed[e["to"]], band + offset, lane, direction)

    # 最后一道：**把叠在同一条线上的段错开**（见 `_spread_lanes`）。
    # 必须放在**折段那一块之后** —— 跨栏连线的走法是那里才定下来的，
    # 早一步做就等于对着一份还没成形的点表算（02-flow 的 `scan→stage` 就是这样漏掉的：
    # `route_edges` 里它还是一根两点斜线，折段回来后才是最终那个五折点路径）。
    # 也只在这里做：重叠是**边与边之间**的事，单看一条边永远看不出来。
    _spread_lanes(routed, placed, direction)

    return LayoutResult(direction=direction, params=p, ranks=ranks, order=order,
                        placed=placed, edges=routed, crossings=crossings,
                        crossing_origins=[[x["origin"], y["origin"]] for x, y in pairs],
                        dummy_count=len(dummy_ids), reversed_edges=reversed_edges,
                        pin_conflicts=pin_conflicts)


@dataclass(frozen=True)
class NodeBox:
    """一个节点的**形状包围盒** + 里面的文字信息。

    为什么要两个：
    - 布局与间隙只看**包围盒**（菱形比它的文字大得多，间隙得按菱形算）
    - 落笔要看**文字**（断行结果与字号）

    为什么不在 TextBox 上直接改宽高：那只会在一个对象上混两套含义，
    而且 TextBox 是 frozen 的、它声称的就是文字尺寸。
    """

    id: str
    shape: str
    width: float
    height: float
    text: Any          # text_metrics.TextBox




REGION_PAD = 26.0        # 区域边框到成员节点的距离
# 区域标题的字号：比节点标题（16）大一步 —— 参考图里它就是整块区域的名字。
REGION_LABEL_SIZE = 20.0
REGION_LABEL_TOP = 10.0      # 标题离区域顶边的距离
REGION_LABEL_GAP = 5.0       # 标题块与成员节点之间至少留的空
# 标题离左右边框至少留这么多 —— 与 `emit._region_label_x` 里挑位用的 8px 是同一个数
REGION_LABEL_MARGIN = 8.0
# 单行标题时占的高度。**它就是下面那个和**（10 + 20×1.25 + 5 = 40），
# 由 `test_region_head_matches_the_single_line_band` 钉住 —— 两处各写一个数迟早会漂。
# 多行时的高度**逐区域由断行结果算**（见 `region_boxes`），不是这个常数。
REGION_HEAD = 40.0
# 标题最多断成几行。**这是判断，不是推导**：标题带是为了让区域有个名字，
# 不是拿来放一段话的。超过就报告建议缩短 —— 与节点那边
# 「标签超过最大断行档位就判失败」是同一类内容级问题。
REGION_TITLE_MAX_LINES = 2
REGION_MIN_GAP = 18.0    # 两个区域贴在一起时至少留这么多


def region_label_lines(label: str, width: float) -> tuple[list[str], float]:
    """把区域标题**断到区域的宽度里**。返回 `(行, 最宽一行的像素宽)`。

    尺寸链和节点是同一套，只是两端互换：
      区域宽度（由成员节点定）→ 断行 → 行数 → **标题带高度**

    反过来（先给标题带一个固定高度，再让文字去挤那个宽度）就是用户报的那个 bug：
    实测一个 368px 的标题画在 324px 的可用宽度里，两头各冒出去 22px，
    而当时的九项校验里**没有一项在量区域标题** —— 标题宽度压根没进过任何尺寸链。
    """
    if not label:
        return [], 0.0
    # 下限 1 个单位：区域比一个字还窄时也不让断行退化成死循环
    max_units = max(1.0, (width - 2 * REGION_LABEL_MARGIN) / REGION_LABEL_SIZE)
    lines, _forced = _tm.wrap(label, max_units)
    # 行数定下来之后，在**同一行数**里挑最均衡的一版。
    # 贪心断行会把最后一行剩下一两个字（实测 "…× 执行 × 物 / 化对齐"），
    # 而把断行宽度收窄一档就能断在空格上（"三真源：完成 = 期望 / × 执行 × 物化对齐"）。
    # 必须卡死**行数不变** —— 否则"最窄"这个目标会把它断成四行。
    count = len(lines)
    widest = max(_tm.weighted_units(line) for line in lines)
    for factor in (0.9, 0.85, 0.8, 0.75, 0.7, 0.65, 0.6, 0.55, 0.5):
        candidate, _ = _tm.wrap(label, max_units * factor)
        if len(candidate) != count:
            continue
        candidate_widest = max(_tm.weighted_units(line) for line in candidate)
        if candidate_widest < widest - 1e-6:
            lines, widest = candidate, candidate_widest
    return lines, widest * REGION_LABEL_SIZE


def region_boxes(spec: dict, placed: dict, boxes: dict) -> list[dict]:
    """把 `groups` 变成**看得见的区域**：成员节点的并集 + 留白 + 标题带。

    这以前是空的 —— `groups` 只被校验、没有任何视觉效果，文档里也如实写着
    以前"既没有分组框，也没有分组标签"。用户拿 Excalidraw 手画的参考图来问
    "需要用区域表示的可以这样做"，那是**一整片浅色交叉网格 + 顶部标题**，
    图上立刻就有了色块 —— 而我们的图一直只有单个节点在承担颜色，95% 是中性色。

    用**成员节点自己的包围盒**算（不是虚线节点那种内部东西），所以区域一定
    框得住它画的每一个节点。标题带留在顶边以上，区域标题因此不会压到任何节点。

    **标题按区域的宽度断行，标题带的高度由断行结果算** —— 于是"标题比区域宽"
    在构造上不可能发生（见 `region_label_lines`）。断行结果与测好的尺寸一起
    放进返回值，落笔那边（`emit.region_elements`）直接用，**不重新量一遂**：
    同一件文字量两遂必然漂移，而漂移的那一遂会让框和字对不上。

    返回 `[{id, label, label_lines, label_size, label_width, label_height,
    level, members, x, y, width, height, label_x, label_y}, ...]`，
    顺序沿用 `groups` 的声明顺序（先声明的画在更下面）。
    """
    members: dict[str, list[str]] = {}
    for node in spec.get("nodes", []):
        gid = node.get("group")
        if gid:
            members.setdefault(gid, []).append(node["id"])

    out: list[dict] = []
    for group in spec.get("groups", []):
        ids = [nid for nid in members.get(group["id"], []) if nid in placed]
        if not ids:
            continue                      # 校验器已经拦了"没有成员的 group"
        left = min(placed[nid].x for nid in ids)
        top = min(placed[nid].y for nid in ids)
        right = max(placed[nid].x + boxes[nid].width for nid in ids)
        bottom = max(placed[nid].y + boxes[nid].height for nid in ids)
        width = (right - left) + REGION_PAD * 2
        label = group.get("label") or ""
        lines, label_width = region_label_lines(label, width)
        label_height = len(lines) * REGION_LABEL_SIZE * _tm.LINE_HEIGHT
        # 标题带的高度 = 上边距 + 标题块 + 与成员之间的空；没有标题时用单行那个数
        head = ((REGION_LABEL_TOP + label_height + REGION_LABEL_GAP)
                if lines else REGION_HEAD)
        x = left - REGION_PAD
        y = top - REGION_PAD - head
        height = (bottom - top) + REGION_PAD * 2 + head
        out.append({
            "id": group["id"],
            "label": label,
            "level": group.get("level", "tint"),
            # 标签断行结果与实际占的尺寸 —— 落笔那边直接用这几个数
            "label_lines": list(lines),
            "label_size": REGION_LABEL_SIZE,
            "label_width": round(label_width, 2),
            "label_height": round(label_height, 2),
            # 成员列表一起带出去：校验器要判"框里有没有夹着非成员"
            "members": list(ids),
            "x": round(x, 2), "y": round(y, 2),
            "width": round(width, 2), "height": round(height, 2),
            # 标题在标题带里**水平居中**（参考图就是这个样子）
            "label_x": round(x + width / 2.0, 2),
            "label_y": round(y + REGION_LABEL_TOP, 2),
        })
    return out


DEFAULT_DETAIL = "standard"


def shows_node_detail(node: dict, level: str | None) -> bool:
    """这一档要不要画这个节点的次要说明（`detail`）。

    ⚠️ `detail` 以前是**空壳**：校验器认它，`layout` / `check_layout` / `emit`
    一处都不读 —— 而 SKILL.md 的硬规则表里写着「信息量用 `detail` 控制」。
    同一类静默失败（旧的 `groups` 也是，声明了没人读）。评审把它抓出来之后，
    这里按那句话字面的意思实现：**它就是信息量档位**。

        executive   只留重点（`primary` / `critical`）节点的说明 —— 摘要只留结论
        standard    全部（默认，= 实现之前的行为，所以不影响任何既有规格）
        diagnostic  全部

    放在 layout 而不是 emit：**布局尺寸也依赖它**（少了那行字，盒子就该变小），
    两边必须用同一个判据 —— 各写一份必然漂移。
    """
    if level == "executive":
        return node.get("emphasis") in ("primary", "critical")
    return True


def shows_edge_label(edge: dict, level: str | None) -> bool:
    """这一档要不要画**用户写的**边标签。`executive` 丢掉（摘要不堆细节）。"""
    return level != "executive"


def boxes_from_spec(spec: dict, icon_sizes: dict | None = None) -> dict[str, Any]:
    """由文字 + 形状反推每个节点的尺寸。**尺寸不由模型给。**

    尺寸链：文字 → `text_metrics.measure` → `shapes.box_for` →
    **× 强调的尺寸倍数** → （枢纽时）交叉轴加长 → （有图标时）为图标加宽。
    
    顺序有讲究：倍数乘在**形状盒子**上（同形状等比放大，图形仍然成立），
    而后两项是**固定像素**的追加量，不该跟着倍数走。

    `icon_sizes` 是 `{node_id: (宽, 高)}`，由调用方从**素材库**里量好传进来
    （图标是缩放到固定高度的，所以这里只需要尺寸，不需要库本身 —— 布局不该知道
    “素材库”这个概念）。

    ⚠ 这是**第一个外部尺寸来源**：前面的每一步都是我们自己算的，而图标的宽高
    来自那个 `.excalidrawlib` 文件。所以 `references/validation.md` 第六节里
    “尺寸只有一个来源”那条前提从这一版起不再成立 —— 已按约定先改文档，
    再改 `TestSizeSourcePremise`（它先失败，那就是流程在起作用）。
    """
    detail_level = spec.get("detail", DEFAULT_DETAIL)
    tm = load_sibling("text_metrics")
    sh = load_sibling("shapes")
    sizes = icon_sizes or {}
    fans = fanout_of(spec)
    cross_axis_is_width = main_axis(spec) == "TB"
    out: dict[str, NodeBox] = {}
    for n in spec.get("nodes", []):
        # 字号层级（§14）：重点节点的**字号**往上一步。
        # 必须在这里传进去，不是落笔时改 fontSize —— 那样盒子的尺寸链就对不上了。
        step = _palette.emphasis_font_step(str(n.get("emphasis", "normal")))
        node_detail = n.get("detail", "") if shows_node_detail(n, detail_level) else ""
        text = tm.measure(n.get("label", ""), node_detail,
                          font_size=tm.FONT_NODE + step)
        shape = sh.resolve(n)
        width, height = sh.box_for(shape, text.width, text.height)
        # 强调的**尺寸层级**：重点节点略大一点。颜色退出主次之后，这是"层次感"的
        # 手段之一（见 §11 的优先级排序）。幅度刻意小（0.94 ~ 1.06）—— 要的是层次，
        # 不是海报式跳跃。实测（#114）：这个幅度在整图尺度上几乎看不见，所以它
        # **不承担焦点**，焦点仍由颜色和位置决定；倍数只让层次细腻一点。
        scale = _palette.emphasis_scale(str(n.get("emphasis", "normal")))
        width, height = width * scale, height * scale
        # 枢纽节点：扇出越大，交叉轴上越长 —— 落点才摊得开（P12）
        extra = hub_extra(fans.get(n["id"], 0))
        if cross_axis_is_width:
            width += extra
        else:
            height += extra
        if n.get("icon"):
            # 图标放左边，文字排在它右边（见 emit 的 node_elements）。
            # 拿不到尺寸就用一个保守的占位 —— 宁可多留白，也不能让图标盖住文字。
            icon_w, icon_h = sizes.get(n["id"], (0.0, 0.0))
            width += (icon_w or ICON_RESERVE) + ICON_GAP
            height = max(height, icon_h + 2 * ICON_VERTICAL_PAD)
        out[n["id"]] = NodeBox(id=n["id"], shape=shape, width=width,
                                height=height, text=text)
    return out


def load_sibling(name: str):
    """按显式文件路径加载同目录模块。

    必须先注册进 sys.modules 再 exec —— `@dataclass` 解析注解时会查
    `sys.modules.get(cls.__module__)`，没注册就拿到 None，然后
    `AttributeError: 'NoneType' object has no attribute '__dict__'`。
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{name}.py")
    mod_spec = importlib.util.spec_from_file_location(f"_diagram_{name}", path)
    if mod_spec is None or mod_spec.loader is None:
        raise RuntimeError(f"加载不了同目录模块：{path}")
    module = importlib.util.module_from_spec(mod_spec)
    sys.modules[mod_spec.name] = module
    mod_spec.loader.exec_module(module)
    return module



# `emphasis_scale` 的值住在 palette 的 EMPHASIS 里。
# 必须放在 load_sibling 定义**之后** —— 模块级代码自顶向下跑（这个坑踩过两次）。
_palette = load_sibling("palette")
# 量区域标题用的那一份。**模块级只加载一次**：`region_boxes` 每次出图会被调两次
# （校验一次、落笔一次），`load_sibling` 每调一次就重新 exec 一遂模块。
_tm = load_sibling("text_metrics")

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="分层布局（干跑，看坐标与交叉数）")
    ap.add_argument("spec", help="*.diagram.json")
    ap.add_argument("--explain", action="store_true", help="打印分层与排序结果")
    args = ap.parse_args(argv)

    try:
        with open(args.spec, encoding="utf-8") as fh:
            spec = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"读不到规格：{exc}", file=sys.stderr)
        return 2

    try:
        result = layout(spec, boxes_from_spec(spec))
    except ValueError as exc:
        print(f"布局失败：{exc}", file=sys.stderr)
        return 1

    if args.explain:
        print(f"方向 {result.direction}  交叉数 {result.crossings}  "
              f"虚节点 {result.dummy_count}  被反转的边 {result.reversed_edges}")
        for r in sorted(result.order):
            print(f"  rank {r}: {result.order[r]}")
        for nid, pl in sorted(result.real_nodes().items(),
                              key=lambda kv: (kv[1].rank, kv[1].y, kv[1].x)):
            print(f"  {nid:<16} x={pl.x:>7} y={pl.y:>7}  {pl.width:.0f}×{pl.height:.0f}")
        for c in result.pin_conflicts:
            print(f"  ⚠ {c}")
    else:
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
