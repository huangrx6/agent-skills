# NovaPay 订单服务配置管理示范

## 1. 配置分类

| 分类 | 示例 | 变更方式 | 回滚 |
| --- | --- | --- | --- |
| Code Constant | HTTP 语义、协议常量 | 改代码 | 代码回滚 |
| Deployment Config | payment 地址、线程数 | 部署时注入 | 部署回滚 |
| Secret | DB password、API key | Secret Manager | rotation |
| Dynamic Config | rate limit、pool 大小 | 配置中心 | revision 回滚 |
| Feature Flag | 新支付渠道开关 | Flag 平台 | 即时关闭 |

## 2. Schema（示例）

| key | type | unit | required | default | dynamic | secret | owner |
| --- | --- | --- | --- | --- | --- | --- | --- |
| http.client.payment.timeout_ms | INTEGER | ms | true | 800 | true | false | payments |
| worker.order.concurrency | INTEGER | count | true | 16 | true | false | orders |
| database.password_secret_ref | STRING | — | true | — | false | true | platform |

- 生产地址和凭据无隐藏默认值（缺失即报错）；
- 跨字段校验：`connect_timeout < request_deadline`；
- 启动时完整校验，失败即启动失败。

## 3. 来源优先级

| priority | source | allowedFor |
| --- | --- | --- |
| 10 | CODE_DEFAULT | safe defaults |
| 20 | VERSIONED_CONFIG | application config |
| 30 | DEPLOYMENT_CONFIG | environment specific |
| 40 | DYNAMIC_CONFIG | approved dynamic keys |

同一 key 不被多层覆盖而无人知道最终值；来源可查询。

## 4. 动态配置策略

| keyPattern | reloadMode | validation | fallback | maxStale |
| --- | --- | --- | --- | --- |
| worker.* | ATOMIC_SNAPSHOT | schema+semantic | LAST_KNOWN_GOOD | 30m |
| feature.* | ATOMIC_SNAPSHOT | schema | SAFE_DEFAULT | 15m |

- rate_limit/burst/window 同 revision 原子更新；
- 失败保持旧 revision；
- 配置中心故障用 last-known-good，超过 maxStale 按风险 fail closed；
- 业务线程不阻塞（本地缓存 + 有界重试）。

## 5. Secret 分离

- 普通配置只存 `database.password_secret_ref`（引用），不存原值；
- Secret 由 Vault/K8s Secret 管理，最小权限、审计、rotation；
- Secret 不进入 ConfigMap、Git、日志；
- base64 不是加密（etcd 加密需显式配置）；
- 轮换双密钥重叠期不中断业务。

## 6. Feature Flag

- `payment.new-gateway`：Release 类型，targeting 1%→100%，owner payments，expiry 30d；
- 100% 后移除 flag 和死代码；
- 定期清理 no-owner、expired、永久 0/100% 的 flag。

## 7. Kubernetes 配置

- env 注入：ConfigMap 修改后需 rollout/restart 才生效；
- volume 挂载：kubelet 刷新但应用需重新读文件；
- subPath：刷新不可靠；
- 高稳定配置用 immutable ConfigMap + 新名称发布。

## 8. 变更流程（示例：payment timeout 800→600ms）

```text
proposal → schema validation → review → staging → canary (1% 实例) → observe (30min) → rollout
```

- 审计：key、old(800)/new(600)、actor、time、scope、revision；
- 回滚：切回 revision（已知好版本），不手工改回；
- 漂移检测：对比期望 vs 实际 revision，发现未跟踪 override。

## 9. 测试

- 缺失必填 → 启动失败；
- 非法类型/范围 → 拒绝；
- 组合冲突（connect_timeout >= request_deadline）→ 拒绝；
- 动态更新失败 → 保留旧值；
- 配置中心不可用 → last-known-good + stale 告警；
- 回滚 → 恢复旧 revision。
