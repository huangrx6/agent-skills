# 韧性测试

## Failure Injection

覆盖场景：

- dependency timeout（下游响应超时）；
- connection refusal（连接拒绝）；
- slow response（慢响应，观察超时与熔断）；
- 429/503（下游限流/不可用）；
- DB pool exhaustion（连接池耗尽）；
- queue full（队列满，背压生效）；
- broker unavailable（消息代理不可用）；
- instance kill（实例被杀，就绪/存活探针行为）；
- DNS/network latency（DNS 解析延迟、网络抖动）。

每个场景验证：

- 保护机制是否按预期触发（超时/重试/熔断/背压/降级）；
- 是否有资源泄漏（连接/线程/内存）；
- 恢复后是否正常（半开探测、积压排空）；
- 指标和告警是否反映注入的故障。

## Overload Test

逐步增加负载直到超过设计容量，验证：

- 是否在 crash 前拒绝（Load Shedding/限流生效）；
- queue 是否有界（不无限堆积）；
- retry 是否被限制（retry budget 生效）；
- 低优先级流量是否先削减；
- 恢复后 backlog 是否可控；
- 实例是否避免 OOM/线程池耗尽；
- 核心流量是否获得可预测服务（P99 满足目标）。

超载测试必须记录：设计容量、实际崩溃点、保护机制触发顺序、恢复时间。

## Chaos

Chaos 用于验证明确假设。生产实验必须有：

- blast radius（影响范围，如 1 实例/1% 流量）；
- Owner；
- 监控（实时观察）；
- 自动停止条件（指标超阈值自动终止）；
- 回滚方案。

Chaos 不是随意破坏，是验证特定韧性假设。

## 测试断言（可自动化）

- 依赖超时后 P99 不超预算；
- 重试有上限（attempt/duration）；
- 队列有界（不无限增长）；
- 熔断打开后快速失败；
- 降级响应可区分；
- 故障恢复后指标回到基线。
