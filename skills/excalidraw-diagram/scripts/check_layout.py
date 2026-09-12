#!/usr/bin/env python3
"""五项校验 + 自动调参循环 + 报告生成。

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
EDGE_MIN = 24.0           # #2 连线最短可见长度
CROSSING_RATIO = 0.5      # #5 交叉数软阈值 = 边数 × 0.5
MAX_TUNE_ROUNDS = 4       # 调参轮数上限
TOLERANCE = 0.5           # 浮点比较容差（#3 断言用）

# 命中这几类就别调参了 —— 改参数没用，那是脚本 bug 或内容错误
STOP_ON = frozenset({"text", "palette"})
# 可以靠调参解决的项。注意 #5（交叉数）是**软**项 —— 它不阻塞输出，但仍然是可调的。
# 只看“阻不阻塞”会让它永远调不动，而 validation.md 明写着它可自动修。
TUNABLE = frozenset({"gap", "edge", "crossing"})

CHECK_LABEL = {
    "gap": "元素间隙",
    "edge": "连线长度",
    "text": "文字溢出",
    "palette": "颜色越界",
    "crossing": "边交叉数",
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
        """没有阻塞项，也没有待调的交叉项 → 可以出图了。

        交叉项单独判：它是软的，不进 blocking，但没收敛就不该停 ——
        否则软项一出现就直接出报告，调参循环对它就等于不存在。
        """
        return not self.blocking and "crossing" not in self.tunable_hits()


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
    """
    gap_x = max(b.x - (a.x + a.width), a.x - (b.x + b.width), 0.0)
    gap_y = max(b.y - (a.y + a.height), a.y - (b.y + b.height), 0.0)
    return math.hypot(gap_x, gap_y)


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
        fresh = tm.measure(node.get("label", ""), node.get("detail", ""))
        # 盒子现在是 NodeBox：形状包围盒 + 里面的文字。断言比的是**文字那一半** ——
        # 形状多出来的余量是从文字算出来的，拿包围盒去比文字尺寸会必然不等。
        # 比文字本身反而更强：形状算错了会从 layout.boxes_from_spec 那条路被发现。
        used = getattr(boxes[nid], "text", boxes[nid])
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

    强调层级的派生色**也从色板算出来**（`palette.emphasis_fill`），
    不是手写第二张表 —— 手写就会漂移，而漂移了这张校验就变成假的。
    """
    colors: set[str] = set()
    for entry in list(palette.KINDS.values()) + list(palette.EDGE_KINDS.values()):
        colors.update(v for k, v in entry.items() if k in ("stroke", "background"))
    colors.update(v for k, v in palette.CANVAS.items() if k in ("background", "grid", "text"))
    for kind in palette.KINDS:
        for emphasis in palette.EMPHASIS:
            colors.add(palette.emphasis_fill(kind, emphasis))
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
        stroke = palette.stroke_for(kind)
        background = palette.emphasis_fill(kind, emphasis)
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
def check(spec: dict, result: ResultT,
          boxes: dict[str, BoxT]) -> Outcome:
    return Outcome(issues=[
        *check_gaps(result),
        *check_edge_lengths(result),
        *check_text_fit(spec, result, boxes),
        *check_palette(spec),
        *check_crossings(spec, result),
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
    return out


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
        current = stepped
        result = L.layout(spec, boxes, current)
        outcome = check(spec, result, boxes)

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
    ap = argparse.ArgumentParser(description="五项校验 + 自动调参（报告里不出现参数名）")
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
