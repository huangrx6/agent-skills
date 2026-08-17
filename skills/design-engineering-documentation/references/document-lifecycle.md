# 文档生命周期与“新建还是更新”

## 目录

- [先找 Canonical Source](#先找-canonical-source)
- [更新已有文档](#更新已有文档)
- [新建文档](#新建文档)
- [新建 ADR](#新建-adr)
- [删除与归档](#删除与归档)
- [Owner 与状态](#owner-与状态)
- [Review Trigger](#review-trigger)

## 先找 Canonical Source

写文档前先回答：

1. 这个事实现在在哪里定义？
2. 是代码/Schema/配置自动定义，还是人工文档定义？
3. 是否已有文档负责这个主题？
4. 新内容的生命周期和 Owner 是否相同？

有 canonical source 时优先更新它。

## 更新已有文档

满足以下情况通常更新：

- 同一主题的当前事实改变；
- 同一流程新增一步；
- 同一模块增加能力；
- 同一约束发生合法调整；
- 当前概览需要反映最新架构；
- 命令或路径变化。

示例：

```text
本地启动从 npm 改为 pnpm
→ 更新 development/setup.md
→ 如果是 Agent 必须执行的命令，同时更新 AGENTS.md
```

## 新建文档

只有以下情况通常新建：

- 新主题有独立受众；
- 新主题有独立 Owner；
- 新主题生命周期不同；
- 旧文档范围会变得模糊；
- 新内容属于独立 How-to/Runbook；
- 一个文档已经同时回答多个互不相关问题。

不要因为内容多了 30 行就自动拆文件。

## 新建 ADR

当决定满足多个条件时新建 ADR：

- 难以逆转；
- 会影响多个模块/团队；
- 有多个合理备选；
- 显著影响安全、性能、可靠性、成本或维护；
- 未来的人很可能问“为什么”。

不要把普通重构、变量命名或框架默认配置写 ADR。

改变历史决定时：

1. 新建 ADR；
2. 标记旧 ADR superseded；
3. 更新当前架构文档；
4. 不删除旧原因。

## 删除与归档

文档失效时优先：

- 删除：内容已经没有历史价值；
- superseded：历史决定仍有解释价值；
- archived：法规、事故、迁移历史需保留。

禁止保留“可能以后有用”的错误当前文档。

AI 检索环境中，错误文档比缺失文档风险更高。

## Owner 与状态

长期文档建议有轻量 metadata：

```yaml
status: active
owner: platform-team
last_reviewed: 2026-08-07
```

只对确实需要治理的文档使用，不要求每个小 How-to 都写复杂 frontmatter。

状态建议：

```text
draft
active
deprecated
superseded
archived
```

## 状态总表（跨文档类型统一约定）

不同类型文档使用不同状态枚举，不要混用：

| 文档类型 | 状态枚举 | frontmatter 字段 |
| --- | --- | --- |
| 长期文档（overview/decision/runbook/how-to/working-agreements 等） | `draft` / `active` / `deprecated` / `superseded` / `archived` | `status` / `owner` / `last_reviewed` |
| ADR（决策记录） | `Proposed` / `Accepted` / `Rejected` / `Superseded` | `status` / `date` / `owners`（多团队） |
| 任务 handoff（临时状态） | `active` / `blocked` / `completed` / `abandoned` | `status` / `owner` / `created` / `expires_or_close_when` |

跨类型同名 `status` 字段值不同（如 handoff `completed` vs ADR `Accepted`），不要混填。

ADR superseded 关系不要靠 `superseded_by` 状态字串表达，使用专门的 `supersedes`/`superseded_by` 字段。
```yaml
status: Superseded
superseded_by: ADR-014
```

## Review Trigger

比固定半年检查更有效的是事件驱动更新。

典型 Trigger：

| 变更 | 必查文档 |
|---|---|
| 新服务/模块 | PROJECT_CONTEXT、architecture |
| API breaking change | contracts、migration guide |
| 新配置项 | development/configuration |
| 数据 Owner 改变 | data/ownership、architecture |
| 新部署方式 | development、operations |
| 新 SLO/告警 | operations |
| 新团队规则 | AGENTS/working-agreements |
| 重大架构决定 | ADR + architecture overview |

定期 Review 只作为漏网补偿。
