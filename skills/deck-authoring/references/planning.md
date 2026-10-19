# 从材料到页面

规划解决“知道什么、按什么顺序讲、每页用什么证明”。它是作者工作，
当前没有独立的 content/storyline/pageplan JSON 解析器，不要求把这三份文件作为交付门槛。
简短 deck 用一张页序表即可，复杂项目按需要保存可追溯的内容说明。

## 建议的页序表

根据材料和演示目的安排页序；长篇可分章，短篇无需章节。章节可用概览、解释、例子或小结，
顺序和取舍由内容决定。单页任务应清楚；比较、目录、仪表盘可以同时呈现多个相关观点。
长表、代码与版本矩阵可在正文、分解页或附录出现，取决于观众是否需要现场阅读。

例如“七阶段×技术×产物”的满页表：先用一页讲七阶段总览，再逐阶段讲作用与产物，
复杂阶段另用例子页；完整版本表放附录。“三份真源＋字段＋约束”：先总览三者分工，
分别解释每份真源，最后一页解释共同完成条件。拆页保留原内容与来源映射，不能丢掉不方便排的事实。

按需要记录页面目的、来源、信息关系、构图和素材；动效、讲稿等只在适用时安排。
封面可以用文字、图像或其他构图建立主题，信息量以明确定位和视觉效果为准。
方向确定后的代表页可以是一段多页的微型章节，按材料论点拆分，不为维持“三页预览”重新塞回原稿。
先看一组页面的节奏：主张、证据、解释、转场各有强弱，不能每页都只有同一排小字。
这是工作记录，字段不直接写入 spec；只有受支持字段进入 [Slide DSL](style-architecture.md)。

| 任务 | 可采用的论证顺序 |
| --- | --- |
| 决策/建议 | 建议 → 证据 → 备选与代价 → 执行 |
| 问题解决 | 情境 → 问题 → 影响 → 方案 → 验证 → 下一步 |
| 技术评审 | 边界与约束 → 总体设计 → 关键权衡 → 证据 → 风险 |
| 进展汇报 | 目标 → 结果 → 差距 → 原因 → 动作 |
| 事故复盘 | 时间线 → 影响 → 根因 → 修复 → 预防 |
| 教学说明 | 问题 → 概念 → 示例 → 推导 → 应用 |

可重排或组合，不让骨架代替论证。限制总页数时先分配真正需要的页，
再检查总数；不存在自动权重配额或复杂度评分器。

## 页面角色与结构

自由 HTML 根据内容选择和改造构图，参见 [构图起点](web-composition.md)。
结构化路线中 `role` 是页面的语义作用，`type` 是渲染器结构。下表从 `scripts/layout/roles.py`
生成，推荐映射由 check 给出提示，不是每个角色只能用一种页型的硬限制。

<!-- roles:start -->
| 角色（spec 的 `role`） | 页型（结构） | 主视觉档 | 什么时候用它 |
| --- | --- | --- | --- |
| `cover` | title | `none` | 第一页；标题 + 副题 + 一句定位 |
| `transition` | title | `none` | 换章；只给章节名 |
| `statement` | content-text / title | `none` | 一个判断，字少、字大 |
| `breakdown` | content-text / two-column | `none` | 把后面要讲的东西列成几块 |
| `evidence` | content-text / content-image | `none` / `evidence_image` | 给人读的页；有截图/材料就配图 |
| `metric` | chart / content-text | `data` / `none` | 数字是主角；能画图就画图 |
| `trend` | chart / timeline | `data` / `none` | 随时间变化；折线或横向时间线 |
| `composition` | chart | `data` | 构成与份额 |
| `comparison` | two-column / chart / content-image | `none` / `data` / `evidence_image` | 两边对照；两栏、对比图或文图 |
| `process` | timeline / content-image | `none` / `evidence_image` | 有几步、有先后 |
| `capabilities` | two-column / content-text | `none` | 几项对等的能力/模块 |
| `architecture` | content-image | `evidence_image` | 层与层的关系；核实节点关系，按项目需求选择解释图 |
| `flow` | content-image | `evidence_image` | 节点与连线；结构图 |
| `topology` | content-image | `evidence_image` | 多节点的连接关系；结构图 |
| `hero_visual` | content-image | `evidence_image` | 一张图承担这一页的主要信息 |
| `context_image` | content-image | `evidence_image` | 图说明背景，文字仍是主角 |
| `risks` | content-text / two-column | `none` | 可能出问题的地方 |
| `actions` | content-text / two-column | `none` | 读完要干什么 |
| `result` | content-text / chart | `none` / `data` | 把结论收成一句或几个数 |
| `observation` | content-text / two-column | `none` | 判断与看法 |
| `team` | content-image / content-text | `evidence_image` / `none` | 谁在做 |
| `closing` | end | `none` | 最后一页 |
<!-- roles:end -->

`visual.kind` 只有 `none`、`data`、`evidence_image` 三档。新作应显式决定；
旧 spec 可省略，检查给提示。声明与页型矛盾则输入会拒绝。
数据与图片槽位用 `visual.ratio` 表达比例意图，见 [素材契约](images.md)。

## 结构与节奏

只有图文页和双栏页支持 layout 候选试排，见 [布局](layout-system.md)。
同一角色连续重复不一定错：并列对比或章节系列可以保持结构，讲稿中说明设计依据即可。
有变化的内容宜变化表达，但不要为版式多样性损坏比较基准或阅读顺序。

当阅读路径混乱、图中文字不可读，或证据与解释争夺空间时，重组、换构图或拆页。
拆分依照语义，不按字符公式机械切段。复杂架构可用总览加局部解释，
图中的关系仍须核实。具体位置计算见 [布局技术](layout-technology.md)。

## 进入渲染前

按 [项目设计记录](refined-workflow.md) 核对视觉方向、素材任务与代表页结果。
按 [制作入口](../SKILL.md#开始制作前先判断是否需要交互) 判断是否已到批量制作阶段；已有选择、品牌与授权持续有效，作者建议不等于用户选择。

素材按页面目的与用户要求选择：真实截图、授权照片、数据图表、生成图或适配的矢量图均有用途；
记录来源与证据边界。用户要求只用生图且禁止 SVG 时严格保留该项目约束，使用 `--raster-only` 检查，
完整新稿按 [素材交接](images.md) 先交 image-brief.md 与已接入的图位，默认由用户出图回填；
不以生图能力是否可用决定是否交文档，不自行换成其他素材类型。

逐页核对意图是否清楚、证据是否足够、来源是否可追踪、版式是否适配；标题可以是结论、问题或主题。
检查全篇页数、叙事连接、术语与单位；规划层无法自动验证这些内容。
最后按所选制作路线运行适用的校验与渲染，并检查真实画面；规划完成不等于产物通过验收。
