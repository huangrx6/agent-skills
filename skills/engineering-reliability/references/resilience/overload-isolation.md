# 过载、背压与隔离

## Overload Signals

不要只看 QPS。观察 CPU、memory、worker、connection pool、queue wait、event loop lag、DB pool、downstream saturation。

## Rate Limit

用于 per-user/per-tenant/per-API 配额和公平性。

必须定义：

- sustained rate 与 burst（如 token bucket 的 rate + burst size）；
- key（用户/租户/IP/API 维度）；
- scope（实例级还是全局共享）；
- 拒绝语义（429 + Retry-After / 排队）；
- 配额超限时的降级与恢复；
- 是否按租户公平（防止大租户占满配额）。

## Load Shedding

实例接近饱和前主动拒绝低优先级工作。拒绝必须比继续处理便宜。

必须定义：

- 触发信号（CPU/内存/queue wait 阈值）；
- 优先级等级（核心请求 > 后台任务 > 非关键流量）；
- 拒绝语义（快速 429/503，不占用资源）；
- 拒绝计数与告警；
- 恢复策略（信号回落后逐步恢复）。

## Backpressure

生产速率超过消费能力时使用 bounded queue、concurrency limit、credit/token、429/RESOURCE_EXHAUSTED、pause consumption 等机制。禁止无限队列。

必须定义：

- 队列容量与等待时间上限；
- 满时的丢弃优先级（先丢低优先级/旧数据）；
- 消费速率控制（逐步增加避免压垮下游）；
- 背压传播（向上游返回 429/RESOURCE_EXHAUSTED）；
- 有界缓冲（内存/磁盘上限）。

## Bulkhead

对高风险依赖、租户或流量等级隔离 worker/connection/queue 资源。

必须定义：

- 隔离粒度（依赖/租户/流量等级）；
- 每舱的连接池/线程池/队列大小；
- 舱内队列容量与等待超时；
- 舱满时的拒绝语义；
- 舱间不共享资源（避免一个舱拖垮整个实例）。

## Circuit Breaker

适用于持续故障、慢故障和失败调用成本高的依赖。Open/Half-open 恢复必须有界。

必须定义：

- 触发阈值（错误率/超时占比 + 时间窗）；
- Open 持续时间；
- Half-open 探测（限制并发探测数、成功阈值）；
- 不把熔断当超时替代（仍需 Timeout/Deadline）；
- 熔断期间的降级（返回 stale/fallback 或快速失败）；
- 恢复后逐步放量。

## Degradation

可关闭昂贵非核心功能、缩小结果、使用允许范围内的陈旧缓存。

### 降级模式分类

| 模式 | 含义 | 适用 |
| --- | --- | --- |
| FAIL_FAST | 立即返回错误，不降级 | 核心依赖不可用、无法降级 |
| STALE_RESPONSE | 返回允许范围内的陈旧缓存 | 读场景、非资金/权限 |
| DEFERRED | 异步处理，稍后重试 | 通知、审计、非实时 |
| THROTTLED | 限速处理 | 过载时保护核心 |
| PARTIAL | 缩小结果集/字段 | 列表、搜索 |

### 必须显式说明

- 完整度：降级响应缺少哪些数据；
- 陈旧度：缓存最大过期时间；
- 恢复条件：何时切回完整模式；
- 降级事件与告警；
- 高风险禁忌：支付、权限、资金操作不得使用 STALE_RESPONSE 或 PARTIAL 降级；这类场景只能 FAIL_FAST 或 DEFERRED（有明确幂等与对账）。

## Health 与 Load

- readiness 与 liveness 语义见 health-readiness.md。
- 过载与健康联动：实例过载时可保持 ready（活性正常），用 Load Shedding/限流处理，不因过载重启。
