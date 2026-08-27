# 表设计评审：orders

## 基本信息

- 表/集合名称：`orders`
- Owner 团队：交易组
- 数据库/版本：PostgreSQL 16
- 业务实体：一笔商户交易
- 预计初始数据量：500 万行
- 日增长：约 3 万行
- 峰值读 QPS：800
- 峰值写 QPS：120
- 在线保留：2 年（之后归档）
- 敏感级别：中（含金额，不含卡数据）

## 业务不变量

- `amount` > 0 且与 `currency` 共同表达精确金额（不用 FLOAT）。
- `status` 只能按状态机转换：PENDING → CONFIRMED → SETTLED / CANCELLED。
- `(merchant_id, merchant_ref)` 全局唯一，防重复下单。
- `created_at` 由数据库 `DEFAULT now()` 维护，应用不覆写。

## 字段

| 字段 | 类型 | NULL | 默认值 | 单位/时区 | 说明 |
| --- | --- | --- | --- | --- | --- |
| id | BIGINT | NO | generated | — | 主键（雪花 ID） |
| merchant_id | BIGINT | NO | — | — | 商户外键 |
| merchant_ref | TEXT | NO | — | — | 商户请求引用，业务唯一键组成 |
| amount | NUMERIC(18,2) | NO | — | 最小货币单位可选 | 交易金额，不用 FLOAT |
| currency | CHAR(3) | NO | — | ISO 4217 | 货币代码 |
| status | TEXT | NO | 'PENDING' | — | 受 CHECK 约束 |
| created_at | TIMESTAMPTZ | NO | now() | UTC | 数据库维护 |
| updated_at | TIMESTAMPTZ | NO | now() | UTC | 触发器维护 |

## Key 与约束

- 主键：`id`
- 对外 ID：API 层暴露 `id` 为不透明字符串（不解析内部结构）
- 业务唯一键：`UNIQUE(merchant_id, merchant_ref)`
- 外键：`merchant_id REFERENCES merchants(id) ON DELETE RESTRICT`
- CHECK：`CHECK (amount > 0)`、`CHECK (status IN ('PENDING','CONFIRMED','SETTLED','CANCELLED'))`

## 查询模式

| Query | 频率 | 过滤 | 排序 | 返回规模 | 目标延迟 |
| --- | ---: | --- | --- | ---: | ---: |
| 按商户+引用查单笔 | 高 | merchant_id, merchant_ref | — | 1 | P99 ≤ 20ms |
| 商户订单列表 | 高 | merchant_id | created_at DESC | 分页 20 | P99 ≤ 100ms |
| 按状态统计 | 中 | status | — | 聚合 | P99 ≤ 500ms |

## 索引

| 索引 | 字段 | UNIQUE | 支持 Query | 写入成本说明 |
| --- | --- | --- | --- | --- |
| PK | id | 是 | 主键查找 | — |
| uq_orders_merchant_ref | (merchant_id, merchant_ref) | 是 | 单笔查询 + 防重 | 写入需维护 |
| idx_orders_merchant_created | (merchant_id, created_at DESC) | 否 | 商户列表分页 | 覆盖排序 |

## 生命周期

- 软删除：不使用（交易不可删除，CANCELLED 为终态）
- 归档：2 年后按 created_at 分区或批量迁移到归档表
- 物理删除：合规要求除外不物理删除
- 备份/PITR：RPO ≤ 5min，RTO ≤ 30min

## 风险

- 热点：单一高活跃商户可能造成 merchant_id 索引热点
- 并发：并发创建同一 merchant_ref 由 UNIQUE 约束保护
- 大字段：无
- 分区/分片：2 年后按 created_at 范围分区以支持归档淘汰
- 迁移：见 migration-plan.example.md
