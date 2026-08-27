# 结构化字段与链路关联

## 字段原则

优先使用结构化字段，不把关键上下文仅拼接进 `message`。

字段必须：

- 命名稳定；
- 类型稳定；
- 单位明确；
- 含义唯一；
- 跨服务尽量一致；
- 有明确的数据分类、索引和保留要求。

## 推荐公共字段

公共字段（登记在 `assets/log-format-schema.csv`，所有事件通用）：

```text
timestamp
observed_timestamp
level
severity_number
service.name
service.version
deployment.environment
event.name
schema.version
message
trace_id
span_id
correlation_id
duration_ms
log.truncated
```

常用事件专属字段（登记在 `assets/log-event-fields.csv`，按事件按需引用）：

```text
operation
error.code
error.type
dependency.name
retry.count
degradation.type
actor.id
resource.id
action
result
auth_type
failure.reason
audit.action
```

不要同时使用 `traceId`、`trace_id`、`trace-id` 等多个名称表达同一概念。团队应选择一个约定并集中维护。

事件目录中 `requiredFields` 引用的每个字段必须能在 `log-format-schema.csv` 或 `log-event-fields.csv` 之一找到登记（由校验脚本强制）。

## 上下文注入

链路与业务上下文应在入口统一注入日志上下文（日志框架的上下文 Map 或等效机制），而不是在每个日志调用点手工传递：

- HTTP/RPC 入口：解析或生成 trace/request 标识，写入日志上下文，请求结束后清理；
- 消息消费者、定时任务、批处理：在任务开始处生成并注入标识；
- 业务操作上下文（操作名、模块）：在统一业务事件记录点注入，随该操作的所有日志自动携带；
- 上下文随日志输出平铺为顶层字段（结构化流）或出现在人读流前缀（文本流），字段语义一致；
- 线程池/异步执行必须显式传递上下文，禁止隐式依赖调用线程上下文残留；
- 入口清理不完整会导致上下文串号，必须在测试中覆盖"上下文隔离"。

## 事件名称

`event.name` 应使用稳定机器标识，例如：

```text
order.created
payment.authorization.failed
inventory.reservation.retry_exhausted
user.permission.changed
authentication.failed
```

事件名称表达"发生了什么"，日志级别表达"影响多大"，错误码表达"为何失败"。三者不得混用。

成功与失败的配对事件应使用成对命名（`authentication.succeeded` / `authentication.failed`），便于聚合对比。

事件名在代码中应集中定义为常量或枚举，禁止散落字符串字面量，避免拼写漂移导致聚合断裂。

## 链路关联

在 HTTP、RPC、消息、后台任务和定时任务之间传播 trace 或 correlation 上下文。

同一标识应关联：

- 应用日志；
- 分布式链路；
- 重试和死信记录；
- 安全情况下的对外错误响应；
- 事故和客服处理流程。

禁止把用户机密或有直接业务含义的标识编码进 trace ID。

## 高基数字段

用户 ID、订单 ID、URL、SQL 指纹等高基数字段必须明确用途和索引策略。不得默认把所有动态值建立索引，否则可能导致成本和查询性能失控。

## 字段目录

为公共字段登记：

- 字段名称；
- 是否必填；
- 数据类型；
- 格式或单位；
- 数据分类；
- 是否索引；
- 最大长度；
- 示例值。

为关键日志事件登记：

- `eventName`；
- 触发条件；
- 默认级别；
- 责任边界；
- 必需字段；
- 采样策略；
- 保留期；
- 责任团队。

使用内置字段目录和事件目录模板集中维护。
