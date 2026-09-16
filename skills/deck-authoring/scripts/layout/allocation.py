"""deck 级**联合**择优：不逐页各挑各的，而是整份 deck 一起挑。

**为什么必须联合**：逐页挑最优会得到"每页都还行、整份却一个版式用五遍"的结果 ——
每页的局部最优互相不知道对方存在。重复是 deck 级的病，就得用 deck 级的目标函数治。

**目标函数**（量级沿用 guizang/dashi 那一系的公开做法，各项治什么写在注释里）：

    score = 拟合损失 × 150 + 页内重复惩罚 + 跨页重复惩罚

- 拟合损失 = Σ(该页候选最高分 − 选中候选分)。带 `FIT_BAND`：**接近最优即可** ——
  在最优带里挑，才有余地换掉重复；否则永远锁死在逐页最优上。
- 页内：同 family ×300、同构图 ×450（三条候选不该是近亲 —— 镜像在
  `fingerprint.composition` 里已经折叠成同一个构图）。
- 跨页：与**上一页** family 重叠 ×90（相邻页换构图最容易被眼睛记住）。
- 全局重复：同 layout ×600、同候选组合 ×1400、同 family ×14，按 n(n-1)/2 增长
  （用得越多惩罚越陡）。

**确定性**：平局靠 `hashSeed(seed|key)` 解 —— 同 seed 同输入必得同结果。
不要用内置 `hash()`（每进程加盐，同输入不同结果）。

边界：本模块只做**选择**，不做测量、不碰几何。候选的分数由调用方（实测 +
`candidates.score_page`）给进来；不认识的候选（无分数）不参与。
"""
from __future__ import annotations

import random

# ── 权重：改这里就是改"什么更重要"，所以每项都写清治什么 ──────────────
FIT_WEIGHT = 150.0          # 拟合损失 → 别为了多样性牺牲"装得下"
FIT_BAND = 0.16             # 拟合带：与最高分相差 ≤0.16 都算"够好"（0~1 分制）
IN_PAGE_SAME_FAMILY = 300.0
IN_PAGE_SAME_COMPOSITION = 450.0
PREV_PAGE_SAME_FAMILY = 90.0
REPEAT_LAYOUT = 600.0
REPEAT_COMBINATION = 1400.0
REPEAT_FAMILY = 14.0
PASSES = 3                  # 坐标下降轮数（dashi 同量级；再大收益递减）
CHOICE_LIMIT = 96           # 单页最多保留多少种"三条候选的组合"
CANDIDATE_LIMIT = 18        # 单页参与组合的候选上限（按构图去重后）


def hash_seed(*parts) -> float:
    """稳定伪随机数（0~1）：`random.Random` 用字符串种子，跨进程/跨机器一致。

    与 `render._rng` 同一套约定（`Random("seed|part|…")`）；不要用内置 `hash()`。
    """
    return random.Random("|".join(str(p) for p in parts)).random()


def repeat_counts(values: list) -> dict:
    """值 → 出现次数（只留 >1 的），给门与诊断用。"""
    counts: dict = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return {k: n for k, n in counts.items() if n > 1}


def _penalty(values: list, weight: float) -> float:
    """n(n-1)/2 × 权重 —— 同一个值出现越多，代价越陡。"""
    return sum(n * (n - 1) / 2 * weight for n in repeat_counts(values).values())


def _intra_page_penalty(items: list, fingerprints) -> float:
    families = [fingerprints[name]["family"] for name in items]
    comps = [fingerprints[name]["composition"] for name in items]
    return ((len(items) - len(set(families))) * IN_PAGE_SAME_FAMILY
            + (len(items) - len(set(comps))) * IN_PAGE_SAME_COMPOSITION)


def _diversity_penalty(assignments: list, fingerprints) -> float:
    total = sum(_intra_page_penalty(a, fingerprints) for a in assignments)
    for prev, cur in zip(assignments, assignments[1:]):
        prev_fams = {fingerprints[n]["family"] for n in prev}
        total += sum(PREV_PAGE_SAME_FAMILY
                     for n in cur if fingerprints[n]["family"] in prev_fams)
    flat = [n for a in assignments for n in a]
    total += _penalty(flat, REPEAT_LAYOUT)
    total += _penalty(["|".join(sorted(a)) for a in assignments], REPEAT_COMBINATION)
    total += _penalty([fingerprints[n]["family"] for n in flat], REPEAT_FAMILY)
    return total


    """拟合带：该组合自身的最差成员相对本页最高分的差距（≤0 表示全是最高分）。"""
    best = max(fit[n] for n in items)
    return best - min(fit[n] for n in items)


def _as_float(value) -> float | None:
    """数字→ float，不是数字→ None。

    不收 `bool`（True/False 不是分数），`NaN` 也挡掉 —— 一个 NaN 混进 `max()`
    会把整页的基准分变成 NaN，后面所有比较全假（静默挑错候选）。
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        num = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return None if num != num else num


def _composition_of(candidate: dict) -> str:
    """候选的构图键；没有指纹（不认识的名字）时用它自己当键（不静默合并）。"""
    fp = candidate.get("fingerprint") or {}
    return fp.get("composition") or f"unknown|{candidate['layout']}"


def combination_loss(combo: list, fit: dict, page_best: float) -> float:
    """一条组合相对该页最高分的损失（取组合里**最差**的成员）。

    为什么看最差成员：三条候选是给作者挑的，他最后只会选其中一条；组合里有一条
    明显更差，等于“给了个坏选项”，应当计入损失。
    """
    return round(page_best - min(fit[n] for n in combo), 6)


def allocate(pages: list, seed=None, per_page: int = 3) -> dict:
    """整份 deck 联合择优。

    ``pages``：``[{"key": <页码>, "pageType": str, "candidates": [{"layout", "fit",
    "fingerprint"}]}]`` —— 只放**有效**候选（作废/无分数的由调用方先剔除）。
    ``fit`` 是 0~1 的实测分数（越高越合适）。

    返回 ``{"assignments": {页码: [候选名…]}, "score", "penalties", "diagnostics"}``；
    候选不足 `per_page` 的页按实际数量给（并写进 diagnostics），一页都没有候选的页
    不出现在 assignments 里（保持它原来的缺省布局）。
    """
    diagnostics: list[str] = []
    fit: dict = {}
    fingerprints: dict = {}
    choices: dict = {}          # 页码 → [(罚分, tie, [候选…]), …]
    defaults: dict = {}         # 页码 → 该页候选里的最高分（作为无需选版式时的基准）

    for page in pages:
        key = page["key"]
        cands: list = []
        for c in page.get("candidates") or []:
            score = _as_float(c.get("fit"))
            if score is None:
                continue                        # 没分数的候选不参与（作废的由调用方剔除）
            layout = c.get("layout")
            if not isinstance(layout, str) or not layout:
                continue
            cands.append({"layout": layout, "fit": score,
                          "fingerprint": c.get("fingerprint") or {}})
        for c in cands:                         # 名字全局唯一（同一页型内 layout 名唯一）
            fit[c["layout"]] = c["fit"]
            fingerprints[c["layout"]] = c["fingerprint"]
        # 按**构图**去重：镜像（图左/图右）与同跨度变体是同一个结构，不能占两个候选位。
        # 这一步由本模块自持 —— 指望调用方先过滤，就会出现"三条候选里两条同构图"。
        # 每个构图留**得分最高**的那一个（平分时保留先出现的），再按分降序：
        # 候选 1 是实测最合适的那条，顺序本身就是信息。
        best_by_comp: dict = {}
        for c in cands:
            comp = _composition_of(c)
            if comp not in best_by_comp or c["fit"] > best_by_comp[comp]["fit"]:
                best_by_comp[comp] = c
        cands = sorted(best_by_comp.values(), key=lambda c: -c["fit"])
        if not cands:
            diagnostics.append(f"第 {key} 页没有可用候选（全部作废或没有结构布局）—— 保持缺省")
            continue
        defaults[key] = max(c["fit"] for c in cands)
        names = [c["layout"] for c in cands][:CANDIDATE_LIMIT]
        want = min(per_page, len(names))
        combos = _combinations(names, want)
        if len(names) < per_page:
            diagnostics.append(
                f"第 {key} 页只有 {len(names)} 个结构不同的候选（{ '、'.join(names) }）"
                f"—— 给不满 {per_page} 个；结构指纹相同的（含镜像）不重复占位")
        if not combos:
            diagnostics.append(f"第 {key} 页组不出候选组合 —— 保持缺省")
            continue
        page_best = defaults[key]
        best_loss = min(combination_loss(c, fit, page_best) for c in combos)
        band = max(FIT_BAND, best_loss)      # 候选普遍差得很开时，至少保住最好的那几条
        kept = []
        for combo in combos:
            loss = combination_loss(combo, fit, page_best)
            if loss > band:
                continue
            kept.append((loss, _intra_page_penalty(combo, fingerprints),
                         hash_seed(seed, key, "|".join(combo)), combo))
        kept.sort(key=lambda row: (row[0], row[1], row[2]))
        if not kept:
            diagnostics.append(f"第 {key} 页候选拟合差距过大 —— 保持缺省")
            continue
        choices[key] = [row[3] for row in kept[:CHOICE_LIMIT]]

    if not choices:
        return {"assignments": {}, "score": 0.0, "penalties": {},
                "diagnostics": diagnostics}

    # 逐页坐标下降：每次只换一页，挑让全局分数最低的那条组合。
    order = sorted(choices)
    selected = [choices[k][0] for k in order]

    def score_of(sel: list):
        assignments = {k: list(c) for k, c in zip(order, sel)}
        flat = [n for c in sel for n in c]
        penalties = {
            "fitLoss": round(sum(combination_loss(c, fit, defaults[k])
                                 for k, c in zip(order, sel)), 4),
            "intraPage": round(sum(_intra_page_penalty(c, fingerprints) for c in sel), 2),
            "diversity": round(_diversity_penalty(sel, fingerprints), 2),
            "repeatLayout": repeat_counts(flat),
            "repeatCombination": repeat_counts(["|".join(sorted(c)) for c in sel]),
        }
        return penalties["fitLoss"] * FIT_WEIGHT + penalties["diversity"], penalties

    for _ in range(PASSES):
        changed = False
        for idx, key in enumerate(order):
            best, best_score = selected[idx], score_of(selected)[0]
            best_tie = hash_seed(seed, key, "|".join(selected[idx]))
            for combo in choices[key]:
                trial = list(selected)
                trial[idx] = combo
                sc, _pen = score_of(trial)
                tie = hash_seed(seed, key, "|".join(combo))
                if sc < best_score or (sc == best_score and tie < best_tie):
                    best, best_score, best_tie = combo, sc, tie
            if best != selected[idx]:
                selected[idx] = best
                changed = True
        if not changed:
            break

    score, penalties = score_of(selected)
    assignments = {k: list(c) for k, c in zip(order, selected)}
    flat = [n for c in selected for n in c]
    for name, n in sorted(repeat_counts(flat).items(), key=lambda kv: -kv[1]):
        if n >= 3:
            diagnostics.append(
                f"版式 {name!r} 在整份 deck 里用了 {n} 次 —— "
                f"（重复惩罚已计入；要再散开就手动给某页指定另一个结构）")
    for combo, n in repeat_counts(["|".join(sorted(c)) for c in selected]).items():
        if n >= 2:
            diagnostics.append(f"候选组合 {combo} 重复 {n} 次 —— 同几页反复用同组结构")
    return {"assignments": assignments, "score": round(score, 2),
            "penalties": penalties, "defaults": defaults,
            "diagnostics": diagnostics}


def _combinations(names: list, k: int) -> list:
    """names 里取 k 个的组合（保序，纯手写以免引 itertools 的排序歧义）。"""
    out: list = []
    n = len(names)
    if k < 1 or n < k:
        return out

    def walk(start: int, acc: list) -> None:
        if len(acc) == k:
            out.append(list(acc))
            return
        for i in range(start, n):
            acc.append(names[i])
            walk(i + 1, acc)
            acc.pop()

    walk(0, [])
    return out


__all__ = ["allocate", "hash_seed", "repeat_counts", "combination_loss",
           "FIT_WEIGHT", "FIT_BAND", "PASSES", "CHOICE_LIMIT"]
