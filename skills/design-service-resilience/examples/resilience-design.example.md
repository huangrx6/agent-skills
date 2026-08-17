# NovaPay 订单服务韧性设计示范

> 场景：POST /v1/orders 创建订单。调用链：HTTP 入口 → 订单服务 → 支付服务 + 库存服务 + 审计事件。

## 1. 关键路径与超时预算

```
客户端 → API Gateway → OrderService → PaymentService
                                → InventoryService
                                → AuditEvent (Pub-Sub)
```

| 节点 | 分配预算 | 包含操作 |
| --- | --- | --- |
| 总 Deadline（客户端契约） | 1500ms | 全链路 |
| Gateway → OrderService | 1200ms | HTTP |
| OrderService → PaymentService | 600ms | HTTP |
| OrderService → InventoryService | 400ms | HTTP |
| 审计事件 | 50ms | 仅确认发出，不等下游 |

下游 Timeout 不得大于调用方剩余时间（如 PaymentService 收到 OrderService 调用时剩余 ≤600ms）。

## 2. 重试责任

| 层 | 是否重试 | 理由 |
| --- | --- | --- |
| 客户端 | 否 | 客户端不该假设服务端幂等 |
| API Gateway | 否 | 网关重试 = 多层重试放大 |
| OrderService → PaymentService | 是 | 本服务内统一层重试（限 1 次 + 幂等键） |
| PaymentService 内部 | 否 | 已由上游重试 |

幂等键：`Idempotency-Key`（`merchantRef + amount`），`POST /v1/payments` 用同一 key 重试同结果。

## 3. 重试参数

| 参数 | 值 | 说明 |
| --- | --- | --- |
| maxAttempts | 2（含首次） | 1 次重试 |
| maxRetryDuration | 300ms | 不超过 PaymentService 预算一半 |
| initialBackoff | 50ms | 首次退避 |
| maxBackoff | 200ms | 退避上限 |
| jitter | ±25% | 随机抖动防同步 |
| retryable | timeout / 429 / 503_if_idempotent | 仅瞬态且幂等 |
| Retry Budget | 10%（20% 上限） | 总请求中重试占比超限触发降级 |

不要重试：参数错误、权限拒绝、确定性业务冲突（如 ORDER_STATE_CONFLICT）、非幂等未知结果。

## 4. 舱壁隔离

| 资源 | 隔离粒度 | 配额 |
| --- | --- | --- |
| PaymentService 连接池 | 全局 | 50 |
| InventoryService 连接池 | 全局 | 100 |
| 高风险租户（Top 5%） | 独立连接池 | 各 20 |
| 异步任务 worker | 共享 + 单租户限流 | 总 200，租户 ≤ 20 |
| 队列容量（订单事件） | 有界 | 10000（超过触发背压） |

## 5. 熔断与降级

| 依赖 | 熔断阈值 | 降级策略 |
| --- | --- | --- |
| PaymentService | 50% 错误率持续 30s | 标记订单 PENDING_PAYMENT，异步重试；不阻断下单 |
| InventoryService | 50% 错误率 | 返回预扣库存失败，订单允许跳过库存扣减（业务特定） |
| 审计事件 | 始终非阻塞 | 失败时写本地缓冲 + 告警；不阻断主流程 |

降级必须显式：响应带 `degradation: { component: "payment", mode: "deferred", stale: false }` 字段。

## 6. 限流与过载

- Per-tenant rate limit：1000 RPS（sustained）+ 2000 burst
- 实例 CPU > 75% 时触发 Load Shedding：拒绝低优先级流量（404 限流错误码）
- Queue depth > 80%：背压降级（减慢入队或 429）

## 7. 故障注入计划（执行验证）

```text
- Service: order-service
- Owner: 交易组
- Hypothesis: PaymentService 持续 1s 慢响应下，OrderService 不会拖垮实例（P99 ≤ 800ms）
- Blast radius: 1 个 canary 实例，1% 流量
- Stop condition: P99 > 1.5s 或错误率 > 5% 持续 2min

## Failure
PaymentService 全连接延迟 1s
## Expected behavior
OrderService P99 < 800ms；Bulkhead 限流生效；熔断 30s 后打开
## Metrics
OrderService P99/P99.9/错误率；PaymentService 客户端超时次数；bulkhead 拒绝数；熔断状态变化
## Result
[待执行]
## Follow-up
[待记录]
```

## 8. 监控与告警

- P99/P99.9 延迟、错误率（必须含 retry rate）
- Bulkhead 拒绝数、熔断状态变化
- Queue depth、oldest age、DLQ rate
- 依赖调用超时占比、5xx/429 上游分布
- Retry budget 剩余比例（< 20% 告警）

## 9. 职责边界

本 Skill 负责韧性保护机制（超时预算、重试调度、隔离、熔断、降级、故障注入验证），不复制错误处理、架构、容量与安全的细节。

上层职责划分：

- 错误码、超时、重试、取消、幂等：异常处理层；
- API 重试与幂等键契约：API 契约层；
- 架构边界与威胁模型：架构层；
- 容量与限流模型：性能与容量层；
- 超时/重试/隔离/降级/背压的**实施**（本 Skill）。
