---
name: engineering-architecture
description: "用户说\"画架构图 / 选单体还是微服务 / 评审架构方案 / 写 ADR / 划分服务或模块边界 / 选部署形态 / 做技术选型 / 跨团队系统集成 / 重构或拆分系统 / 治理架构文档 / 设计或评审 API 契约 / 设计或评审数据库 schema 和迁移 / 写或评审工程文档 / 规范 Git 工作流 / 做版本发布\"时激活。覆盖模块与边界、架构风格选择、API 契约、数据库设计、迁移安全、工程文档体系、Git 工作流。不要用它做：性能与容量目标 → engineering-reliability；安全威胁建模与代码评审 → engineering-security；代码风格与 lint → engineering-quality。"
---

# 工程架构

## 目标

为软件系统建立可演进、可沟通、可治理的工程骨架：清晰的模块/服务边界、稳定的 API 契约、可演进的数据库、长期可维护的文档、可重复的 Git 工作流。

## 职责边界

本 skill 负责"系统骨架与契约"：

- 模块与服务的划分、依赖方向、数据所有权；
- 架构风格（模块化单体、微服务、分层、六边形、事件驱动、CQRS、事件溯源）的选择与权衡；
- API 契约风格（REST/gRPC/GraphQL/WebSocket/SSE/Webhook/JSON-RPC/Event）、Schema、版本、错误响应；
- 数据库建模、约束、索引、迁移、扩容、回填、备份；
- 工程文档分层（README/AGENTS/PROJECT_CONTEXT/docs/index）、ADR、handoff 流程；
- Git 分支模型、提交信息规范、worktree 隔离、危险操作门控、发布。

不负责：异常分类与错误码、监控告警与 SLO、性能与容量压测、代码风格与 lint。

## 何时使用（用户原话触发）

| 用户说 | 进入本 skill 哪个子主题 |
| --- | --- |
| 画架构图、模块边界、服务边界 | architecture |
| 选单体 vs 微服务、选分层/六边形/CQRS | architecture |
| 写 ADR、架构评审、技术选型 | architecture |
| 评审 OpenAPI/Proto/GraphQL Schema | api-contracts |
| API 错误响应、幂等、分页、Webhook 签名 | api-contracts |
| 数据库表设计、索引、迁移、回填 | database |
| Schema 变更不兼容、Online DDL | database |
| README / AGENTS.md / PROJECT_CONTEXT / docs 目录 | documentation |
| ADR 模板、Handoff 模板 | documentation |
| 分支策略、提交信息、merge/rebase、reset 恢复 | git |
| Worktree 隔离、force push 规范 | git |

## 何时不要使用（路由到其它 skill）

| 用户说 | 跳到 |
| --- | --- |
| 服务挂了、报错、超时 | engineering-reliability |
| 加监控告警、加 SLO/SLI | engineering-reliability |
| 性能压测、容量规划、慢 SQL 排查 | engineering-reliability |
| SQL 注入、密钥管理、XSS/CSRF/SSRF、代码评审安全 | engineering-security |
| 代码风格、命名、lint、配置中心、Feature Flag | engineering-quality |

## 工作流

1. 先确认问题驱动和约束（业务目标、团队、时间、合规），不先选风格。
2. 划分业务能力边界和数据所有权，落地为 ADR 或 architecture brief。
3. 同步定义 API 契约（resources、Schema、错误响应）和数据库 Schema（表、约束、迁移）。
4. 把架构决策、ADR、Handoff 写进 docs 体系，确保新成员和 AI Agent 能在 PROJECT_CONTEXT 找到入口。
5. Git 流程和 worktree 隔离按团队决策落地；高风险操作有 reflog 兜底。

## 核心原则

- 业务能力和质量属性驱动架构，技术栈不能反向定义边界。
- 优先模块化单体；只有独立部署、独立扩缩、故障隔离、团队自治或明确业务边界等收益足够时才拆服务。
- 同一事实只存在一个 canonical source；其它位置用链接或摘要。
- ADR 记录重要决定；过时 ADR 标记 superseded，不删除历史。
- Git 不可逆操作必须有恢复点；共享分支禁止 rebase/force push。

## 子主题与资源入口

- **architecture**：`references/architecture/` + `assets/architecture/` + `scripts/architecture/`
- **api-contracts**：`references/api-contracts/` + `assets/api-contracts/` + `scripts/api-contracts/`
- **database**：`references/database/` + `assets/database/` + `scripts/database/`
- **documentation**：`references/documentation/` + `assets/documentation/` + `scripts/documentation/`
- **git**：[`git/README.md`](git/README.md) + `references/git/` + `assets/git/` + `scripts/git/`

完整示例见 `examples/<sub>/`。

## 环境与运行

脚本统一通过 `uv` 运行（PEP 723 / `# /// script` 声明，无第三方依赖）。

```bash
uv run scripts/<sub>/validate_*.py --<args>
uv run python -m unittest discover -s scripts/tests
```

uv 缓存全局共享（`~/.cache/uv`），不会在每个 skill 目录创建 .venv。
