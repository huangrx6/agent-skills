---
name: design-database-standards
description: "设计、审查和完善生产级数据库规范，重点覆盖关系型数据库的数据模型、命名、字段类型、主键与约束、索引、SQL、事务与并发、Schema 迁移、Expand-Migrate-Contract、在线 DDL、大表变更、数据回填、分区与分片、读副本、数据保留与归档、备份恢复、安全、性能、容量和数据库上线验收。用于制定组织级或项目级 PostgreSQL / MySQL 数据库规范、评审表结构与迁移方案、生成数据库检查清单与迁移模板，MongoDB 等文档数据库仅在明确需要时读取可选附录。API 契约设计、异常重试策略、代码书写规范与日志字段定义参考独立规范。"
---

# 数据库设计与变更规范

## 目标

产出**安全演进、可回滚/可前滚、可观测、可验证**的数据库设计与变更方案。优先解决最容易造成生产事故的问题，而不是罗列数据库所有功能。

## 默认范围

主规范面向事务型关系数据库，优先适配 PostgreSQL 和 MySQL。

只有项目明确使用文档数据库时，才读取 MongoDB 附录。缓存、搜索引擎、分析仓库和对象存储属于其他数据基础设施，不强行套用本规范。

## 工作流

1. 明确数据库类型、版本、数据量、增长率、峰值 QPS、读写比和可用性目标。
2. 先识别业务不变量、查询模式和生命周期，再设计表与索引。
3. 明确主键、业务唯一性、外键/约束、NULL、时间、金额和状态语义。
4. 对 SQL 和事务识别锁、隔离级别、慢查询、N+1 和批量边界。
5. 所有生产 Schema 变更先做兼容性分类；破坏性变更必须拆成多阶段发布。
6. 大表 DDL 和回填必须评估锁、表重写、临时空间、复制延迟和故障恢复。
7. 数据迁移使用可暂停、可恢复、幂等、限速、可校验的批处理。
8. 发布前验证备份/恢复、监控、回滚/前滚、数据一致性和新旧应用并存。
9. 只读取当前任务需要的参考文件。

## 核心规则

- 数据库 Schema 是持久化契约，不得假设应用与数据库会同时发布。
- 数据完整性优先通过数据库约束表达；唯一约束和非空约束必须在数据库层保障；引用完整性（外键）默认在应用层保障，仅在确定不分库分表且写入吞吐可接受时考虑数据库外键。
- 主键、业务唯一键和对外 ID 是不同概念；不要让可变业务字段承担主键职责。
- 字段类型必须表达真实语义；金额使用精确类型，时间明确时区，布尔不要用含糊字符串。
- NULL 必须有独立业务含义；不要用 NULL、空字符串、0 和特殊值混合表示“未知/不存在/未设置”。
- 索引由查询和约束驱动，不按“常用字段都加索引”；每个索引都有写入、空间和维护成本。
- SQL 必须参数化；生产查询不得依赖无上限结果集或不稳定分页。
- 事务必须尽量短；禁止在持有数据库锁的事务中执行不可控网络调用。
- 隔离级别由业务不变量决定；不要以“默认隔离级别”代替并发设计。
- 死锁、序列化失败等重试必须有边界且保证事务重放安全。
- 生产 DDL 必须先确认数据库版本的实际锁行为、是否表重写、是否支持在线/并发操作。
- 迁移默认使用 **Expand → Migrate → Contract**，先兼容扩展，再迁移流量/数据，最后删除旧结构。
- 大规模回填必须批量、限速、checkpoint、可暂停、可恢复并监控复制延迟和业务负载。
- 删除列、改类型、改唯一性、缩短长度等破坏性操作不得与依赖它的应用改动在同一步完成。
- 回滚不能依赖“把 DROP 的数据找回来”；破坏性迁移优先设计前滚修复与备份恢复路径。
- 备份只有经过定期恢复演练才能视为有效；RPO/RTO 必须可验证。
- 数据保留、归档和删除必须有明确责任方和容量上限，不能只靠磁盘告警临时处理。
- 分区、分片、读副本、CQRS 等复杂架构必须有容量或一致性证据，不作为默认设计。

## 参考文件选择

- 表、字段、命名、主键、NULL、时间、金额、枚举和审计列：读取 [references/data-modeling-types.md](references/data-modeling-types.md)。
- 唯一约束、外键、CHECK、索引、联合索引和查询模式：读取 [references/constraints-indexes.md](references/constraints-indexes.md)。
- SQL、分页、批量、事务、隔离、锁、死锁和读副本：读取 [references/sql-transactions-concurrency.md](references/sql-transactions-concurrency.md)。
- Schema 兼容性、迁移、在线 DDL、大表变更、回填和发布顺序：读取 [references/migrations-rollout.md](references/migrations-rollout.md)。
- 性能、容量、分区、分片、连接池和热点：读取 [references/performance-scaling.md](references/performance-scaling.md)。
- 安全、数据保留、归档、备份、PITR、恢复和容灾：读取 [references/security-retention-recovery.md](references/security-retention-recovery.md)。
- MongoDB/文档数据库：仅明确使用时读取 [references/document-database.md](references/document-database.md)。
- PostgreSQL/MySQL 差异与实施提示：读取 [references/engine-specific.md](references/engine-specific.md)。
- 测试、代码评审、迁移评审和上线验收：读取 [references/testing-review.md](references/testing-review.md)。
- 标准与官方文档：读取 [references/standards-sources.md](references/standards-sources.md)。
- 需要完整产出样例时：读取 [examples/README.md](examples/README.md) 下的虚构项目示范。

## 输出结构

完整数据库规范优先采用：

1. 适用范围与数据库版本；
2. 数据模型和命名；
3. 类型、约束和索引；
4. SQL、事务和并发；
5. Schema 迁移与数据回填；
6. 性能、容量与扩展；
7. 安全、保留和恢复；
8. 测试、监控和上线门禁；
9. 数据库引擎实施附录。

不要把某个数据库产品的特性描述为通用 SQL 要求。对于 DDL 锁和在线能力，必须以项目实际数据库版本的官方文档为准。

## 职责边界

- API 契约与版本兼容：不属本 Skill 范围。
- 异常重试与超时：不属本 Skill 范围。
- 代码书写规范：不属本 Skill 范围。
- 日志字段与审计衔接：不属本 Skill 范围。

本 Skill 负责“数据模型、约束、索引、SQL、事务、迁移、性能与恢复”，不复制上述领域的实施细节。

注：数据库事务隔离与锁属本 Skill；数据库对象命名（表/列/索引）属本 Skill；代码级线程安全属代码层；API 字段命名属 API 契约层。

## 内置资源

- [assets/database-naming-catalog.csv](assets/database-naming-catalog.csv)：对象命名目录。
- [assets/data-type-decision-matrix.csv](assets/data-type-decision-matrix.csv)：常见业务数据类型选择。
- [assets/migration-change-matrix.csv](assets/migration-change-matrix.csv)：Schema 变更风险与发布方式。
- [assets/database-review-checklist.csv](assets/database-review-checklist.csv)：设计与上线检查清单。
- [assets/table-design.template.md](assets/table-design.template.md)：表设计模板。
- [assets/migration-plan.template.md](assets/migration-plan.template.md)：生产迁移计划模板。
- `scripts/validate_database_standard.py`：校验目录和模板。

## 环境与运行

本 Skill 脚本统一通过 **uv** 运行（不使用宿主机的原始 Python，避免环境污染）。

- 所有脚本均为纯标准库，无需安装任何第三方包；uv 仅用于隔离 Python 解释器。
- uv 使用全局缓存（`~/.cache/uv`），**不会在每个 skill 目录创建 .venv**；Python 解释器与依赖在所有 skill 间共享，不重复下载。
- 固定路径约定：
  - uv 二进制：`~/.local/bin/uv`
  - 依赖与 Python 缓存：`~/.cache/uv`（全局共享）
  - Python 解释器：`~/.local/share/uv/python/`
  - 脚本：各 skill 的 `scripts/` 目录

首次使用前确保 uv 可用（不可用则自动安装，无需用户操作）：

```bash
python scripts/ensure_uv.py
# 或手动：curl -LsSf https://astral.sh/uv/install.sh | sh
```

统一运行方式：

```bash
uv run scripts/validate_database_standard.py assets/database-naming-catalog.csv --types assets/data-type-decision-matrix.csv --migration assets/migration-change-matrix.csv --review assets/database-review-checklist.csv --table-template assets/table-design.template.md --migration-template assets/migration-plan.template.md
uv run python -m unittest discover -s scripts/tests   # 跑测试
```
