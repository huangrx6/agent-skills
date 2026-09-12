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
from dataclasses import dataclass
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
# 【待验证】初值取自前作 layout.mjs 的 Dagre 默认值（nodeSeparation 70 / rankSeparation 120）。
# 原则：别人失败经验里的**具体数值**值得复用；他们的**架构决策**不值得复用。
# 但注意——“前作用过、没被推翻”≠“已经验证过”。这两个数我们没量过，所以标待验证。
# 信任状态总表见 references/diagram-spec.md（“数值的信任状态”一节）。
DEFAULT_PARAMS: dict[str, float] = {
    "nodeSeparation": 70.0,
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
WRAP_SEGMENT_GAP = 150.0
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


def _radial_extent(box: Any, theta: float) -> float:
    """盒子在**半径方向**（角度 theta）上的半宽。"""
    return ((box.width / 2.0) * abs(math.cos(theta))
            + (box.height / 2.0) * abs(math.sin(theta)))


def _tangential_extent(box: Any, theta: float) -> float:
    """盒子在**切向**上的半宽。"""
    return ((box.width / 2.0) * abs(math.sin(theta))
            + (box.height / 2.0) * abs(math.cos(theta)))


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
    return placed, rings, radial_edges(edges, placed)


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


def radial_edges(edges: list[dict], placed: dict[str, Any]) -> list[dict]:
    """径向的连线：两个节点中心之间的直线，裁到盒子边上。

    分层那套"按 LR/TB 的四个边贴点"在这里不成立 —— 径向的线是**朝外的辐条**，
    方向取决于两个节点在环上的相对位置，不是固定的上下左右。

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
                       direction: str, node_sep: float, rank_sep: float
                       ) -> Coords:
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
        for index, r in enumerate(ranks):
            segment = index // per_segment
            segments[r] = segment
            # 交叉轴：每段往右让开一个"段宽 + 段间空档"。第 0 段不让。
            cross_shift = segment * (cross_max + WRAP_SEGMENT_GAP)
            # 主轴：**每段都从 0 重新开始**。
            # 少了这一步就不是"折"，而是"斜着错开的楼梯" —— 高度一点没降，只多了宽度，
            # 长宽比数字会变好看但图反而更大。第一版就漏了这一步。
            main_shift = main_start[ranks[segment * per_segment]] if segment else 0.0
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
                reversed_set: set[tuple[str, str]]) -> list[dict]:
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
    starts, ends = _anchor_slots(resolved, placed, direction)

    for idx, chain in resolved:
        e = origins[idx]
        pts = _points(chain, placed, direction, starts[idx], ends[idx])
        # 推开挡路的节点。排除自己的两端 —— 它们本来就贴着线。
        pts = avoid_nodes(pts, placed, {chain[0], chain[-1]})
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


def _points(chain: list[str], placed: dict[str, Placed], direction: str,
            start_off: float = 0.0, end_off: float = 0.0) -> list[list[float]]:
    pts: list[list[float]] = []
    last = len(chain) - 1
    for i, nid in enumerate(chain):
        p = placed[nid]
        cx, cy = p.x + p.width / 2, p.y + p.height / 2
        if i == 0:
            pts.append([p.x + p.width, cy + start_off] if direction == "LR"
                       else [cx + start_off, p.y + p.height])
        elif i == last:
            pts.append([p.x, cy + end_off] if direction == "LR"
                       else [cx + end_off, p.y])
        else:
            pts.append([cx, cy])
    return [[round(x, 2), round(y, 2)] for x, y in pts]


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

    三个坑，全是实测踩出来的：

    1. **不能直连**。直连是从一栏的末尾斜拉到另一栏的开头，横穿两栏 ——
       实测 `02-flow` 的 `scan → stage` 撞掉 2 个节点（`cache`、`gate`）。
    2. **也不能顺着"出源节点后直接走交叉轴"**。TB 下这招碰巧能用（层是横排，
       从源节点下方走出去天然是空的），**LR 下必撞** —— 层是竖列，源节点正下方
       往往就站着同列的下一个节点。实测 `04-state` 的 `paid → refunding`
       就这么撞上了 `cancelled`。
    3. 所以第一步必须是**沿主轴**绕到本层外缘之外那条通道（`lane`），再拐。

    `lane` 由调用方按源节点所在层的实际外缘算出（主轴方向）。
    """
    if direction == "TB":
        start = [a.x + a.width / 2.0, a.y + a.height]        # 底边中点
        end = [b.x + b.width / 2.0, b.y]                     # 顶边中点
        pts = [start, [start[0], lane], [band, lane],
               [band, end[1]], end]
    else:
        start = [a.x + a.width, a.y + a.height / 2.0]        # 右边中点
        end = [b.x, b.y + b.height / 2.0]                    # 左边中点
        pts = [start, [lane, start[1]], [lane, band],
               [end[0], band], end]
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

    coords = assign_coordinates(order, all_boxes, direction,
                                p["nodeSeparation"], p["rankSeparation"])
    placed = coords.placed
    routed = route_edges(origins, segments, placed, direction, set(reversed_edges))
    # 折段之后，两端落在不同段的连线改走空档 —— 直连会横穿两栏。
    if coords.bands:
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
            e["points"] = wrap_route(pa, placed[e["to"]], coords.bands[min(sa, sb)],
                                     lane, direction)

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
        text = tm.measure(n.get("label", ""), n.get("detail", ""),
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
