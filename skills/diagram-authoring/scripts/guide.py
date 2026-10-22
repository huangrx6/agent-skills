#!/usr/bin/env python3
"""按表达意图、图型信号推荐起手方案。推荐不是事实判断。

语义模式优先；多个模式命中时保留候选，由作者结合上下文选择。
只有无法从材料消除且影响产物的歧义才询问用户。不按关键词删改内容。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys


def _load_sibling(name: str):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"_guide_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了同目录模块：{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


L = _load_sibling("layout")
A = _load_sibling("authoring")

# ── 场景目录 ────────────────────────────────────────────────
# signals: (词, 权重)。中英混排，全小写匹配；权重刻画「这个词出现时它有多像这个类型」。
# include: 推荐输出里给作者的起手清单（内容层，不是布局参数 —— 那些是脚本的活）。
SCENARIOS: dict[str, dict] = {
    "architecture": {
        "signals": [
            ("架构", 10), ("architecture", 10), ("组件", 6), ("component", 6),
            ("服务", 4), ("service", 4), ("系统", 5), ("system", 4),
            ("部署", 6), ("deployment", 6), ("拓扑", 8), ("topology", 8),
            ("边界", 5), ("boundary", 5), ("网关", 4), ("gateway", 4),
            ("微服务", 8), ("microservice", 8),
        ],
        "question": "系统里有什么、彼此怎么连接？",
        "include": ["本次问题必需的核心组件（不设硬性数量上限）", "一条主路径", "外部依赖", "边界（用 groups 圈）",
                    "支撑细节放 cards，不堆节点"],
    },
    "flow": {
        "signals": [
            ("流程", 12), ("workflow", 10), ("步骤", 8), ("step", 5),
            ("先", 3), ("然后", 4), ("接着", 4), ("审批", 8), ("approval", 8),
            ("回退", 6), ("rollback", 6), ("失败", 3), ("分支", 5),
            ("流程图", 14), ("runbook", 8), ("ci/cd", 8), ("pipeline", 6),
        ],
        "question": "一件事按什么顺序发生、在哪里分岔？",
        "include": ["一条主路径（其余分支从最近的节点出发）", "判断/分支用 diamond 形状",
                    "异常动作与恢复入口；仅真实边界才用分组", "每步一句动词短语"],
    },
    "dependency": {
        "signals": [
            ("依赖", 14), ("dependency", 12), ("depend", 8), ("引用", 6),
            ("import", 6), ("模块依赖", 12), ("包依赖", 12), ("分层", 5),
            ("谁用谁", 8), ("耦合", 6),
        ],
        "question": "谁依赖谁、层级怎么叠？",
        "include": ["一个节点 = 一个模块/包", "边只表达「依赖」一种语义",
                    "确有层级约束时用 rank", "循环依赖保留原方向，布局内部临时断环"],
    },
    "state": {
        "signals": [
            ("状态", 12), ("state", 10), ("状态机", 14), ("生命周期", 10),
            ("lifecycle", 10), ("重试", 8), ("retry", 8), ("等待", 6),
            ("终态", 10), ("terminal", 8), ("转移", 8), ("transition", 8),
        ],
        "question": "一个东西会经历哪些状态、怎么流转？",
        "include": ["一个节点 = 一个状态（不是动作）", "边写触发事件",
                    "终止/失败语义写清标签；emphasis 只表达阅读重点", "支持不同节点间回边，暂不支持自环"],
    },
    "network": {
        "signals": [
            ("网状", 12), ("网络拓扑", 12), ("network", 10), ("集群", 6),
            ("cluster", 6), ("节点间互连", 10), ("mesh", 10), ("对等", 6),
            ("没有明显层级", 8), ("多对多", 8),
        ],
        "question": "一堆对等的东西怎么连？",
        "include": ["节点 = 对等实体", "没有主路径，emphasis 只给真正的枢纽",
                    "边多时靠 detail 控制标签量"],
    },
    "mindmap": {
        "signals": [
            ("思维导图", 14), ("脑图", 14), ("mindmap", 12), ("知识体系", 8),
            ("大纲", 8), ("树状", 8), ("中心", 6), ("分支展开", 8),
            ("主题", 5),
        ],
        "question": "一个中心概念怎么展开成树？",
        "include": ["第一个节点即根", "子主题按层展开", "叶子上放细节（detail）"],
    },
}


# 用户已经把方向说出口时，不要让类型默认值盖过它。只认明确的排版词，
# 不把“上下文”“上下班”之类的日常词误判成 TB。
DIRECTION_CUES = {
    "LR": ("横向", "横着", "横屏", "水平", "从左到右", "左到右", "left to right", "horizontal"),
    "TB": ("纵向", "竖着", "竖排", "竖屏", "垂直", "从上到下", "上到下", "top to bottom", "vertical"),
}


def _negated(text: str, index: int) -> bool:
    prefix = text[max(0, index - 6):index]
    return any(prefix.endswith(word) for word in
               ("不", "不要", "不用", "别", "不是", "而非", "不想"))


def direction_cue(text: str) -> str | None:
    """从描述里读显式方向；跳过“不要竖着”这类否定，同时出现时取最先的肯定项。"""
    lowered = text.lower()
    hits = [(lowered.find(cue), direction)
            for direction, cues in DIRECTION_CUES.items() for cue in cues
            if cue in lowered and not _negated(lowered, lowered.find(cue))]
    return min(hits)[1] if hits else None


def score(scenario: str) -> list[tuple[str, int]]:
    """按信号词打分，返回按分数降序的 (类型, 分数)。"""
    text = scenario.lower()
    hits = {name: 0 for name in SCENARIOS}
    terms: dict[str, set[str]] = {name: set() for name in SCENARIOS}
    for name, entry in SCENARIOS.items():
        for word, weight in entry["signals"]:
            if word.lower() in text:
                hits[name] += weight
                terms[name].add(word)
    ranked = sorted(hits.items(), key=lambda kv: (-kv[1], kv[0]))
    return ranked


def _recommend_type(scenario: str) -> dict:
    """推荐一个图型；分不出胜负时如实说「这几个都像」。"""
    ranked = score(scenario)
    top_name, top_score = ranked[0]
    if top_score == 0:
        return {
            "recommended": None,
            "candidates": [],
            "why": "没有命中任何信号词 —— 把要回答的问题说得更具体一点，"
                   "或直接告诉脚本图型。",
        }
    tied = [name for name, s in ranked if s == top_score]
    entry = SCENARIOS[top_name]
    return {
        "recommended": top_name if len(tied) == 1 else None,
        "candidates": tied,
        "direction": L.DIRECTION_FOR_TYPE.get(top_name, "LR"),
        "question": entry["question"],
        "include": entry["include"],
        "why": (f"命中信号词 {len(SCENARIOS[top_name]['signals'])} 组里得分最高（{top_score} 分）"
                if len(tied) == 1 else
                f"{('、'.join(tied))} 同分（{top_score}）—— 这几个类型都像，结合材料选择："),
    }


def recommend(scenario: str, *, pattern: str | None = None,
              audience: str = "mixed", preset: str = "doc-inline") -> dict:
    if pattern is not None and pattern not in A.PATTERNS:
        raise ValueError(f"未知表达模式：{pattern}")
    if audience not in A.AUDIENCES or preset not in A.PRESETS:
        raise ValueError("未知受众或输出场景")
    text = scenario.lower()
    unsupported = [name for name, signals in {
        "sequence": ("时序图", "sequence diagram"),
        "swimlane": ("泳道图", "swimlane"),
        "er": ("er 图", "er图", "实体关系图", "er diagram"),
    }.items() if any(signal in text for signal in signals)]
    rec = _recommend_type(scenario)
    matches = [name for name, entry in A.PATTERNS.items()
               if any(signal in text for signal in entry["signals"])]
    selected = pattern or (matches[0] if len(matches) == 1 else None)
    if selected:
        entry = A.PATTERNS[selected]
        rec.update(recommended=entry["type"], candidates=[entry["type"]],
                   direction=L.DIRECTION_FOR_TYPE[entry["type"]],
                   question=entry["question"], include=list(entry["required"]),
                   why=f"表达模式：{entry['name']}；须对照实际材料确认。",
                   avoid=entry["avoid"])
    if unsupported:
        rec.update(recommended=None, candidates=[],
                   why="请求含当前生成器尚不支持的专用图型；不能把普通节点图冒充该图型。")
    cue = direction_cue(text)
    if cue and rec.get("recommended") in L.DIRECTION_FOR_TYPE:
        rec["direction"] = cue
    rec["direction_explicit"] = bool(cue and rec.get("recommended") in L.DIRECTION_FOR_TYPE)
    rec.update(pattern=selected, pattern_candidates=matches,
               unsupported_types=unsupported, audience=audience,
               audience_guidance=A.AUDIENCES[audience], preset=preset,
               display_target=dict(A.PRESETS[preset]),
               type_reference="references/type-guides.md",
               semantic_reference="references/semantic-patterns.md" if selected or matches else None)
    return rec


def starter_prompt(rec: dict, scenario: str) -> str:
    """给作者的起手骨架：推荐类型 + include 清单 + 原话。"""
    name = rec.get("recommended") or "<从候选里挑一个>"
    include = "\n".join(f"  - {item}" for item in rec.get("include", []))
    direction = rec.get("direction")
    direction_note = "来自你的方向描述" if rec.get("direction_explicit") else "只是默认值"
    direction_line = (f"方向起手：{direction}（{direction_note}；按内容和媒介可用 direction 改成 LR/TB）。\n"
                      if direction else "")
    return (f"用 {name} 画：{scenario}\n"
            f"要包含：\n{include}\n"
            f"{direction_line}"
            f"先明确读者要理解的问题；intent 可记录 question/audience/pattern。\n"
            f"受众：{rec.get('audience', 'mixed')}；观看场景：{rec.get('preset', 'doc-inline')}。\n"
            "规格不写坐标、颜色、字号；生成后运行语义检查和场景可读性检查。")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="场景 → 图型推荐（信号词打分，不硬选）")
    ap.add_argument("scenario", help="用一句话描述你要画什么")
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    ap.add_argument("--pattern", choices=tuple(A.PATTERNS))
    ap.add_argument("--audience", choices=tuple(A.AUDIENCES), default="mixed")
    ap.add_argument("--preset", choices=tuple(A.PRESETS), default="doc-inline")
    args = ap.parse_args(argv)

    rec = recommend(args.scenario, pattern=args.pattern, audience=args.audience, preset=args.preset)
    if args.json:
        print(json.dumps({"scenario": args.scenario, **rec,
                          "starter_prompt": starter_prompt(rec, args.scenario)},
                         ensure_ascii=False, indent=2))
        return 0

    print(f"场景：{args.scenario}")
    print(f"观看目标：{args.preset}；受众：{args.audience}。{rec['audience_guidance']}")
    if rec["pattern_candidates"]:
        print("表达模式候选：" + "、".join(rec["pattern_candidates"]))
    if rec.get("avoid"):
        print("注意：" + rec["avoid"])
    if rec["recommended"]:
        print(f"推荐图型：{rec['recommended']}（默认方向 {rec['direction']}）")
        print(f"它回答的问题：{rec['question']}")
        print(f"判据：{rec['why']}")
        print("起手清单：")
        for item in rec["include"]:
            print(f"  - {item}")
        print()
        print("起手 prompt：")
        print(starter_prompt(rec, args.scenario))
    else:
        print(f"还定不下来：{rec['why']}")
        for name in rec["candidates"]:
            entry = SCENARIOS[name]
            print(f"  - {name}：{entry['question']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
