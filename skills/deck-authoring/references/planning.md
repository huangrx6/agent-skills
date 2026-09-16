# 规划层：内容理解 → Storyline → Page Planner → Slide DSL

这一层回答四个问题，**每层只回答一个**。说什么/为什么这样说的**规则**（Brief、
Core Thesis、一页一 Takeaway、数字优先……）见 `content-intelligence.md`（内容智能 / 内容规划系统）；本篇是模块文档：
schema、骨架表、检查与自查（**`plan.py` v4 已删**，规划层不再有校验 CLI）。

```text
① content.json   「我们知道什么」        事实 / 观点 / 数字 / 关系
② storyline.json 「按什么顺序讲」        骨架 + 节奏
③ pageplan.json  「每页怎么表达」        页型 / 主视觉 / 密度 / 拆页
④ deck-spec.json 「怎么描述给渲染器」    ←—— 既有的 Slide DSL（224 条测试护着）
```

## 越靠近渲染，AI 自由度越低

这是这一层最重要的工程原则（规范定的，本模块的形状就是它的落地）：

| 层 | AI 自由度 | 程序确定性 |
| --- | --- | --- |
| 内容理解 | 中 | Schema + 引用完整性 + 事实/推断分离 |
| Storyline | 中 | archetype 骨架成文 + 权重→页数配额必须自洽 |
| Page Planner | 低~中 | 复杂度评分 + 拆页阈值 + 页型→版式映射 |
| Slide DSL | 很低 | 封闭字段集（`validate_spec.py`） |
| Layout / 渲染 | 0 | `grid.py` / `render.py` |

最容易踩的坑是让四层都自由生成自然语言 —— 那样产出的东西渲染器吃不下，
校验也无处下手。

> v4 说明：规划三层（内容理解 / Storyline / Page Planner）原先由 `plan.py` 做的那几项
> 确定性校验已随脚本删除 —— 表中这几格的"程序确定性"现在退化为**自查**；
> 只有 Slide DSL 的封闭字段集（`validate_spec.py`）与 Layout / 渲染仍是程序保证。

## 为什么从后往前建（已经走完了）

规范建议的开发顺序：Schema → Renderer → Layout → Page Planner → Storyline →
内容理解。本仓库天然满足：**渲染链先稳定**（224 条测试），规划层才有一个明确
的目标 —— 产出一份能过 `validate_spec` 的 `deck-spec.json`。反过来先写 AI
Agent，产出的东西渲染器吃不下，就全白写。

## ① 内容理解（content.json）

把原始材料变成**可用于 PPT 的结构化事实库**。这一层不考虑颜色、布局、页数。

```json
{
  "topic": "统一 AI 能力平台建设",
  "document_intent": "solution_proposal",
  "facts": [
    {"id": "fact_01", "type": "problem", "text": "模型资源分散",
     "source_type": "original", "source_ref": "doc_01:p2"}
  ],
  "metrics": [{"id": "m_01", "label": "运维工时降幅", "value": 60, "unit": "%"}],
  "messages": [
    {"id": "msg_01", "statement": "当前模型服务分散，缺乏统一管理能力",
     "importance": 0.95, "evidence_refs": ["fact_01", "fact_02"]}
  ],
  "entities": ["DeepSeek", "Qwen"],
  "relationships": [{"from": "平台", "relation": "解决", "to": "纳管/调用/监控"}]
}
```

**两条硬规矩（自查，不再有脚本拦）**：

1. **事实与推断必须分开**（`source_type ∈ original / inferred / generated`）。
   不分开的后果：PPT 把 AI 自己推断出来的话当成事实讲。
2. **引用必须可解析**：message 的 `evidence_refs` 指向不存在的 fact → 错。
   悬空引用的证据不是证据。

**一条自查提示**：一条重要性 ≥0.9 的 message，证据却全是 `inferred` →
"你在把 AI 推断的话当事实讲；要么找到原文证据，要么降重要性"。为什么只是
提示：推断也可以是结论（预测本来就是推断），但高重要性结论值得知道自己的
证据是什么成色。

内部建议拆三个动作（AI 做，规范定的）：**Extraction**（抽事实）→
**Normalization**（去重、统一名称与数字）→ **Semantic Structuring**（建观点、
关系、证据）。不要一句"帮我分析这篇文章"全黑盒。

## ② Storyline（storyline.json）

把知识点排列成**有逻辑的顺序**。这一层不生成页面。

```json
{
  "archetype": "problem_solution",
  "target_slide_count": 15,
  "beats": [
    {"order": 1, "role": "context", "message_ref": "msg_01"},
    {"order": 2, "role": "problem",  "message_ref": "msg_02"}
  ],
  "sections": [
    {"name": "背景与问题", "weight": 0.2, "target_slides": 3},
    {"name": "解决方案",   "weight": 0.4, "target_slides": 6}
  ]
}
```

**骨架是预定义的**（下表列全），不让 LLM 自由写故事 ——
自由发挥的故事结构没有逻辑保证。十个骨架：

| 骨架 | 顺序 | 适合 |
| --- | --- | --- |
| problem_solution | 情境→问题→影响→目标→方案→架构→能力→实施→价值→下一步 | 技术方案、立项 |
| scr | 情境→冲突→解法→证据→下一步 | 汇报、说服 |
| past_present_future | 过去→现在→未来→含义→下一步 | 战略、展望 |
| why_what_how | 为什么→是什么→怎么做→证明→下一步 | 产品、理念 |
| goal_progress_result | 目标→进展→结果→差距→下一步 | 项目、OKR |
| overview_detail_evidence | 总览→细节→证据→小结 | 评审、研究 |
| product_capability_value | 用户问题→机会→定位→能力→用法→差异→案例→价值 | 产品、售前 |
| incident_review | 时间线→影响→根因→修复→预防 | 事故复盘 |
| tech_proposal | 背景→问题→目标→总体设计→架构→模块→部署→安全→性能→收益→计划 | 架构评审 |
| project_report | 目标→完成→成果→数据→问题→风险→下一步 | 周报月报 |

**三条硬规矩（自查）**：

1. beats 的 role **允许跳过、不许乱序**（"先讲方案再讲问题"不是自由，是错）；
2. sections 的 `target_slides` 加起来 == `target_slide_count`
   —— **"15 页做成 28 页"就是这条漏的**；
3. weights 加起来 ≈ 1.0。

## ③ Page Planner（pageplan.json）

到这一层才回答"这一页长什么样"。输入是 storyline beat + 对应事实 + 页数配额，
输出是**页的意图**（不是坐标）。

```json
{
  "pages": [
    {"page_id": "p02", "section": "背景与问题", "message_ref": "msg_01",
     "page_type": "comparison", "density": "medium",
     "data": [{"label": "DeepSeek", "value": 86}],
     "emphasis": {"values": ["DeepSeek"]}}
  ]
}
```

**页型 → 版式是查表**（下表），AI 判页型、程序决定用哪个
版式画：

| 页型 | 版式 | 主视觉 |
| --- | --- | --- |
| statement | content-text | 无（靠字与留白） |
| metric | chart（donut + progress） | 大数字（环图中心） |
| comparison / trend / composition | chart（bar / line / stacked） | 图表 |
| process | timeline | 时间线 |
| capabilities | two-column | 无（两组并列） |
| hero_visual / context_image | content-image | 图 |
| evidence | content-text | 无（读的页，密一点可以） |

**复杂度评分与拆页**（确定性公式；原来 `plan.py` 据此落门，**脚本 v4 已删，现在靠自查**）：

```text
复杂度 = 字符数/120 + 节点数×0.12 + 图表×0.25 + 图×0.15 + (层级-1)×0.10
复杂度 ≥ 0.70 就该考虑拆页（"一页塞下架构+五个能力+三个优势+拓扑"
                        是 AI PPT 最典型的爆法）
内容很轻却标了 split   → 拆得太碎也会散
```

页数还必须对齐 storyline 的配额 —— 配额到执行层不许丢，这是"节奏可控"的落点。

## ③→④ 桥：从 pageplan 写 deck-spec

原先这一步是 `plan.py --to-spec` 的**确定性映射**（把 pageplan 的 `metric_ref`
解析成图表数据、`process` 带成 timeline 节点……）；**`plan.py` v4 已删，映射改由
AI 自己写**。原来的几条硬约束仍然成立，但**不再有脚本替你把关**，得自己守：

- 图表页必须有数据（`data`，或 `series`）—— 空数据的图表页是空的；
- 图页必须有 `image`（这条 `validate_spec.py` 仍拦：`REQUIRED_SLIDE_FIELDS`）；
- **页没有 message → 不要写**（一页不知道自己在讲什么，就没法排版）。

```bash
python3 scripts/validate_spec.py deck.spec.json     # 字段集封闭：未知键直接失败
python3 scripts/check.py deck.spec.json out.html    # 产物实测门
```

写出的 spec 直接进既有渲染链（render / check / pdf / pptx / animate 全部可用）。

## 还没做的（写清楚，别假装做了）

1. **从原始文档抽取 content.json**（Word/PDF/网页 → 事实库）—— 现在这一步是
   AI 照着 Schema 写（**`plan.py` v4 已删，连校验脚本都没有了**）。抽取管线
   （格式解析、去重、指代消解）是单独的一块工程。
2. **页型候选打分**（规范里的 candidates + score）—— 现在是 AI 直接定页型，
   打分排序那层没做。
3. **architecture 页型**（分层架构图）—— 页型表里**故意没有**它：渲染器没有
   架构图版式，映射过去就是死路。等图形版式落地再加。
4. **自动拆页策略**（split_strategy 建议拆成哪两页）—— 现在只判"该不该拆"，
   怎么拆是人的判断。
