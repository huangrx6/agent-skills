# PROJECT_CONTEXT（NovaPay · 稳定快照）

> 工具无关的项目知识入口。新 AI 会话先读本文件 + docs/index.md。
> 本文件是有界快照，不保存临时进度或任务流水账。

## Purpose

商户收款、资金清算与对账平台。日均 100 万笔交易，2 组 8 人团队。

## Repository Map

```
novapay-server/       # 模块化单体（交易/清算/商户/审计）
novapay-apps/         # 商户后台 + 收银终端
docs/                 # 长期文档（见 docs/index.md）
```

## Stack

- Java 21 + Spring Boot；PostgreSQL；Outbox 队列；单云厂商。

## Architecture Summary

模块化单体 + 清算任务队列（ADR-001）。交易受理与清算分离故障域。
详见 `docs/architecture/overview.md`。

## Domain Vocabulary

- Trade：一笔交易（merchantRef + amount 唯一键）。
- Settlement：清算批次。
- 术语表见 `docs/project/glossary.md`。

## Critical Invariants

- 交易写入强一致；对账读模型最终一致（99.9% 5 秒内可见）。
- 卡数据不落库，token 化处理（PCI-DSS）。
- 跨模块只经公开契约，禁止直接写他模块表。

## Common Commands

```bash
cd novapay-server && mvn test
cd novapay-apps && pnpm dev
```

## Canonical Docs

- 架构：`docs/architecture/overview.md`
- 契约：`docs/contracts/index.md`
- 数据：`docs/data/ownership.md`
- 运维：`docs/operations/overview.md`

## Known Sharp Edges

- 单库容量上限（ADR-001 revisit 条件之一）。
- 清算 worker 积压时对账可能超时（见 runbook）。
