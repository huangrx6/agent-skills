# PostgreSQL / MySQL 实施提示

本文件只用于把通用规则映射到具体数据库，最终以项目实际版本官方文档为准。

## PostgreSQL

重点检查：

- `CREATE INDEX CONCURRENTLY` 的阶段、失败后的 invalid index 和事务限制；
- `ALTER TABLE` 不同子命令的锁等级；
- 大表加约束可考虑 `NOT VALID` + 后续 `VALIDATE CONSTRAINT`（适用约束）；
- 使用已有 unique index 绑定 constraint 的能力；
- `timestamptz` 与 session TimeZone 的显示语义；
- MVCC、VACUUM、长事务和表膨胀；
- transaction isolation / serialization failure；
- WAL、replication slot 和 PITR；
- partition pruning 和分区维护。

不要因为某个 `ALTER TABLE` 在新版本有 fast path，就假设旧版本也相同。

## MySQL / InnoDB

重点检查：

- `ALGORITHM=INSTANT/INPLACE/COPY` 是否支持目标 DDL；
- `LOCK` 语义和 concurrent DML 能力；
- metadata lock；
- Online DDL 的临时空间和失败条件；
- invisible index 用于删除索引前验证影响；
- InnoDB isolation 和 gap/next-key lock；
- 自增主键、聚簇索引和随机主键写入局部性；
- binlog/replica lag；
- charset/collation 和大小写唯一性；
- online schema change 工具的触发器、复制和切表风险。

## 共同要求

生产变更说明中必须写明：

- 数据库产品和版本；
- DDL 预计 algorithm/lock；
- 测试数据规模；
- 最大锁等待；
- 是否表重写；
- 临时空间；
- 复制延迟阈值；
- 暂停条件；
- 失败清理步骤。
