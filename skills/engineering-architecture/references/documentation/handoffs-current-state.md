# 任务 Handoff 与当前状态

## 使用条件

只有在任务未完成且下一位人/Agent 需要继续时创建 handoff。

典型场景：

- 跨会话长任务；
- 跨时区开发；
- 需要等待外部依赖；
- 复杂迁移分阶段执行；
- Agent 上下文即将结束。

## 内容

Handoff 必须包含：

- Goal；
- Current State；
- Completed；
- Remaining；
- Changed Files；
- Validation；
- Known Risks；
- Exact Next Step；
- Relevant Docs；
- Expiry/Close Condition。

## 不要复制日志

不要写：

```text
我先看了 A，然后想了 B……
```

只写继续工作所需状态。

## 生命周期

状态：

```text
active
blocked
completed
abandoned
```

任务完成后：

- 删除没有历史价值的 handoff；
- 或移到 archive；
- 重要长期事实迁移到 canonical docs；
- 决策迁移到 ADR；
- 不让 handoff 成为永久知识库。

## Current State 文档

不要维护全仓库单一 `current-state.md` 记录所有正在发生的事情。

它会快速过期，并让 AI 误判优先级。

任务状态属于 Issue/PR/任务系统；Handoff 只用于真正需要上下文续接的例外。
