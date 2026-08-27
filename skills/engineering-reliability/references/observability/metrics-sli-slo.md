# Metrics、SLI 与 SLO

## Golden Signals

用户服务通常至少关注 latency、traffic、errors、saturation。

基础资源可使用 USE：utilization、saturation、errors。

| 信号 | 含义 | 示例 |
| --- | --- | --- |
| latency | 请求处理耗时 | P50/P95/P99 |
| traffic | 请求量/吞吐 | requests/s、QPS |
| errors | 失败率 | 5xx/4xx、超时、异常 |
| saturation | 资源使用程度 | CPU、queue、连接池 |

## SLI

SLI 必须有 numerator、denominator、window、scope、exclusion 和 data source。

示例：`成功订单创建数 / 合法订单创建请求数`。

### 定义步骤

1. 从用户关键旅程选一个可观察行为（如"下单成功"）；
2. 定义 numerator（成功的）和 denominator（所有的合法请求）；
3. 定义 window（如 28 天）和 scope（服务/端点/租户）；
4. 定义 exclusion（哪些不算：压测、已取消、内网健康检查）；
5. 指定 data source（Trace 或 Metric，必须能持续采集）。

### 好 SLI 特征

- 从用户可见行为定义，不用 Pod Running 代替用户成功率；
- 可计算、可自动采集、可回溯；
- 与告警和容量决策直接相关。

## Latency

使用 Histogram/分布关注 P50/P95/P99。平均值不能代表尾延迟。

- 用 histogram 而不是 gauge 存延迟（可聚合分位数）；
- bucket 边界覆盖目标范围（如 100ms/200ms/500ms/1s/2s/5s）；
- P99 反映最差用户体验和排队信号。

## Cardinality

Metric label 必须有界。优先 route template、method、status class、dependency、region；避免 user/order/request ID、exception message、raw URL。

### 高基数字段处理

| 字段 | 归入 | 原因 |
| --- | --- | --- |
| user_id / order_id / request_id | Trace / Log | 每个请求都不同，Metric 会爆炸 |
| route template（/v1/orders/{id}） | Metric | 低基数、稳定 |
| raw URL | Log（脱敏后） | 高基数且可能含敏感 |
| exception message | Log | 高基数且可能含 PII |

评估 Metric 属性时计算笛卡尔组合后的 Series 数量：每个 label 的取值数相乘，超过可承受上限就降基数或移到 Trace/Log。

## SLO

SLO 表达用户期望，告警可使用 error-budget burn，而不是只对瞬时失败率配置固定阈值。

### error budget 计算

```text
SLO = 99.9% → error budget = 0.1% × 28d ≈ 40.3 min 的允许失败时间
```

### burn-rate 告警

- burn rate = 实际错误率 / 允许错误率；
- 多窗口 burn：如 1h 窗口 burn > 14.4（PAGE）+ 5min 窗口 burn > 14.4（快速恢复）；
- 高 burn 短窗口（快）触发页，低 burn 长窗口（慢）触发工单；
- 不只用瞬时失败率告警（单次抖动会误报，持续超预算才该行动）。

### 告警原则

- Alert 只针对需要人行动的问题；
- 优先 SLO burn、用户影响和容量风险；
- 长期没人处理的 Alert 应删除或重做。
