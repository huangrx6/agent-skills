# 从材料到页面

规划解决“知道什么、按什么顺序讲、每页用什么证明”。它是作者工作，
当前没有独立的 content/storyline/pageplan JSON 解析器，不要求把这三份文件作为交付门槛。
简短 deck 用一张页序表即可，复杂项目按需要保存可追溯的内容说明。

## 建议的页序表

每页记录：主要结论、支持它的来源、页面角色、实际页型、主视觉、必要讲稿。
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

`role` 是页面的语义作用，`type` 是渲染器结构。下表从 `scripts/layout/roles.py`
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
| `architecture` | content-image | `evidence_image` | 层与层的关系；结构图（excalidraw / draw.io） |
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

一页同时承担多个独立结论、图中文字缩到不可读，或证据与解释争夺空间时，考虑拆页。
先拆语义，再选结构；不是按字符公式机械切段。复杂架构用总览加细节图，
外部结构图进入 PPTX 后通常是图片，要保留其编辑源。

## 进入渲染前

逐页核对标题能否说出主要结论、证据是否足够、来源是否可追踪、页型是否匹配。
检查全篇页数、叙事连接、术语与单位；规划层无法自动验证这些内容。
然后运行 validate_spec、渲染、check 和真实视觉审查，不能用规划完成替代产物验收。
