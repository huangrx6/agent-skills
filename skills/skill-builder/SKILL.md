---
name: skill-builder
description: >-
  Use this skill before creating a new skill, or when judging whether an existing skill's trigger description is too broad / too narrow / too vague.
  Decides whether a skill is the right tool, defines a non-flaky trigger description, scopes the new skill to P0 / P1 / P2, and produces a SKILL.md checklist.
  Also use it when an existing skill keeps getting missed or over-firing, to revise the description.
  Do NOT use for: editing an existing skill's body content, writing a one-off prompt that does not need to persist, running formal eval to validate trigger accuracy, or maintaining references/ assets/ scripts/ inside an existing skill.
---

# skill-builder — 建 Skill 前的 5 分钟决策

Decides whether a skill is worth building and produces a tight SKILL.md draft. Lightweight by design — no eval pipeline, no asset tooling.

Use when: 用户想建一个 skill / 问触发描述是不是太宽太窄 / 拿新需求问要不要包成 skill / 现有 skill 触发重叠要拆合 / 现有 skill 反复触发错要重写 description。

Do NOT use when: 编辑现有 skill 的正文(直接改 SKILL.md)/ 写一次性 prompt 或 alias / 跑 formal eval 验证触发准确度(另起流程)/ 补 references/ 或 assets/(直接补,不重做决策)。

## The 5-Minute Decision Tree

按顺序回答 5 个问题。任何一题答不上来 = 不要建 skill,先回去想清楚再回来。

### Q1. 这是不是一个 skill 该解决的问题?

Skill 解决"Agent 该做但反复做"的事。如果只是单次任务,不要包成 skill。

| 信号 | 含义 |
| --- | --- |
| 同一个动作 / 决策 / 流程,在最近 30 天出现 ≥3 次 | 值得建 skill |
| 单次一次性需求,只在本次对话里出现 | 不需要 skill,直接 prompt |
| 是 prompt / alias / config toggle 就能解决的 | 不是 skill 问题 |
| 用户已经把流程写成 SOP / runbook | 可以考虑 skill 化,但先确认 Q2 |

### Q2. 触发关键词能不能写在 1-3 句话里?

description 字段决定 Agent 何时触发。模糊 description = 永不触发 / 永远误触发。

能写出来 = 继续;写不出来 = Q1 答错了,回去再确认需求。

### Q3. 这个 skill 的"做什么"和"不做什么"边界清不清?

边界不清的 skill 会跟现有 skill 打架(尤其是 obsidian 类)。如果边界说不清:

- 太宽:拆成 P0 skill + 引用
- 太窄:合并到现有 skill
- 不清:先写一版 Do NOT use this skill when,看能不能收紧;收不紧就别建

### Q4. 范围是 P0 / P1 / P2 哪一档?

| 档 | 触发频率 | 范围 | 例子 |
| --- | --- | --- | --- |
| **P0** | 每天 / 每周多次 | 单流程、单一决策 | skill-builder(本 skill)、仓库考古、PR diff 解读 |
| **P1** | 每周一次左右 | 跨流程 / 多步骤 | 工作流闭环、完整发版文档生成 |
| **P2** | 每月 / 按需 | 大而广,通用方法论 | 工程标准合集、安全审查清单 |

P0 是新 skill 的最佳档。P1 / P2 一开始就要警惕——很可能该拆成几个 P0 而不是一个大 skill。

### Q5. 你能在 15 分钟内写完 SKILL.md 一稿吗?

写不完 = 范围太大,先回到 Q4 拆。

如果 Q4 已经 P0 还写不完 = SKILL.md 超过 ~150 行,把长文背景知识移到 `references/`,正文只留决策表和 anti-pattern。

## Trigger Description 写作规范

description 是 Agent 唯一的触发器,占整张 SKILL.md 工作量的 60%。

### Anti-patterns(导致触发失败)

- ❌ **太宽**:"AI 助手"、"提高效率"、"通用工具"(Agent 不知道何时触发)
- ❌ **太窄**:列举具体文件路径、具体人名、具体机器(换环境就不触发)
- ❌ **关键词堆砌**:"X、Y、Z、A、B、C"(没权重信号,Agent 全打散)
- ❌ **模糊动词**:"处理"、"搞定"、"做"(没说做什么动作)
- ❌ **没有 Do NOT use this skill when 边界**(几乎一定误触发)

### Good patterns

- ✅ 第一句说"Use this skill when..."触发场景
- ✅ 列出 3-6 个具体动词 + 1-3 个对象(`整理`、`归位`、`创建`、`审阅` + `笔记`)
- ✅ 第二句说"Do NOT use this skill when..."边界,边界尽量具体
- ✅ 如果 skill 跨机 / 跨环境不可用,**显式声明**("bound to specific machine" / "依赖特定 vault 路径")
- ✅ description 总长度控制在 800 字符以内(太长会触发阈值被截断)

### 描述模板

```yaml
description: >-
  Use this skill when <触发场景 1> or <触发场景 2>.
  <这个 skill 做什么,一句话>.
  Also use it when <边界场景>.
  Do NOT use for <不该用的场景 1> or <不该用的场景 2>.
```

## Scope Discipline — 写什么 / 不写什么

### 写进 SKILL.md 的

- 起手流程(用户在第一句问"怎么办"时就能跑)
- 1-3 个核心决策表
- Anti-pattern(明确的"不要做")
- 一两个例子(如果有)

### 不写进 SKILL.md 的(放到 `references/` 或 `examples/`)

- 长文背景知识
- 完整的决策树图(mermaid 用 `references/decision-tree.md`)
- 工具 / 库的安装说明
- 重复的引用
- 跨 skill 共用的写作约定(那是根 README 或单独的 style-guide)

### 永远不要写进 skill

- 个人吐槽、临时想法、试验性段落
- 没经过验证的"最佳实践"
- "读者复制代码"、"这里要提醒读者"、"给作者自己看"这种后台话术

## Minimum Viable SKILL.md Checklist

在宣布 skill 完成前,逐项确认:

- [ ] 目录名 = frontmatter `name` 字段(强制一致,大小写敏感)
- [ ] frontmatter 含 `name` + `description`,YAML 合法
- [ ] description 第一段是"Use this skill when..."(或等价表达)
- [ ] description 含 3-6 个具体动词 + 1-3 个对象,不是模糊词
- [ ] description 含"Do NOT use this skill when..."边界
- [ ] description 总长度 < 800 字符
- [ ] SKILL.md 正文 ≤ ~150 行(超过则拆 `references/`)
- [ ] 正文有 1-3 个表格 / 清单,Agent 能直接照做
- [ ] 没有"个人吐槽 / 临时想法 / 试验性"段落
- [ ] 同步更新根 README 索引表 + Roadmap
- [ ] 同步更新 `skills-lock.json`,新增一条 entry

## Anatomy & Out-of-Scope

`SKILL.md` 默认是 skill 的全部内容;`references/` 留给长文(决策树可视化、anti-pattern 详表、跨 skill 约定)。完整目录树 + Out-of-Scope 列表见 `references/anatomy-and-scope.md`。

## Self-Review(写完前 1 分钟)

把这 3 个问题在脑子里过一遍:① 3 个具体动词(Q2)每个 Agent 都能命中?② "Do NOT use this skill when" 是真边界而不是凑数?③ 30 天后再打开这个 skill,是否仍然觉得它"显然该做"?3 个都过 = ship。
