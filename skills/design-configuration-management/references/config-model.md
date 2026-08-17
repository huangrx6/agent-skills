# 配置模型

## 分类

| 分类 | 含义 | 示例 | 变更方式 |
| --- | --- | --- | --- |
| Code Constant | 协议/算法固定值 | HTTP 语义、数学常量 | 改代码 |
| Deployment Config | 环境参数 | 地址、线程数、timeout | 部署时注入 |
| Secret | 敏感凭据 | password/token/private key | Secret Manager |
| Dynamic Config | 运行时调整 | rate limit、开关 | 配置中心 |
| Feature Flag | 渐进启用/实验/kill switch | 新功能开关 | Flag 平台 |

分类决定：变更方式、回滚方式、审计要求、是否可动态更新。

## Schema

每项配置定义：key、type、unit、required、default、min/max、enum、secret、dynamic、owner、description。

命名示例：`http.client.payment.timeout_ms`、`worker.order.concurrency`。

### 命名规则

- 点分命名空间：`<domain>.<component>.<key>`；
- 单位进名称（`timeout_ms`、`concurrency`）；
- 避免歧义（`retry_count` vs `retry_total_duration`）。

### 类型与校验

- 类型：STRING/INTEGER/FLOAT/BOOLEAN/DURATION/LIST/MAP；
- 校验：type、range、enum、required、跨字段组合（如 `connect_timeout < request_deadline`）；
- 启动时完整校验，无效配置直接失败（fail fast），不静默用默认值。

## Defaults

默认值必须安全、可解释、跨环境合理。

- 关键生产地址和凭据通常不应有隐藏默认值（无默认值，缺失即报错）；
- 容量参数默认值要保守，不能默认大并发大缓存；
- 默认值改变要评审（同代码变更）。

## Precedence

必须记录唯一顺序，例如：code safe defaults < versioned config < deployment config < approved dynamic config。

- 同一 key 不应被 env、文件、参数、配置中心多层覆盖而无人知道最终值；
- 来源和优先级必须显式、可查询；
- 环境差异（dev/prod）通过 deployment config 表达，不在代码里 if env。

## Validation

启动时验证 type、range、enum、required 和跨字段约束，例如 `connect_timeout < request_deadline`。

- 校验失败即启动失败，不降级为默认；
- 动态配置变更时同样校验（见 dynamic-configuration.md）；
- 校验信息不含 Secret 值。
