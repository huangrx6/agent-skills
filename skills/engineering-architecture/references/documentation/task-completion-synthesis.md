# AI 任务完成后的知识沉淀

## 目录

- [为什么必须在任务结束时做](#为什么必须在任务结束时做)
- [输入](#输入)
- [分类](#分类)
- [路由](#路由)
- [写入标准](#写入标准)
- [自动流程](#自动流程)
- [禁止行为](#禁止行为)

## 为什么必须在任务结束时做

任务进行中，Agent 拥有最完整的上下文：

- 用户为什么要改；
- 看过哪些旧代码；
- 做了什么选择；
- 哪些方案被拒绝；
- 哪些测试证明行为；
- 哪些坑只有这次才发现。

如果任务结束后不沉淀，新会话只能重新扫描和推理。

但不能把整个聊天记录提交到仓库。需要“提炼长期知识”。

## 输入

任务结束前检查四类输入：

1. 用户明确需求；
2. 最终代码 diff；
3. 测试/验证结果；
4. 本次产生的重要决策。

可选输入：

- Issue/PR；
- 事故记录；
- Benchmark；
- Migration 结果。

## 分类

把候选信息分成：

### A. Stable Fact

长期项目事实，例如：

```text
payments 模块是支付状态的唯一 Owner。
```

写入现有 canonical doc。

### B. Decision

例如：

```text
选择 Outbox 而不是同步双写。
```

满足 ADR 阈值时新建 Decision。

### C. Working Agreement

例如用户明确说：

```text
这个项目以后所有迁移都必须提供 dry-run。
```

写入 `working-agreements.md`；如果它是 Agent 必须执行的规则，再把简短执行要求写入 AGENTS。

### D. Operational Knowledge

例如：

```text
遇到 consumer lag 时先检查 partition skew。
```

写入 Runbook。

### E. Temporary Task State

例如：

```text
还有两个测试没修完。
```

仅写 active handoff。

### F. One-off Preference

例如：

```text
这次帮我先别跑集成测试。
```

不持久化。

## 路由

使用顺序：

```text
已有 canonical doc?
  ├─ 有 → 更新
  └─ 无
      ↓
是历史重要决策?
  ├─ 是 → 新 ADR
  └─ 否
      ↓
是可重复操作?
  ├─ 是 → How-to/Runbook
  └─ 否
      ↓
是明确项目工作约定?
  ├─ 是 → working-agreements
  └─ 否
      ↓
只是未完成状态?
  ├─ 是 → handoff
  └─ 否 → 不创建文档
```

## 写入标准

只有同时满足以下条件才沉淀：

- 对未来任务有价值；
- 项目相关；
- 可以验证；
- 不是秘密；
- 不是未经确认的个人推断；
- 找到了合适 Owner；
- 不与现有事实来源重复。

写入时：

- 删除聊天语气；
- 写成独立可理解事实；
- 添加上下文和边界；
- 链接代码/ADR/Schema；
- 不写“AI 认为”。

## 自动流程

任务结束前 Agent 执行：

```text
1. git diff / changed files
2. classify affected domains
3. run doc_impact.py
4. inspect candidate canonical docs
5. extract durable facts from conversation
6. update/create only necessary docs
7. run documentation validator
8. include "Documentation impact" in final task summary
```

推荐 PR 模板增加：

```text
Documentation impact:
- [ ] None
- [ ] Updated existing docs
- [ ] Added decision record
- [ ] Updated Agent/project context
- [ ] Added/closed handoff
```

## 禁止行为

禁止：

- 自动保存完整聊天 transcript；
- 每次任务都新建“task-summary-日期.md”；
- 把所有调试过程写进 PROJECT_CONTEXT；
- 把推测当成事实；
- 把个人偏好自动提交到团队仓库；
- 因为用户称赞某种写法就永久写入规则；
- 创建新文档而不更新 docs/index；
- 只更新文档不更新真正的 Schema/配置事实来源。
