# Feature Flag 与 Secret

## Feature Flag

类型可包括 Release、Experiment、Operational Kill Switch、Entitlement。不要用 Feature Flag 替代真正授权系统。

### Flag 类型

| 类型 | 用途 | 示例 |
| --- | --- | --- |
| Release | 渐进发布新功能 | 新支付渠道 1%→100% |
| Experiment | A/B 测试 | 不同算法对比 |
| Operational Kill Switch | 紧急关停 | 暂停某依赖调用 |
| Entitlement | 功能权限 | 会员专属功能 |

### 必须定义

- key（唯一、低基数）；
- owner；
- purpose；
- created_at；
- targeting（用户/租户/百分比/环境）；
- default；
- expiry/removal condition。

### 生命周期

create → dark launch → canary → rollout → 100% → remove flag and dead code。

- 100% 后必须移除 flag 和死分支（否则永久残留）；
- 定期清理 no-owner、expired、永久 0/100% 和死分支；
- Flag 变更走配置变更流程（灰度、审计、回滚）。

## Secret

Secret 包括 password、API key、token、private/signing key。

### 原则

- 普通配置只保存 Secret reference（如 `database.password_secret_ref`），不保存原值；
- Secret 由独立 Secret Manager 管理（支持最小权限、审计、rotation、环境隔离）；
- Secret 不进入 ConfigMap、普通配置文件、Git、日志或文档；
- Kubernetes Secret 的 base64 不是加密；
- 应用读取 Secret 后仍必须避免日志、转发和意外暴露；
- 密钥轮换不中断业务（双密钥重叠期）。

### 验证

- 测试：Secret 不出现在日志/配置导出/错误信息；
- 审计：谁读取了哪个 Secret；
- rotation 演练。
