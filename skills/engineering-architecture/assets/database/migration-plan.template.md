# 数据库生产迁移计划

## 基本信息

- 变更名称：
- Owner：
- 数据库产品/版本：
- 目标表：
- 表行数/大小：
- 峰值 QPS：
- 变更分类：LOW / MEDIUM / HIGH / DESTRUCTIVE
- 迁移工具/版本：

## 兼容性

- 旧应用 + 新 Schema：
- 新应用 + 旧 Schema：
- 应用回滚是否安全：
- 后台任务/CDC/ETL 影响：

## Expand

- DDL：
- 预计 lock：
- 是否表重写：
- online/concurrent/instant 能力：
- 临时空间：
- lock/statement timeout：

## Migrate

- 双写/双读：
- 回填范围：
- batch size：
- checkpoint：
- rate limit：
- 预计时长：
- 校验方式：

## Contract

- 删除旧读写的证据：
- 观察窗口：
- DROP/约束收紧：

## 监控与停止条件

- DB CPU：
- I/O：
- lock wait：
- replication lag：
- 应用错误率：
- 停止阈值：

## 失败处理

- 可安全取消阶段：
- cleanup：
- application rollback：
- forward fix：
- backup/PITR：

## 验证

- migration dry-run：
- 代表性数据测试：
- 数据一致性：
- 性能：
- 新旧版本并存：
- 恢复演练：
