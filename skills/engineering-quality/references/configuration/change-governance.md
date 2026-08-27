# 配置变更治理

## 变更流程

```text
proposal → schema validation → review → staging → canary → observe → rollout
```

每个阶段有明确通过/失败标准。

## 高风险配置

高风险配置包括 auth、payment、rate limit、thread/connection pool、timeout、cache consistency、retention。

| 高风险项 | 风险 |
| --- | --- |
| auth/payment 相关 | 安全与资金 |
| rate limit / pool / timeout | 容量与稳定性 |
| cache consistency / retention | 数据正确性 |

高风险配置必须：灰度、审计、快速回滚、canary 观察。

## 审计

审计记录 key、old/new（Secret 不记录明文）、actor、time、reason、scope、revision。

- 每次变更有审计事件；
- Secret 变更只记引用/元数据，不记明文；
- 审计可追溯（谁、何时、改了什么、影响范围）。

## Rollback

Rollback 必须能回到已知好 revision，不以"手工再改回去"作为唯一方法。

- 每个动态配置保留历史 revision；
- 回滚 = 切到上一个已知好 revision（原子）；
- 回滚后验证；
- 配置变更与代码变更一样可回滚。

## 漂移检测

检测 expected vs actual revision、环境差异和未跟踪本地 override。

- 运行实例报告配置 revision/摘要；
- 对比期望 revision vs 实际（漂移告警）；
- 检测未跟踪的本地 override（绕过配置中心的变更）；
- 环境间差异可查询。

## 测试

至少覆盖 missing required、invalid type/range、组合冲突、dynamic update、update failure、stale cache、rollback 和 config center unavailable。

- 缺失必填配置 → 启动失败；
- 非法类型/范围 → 拒绝；
- 组合冲突（connect_timeout >= request_deadline）→ 拒绝；
- 动态更新失败 → 保留旧值；
- 配置中心不可用 → last-known-good + stale 告警；
- 回滚 → 恢复旧 revision。
