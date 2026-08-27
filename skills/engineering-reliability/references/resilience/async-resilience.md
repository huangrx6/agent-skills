# 异步任务韧性

消费者必须假设 duplicate、retry、delay、out-of-order 和进程在副作用后崩溃。

## 必须具备

- 幂等（业务唯一键、去重表、条件写入、inbox 模式）；
- 有界 concurrency（每消费者/每租户上限，防止一个慢任务占满）；
- retry classification（瞬态可重试 vs 永久失败）；
- delayed retry（退避 + 抖动，不立即重试）；
- DLQ/parking queue（重试耗尽后进入死信，不无限重投）；
- checkpoint（进度持久化，崩溃后从 checkpoint 恢复）；
- 安全重放工具（重放不产生重复副作用）。

## poison message

- 识别：消息重复失败、反序列化失败、业务永久失败。
- 处理：隔离到 parking queue/DLQ，附带失败原因和首次/最后失败时间。
- 不得无限重投 poison message（会拖垮消费者）。
- 人工处理路径：检查、修复、重放或丢弃，有审计。

## 积压恢复

- 积压时逐步增加消费 concurrency，避免瞬间压垮数据库或下游。
- 恢复速率按下游容量验证决定（如每秒最多增加 X）。
- 监控积压深度、oldest age、消费速率、生产速率。
- 若为瞬时峰值，等自然排空；若持续，检查下游容量或加消费者。

## 定时任务

必须明确：

- overlap（同一任务是否允许并发执行）；
- missed schedule（错过调度如何处理）；
- singleton/leader（分布式锁、leader election、锁过期）；
- lock expiry（锁超时后如何处理，避免重复执行）；
- 最大执行时间（超时终止）；
- 重复执行语义（幂等）。

## 监控

- queue depth、oldest age、incoming/processing rate、retry rate、DLQ rate、poison message 数。
- 告警：DLQ 增长、消费延迟超阈值、重试率异常、积压持续增长。

## 验证

- 测试：重复投递不产生重复副作用；崩溃后从 checkpoint 恢复；poison message 进 DLQ 不无限重投；积压恢复速率受控。
