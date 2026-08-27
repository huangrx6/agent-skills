# 文档类型与写作目的

## Diátaxis 四类

工程知识可以借用 Diátaxis 区分四种用途：

### Tutorial

面向学习。

目标：

```text
带新开发者从零完成一个受控任务。
```

不塞大量背景解释。

### How-to

面向工作目标。

例如：

```text
如何新增一个 API
如何执行数据库迁移
如何本地启动支付服务
```

步骤必须可执行。

### Reference

面向事实查询。

例如：

```text
配置项
API Schema
CLI 参数
错误码
数据字段
```

Reference 应准确、简洁、接近事实来源。

### Explanation

回答“为什么”。

例如：

```text
为什么订单与库存采用最终一致
为什么没有拆微服务
```

重大“为什么”通常进一步链接 ADR。

## 工程中特殊文档类型

### Overview

当前状态快照。

### Decision

历史决定及理由。

### Runbook

生产事件下的可执行恢复步骤。

### Handoff

临时未完成状态。

### Working Agreement

团队明确的长期协作规则。

### Generated Reference

从代码、Schema、配置生成，不手工编辑。

## 不要混用

常见失败：

- README 同时做 Tutorial + Reference + Architecture + Changelog；
- Runbook 前半篇解释理论，真正命令藏在末尾；
- API Reference 中混入历史讨论；
- ADR 不记录 alternatives，只写最终方案；
- PROJECT_CONTEXT 变成会议纪要。

一个文档有一个主要工作。
