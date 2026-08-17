# Telemetry 治理

## 预算

为 telemetry 设预算：events/sec、metric series、trace volume、log GB/day、retention、export bandwidth、SDK overhead。

### 预算项

| 项 | 说明 | 示例 |
| --- | --- | --- |
| metric series | 所有 label 组合后的数量 | 每服务 ≤ 5000 series |
| trace volume | 每秒/每天 span 数 | 采样后 ≤ 100 span/s |
| log volume | 每天 GB | 每实例 ≤ 2 GB/day |
| retention | 各信号保留期 | metrics 90d / traces 30d / logs 30d |
| export bandwidth | 传输占用 | ≤ 5% 网络预算 |
| SDK overhead | 埋点 CPU/内存 | ≤ 2% CPU |

## Cardinality 治理

新增 Metric 属性前评估笛卡尔组合后的 Series 数量。

```text
如果 label A 有 10 值、B 有 20 值、C 有 100 值 → 10×20×100 = 20000 series
```

- 超过预算就降基数（用 status class 而非 status code、route template 而非 raw URL）；
- 高基数字段移到 Trace/Log attributes；
- 定期审查无引用 label 和废弃 series。

## Collector/Pipeline

Collector/Pipeline 需要 bounded queue、retry、drop counter、self metrics、health check。Telemetry 后端故障不能拖垮业务。

- bounded queue：有上限，满时丢弃低优先级并计数；
- retry：有界退避，不无限重试；
- drop counter：丢弃必须可见（指标/日志）；
- self metrics：collector 自身健康可观测；
- health check：管道状态可探测；
- 故障隔离：telemetry 故障不阻塞业务主流程。

## 采样

高频成功 Trace 可降采样，错误/慢 Trace 提高保留。Debug telemetry 必须有期限。

- head/tail sampling 结合（见 tracing-alerting.md）；
- debug 级别 telemetry 有自动过期（重启恢复、有效期）；
- 采样策略可配置，故障排查时可临时提高，但要有回退。

## 敏感数据

Telemetry 可能包含 PII/Secret/query text，仍需数据分类与脱敏。

- trace attributes 不记录完整敏感值（token、password、完整请求体）；
- log 字段按敏感策略脱敏（见日志规范）；
- query text 脱敏后再进 telemetry；
- 导出到外部平台前再次检查脱敏。

## 验证

通过故障演练验证：只依靠当前信号能否回答"谁受影响、从何时开始、哪一层根因、哪个版本"。

- 注入故障后，工程师能否用现有 Dashboard/Trace/Log 定位；
- 信号缺失时补齐，不是先建图后验证；
- 演练结果驱动 Dashboard 和告警调整。
