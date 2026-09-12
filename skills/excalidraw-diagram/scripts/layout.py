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

DIRECTION_FOR_TYPE = {
    "architecture": "LR",
    "component": "LR",
    "sequence": "LR",
    "dependency": "TB",
    "flow": "TB",
    "state": "LR",
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
def assign_coordinates(order: dict[int, list[str]], boxes: dict[str, Box],
                       direction: str, node_sep: float, rank_sep: float
                       ) -> dict[str, Placed]:
    live = {r: [n for n in layer if n in boxes] for r, layer in order.items()}
    live = {r: layer for r, layer in live.items() if layer}
    if not live:
        return {}

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
    return placed


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
    left, top = p.x - pad, p.y - pad
    right, bottom = p.x + p.width + pad, p.y + p.height + pad
    return any(left <= x <= right and top <= y <= bottom
               for x, y in _sample_points(a, b))


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

    placed = assign_coordinates(order, all_boxes, direction,
                                p["nodeSeparation"], p["rankSeparation"])
    routed = route_edges(origins, segments, placed, direction, set(reversed_edges))

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

    尺寸链：文字 → `text_metrics.measure` → `shapes.box_for` → （有图标时）为图标加宽。

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
    out: dict[str, NodeBox] = {}
    for n in spec.get("nodes", []):
        text = tm.measure(n.get("label", ""), n.get("detail", ""))
        shape = sh.resolve(n)
        width, height = sh.box_for(shape, text.width, text.height)
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
