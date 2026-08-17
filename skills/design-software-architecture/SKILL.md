---
name: design-software-architecture
description: "设计、评审和演进软件系统架构，包括架构约束与质量属性、模块和服务边界、模块化单体与微服务选择、分层/六边形/事件驱动/CQRS 等架构风格、同步与异步集成、数据所有权与一致性、可用性/扩展性/性能/安全/可运维性、部署拓扑、故障域、遗留系统现代化、ADR、C4 架构图、架构风险和评审门禁。用于新系统架构设计、现有系统重构、单体拆分、微服务边界评审、跨团队系统集成、重大技术选型和架构文档治理。不覆盖 API 契约细节、数据库表结构、异常处理、日志格式与代码级书写规范。"
---

# 软件架构设计

## 目标

先识别业务驱动、约束和质量属性，再做最小充分的架构决策。输出必须能指导开发、部署、运维和演进，而不是只产生架构图或模式名称。

## 工作流

1. 建立系统上下文：用户、外部系统、核心业务能力、数据和信任边界。
2. 记录不可忽略的约束：合规、预算、团队、交付周期、现有平台、延迟、容量和兼容要求。
3. 把质量属性写成可验证场景，不接受“高性能、高可用、高扩展”作为完整要求。
4. 划分业务与模块边界，明确所有权、公共接口和禁止依赖。
5. 选择部署形态和架构风格；优先简单方案，不默认微服务。
6. 设计同步/异步集成、数据所有权、一致性和失败边界。
7. 设计容量、故障域、安全、可观测性和运维路径。
8. 对关键决策写 ADR，记录备选方案、理由、代价和退出条件。
9. 只绘制能支持沟通和决策的架构视图。
10. 用风险登记、架构适应度检查和评审清单验证方案。
11. 对遗留系统采用渐进演进，不进行无退出策略的大爆炸重写。

## 核心原则

- 业务能力和质量属性驱动架构，技术栈不能反向定义业务边界。
- 优先模块化单体；只有独立部署、独立扩缩、故障隔离、团队自治或明确业务边界等收益足以覆盖分布式成本时才拆服务。
- 服务边界优先围绕稳定业务能力和数据所有权，不按表、Controller、技术层或团队人数机械拆分。
- 每份核心业务数据必须有明确权威 Owner；跨边界访问通过契约，不直接读写其他模块或服务的私有存储。
- 同步调用链保持短小；跨多个故障域的业务流程优先重新设计，而不是无限串联 RPC。
- 异步通信用于时间解耦、削峰、广播或工作流，不用于隐藏不清晰的职责和一致性需求。
- 分布式事务不是默认方案；优先局部事务、幂等、Outbox/Inbox、补偿和显式最终一致性。
- 共享数据库、共享可变缓存、共享内部模型和跨服务事务会重新建立强耦合，应视为架构风险。
- CQRS、Event Sourcing、Service Mesh、Saga 等只在明确问题存在时采用，不作为“先进架构”标配。
- 架构必须定义故障模式、降级边界、恢复路径和容量上限，而不只描述正常流程。
- 安全、隐私和多租户隔离必须在边界设计阶段进入架构，不在上线前补充。
- 可观测性、可部署性和可回滚性属于架构质量，不是运维团队的后置工作。
- 架构决策必须可追溯；重要选择用 ADR 记录，过时 ADR 标记为 superseded 而不是删除历史。
- 图的价值在于回答问题；不为完整性绘制无人维护的代码级架构图。
- 架构文档必须随系统演进，无法验证或无人负责的图和文档应删除或自动生成。

## 参考文件选择

- 做完整架构设计、需求澄清和决策流程：读取 [references/architecture-workflow.md](references/architecture-workflow.md)。
- 划分模块、Bounded Context、服务和团队边界：读取 [references/boundaries-modularity.md](references/boundaries-modularity.md)。
- 选择模块化单体、微服务、分层、六边形、事件驱动、CQRS 等：读取 [references/architecture-styles.md](references/architecture-styles.md)。
- 设计同步/异步调用、工作流、消息和分布式失败：读取 [references/integration-distributed.md](references/integration-distributed.md)。
- 处理数据库归属、读模型、缓存和一致性：读取 [references/data-ownership-consistency.md](references/data-ownership-consistency.md)。
- 定义可用性、性能、扩展、安全、可维护性等质量属性：读取 [references/quality-attributes.md](references/quality-attributes.md)。
- 设计部署单元、故障域、灰度、扩缩和遗留现代化：读取 [references/deployment-evolution.md](references/deployment-evolution.md)。
- 编写 ADR、C4 图、架构说明和风险记录：读取 [references/documentation-adrs.md](references/documentation-adrs.md)。
- 做架构评审、例外审批和持续治理：读取 [references/review-governance.md](references/review-governance.md)。
- 需要权威来源和术语依据：读取 [references/standards-sources.md](references/standards-sources.md)。
- 需要完整产出样例时：读取 [examples/README.md](examples/README.md) 下的虚构项目示范。

## 职责边界

- API、REST/gRPC/GraphQL/WebSocket/Event 契约细节：不属本 Skill 范围。
- 表、索引、事务、数据库迁移和回填：不属本 Skill 范围。
- 异常分类、错误码、重试和超时：不属本 Skill 范围。
- 日志格式、脱敏、轮转和保留：不属本 Skill 范围。
- 类、函数、命名、注释和代码级设计模式：不属本 Skill 范围。

架构 Skill 负责“边界与系统级决策”，不要复制上述领域 的实施细则。

注：ADR 的架构决策内容（为什么选这个方案）属本 Skill；ADR 文档的放置、生命周期、索引与 AI 发现属文档管理层。

## 内置资源

- [assets/adr.template.md](assets/adr.template.md)：架构决策记录模板。
- [assets/architecture-brief.template.md](assets/architecture-brief.template.md)：轻量架构说明模板。
- [assets/architecture-decision-matrix.csv](assets/architecture-decision-matrix.csv)：架构风格选择矩阵。
- [assets/quality-attribute-scenarios.csv](assets/quality-attribute-scenarios.csv)：质量属性场景模板。
- [assets/architecture-risk-register.csv](assets/architecture-risk-register.csv)：架构风险登记表。
- [assets/architecture-review-checklist.csv](assets/architecture-review-checklist.csv)：架构评审清单。
- `scripts/validate_architecture_catalog.py`：校验目录和模板。

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
uv run scripts/validate_architecture_catalog.py --decision assets/architecture-decision-matrix.csv --quality assets/quality-attribute-scenarios.csv --risk assets/architecture-risk-register.csv --review assets/architecture-review-checklist.csv --adr assets/adr.template.md --brief assets/architecture-brief.template.md
uv run python -m unittest discover -s scripts/tests   # 跑测试
```

