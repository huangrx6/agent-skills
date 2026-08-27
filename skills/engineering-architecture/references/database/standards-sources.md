# 官方资料与使用原则

## PostgreSQL

- PostgreSQL Current — Data Types  
  <https://www.postgresql.org/docs/current/datatype.html>
- PostgreSQL Current — Modifying Tables  
  <https://www.postgresql.org/docs/current/ddl-alter.html>
- PostgreSQL Current — ALTER TABLE  
  <https://www.postgresql.org/docs/current/sql-altertable.html>
- PostgreSQL Current — CREATE INDEX  
  <https://www.postgresql.org/docs/current/sql-createindex.html>
- PostgreSQL Current — Transaction Isolation  
  <https://www.postgresql.org/docs/current/transaction-iso.html>
- PostgreSQL Current — Backup and Restore  
  <https://www.postgresql.org/docs/current/backup.html>

生产 DDL 必须查询项目实际 PostgreSQL 主版本的文档，不只看 current。

## MySQL

- MySQL 8.4 Reference — InnoDB and Online DDL  
  <https://dev.mysql.com/doc/refman/8.4/en/innodb-online-ddl.html>
- MySQL 8.4 Reference — Online DDL Operations  
  <https://dev.mysql.com/doc/refman/8.4/en/innodb-online-ddl-operations.html>
- MySQL 8.4 Reference — Invisible Indexes  
  <https://dev.mysql.com/doc/refman/8.4/en/invisible-indexes.html>
- MySQL 8.4 Reference — Transaction Isolation  
  <https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-isolation-levels.html>

## MongoDB（仅文档库场景）

- Schema Design Process  
  <https://www.mongodb.com/docs/manual/data-modeling/schema-design-process/>
- Indexing Strategies  
  <https://www.mongodb.com/docs/manual/applications/indexes/>
- TTL Indexes  
  <https://www.mongodb.com/docs/manual/core/index-ttl/>
- Transactions  
  <https://www.mongodb.com/docs/manual/core/transactions/>

## 迁移工具

- Flyway Documentation  
  <https://documentation.red-gate.com/flyway>
- Liquibase Documentation  
  <https://docs.liquibase.com/>

迁移工具负责顺序、校验和执行机制，不替代数据库锁、兼容性和数据迁移设计。

## 使用原则

- 区分 SQL/数据库通用原则与数据库产品特性。
- Online、Concurrent、Instant 等术语含义由具体引擎和版本决定。
- 不根据开发环境小表执行时间推断生产锁风险。
- 任何会触发表扫描、表重写、长锁、全量回填的操作都应在代表性环境验证。
- 标准和官方文档变化时，优先更新 engine-specific 附录，而非扩大 SKILL.md。
