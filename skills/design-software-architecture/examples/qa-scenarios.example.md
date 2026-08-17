# NovaPay QA 场景示例（4 条）

| id | 属性 | source | stimulus | environment | artifact | response | measure | priority |
|---|---|---|---|---|---|---|---|---|
| QA-101 | PERFORMANCE | 终端用户 | 提交交易 | 正常高峰 | 交易受理 API | 完成交易创建 | P99 ≤ 800ms | HIGH |
| QA-102 | AVAILABILITY | 可用区故障 | 计算节点不可用 | 高峰期 | 交易系统 | 流量切换并继续服务 | 2 分钟恢复；错误率 <1% | HIGH |
| QA-103 | RECOVERABILITY | 数据库故障 | 主节点不可恢复 | 灾难恢复 | 交易数据 | 从备份/PITR 恢复 | RPO ≤ 5min；RTO ≤ 30min | HIGH |
| QA-104 | COST | 产品/财务 | 扩展到 5 倍当前容量 | 正常运行 | 基础设施 | 成本可预测 | 单交易成本增长 ≤ 2x | MEDIUM |
