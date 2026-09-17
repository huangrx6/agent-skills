# AI PPT 内容智能与规划系统（Content Intelligence）

> 命名升级：这一层不再叫单纯的"内容设计"——它是一套**内容智能 / 内容规划系统**
> ：从原始材料到"每页唯一 Takeaway"的完整规划链（理解 → 论证 → 叙事 → 页规划）。
> "设计"只是它的最后一步（交给视觉系统）。

适用：内容规划层（PPT / HTML Deck / PDF / MP4 / GIF 共用）。核心目标：把原始材料
从"信息集合"转化为**有目标、有论证、有证据、有节奏、可设计**的演示内容。
本规则只负责**说什么、为什么这样说、每页该让观众记住什么**；坐标、颜色、字体、
动效、图片文件由 Page Planner / Layout / Style / Chart / Image / Motion 接管。

> 字段口径：本文 JSON 示例是规范推荐形（camelCase）；本仓库 schema 用 snake_case
> （`source_ref` / `source_type`），fact 的 `inferred` 即规范的 `derived` 语义，
> claim 的 `type` 用 `original | derived`。执行标记：【拦】= 硬约束（按本文自查），
> 【提示】= 开口不拦。
> schema 全表见 `planning.md`。

## 0. 核心原则

```text
Audience / Goal → Desired Action → Core Thesis → Facts & Evidence → Claims
  → Storyline → Section Messages → Slide Message → Display Copy
  → Visual Requirement → Page Planner → Design / Render
```

先明确观众最终要**做什么**，再决定他需要**相信什么**；用事实和证据形成论证；
把论证拆成每页唯一 Takeaway；最后才进页面设计。优秀的 PPT 不是把资料压缩后排漂亮。

## 1. 模块职责（四层）

| 层 | 负责 | 回答 |
| --- | --- | --- |
| Content Understanding | 抽取事实/数字/时间/实体/关系/问题/原因/方案/结果/风险/证据，建立来源追踪 | 我们到底知道什么 |
| Storyline | Core Thesis、叙事骨架、Section、页序、节奏、页数、防断层 | 按什么顺序说 |
| Slide Content Planning | 每页唯一 Message、Claim+Evidence 绑定、压缩、信息预算、视觉需求、拆页、附录 | 这一页让观众记住什么 |
| Content QA | 事实一致性、来源、无证据结论、重复、断点、焦点、受众、过载、完整性 | 够不够清楚可信完整 |

## 2. Presentation Brief【缺 desiredAction/desiredBelief=拦；枚举=拦；缺席=提示】

```json
{"purpose": "proposal", "audience": "technical", "delivery": "live",
 "targetSlides": 15, "durationMinutes": 20,
 "desiredAction": "批准统一 AI 平台建设方案",
 "desiredBelief": "统一平台建设现在有必要且可实施",
 "audienceKnows": [], "audienceNeeds": [], "constraints": []}
```

最重要的字段是 **desiredAction**：PPT 放完观众要做什么。推不出来至少推断
desiredBelief。purpose ∈ decision/proposal/report/update/training/sales/explanation/review；
audience ∈ executive/technical/customer/internal/general；delivery ∈ live/async/printable/editable。

## 3. Audience Model（同一份材料按观众重组）

| 观众 | 优先 | 降低 |
| --- | --- | --- |
| Executive | 结论、影响、成本、风险、决策、ROI、时间计划 | 参数、技术细节、代码、底层实现 |
| Technical | 架构、接口、资源、性能、依赖、部署、兼容、运维、风险 | 营销话术 |
| Customer | 问题、价值、方案、使用方式、案例、交付、收益 | 内部实现细节 |
| Training | 概念、步骤、原理、示例、易错点、总结 | 跳步、术语堆砌 |

## 4. 原始内容类型

一句话 / Word / PDF / Markdown / Excel / 网页 / 数据库导出 / 多份材料 / 历史 deck /
截图表格。Content Understanding **不得因文件类型不同改变最终语义结构**。

## 5. 四类核心内容对象（不得混用）

**Fact**（材料明确存在的）：
`{"id": "fact_021", "type": "problem", "text": "部署 8 个模型服务，5 个接口协议不一致", "source_type": "original", "source_ref": "doc01:p8", "confidence": 1.0}`

**Claim**（基于事实的判断）：
`{"id": "claim_03", "statement": "模型服务已出现明显接口碎片化", "derivedFrom": ["fact_021", "fact_024"], "type": "derived", "confidence": 0.92}`【derivedFrom 悬空=拦】

**Slide Message**（这页观众记住的唯一 Takeaway）：
"超过一半的模型接口不统一，平台治理已经成为必要条件。"

**Display Copy**（真正写到页面上的字）：Headline "5/8 模型接口仍未统一"；Subheadline "接口碎片化正在增加业务接入和运维复杂度"。

## 6. 来源与事实追踪【source_type 封闭=拦】

数字、日期、百分比、排名、事实陈述、对外引用、Chart 数据、关键结论依据——全部
可追溯：`{"source_type": "original|inferred|generated", "source_ref": "doc01:p8", "confidence": 0.94}`。
original=材料明确给出；inferred/derived=可从原始事实合理推导；generated=仅为叙事、
措辞或结构生成，**不得伪装为事实**。

## 7. 禁止事实幻觉

不得：补造数字、猜测同比环比、编案例/客户名/性能结果/日期、把推断写成原始事实。
需要但资料不存在 → 标 **missing_evidence**，而不是编。

## 8. Content Understanding 标准输出

`{"topic", "document_intent", "facts", "metrics", "entities", "events", "problems",
"causes", "solutions", "results", "risks", "evidence", "relationships"}` —— fact 的
`type` ∈ context/problem/solution/metric/constraint/risk/result（封闭集）【拦】。

## 9. 内容标准化（进 Storyline 前必须执行）

去重（同一事实一份主记录）；名称统一（"大模型平台/AI 能力平台/统一模型平台"本质
同一实体 → canonicalName）；数字统一（单位/千分位/小数位/百分比）；时间统一
（2026/9/1、2026-09-01、9 月 1 日 → 标准格式）。

## 10. 内容价值分类

must_have（没它论证不成立）/ supporting（增强可信度）/ optional / appendix（保留
但不打断主线）/ drop（与目标无关）。**原材料里有，不代表 PPT 必须讲。**

## 11. Core Thesis【缺失=拦】

```json
{"coreThesis": {"statement": "建设统一 AI 能力平台可以解决模型服务碎片化问题，并形成规模化服务能力",
                 "desiredBelief": "统一平台建设现在有必要且可实施"}}
```

检查：能否一句话说清；与 desiredAction 是否一致；能否被事实支撑；能否统领全篇。

## 12. Thesis Coverage

每个 must_have Claim 必须能回答"它如何支撑 Core Thesis"；答不上 → drop / appendix。

## 13. Storyline Archetype（不从零自由生成故事）

预定义骨架（`planning.md` 列全表）：problem_solution（问题→影响→方案→证明，
适合方案/产品/销售）、scr（情境→冲突→解法，咨询/决策）、why_what_how（技术方案/
战略）、project_report（项目汇报，周报/月报/阶段汇报）、goal_progress_result（汇报/复盘）、
overview_detail_evidence（评审/研究）、product_capability_value（产品/售前）、
incident_review（事故复盘）、tech_proposal（架构评审）、past_present_future（发展史/
路线）。

## 14. Storyline 选择规则

按 purpose + audience + content type 选最匹配骨架；一个不够可组合，**最多两种**；
避免每页一个不同的逻辑结构。

## 15. Section 规则【乱序/角色越界=拦】

每个 Section 必须有 topic **加** message："技术方案"不够，"通过统一模型层、服务层
和治理层完成平台化改造"才是。禁止只有 topic 没有 message 的 section。

## 16. 页面数量分配【sections 页数之和 ≠ target_slide_count=拦；权重和≠1=拦】

```json
{"target_slide_count": 15, "sections": [
  {"name": "背景与问题", "weight": 0.20, "target_slides": 3},
  {"name": "解决方案",   "weight": 0.40, "target_slides": 6},
  {"name": "价值与实施", "weight": 0.27, "target_slides": 4},
  {"name": "总结",       "weight": 0.13, "target_slides": 2}]}
```

总页数是约束不是死值；严重不足或超载可调，但**必须说明原因**。

## 17. 一页一个 Takeaway【页无 message=拦】

一页只允许一个主要 Takeaway，但可以有多个事实**支撑**它。吞吐 +42%、成本 -31%
可以同页——只要都在证明"优化方案显著提升推理效率"。禁止机械理解为"一页只能一个
数字/一条事实"。

## 18. Slide Message Test（每页四问）

1. 能否一句话表达？ 2. 所有主要元素都在支持这句话吗？ 3. 存在第二个同等重要、
结论不同的观点吗（是 → split_candidate）？ 4. 去掉某元素结论完全不受影响吗
（是 → 该元素可能是无关内容）？

## 19. 标题规则

Topic Title（"技术架构"）只适合目录/章节/附录；内容页默认 **Message Title**
（"四层架构将模型接入、推理与治理统一到一条服务链路"）。

## 20. 标题质量检查

尽量有：主语或明确对象、动词或变化、判断、结果、方向。避免"平台能力/项目背景/
数据情况/实施方案"这类无结论标题。

## 21. Claim + Evidence【claimId 悬空=拦】

重要页面必须明确 Claim + Evidence：
`{"message": "统一入口显著降低模型接入复杂度", "claimId": "claim_08", "evidence": ["metric_12", "fact_37"]}`。

## 22. Evidence 等级

Primary（没它 Claim 站不住）/ Supporting（增强可信度）/ Context（背景）/
Decorative（只承担氛围）。Page Planner 优先保留 Primary。

## 23. 无证据 Claim

重要但没证据 → unsupported_claim：继续检索 / 降措辞强度 / 标注为推测 / 删除 /
放"待验证"。**禁止强行保留为确定事实**。【高重要性只靠 inferred 支撑=提示】

## 24. 文案压缩规则

保留事实、因果、数字、对象；不增加新事实；不改结论方向。
原文（83 字）→ Long："多模型独立接入导致接口、鉴权和调用方式不一致，业务维护
成本持续增加" → Medium："多模型独立接入导致接口治理复杂" → Short："多模型接入碎片化"。

## 25. Copy Level

重要文本同时生成 `{"long": "", "medium": "", "short": ""}`，版面按真实空间选。
**Renderer 不允许临时截断句子**（`measure.py` 量的是"装不装得下"，装不下回来改文案或减条目）。

## 26. Content Budget（语义预算，几何仍由 measure 实测）

`{"headline": {"preferredChars": 24, "maxLines": 2}, "supportingPoints": {"preferredCount": 3, "maxCount": 5}, "body": {"preferredChars": 80}}`

## 27. 条目数量规则

2~4 条适合一页；5~6 进拆分评估；>6 默认高风险；10 条除 Appendix/Table 外原则上
拆页。是 QA 初筛，不是绝对法律。

## 28. 内容复杂度评分【≥0.70 未标 split=拦】

complexity = textAmount + nodeCount + evidenceCount + hierarchyDepth +
chartSeriesCount + visualRequirementCount。本仓库用一条**确定性公式**自查：`字符/120 + 节点×0.12 + 图表×0.25 +
图×0.15 + (层级-1)×0.10`，封顶 1.0 —— 没有 `complexityScore` / `risk` /
`splitSuggested` 这类输出字段，现在也没有脚本替你算：**≥ 0.70 且没标拆页 = 硬约束**
（自查）。标了拆页而内容很轻则会把一页拆散。

## 29. 拆页策略

优先：按观点拆 / 按证据类型拆 / 按时间拆 / 按层级拆 / 按过程拆 / 主线+Appendix。
**禁止第一反应就是缩字体**。

## 30. 内容与视觉表达关系

Content Engine 不决定 Layout，只输出语义关系（如 `"semanticRelation": "comparison"`），
Page Planner 再映射（comparison → chart / two-column）。

## 31. Visual Requirement（落进 spec 就是 `visual`）

Page Planner 必须给每页**决定一个视觉载体**，写进 spec 的 `visual`：`none`（纯文字立得住）/ 
`evidence_image`（照片、插画、结构图、流程图 —— 都由人拿提示词出图）/ `data`（图表）。
要图与要图表时 `ratio` 必填（`"3:2"` / `"4:3"` / `"1:1"` / `"16:9"`）—— 比例写下来才算定，
槽位高度按它算。**档位的语义、谁做、落到哪见 `images.md`**；`validate_spec.py` 拦未知档与
自相矛盾，`check.py` 点出没决定的页。

语义层可以想得更细（process / hierarchy / comparison / architecture / mood），但落到 spec
只有这三档：**除了图表，凡是图都归 `evidence_image`**；氛围归风格（`colorSet` / `decor` /
字体），**不单独设档** —— 多出来的档没有谁能交付它。

## 32. 什么时候必须有视觉

需要观众"看这个"就该产生：产品/UI 长什么样、改造前后、两方案差异、空间布局、
数据趋势、系统关系、架构层级。

## 33. 什么时候不需要额外图片

Timeline / Chart / Architecture / Process / Table / Diagram 本身已是视觉结构——
除非图片提供额外证据，否则不要为了"丰富"再塞一张。

## 34. 图片职责

图片不承载 PPT 正式信息（标题/正文/数字/标签/图表说明/流程文字必须由 Renderer
用真实文字绘制）；图片只负责观感、场景、证据、氛围、产品/人物/环境呈现。

## 35. Chart Requirement

内容层只定义 `{"kind": "data", "intent": "trend", "message": "调用量自 Q3 开始快速增长", "metricIds": ["m01", "m02"]}`；Chart Engine 决定类型、编码、标注、强调、动画。

## 36. Image Requirement

内容层只定义 `{"kind": "evidence_image", "role": "hero", "reason": "展示产品实际外观"}`；prompt、比例、留白由 Image Pipeline 处理（见 images.md）。

## 37. Audience Distance

Live：一页一个强 Message、少条目、大字、强视觉；Async：更多解释、更密、更完整
上下文；Printable/Archive：更高密度、注释、来源、页码。

## 38. Delivery Context 的边界

Content 只读 delivery mode、时长、观看距离（影响页数/密度/解释深度）；具体导出
格式由 Delivery Rules 管（见 delivery-formats.md）。

## 39. 叙事节奏

整套 PPT 不应每页同强度：高强度结论页 → 解释 → 证据 → 结构 → 数据 → 留白/过渡 →
强结论。Storyline 主动创造节奏。

## 40. 章节内节奏

Section 推荐：Section Message → Explain → Evidence → Implication；不要连续 6 页
并列信息。

## 41. 结论先行

决策/汇报/方案类默认结论先行，不故意拖到最后。例外：故事型演讲、教学探索、
悬念式发布、特定叙事需求。

## 42. Ending 规则

结束页不只是 THANK YOU；优先最终判断 / 下一步 / 决策请求 / 关键行动 / 待确认事项
（"下一步：完成 4 个核心模型统一纳管，并启动网关切换"）。

## 43. Appendix

详细参数、原始表格、参考文献、完整测试数据、详细日志、低频问题、备份方案、
不影响主线的技术细节 → 附录。**Appendix 不占主叙事页预算**。

## 44. Redundancy Detection【归一化相同=提示】

两条 message 语义相似（规范阈值 0.85）且证据角色无异 → merge/rewrite/remove。
本仓库实现：归一化（去标点/小写）后**完全相同**才提示；语义相似度是未实现约定。

## 45. Narrative Gap Detection

Story Graph 不允许逻辑断层：Problem → Implementation 缺 Solution → narrative_gap。
本仓库由骨架顺序检查兜底【乱序=拦】。

## 46. Narrative Transition

每页之间应能回答"为什么下一页现在出现"：
`{"transitionReason": "既然现有接口碎片化，下一步需要说明统一平台如何解决"}`。
答不出 = 可能叙事跳跃。

## 47. 内容密度不是越满越好

目标不是"填满页面"而是**信息理解效率**；大量留白若强化核心 Message，合法。

## 48. 不得为了"页面不空"增加无关内容

禁止：空洞口号、无证据数字、泛化描述、重复卡片、不相关图片、"为了完整"但无
价值的 bullet。

## 49. Copy Style

简洁、具体、有信息量；少空话、套话、名词堆砌、无量化表达。优先"统一入口将 5 套
调用方式收敛为 1 套"，而不是"全面提升模型统一管理能力"。

## 50. 空洞语言检测【变化词且全句无数字=提示】

提升 / 优化 / 降低 / 提高 / 改善 / 赋能 / 助力 / 领先 / 先进 ——
单独出现就追问：提升什么？优化多少？为什么？有什么证据？

## 51. 数字优先

有数字证据就用数字："成功率从 92.4% 提升至 98.7%" 优于 "成功率明显提升"。

## 52. 因果关系必须谨慎

只有材料明确支持才用因果措辞；否则用"同时出现 / 可能影响 / 存在关联"。

## 53. 比较必须有基准

更快/更高/更低/更稳定/更节省必须有 comparison baseline；没有就降措辞强度。

## 54. 数字一致性【冲突应=阻断；跨页比对未实现】

同一指标跨页必须同单位、同精度、同时间口径、同定义；冲突 = blocking error
（当前由人工保证，脚本未做跨页指标比对）。

## 55. Slide Content Object（推荐最终格式）

```json
{"slideId": "slide_07", "purpose": "prove_problem",
 "message": "超过一半的模型接口不统一，平台治理已经成为必要条件",
 "claim": {"id": "claim_08", "type": "derived", "confidence": 0.94},
 "evidence": [{"id": "metric_03", "role": "primary"}, {"id": "fact_18", "role": "supporting"}],
 "copy": {"headline": "5/8 模型接口仍未统一",
          "subheadline": "接口碎片化正在增加业务接入和运维复杂度",
          "points": ["鉴权方式不统一", "调用协议不统一", "错误处理方式不统一"]},
 "visualRequirement": {"kind": "data_comparison", "intent": "emphasize_ratio", "priority": "primary"},
 "contentBudget": {"headlineMaxLines": 2, "maxSupportingPoints": 3},
 "sources": ["doc01:p8", "doc02:p14"]}
```

本仓库对应：pageplan 的页对象（message_ref + 页型 + data/nodes/columns）——
**由 AI 自己写成 deck-spec 的 slide**（写完跑 `validate_spec.py` + `check.py`）。

## 56. Presentation Plan（推荐）

`{"brief", "coreThesis", "storyArchetype", "sections": [{"id", "title", "message", "slides": []}], "slides": []}` —— 本仓库拆成三份 JSON（content / storyline / pageplan），**由 AI 按本文自查**。

## 57. Content QA（进 Page Planner 前必须完成）

Thesis（存在且与 desiredAction 一致）/ Coverage（must_have 全覆盖）/ Evidence /
Traceability / Unsupported Claim / Redundancy / Narrative Flow / One Takeaway /
Audience Fit / Density Risk / Relevance。落地：**内容层没有自动门** ——
这一节靠人/AI 自查；产物层的硬门由 `check.py` 兜。

## 58. Content QA Score

`{"contentScore": {"thesisClarity", "evidenceCoverage", "narrativeFlow", "redundancy",
"audienceFit", "slideFocus", "traceability"}}`；建议总分 <85 不进视觉设计
（评分模型未实现，作为人工口径）。

## 59. Hard Error（阻塞）

关键数字冲突；关键事实来源缺失；**Core Thesis 不存在**；关键 Claim 无证据且被写成
确定事实；同一页两个完全独立核心观点；明显超页数且未说明；必须内容被遗漏。

## 60. Warning（提示）

页面内容偏多；章节页数失衡；Message 偏弱；标题只有 Topic 没结论；多页语义相似；
视觉需求不足；过多纯文字页；附录内容进入主线。

## 61. Content Repair（按序修，别跳步）

修事实和数字 → 补来源 → 重写 Core Thesis → 删无关 → 合并重复 Claim → 补证据 →
修 Storyline → 拆多观点页 → 压 Copy → 调 Appendix → **最后才动页数**。

## 62. 与实测层的接口

"装不装得下"由 `measure.py` 实测：Content Planner → Content Budget → Page Planner →
Layout Resolver → **实测** → Repair。Content Engine 判断"值不值得说"。
（**装不下**由 `check.py` 的越界 / 裁切两道门直接报。）

## 63. 与 Page Planner 的接口

Content 输出 message / claim / evidence / copy / semanticRelation /
visualRequirement / contentBudget；Page Planner 决定 pageType / layoutFamily /
primaryVisual / density / focalPoint。

## 64. 与 Image Pipeline 的接口

Content 只说"需要什么视觉、为什么、什么证据角色"；prompt 结合 Layout/Style/Brand/
Color/比例/留白由 Image Pipeline 生成（`image_source.py --brief`）。

## 65. 与 Chart Engine 的接口

Content 输出 data intent / message / metrics / comparison relation；图形类型
（`chart`，八类）由 spec 显式声明（不由 intent 推断），Chart Engine
负责编码、标注、强调（`render.py::chart_g2_spec`，AntV G2；图表内部不动）。

## 66. 与 Motion Engine 的接口

Content 可输出 `{"motionIntent": "explain|reveal|compare|progress|focus"}`；具体
效果由 Motion 层决定（`animation.md` 的决策优先级）。

## 67. 反 AI-Slop 内容规则

禁止：每页"标题+三条"；每页都"现状/问题/对策"；标题堆"赋能/提升/优化"；同一观点
换词重复；为凑页数硬编；无证据的"大幅提升"；结论藏在最后；长文直接摘要成 bullet；
页面只有 Topic 没有 Message；过度均匀的章节结构。

## 68. 合法例外（必须有明确原因）

一页只有一句话（若它就是核心结论）；故意密集（附录/数据表/参考文献）；没有封面
（补充材料）；留白很多（构图的一部分）；多证据同页（同撑一个 Takeaway）；单一版式
多页（内容要求连续比对）。

## 69. 推荐运行流程

Input → Brief → Audience Model → Content Understanding → Normalization →
Fact/Metric/Evidence Store → Claim Synthesis → Core Thesis → Story Archetype →
Section Plan → Slide Message Plan → Claim+Evidence Mapping → Display Copy →
Visual Requirement → Content Budget → **Content QA** → Page Planner。

## 70. 最终元规则

Rule 1 先明确观众要做什么，再决定内容。Rule 2 一份 deck 必须有唯一 Core Thesis。
Rule 3 一页只允许一个主要 Takeaway。Rule 4 多个事实可以同页，但必须服务同一个
Takeaway。Rule 5 重要 Claim 必须有 Evidence。Rule 6 原始事实、推断和生成表达
必须分开。Rule 7 任何数字和事实必须可追溯。Rule 8 原材料里有，不等于 PPT 必须讲。
Rule 9 内容价值高于页面填满程度。Rule 10 标题优先表达结论，而不只是主题。
Rule 11 文案压缩不得改变事实和因果。Rule 12 视觉需求由语义决定，不由"页面空
不空"决定。Rule 13 Content Engine 决定"说什么"，Page Planner 决定"怎么表达"。
Rule 14 实测层只判断"装不装得下"（原 `fit.py`，现 `measure.py`），不能反过来决定"值不值得说"。Rule 15 任何
视觉设计开始前，Content QA 必须通过。

## 71. 一句话定义

优秀的 AI PPT 内容系统，不是把资料总结成几页，而是围绕观众目标建立 Core Thesis，
用可追溯事实形成 Claim 与 Evidence，通过 Storyline 控制认知推进，再把每页压缩成
一个唯一 Takeaway，最后才交给视觉系统设计。
