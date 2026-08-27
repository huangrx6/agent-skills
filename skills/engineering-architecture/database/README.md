# Database

> Parent: [`engineering-architecture`](../SKILL.md). Spec for relational schema, indexes, transactions, migrations, Expand-Migrate-Contract, online DDL, retention, backup.

## What this is

Spec for designing and evolving production databases — primarily PostgreSQL and MySQL. Covers data modeling, types, primary keys, constraints, indexes, SQL, transactions, migrations, online DDL, large-table changes, partitioning, replication, retention, backup/recovery, security, performance, capacity, and acceptance. MongoDB appendix for explicit document-database use.

## How to invoke

```text
使用 $engineering-architecture/database 帮我 <做什么>
```

| You say | Agent does |
| --- | --- |
| 设计一张新表 | copy `table-design.template.md`; load `data-modeling-types.md` + `constraints-indexes.md` + `database-naming-catalog.csv` |
| 评审一张表 | load `database-review-checklist.csv`; check naming / types / keys / indexes / lifecycle / risks |
| 写 migration plan | copy `migration-plan.template.md`; load `migrations-rollout.md`; classify as Expand / Migrate / Contract |
| 做大表 DDL | load `migrations-rollout.md` (large-table DDL section); pick strategy by engine and version |
| 数据回填 | load `migrations-rollout.md` (backfill section); define batch size, retry, kill switch |
| 加索引 | load `constraints-indexes.md` + `migrations-rollout.md`; prefer CREATE INDEX CONCURRENTLY (Postgres) / INVISIBLE first (MySQL) |
| 改字段类型 | use Expand-Migrate-Contract: add new column, dual-write, switch reads, drop old |
| 排查慢 SQL | load `performance-scaling.md`; explain plan, index review, hot row check |
| 备份与恢复 | load `security-retention-recovery.md`; define RPO / RTO / PITR strategy |
| 容量规划 | use capacity / load test from `engineering-reliability/performance-capacity/` |

## Core principles

- Do not assume application and schema switch in lockstep. Production changes must work with old app + new schema, new app + old schema, in-flight requests, read replicas, CDC, and offline jobs.
- Prefer Expand-Migrate-Contract over in-place destructive changes. Add new column → dual-write → backfill → switch reads → drop old.
- Use the most restrictive type that satisfies the business invariant. `NUMERIC` for money, never `FLOAT`. `TIMESTAMPTZ` for instants, never `TIMESTAMP`.
- Primary keys are stable, opaque, internal. Expose a separate external ID. Never let clients parse the internal structure.
- Business unique keys go on a separate `UNIQUE` index. Do not overload the primary key.
- Indexes serve real query patterns. Unused indexes are write cost. High-cardinality columns in metrics belong in traces/logs, not metrics labels.
- Migrations must be idempotent, forward-only by default. Forward and backward paths are both tested. Rollback path is documented even if never executed.
- New SQL goes through parameterized queries. ORM "raw" queries must keep parameter binding. User-supplied sort / table / column must use allowlist mapping, not string concatenation.
- Data classification drives retention. PII, payment data, audit logs have separate retention and access rules.
- Backup, PITR, and restore drills are routine. RPO / RTO are stated, not assumed.
- Database-specific behavior follows the project's actual engine and version, not generic advice. Read `engine-specific.md` and the official docs.

## Quick reference

### Type decision (examples)

| Field | Use | Avoid |
| --- | --- | --- |
| Money | `NUMERIC(precision, scale)` | `FLOAT`, `DOUBLE` |
| Instant | `TIMESTAMPTZ` (UTC) | `TIMESTAMP` (no TZ) |
| ID (internal) | `BIGINT GENERATED` / `UUID v7` | table name, business field |
| Status enum | `TEXT` + `CHECK` | `INT` magic numbers |
| JSON payload | `JSONB` with explicit shape, not free blob | `TEXT` with hidden schema |

Full decision matrix: [`../assets/database/data-type-decision-matrix.csv`](../assets/database/data-type-decision-matrix.csv).

### Migration classification

| Change | Strategy |
| --- | --- |
| Add nullable column | single DDL |
| Add NOT NULL column with default | add nullable → backfill → set NOT NULL (Postgres 11+) |
| Rename column | dual-write with old + new → switch reads → drop old |
| Change column type | add new column → dual-write → backfill → switch → drop old |
| Add index | `CREATE INDEX CONCURRENTLY` (Postgres) / `INVISIBLE` first (MySQL) |
| Drop index | drop with monitoring window first |
| Drop column | mark deprecated → drop after release window |
| Drop table | archive → revoke access → rename → drop |

Full guidance: [`../references/database/migrations-rollout.md`](../references/database/migrations-rollout.md).

### Online DDL strategy by engine

| Engine | Strategy | Watch out for |
| --- | --- | --- |
| PostgreSQL | `ALTER TABLE ... ADD COLUMN ... DEFAULT` (PG 11+ is metadata-only); `CREATE INDEX CONCURRENTLY`; partition for hot tables | default rewriting on older versions; long lock for type change |
| MySQL 8 | `ALGORITHM=INPLACE, LOCK=NONE` where supported; `INVISIBLE` index first | some DDL still copies table; online DDL cost depends on operation |

Full guide: [`../references/database/engine-specific.md`](../references/database/engine-specific.md).

### Review checklist categories

`database-review-checklist.csv` covers: data type, key / constraint, query pattern coverage, index cost, lifecycle, security, partition, retention, migration plan, acceptance criteria.

## Reference index

| File | When to load |
| --- | --- |
| [`../references/database/data-modeling-types.md`](../references/database/data-modeling-types.md) | Type choice, naming, primary key patterns, business invariants |
| [`../references/database/constraints-indexes.md`](../references/database/constraints-indexes.md) | CHECK / UNIQUE / FK / index design / query pattern coverage |
| [`../references/database/sql-transactions-concurrency.md`](../references/database/sql-transactions-concurrency.md) | Isolation levels, locking, deadlock, retries |
| [`../references/database/migrations-rollout.md`](../references/database/migrations-rollout.md) | Expand-Migrate-Contract, large-table DDL, backfill, rollback |
| [`../references/database/performance-scaling.md`](../references/database/performance-scaling.md) | Slow query, hot row, partition, read replica, sharding |
| [`../references/database/security-retention-recovery.md`](../references/database/security-retention-recovery.md) | Auth, encryption, retention, backup, PITR |
| [`../references/database/engine-specific.md`](../references/database/engine-specific.md) | PostgreSQL vs MySQL behavior differences |
| [`../references/database/document-database.md`](../references/database/document-database.md) | MongoDB appendix (load only when project uses MongoDB) |
| [`../references/database/testing-review.md`](../references/database/testing-review.md) | Migration testing, schema diff, rollback test |
| [`../references/database/standards-sources.md`](../references/database/standards-sources.md) | PostgreSQL / MySQL / MongoDB / Flyway / Liquibase official docs |

## Asset index

| File | Purpose |
| --- | --- |
| [`../assets/database/table-design.template.md`](../assets/database/table-design.template.md) | Table design review template |
| [`../assets/database/migration-plan.template.md`](../assets/database/migration-plan.template.md) | Migration plan template |
| [`../assets/database/data-type-decision-matrix.csv`](../assets/database/data-type-decision-matrix.csv) | Type decision matrix |
| [`../assets/database/database-naming-catalog.csv`](../assets/database/database-naming-catalog.csv) | Naming rules catalog |
| [`../assets/database/migration-change-matrix.csv`](../assets/database/migration-change-matrix.csv) | Migration classification and risk |
| [`../assets/database/database-review-checklist.csv`](../assets/database/database-review-checklist.csv) | Database review checklist |

## Validation

```bash
uv run scripts/database/validate_database_standard.py \
  ../assets/database/database-naming-catalog.csv \
  --types ../assets/database/data-type-decision-matrix.csv \
  --migration ../assets/database/migration-change-matrix.csv \
  --review ../assets/database/database-review-checklist.csv \
  --table-template ../assets/database/table-design.template.md \
  --migration-template ../assets/database/migration-plan.template.md

uv run python -m unittest discover -s scripts/database/tests
```

## Worked example

[`../examples/database/table-design.example.md`](../examples/database/table-design.example.md) — concrete `orders` table on PostgreSQL 16: type choices, business invariants, query patterns, index plan, lifecycle, risks.

[`../examples/database/migration-plan.example.md`](../examples/database/migration-plan.example.md) — Expand-Migrate-Contract walkthrough for changing a column type.
