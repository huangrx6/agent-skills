# 示例：数据库设计与迁移产出样例（虚构项目）

> 本项目设定：虚构公司 "NovaPay"（与其他 skill 示例同项目），PostgreSQL 16。
> 演示用本 skill 产出的表设计评审 + 生产迁移计划形态。
> **本示例不抄用、仅作参照——实际项目以自身约束、数据库版本和官方文档为准。**

## 文件

- `table-design.example.md` — 订单表设计评审（对齐 table-design.template）
- `migration-plan.example.md` — 订单表新增"结算币种"列的 Expand-Migrate-Contract 迁移

## 要点

1. **先不变量后表结构**：示例先列业务不变量（金额精度、状态合法转换），再设计字段与约束。
2. **金额用 NUMERIC**：不用 FLOAT；保存货币代码 + scale 对齐结算规则。
3. **迁移走 Expand-Migrate-Contract**：加 nullable 列 → 双写回填 → 校验 → NOT NULL → 删旧依赖，不一步到位。
4. **回填幂等 + checkpoint**：按主键游标分批，可暂停恢复，监控复制延迟。
5. **破坏性操作前向修复**：DROP 前确认 PITR 覆盖；不依赖"找回 DROP 数据"。
