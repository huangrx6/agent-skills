# 生产迁移计划：orders 新增 settlement_currency 列

## 基本信息

- 变更名称：orders 新增 settlement_currency（结算币种）
- Owner：交易组
- 数据库产品/版本：PostgreSQL 16
- 目标表：orders（约 500 万行）
- 表行数/大小：500 万行 / 约 3 GB
- 峰值 QPS：写 120 / 读 800
- 变更分类：MEDIUM（nullable 列 + 回填 + 后续 NOT NULL）
- 迁移工具/版本：Flyway 10

## 兼容性

- 旧应用 + 新 Schema：旧应用不读取新列，nullable 安全 ✓
- 新应用 + 旧 Schema：新应用在列不存在时回退到 currency 值 ✓
- 应用回滚是否安全：Expand 阶段可回滚应用（旧应用忽略新列）
- 后台任务/CDC/ETL 影响：CDC 消费者需确认是否解析新列；通知下游

## Expand

- DDL：`ALTER TABLE orders ADD COLUMN settlement_currency CHAR(3);`
- 预计 lock：PG 16 加 nullable 无默认列——AccessExclusiveLock 但元数据级，快速
- 是否表重写：否（nullable 无默认不重写）
- online/concurrent/instant 能力：PG 无 CONCURRENTLY 加列，但元数据操作毫秒级
- 临时空间：无
- lock/statement timeout：`SET lock_timeout = '3s'; SET statement_timeout = '30s';`

## Migrate

- 双写/双读：新写入同时写 currency 和 settlement_currency
- 回填范围：历史 500 万行，settlement_currency = currency
- batch size：每批 5000 行
- checkpoint：记录最后处理的 id 到 migration_progress 表
- rate limit：每秒 2 批（10000 行/s），观察复制延迟
- 预计时长：约 10 分钟
- 校验方式：
  - 行数：回填后 COUNT(settlement_currency IS NULL) = 0
  - 抽样：随机 1000 行比对 settlement_currency = currency

## Contract

- 删除旧读写的证据：应用日志确认无 settlement_currency IS NULL 的读取
- 观察窗口：3 天
- DROP/约束收紧：
  - `ALTER TABLE orders ALTER COLUMN settlement_currency SET NOT NULL;`
  - 移除应用回退逻辑

## 监控与停止条件

- DB CPU：> 70% 暂停
- I/O：等待队列 > 100ms 暂停
- lock wait：> 5s 暂停
- replication lag：> 10s 暂停
- 应用错误率：> 1% 暂停
- 停止阈值：任一触发即暂停回填，保持 Expand Schema 不变

## 失败处理

- 可安全取消阶段：Expand 后、Contract 前均可暂停
- cleanup：回填失败保留 nullable 列，不影响现有读写
- application rollback：Expand 阶段应用可回滚到不感知新列的版本
- forward fix：若 NOT NULL 失败（仍有 NULL），回到回填阶段补数据
- backup/PITR：变更前确认 PITR 窗口覆盖变更时间点

## 验证

- migration dry-run：在 staging（500 万代表性数据）完整跑通
- 代表性数据测试：含 NULL、多币种、边界 merchant_ref
- 数据一致性：回填后抽样 + 聚合校验
- 性能：回填期间订单查询 P99 ≤ 100ms（不影响业务）
- 新旧版本并存：旧应用（不感知新列）与新应用（双写）并存 24h
- 恢复演练：从变更前 PITR 恢复到测试环境，验证可回退
