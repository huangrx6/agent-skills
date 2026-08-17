# 工程文档信息架构

## 目录

- [推荐入口](#推荐入口)
- [推荐目录](#推荐目录)
- [README](#readme)
- [PROJECT_CONTEXT](#project_context)
- [docs/index](#docsindex)
- [主题目录](#主题目录)
- [目录规模规则](#目录规模规则)
- [避免重复](#避免重复)

## 推荐入口

仓库根目录建议至少有：

```text
README.md
AGENTS.md
PROJECT_CONTEXT.md
docs/index.md
```

四者职责不同。

| 文件 | 主要读者 | 职责 |
|---|---|---|
| `README.md` | 人类 | 项目是什么、最快怎么开始 |
| `AGENTS.md` | AI Agent | 工作前后必须执行的指令 |
| `PROJECT_CONTEXT.md` | 人类 + AI | 当前稳定项目快照与知识路由 |
| `docs/index.md` | 人类 + AI | 全部长期文档的导航 |

不要把四者合并成一个巨型 README。

## 推荐目录

```text
/
├── README.md
├── AGENTS.md
├── PROJECT_CONTEXT.md
└── docs/
    ├── index.md
    ├── project/
    │   ├── overview.md
    │   ├── glossary.md
    │   └── constraints.md
    ├── architecture/
    │   ├── overview.md
    │   ├── diagrams/
    │   └── decisions/
    ├── development/
    │   ├── setup.md
    │   ├── workflows.md
    │   └── testing.md
    ├── contracts/
    │   └── index.md
    ├── data/
    │   ├── ownership.md
    │   └── lifecycle.md
    ├── operations/
    │   ├── overview.md
    │   └── runbooks/
    ├── working-agreements.md
    └── handoffs/
        └── active/
```

这是“按需创建”的目标结构，不要求新项目第一天创建所有空目录。

## README

README 只回答：

- 项目是什么；
- 谁应该使用；
- 如何本地启动；
- 最短测试命令；
- 去哪里看详细文档。

README 不保存：

- 完整架构；
- 全量 API；
- 所有部署步骤；
- 决策历史；
- 长期排障手册。

## PROJECT_CONTEXT

它是工具无关的“Project Bootstrap Pack”。

建议限制在约 100–200 行，并包含：

- Purpose；
- Repo Map；
- Stack；
- Architecture Summary；
- Domain Vocabulary；
- Critical Invariants；
- Common Commands；
- Current Canonical Docs；
- Known Sharp Edges。

它只总结稳定事实，并链接详细文档。

不要加入：

- 当前 Sprint；
- PR 状态；
- 某次对话全文；
- 临时调试发现；
- 完整 Changelog；
- 个人隐私偏好。

## docs/index

索引必须让读者通过问题导航，例如：

```text
我要理解系统架构 → architecture/overview.md
我要新增 API → contracts/index.md + API 规范
我要改数据库 → data/ownership.md + migration 规则
我要排障 → operations/runbooks/
我要理解一个历史决定 → architecture/decisions/
```

索引不是文件列表 dump。

## 主题目录

### project

当前项目事实：

- 目标；
- 范围；
- 术语；
- 外部依赖；
- 固定约束。

### architecture

当前结构和历史决策。

`overview.md` 描述现在是什么；`decisions/` 描述为什么变成这样。

### development

开发人员执行任务的 How-to。

### contracts

不要复制 OpenAPI/Proto/GraphQL Schema。

这里保存：

- 契约事实来源的位置；
- 版本策略；
- 如何生成/验证；
- 关键入口。

### data

保存数据 Ownership、生命周期、敏感分类等跨数据库长期规则。

表字段细节优先由 Schema/Migration/数据库目录作为事实来源。

### operations

生产运行、告警、Runbook、恢复和常见故障。

### working-agreements

只保存明确、稳定、项目相关的团队工作约定。

### handoffs

只保存当前未完成且确实需要跨人或跨会话交接的状态。

## 目录规模规则

当一个目录出现以下情况时，应增加局部 `index.md`：

- 文件超过约 7–10 个；
- 新成员无法凭名称找到内容；
- 同一主题存在多种阅读路径；
- AI 需要先扫描整个目录才能判断读哪个文件。

不要因为有三个文件就创建复杂层级。

## 避免重复

同一事实只存在一个 **canonical source（唯一事实来源）**——本 Skill 中 “canonical source”、“唯一事实来源”、“事实来源” 指同一概念，首次出现时使用全称，后续可简称为 canonical source 或事实来源。

其他文档使用：

- 链接；
- 摘要；
- 自动生成引用。

例如版本号来自包清单，不同时写在 README、PROJECT_CONTEXT、部署文档和代码注释中。

## 文档元数据约定

为避免 Agent 解析异构 frontmatter，所有使用 status 字段的模板遵循以下字段名：

| 字段 | 适用 | 必填 |
| --- | --- | --- |
| `status` | 状态（参考 §状态总表） | 长期文档/ADR/handoff 必填 |
| `owner` | 负责团队或个人（单数） | 长期文档必填 |
| `created` | 创建日期 | handoff 必填 |
| `date` | 决议日期 | ADR 必填 |
| `last_reviewed` | 上次评审日期 | 长期文档推荐 |
| `expires_or_close_when` | 关闭/过期条件 | handoff 必填 |
| `supersedes` / `superseded_by` | ADR supersede 关系 | 适用时 |

约定：

- `owner` 统一为单数（不混用 `owner` / `owners`）；
- ADR 用 `date` + `supersedes`，handoff 用 `created` + `expires_or_close_when`——语义不同，不强制统一字段名；
- 不要自动更新 `last_reviewed` 只为让 CI 变绿。
