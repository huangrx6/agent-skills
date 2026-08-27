# Kubernetes 配置

ConfigMap 用于非机密配置，Secret 用于机密数据。

## Environment Variable

ConfigMap/Secret 通过 environment variable 注入后，源对象更新并不会让已运行进程自动获得新值，通常需要 rollout/restart。

- env 注入在容器启动时一次生效；
- 修改 ConfigMap 后已运行 Pod 不会自动拿到新值；
- 需要 rollout/restart 才能生效（`kubectl rollout restart` 或更新 trigger）。

## Volume

Volume 挂载可由 kubelet 后续刷新，但应用必须重新读取文件；`subPath` 等挂载方式存在不同刷新行为。

- 普通 volume：kubelet 定期同步，应用需主动重新读取文件（如监听文件变化）；
- subPath 挂载：更新可能不刷新（视为不可靠）；
- 应用要有自己的 reload 机制（文件监听/周期重读）。

因此不能把"ConfigMap 已修改"当作"所有实例已生效"。生效语义取决于注入方式 + 应用重读机制。

## Secret

- 考虑 RBAC、etcd encryption、namespace 权限；
- 只给真正需要的 container 读取；
- Secret 不写入镜像、不写日志；
- base64 不是加密，etcd 加密需显式配置；
- 轮换：新 Secret 对象 + 重启或重读。

## Immutable

高稳定配置可以使用 immutable ConfigMap，再以新名称/revision 发布，减少意外原地修改。

- immutable 防意外修改；
- 变更走新名称 + 新 revision；
- 适合几乎不变的配置（如框架默认、固定协议参数）。

## 变更策略

- 关键配置变更走灰度（先部分实例）；
- 变更后验证（日志、指标、错误率）；
- 回滚：切回旧 ConfigMap/revision 并重启；
- 记录 revision 与生效范围。
