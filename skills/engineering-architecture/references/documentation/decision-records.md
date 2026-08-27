# 决策记录

## 何时记录

满足多个条件时记录：

- 难逆转；
- 多个合理方案；
- 跨模块；
- 显著影响性能、安全、可靠性、成本或兼容性；
- 未来很可能重新讨论。

## 最小结构

```text
Title
Status
Date
Context
Decision Drivers
Considered Options
Decision
Consequences
Validation
Revisit Trigger
```

与 `assets/decision.template.md`（MADR 风格）保持一致；模板还包含 `Related` 与 `supersedes`/`superseded_by` 关系字段。

## 不可静默改写历史

当决定改变：

```text
ADR-001 Accepted
↓
新事实出现
↓
ADR-014 Supersedes ADR-001
```

当前 `architecture/overview.md` 更新为新状态。

旧 ADR 保留当时为什么做出决定。

ADR 社区也把 ADR 定义为记录重要架构决定及其上下文和后果的文档；新决定取代旧决定时，应保留关系，而不是让历史原因消失。

## ADR 与 PROJECT_CONTEXT

PROJECT_CONTEXT：

```text
当前使用 PostgreSQL 作为订单权威存储。
```

ADR：

```text
为什么当时选择 PostgreSQL 而不是 DynamoDB。
```

两者不要互相替代。

## ADR 与会议纪要

会议不是决策。

不要把：

```text
2026-08-07 架构会议纪要
```

当作 canonical decision。

从会议中提取正式 Decision。
