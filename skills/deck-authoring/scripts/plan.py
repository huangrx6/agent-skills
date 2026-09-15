#!/usr/bin/env python3
"""规划层：内容理解 → Storyline → Page Planner →（既有的）Slide DSL。

## 这一层在整条链里的位置

```text
① content.json   「我们知道什么」        事实/观点/数字/关系（AI 写，本模块校验）
② storyline.json 「按什么顺序讲」        骨架 + 节奏（AI 选 archetype，本模块管骨架与配额）
③ pageplan.json  「每页怎么表达」        页型/主视觉/密度/拆页（AI 判，本模块管复杂度与映射）
④ deck-spec.json 「怎么描述给渲染器」    ←—— 既有的 Slide DSL，358 条测试护着
```

**越靠近渲染，AI 自由度越低**（规范定的工程原则，本模块的形状就是它的落地）：

| 层 | AI 自由度 | 程序确定性 |
| --- | --- | --- |
| 内容理解 | 中 | Schema + 引用完整性 + 事实/推断分离 |
| Storyline | 中 | archetype 骨架成文 + 权重→页数配额必须自洽 |
| Page Planner | 低~中 | 复杂度评分 + 拆页阈值 + 页型→版式映射 |
| Slide DSL | 很低 | 封闭字段集（validate_spec） |
| Layout/渲染 | 0 | grid.py / render.py |

## 为什么从后往前建（已经走完了）

规范说的开发顺序 —— Schema → Renderer → Layout → Page Planner → Storyline →
内容理解 —— 本仓库天然满足：渲染链先稳定（358 条测试），规划层才有一个**明确的
目标**（产出一份能过 validate_spec 的 deck-spec.json）。反过来先写 AI Agent，
产出的东西渲染器吃不下，就全白写。

## 三条能失败的硬规矩（不是文档，是检查）

1. **引用必须可解析**：message 的 evidence_refs 指向不存在的 fact → 错。
   悬空引用的"证据"不是证据。
2. **事实与推断必须分开**：source_type ∈ {original, inferred, generated}；
   一条高重要性的 message 如果只靠 **inferred** 事实支撑 → 提示
   （"你把 AI 推断的话当事实讲了"—— 这是 AI PPT 最危险的一类错）。
3. **配额必须自洽**：sections 的 target_slides 加起来 == target_slide_count、
   weights 加起来 ≈ 1.0、beat 的 role 顺序必须符合所选 archetype 的骨架。
   "15 页的 PPT 做成 28 页"就是这里漏的。

跑法：
    python3 scripts/plan.py --archetypes          # 十个叙事骨架
    python3 scripts/plan.py --check content.json storyline.json pageplan.json
    python3 scripts/plan.py --to-spec pageplan.json content.json -o deck.spec.json
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)


def _load_sibling(name: str):
    key = f"_deck_{name}"
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, os.path.join(HERE, f"{name}.py"))
    if spec is None or spec.loader is None:
        raise SystemExit(f"✗ 加载不了 scripts/{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


deckio = _load_sibling("deckio")
hierarchy = _load_sibling("hierarchy")

# ═══════════════════════════════════════════════════════════════════════════
# ② 叙事骨架（Archetype）—— 成文的数据，不是让 LLM 自由发挥
#
# 为什么骨架要预定义：让 LLM 自由写故事，十次会得到十种结构，其中大部分没有
# 逻辑递进。骨架把"为什么先讲这个"固化成顺序，LLM 只需要**选**骨架 + 填内容。
# ═══════════════════════════════════════════════════════════════════════════

ARCHETYPES: dict[str, dict] = {
    "problem_solution": {
        "label": "问题 → 方案",
        "roles": ["context", "problem", "impact", "goal", "solution",
                  "architecture", "capabilities", "implementation", "value", "next_step"],
        "fits": "技术方案、立项建议",
    },
    "scr": {
        "label": "情境 → 冲突 → 解法",
        "roles": ["situation", "complication", "resolution", "evidence", "next_step"],
        "fits": "汇报、说服",
    },
    "past_present_future": {
        "label": "过去 → 现在 → 未来",
        "roles": ["past", "present", "future", "implication", "next_step"],
        "fits": "战略、回顾与展望",
    },
    "why_what_how": {
        "label": "为什么 → 是什么 → 怎么做",
        "roles": ["why", "what", "how", "proof", "next_step"],
        "fits": "产品介绍、理念宣讲",
    },
    "goal_progress_result": {
        "label": "目标 → 进展 → 结果 → 下一步",
        "roles": ["goal", "progress", "result", "gap", "next_step"],
        "fits": "项目汇报、OKR 复盘",
    },
    "overview_detail_evidence": {
        "label": "总览 → 细节 → 证据 → 小结",
        "roles": ["overview", "detail", "evidence", "summary"],
        "fits": "评审、研究报告",
    },
    "product_capability_value": {
        "label": "产品 → 能力 → 价值 → 证明",
        "roles": ["user_problem", "opportunity", "positioning", "capability",
                  "usage", "differentiation", "case", "value"],
        "fits": "产品介绍、售前",
    },
    "incident_review": {
        "label": "事故复盘",
        "roles": ["timeline", "impact", "root_cause", "fix", "prevention"],
        "fits": "事故复盘、故障报告",
    },
    "tech_proposal": {
        "label": "技术方案（中文场景）",
        "roles": ["context", "problem", "goal", "design", "architecture",
                  "modules", "deployment", "security", "performance", "value", "plan"],
        "fits": "架构设计、技术评审",
    },
    "project_report": {
        "label": "项目汇报（中文场景）",
        "roles": ["goal", "status", "achievements", "data", "issues", "risks", "next_step"],
        "fits": "周报、月报、阶段汇报",
    },
}

# ═══════════════════════════════════════════════════════════════════════════
# ③ 页型 → 版式的映射（确定性）+ 复杂度评分
#
# 页型是**表达意图**（comparison / process / architecture…），版式是**渲染器认的
# type**。映射是查表，不是判断 —— AI 判页型，程序决定用哪个版式画。
# ═══════════════════════════════════════════════════════════════════════════

PAGE_TYPES: dict[str, dict] = {
    "statement":     {"layout": "content-text", "visual": "none",
                      "why": "一个核心观点，靠字与留白立住"},
    "metric":        {"layout": "chart", "visual": "metric", "chart": "donut",
                      "why": "一个大数字是焦点（进度/达成率用环图中心）"},
    "comparison":    {"layout": "chart", "visual": "chart", "chart": "bar",
                      "why": "多个类别比大小"},
    "trend":         {"layout": "chart", "visual": "chart", "chart": "line",
                      "why": "时间横向展开"},
    "composition":   {"layout": "chart", "visual": "chart", "chart": "bar-stacked",
                      "why": "部分与整体"},
    "process":       {"layout": "timeline", "visual": "timeline",
                      "why": "步骤有先后"},
    "capabilities":  {"layout": "two-column", "visual": "none",
                      "why": "并列的两组能力/论点"},
    "hero_visual":   {"layout": "content-image", "visual": "image",
                      "why": "图是主视觉，文字是配角"},
    "context_image": {"layout": "content-image", "visual": "image",
                      "why": "现场/界面/实物，配一段说明"},
    "evidence":      {"layout": "content-text", "visual": "none",
                      "why": "证据细目，读的页（密一点可以接受）"},
}

# 复杂度评分的权重：字符数 + 节点数×权重 + 图表数 + 图数 + 层级深度。
# 超过 SPLIT_THRESHOLD 就该拆页 —— "一页塞下架构+五个能力+三个优势+拓扑"
# 是 AI PPT 最典型的爆法。
COMPLEXITY = {"char_weight": 1 / 120.0, "node_weight": 0.12, "chart_weight": 0.25,
              "image_weight": 0.15, "depth_weight": 0.10}
SPLIT_THRESHOLD = 0.70


def complexity(page: dict) -> float:
    """这一页的内容复杂度（0~1）。超过阈值 → 拆。

    为什么是这些项：字符是**读的量**、节点/图表/图是**看的量**、层级深度是
    **组织的量**。三项都压不住的页,无论版式多好都救不回来。
    """
    text = str(page.get("message", "")) + str(page.get("body", ""))
    chars = len(text) * COMPLEXITY["char_weight"]
    nodes = len(page.get("nodes", []) or []) * COMPLEXITY["node_weight"]
    charts = (1 if page.get("page_type") in PAGE_TYPES
              and PAGE_TYPES[page["page_type"]]["visual"] == "chart" else 0) \
        * COMPLEXITY["chart_weight"]
    images = (1 if page.get("image") else 0) * COMPLEXITY["image_weight"]
    depth = max(0, len(page.get("structure", [])) - 1) * COMPLEXITY["depth_weight"]
    return min(1.0, chars + nodes + charts + images + depth)


def should_split(page: dict) -> tuple[bool, float]:
    score = complexity(page)
    return (score >= SPLIT_THRESHOLD, score)


# ═══════════════════════════════════════════════════════════════════════════
# ① 内容理解：Schema + 引用完整性 + 事实/推断分离
# ═══════════════════════════════════════════════════════════════════════════

FACT_TYPES = ("context", "problem", "solution", "metric", "constraint", "risk", "result")
SOURCE_TYPES = ("original", "inferred", "generated")


PURPOSES = ("decision", "proposal", "report", "update", "training",
            "sales", "explanation", "review")
AUDIENCES = ("executive", "technical", "customer", "internal", "general")
DELIVERIES = ("live", "async", "printable", "editable")
CLAIM_TYPES = ("original", "derived")
# v3.0 §50：变化词单独出现（句里没有数字撑着）就该被追问"提升什么？多少？"
VAGUE_CHANGE_WORDS = ("提升", "优化", "降低", "提高", "改善", "赋能", "助力",
                       "领先", "先进")


def _norm_statement(text: str) -> str:
    """归一化陈述：去空白与标点、小写 —— 只用于**完全重复**检测。"""
    return "".join(ch.lower() for ch in text if ch.isalnum())


def check_content(content: dict) -> tuple[list[str], list[str]]:
    """校验 content.json。返回 (错误, 提示)。"""
    problems: list[str] = []
    notes: list[str] = []
    facts = content.get("facts", [])
    fact_ids = {f.get("id") for f in facts}
    if not facts:
        problems.append("content.json 里没有 facts —— 内容理解是空的")
    messages = content.get("messages", [])
    if not messages:
        problems.append("content.json 里没有 messages —— 每页的 Takeaway 无从谈起")
    for f in facts:
        for key in ("id", "type", "text"):
            if not f.get(key):
                problems.append(f"fact {f.get('id', '?')} 缺 {key}")
        if f.get("type") not in FACT_TYPES:
            problems.append(f"fact {f.get('id', '?')}.type={f.get('type')!r} "
                            f"不在 {list(FACT_TYPES)}")
        if f.get("source_type") not in SOURCE_TYPES:
            problems.append(f"fact {f.get('id', '?')}.source_type={f.get('source_type')!r} "
                            f"不在 {list(SOURCE_TYPES)} —— 事实与推断必须分开标")
    for m in content.get("messages", []):
        refs = m.get("evidence_refs", [])
        dangling = [r for r in refs if r not in fact_ids]
        if dangling:
            problems.append(f"message {m.get('id', '?')} 的证据 {dangling} 指向不存在的 "
                            f"fact —— 悬空引用的证据不是证据")
        # 一条重要结论只靠**推断**支撑 → 这是 AI PPT 最危险的一类错
        backed = [f for f in facts if f.get("id") in refs]
        original = [f for f in backed if f.get("source_type") == "original"]
        inferred = [f for f in backed if f.get("source_type") == "inferred"]
        if (m.get("importance", 0) or 0) >= 0.9 and refs and not original and inferred:
            notes.append(f"message「{str(m.get('statement', ''))[:20]}…」重要性 "
                         f"{m.get('importance')}，但证据全部是 inferred —— "
                         f"你在把 AI 推断的话当事实讲；要么找到原文证据，要么降重要性")
        # v3.0 §50/§51：变化词没有数字撑着 → 追问（提示，不阻断）
        text = str(m.get("statement", ""))
        if (any(w in text for w in VAGUE_CHANGE_WORDS)
                and not any(ch.isdigit() for ch in text)):
            notes.append(f"message「{text[:20]}…」有变化词但全句没有数字 —— "
                         f"追问：提升什么？多少？有证据吗（数字优先）")

    # v3.0 §44：同一句话讲两遍。归一化后**完全相同**才算（语义相似度是
    # 未实现的约定 —— 离线、零依赖做不了 embedding）。
    seen: dict[str, str] = {}
    for m in messages:
        norm = _norm_statement(str(m.get("statement", "")))
        if norm and norm in seen:
            notes.append(f"message {m.get('id', '?')} 与 {seen[norm]} 是同一句话 —— "
                         f"合并 / 改写 / 删一条，别让观众听第二遍")
        elif norm:
            seen[norm] = str(m.get("id", "?"))

    # ── v3.0 §2：Presentation Brief（可选；给了就必须像样）────────
    brief = content.get("brief")
    if brief is None:
        notes.append("没有 brief —— desiredAction 不明：观众看完该做什么没有答案，"
                     "骨架只能按 topic 猜")
    elif not isinstance(brief, dict):
        problems.append("brief 必须是对象")
    else:
        for key, allowed in (("purpose", PURPOSES), ("audience", AUDIENCES),
                             ("delivery", DELIVERIES)):
            if key in brief and brief[key] not in allowed:
                problems.append(f"brief.{key}={brief[key]!r} 不在 {list(allowed)}")
        if not (brief.get("desiredAction") or brief.get("desiredBelief")):
            problems.append("brief 缺 desiredAction / desiredBelief —— 先明确观众"
                            "最终要做什么，再决定他需要相信什么（元规则 1）")
        for key in ("targetSlides", "durationMinutes"):
            v = brief.get(key)
            if v is not None and (not isinstance(v, int) or isinstance(v, bool) or v < 1):
                problems.append(f"brief.{key}={v!r} 应为正整数")

    # ── v3.0 §11 / §59：Core Thesis 必须存在（阻断）───────────────
    thesis = content.get("coreThesis")
    stmt = thesis.get("statement") if isinstance(thesis, dict) else None
    if not stmt:
        problems.append("缺 coreThesis.statement —— 一份 deck 必须有一句统领全篇的"
                        "论断（元规则 2）；没有它，每页各自为政")

    # ── v3.0 §5.2：Claim 层（可选；判断基于事实，事实不许混进来）──
    claim_ids = set()
    for c in content.get("claims", []):
        cid = c.get("id")
        if not cid or not c.get("statement"):
            problems.append(f"claim {cid or '?'} 缺 id / statement")
            continue
        claim_ids.add(cid)
        if c.get("type") not in CLAIM_TYPES:
            problems.append(f"claim {cid}.type={c.get('type')!r} "
                            f"不在 {list(CLAIM_TYPES)}")
        dangling = [d for d in c.get("derivedFrom", []) if d not in fact_ids]
        if dangling:
            problems.append(f"claim {cid}.derivedFrom {dangling} 指向不存在的 fact")
        conf = c.get("confidence")
        if conf is not None and (not isinstance(conf, (int, float))
                                 or isinstance(conf, bool) or not 0 <= conf <= 1):
            problems.append(f"claim {cid}.confidence={conf!r} 应在 [0,1]")

    # v3.0 §21：message 可挂 claimId（挂了就要能解析）
    for m in messages:
        cid = m.get("claimId")
        if cid is not None and cid not in claim_ids:
            problems.append(f"message {m.get('id', '?')}.claimId={cid!r} "
                            f"指向不存在的 claim")
    return problems, notes


# ═══════════════════════════════════════════════════════════════════════════
# ② Storyline：骨架符合度 + 配额自洽
# ═══════════════════════════════════════════════════════════════════════════

def check_storyline(story: dict) -> list[str]:
    problems: list[str] = []
    archetype = story.get("archetype")
    if archetype not in ARCHETYPES:
        problems.append(f"archetype={archetype!r} 不在预定义骨架里（可选 "
                        f"{sorted(ARCHETYPES)}）—— 自由发挥的故事结构没有逻辑保证")
        return problems
    roles = ARCHETYPES[archetype]["roles"]
    beats = sorted(story.get("beats", []), key=lambda b: b.get("order", 0))
    beat_roles = [b.get("role") for b in beats]
    # beat 的 role 必须都存在于骨架，且**出现顺序**符合骨架（允许跳过角色，
    # 不允许乱序 —— "先讲方案再讲问题"不是自由，是错）
    unknown = [r for r in beat_roles if r not in roles]
    if unknown:
        problems.append(f"beats 里的角色 {unknown} 不属于 {archetype} 骨架（其角色："
                        f"{roles}）")
    known = [r for r in beat_roles if r in roles]
    if known != sorted(known, key=roles.index):
        problems.append(f"beats 的顺序不符合 {archetype} 骨架（{known}）—— "
                        f"骨架的意义就是逻辑递进，跳过可以，乱序不行")
    sections = story.get("sections", [])
    total = story.get("target_slide_count")
    if total:
        got = sum(s.get("target_slides", 0) for s in sections)
        if got and got != total:
            problems.append(f"sections 的页数加起来是 {got}，target_slide_count 是 "
                            f"{total} —— 「15 页做成 28 页」就是这条漏的")
    weights = sum(s.get("weight", 0) for s in sections)
    if sections and abs(weights - 1.0) > 0.02:
        problems.append(f"sections 的权重加起来是 {weights:.2f}，不是 1.0")
    return problems


# ═══════════════════════════════════════════════════════════════════════════
# ③ Page Planner：页型合法 + 配额对齐 + 拆页判断
# ═══════════════════════════════════════════════════════════════════════════

def check_pageplan(pageplan: dict, story: dict | None = None) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    notes: list[str] = []
    pages = pageplan.get("pages", [])
    if not pages:
        problems.append("pageplan.json 里没有 pages")
    for p in pages:
        pt = p.get("page_type")
        if pt not in PAGE_TYPES:
            problems.append(f"page {p.get('page_id', '?')}.page_type={pt!r} 不在页型表里"
                            f"（可选 {sorted(PAGE_TYPES)}）")
        if p.get("density") not in ("sparse", "medium", "dense", None):
            problems.append(f"page {p.get('page_id', '?')}.density={p.get('density')!r} "
                            f"不认识（sparse / medium / dense）")
        # 拆页判断（确定性）：AI 标了 split 但复杂度没到 → 提示；复杂度到了但没拆 → 错
        need, score = should_split(p)
        if need and not p.get("split"):
            problems.append(f"page {p.get('page_id', '?')} 复杂度 {score:.2f} ≥ "
                            f"{SPLIT_THRESHOLD} 但没标 split —— 硬塞是 AI PPT 最典型的"
                            f"爆法；拆成两页（页数没有上限，挤在一页才是问题）")
        if p.get("split") and not need:
            notes.append(f"page {p.get('page_id', '?')} 标了 split 但复杂度只有 "
                         f"{score:.2f} —— 拆得太碎也会散")
    if story and pages:
        # 页数必须对齐 storyline 的配额（这是"节奏可控"的落点）
        total = story.get("target_slide_count")
        if total and len(pages) != total:
            problems.append(f"pageplan 有 {len(pages)} 页，storyline 定的是 {total} 页 —— "
                            f"规划层的配额到执行层就丢了")
    return problems, notes


# ═══════════════════════════════════════════════════════════════════════════
# ③→④ 桥：pageplan + content → deck-spec.json（确定性映射）
#
# 这是规划层与渲染层的**唯一接口**：产出的 spec 必须能过 validate_spec，
# 这条由测试钉死（规划层产出的东西渲染器吃不下 = 全白写）。
# ═══════════════════════════════════════════════════════════════════════════

# 页型里带图表的 → chart DSL 的 intent
_PAGE_CHART_INTENT = {"metric": "progress", "comparison": "comparison",
                      "trend": "trend", "composition": "composition"}


def to_spec(pageplan: dict, content: dict, style: str = "swiss-grid",
            color_set: str | None = None) -> dict:
    """把 pageplan + content 映射成 deck-spec.json（确定性，无判断）。"""
    messages = {m.get("id"): m for m in content.get("messages", [])}
    metrics = {m.get("id"): m for m in content.get("metrics", [])}
    slides: list[dict] = []
    for p in pageplan.get("pages", []):
        pt = p.get("page_type")
        if pt not in PAGE_TYPES:
            raise SystemExit(f"✗ page {p.get('page_id')}.page_type={pt!r} 不在页型表里")
        row = PAGE_TYPES[pt]
        msg = messages.get(p.get("message_ref"), {})
        headline = p.get("message") or msg.get("statement") or ""
        if not str(headline).strip():
            raise SystemExit(f"✗ page {p.get('page_id')} 没有 message —— "
                             f"一页不知道自己在讲什么，就没法排版")
        base: dict = {"title": str(headline)[:48]}   # dict：值既有 str 也有 list
        if row["layout"] == "chart":
            base["type"] = "chart"
            base["chart"] = row.get("chart", "bar")
            if pt in _PAGE_CHART_INTENT:
                base["intent"] = _PAGE_CHART_INTENT[pt]
            base["message"] = str(headline)
            metric = metrics.get(p.get("metric_ref"))
            if metric:
                base["unit"] = str(metric.get("unit", ""))
                base["data"] = [{"label": str(metric.get("label", "值")),
                                 "value": metric.get("value", 0)}]
            elif p.get("data"):
                base["data"] = p["data"]
            else:
                raise SystemExit(f"✗ page {p.get('page_id')} 是图表页但没有数据"
                                 f"（metric_ref 或 data 二选一）")
        elif row["layout"] == "timeline":
            base["type"] = "timeline"
            base["nodes"] = p.get("nodes") or [
                {"label": str(n.get("label", "")), "note": str(n.get("note", ""))}
                for n in p.get("structure", [])]
        elif row["layout"] == "two-column":
            base["type"] = "two-column"
            cols = p.get("columns") or []
            base["columns"] = [{"title": str(c.get("title", "")),
                                "bullets": [str(b) for b in c.get("bullets", [])]}
                               for c in cols]
        elif row["layout"] == "content-image":
            base["type"] = "content-image"
            if not p.get("image"):
                raise SystemExit(f"✗ page {p.get('page_id')} 是图页但没有 image 文件名")
            base["image"] = p["image"]
            base["bullets"] = [str(b) for b in p.get("bullets", [])]
        else:
            base["type"] = "content-text"
            base["bullets"] = [str(b) for b in p.get("bullets", [])]
        if p.get("image") and base["type"] != "content-image":
            notes_img = p.get("image")
            if base["type"] == "content-text":
                base["type"] = "content-image"
                base["image"] = notes_img
        slides.append(base)
    if not slides:
        raise SystemExit("✗ pageplan 里没有可用页")
    # 封面与收尾：storyline 的第一个 beat 是 context/goal 类 → 封面用 deck 标题
    deck: dict = {"title": content.get("topic") or "演示", "style": style,
                  "slides": slides}
    if color_set:
        deck["colorSet"] = color_set
    else:
        # load_style 返回 {tokens, skin} —— 要取 tokens 那层（这里曾少取一层，
        # KeyError: colorSets）。
        render = _load_sibling("render")
        tokens = render.load_style(style)["tokens"]
        deck["colorSet"] = next(iter(tokens["colorSets"]))
    return {"deck": deck}


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="规划层：内容理解 / Storyline / Page Planner")
    ap.add_argument("--archetypes", action="store_true", help="列出十个叙事骨架")
    ap.add_argument("--page-types", action="store_true", help="列出页型 → 版式映射")
    ap.add_argument("--check", nargs=3, metavar=("CONTENT", "STORYLINE", "PAGEPLAN"),
                    help="校验三份 JSON（引用完整 / 骨架符合 / 配额自洽）")
    ap.add_argument("--to-spec", nargs=2, metavar=("PAGEPLAN", "CONTENT"),
                    help="映射成 deck-spec.json（过 validate_spec 才算数）")
    ap.add_argument("--style", default="swiss-grid")
    ap.add_argument("-o", "--out", default=None)
    args = ap.parse_args(argv[1:])

    if args.archetypes:
        for key, row in ARCHETYPES.items():
            print(f"{key:26} {row['label']}")
            print(f"{'':26} {' → '.join(row['roles'])}")
            print(f"{'':26} 适合：{row['fits']}")
        return 0

    if args.page_types:
        for key, row in PAGE_TYPES.items():
            chart = f" chart={row['chart']}" if row.get("chart") else ""
            print(f"{key:16} → {row['layout']:<14} visual={row['visual']}{chart}")
            print(f"{'':16} {row['why']}")
        return 0

    if args.check:
        content = deckio.read_json(args.check[0])
        story = deckio.read_json(args.check[1])
        pageplan = deckio.read_json(args.check[2])
        failed = 0
        for name, probs in (("内容理解", check_content(content)[0]),
                            ("Storyline", check_storyline(story)),
                            ("Page Planner", check_pageplan(pageplan, story)[0])):
            for p in probs:
                print(f"✗ [{name}] {p}")
                failed += 1
        for name, notes in (("内容理解", check_content(content)[1]),
                            ("Page Planner", check_pageplan(pageplan, story)[1])):
            for n in notes:
                print(f"· [{name}] {n}")
        print("✓ 三份规划全部自洽" if not failed else f"✗ {failed} 个问题")
        return 1 if failed else 0

    if args.to_spec:
        pageplan = deckio.read_json(args.to_spec[0])
        content = deckio.read_json(args.to_spec[1])
        spec = to_spec(pageplan, content, style=args.style)
        out = args.out or "deck.spec.json"
        deckio.write_text(out, __import__("json").dumps(spec, ensure_ascii=False, indent=1))
        print(f"✓ {out}（{len(spec['deck']['slides'])} 页）—— 记得过 validate_spec")
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
