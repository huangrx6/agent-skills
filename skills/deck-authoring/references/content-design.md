# 内容设计：说什么、为什么这样说（v3.0）

这一层只回答三个问题：**我们知道什么、按什么顺序讲、每页让观众记住什么**。
颜色、坐标、字体、动效、图片文件——全都不归它管（那是 layout / style / chart /
image / motion 的事，见 `pipeline.md` 的分层地图）。

## 0. 核心链路

```text
Audience / Goal → Desired Action → Core Thesis → Facts & Evidence → Claims
    → Storyline → Section Message → Slide Message → Display Copy
    → Visual Requirement → Page Planner →（设计/渲染）
```

先明确观众最终要**做什么**，再决定他需要**相信什么**；用事实形成论证；把论证
拆成每页唯一的 Takeaway；最后才进视觉。顺序反了就是"把资料压缩后排漂亮"——
那是排版，不是演示。

## 1. Presentation Brief 【缺 desiredAction/desiredBelief = 阻塞；缺 brief = 提示】

任何 deck 开工前先写 brief（`content.json` 的 `brief` 字段）：

```json
{"purpose": "proposal", "audience": "technical", "delivery": "live",
 "targetSlides": 5, "durationMinutes": 10,
 "desiredAction": "批准统一 AI 能力平台建设方案"}
```

- `purpose` ∈ decision/proposal/report/update/training/sales/explanation/review，
  `audience` ∈ executive/technical/customer/internal/general，
  `delivery` ∈ live/async/printable/editable —— 封闭集，`plan.py --check` 拦。
- **最重要的是 `desiredAction`**：PPT 放完观众做什么。推不出来至少给
  `desiredBelief`（该相信什么）。两者都没有 = 阻塞——元规则 1。
- 同一份材料，观众不同则组织不同：executive 要结论/影响/成本/风险/决策；
  technical 要架构/接口/性能/部署；customer 要问题/价值/案例/收益。
- delivery 影响密度：live 一页一个强 message、大字少条目；async 可更密；
  printable 可带来源和注释。

## 2. 四类内容对象（不得混用）

| 对象 | 是什么 | 例子 |
| --- | --- | --- |
| **Fact** | 材料里明确存在的 | "部署 8 个模型服务，5 个接口协议不一致" |
| **Claim** | 基于事实的判断 | "模型服务已出现明显碎片化"（derivedFrom 两个 fact） |
| **Message** | 这一页观众该记住的唯一 Takeaway | "超一半接口不统一，治理已成必要条件" |
| **Display Copy** | 真正写到页面上的字 | 标题"5/8 模型接口仍未统一" |

schema 都在 `planning.md`；`plan.py --check` 拦的：fact 缺 id/type/text、
claim 的 `derivedFrom` 悬空、message 的 `claimId` 悬空、`claims` 空。

## 3. 事实追踪与禁止幻觉【source_type 封闭 = 阻塞】

每个 fact 标 `source_type`：`original`（材料明确给出）/ `inferred`（可从原始
事实推导）/ `generated`（仅为叙事生成，不得伪装为事实）。数字、日期、百分比、
排名、图表数据——全部要能追到 `source_ref`。

**不许补造**：用户没给的数字、同比环比、案例、客户名、性能结果、日期。
资料里没有就标 missing_evidence，不编。【已拦：`source_type` 不在封闭集 = 错】

**最危险的一类错**【提示】：重要性 ≥0.9 的 message，证据却全是 `inferred`
——把 AI 推断的话当事实讲。要么找到原文证据，要么降重要性。

## 4. Core Thesis【缺失 = 阻塞】

```json
{"coreThesis": {"statement": "统一平台能解决碎片化并形成规模化服务能力",
                 "desiredBelief": "现在有必要且可实施"}}
```

一份 deck **一句**统领论断。检验：能一句话说清？和 desiredAction 一致？
能被事实支撑？足以统领全篇？没有它，每页各自为政——`plan.py --check` 直接拦。
每个 must-have 的 claim 都要能回答"它如何支撑 thesis"；答不上 → drop 或进附录。

## 5. 叙事骨架（细节见 planning.md）

不从零编故事。十个预定义骨架（问题→方案 / SCR / 过去现在未来 / why-what-how /
目标进展结果 / 总览细节证据 / 复盘 / 技术方案 / 项目汇报），按 purpose+audience
选；【拦：骨架乱序、sections 页数之和 ≠ target_slide_count】。每个 section 要有
**message** 不只有 topic——"技术方案"不是 section message，"四层架构把接入、
推理、治理收敛成一条服务链路"才是。

## 6. 一页一个 Takeaway【页无 message = to_spec 阻塞】

一页只允许**一个主要** Takeaway，但可以有多个事实**支撑**它——"吞吐 +42%、
成本 -31%"可以同页，只要都在证明"优化显著提升推理效率"。

四问检验（写 pageplan 时过一遍）：

1. 能否一句话说出来？（说不出 = 还没想清楚）
2. 页面所有元素都在支撑这句话吗？（不是的删掉）
3. 存在第二个同等重要、结论不同的观点？（是 → 拆页，`split`）
4. 去掉某元素结论完全不变？（是 → 该元素是无关内容）

## 7. 标题：结论优先，不是主题

内容页默认 **Message Title**（"5/8 模型接口仍未统一"），不是 Topic Title
（"平台现状"——这适合目录和章节页）。好标题尽量有：对象、变化、判断、结果、
方向。【提示层：标题空洞会由"空话检测"与层级检查兜住】

## 8. 文案压缩与 Copy Level

压缩**保留**事实/因果/数字/对象，**不增加**新事实、不改结论方向。重要文本给
三档（long/medium/short），版面按实测空间选——**Renderer 不许临时截断句子**
（fit.py 量的是"装不装得下"，装不下回来改文案或减条目，不是悄悄截）。

条目数初筛：2~4 条适合一页；5~6 进拆分评估；>6 高风险；10 条除附录/表格外
原则上拆页。复杂度评分（字符/120 + 节点×0.12 + 图表×0.25 + 图×0.15 + 层级×0.10，
阈值 0.70）【已拦：超阈值未标 split = 错】。

## 9. 措辞的四条硬规矩

1. **数字优先**：有数字证据就用数字（"92.4% → 98.7%"好于"明显提升"）。
   【提示：变化词（提升/优化/降低/…）出现但全句无数字 → 追问"提升什么？多少？"】
2. **因果谨慎**：材料明确支持才用"导致"；否则用"同时出现 / 可能影响 / 存在关联"。
3. **比较要有基准**："更快/更省"必须有 baseline，没有就降措辞强度。
4. **数字一致性**：同一指标跨页同单位、同精度、同口径、同定义——冲突 = 阻塞
   （当前由人工保证，脚本未做跨页指标比对）。

空话黑名单：赋能 / 助力 / 全面提升 / 一体化 / 领先 / 先进……单独出现就该被追问。
反 AI-Slop：不许每页"标题+三条"、不许同一观点换词重复、不为凑页数加空洞 bullet、
结论不藏最后（决策/汇报类默认结论先行）。

## 10. 重复与叙事断层

【提示：两条 message 归一化后完全相同 → 合并/改写/删一条（语义相似度是未实现
约定，离线零依赖做不了 embedding）】。骨架已保证不断层（乱序=拦）；section 内
推荐节奏：Section Message → Explain → Evidence → Implication，不要连续 6 页
并列信息。整套 deck 主动创造强弱节奏：结论页 → 解释 → 证据 → 结构 → 数据 →
留白 → 强结论。

## 11. 结尾与附录

结尾不只有 THANK YOU：最终判断 / 下一步 / 决策请求 / 待确认事项
（"下一步：完成 4 个核心模型统一纳管，启动网关切换"）。详细参数、原始表格、
参考文献、完整测试数据 → 附录，不占主叙事页预算。

## 12. 视觉需求由语义决定

内容层只声明"需要什么视觉、为什么"（`visualRequirement` 的 kind/intent/reason），
不决定怎么画：

- **该有视觉**：观众要"看这个"——产品/UI 长什么样、改造前后、方案差异、
  数据趋势、架构层级。
- **不必塞图**：Timeline / Chart / 架构 / 流程 / 表格本身已是视觉结构；
  纯结论页靠字与留白。宁多勿少，但"这一页你要说'看这个'"才是判据。
- **图不承载信息**：标题/正文/数字/标签由 Renderer 用真文字排（可搜索、可翻译、
  屏幕阅读器、PPTX 可编辑）；图只管观感、场景、证据、氛围。图不许盖满整页
  （check.py ≥60% 阻塞）。

图表：内容层给 intent（trend/comparison/composition…）+ message + metric 引用，
类型由 `chart.py` 的意图树查表。图片：prompt、比例、留白由 `image_source.py`
的契约流程处理（见 images.md）。

## 13. Content QA 与修复顺序

进视觉设计前过 `plan.py --check`（上表所有【拦】项）+ 人工过一遍提示项。
修复顺序（别跳步）：**修事实和数字 → 补来源 → 重写 thesis → 删无关 → 合并
重复 → 补证据 → 修骨架 → 拆多观点页 → 压文案 → 调附录 → 最后才动页数**。
第一反应是缩字体 = 最差的修法（布局层还有排版预算兜底，但内容超载是内容层的错）。

## 14. 元规则

1. 先明确观众要做什么，再决定内容。
2. 一份 deck 一句 Core Thesis。
3. 一页一个主要 Takeaway；多事实同页必须服务同一个 Takeaway。
4. 重要 Claim 必须有 Evidence；事实、推断、生成表达分开。
5. 数字和事实可追溯；材料里有 ≠ PPT 必须讲。
6. 内容价值高于页面填满程度；标题表达结论而非主题。
7. 压缩不改事实和因果；视觉需求由语义决定。
8. Content 说"说什么"，Page Planner 说"怎么表达"。
9. fit.py 只判"装不装得下"，不判"值不值得说"。
10. 视觉设计开始前，内容 QA 必须通过。

合法例外（要有明确理由）：一页一句话若是核心结论；附录故意密集；留白是构图
的一部分；多证据同页若同撑一个 Takeaway。
