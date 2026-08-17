# NovaPay 订单服务可观测性示范

## 1. SLI/SLO（从用户旅程定义）

| SLI | 定义 | window | 目标 |
| --- | --- | --- | --- |
| 下单可用性 | 成功创建订单 / 合法下单请求 | 28d | 99.9% |
| 下单延迟 | P99 < 800ms 的请求 / 合法请求 | 28d | 99.0% |

exclusion：压测流量、已取消、内网健康检查。

error budget（99.9% × 28d ≈ 40.3 min 允许失败）。

## 2. 信号目录

| 信号 | 用途 | requiredIdentity | cardinalityPolicy |
| --- | --- | --- | --- |
| METRICS | 趋势/SLI/告警 | service.name|environment | bounded_labels_only |
| TRACES | 请求因果 | service.name|version | sampled_high_cardinality_allowed |
| LOGS | 事件诊断 | service.name|trace_id | redacted_high_cardinality_allowed |
| PROFILES | 资源热点（可选） | service.name|version | controlled_sampling |

## 3. Metric 设计（低基数）

```text
orders_create_total{route="/v1/orders",status_class="2xx|4xx|5xx"}
orders_create_duration_ms_histogram{route="/v1/orders"}
orders_dependency_latency{downstream="payment-service"}
orders_saturation{resource="db_pool"}
```

高基数字段（order_id、user_id、merchant_ref）**不进 Metric**，进 Trace/Log attributes。

## 4. Trace 设计

Span 覆盖：

- inbound `POST /v1/orders`；
- outbound `payment-service.charge`、`inventory-service.reserve`；
- DB `orders.create`；
- queue `order-events.produce`。

Span name 用模板（`POST /v1/orders`），不用实际 ID。trace_id 跨 HTTP/gRPC/消息传播（W3C traceparent）。

采样：错误 trace 100% 保留、慢 trace（> P95）高保留、正常 trace 10%。

## 5. 告警策略（error-budget burn）

| 告警 | 条件 | severity | 动作 |
| --- | --- | --- | --- |
| orders-slo-burn | multi_window_burn（1h burn>14.4 + 5min burn>14.4） | PAGE | 调查用户影响 |
| queue-backlog | oldest_age 超预算 | TICKET | 检查容量 |

不用瞬时失败率阈值（单次抖动会误报）。

## 6. Dashboard 组织

- Service Overview：rate、success/error、latency、saturation、SLO；
- 依赖视图：payment/inventory 延迟/错误/配额；
- 容量视图：DB pool、queue、连接池；
- 每图有用途和 Owner，无维护的删。

## 7. Telemetry 预算

- metric series ≤ 5000/service；
- trace 采样后 ≤ 100 span/s；
- log ≤ 2 GB/day/实例；
- collector bounded queue + drop counter + self metrics；
- telemetry 故障不阻塞业务。

## 8. 故障演练验证

注入"payment 慢响应"故障，验证：

- 能否从 Dashboard 看到 payment 延迟上升；
- 能否用 Trace 定位到 payment-service.charge span；
- 能否用 Log 关联到受影响请求；
- SLO burn 告警是否触发；
- 结论：信号是否足够解释真实问题。
