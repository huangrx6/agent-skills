#!/usr/bin/env python3
"""图型场景路由器 —— 「这段描述该画成哪种图」的机械判据（模仿 archify 的 guide）。

## 为什么做成命令而不是 SKILL.md 里的一张表

类型判断目前写在 SKILL.md 的策略表里，靠模型对照执行。archify 把这件事做成了
`archify guide "<scenario>"`：信号词打分 + 稳定输出。照搬到本 skill 的收益：

- **判据可执行**：打分表在脚本里，同一句话永远得到同一个推荐 —— 模型对照表格
  「自己挑」没有这个保证；
- **低上下文**：模型拿不准时跑一条命令，不用把整张表读进上下文；
- **输出即起手**：推荐里带 include 清单与起手 prompt 骨架，直接接规格书写。

## 打分不是判断

每个类型有一组（中英）信号词与权重；命中最多的类型胜出，**平分或全零时不硬选**，
而是把最像的几个列出来让用户挑 —— 与「先让用户挑主题」同一条哲学：
宁可多问一句，不替用户做他没说的事。

用法：
    python3 scripts/guide.py "下单后先校验库存，库存够就调支付网关，失败回购物车"
    python3 scripts/guide.py "Kafka topics 与消费者组的血缘" --json
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
        "include": ["6~12 个核心组件", "一条主路径", "外部依赖", "边界（用 groups 圈）",
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
                    "异常路径用 critical 区域圈出来", "每步一句动词短语"],
    },
    "dependency": {
        "signals": [
            ("依赖", 14), ("dependency", 12), ("depend", 8), ("引用", 6),
            ("import", 6), ("模块依赖", 12), ("包依赖", 12), ("分层", 5),
            ("谁用谁", 8), ("耦合", 6),
        ],
        "question": "谁依赖谁、层级怎么叠？",
        "include": ["一个节点 = 一个模块/包", "边只表达「依赖」一种语义",
                    "层级深的用 rank 固定", "循环依赖会断环处理，如实标注"],
    },
    "state": {
        "signals": [
            ("状态", 12), ("state", 10), ("状态机", 14), ("生命周期", 10),
            ("lifecycle", 10), ("重试", 8), ("retry", 8), ("等待", 6),
            ("终态", 10), ("terminal", 8), ("转移", 8), ("transition", 8),
        ],
        "question": "一个东西会经历哪些状态、怎么流转？",
        "include": ["一个节点 = 一个状态（不是动作）", "边写触发事件",
                    "终态/失败态用 emphasis 标", "回边是常态，别怕环"],
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


def recommend(scenario: str) -> dict:
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
                f"{('、'.join(tied))} 同分（{top_score}）—— 这几个类型都像，挑一个："),
    }


def starter_prompt(rec: dict, scenario: str) -> str:
    """给作者的起手骨架：推荐类型 + include 清单 + 原话。"""
    name = rec.get("recommended") or "<从候选里挑一个>"
    include = "\n".join(f"  - {item}" for item in rec.get("include", []))
    return (f"用 {name} 画：{scenario}\n"
            f"要包含：\n{include}\n"
            f"规格里只写结构（节点/边/分组），不写坐标、颜色、字号 —— 布局由脚本算。")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="场景 → 图型推荐（信号词打分，不硬选）")
    ap.add_argument("scenario", help="用一句话描述你要画什么")
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    args = ap.parse_args(argv)

    rec = recommend(args.scenario)
    if args.json:
        print(json.dumps({"scenario": args.scenario, **rec,
                          "starter_prompt": starter_prompt(rec, args.scenario)},
                         ensure_ascii=False, indent=2))
        return 0

    print(f"场景：{args.scenario}")
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
