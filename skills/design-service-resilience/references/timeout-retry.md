# 超时、Deadline 与重试

本文聚焦同步 HTTP/RPC 调用的超时与重试。消费者侧的重试、DLQ、幂等消费见 async-resilience.md；限流、背压、熔断见 overload-isolation.md；测试见 resilience-testing.md。

## Deadline

入口先定义总 Deadline，再向下游分配预算。下游 Timeout 不得大于调用方剩余时间。

需要分别考虑 connect、TLS、pool acquisition、request/write、response/read 和总操作时间。

### 预算分配原则

- 总 Deadline 来自业务 SLO（如"下单 P99 ≤ 1.5s"），不是随意值。
- 从入口向下游逐层递减：客户端 → Gateway → Service → 下游依赖，每层只能使用剩余预算。
- 预留一部分给自身处理（序列化/业务逻辑），不要把全部预算给下游。
- 下游收到调用时，必须知道剩余预算（通过 metadata/header 传递 deadline），不能每层重新获取完整超时。

### 超时类型

| 阶段 | 超时 | 说明 |
| --- | --- | --- |
| connect | 连接建立 | 通常几十 ms |
| TLS handshake | 握手 | 通常几十 ms |
| pool acquisition | 等待连接池 | 连接池耗尽时快速失败 |
| request/write | 发送请求 | 通常几 ms |
| response/read | 等待响应 | 主要等待时间 |
| 总操作 | 全流程 | 受剩余预算约束 |

单一总超时不够：连接卡住（connect timeout 缺失）会占满总超时导致下游永远得不到响应。每个阶段都应有上限，且总超时是最后防线。

## Retry

只有同时满足以下条件才重试：

- 大概率瞬态；
- 操作幂等或有幂等键/去重；
- 剩余 Deadline 足够；
- 当前 Retry Budget 未耗尽。

不要重试参数错误、权限错误、确定性业务冲突、非幂等未知结果和明确的整体过载失败。

### 可重试 vs 不可重试

| 失败 | 是否重试 | 理由 |
| --- | --- | --- |
| 连接重置 / 临时不可达 | 是 | 瞬态 |
| 下游 5xx（非过载） | 是（幂等时） | 瞬态可能性高 |
| 429 限流 | 是（遵循 Retry-After） | 上游指示稍后重试 |
| 4xx 业务错误 | 否 | 确定性失败 |
| 非幂等未知结果（超时后不确定是否提交） | 否 | 重试可能重复副作用 |
| 整体过载（Load Shedding 拒绝） | 否 | 重试加剧过载 |

### 重试参数

| 参数 | 说明 |
| --- | --- |
| maxAttempts | 最大尝试次数（含首次） |
| maxRetryDuration | 重试总时长上限（受剩余预算约束） |
| initialBackoff | 首次退避 |
| maxBackoff | 退避上限 |
| backoffMultiplier | 指数倍率（如 2x） |
| jitter | 随机抖动（±25% 或 full jitter） |
| retryableErrors | 明确的可重试错误集合 |

指数退避 + jitter 是防雪崩的关键：固定节拍会让大量客户端同步重试（thundering herd）。

### 重试预算

监控 retry/original 比例。重试占比异常升高时，优先停止重试、降级或将错误向上游传播。具体阈值由真实容量验证决定。

- 每请求重试预算：重试消耗受 deadline 约束（重试不能无限延长总时间）。
- 全局重试预算：某依赖的重试率超阈值（如 >20%）时，停止对该依赖重试，避免放大下游负载。
- 预算耗尽时：快速失败并把错误传给上游，而不是静默无限重试。

## Retry Ownership

A→B→C 时，如果 B 已负责重试 C，A 不应再次对同一 C 故障形成多层重试。

### 单层重试原则

- 每个失败只允许一个明确层负责重试。
- 多层重试放大：若 Gateway、Service、SDK 各重试 3 次，单请求可能放大为数十次下游调用，把局部故障变雪崩。
- 选择哪一层重试：通常选"最接近依赖、且能提供幂等保护"的一层。
- 其他层：只透传错误，不重试；或只做有限重试（如客户端对超时重试 1 次，但依赖 Service 已重试则不重复）。

### 幂等保护

- 重试写操作必须有幂等键、唯一约束、条件写入、版本检查或去重表。
- 超时不能证明写操作失败——重试前应查询状态或用同一幂等键，不盲目重提交。
- 幂等键契约设计（Header/作用域/冲突行为）属 API 契约 Skill；本 Skill 只负责重试调度。

## Backoff + Jitter

必须设置：最大 attempts、总 retry duration、最大 backoff、随机 jitter。

- fixed backoff：客户端同步重试 → thundering herd。
- exponential backoff：指数增长（2x/3x），但需上限。
- full jitter：`random(0, min(cap, base * 2^attempt))` 分散请求。
- 遵循 Retry-After：上游明确指示时，以它为准。

## 验证

- 测试：重试有上限（attempt/duration）、退避生效、jitter 分散、重试预算耗尽后快速失败、幂等重试不产生重复副作用。
- 故障注入：模拟下游超时/429/5xx，验证重试行为符合预期且不放大。
