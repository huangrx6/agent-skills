# Tracing、Dashboard 与告警

## Span

为 inbound request、outbound HTTP/gRPC、DB、queue produce/consume 和重要内部操作建 Span。Span name 使用稳定低基数名称，不包含实际资源 ID。

### 建 Span 的边界

| 建 Span | 不建 Span |
| --- | --- |
| inbound HTTP/gRPC 请求 | 每个 helper 函数 |
| outbound 依赖调用 | 纯内存计算 |
| DB 查询 | 循环内每次迭代（聚合到一个 Span） |
| queue produce/consume | 无关紧要的日志级别操作 |
| 重要内部操作（支付、权限） | 高频低价值调用 |

Span name 用模板（`GET /v1/orders/{orderId}`），不用实际 ID（`GET /v1/orders/123`）——否则高基数无法聚合。

### Span 属性

- 记录业务相关低基数属性（route、status、dependency）；
- 高基数（order_id、user_id）放 attributes，供查询但不上 Metric；
- 错误/异常记录 error event，不吞掉。

## Context

Trace Context 必须跨线程/协程/HTTP/gRPC/消息边界传播。

- 入口生成或接收 trace_id/span_id，写入上下文；
- 线程池/异步任务显式传播（Context Propagation），不依赖线程局部残留；
- HTTP 用 W3C traceparent；gRPC 用 metadata；消息队列在 header 传播；
- 上下文必须清理，避免串号。

## Sampling

明确 head/tail sampling。错误、高延迟和关键业务流量应优先保留。

### Head sampling

- 入口决定采样与否；
- 适合简单场景，但可能丢关键错误（如果错误发生在采样决策之后）。

### Tail sampling

- 等完整 trace 结束后按规则采样（保留含 error/慢的 trace）；
- 更精准，但需要缓冲和复杂度；
- 错误和慢请求应优先保留（错误率 < 5% 时保留全部错误成本可控）。

### 采样策略

- 错误 trace：100% 保留；
- 慢 trace（> P95）：高比例保留；
- 正常 trace：按预算采样（如 10%）；
- 关键业务（支付、权限）：单独提高保留率。

## Dashboard

Service Overview 至少包含 rate、success/error、latency、saturation、SLO；依赖和容量单独组织。

### Dashboard 组织原则

- 按排障问题组织，不按"指标数量"组织；
- Service Overview：该服务的 RED + SLO；
- 依赖视图：下游调用延迟/错误/配额；
- 容量视图：CPU/内存/queue/连接池；
- 每个图有明确用途和 Owner；
- 过多图且无人维护的 Dashboard 应删。

## Alert

Page 的前提：用户受影响、需要立即行动、不处理会恶化、存在 Owner/Runbook。长期没人处理的 Alert 应删除或重做。

### 告警分级

| 级别 | 触发条件 | 动作 |
| --- | --- | --- |
| PAGE | 用户受影响、需立即行动 | 即时通知 + runbook |
| TICKET | 需要人看但不紧急 | 工单跟踪 |
| INFO | 仅记录 | 不打扰 |

### 告警设计

- 每条 Alert 有明确条件、Owner、runbook；
- 用 SLO burn 而不是瞬时阈值（见 metrics-sli-slo.md）；
- 告警静默必须有上限和复核；
- 重复/聚合避免风暴；
- 通知内容脱敏，不含敏感日志。
