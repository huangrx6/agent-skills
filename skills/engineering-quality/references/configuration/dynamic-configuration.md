# 动态配置

## 刷新机制

必须定义 polling/push、refresh interval、revision、atomic snapshot、local cache、fallback、rollback。

| 机制 | 说明 |
| --- | --- |
| polling | 定时拉取，简单但延迟高 |
| push | 服务端推送，低延迟但需连接管理 |
| refresh interval | 拉取频率（如 30s） |
| revision | 配置版本标识（单调递增） |
| atomic snapshot | 一批相关字段作为一个版本读取 |
| local cache | 客户端缓存最后有效配置 |
| fallback | 配置中心不可用时的行为 |
| rollback | 恢复到已知好 revision |

## Last Known Good

配置中心失败时保留最后有效版本；不得用空值覆盖。记录 stale age，超过最大允许陈旧时间后按风险 fail closed 或降级。

- 安全相关配置：fail closed（超过 maxStale 拒绝）；
- 非安全配置：可按风险使用 last-known-good 或降级。

## Atomic Apply

相关字段作为同一 revision 更新。例如 rate_limit/burst/window 不能分批生效。

应用流程：parse → schema validate → semantic validate → stage → atomic swap → emit change event。

失败保持旧 revision。

- 半套新值（rate_limit 新值 + burst 旧值）会导致行为不一致；
- 用 revision 快照保证读取一致性；
- 变更事件可观测（revision/change event）。

## Side Effects

如果更新触发 pool resize、connection recreate、model reload、cache clear，必须定义失败与回滚。

- 副作用可能失败（如连接池扩容失败）；
- 失败时保持旧配置（原子回滚）；
- 副作用期间新请求行为要明确（短暂用旧值 or 排队）。

## Client

业务线程不能同步依赖配置中心；客户端使用本地缓存、timeout、bounded retry、metrics 和 last-known-good。

- 读取配置不阻塞（缓存优先）；
- 刷新失败不把当前有效配置清空；
- 配置中心故障不拖垮业务（有界重试 + 降级）；
- 暴露配置 revision/摘要指标（不含 Secret）。
